"""User-list SQL. Callers pass a cursor."""


def fetch_role_names(cursor):
    """Return role names in display order."""
    cursor.execute('SELECT name FROM roles ORDER BY name')
    return cursor.fetchall()


def fetch_users(cursor, role_filter, status_filter, search):
    """Return users, optionally limited by role, status, and username."""
    conditions = []
    params = []
    if role_filter:
        conditions.append("u.role = %s")
        params.append(role_filter)
    if status_filter:
        conditions.append("u.status = %s")
        params.append(status_filter)
    if search:
        conditions.append("(u.username LIKE %s)")
        params.extend([f"%{search}%"])
    query = """
        SELECT u.id, u.username, u.role, u.status, u.last_login,
               u.username as display_name
        FROM users u
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY u.username"
    cursor.execute(query, params)
    return cursor.fetchall()


def fetch_user_id_by_username(cursor, username):
    """Return a user id row when the username is taken."""
    cursor.execute('SELECT id FROM users WHERE username = %s', [username])
    return cursor.fetchone()


def insert_user(cursor, username, hashed_password, role, status):
    """Insert a user and return the new id."""
    cursor.execute(
        'INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)',
        [username, hashed_password, role, status],
    )
    return cursor.lastrowid


def fetch_user_record(cursor, user_id):
    """Return one user row for the lookup."""
    cursor.execute(
        "SELECT id, username, email, role, status, last_login, is_hod, department_id FROM users WHERE id = %s",
        [user_id],
    )
    return cursor.fetchone()


def fetch_user_for_edit(cursor, user_id):
    """Return the id, role, status, and lock for the user being edited."""
    cursor.execute('SELECT id, role, status, locked_until FROM users WHERE id = %s', [user_id])
    return cursor.fetchone()


def fetch_other_user_by_username(cursor, username, user_id):
    """Return another user row that already has this username."""
    cursor.execute(
        'SELECT id FROM users WHERE username = %s AND id != %s',
        [username, user_id],
    )
    return cursor.fetchone()


def fetch_other_user_by_email(cursor, email, user_id):
    """Return another user row that already has this email."""
    cursor.execute(
        'SELECT id FROM users WHERE email = %s AND id != %s',
        [email, user_id],
    )
    return cursor.fetchone()


def update_user_with_password(cursor, values):
    """Update the user, including the password."""
    cursor.execute('''
                    UPDATE users 
                    SET username=%s, email=%s, password=%s, role=%s, status=%s, department_id=%s, is_hod=%s
                    WHERE id=%s
                ''', values)


def update_user_without_password(cursor, values):
    """Update the user and leave the password unchanged."""
    cursor.execute('''
                    UPDATE users 
                    SET username=%s, email=%s, role=%s, status=%s, department_id=%s, is_hod=%s
                    WHERE id=%s
                ''', values)


def fetch_faculty_profile(cursor, user_id):
    """Return the faculty row linked by user id or by the same id."""
    cursor.execute(
        """
        SELECT id, user_id, name, email, phone, department_id
        FROM faculty
        WHERE user_id = %s OR id = %s
        ORDER BY user_id = %s DESC, id ASC
        LIMIT 1
        """,
        [user_id, user_id, user_id],
    )
    return cursor.fetchone()


def fetch_student_contact(cursor, user_id):
    """Return the student name, phone, and course used to fill a faculty profile."""
    cursor.execute(
        """
        SELECT name, phone, course_id
        FROM students
        WHERE user_id = %s OR id = %s
        ORDER BY user_id = %s DESC, id ASC
        LIMIT 1
        """,
        [user_id, user_id, user_id],
    )
    return cursor.fetchone()


def fetch_student_profile(cursor, user_id):
    """Return the student row linked by user id or by the same id."""
    cursor.execute(
        """
        SELECT id, user_id, name, email, phone, course_id
        FROM students
        WHERE user_id = %s OR id = %s
        ORDER BY user_id = %s DESC, id ASC
        LIMIT 1
        """,
        [user_id, user_id, user_id],
    )
    return cursor.fetchone()


def fetch_faculty_contact(cursor, user_id):
    """Return the faculty name, phone, and department used to fill a student profile."""
    cursor.execute(
        """
        SELECT name, phone, department_id
        FROM faculty
        WHERE user_id = %s OR id = %s
        ORDER BY user_id = %s DESC, id ASC
        LIMIT 1
        """,
        [user_id, user_id, user_id],
    )
    return cursor.fetchone()


def fetch_course_department_id(cursor, course_id):
    """Return the department for one course."""
    cursor.execute("SELECT department_id FROM courses WHERE id = %s", [course_id])
    return cursor.fetchone()


def fetch_default_department_id(cursor):
    """Return the first department id."""
    cursor.execute("SELECT id FROM departments ORDER BY id LIMIT 1")
    return cursor.fetchone()


def fetch_default_course_id(cursor):
    """Return the first course id."""
    cursor.execute("SELECT id FROM courses ORDER BY id LIMIT 1")
    return cursor.fetchone()


def fetch_first_course_for_department(cursor, department_id):
    """Return the first course in one department."""
    cursor.execute(
        "SELECT id FROM courses WHERE department_id = %s ORDER BY id LIMIT 1",
        [department_id],
    )
    return cursor.fetchone()


def update_faculty_profile(cursor, values):
    """Point an existing faculty row at this user."""
    cursor.execute(
        """
            UPDATE faculty
            SET user_id = %s,
                name = %s,
                email = %s,
                phone = %s,
                department_id = %s,
                is_active = 1
            WHERE id = %s
            """,
        values,
    )


def insert_faculty_profile(cursor, values):
    """Insert a faculty row. The id is the user id."""
    cursor.execute(
        """
        INSERT INTO faculty (id, user_id, name, email, department_id, employee_id, phone, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        """,
        values,
    )


def update_student_profile(cursor, values):
    """Point an existing student row at this user."""
    cursor.execute(
        """
            UPDATE students
            SET user_id = %s,
                email = %s,
                is_active = 1
            WHERE id = %s
            """,
        values,
    )


def insert_student_profile(cursor, values):
    """Insert a student row. The id is the user id."""
    cursor.execute(
        """
        INSERT INTO students (id, user_id, name, email, phone, course_id, admission_id, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        """,
        values,
    )


def deactivate_students(cursor, user_id):
    """Mark this user's student rows inactive."""
    cursor.execute("UPDATE students SET is_active = 0 WHERE user_id = %s", [user_id])


def deactivate_faculty(cursor, user_id):
    """Mark this user's faculty rows inactive."""
    cursor.execute("UPDATE faculty SET is_active = 0 WHERE user_id = %s", [user_id])


def set_faculty_active(cursor, is_active, user_id):
    """Set the faculty active flag for this user."""
    cursor.execute("UPDATE faculty SET is_active = %s WHERE user_id = %s", [is_active, user_id])


def set_student_active(cursor, is_active, user_id):
    """Set the student active flag for this user."""
    cursor.execute("UPDATE students SET is_active = %s WHERE user_id = %s", [is_active, user_id])


def fetch_user_identity(cursor, user_id):
    """Return the username and role before a deactivation."""
    cursor.execute('SELECT username, role FROM users WHERE id = %s', [user_id])
    return cursor.fetchone()


def mark_user_inactive(cursor, user_id):
    """Mark one user account inactive."""
    cursor.execute("UPDATE users SET status = 'inactive' WHERE id = %s", [user_id])
