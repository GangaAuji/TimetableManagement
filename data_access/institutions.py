"""Organizations, institutions, memberships and resource shares. Callers pass a dictionary cursor.

See docs/DESIGN_INSTITUTIONS.md. An institution owns departments and rooms
directly; everything else reaches its institution through its department
(courses, faculty) or its course (subjects, students, timetable).
"""

SHARING = ('private', 'listed', 'organization')
RESOURCE_TYPES = ('room', 'faculty')

INSTITUTION_COLUMNS = 'i.id, i.organization_id, i.name, i.code, i.short_name, i.is_active, i.sort_order, i.created_at, i.updated_at'


def table_exists(cursor, name='institutions'):
    cursor.execute(
        'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1',
        (name,),
    )
    return cursor.fetchone() is not None


# Organization -----------------------------------------------------------------

def fetch_organization(cursor):
    cursor.execute('SELECT id, name, short_name, created_at, updated_at FROM organizations WHERE id = 1')
    return cursor.fetchone()


def upsert_organization(cursor, *, name, short_name):
    cursor.execute(
        'INSERT INTO organizations (id, name, short_name) VALUES (1, %s, %s) '
        'ON DUPLICATE KEY UPDATE name = VALUES(name), short_name = VALUES(short_name)',
        (name, short_name),
    )


# Institutions -----------------------------------------------------------------

def fetch_institutions(cursor, *, active_only=False):
    where = 'WHERE i.is_active = 1' if active_only else ''
    cursor.execute(f'SELECT {INSTITUTION_COLUMNS} FROM institutions i {where} ORDER BY i.sort_order, i.name, i.id')
    return cursor.fetchall()


def fetch_institution(cursor, institution_id):
    cursor.execute(f'SELECT {INSTITUTION_COLUMNS} FROM institutions i WHERE i.id = %s', (institution_id,))
    return cursor.fetchone()


def fetch_institution_by_code(cursor, code):
    cursor.execute(f'SELECT {INSTITUTION_COLUMNS} FROM institutions i WHERE i.code = %s', (code,))
    return cursor.fetchone()


def count_active_institutions(cursor):
    cursor.execute('SELECT COUNT(*) AS n FROM institutions WHERE is_active = 1')
    return int((cursor.fetchone() or {}).get('n') or 0)


def first_institution_id(cursor):
    cursor.execute('SELECT id FROM institutions ORDER BY is_active DESC, sort_order, id LIMIT 1')
    row = cursor.fetchone()
    return int(row['id']) if row else None


def insert_institution(cursor, *, name, code, short_name, is_active, sort_order):
    cursor.execute(
        'INSERT INTO institutions (organization_id, name, code, short_name, is_active, sort_order) '
        'VALUES (1, %s, %s, %s, %s, %s)',
        (name, code, short_name, 1 if is_active else 0, sort_order),
    )
    return cursor.lastrowid


def update_institution(cursor, institution_id, *, name, code, short_name, is_active, sort_order):
    cursor.execute(
        'UPDATE institutions SET name = %s, code = %s, short_name = %s, is_active = %s, sort_order = %s WHERE id = %s',
        (name, code, short_name, 1 if is_active else 0, sort_order, institution_id),
    )
    return cursor.rowcount


def institution_usage(cursor, institution_id):
    """Counts of what points at the institution; used to refuse deactivating the last one with data."""
    cursor.execute('SELECT COUNT(*) AS n FROM departments WHERE institution_id = %s', (institution_id,))
    departments = int(cursor.fetchone()['n'])
    cursor.execute('SELECT COUNT(*) AS n FROM rooms WHERE institution_id = %s', (institution_id,))
    rooms = int(cursor.fetchone()['n'])
    cursor.execute('SELECT COUNT(*) AS n FROM institution_memberships WHERE institution_id = %s', (institution_id,))
    members = int(cursor.fetchone()['n'])
    return {'departments': departments, 'rooms': rooms, 'members': members}


