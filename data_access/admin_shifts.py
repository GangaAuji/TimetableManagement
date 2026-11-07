"""Shift pattern and faculty availability SQL. Callers pass a cursor."""


def fetch_shift_patterns(cursor):
    """Return shift patterns with a faculty count."""
    cursor.execute("""
            SELECT sp.*, 
                   COUNT(DISTINCT fa.faculty_id) as faculty_count
            FROM shift_patterns sp
            LEFT JOIN faculty_availability fa ON sp.id = fa.shift_pattern_id
            GROUP BY sp.id
            ORDER BY sp.shift_order
        """)
    return cursor.fetchall()


def count_active_shifts(cursor):
    """Return the active shift-pattern count row."""
    cursor.execute("SELECT COUNT(*) as count FROM shift_patterns WHERE is_active = TRUE")
    return cursor.fetchone()


def count_faculty_with_shifts(cursor):
    """Return the distinct faculty-availability count row."""
    cursor.execute("SELECT COUNT(DISTINCT faculty_id) as count FROM faculty_availability")
    return cursor.fetchone()


def insert_shift_pattern(cursor, values):
    """Insert one shift pattern."""
    cursor.execute("""
            INSERT INTO shift_patterns 
            (shift_name, shift_code, start_time, end_time, shift_order, description, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, values)


def update_shift_pattern(cursor, values):
    """Update one shift pattern."""
    cursor.execute("""
            UPDATE shift_patterns 
            SET shift_name = %s, shift_code = %s, start_time = %s, end_time = %s,
                shift_order = %s, description = %s, is_active = %s
            WHERE id = %s
        """, values)


def count_shift_usage(cursor, shift_id):
    """Return the usage count row for one shift pattern."""
    cursor.execute("""
            SELECT COUNT(*) as count FROM faculty_availability 
            WHERE shift_pattern_id = %s
        """, (shift_id,))
    return cursor.fetchone()


def delete_shift_pattern(cursor, shift_id):
    """Delete one shift pattern."""
    cursor.execute("DELETE FROM shift_patterns WHERE id = %s", (shift_id,))


def fetch_active_faculty(cursor):
    """Return active faculty with department names."""
    cursor.execute("""
            SELECT f.id, f.user_id, f.name, f.email, f.department_id, d.name as department_name
            FROM faculty f
            LEFT JOIN departments d ON f.department_id = d.id
            WHERE f.is_active = TRUE
            ORDER BY d.name, f.name
        """)
    return cursor.fetchall()


def fetch_availability_records(cursor):
    """Return every faculty availability row."""
    cursor.execute("""
            SELECT fa.faculty_id, fa.day_of_week, fa.is_available,
                   fa.shift_pattern_id, fa.start_time, fa.end_time, fa.notes,
                   sp.shift_code, sp.shift_name, sp.start_time as shift_start, sp.end_time as shift_end
            FROM faculty_availability fa
            LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
        """)
    return cursor.fetchall()


def fetch_active_shift_choices(cursor):
    """Return active shift patterns for the availability page."""
    cursor.execute("""
            SELECT id, shift_name, shift_code, start_time, end_time, 
                   shift_order, description, is_active
            FROM shift_patterns 
            WHERE is_active = TRUE 
            ORDER BY shift_order
        """)
    return cursor.fetchall()


def fetch_active_departments(cursor):
    """Return active departments."""
    cursor.execute("SELECT id, name FROM departments WHERE is_active = TRUE ORDER BY name")
    return cursor.fetchall()


def fetch_day_availability(cursor, faculty_user_id, day_of_week):
    """Return one faculty day row."""
    cursor.execute("""
            SELECT id, shift_pattern_id, notes FROM faculty_availability 
            WHERE faculty_id = %s AND day_of_week = %s
        """, (faculty_user_id, day_of_week))
    return cursor.fetchone()


def fetch_day_availability_id(cursor, faculty_user_id, day):
    """Return the id row for one faculty day."""
    cursor.execute("""
                    SELECT id FROM faculty_availability 
                    WHERE faculty_id = %s AND day_of_week = %s
                """, (faculty_user_id, day))
    return cursor.fetchone()


def update_day_availability(cursor, is_available, shift_pattern_id, notes, row_id):
    """Update one availability row."""
    cursor.execute("""
                UPDATE faculty_availability 
                SET is_available = %s, shift_pattern_id = %s, notes = %s
                WHERE id = %s
            """, (is_available, shift_pattern_id, notes, row_id))


def insert_day_availability(cursor, faculty_user_id, day_of_week, is_available, shift_pattern_id, notes):
    """Insert one availability row."""
    cursor.execute("""
                INSERT INTO faculty_availability 
                (faculty_id, day_of_week, is_available, shift_pattern_id, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (faculty_user_id, day_of_week, is_available, shift_pattern_id, notes))


def fetch_faculty_available_days(cursor, faculty_user_id):
    """Return available days for one faculty user."""
    cursor.execute("""
            SELECT fa.day_of_week, fa.is_available, 
                   sp.start_time, sp.end_time, sp.shift_name
            FROM faculty_availability fa
            LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
            WHERE fa.faculty_id = %s AND fa.is_available = TRUE
            ORDER BY fa.day_of_week
        """, (faculty_user_id,))
    return cursor.fetchall()


def fetch_active_patterns(cursor):
    """Return active shift patterns for the API."""
    cursor.execute("""
            SELECT id, shift_name, shift_code, start_time, end_time, 
                   shift_order, is_active
            FROM shift_patterns 
            WHERE is_active = TRUE
            ORDER BY shift_order
        """)
    return cursor.fetchall()


def fetch_change_requests(cursor):
    """Return shift change requests."""
    cursor.execute("""
            SELECT scr.id, scr.faculty_id, scr.day_of_week, 
                   scr.current_shift_name, scr.requested_shift_name,
                   scr.reason, scr.status, scr.admin_response,
                   scr.created_at, scr.reviewed_at,
                   f.name as faculty_name, d.name as department_name,
                   u.username as reviewed_by_name
            FROM shift_change_requests scr
            JOIN faculty f ON scr.faculty_id = f.user_id
            LEFT JOIN departments d ON f.department_id = d.id
            LEFT JOIN users u ON scr.reviewed_by = u.id
            ORDER BY 
                CASE scr.status 
                    WHEN 'pending' THEN 1 
                    WHEN 'approved' THEN 2 
                    ELSE 3 
                END,
                scr.created_at DESC
        """)
    return cursor.fetchall()


def fetch_change_request(cursor, request_id):
    """Return one shift change request."""
    cursor.execute("""
            SELECT faculty_id, day_of_week, requested_shift_name
            FROM shift_change_requests
            WHERE id = %s
        """, (request_id,))
    return cursor.fetchone()


def update_change_request(cursor, status, admin_response, user_id, request_id):
    """Store a review on one shift change request."""
    cursor.execute("""
            UPDATE shift_change_requests
            SET status = %s, admin_response = %s, 
                reviewed_by = %s, reviewed_at = NOW()
            WHERE id = %s
        """, (status, admin_response, user_id, request_id))


def fetch_shift_by_name(cursor, requested_shift_name):
    """Return a shift pattern matching a requested name."""
    cursor.execute("""
                SELECT id FROM shift_patterns 
                WHERE shift_name LIKE %s OR shift_code LIKE %s
                LIMIT 1
            """, (f"%{requested_shift_name}%", f"%{requested_shift_name}%"))
    return cursor.fetchone()


def upsert_approved_availability(cursor, faculty_id, day_of_week, shift_id):
    """Store an approved shift on the faculty availability row."""
    cursor.execute("""
                INSERT INTO faculty_availability 
                (faculty_id, day_of_week, is_available, shift_pattern_id, notes)
                VALUES (%s, %s, 1, %s, 'Approved shift change request')
                ON DUPLICATE KEY UPDATE
                    shift_pattern_id = VALUES(shift_pattern_id),
                    is_available = 1,
                    notes = 'Approved shift change request'
            """, (faculty_id, day_of_week, shift_id))
