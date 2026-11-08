"""Teacher attendance SQL. Callers pass a cursor."""


def fetch_faculty_table_id(cursor, user_id):
    """Return the faculty table id for a user."""
    cursor.execute("SELECT id FROM faculty WHERE user_id = %s", (user_id,))
    return cursor.fetchone()


def fetch_teacher_lectures(cursor, user_id):
    """Return lectures taught by one faculty user."""
    cursor.execute("""
            SELECT DISTINCT 
                t.id as timetable_id,
                t.day_of_week,
                t.start_time,
                t.end_time,
                s.id as subject_id,
                s.name as subject_name,
                c.id as class_id,
                c.name as class_name,
                t.division_id as division_id,
                d.name as division_name,
                co.id as course_id,
                co.name as course_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
            JOIN courses co ON t.course_id = co.id
            WHERE t.faculty_id = %s
            ORDER BY t.day_of_week, t.start_time
        """, (user_id,))
    return cursor.fetchall()


def count_attendance_for_date(cursor, timetable_id, today):
    """Return the attendance count row for one lecture and date."""
    cursor.execute("""
                SELECT COUNT(*) as count 
                FROM attendance 
                WHERE timetable_id = %s AND attendance_date = %s
            """, (timetable_id, today))
    return cursor.fetchone()


_APPROVED_PROXY = """
    EXISTS (
        SELECT 1 FROM proxy_log pl
        WHERE pl.timetable_id = t.id AND pl.absence_date = %s AND pl.proxy_faculty_id = %s
          AND pl.status = 'ASSIGNED' AND pl.approval_status = 'APPROVED'
    )
"""


def fetch_owned_lecture_detail(cursor, timetable_id, user_id, on_date=None):
    """Return one lecture when this faculty user may mark it. division_id is None for a whole-class lecture.

    The slot's teacher always may. With `on_date`, so may the proxy approved
    for that date in proxy_log. `taught_by` says which of the two is teaching.
    """
    owner = ['t.faculty_id = %s']
    params = [timetable_id, user_id]
    if on_date is not None:
        owner.append(_APPROVED_PROXY)
        params.extend([on_date, user_id])
    cursor.execute(f"""
            SELECT 
                t.id as timetable_id,
                t.day_of_week,
                t.start_time,
                t.end_time,
                t.semester_id,
                t.academic_year_id,
                t.faculty_id as faculty_user_id,
                (t.faculty_id = %s) as is_owner,
                s.id as subject_id,
                s.name as subject_name,
                (s.is_elective = 1 OR s.course_type IN ('Elective', 'Elective Practical')) as is_elective,
                c.id as class_id,
                c.name as class_name,
                t.division_id as division_id,
                d.name as division_name,
                co.id as course_id,
                co.name as course_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
            JOIN courses co ON t.course_id = co.id
            WHERE t.id = %s AND ({' OR '.join(owner)})
        """, (user_id, *params))
    return cursor.fetchone()


def fetch_lecture_roster(cursor, lecture):
    """Return the students who may be marked for this lecture.

    Everyone in the lecture's course and class, narrowed to its division when
    it has one. For an elective subject, only students with a
    student_subject_selections row for that subject (not withdrawn, and in
    the lecture's semester and academic year when the lecture names them).
    """
    clauses, params = roster_clauses(lecture)
    cursor.execute(f"""
            SELECT 
                s.id,
                s.user_id,
                s.name,
                s.roll_number,
                s.admission_id,
                s.email
            FROM students s
            WHERE {' AND '.join(clauses)}
            ORDER BY s.roll_number, s.name
        """, tuple(params))
    return cursor.fetchall()


