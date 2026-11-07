"""Admin student SQL. Callers pass a cursor."""


def run_query(cursor, query, params=None):
    """Run one assembled student query."""
    if params is None:
        cursor.execute(query)
    else:
        cursor.execute(query, params)
    return cursor.fetchall()


def run_one(cursor, query, params=None):
    """Run one assembled student query and return the first row."""
    if params is None:
        cursor.execute(query)
    else:
        cursor.execute(query, params)
    return cursor.fetchone()


def fetch_courses(cursor):
    """Return courses ordered by name."""
    cursor.execute("SELECT id, name FROM courses ORDER BY name")
    return cursor.fetchall()


def fetch_classes(cursor):
    """Return classes ordered for the student form."""
    cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name")
    return cursor.fetchall()


def fetch_divisions(cursor):
    """Return divisions ordered by name."""
    cursor.execute("SELECT id, name FROM divisions ORDER BY name")
    return cursor.fetchall()


def fetch_username(cursor, username):
    """Return a user id when the username exists. The value is a list."""
    cursor.execute("SELECT id FROM users WHERE username = %s", [username])
    return cursor.fetchone()


def fetch_student_email(cursor, email):
    """Return a student id when the email exists. The value is a list."""
    cursor.execute("SELECT id FROM students WHERE email = %s", [email])
    return cursor.fetchone()


def insert_student_user(cursor, username, hashed_password):
    """Insert a student login without an email column."""
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, 'Student')",
        (username, hashed_password),
    )
    return cursor.lastrowid


def insert_student_profile(cursor, values):
    """Insert one student profile. The student id matches the user id."""
    cursor.execute(
        "INSERT INTO students (id, user_id, name, email, phone, roll_number, course_id, class_id, division_id, admission_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        values,
    )


def fetch_student(cursor, student_id):
    """Return one student and username. The id is a list."""
    cursor.execute("""
        SELECT s.name, s.email, s.phone, s.roll_number, s.course_id, s.class_id, s.division_id, u.username
        FROM students s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = %s
    """, [student_id])
    return cursor.fetchone()


def update_student_profile(cursor, values):
    """Update one student profile."""
    cursor.execute("""
            UPDATE students 
            SET name = %s, email = %s, phone = %s, roll_number = %s, 
                course_id = %s, class_id = %s, division_id = %s
            WHERE id = %s
        """, values)


def update_user_password(cursor, hashed_password, student_id):
    """Store a password on the user row with the same id as the student."""
    cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, student_id))


def fetch_student_user_ids(cursor, student_ids):
    """Return user ids for the selected students."""
    format_strings = ','.join(['%s'] * len(student_ids))
    cursor.execute(
        f"SELECT user_id FROM students WHERE id IN ({format_strings})",
        tuple(student_ids),
    )
    return cursor.fetchall()


def deactivate_students(cursor, student_ids):
    """Soft-delete the selected students."""
    format_strings = ','.join(['%s'] * len(student_ids))
    cursor.execute(
        f"UPDATE students SET is_active = 0 WHERE id IN ({format_strings})",
        tuple(student_ids),
    )


def deactivate_student_users(cursor, user_ids):
    """Soft-delete linked users, leaving Super Admin untouched."""
    user_format_strings = ','.join(['%s'] * len(user_ids))
    cursor.execute(
        f"UPDATE users SET status = 'inactive' WHERE id IN ({user_format_strings}) AND role != 'Super Admin'",
        tuple(user_ids),
    )


def insert_invited_user(cursor, username, hashed_password, email):
    """Insert a student login created by bulk invite."""
    cursor.execute(
        "INSERT INTO users (username, password, role, email, status) VALUES (%s, %s, 'Student', %s, 'active')",
        (username, hashed_password, email),
    )
    return cursor.lastrowid


def insert_invited_student(cursor, values):
    """Insert a student profile created by bulk invite."""
    cursor.execute(
        "INSERT INTO students (id, user_id, name, email, course_id, class_id, division_id, admission_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        values,
    )
