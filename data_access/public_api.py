"""Read queries behind the public /api/v1. Every list takes `limit`/`offset`; callers bound them first."""


def _where(clauses):
    return f"WHERE {' AND '.join(clauses)}" if clauses else ''


def _page(cursor, sql, params, limit, offset):
    """Fetch limit + 1 rows so the caller can report has_more without a COUNT."""
    cursor.execute(f'{sql} LIMIT %s OFFSET %s', (*params, int(limit) + 1, int(offset)))
    rows = cursor.fetchall()
    return rows[:limit], len(rows) > limit


def fetch_courses(cursor, limit, offset):
    return _page(
        cursor,
        'SELECT c.id, c.name, c.code, c.program, c.duration_years, c.total_semesters, c.department_id, d.name AS department_name, '
        'COALESCE(c.is_active, 1) AS is_active FROM courses c JOIN departments d ON d.id = c.department_id ORDER BY c.name, c.id',
        (), limit, offset,
    )


def fetch_departments(cursor, limit, offset):
    return _page(
        cursor,
        'SELECT id, name, code, COALESCE(is_active, 1) AS is_active FROM departments ORDER BY name, id', (), limit, offset,
    )


def fetch_classes(cursor):
    cursor.execute('SELECT id, name, display_order FROM classes ORDER BY display_order, name, id')
    return cursor.fetchall()


def fetch_divisions(cursor):
    cursor.execute('SELECT id, name, capacity FROM divisions ORDER BY name, id')
    return cursor.fetchall()


def fetch_academic_years(cursor):
    cursor.execute('SELECT id, name, start_date, end_date, COALESCE(is_current, 0) AS is_current FROM academic_years ORDER BY start_date DESC, id')
    return cursor.fetchall()


def fetch_rooms(cursor, limit, offset):
    return _page(
        cursor,
        'SELECT id, room_number, room_type, capacity, building, floor, department_id, COALESCE(is_available, 1) AS is_available '
        'FROM rooms ORDER BY room_number, id',
        (), limit, offset,
    )


def fetch_subjects(cursor, *, course_id=None, class_id=None, limit, offset):
    clauses, params = [], []
    if course_id:
        clauses.append('s.course_id = %s')
        params.append(course_id)
    if class_id:
        clauses.append('s.class_id = %s')
        params.append(class_id)
    return _page(
        cursor,
        'SELECT s.id, s.name, s.course_code AS code, s.course_id, s.class_id, s.semester_id, s.course_type, s.theory_practical, '
        's.credits, s.lectures_per_week, s.practical_hours_per_week, '
        '(s.is_elective = 1 OR s.course_type IN (\'Elective\', \'Elective Practical\')) AS is_elective '
        f'FROM subjects s {_where(clauses)} ORDER BY s.course_id, s.class_id, s.name, s.id',
        params, limit, offset,
    )


def fetch_lab_batches(cursor, *, course_id=None, class_id=None, division_id=None, limit, offset):
    clauses, params = ['g.is_active = 1'], []
    for column, value in (('course_id', course_id), ('class_id', class_id), ('division_id', division_id)):
        if value:
            clauses.append(f'g.{column} = %s')
            params.append(value)
    return _page(
        cursor,
        'SELECT g.id, g.name, g.course_id, g.class_id, g.division_id, g.academic_year_id, g.semester_id, g.capacity, '
        '(SELECT COUNT(*) FROM lab_batch_members m WHERE m.lab_batch_group_id = g.id AND m.ended_at IS NULL) AS member_count '
        f'FROM lab_batch_groups g {_where(clauses)} ORDER BY g.course_id, g.class_id, g.division_id, g.name, g.id',
        params, limit, offset,
    )


def fetch_timetable(cursor, *, course_id=None, class_id=None, division_id=None, day=None, limit, offset):
    clauses, params = ['COALESCE(t.is_active, 1) = 1'], []
    for column, value in (('course_id', course_id), ('class_id', class_id), ('division_id', division_id), ('day_of_week', day)):
        if value:
            clauses.append(f't.{column} = %s')
            params.append(value)
    return _page(
        cursor,
        """
        SELECT t.id, t.course_id, t.class_id, t.division_id, t.day_of_week, t.start_time, t.end_time,
               t.subject_id, s.name AS subject_name, s.theory_practical, t.faculty_id AS faculty_user_id, f.id AS faculty_id,
               f.name AS faculty_name, t.room_id, COALESCE(r.room_number, t.room_number) AS room_number,
               t.lab_batch_group_id, lbg.name AS lab_batch_name, t.academic_year_id, t.semester_id
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN faculty f ON f.user_id = t.faculty_id
        LEFT JOIN rooms r ON r.id = t.room_id
        LEFT JOIN lab_batch_groups lbg ON lbg.id = t.lab_batch_group_id
        """ + _where(clauses) + """
        ORDER BY FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), t.start_time, t.id
        """,
        params, limit, offset,
    )


