"""Invitation registration SQL. Callers pass a cursor."""


def fetch_invitation(cursor, token):
    """Return the invitation row for this token."""
    cursor.execute("""
        SELECT id, email, role, name, course_id, class_id, division_id, department_id, expires_at, status
        FROM registration_invitations 
        WHERE token = %s
    """, (token,))
    return cursor.fetchone()


def mark_invitation_expired(cursor, invitation_id):
    """Mark one invitation expired."""
    cursor.execute("UPDATE registration_invitations SET status = 'expired' WHERE id = %s", (invitation_id,))


def fetch_user_id_by_username(cursor, username):
    """Return a user id row when the username is taken."""
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    return cursor.fetchone()


def fetch_student_id_by_email(cursor, email):
    """Return a student id row for this email."""
    cursor.execute("SELECT id FROM students WHERE email = %s", (email,))
    return cursor.fetchone()


def fetch_faculty_id_by_email(cursor, email):
    """Return a faculty id row for this email."""
    cursor.execute("SELECT id FROM faculty WHERE email = %s", (email,))
    return cursor.fetchone()


def insert_user(cursor, username, hashed_password, role):
    """Insert the login account and return its id."""
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
        (username, hashed_password, role),
    )
    return cursor.lastrowid


def update_profile_photo(cursor, face_image_path, user_id):
    """Store the captured profile photo."""
    cursor.execute(
        "UPDATE users SET profile_photo = %s, updated_at = NOW() WHERE id = %s",
        (face_image_path, user_id),
    )


def insert_student(cursor, values):
    """Insert the student row. The id is the new user id."""
    cursor.execute("""
                    INSERT INTO students (id, user_id, admission_id, name, email, course_id, class_id, division_id) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, values)


def insert_faculty(cursor, values):
    """Insert the faculty row. The id is the new user id."""
    cursor.execute("""
                    INSERT INTO faculty (id, user_id, name, email, department_id, employee_id) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, values)


def table_exists(cursor, table_name):
    """Return whether the current database has this table."""
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def save_face_template(cursor, values):
    """Insert or update the mobile face template row."""
    cursor.execute(
        """
                    INSERT INTO mobile_face_templates (
                        user_id, embedding_json, image_path, quality_score, embedding_version, is_active, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 1, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        embedding_json = VALUES(embedding_json),
                        image_path = VALUES(image_path),
                        quality_score = VALUES(quality_score),
                        embedding_version = VALUES(embedding_version),
                        is_active = 1,
                        updated_at = NOW()
                    """,
        values,
    )


def mark_invitation_used(cursor, invitation_id):
    """Mark one invitation used."""
    cursor.execute("""
                UPDATE registration_invitations 
                SET status = 'used', used_at = NOW() 
                WHERE id = %s
            """, (invitation_id,))