# Deriving an institution ------------------------------------------------------

def institution_of_department(cursor, department_id):
    cursor.execute('SELECT institution_id FROM departments WHERE id = %s', (department_id,))
    row = cursor.fetchone()
    return int(row['institution_id']) if row and row.get('institution_id') is not None else None


def institution_of_course(cursor, course_id):
    cursor.execute(
        'SELECT d.institution_id FROM courses c JOIN departments d ON d.id = c.department_id WHERE c.id = %s',
        (course_id,),
    )
    row = cursor.fetchone()
    return int(row['institution_id']) if row and row.get('institution_id') is not None else None


def institution_of_faculty(cursor, faculty_id):
    cursor.execute(
        'SELECT d.institution_id FROM faculty f JOIN departments d ON d.id = f.department_id WHERE f.id = %s',
        (faculty_id,),
    )
    row = cursor.fetchone()
    return int(row['institution_id']) if row and row.get('institution_id') is not None else None


def institution_of_room(cursor, room_id):
    cursor.execute('SELECT institution_id FROM rooms WHERE id = %s', (room_id,))
    row = cursor.fetchone()
    return int(row['institution_id']) if row and row.get('institution_id') is not None else None


def institution_of_student(cursor, student_id):
    cursor.execute(
        'SELECT d.institution_id FROM students s JOIN courses c ON c.id = s.course_id '
        'JOIN departments d ON d.id = c.department_id WHERE s.id = %s',
        (student_id,),
    )
    row = cursor.fetchone()
    return int(row['institution_id']) if row and row.get('institution_id') is not None else None


# Memberships ------------------------------------------------------------------

def fetch_memberships(cursor, user_id):
    cursor.execute(
        'SELECT m.id, m.institution_id, m.role, m.department_id, m.is_primary, i.name, i.code, i.short_name, i.is_active '
        'FROM institution_memberships m JOIN institutions i ON i.id = m.institution_id '
        'WHERE m.user_id = %s ORDER BY m.is_primary DESC, i.sort_order, i.name',
        (user_id,),
    )
    return cursor.fetchall()


def fetch_members(cursor, institution_id):
    cursor.execute(
        'SELECT m.id, m.user_id, m.role, m.department_id, m.is_primary, u.username, u.email, u.status '
        'FROM institution_memberships m JOIN users u ON u.id = m.user_id '
        'WHERE m.institution_id = %s ORDER BY u.username',
        (institution_id,),
    )
    return cursor.fetchall()


def replace_memberships(cursor, user_id, institution_ids, *, role, department_id, primary_id):
    """Make the user's memberships exactly `institution_ids`; `primary_id` is marked primary."""
    wanted = {int(item) for item in institution_ids}
    cursor.execute('SELECT institution_id FROM institution_memberships WHERE user_id = %s', (user_id,))
    current = {int(row['institution_id']) for row in cursor.fetchall()}
    for institution_id in current - wanted:
        cursor.execute(
            'DELETE FROM institution_memberships WHERE user_id = %s AND institution_id = %s', (user_id, institution_id),
        )
    for institution_id in wanted - current:
        cursor.execute(
            'INSERT INTO institution_memberships (user_id, institution_id, role, department_id, is_primary) '
            'VALUES (%s, %s, %s, %s, 0)',
            (user_id, institution_id, role, department_id),
        )
    cursor.execute('UPDATE institution_memberships SET role = %s WHERE user_id = %s', (role, user_id))
    cursor.execute('UPDATE institution_memberships SET is_primary = 0 WHERE user_id = %s', (user_id,))
    if primary_id is not None and int(primary_id) in wanted:
        cursor.execute(
            'UPDATE institution_memberships SET is_primary = 1, department_id = %s WHERE user_id = %s AND institution_id = %s',
            (department_id, user_id, primary_id),
        )


