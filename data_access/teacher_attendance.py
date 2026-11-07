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
                d.id as division_id,
                d.name as division_name,
                co.id as course_id,
                co.name as course_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
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


def fetch_owned_lecture_detail(cursor, timetable_id, user_id):
    """Return one lecture when it belongs to this faculty user."""
    cursor.execute("""
            SELECT 
                t.id as timetable_id,
                t.day_of_week,
                t.start_time,
                t.end_time,
                s.id as subject_id,
                s.name as subject_name,
                c.id as class_id,
                c.name as class_name,
                d.id as division_id,
                d.name as division_name,
                co.id as course_id,
                co.name as course_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            JOIN courses co ON t.course_id = co.id
            WHERE t.id = %s AND t.faculty_id = %s
        """, (timetable_id, user_id))
    return cursor.fetchone()


def fetch_class_students(cursor, course_id, class_id, division_id):
    """Return students in one class division."""
    cursor.execute("""
            SELECT 
                s.id,
                s.name,
                s.roll_number,
                s.email
            FROM students s
            WHERE s.course_id = %s 
              AND s.class_id = %s 
              AND s.division_id = %s
            ORDER BY s.roll_number, s.name
        """, (course_id, class_id, division_id))
    return cursor.fetchall()


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


def upsert_attendance(cursor, student_id, timetable_id, attendance_date, status, faculty_id, remarks):
    """Insert or update one attendance mark. marked_by is the faculty table id."""
    cursor.execute("""
                    INSERT INTO attendance (student_id, timetable_id, attendance_date, status, marked_by, remarks)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        status = VALUES(status),
                        marked_by = VALUES(marked_by),
                        remarks = VALUES(remarks),
                        marked_at = NOW()
                """, (student_id, timetable_id, attendance_date, status, faculty_id, remarks))


def fetch_lecture_filters(cursor, user_id):
    """Return class and subject choices for the attendance report."""
    cursor.execute("""
            SELECT DISTINCT 
                s.id as subject_id,
                s.name as subject_name,
                c.id as class_id,
                c.name as class_name,
                d.id as division_id,
                d.name as division_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            WHERE t.faculty_id = %s
            ORDER BY c.name, d.name, s.name
        """, (user_id,))
    return cursor.fetchall()


def fetch_attendance_summary(cursor, date_filter, params):
    """Return the attendance summary. date_filter is a fixed SQL fragment."""
    cursor.execute(f"""
                SELECT 
                    s.id as student_id,
                    s.name as student_name,
                    s.roll_number,
                    COUNT(DISTINCT a.id) as total_marked,
                    SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_count,
                    SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late_count,
                    SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent_count,
                    ROUND(
                        (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0) / 
                        NULLIF(COUNT(DISTINCT a.id), 0), 
                        2
                    ) as attendance_percentage
                FROM students s
                LEFT JOIN attendance a ON a.student_id = s.id
                LEFT JOIN timetable t ON t.id = a.timetable_id
                WHERE s.class_id = %s 
                  AND s.division_id = %s
                  AND (t.subject_id = %s OR a.id IS NULL)
                  AND t.faculty_id = %s
                  {date_filter}
                GROUP BY s.id
                ORDER BY s.roll_number, s.name
            """, tuple(params))
    return cursor.fetchall()


def fetch_history_lecture(cursor, timetable_id, user_id):
    """Return the lecture heading when this faculty user owns it."""
    cursor.execute("""
            SELECT 
                t.id, s.name as subject_name, c.name as class_name, d.name as division_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            WHERE t.id = %s AND t.faculty_id = %s
        """, (timetable_id, user_id))
    return cursor.fetchone()


def fetch_attendance_history(cursor, timetable_id):
    """Return the last 50 attendance dates for one lecture."""
    cursor.execute("""
            SELECT 
                a.attendance_date,
                COUNT(DISTINCT a.student_id) as total_students,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                MAX(a.marked_at) as marked_at
            FROM attendance a
            WHERE a.timetable_id = %s
            GROUP BY a.attendance_date
            ORDER BY a.attendance_date DESC
            LIMIT 50
        """, (timetable_id,))
    return cursor.fetchall()
