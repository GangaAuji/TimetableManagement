"""Institutions without a database: the scope predicates, the revision 0014 planner,
sign-in and switcher behaviour against a fake cursor, the sharing predicates and
the joint solver's per-cohort room pools."""

import importlib.util
from pathlib import Path

import pytest

from core import scope as scope_module
from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision
from core.scope import SINGLE, Scope, apply_at_login, build_scope, choose_institution
from data_access import institutions as store
from services.timetable import joint_solver


# Scope predicates ---------------------------------------------------------------

def test_single_institution_tenant_sees_everything_with_no_predicates():
    assert SINGLE.enabled is False
    assert SINGLE.clause('d.institution_id') == ('1=1', ())
    assert SINGLE.course_clause() == ('1=1', ())
    assert SINGLE.student_clause() == ('1=1', ())
    assert SINGLE.rooms_clause() == ('1=1', ())
    assert SINGLE.faculty_clause() == ('1=1', ())
    assert SINGLE.allows(7) and SINGLE.allows(None)
    one = Scope(institution_id=3, visible=(3,), multiple=False)
    assert one.clause('x') == ('1=1', ()) and one.allows(9)


def test_chosen_institution_restricts_every_predicate_to_it():
    scope = Scope(institution_id=2, visible=(2, 5), multiple=True)
    assert scope.clause('d.institution_id') == ('d.institution_id = %s', (2,))
    sql, params = scope.course_clause('c')
    assert sql == 'c.department_id IN (SELECT id FROM departments WHERE institution_id = %s)' and params == (2,)
    sql, params = scope.student_clause('s')
    assert sql.startswith('s.course_id IN (SELECT c.id FROM courses c WHERE c.department_id IN') and params == (2,)
    assert scope.allows(2) and not scope.allows(5) and not scope.allows(9)
    assert scope.allows(None)
    rooms_sql, rooms_params = scope.rooms_clause('r')
    assert "r.sharing = 'organization'" in rooms_sql and rooms_params == (2, 2)
    faculty_sql, faculty_params = scope.faculty_clause('f', 'fd')
    assert 'fd.institution_id = %s' in faculty_sql and faculty_params == (2, 2)


def test_member_of_several_institutions_without_a_choice_sees_all_of_them():
    scope = Scope(institution_id=None, visible=(4, 6), multiple=True)
    assert scope.clause('r.institution_id') == ('r.institution_id IN (%s, %s)', (4, 6))
    assert scope.allows(4) and scope.allows(6) and not scope.allows(5)
    # No chosen institution: candidate predicates fall back to the visible set rather than sharing.
    assert scope.rooms_clause() == ('1=1', ())
    assert Scope(institution_id=None, visible=(), multiple=True).clause('x') == ('1=0', ())


def test_super_admin_sees_the_organization_until_they_pick_an_institution():
    wide = Scope(institution_id=None, organization_wide=True, multiple=True)
    assert wide.clause('d.institution_id') == ('1=1', ())
    assert wide.allows(1) and wide.allows(99)
    picked = Scope(institution_id=3, organization_wide=True, multiple=True)
    assert picked.clause('d.institution_id') == ('d.institution_id = %s', (3,))
    assert picked.allows(3) and not picked.allows(4)
    assert picked.as_dict() == {'institution_id': 3, 'visible': [], 'organization_wide': True, 'multiple': True}


# Fake cursor for the store-backed helpers -----------------------------------------

class _Cursor:
    """Answers the store's queries from a small in-memory tenant."""

    def __init__(self, *, institutions, memberships=(), tables=True):
        self.institutions = {row['id']: row for row in institutions}
        self.memberships = list(memberships)
        self.tables = tables
        self.rows = []
        self.one = None
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        text = ' '.join(sql.split())
        if 'information_schema.TABLES' in text:
            self.one = {'n': 1 if self.tables else 0} if 'COUNT' in text else ((1,) if self.tables else None)
            self.rows = [self.one] if self.one else []
        elif text.startswith('SELECT COUNT(*) AS n FROM institutions'):
            self.one = {'n': sum(1 for row in self.institutions.values() if row['is_active'])}
        elif 'FROM institution_memberships' in text and 'JOIN institutions' in text:
            user_id = params[0]
            self.rows = [
                {**self.institutions[m['institution_id']], 'institution_id': m['institution_id'], 'is_primary': m['is_primary'], 'membership_role': m['role']}
                for m in sorted(self.memberships, key=lambda m: -m['is_primary']) if m['user_id'] == user_id
            ]
        elif 'FROM institutions i WHERE i.id = %s' in text:
            self.one = self.institutions.get(params[0])
        elif 'FROM institutions' in text and 'ORDER BY' in text and 'LIMIT 1' in text:
            active = sorted((row for row in self.institutions.values() if row['is_active']), key=lambda r: (r['sort_order'], r['id']))
            self.one = {'id': active[0]['id']} if active else None
        else:
            self.one = None
            self.rows = []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows

    def close(self):
        pass


