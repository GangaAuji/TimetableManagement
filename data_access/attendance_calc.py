"""Rows for the attendance calculation. Callers pass a cursor; services/attendance_calc turns them into dataclasses.

Every query here is a plain SELECT. No percentage is computed in SQL: the
pure functions in attendance_calc do that from these rows.
"""


def _marks(values):
    return ', '.join(['%s'] * len(values))


STUDENT_COLUMNS = """
    s.id, s.name, s.roll_number, s.email, s.phone, s.user_id,
    s.course_id, s.class_id, s.division_id, s.is_active,
    DATE(s.created_at) AS enrolled_from,
    CASE WHEN COALESCE(s.is_active, 1) = 0 THEN DATE(s.updated_at) END AS enrolled_to,
    c.name AS course_name, c.program, cl.name AS class_name, d.name AS division_name
"""

_STUDENT_FROM = """
    FROM students s
    LEFT JOIN courses c ON c.id = s.course_id
    LEFT JOIN classes cl ON cl.id = s.class_id
    LEFT JOIN divisions d ON d.id = s.division_id
"""


def fetch_student(cursor, student_id):
    """One student with cohort names and the enrolment dates (created_at; updated_at once inactive)."""
    cursor.execute(f'SELECT {STUDENT_COLUMNS} {_STUDENT_FROM} WHERE s.id = %s', (student_id,))
    return cursor.fetchone()


def fetch_student_by_user(cursor, user_id):
    cursor.execute(f'SELECT {STUDENT_COLUMNS} {_STUDENT_FROM} WHERE s.user_id = %s', (user_id,))
    return cursor.fetchone()


def fetch_students(cursor, *, course_id=None, class_id=None, division_id=None, active_only=True):
    """Students of a cohort, every column the summaries and exports show. Ordered by roll number."""
    clauses, params = [], []
    if active_only:
        clauses.append('COALESCE(s.is_active, 1) = 1')
    if course_id is not None:
        clauses.append('s.course_id = %s')
        params.append(course_id)
    if class_id is not None:
        clauses.append('s.class_id = %s')
        params.append(class_id)
    if division_id is not None:
        clauses.append('s.division_id = %s')
        params.append(division_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    cursor.execute(
        f'SELECT {STUDENT_COLUMNS} {_STUDENT_FROM} {where} ORDER BY s.course_id, s.class_id, s.division_id, s.roll_number, s.name',
        tuple(params),
    )
    return cursor.fetchall()


def fetch_selections(cursor, student_ids):
    """Chosen subjects (student_subject_selections, not Withdrawn) for the students."""
    if not student_ids:
        return []
    cursor.execute(
        f"""
        SELECT student_id, subject_id, semester_id, academic_year_id
        FROM student_subject_selections
        WHERE student_id IN ({_marks(student_ids)}) AND (status IS NULL OR status <> 'Withdrawn')
        """,
        tuple(student_ids),
    )
    return cursor.fetchall()


SLOT_COLUMNS = """
    t.id, t.subject_id, t.course_id, t.class_id, t.division_id, t.semester_id, t.academic_year_id,
    t.faculty_id AS faculty_user_id, COALESCE(t.is_active, 1) AS is_active,
    t.day_of_week, t.start_time, t.end_time,
    sub.name AS subject_name, COALESCE(sub.is_elective, 0) AS is_elective,
    sub.theory_practical, sub.course_type,
    sem.start_date AS semester_start, sem.end_date AS semester_end
"""

_SLOT_FROM = """
    FROM timetable t
    JOIN subjects sub ON sub.id = t.subject_id
    LEFT JOIN semesters sem ON sem.id = t.semester_id
"""


def fetch_slots(cursor, cohorts, student_ids=()):
    """Timetable rows of the cohorts (course, class pairs), active or retired, plus any slot the students have marks in.

    Retired slots keep their sessions, so they are loaded too; in_roster and
    the session rows decide what counts. The marks branch keeps a student's
    history after a transfer to another cohort.
    """
    clauses, params = [], []
    for course_id, class_id in sorted(cohorts):
        clauses.append('(t.course_id = %s AND t.class_id = %s)')
        params.extend((course_id, class_id))
    if student_ids:
        clauses.append(f't.id IN (SELECT DISTINCT a.timetable_id FROM attendance a WHERE a.student_id IN ({_marks(student_ids)}))')
        params.extend(student_ids)
    if not clauses:
        return []
    cursor.execute(f"SELECT {SLOT_COLUMNS} {_SLOT_FROM} WHERE {' OR '.join(clauses)} ORDER BY t.id", tuple(params))
    return cursor.fetchall()


def fetch_sessions(cursor, slot_ids, date_from=None, date_to=None):
    """lecture_sessions rows of the slots. A slot with a semester is limited to that semester's dates."""
    if not slot_ids:
        return []
    clauses = [f'ls.timetable_id IN ({_marks(slot_ids)})']
    params = list(slot_ids)
    clauses.append('(t.semester_id IS NULL OR sem.id IS NULL OR ls.session_date BETWEEN sem.start_date AND sem.end_date)')
    if date_from is not None:
        clauses.append('ls.session_date >= %s')
        params.append(date_from)
    if date_to is not None:
        clauses.append('ls.session_date <= %s')
        params.append(date_to)
    cursor.execute(
        f"""
        SELECT ls.id, ls.timetable_id, ls.session_date, ls.status, ls.taught_by, ls.cancel_reason, ls.marked_at
        FROM lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        LEFT JOIN semesters sem ON sem.id = t.semester_id
        WHERE {' AND '.join(clauses)}
        ORDER BY ls.session_date, ls.id
        """,
        tuple(params),
    )
    return cursor.fetchall()


def fetch_marks(cursor, student_ids, session_ids):
    """attendance rows of the students on the sessions, with the marker's name.

    A row that the backfill has not linked yet is matched through its slot
    and date, so the figures do not depend on the backfill having run.
    """
    if not student_ids or not session_ids:
        return []
    columns = """
        SELECT a.id, a.student_id, a.status, a.remarks, a.marked_at, a.attendance_date, a.timetable_id,
               ls.id AS session_id, f.name AS marked_by_name
        FROM attendance a
    """
    where = f'a.student_id IN ({_marks(student_ids)}) AND ls.id IN ({_marks(session_ids)})'
    params = tuple(student_ids) + tuple(session_ids)
    cursor.execute(
        f"""
        {columns}
        JOIN lecture_sessions ls ON ls.id = a.session_id
        LEFT JOIN faculty f ON f.id = a.marked_by
        WHERE {where}
        UNION ALL
        {columns}
        JOIN lecture_sessions ls ON ls.timetable_id = a.timetable_id AND ls.session_date = a.attendance_date
        LEFT JOIN faculty f ON f.id = a.marked_by
        WHERE a.session_id IS NULL AND {where}
        """,
        params + params,
    )
    return cursor.fetchall()


def fetch_excuses(cursor, student_ids):
    if not student_ids:
        return []
    cursor.execute(
        f"""
        SELECT student_id, subject_id, date_from, date_to, reason
        FROM attendance_excuses
        WHERE student_id IN ({_marks(student_ids)})
        """,
        tuple(student_ids),
    )
    return cursor.fetchall()


def count_not_marked_sessions(cursor):
    cursor.execute("SELECT COUNT(*) AS total FROM lecture_sessions WHERE status = 'not_marked'")
    row = cursor.fetchone() or {}
    return int(row.get('total') or 0)
