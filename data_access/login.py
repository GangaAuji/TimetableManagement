"""Sign-in SQL. Callers pass a cursor."""


def fetch_login_user(cursor, username):
    """Return a non-admin user row for this username."""
    cursor.execute(
        "SELECT id, password, role, status FROM users WHERE username = %s AND role NOT IN ('Admin', 'Super Admin')",
        (username,),
    )
    return cursor.fetchone()


def fetch_admin_login_user(cursor, username):
    """Return an admin, super admin, or HOD row for this username."""
    cursor.execute(
        "SELECT id, password, role, status FROM users WHERE username = %s AND role IN ('Admin', 'Super Admin', 'HOD')",
        (username,),
    )
    return cursor.fetchone()


def insert_user_session(cursor, session_id, user_id, ip_address, user_agent, expires_at):
    """Insert the login session row."""
    cursor.execute("""
                INSERT INTO user_sessions 
                (session_id, user_id, ip_address, user_agent, expires_at, is_active) 
                VALUES (%s, %s, %s, %s, %s, 1)
            """, (session_id, user_id, ip_address, user_agent, expires_at))


def update_last_login(cursor, user_id):
    """Stamp the user's last login."""
    cursor.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))


def deactivate_user_session(cursor, session_id):
    """Mark one login session inactive."""
    cursor.execute("""
                UPDATE user_sessions 
                SET is_active = 0 
                WHERE session_id = %s
            """, (session_id,))


def fetch_user_profile(cursor, user_id):
    """Return department, HOD flag, and profile photo."""
    cursor.execute("SELECT department_id, is_hod, profile_photo FROM users WHERE id = %s", (user_id,))
    return cursor.fetchone()


def fetch_student_by_user(cursor, user_id):
    """Return the student row linked to this user."""
    cursor.execute(
        "SELECT id, name, email, course_id, class_id, division_id FROM students WHERE user_id = %s",
        (user_id,),
    )
    return cursor.fetchone()


def fetch_student_fallback(cursor):
    """Return the first student row when the user link is missing."""
    cursor.execute(
        "SELECT id, name, email, course_id, class_id, division_id FROM students LIMIT 1"
    )
    return cursor.fetchone()


def fetch_faculty_by_user(cursor, user_id):
    """Return the faculty row linked to this user."""
    cursor.execute(
        "SELECT id, name, email, department_id FROM faculty WHERE user_id = %s",
        (user_id,),
    )
    return cursor.fetchone()


def fetch_faculty_fallback(cursor):
    """Return the first faculty row when the user link is missing."""
    cursor.execute(
        "SELECT id, name, email, department_id FROM faculty LIMIT 1"
    )
    return cursor.fetchone()
