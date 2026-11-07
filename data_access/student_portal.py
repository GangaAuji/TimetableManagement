"""Student portal SQL. Callers pass a cursor."""


def fetch_student_profile(cursor, user_id):
    """Return the student row used by the dashboard."""
    cursor.execute("""
            SELECT s.id, s.course_id, s.class_id, s.division_id, 
                   c.name as course_name, cl.name as class_name, d.name as division_name
            FROM students s
            LEFT JOIN courses c ON s.course_id = c.id
            LEFT JOIN classes cl ON s.class_id = cl.id
            LEFT JOIN divisions d ON s.division_id = d.id
            WHERE s.user_id = %s
        """, [user_id])
    return cursor.fetchone()


def fetch_today_classes(cursor, course_id, class_id, division_id, today):
    """Return today's classes for one section."""
    cursor.execute("""
                SELECT 
                    t.id,
                    t.start_time, 
                    t.end_time, 
                    s.name as subject_name, 
                    f.name as faculty_name,
                    r.room_number
                FROM timetable t 
                JOIN subjects s ON t.subject_id = s.id 
                JOIN faculty f ON t.faculty_id = f.user_id
                LEFT JOIN rooms r ON t.room_id = r.id
                WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s 
                AND t.day_of_week = %s
                ORDER BY t.start_time
            """, (course_id, class_id, division_id, today))
    return cursor.fetchall()


def count_weekly_classes(cursor, course_id, class_id, division_id):
    """Return the weekly class count row."""
    cursor.execute("""
            SELECT COUNT(*) as count FROM timetable 
            WHERE course_id = %s AND class_id = %s AND division_id = %s
        """, (course_id, class_id, division_id))
    return cursor.fetchone()


def fetch_overall_attendance(cursor, student_id):
    """Return the overall attendance row."""
    cursor.execute("""
            SELECT 
                COALESCE(total_lectures, 0) as total_lectures,
                COALESCE(total_present, 0) as total_present,
                COALESCE(total_late, 0) as total_late,
                COALESCE(total_absent, 0) as total_absent,
                COALESCE(overall_percentage, 0) as attendance_percentage
            FROM student_overall_attendance
            WHERE student_id = %s
        """, [student_id])
    return cursor.fetchone()


def fetch_student_section(cursor, user_id):
    """Return the section ids for the timetable page."""
    cursor.execute(
        "SELECT course_id, class_id, division_id FROM students WHERE user_id = %s",
        [user_id],
    )
    return cursor.fetchone()


def fetch_student_timetable(cursor, course_id, class_id, division_id):
    """Return the weekly timetable for one section."""
    cursor.execute("""
            SELECT 
                t.day_of_week, 
                t.start_time, 
                t.end_time, 
                s.name as subject_name, 
                f.name as faculty_name,
                r.room_number
            FROM timetable t 
            JOIN subjects s ON t.subject_id = s.id 
            JOIN faculty f ON t.faculty_id = f.user_id
            LEFT JOIN rooms r ON t.room_id = r.id
            WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s 
            ORDER BY 
                FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), 
                t.start_time
        """, (course_id, class_id, division_id))
    return cursor.fetchall()


def fetch_student_id(cursor, user_id):
    """Return the student id row."""
    cursor.execute("SELECT id FROM students WHERE user_id = %s", [user_id])
    return cursor.fetchone()


def fetch_attendance_totals(cursor, student_id):
    """Return the raw overall attendance row."""
    cursor.execute("""
            SELECT 
                total_lectures,
                total_present,
                total_late,
                total_absent,
                overall_percentage
            FROM student_overall_attendance
            WHERE student_id = %s
        """, [student_id])
    return cursor.fetchone()


def fetch_subject_attendance(cursor, student_id):
    """Return subject attendance rows."""
    cursor.execute("""
            SELECT 
                subject_id,
                subject_name,
                total_lectures_scheduled as total_lectures,
                lectures_attended as attended_lectures,
                attendance_percentage,
                lectures_attended as present_count,
                lectures_missed as absent_count,
                lectures_late as late_count
            FROM attendance_summary
            WHERE student_id = %s
            ORDER BY subject_name
        """, [student_id])
    return cursor.fetchall()


def fetch_recent_attendance(cursor, student_id):
    """Return the latest attendance rows."""
    cursor.execute("""
            SELECT 
                a.attendance_date,
                a.status,
                a.remarks,
                s.name as subject_name,
                CONCAT(c.name, ' - ', cl.name, ' ', d.name) as class_info,
                COALESCE(f.name, 'Unknown') as marked_by_name
            FROM attendance a
            JOIN students st ON a.student_id = st.id
            JOIN timetable t ON a.timetable_id = t.id
            JOIN subjects s ON t.subject_id = s.id
            JOIN courses c ON t.course_id = c.id
            JOIN classes cl ON t.class_id = cl.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN faculty f ON a.marked_by = f.id OR a.marked_by = f.user_id
            WHERE a.student_id = %s
            AND t.course_id = st.course_id
            AND t.class_id = st.class_id
            AND t.division_id = st.division_id
            AND a.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            ORDER BY a.attendance_date DESC, s.name
            LIMIT 50
        """, [student_id])
    return cursor.fetchall()


def fetch_subject_stats(cursor, student_id, subject_id):
    """Return one subject attendance row."""
    cursor.execute("""
            SELECT 
                subject_id,
                subject_name,
                total_lectures_scheduled as total_lectures,
                lectures_attended as attended_lectures,
                attendance_percentage,
                lectures_attended as present_count,
                lectures_missed as absent_count,
                lectures_late as late_count
            FROM attendance_summary
            WHERE student_id = %s AND subject_id = %s
        """, [student_id, subject_id])
    return cursor.fetchone()


def fetch_subject_records(cursor, student_id, subject_id):
    """Return attendance records for one subject."""
    cursor.execute("""
            SELECT 
                a.attendance_date,
                a.status,
                a.remarks,
                t.start_time,
                t.end_time,
                t.day_of_week,
                CONCAT(c.name, ' - ', cl.name, ' ', d.name) as class_info,
                COALESCE(f.name, 'Unknown') as marked_by_name,
                a.marked_at
            FROM attendance a
            JOIN students st ON a.student_id = st.id
            JOIN timetable t ON a.timetable_id = t.id
            JOIN courses c ON t.course_id = c.id
            JOIN classes cl ON t.class_id = cl.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN faculty f ON a.marked_by = f.id OR a.marked_by = f.user_id
            WHERE a.student_id = %s 
            AND t.course_id = st.course_id
            AND t.class_id = st.class_id
            AND t.division_id = st.division_id
            AND t.subject_id = %s
            ORDER BY a.attendance_date DESC, t.start_time DESC
        """, [student_id, subject_id])
    return cursor.fetchall()


def fetch_monthly_attendance(cursor, student_id, subject_id):
    """Return the six-month attendance breakdown."""
    cursor.execute("""
            SELECT 
                DATE_FORMAT(a.attendance_date, '%Y-%m') as month,
                COUNT(*) as total_lectures,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                ROUND((SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(*)) * 100, 2) as percentage
            FROM attendance a
            JOIN timetable t ON a.timetable_id = t.id
            WHERE a.student_id = %s 
            AND t.subject_id = %s
            AND a.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
            GROUP BY DATE_FORMAT(a.attendance_date, '%Y-%m')
            ORDER BY month DESC
        """, [student_id, subject_id])
    return cursor.fetchall()
