"""Admin dashboard SQL. Callers pass a cursor."""


def count_active(cursor, table):
    """Return the active-row count for one known table."""
    if table not in ('students', 'faculty', 'courses', 'departments', 'course_batches'):
        raise ValueError(table)
    cursor.execute(f"SELECT COUNT(id) as count FROM {table} WHERE is_active = 1")
    return cursor.fetchone()


def count_rows(cursor, table):
    """Return the row count for one known table."""
    if table not in ('rooms', 'subjects', 'faculty_allocations'):
        raise ValueError(table)
    cursor.execute(f"SELECT COUNT(id) as count FROM {table}")
    return cursor.fetchone()


def fetch_room_breakdown(cursor):
    """Return room counts by type."""
    cursor.execute("SELECT room_type, COUNT(*) as count FROM rooms GROUP BY room_type")
    return cursor.fetchall()


def fetch_weekly_load(cursor):
    """Return timetable rows per weekday."""
    cursor.execute("""
            SELECT day_of_week, COUNT(*) as class_count
            FROM timetable
            GROUP BY day_of_week
            ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')
        """)
    return cursor.fetchall()


def fetch_session_types(cursor):
    """Return timetable rows by theory or practical."""
    cursor.execute("""
            SELECT s.theory_practical, COUNT(t.id) as count
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            GROUP BY s.theory_practical
        """)
    return cursor.fetchall()


def fetch_todays_classes(cursor, today):
    """Return today's timetable rows."""
    cursor.execute("""
            SELECT t.start_time, t.end_time, s.name as subject_name, 
                   f.name as faculty_name, r.room_number,
                   c.name as class_name, d.name as division_name,
                   s.theory_practical,
                   dept.name as department_name,
                   course.name as course_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN faculty f ON t.faculty_id = f.user_id
            LEFT JOIN rooms r ON t.room_id = r.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
            LEFT JOIN courses course ON s.course_id = course.id
            LEFT JOIN departments dept ON course.department_id = dept.id
            WHERE t.day_of_week = %s
            ORDER BY t.start_time
            LIMIT 50
        """, (today,))
    return cursor.fetchall()


def fetch_recent_proxies(cursor):
    """Return the five newest proxy rows."""
    cursor.execute("""
            SELECT pl.id, pl.absence_date, 
                   f1.name as original_faculty, 
                   f2.name as proxy_faculty,
                   pl.status, pl.approval_status,
                   s.name as subject_name,
                   pl.approval_date
            FROM proxy_log pl
            JOIN faculty f1 ON pl.original_faculty_id = f1.user_id
            LEFT JOIN faculty f2 ON pl.proxy_faculty_id = f2.user_id
            JOIN timetable t ON pl.timetable_id = t.id
            JOIN subjects s ON t.subject_id = s.id
            ORDER BY pl.absence_date DESC, pl.id DESC
            LIMIT 5
        """)
    return cursor.fetchall()


def fetch_upcoming_holidays(cursor):
    """Return the next five dated holidays."""
    cursor.execute("""
            SELECT name, holiday_date, applies_to_program
            FROM institution_holidays
            WHERE holiday_date >= CURDATE()
            ORDER BY holiday_date
            LIMIT 5
        """)
    return cursor.fetchall()


def fetch_faculty_workload(cursor):
    """Return the five busiest active faculty members."""
    cursor.execute("""
            SELECT f.name, 
                   COUNT(t.id) as class_count,
                   COALESCE(SUM(TIMESTAMPDIFF(MINUTE, t.start_time, t.end_time) / 60), 0) as hours
            FROM faculty f
            LEFT JOIN timetable t ON f.user_id = t.faculty_id
            WHERE f.is_active = 1
            GROUP BY f.user_id, f.name
            ORDER BY class_count DESC
            LIMIT 5
        """)
    return cursor.fetchall()
