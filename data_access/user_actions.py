"""Bulk user, password, status, and export SQL. Callers pass a cursor."""


def fetch_bulk_targets(cursor, ids):
    """Return selected users except Super Admin accounts."""
    format_str = ','.join(['%s'] * len(ids))
    cursor.execute(
        f"SELECT id, role FROM users WHERE id IN ({format_str}) AND role != 'Super Admin'",
        ids,
    )
    return cursor.fetchall() or []


def update_bulk_user_status(cursor, new_status, target_ids):
    """Set status for the selected accounts."""
    target_format = ','.join(['%s'] * len(target_ids))
    cursor.execute(
        f"UPDATE users SET status = %s WHERE id IN ({target_format})",
        [new_status, *target_ids],
    )


def update_bulk_faculty_active(cursor, is_active_flag, teacher_ids):
    """Set the faculty active flag for the selected teachers."""
    teacher_format = ','.join(['%s'] * len(teacher_ids))
    cursor.execute(
        f"UPDATE faculty SET is_active = %s WHERE user_id IN ({teacher_format})",
        [is_active_flag, *teacher_ids],
    )


def update_bulk_student_active(cursor, is_active_flag, student_ids):
    """Set the student active flag for the selected students."""
    student_format = ','.join(['%s'] * len(student_ids))
    cursor.execute(
        f"UPDATE students SET is_active = %s WHERE user_id IN ({student_format})",
        [is_active_flag, *student_ids],
    )


def update_bulk_passwords(cursor, hashed_password, ids):
    """Replace passwords for the selected accounts except Super Admin."""
    format_str = ','.join(['%s'] * len(ids))
    cursor.execute(
        f"UPDATE users SET password = %s WHERE id IN ({format_str}) AND role != 'Super Admin'",
        [hashed_password, *ids],
    )


def fetch_user_role(cursor, user_id):
    """Return the role row used by password reset."""
    cursor.execute("SELECT role FROM users WHERE id = %s", [user_id])
    return cursor.fetchone()


def update_user_password(cursor, hashed_password, user_id):
    """Store one new password hash."""
    cursor.execute("UPDATE users SET password = %s WHERE id = %s", [hashed_password, user_id])


def fetch_user_status(cursor, user_id):
    """Return the status and role row used by the status toggle."""
    cursor.execute("SELECT status, role FROM users WHERE id = %s", [user_id])
    return cursor.fetchone()


def update_user_status(cursor, new_status, user_id):
    """Store one account status."""
    cursor.execute("UPDATE users SET status = %s WHERE id = %s", [new_status, user_id])


def update_faculty_active_flag(cursor, is_active_flag, user_id):
    """Store one faculty active flag."""
    cursor.execute(
        "UPDATE faculty SET is_active = %s WHERE user_id = %s",
        [is_active_flag, user_id],
    )


def update_student_active_flag(cursor, is_active_flag, user_id):
    """Store one student active flag."""
    cursor.execute(
        "UPDATE students SET is_active = %s WHERE user_id = %s",
        [is_active_flag, user_id],
    )


def fetch_users_for_export(cursor, role_filter, status_filter, search):
    """Return the user export rows using the list-page filters."""
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
        params.append(f"%{search}%")
    query = """
        SELECT u.id, u.username, u.role, u.status, u.last_login
        FROM users u
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY u.username"
    cursor.execute(query, params)
    return cursor.fetchall()


def fetch_activity_for_export(cursor):
    """Return the latest activity rows for the CSV export."""
    cursor.execute(
        """
            SELECT l.created_at, u.username, l.activity_type, l.description, l.ip_address, l.user_agent
            FROM user_activity_log l
            JOIN users u ON l.user_id = u.id
            ORDER BY l.created_at DESC
            LIMIT 5000
            """
    )
    return cursor.fetchall()