def roster_clauses(lecture):
    """The SQL twin of attendance_calc.roster.in_roster for today, on a `students s` row: clauses and their parameters."""
    clauses = ['COALESCE(s.is_active, 1) = 1', 's.course_id = %s', 's.class_id = %s']
    params = [lecture['course_id'], lecture['class_id']]
    if lecture.get('division_id') is not None:
        clauses.append('s.division_id = %s')
        params.append(lecture['division_id'])
    if lecture.get('is_elective'):
        chosen = [
            'sss.student_id = s.id', 'sss.subject_id = %s', "(sss.status IS NULL OR sss.status <> 'Withdrawn')",
        ]
        params.append(lecture['subject_id'])
        if lecture.get('semester_id') is not None:
            chosen.append('sss.semester_id = %s')
            params.append(lecture['semester_id'])
        if lecture.get('academic_year_id') is not None:
            chosen.append('sss.academic_year_id = %s')
            params.append(lecture['academic_year_id'])
        clauses.append(f"EXISTS (SELECT 1 FROM student_subject_selections sss WHERE {' AND '.join(chosen)})")
    return clauses, params


def student_in_roster(cursor, lecture, student_id):
    """Whether one student belongs to the lecture's roster."""
    clauses, params = roster_clauses(lecture)
    cursor.execute(
        f"SELECT 1 AS ok FROM students s WHERE s.id = %s AND {' AND '.join(clauses)} LIMIT 1",
        (student_id, *params),
    )
    return cursor.fetchone() is not None


def fetch_existing_attendance(cursor, timetable_id, attendance_date):
    """Return attendance already stored for a lecture and date."""
    cursor.execute("""
            SELECT 
                student_id,
                status,
                remarks
            FROM attendance
            WHERE timetable_id = %s AND attendance_date = %s
        """, (timetable_id, attendance_date))
    return cursor.fetchall()


def fetch_owned_timetable_id(cursor, timetable_id, user_id):
    """Return a timetable id row when this faculty user owns it."""
    cursor.execute("SELECT id FROM timetable WHERE id = %s AND faculty_id = %s",
                   (timetable_id, user_id))
    return cursor.fetchone()


def upsert_attendance(cursor, student_id, timetable_id, attendance_date, status, faculty_id, remarks, session_id=None):
    """Insert or update one attendance mark. marked_by is the faculty table id; session_id the lecture_sessions row."""
    cursor.execute("""
                    INSERT INTO attendance (student_id, timetable_id, session_id, attendance_date, status, marked_by, remarks)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        status = VALUES(status),
                        session_id = COALESCE(VALUES(session_id), session_id),
                        marked_by = VALUES(marked_by),
                        remarks = VALUES(remarks),
                        marked_at = NOW()
                """, (student_id, timetable_id, session_id, attendance_date, status, faculty_id, remarks))


def fetch_history_lecture(cursor, timetable_id, user_id):
    """Return the lecture heading and roster columns when this faculty user owns it or is its approved proxy on some date."""
    cursor.execute("""
            SELECT 
                t.id, t.course_id, t.class_id, t.division_id, t.subject_id, t.semester_id, t.academic_year_id,
                COALESCE(s.is_elective, 0) AS is_elective,
                s.name as subject_name, c.name as class_name, d.name as division_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
            WHERE t.id = %s
              AND (t.faculty_id = %s OR EXISTS (
                    SELECT 1 FROM proxy_log pl
                    WHERE pl.timetable_id = t.id AND pl.proxy_faculty_id = %s
                      AND pl.status = 'ASSIGNED' AND pl.approval_status = 'APPROVED'))
        """, (timetable_id, user_id, user_id))
    return cursor.fetchone()


def fetch_attendance_history(cursor, timetable_id):
    """Return the last 50 recorded lectures of one slot, newest first, with the marks on each.

    Every lecture_sessions row appears, so cancelled and not-marked dates are
    listed beside the marked ones.
    """
    cursor.execute("""
            SELECT 
                ls.id AS session_id,
                ls.session_date AS attendance_date,
                ls.status AS session_status,
                ls.cancel_reason,
                ls.source,
                COUNT(DISTINCT a.student_id) as total_students,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                MAX(a.marked_at) as marked_at
            FROM lecture_sessions ls
            LEFT JOIN attendance a ON a.session_id = ls.id
            WHERE ls.timetable_id = %s
            GROUP BY ls.id
            ORDER BY ls.session_date DESC, ls.id DESC
            LIMIT 50
        """, (timetable_id,))
    return cursor.fetchall()