def fetch_students(cursor, *, course_id=None, class_id=None, division_id=None, limit, offset):
    clauses, params = ['COALESCE(s.is_active, 1) = 1'], []
    for column, value in (('course_id', course_id), ('class_id', class_id), ('division_id', division_id)):
        if value:
            clauses.append(f's.{column} = %s')
            params.append(value)
    return _page(
        cursor,
        'SELECT s.id, s.name, s.roll_number, s.admission_id, s.course_id, s.class_id, s.division_id, s.admission_year '
        f'FROM students s {_where(clauses)} ORDER BY s.course_id, s.class_id, s.division_id, s.roll_number, s.id',
        params, limit, offset,
    )


def fetch_student(cursor, student_id):
    cursor.execute(
        'SELECT s.id, s.name, s.roll_number, s.admission_id, s.course_id, s.class_id, s.division_id, s.admission_year, '
        'COALESCE(s.is_active, 1) AS is_active FROM students s WHERE s.id = %s',
        (student_id,),
    )
    return cursor.fetchone()


def fetch_faculty(cursor, *, department_id=None, limit, offset):
    clauses, params = ['COALESCE(f.is_active, 1) = 1'], []
    if department_id:
        clauses.append('f.department_id = %s')
        params.append(department_id)
    return _page(
        cursor,
        'SELECT f.id, f.name, f.employee_id, f.designation, f.department_id, d.name AS department_name '
        f'FROM faculty f JOIN departments d ON d.id = f.department_id {_where(clauses)} ORDER BY f.name, f.id',
        params, limit, offset,
    )


def fetch_sessions(cursor, *, date_from=None, date_to=None, status=None, course_id=None, class_id=None, division_id=None, subject_id=None, limit, offset):
    clauses, params = [], []
    if date_from:
        clauses.append('ls.session_date >= %s')
        params.append(date_from)
    if date_to:
        clauses.append('ls.session_date <= %s')
        params.append(date_to)
    if status:
        clauses.append('ls.status = %s')
        params.append(status)
    for column, value in (('course_id', course_id), ('class_id', class_id), ('division_id', division_id), ('subject_id', subject_id)):
        if value:
            clauses.append(f't.{column} = %s')
            params.append(value)
    return _page(
        cursor,
        """
        SELECT ls.id, ls.timetable_id, ls.session_date, ls.status, ls.cancel_reason, ls.marked_at, ls.source,
               t.course_id, t.class_id, t.division_id, t.subject_id, s.name AS subject_name, t.day_of_week, t.start_time, t.end_time,
               t.lab_batch_group_id, lbg.name AS lab_batch_name, f.id AS faculty_id, f.name AS faculty_name,
               (SELECT COUNT(*) FROM attendance a WHERE a.session_id = ls.id) AS marks
        FROM lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN faculty f ON f.user_id = ls.taught_by
        LEFT JOIN lab_batch_groups lbg ON lbg.id = t.lab_batch_group_id
        """ + _where(clauses) + ' ORDER BY ls.session_date, t.start_time, ls.id',
        params, limit, offset,
    )


def fetch_session(cursor, session_id):
    cursor.execute(
        """
        SELECT ls.id, ls.timetable_id, ls.session_date, ls.status, ls.cancel_reason, ls.marked_at, ls.source,
               t.course_id, t.class_id, t.division_id, t.subject_id, s.name AS subject_name, t.day_of_week, t.start_time, t.end_time,
               t.lab_batch_group_id, lbg.name AS lab_batch_name, f.id AS faculty_id, f.name AS faculty_name
        FROM lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN faculty f ON f.user_id = ls.taught_by
        LEFT JOIN lab_batch_groups lbg ON lbg.id = t.lab_batch_group_id
        WHERE ls.id = %s
        """,
        (session_id,),
    )
    return cursor.fetchone()


def fetch_session_marks(cursor, session_id):
    cursor.execute(
        'SELECT a.student_id, st.roll_number, st.name, a.status, a.marked_at FROM attendance a '
        'JOIN students st ON st.id = a.student_id WHERE a.session_id = %s ORDER BY st.roll_number, st.id',
        (session_id,),
    )
    return cursor.fetchall()