def _institution(institution_id, *, active=True, sort_order=0):
    return {'id': institution_id, 'organization_id': 1, 'name': f'College {institution_id}', 'code': f'C{institution_id}',
            'short_name': None, 'is_active': 1 if active else 0, 'sort_order': sort_order}


def _membership(user_id, institution_id, *, primary=False, role='Admin'):
    return {'user_id': user_id, 'institution_id': institution_id, 'is_primary': 1 if primary else 0, 'role': role}


def test_store_queries_the_fake_cursor_answers(monkeypatch):
    """Guard: the fake answers the exact store queries the scope relies on."""
    cursor = _Cursor(institutions=[_institution(1), _institution(2, active=False)], memberships=[_membership(9, 1, primary=True)])
    assert store.table_exists(cursor) is True
    assert store.count_active_institutions(cursor) == 1
    assert store.first_institution_id(cursor) == 1
    assert store.fetch_institution(cursor, 2)['is_active'] == 0
    assert [row['institution_id'] for row in store.fetch_memberships(cursor, 9)] == [1]
    assert store.fetch_memberships(cursor, 8) == []


# Sign-in and the switcher ------------------------------------------------------------

def test_sign_in_on_a_single_institution_tenant_still_records_the_institution():
    cursor = _Cursor(institutions=[_institution(1)], memberships=[_membership(5, 1, primary=True)])
    session = {'user_id': 5, 'role': 'Admin'}
    apply_at_login(cursor, session)
    assert session['institution_id'] == 1
    assert build_scope(cursor, session) == Scope(institution_id=None, visible=(), organization_wide=False, multiple=False)


def test_sign_in_picks_the_primary_membership_and_super_admin_starts_organization_wide():
    cursor = _Cursor(
        institutions=[_institution(1), _institution(2)],
        memberships=[_membership(5, 2), _membership(5, 1, primary=True)],
    )
    session = {'user_id': 5, 'role': 'Admin'}
    apply_at_login(cursor, session)
    assert session['institution_id'] == 1
    scope = build_scope(cursor, session)
    assert (scope.institution_id, scope.visible, scope.organization_wide, scope.multiple) == (1, (1, 2), False, True)

    boss = {'user_id': 1, 'role': 'Super Admin', 'institution_id': 2}
    apply_at_login(cursor, boss)
    assert 'institution_id' not in boss
    assert build_scope(cursor, boss) == Scope(institution_id=None, visible=(), organization_wide=True, multiple=True)


def test_sign_in_without_membership_falls_back_to_the_first_institution_and_tolerates_missing_tables():
    cursor = _Cursor(institutions=[_institution(3, sort_order=1), _institution(2, sort_order=0)])
    session = {'user_id': 7, 'role': 'HOD'}
    apply_at_login(cursor, session)
    assert session['institution_id'] == 2
    missing = _Cursor(institutions=[], tables=False)
    plain = {'user_id': 7, 'role': 'Admin'}
    apply_at_login(missing, plain)
    assert plain == {'user_id': 7, 'role': 'Admin'}


def test_switcher_rejects_unknown_inactive_and_foreign_institutions():
    cursor = _Cursor(
        institutions=[_institution(1), _institution(2), _institution(3, active=False)],
        memberships=[_membership(5, 1, primary=True)],
    )
    session = {'user_id': 5, 'role': 'Admin', 'institution_id': 1}
    with pytest.raises(ValueError, match='institution_not_found'):
        choose_institution(cursor, session, 99)
    with pytest.raises(ValueError, match='institution_not_found'):
        choose_institution(cursor, session, 3)
    with pytest.raises(ValueError, match='institution_forbidden'):
        choose_institution(cursor, session, 2)
    with pytest.raises(ValueError, match='institution_required'):
        choose_institution(cursor, session, None)
    assert session['institution_id'] == 1
    assert choose_institution(cursor, session, 1) == 1

    boss = {'user_id': 1, 'role': 'Super Admin'}
    assert choose_institution(cursor, boss, 2) == 2 and boss['institution_id'] == 2
    assert choose_institution(cursor, boss, None) is None and 'institution_id' not in boss


def test_a_stale_choice_is_replaced_by_the_primary_membership():
    cursor = _Cursor(institutions=[_institution(1), _institution(2)], memberships=[_membership(5, 1, primary=True)])
    scope = build_scope(cursor, {'user_id': 5, 'role': 'Admin', 'institution_id': 2})
    assert scope.institution_id == 1 and scope.visible == (1,)
    # A tampered value that is not an int is ignored rather than trusted.
    scope = build_scope(cursor, {'user_id': 5, 'role': 'Admin', 'institution_id': '2'})
    assert scope.institution_id == 1
    assert build_scope(cursor, {'user_id': 5, 'role': 'Admin', 'institution_id': True}).institution_id == 1