def ensure_membership(cursor, user_id, institution_id, *, role, department_id=None, primary=True):
    cursor.execute(
        'INSERT INTO institution_memberships (user_id, institution_id, role, department_id, is_primary) '
        'VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE role = VALUES(role)',
        (user_id, institution_id, role, department_id, 1 if primary else 0),
    )


# Sharing ----------------------------------------------------------------------

def fetch_shares(cursor, resource_type, resource_id):
    cursor.execute(
        'SELECT s.institution_id, i.name, i.code, i.short_name FROM resource_shares s '
        'JOIN institutions i ON i.id = s.institution_id WHERE s.resource_type = %s AND s.resource_id = %s '
        'ORDER BY i.sort_order, i.name',
        (resource_type, resource_id),
    )
    return cursor.fetchall()


def fetch_shares_for(cursor, resource_type, resource_ids):
    """{resource_id: [institution_id, ...]} for many resources at once."""
    ids = sorted({int(item) for item in resource_ids})
    if not ids:
        return {}
    marks = ', '.join(['%s'] * len(ids))
    cursor.execute(
        f'SELECT resource_id, institution_id FROM resource_shares WHERE resource_type = %s AND resource_id IN ({marks})',
        (resource_type, *ids),
    )
    shares = {}
    for row in cursor.fetchall():
        shares.setdefault(int(row['resource_id']), []).append(int(row['institution_id']))
    return shares


def replace_shares(cursor, resource_type, resource_id, institution_ids, *, created_by):
    wanted = {int(item) for item in institution_ids}
    cursor.execute(
        'SELECT institution_id FROM resource_shares WHERE resource_type = %s AND resource_id = %s',
        (resource_type, resource_id),
    )
    current = {int(row['institution_id']) for row in cursor.fetchall()}
    for institution_id in current - wanted:
        cursor.execute(
            'DELETE FROM resource_shares WHERE resource_type = %s AND resource_id = %s AND institution_id = %s',
            (resource_type, resource_id, institution_id),
        )
    for institution_id in wanted - current:
        cursor.execute(
            'INSERT INTO resource_shares (resource_type, resource_id, institution_id, created_by) VALUES (%s, %s, %s, %s)',
            (resource_type, resource_id, institution_id, created_by),
        )


def candidate_rooms_clause(institution_id, alias='r'):
    """SQL predicate: rooms the institution may timetable (own, organization-wide, or listed to it)."""
    if institution_id is None:
        return '1=1', ()
    return (
        f"({alias}.institution_id = %s OR {alias}.sharing = 'organization' OR ({alias}.sharing = 'listed' AND EXISTS ("
        f"SELECT 1 FROM resource_shares rs WHERE rs.resource_type = 'room' AND rs.resource_id = {alias}.id "
        f"AND rs.institution_id = %s)))",
        (institution_id, institution_id),
    )


def candidate_faculty_clause(institution_id, alias='f', department_alias='fd'):
    """SQL predicate: faculty the institution may allocate. Needs `departments {department_alias}` joined on the faculty's department."""
    if institution_id is None:
        return '1=1', ()
    return (
        f"({department_alias}.institution_id = %s OR {alias}.sharing = 'organization' OR ({alias}.sharing = 'listed' AND EXISTS ("
        f"SELECT 1 FROM resource_shares rs WHERE rs.resource_type = 'faculty' AND rs.resource_id = {alias}.id "
        f"AND rs.institution_id = %s)))",
        (institution_id, institution_id),
    )


def fetch_candidate_rooms(cursor, institution_id):
    """Rooms a timetable for `institution_id` may use, with their owner for labelling."""
    clause, params = candidate_rooms_clause(institution_id)
    cursor.execute(
        f'SELECT r.id, r.room_number, r.room_type, r.capacity, r.department_id, r.institution_id, r.sharing, '
        f'i.short_name AS institution_short_name, i.name AS institution_name '
        f'FROM rooms r JOIN institutions i ON i.id = r.institution_id WHERE {clause} ORDER BY r.room_number',
        params,
    )
    return cursor.fetchall()
