"""Sign-in SQL. Callers pass a cursor."""


_LOGIN_COLUMNS = """id, password, role, status, locked_until,
    locked_until IS NOT NULL AND locked_until > NOW() AS locked_now,
    GREATEST(TIMESTAMPDIFF(SECOND, NOW(), locked_until), 0) AS lock_seconds"""


def fetch_login_user(cursor, username):
    """Return a non-admin user row for this username, with its lock state."""
    cursor.execute(
        f"SELECT {_LOGIN_COLUMNS} FROM users WHERE username = %s AND role NOT IN ('Admin', 'Super Admin')",
        (username,),
    )
    return cursor.fetchone()


def fetch_admin_login_user(cursor, username):
    """Return an admin, super admin, or HOD row for this username, with its lock state."""
    cursor.execute(
        f"SELECT {_LOGIN_COLUMNS} FROM users WHERE username = %s AND role IN ('Admin', 'Super Admin', 'HOD')",
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


def fetch_student_links(cursor, user_id):
    """Return every student row linked to this user. Login requires exactly one."""
    cursor.execute(
        "SELECT id, name, email, course_id, class_id, division_id FROM students WHERE user_id = %s",
        (user_id,),
    )
    return cursor.fetchall()


def fetch_faculty_links(cursor, user_id):
    """Return every faculty row linked to this user. Login requires exactly one."""
    cursor.execute(
        "SELECT id, name, email, department_id FROM faculty WHERE user_id = %s",
        (user_id,),
    )
    return cursor.fetchall()


def update_password_hash(cursor, hashed_password, user_id):
    """Replace a stored password with a one-way hash."""
    cursor.execute(
        "UPDATE users SET password = %s WHERE id = %s",
        (hashed_password, user_id),
    )