def test_current_scope_is_single_outside_a_request_and_cached_inside_one(monkeypatch):
    assert scope_module.current_scope() is SINGLE
    from flask import Flask, g, session as flask_session
    app = Flask(__name__)
    app.secret_key = 'unit-test'
    cursor = _Cursor(institutions=[_institution(1), _institution(2)], memberships=[_membership(5, 2, primary=True)])
    with app.test_request_context():
        assert scope_module.current_scope(cursor) is SINGLE  # nobody signed in
        flask_session['user_id'] = 5
        flask_session['role'] = 'Teacher'
        scope_module.forget()
        first = scope_module.current_scope(cursor)
        assert first.institution_id == 2 and first.visible == (2,)
        assert scope_module.current_scope() is first  # cached on g, no cursor needed
        scope_module.forget()
        assert scope_module._CACHE_KEY not in g


# Sharing predicates -------------------------------------------------------------------

def test_candidate_clauses_cover_own_organization_wide_and_listed_resources():
    assert store.candidate_rooms_clause(None) == ('1=1', ())
    sql, params = store.candidate_rooms_clause(4, 'rm')
    assert params == (4, 4)
    assert sql.startswith('(rm.institution_id = %s OR rm.sharing = \'organization\' OR (rm.sharing = \'listed\' AND EXISTS (')
    assert "rs.resource_type = 'room' AND rs.resource_id = rm.id AND rs.institution_id = %s" in sql
    sql, params = store.candidate_faculty_clause(4, 'f', 'dep')
    assert params == (4, 4)
    assert sql.startswith("(dep.institution_id = %s OR f.sharing = 'organization'")
    assert "rs.resource_type = 'faculty' AND rs.resource_id = f.id" in sql
    assert store.candidate_faculty_clause(None) == ('1=1', ())


def test_replace_shares_only_writes_the_difference():
    class Cursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=()):
            self.executed.append((' '.join(sql.split()), params))

        def fetchall(self):
            return [{'institution_id': 2}, {'institution_id': 3}]

    cursor = Cursor()
    store.replace_shares(cursor, 'room', 10, [3, 4], created_by=1)
    writes = [(sql.split(' ')[0], params) for sql, params in cursor.executed[1:]]
    assert writes == [('DELETE', ('room', 10, 2)), ('INSERT', ('room', 10, 4, 1))]


# Revision 0014 planner -------------------------------------------------------------------

def _load_0014():
    path = Path(MIGRATIONS_DIR) / 'versions' / '0014_institutions.py'
    spec = importlib.util.spec_from_file_location('revision_0014', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0014_follows_0013_and_is_in_the_chain():
    module = _load_0014()
    assert module.revision == '0014_institutions' and module.down_revision == '0013_integrations'
    assert head_revision() >= '0014_institutions'


def test_0014_creates_only_what_is_missing_and_drops_only_what_exists():
    module = _load_0014()
    names = [name for name, _, _ in module.OBJECTS]
    assert names[:2] == ['organizations', 'institutions'], 'tables the backfill writes come first'
    assert names.index('departments.institution_id') < names.index('fk_department_institution')
    assert names.index('rooms.institution_id') < names.index('fk_room_institution')

    fresh = module.upgrade_statements(set())
    assert len(fresh) == len(module.OBJECTS)
    partial = module.upgrade_statements({'organizations', 'institutions', 'departments.institution_id', 'fk_department_institution'})
    assert [statement.split()[2] for statement in partial] == [
        'rooms', 'rooms', 'rooms', 'faculty', 'institution_memberships', 'resource_shares',
    ]
    assert module.upgrade_statements(set(names)) == []

    drops = module.downgrade_statements({'organizations', 'institutions', 'rooms.sharing', 'resource_shares'})
    assert drops == [
        'DROP TABLE resource_shares', 'ALTER TABLE rooms DROP COLUMN sharing', 'DROP TABLE institutions', 'DROP TABLE organizations',
    ]


def test_0014_backfill_runs_only_on_empty_tables_and_in_the_right_phase():
    module = _load_0014()
    before, after = module.backfill_statements(organizations=0, institutions=0, memberships=0, title='Pillai Group')
    assert [sql.split('(')[0].strip() for sql, _ in before] == ['INSERT INTO organizations', 'INSERT INTO institutions']
    assert all(params == {'title': 'Pillai Group'} for _, params in before)
    assert "'MAIN'" in before[1][0]
    assert len(after) == 1 and "WHERE u.role <> 'Student'" in after[0][0]
    assert module.backfill_statements(organizations=1, institutions=1, memberships=1, title='x') == ([], [])
    before, after = module.backfill_statements(organizations=1, institutions=0, memberships=3, title='x')
    assert len(before) == 1 and after == []


# Joint solver room pools ---------------------------------------------------------------------

def test_joint_solver_pools_rooms_per_cohort():
    rooms = [{'id': 1}, {'id': 2}, {'id': 3}]
    assert joint_solver._pool(rooms, None) == rooms
    assert joint_solver._pool(rooms, frozenset({2, 3})) == [{'id': 2}, {'id': 3}]
    assert joint_solver._pool(rooms, frozenset()) == []


def test_demand_room_ids_default_to_any_room():
    import inspect
    parameters = inspect.signature(joint_solver.Demand).parameters
    assert 'room_ids' in parameters and parameters['room_ids'].default is None
