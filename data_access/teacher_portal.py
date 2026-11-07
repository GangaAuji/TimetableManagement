"""Teacher class, absence, and availability SQL. Callers pass a cursor."""


def fetch_faculty_user_id(cursor, faculty_id):
    """Return the user id row for a faculty table id."""
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    return cursor.fetchone()


def fetch_teaching_assignments(cursor, faculty_user_id):
    """Return the classes taught by one faculty user."""
    cursor.execute(
        """
        SELECT DISTINCT 
            cl.id as class_id,
            cl.name as class_name, 
            d.id as division_id,
            d.name as division_name, 
            co.id as course_id,
            co.name as course_name,
            s.id as subject_id,
            s.name as subject_name
        FROM timetable t
        JOIN classes cl ON t.class_id = cl.id
        JOIN divisions d ON t.division_id = d.id
        JOIN courses co ON t.course_id = co.id
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.faculty_id = %s
        ORDER BY cl.name, d.name, co.name, s.name
        """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_class_students(cursor, class_id, division_id, course_id):
    """Return students in one class, division, and course."""
    cursor.execute(
        """
            SELECT st.id, st.name, st.email, u.username
            FROM students st
            JOIN users u ON st.user_id = u.id
            WHERE st.class_id = %s 
                AND st.division_id = %s 
                AND st.course_id = %s
            ORDER BY st.name
            """,
        [class_id, division_id, course_id],
    )
    return cursor.fetchall()


def fetch_faculty_absences(cursor, faculty_id):
    """Return absences for one faculty table id."""
    cursor.execute(
        "SELECT id, absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC",
        [faculty_id],
    )
    return cursor.fetchall()


def insert_unprocessed_absence(cursor, faculty_id, absence_date, reason):
    """Insert a teacher absence that still needs processing."""
    cursor.execute(
        "INSERT INTO faculty_absences (faculty_id, absence_date, reason, status) VALUES (%s, %s, %s, 'UNPROCESSED')",
        (faculty_id, absence_date, reason),
    )


def fetch_absence_status(cursor, absence_id, faculty_id):
    """Return the status of one absence owned by this faculty member."""
    cursor.execute(
        "SELECT status FROM faculty_absences WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )
    return cursor.fetchone()


def delete_faculty_absence(cursor, absence_id, faculty_id):
    """Delete one absence owned by this faculty member."""
    cursor.execute(
        "DELETE FROM faculty_absences WHERE id = %s AND faculty_id = %s",
        (absence_id, faculty_id),
    )


def delete_faculty_availability(cursor, faculty_user_id):
    """Remove every availability row for one faculty user."""
    cursor.execute("DELETE FROM faculty_availability WHERE faculty_id = %s", [faculty_user_id])


def insert_availability_slot(cursor, faculty_user_id, day_num, is_available, start_time, end_time, notes):
    """Insert one availability slot."""
    cursor.execute(
        """
                            INSERT INTO faculty_availability 
                            (faculty_id, day_of_week, is_available, start_time, end_time, notes)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
        (faculty_user_id, day_num, is_available, start_time, end_time, notes),
    )


def fetch_availability_slots(cursor, faculty_user_id):
    """Return availability slots with their shift pattern."""
    cursor.execute("""
        SELECT fa.day_of_week, fa.is_available, fa.start_time, fa.end_time, fa.notes,
               fa.shift_pattern_id, sp.shift_name, sp.shift_code,
               sp.start_time as shift_start, sp.end_time as shift_end
        FROM faculty_availability fa
        LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
        WHERE fa.faculty_id = %s
        ORDER BY fa.day_of_week, fa.start_time
    """, [faculty_user_id])
    return cursor.fetchall()


def fetch_faculty_by_user(cursor, user_id):
    """Return the faculty row for a user id."""
    cursor.execute("SELECT id, user_id, name FROM faculty WHERE user_id = %s", (user_id,))
    return cursor.fetchone()


def fetch_assignments(cursor, faculty_user_id):
    """Return allocated subjects for one faculty user."""
    cursor.execute(
        """
        SELECT dep.name AS department, crs.name AS course, c.name AS class_name, d.name AS division_name,
               s.id AS subject_id, s.name AS subject_name, COALESCE(s.syllabus_url, '') AS syllabus_url
        FROM faculty_allocations fa
        JOIN subjects s ON s.id = fa.subject_id
        JOIN classes c ON c.id = fa.class_id
        JOIN divisions d ON d.id = fa.division_id
        JOIN courses crs ON crs.id = s.course_id
        JOIN departments dep ON dep.id = crs.department_id
        WHERE fa.faculty_id = %s
        ORDER BY dep.name, crs.name, c.name, d.name, s.name
        """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_day_schedule(cursor, faculty_user_id, today_day):
    """Return one day's timetable rows."""
    cursor.execute(
        """
        SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s AND t.day_of_week = %s
        ORDER BY t.start_time
        """,
        [faculty_user_id, today_day],
    )
    return cursor.fetchall()


def fetch_week_schedule(cursor, faculty_user_id):
    """Return the weekly timetable rows."""
    cursor.execute(
        """
        SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s
        ORDER BY 
            CASE t.day_of_week
                WHEN 'Monday' THEN 1
                WHEN 'Tuesday' THEN 2
                WHEN 'Wednesday' THEN 3
                WHEN 'Thursday' THEN 4
                WHEN 'Friday' THEN 5
                WHEN 'Saturday' THEN 6
                WHEN 'Sunday' THEN 7
            END,
            t.start_time
        """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_absence_rows(cursor, faculty_id):
    """Return absence rows for the teacher dashboard."""
    cursor.execute(
        "SELECT absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC",
        [faculty_id],
    )
    return cursor.fetchall()


def fetch_teaching_class_counts(cursor, faculty_user_id):
    """Return classes with a student count."""
    cursor.execute(
        """
        SELECT DISTINCT 
            cl.name as class_name, 
            d.name as division_name, 
            co.name as course_name,
            s.name as subject_name,
            COUNT(DISTINCT st.id) as student_count
        FROM timetable t
        JOIN classes cl ON t.class_id = cl.id
        JOIN divisions d ON t.division_id = d.id
        JOIN courses co ON t.course_id = co.id
        JOIN subjects s ON t.subject_id = s.id
        LEFT JOIN students st ON st.class_id = t.class_id 
            AND st.division_id = t.division_id 
            AND st.course_id = t.course_id
        WHERE t.faculty_id = %s
        GROUP BY cl.id, d.id, co.id, s.id
        ORDER BY cl.name, d.name, s.name
        """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_timetable_rows(cursor, faculty_user_id):
    """Return timetable rows for the teacher timetable page."""
    cursor.execute(
        """
        SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_timetable_download_rows(cursor, faculty_user_id):
    """Return timetable rows for the CSV download."""
    cursor.execute(
        """
        SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_shift_faculty(cursor, faculty_id):
    """Return the faculty name and department for the shifts page."""
    cursor.execute("""
            SELECT f.name, f.email, d.name as department_name
            FROM faculty f
            LEFT JOIN departments d ON f.department_id = d.id
            WHERE f.id = %s
        """, (faculty_id,))
    return cursor.fetchone()


def fetch_shift_availability(cursor, faculty_user_id):
    """Return availability rows with shift patterns."""
    cursor.execute("""
            SELECT fa.day_of_week, fa.is_available, fa.notes,
                   sp.shift_name, sp.shift_code, sp.start_time, sp.end_time
            FROM faculty_availability fa
            LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
            WHERE fa.faculty_id = %s
            ORDER BY fa.day_of_week
        """, (faculty_user_id,))
    return cursor.fetchall()


def fetch_shift_requests(cursor, faculty_user_id):
    """Return the latest shift-change requests."""
    cursor.execute("""
            SELECT id, day_of_week, current_shift_name, requested_shift_name, 
                   reason, status, created_at, admin_response
            FROM shift_change_requests
            WHERE faculty_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (faculty_user_id,))
    return cursor.fetchall()


def insert_shift_request(cursor, faculty_user_id, day_of_week, current_shift_name, requested_shift_name, reason):
    """Insert a pending shift-change request."""
    cursor.execute("""
            INSERT INTO shift_change_requests 
            (faculty_id, day_of_week, current_shift_name, requested_shift_name, reason, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
        """, (faculty_user_id, day_of_week, current_shift_name, requested_shift_name, reason))


def fetch_proxy_logs(cursor, faculty_user_id):
    """Return proxy rows where this faculty user is original or proxy."""
    cursor.execute(
        """
        SELECT p.id, p.absence_date, p.status, p.approval_status, t.day_of_week, t.start_time, t.end_time, s.name AS subject_name,
               ofc.name AS original_name, pfc.name AS proxy_name
        FROM proxy_log p
        JOIN timetable t ON p.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN faculty ofc ON ofc.user_id = p.original_faculty_id
        LEFT JOIN faculty pfc ON pfc.user_id = p.proxy_faculty_id
        WHERE p.original_faculty_id = %s OR p.proxy_faculty_id = %s
        ORDER BY p.absence_date DESC, t.start_time
        """,
        (faculty_user_id, faculty_user_id),
    )
    return cursor.fetchall()


def fetch_faculty_lectures(cursor, faculty_user_id):
    """Return lectures taught by one faculty user."""
    cursor.execute(
        """
        SELECT t.id, t.day_of_week, t.start_time, t.end_time, s.name
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        WHERE t.faculty_id = %s
        ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), t.start_time
        """,
        [faculty_user_id],
    )
    return cursor.fetchall()


def fetch_proxy_candidates(cursor, faculty_id):
    """Return other faculty allocated by faculty table id."""
    cursor.execute(
        """
        SELECT fa.subject_id, fa.faculty_id, f.name
        FROM faculty_allocations fa
        JOIN faculty f ON f.id = fa.faculty_id
        WHERE fa.faculty_id != %s
        """,
        [faculty_id],
    )
    return cursor.fetchall()


def fetch_owned_lecture(cursor, timetable_id, faculty_user_id):
    """Return a lecture owned by this faculty user."""
    cursor.execute(
        "SELECT day_of_week, subject_id, start_time, end_time FROM timetable WHERE id = %s AND faculty_id = %s",
        (timetable_id, faculty_user_id),
    )
    return cursor.fetchone()


def insert_pending_proxy(cursor, faculty_user_id, proxy_user_id, timetable_id, absence_date):
    """Insert a teacher proxy request with status PENDING."""
    cursor.execute(
        """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
        (faculty_user_id, proxy_user_id, timetable_id, absence_date, 'PENDING'),
    )


def fetch_lectures_on_day(cursor, faculty_id, day_of_week):
    """Return lectures for one faculty on one weekday."""
    cursor.execute(
        "SELECT id, subject_id, start_time, end_time FROM timetable WHERE faculty_id = %s AND day_of_week = %s",
        (faculty_id, day_of_week),
    )
    return cursor.fetchall()


def fetch_other_allocated_faculty(cursor, subject_id, faculty_id):
    """Return faculty allocated to a subject except one faculty."""
    cursor.execute(
        "SELECT faculty_id FROM faculty_allocations WHERE subject_id = %s AND faculty_id != %s",
        (subject_id, faculty_id),
    )
    return cursor.fetchall()


def insert_assigned_proxy(cursor, original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status):
    """Insert a teacher proxy row with status only."""
    cursor.execute(
        """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
        (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status),
    )
