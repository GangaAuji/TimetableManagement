"""Institution scope for the signed-in user. See docs/DESIGN_INSTITUTIONS.md.

Permissions say what a user may do; scope says which institution's rows
they see while doing it. The two combine: a Super Admin sees everything
(`organization_wide`) and may pick one institution to work in; everyone
else sees the institutions they are a member of, which is almost always one.

Only the chosen institution is kept in the session (`institution_id`).
Memberships are read on each request that needs them and cached on `g`, so
a change to a user's memberships applies immediately.
"""

from dataclasses import dataclass, field

from flask import g, has_request_context, session

from data_access import institutions as store

SESSION_KEY = 'institution_id'
_CACHE_KEY = '_institution_scope'


@dataclass(frozen=True)
class Scope:
    institution_id: int | None
    visible: tuple = field(default_factory=tuple)
    organization_wide: bool = False
    multiple: bool = False  # the tenant has more than one active institution

    @property
    def enabled(self):
        """False when the tenant has one institution: every predicate is `1=1`."""
        return self.multiple

    def allows(self, institution_id):
        """Whether a row owned by `institution_id` is in scope; the same rule `clause()` applies in SQL."""
        if institution_id is None or not self.multiple:
            return True
        if self.institution_id is not None:
            return int(institution_id) == self.institution_id
        if self.organization_wide:
            return True
        return int(institution_id) in self.visible

    def clause(self, column):
        """SQL fragment and params restricting `column` to what this scope sees."""
        if not self.multiple:
            return '1=1', ()
        if self.institution_id is not None:
            return f'{column} = %s', (self.institution_id,)
        if self.organization_wide:
            return '1=1', ()
        if not self.visible:
            return '1=0', ()
        marks = ', '.join(['%s'] * len(self.visible))
        return f'{column} IN ({marks})', tuple(self.visible)

    def course_clause(self, alias='c'):
        """Courses whose department the scope sees (a course belongs to its department's institution)."""
        clause, params = self.clause('institution_id')
        if clause == '1=1':
            return '1=1', ()
        return f'{alias}.department_id IN (SELECT id FROM departments WHERE {clause})', params

    def student_clause(self, alias='s'):
        clause, params = self.course_clause('c')
        if clause == '1=1':
            return '1=1', ()
        return f'{alias}.course_id IN (SELECT c.id FROM courses c WHERE {clause})', params

    def rooms_clause(self, alias='r'):
        """Rooms the current institution may timetable (own, organization-wide, or listed to it)."""
        if not self.multiple or self.institution_id is None:
            return '1=1', ()
        return store.candidate_rooms_clause(self.institution_id, alias)

    def faculty_clause(self, alias='f', department_alias='fd'):
        if not self.multiple or self.institution_id is None:
            return '1=1', ()
        return store.candidate_faculty_clause(self.institution_id, alias, department_alias)

    def as_dict(self):
        return {
            'institution_id': self.institution_id,
            'visible': list(self.visible),
            'organization_wide': self.organization_wide,
            'multiple': self.multiple,
        }


SINGLE = Scope(institution_id=None, visible=(), organization_wide=True, multiple=False)


def _fallback_institution(cursor, flask_session):
    """Institution for a user with no membership row: their department's, their course's, else the first."""
    role = flask_session.get('role')
    if role == 'Student' and flask_session.get('course_id'):
        found = store.institution_of_course(cursor, flask_session['course_id'])
        if found:
            return found
    if role == 'Teacher' and flask_session.get('faculty_id'):
        found = store.institution_of_faculty(cursor, flask_session['faculty_id'])
        if found:
            return found
    if flask_session.get('department_id'):
        found = store.institution_of_department(cursor, flask_session['department_id'])
        if found:
            return found
    return store.first_institution_id(cursor)


def visible_institutions(cursor, flask_session):
    """Ids the signed-in user may work in, primary first. Empty for a Super Admin (sees all)."""
    if flask_session.get('role') == 'Super Admin':
        return ()
    user_id = flask_session.get('user_id')
    rows = store.fetch_memberships(cursor, user_id) if user_id else []
    ids = tuple(int(row['institution_id']) for row in rows if row.get('is_active'))
    if ids:
        return ids
    fallback = _fallback_institution(cursor, flask_session)
    return (fallback,) if fallback else ()


def build_scope(cursor, flask_session):
    multiple = store.count_active_institutions(cursor) > 1
    organization_wide = flask_session.get('role') == 'Super Admin'
    chosen = flask_session.get(SESSION_KEY)
    chosen = int(chosen) if isinstance(chosen, int) and not isinstance(chosen, bool) and chosen > 0 else None
    if not multiple:
        return Scope(institution_id=None, visible=(), organization_wide=organization_wide, multiple=False)
    if organization_wide:
        return Scope(institution_id=chosen, visible=(), organization_wide=True, multiple=True)
    visible = visible_institutions(cursor, flask_session)
    if chosen not in visible:
        chosen = visible[0] if visible else None
    return Scope(institution_id=chosen, visible=visible, organization_wide=False, multiple=True)


def current_scope(cursor=None):
    """Scope for this request, computed once. Outside a request (or with no institutions table) everything is visible."""
    if has_request_context() and _CACHE_KEY in g:
        return g.get(_CACHE_KEY)
    if not has_request_context() or 'user_id' not in session:
        return SINGLE
    owns = cursor is None
    connection = None
    try:
        if owns:
            from extensions import get_db_connection
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
        if not store.table_exists(cursor):
            scope = SINGLE
        else:
            scope = build_scope(cursor, session)
    finally:
        if owns:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
    setattr(g, _CACHE_KEY, scope)
    return scope


def forget():
    if has_request_context() and _CACHE_KEY in g:
        g.pop(_CACHE_KEY)


def choose_institution(cursor, flask_session, institution_id):
    """Set the session's institution. Returns the id kept, or raises ValueError when it is not allowed."""
    forget()
    if institution_id is None:
        if flask_session.get('role') != 'Super Admin':
            raise ValueError('institution_required')
        flask_session.pop(SESSION_KEY, None)
        return None
    institution = store.fetch_institution(cursor, institution_id)
    if institution is None or not institution.get('is_active'):
        raise ValueError('institution_not_found')
    if flask_session.get('role') != 'Super Admin' and int(institution_id) not in visible_institutions(cursor, flask_session):
        raise ValueError('institution_forbidden')
    flask_session[SESSION_KEY] = int(institution_id)
    return int(institution_id)


def apply_at_login(cursor, flask_session):
    """Pick the institution for a session that was just opened. Safe on databases without the tables."""
    try:
        if not store.table_exists(cursor):
            return
        if flask_session.get('role') == 'Super Admin':
            flask_session.pop(SESSION_KEY, None)
            return
        visible = visible_institutions(cursor, flask_session)
        if visible:
            flask_session[SESSION_KEY] = visible[0]
    except Exception:
        from flask import current_app
        current_app.logger.exception('Could not pick an institution at sign-in')
