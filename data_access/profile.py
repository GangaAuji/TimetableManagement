"""Profile SQL. Callers pass a cursor."""


def fetch_profile_user(cursor, user_id):
    """Return the account row shown on the profile page."""
    cursor.execute("""
            SELECT u.id, u.username, u.role, u.email,
                   u.profile_photo, u.phone, u.address, 
                   u.bio, u.date_of_birth, u.status, u.last_login, 
                   u.created_at, u.department_id, u.is_hod
            FROM users u
            WHERE u.id = %s
        """, [user_id])
    return cursor.fetchone()


def fetch_department_name(cursor, department_id):
    """Return a department name row."""
    cursor.execute("SELECT name FROM departments WHERE id = %s", [department_id])
    return cursor.fetchone()


def fetch_faculty_email(cursor, user_id):
    """Return the faculty email row for this user."""
    cursor.execute("""
                SELECT f.email FROM faculty f WHERE f.user_id = %s
            """, [user_id])
    return cursor.fetchone()


def fetch_student_email(cursor, user_id):
    """Return the student email row for this user."""
    cursor.execute("""
                SELECT s.email FROM students s WHERE s.user_id = %s
            """, [user_id])
    return cursor.fetchone()


def fetch_profile_form(cursor, user_id):
    """Return the row used to fill the profile form."""
    cursor.execute("""
            SELECT u.id, u.username, u.email, u.role, u.phone, u.address, 
                   u.bio, u.date_of_birth, u.profile_photo,
                   d.name as department_name
            FROM users u
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE u.id = %s
        """, [user_id])
    return cursor.fetchone()


def update_profile_with_photo(cursor, values):
    """Update profile fields and the photo."""
    cursor.execute("""
                    UPDATE users 
                    SET email = %s, phone = %s, address = %s, bio = %s, 
                        date_of_birth = %s, profile_photo = %s
                    WHERE id = %s
                """, values)


def update_profile_without_photo(cursor, values):
    """Update profile fields and leave the photo unchanged."""
    cursor.execute("""
                    UPDATE users 
                    SET email = %s, phone = %s, address = %s, bio = %s, date_of_birth = %s
                    WHERE id = %s
                """, values)


def update_faculty_email(cursor, email, user_id):
    """Copy the profile email onto the faculty row."""
    cursor.execute("""
                    UPDATE faculty 
                    SET email = %s
                    WHERE user_id = %s
                """, [email, user_id])


def update_student_email(cursor, email, user_id):
    """Copy the profile email onto the student row."""
    cursor.execute("""
                    UPDATE students 
                    SET email = %s
                    WHERE user_id = %s
                """, [email, user_id])


def fetch_password_hash(cursor, user_id):
    """Return the stored password row."""
    cursor.execute("SELECT password FROM users WHERE id = %s", [user_id])
    return cursor.fetchone()


def update_password(cursor, hashed_password, user_id):
    """Store a new password hash."""
    cursor.execute(
        "UPDATE users SET password = %s WHERE id = %s",
        [hashed_password, user_id],
    )
