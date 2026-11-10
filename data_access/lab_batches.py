"""Lab batch SQL (lab_batch_groups, lab_batch_members). Callers pass a cursor; services/lab_batches holds the rules."""

GROUP_COLUMNS = """
    g.id, g.course_id, g.class_id, g.division_id, g.academic_year_id, g.semester_id, g.name, g.capacity, g.is_active,
    c.name AS course_name, cl.name AS class_name, d.name AS division_name, ay.name AS academic_year_name,
    sem.semester_name,
    (SELECT COUNT(*) FROM lab_batch_members m WHERE m.lab_batch_group_id = g.id AND m.ended_at IS NULL) AS member_count,
    (SELECT COUNT(*) FROM timetable t WHERE t.lab_batch_group_id = g.id AND COALESCE(t.is_active, 1) = 1) AS slot_count
"""

_GROUP_FROM = """
    FROM lab_batch_groups g
    JOIN courses c ON c.id = g.course_id
    JOIN classes cl ON cl.id = g.class_id
    LEFT JOIN divisions d ON d.id = g.division_id
    JOIN academic_years ay ON ay.id = g.academic_year_id
    LEFT JOIN semesters sem ON sem.id = g.semester_id
"""


def fetch_groups(cursor, *, course_id=None, class_id=None, division_id=None, academic_year_id=None, active_only=False):
    """Lab batch groups, narrowed by any of the cohort keys. `division_id` matches that division or a whole-class split."""
    clauses, params = [], []
    if course_id is not None:
        clauses.append('g.course_id = %s')
        params.append(course_id)
    if class_id is not None:
        clauses.append('g.class_id = %s')
        params.append(class_id)
    if division_id is not None:
        clauses.append('(g.division_id = %s OR g.division_id IS NULL)')
        params.append(division_id)
    if academic_year_id is not None:
        clauses.append('g.academic_year_id = %s')
        params.append(academic_year_id)
    if active_only:
        clauses.append('g.is_active = 1')
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    cursor.execute(
        f"SELECT {GROUP_COLUMNS} {_GROUP_FROM} {where} "
        "ORDER BY ay.start_date DESC, c.name, cl.name, d.name, g.semester_id, g.name",
        tuple(params),
    )
    return cursor.fetchall()


def fetch_group(cursor, group_id):
    cursor.execute(f'SELECT {GROUP_COLUMNS} {_GROUP_FROM} WHERE g.id = %s', (group_id,))
    return cursor.fetchone()


def fetch_sibling_groups(cursor, group):
    """Every active group of the same split (cohort, year, semester) as `group`, itself included."""
    cursor.execute(
        """
        SELECT id, name, capacity
        FROM lab_batch_groups
        WHERE course_id = %s AND class_id = %s AND academic_year_id = %s AND is_active = 1
          AND ((division_id IS NULL AND %s IS NULL) OR division_id = %s)
          AND ((semester_id IS NULL AND %s IS NULL) OR semester_id = %s)
        ORDER BY name
        """,
        (
            group['course_id'], group['class_id'], group['academic_year_id'],
            group.get('division_id'), group.get('division_id'), group.get('semester_id'), group.get('semester_id'),
        ),
    )
    return cursor.fetchall()


def fetch_same_named(cursor, values, exclude_id=None):
    """A group of the same split with the same name. The unique key cannot see this when division or semester is NULL."""
    clauses = [
        'course_id = %(course_id)s', 'class_id = %(class_id)s', 'academic_year_id = %(academic_year_id)s', 'name = %(name)s',
        '((division_id IS NULL AND %(division_id)s IS NULL) OR division_id = %(division_id)s)',
        '((semester_id IS NULL AND %(semester_id)s IS NULL) OR semester_id = %(semester_id)s)',
    ]
    params = dict(values)
    if exclude_id is not None:
        clauses.append('id <> %(exclude_id)s')
        params['exclude_id'] = exclude_id
    cursor.execute(f"SELECT id FROM lab_batch_groups WHERE {' AND '.join(clauses)} LIMIT 1", params)
    return cursor.fetchone()


def insert_group(cursor, values):
    cursor.execute(
        """
        INSERT INTO lab_batch_groups (course_id, class_id, division_id, academic_year_id, semester_id, name, capacity, is_active)
        VALUES (%(course_id)s, %(class_id)s, %(division_id)s, %(academic_year_id)s, %(semester_id)s, %(name)s, %(capacity)s, %(is_active)s)
        """,
        values,
    )
    return cursor.lastrowid


def update_group(cursor, group_id, values):
    cursor.execute(
        """
        UPDATE lab_batch_groups
        SET name = %(name)s, capacity = %(capacity)s, is_active = %(is_active)s, semester_id = %(semester_id)s
        WHERE id = %(id)s
        """,
        {**values, 'id': group_id},
    )
    return cursor.rowcount


def delete_group(cursor, group_id):
    """Delete a group. Its timetable rows become whole-division slots (FK SET NULL); members cascade."""
    cursor.execute('DELETE FROM lab_batch_groups WHERE id = %s', (group_id,))
    return cursor.rowcount


def fetch_members(cursor, group_id, *, current_only=True):
    clause = 'AND m.ended_at IS NULL' if current_only else ''
    cursor.execute(
        f"""
        SELECT m.id, m.student_id, m.added_at, m.ended_at, s.name, s.roll_number, s.email
        FROM lab_batch_members m
        JOIN students s ON s.id = m.student_id
        WHERE m.lab_batch_group_id = %s {clause}
        ORDER BY s.roll_number, s.name
        """,
        (group_id,),
    )
    return cursor.fetchall()


def fetch_cohort_students(cursor, course_id, class_id, division_id=None):
    """Active students of the cohort the split applies to, in roll-number order."""
    clauses = ['COALESCE(s.is_active, 1) = 1', 's.course_id = %s', 's.class_id = %s']
    params = [course_id, class_id]
    if division_id is not None:
        clauses.append('s.division_id = %s')
        params.append(division_id)
    cursor.execute(
        f"SELECT s.id, s.name, s.roll_number, s.email FROM students s WHERE {' AND '.join(clauses)} "
        "ORDER BY s.roll_number, s.name",
        tuple(params),
    )
    return cursor.fetchall()


def fetch_current_memberships(cursor, group_ids):
    """(student_id -> lab_batch_group_id) for current members of any of the groups."""
    if not group_ids:
        return {}
    marks = ', '.join(['%s'] * len(group_ids))
    cursor.execute(
        f'SELECT student_id, lab_batch_group_id FROM lab_batch_members WHERE ended_at IS NULL AND lab_batch_group_id IN ({marks})',
        tuple(group_ids),
    )
    return {row['student_id']: row['lab_batch_group_id'] for row in cursor.fetchall()}


def end_membership(cursor, group_id, student_id, on_date):
    """Close the student's current membership of the group on `on_date` (the last day they count as a member)."""
    cursor.execute(
        'UPDATE lab_batch_members SET ended_at = %s WHERE lab_batch_group_id = %s AND student_id = %s AND ended_at IS NULL',
        (on_date, group_id, student_id),
    )
    return cursor.rowcount


def add_membership(cursor, group_id, student_id, on_date):
    """Start (or re-open) the student's membership of the group from `on_date`."""
    cursor.execute(
        """
        INSERT INTO lab_batch_members (lab_batch_group_id, student_id, added_at, ended_at)
        VALUES (%s, %s, %s, NULL)
        ON DUPLICATE KEY UPDATE added_at = IF(ended_at IS NULL, added_at, VALUES(added_at)), ended_at = NULL
        """,
        (group_id, student_id, on_date),
    )
    return cursor.rowcount
