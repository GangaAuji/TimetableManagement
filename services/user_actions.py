"""Bulk user changes, password reset, status toggle, and exports."""

import secrets
import string

from flask import current_app
from werkzeug.security import generate_password_hash

from data_access.user_actions import (
    fetch_activity_for_export,
    fetch_bulk_targets,
    fetch_user_role,
    fetch_user_status,
    fetch_users_for_export,
    update_bulk_faculty_active,
    update_bulk_passwords,
    update_bulk_student_active,
    update_bulk_user_status,
    update_faculty_active_flag,
    update_student_active_flag,
    update_user_password,
    update_user_status,
)
from extensions import get_db_connection
from security import log_activity
from services.users import soft_delete_user_relations


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _temp_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def apply_bulk_user_action(action, ids, new_password, session):
    """Apply one bulk action. Return the JSON payload and status."""
    connection, cursor = _cursor()
    try:
        if action in ('activate', 'deactivate'):
            new_status = 'active' if action == 'activate' else 'inactive'
            is_active_flag = 1 if new_status == 'active' else 0
            rows = fetch_bulk_targets(cursor, ids)
            target_ids = [row['id'] for row in rows]
            if target_ids:
                update_bulk_user_status(cursor, new_status, target_ids)
                teacher_ids = [row['id'] for row in rows if row['role'] == 'Teacher']
                student_ids = [row['id'] for row in rows if row['role'] == 'Student']
                if teacher_ids:
                    update_bulk_faculty_active(cursor, is_active_flag, teacher_ids)
                if student_ids:
                    update_bulk_student_active(cursor, is_active_flag, student_ids)
            connection.commit()
            log_activity(session['user_id'], f'bulk_{action}_users', f"Affected IDs: {','.join(ids)}")
            return {'message': f"Users {action}d successfully."}, 200
        if action == 'delete':
            rows = fetch_bulk_targets(cursor, ids)
            for row in rows:
                soft_delete_user_relations(cursor, row['id'], row['role'])
            connection.commit()
            log_activity(session['user_id'], 'bulk_delete_users', f"Deactivated IDs: {','.join(ids)}")
            return {'message': 'Users deactivated successfully.'}, 200
        if action == 'reset_password':
            if new_password and len(new_password) < 8:
                return {'error': 'New password must be at least 8 characters.'}, 400
            if not new_password:
                new_password = _temp_password()
            update_bulk_passwords(cursor, generate_password_hash(new_password), ids)
            connection.commit()
            log_activity(session['user_id'], 'bulk_reset_password', f"Affected IDs: {','.join(ids)}")
            return {'message': 'Passwords reset successfully.', 'temp_password': new_password}, 200
        return {'error': 'Unknown action.'}, 400
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Bulk users action error: {exc}")
        return {'error': 'Operation failed.'}, 500
    finally:
        cursor.close()
        connection.close()


def reset_user_password(user_id, new_password, session):
    """Reset one password. Return the JSON payload and status."""
    if new_password and len(new_password) < 8:
        return {'error': 'Password must be at least 8 characters.'}, 400
    if not new_password:
        new_password = _temp_password()
    hashed = generate_password_hash(new_password)
    connection, cursor = _cursor()
    try:
        row = fetch_user_role(cursor, user_id)
        if not row:
            return {'error': 'User not found.'}, 404
        if row['role'] == 'Super Admin':
            return {'error': 'Cannot reset password for Super Admin.'}, 403
        update_user_password(cursor, hashed, user_id)
        connection.commit()
        log_activity(session['user_id'], 'reset_password', f'Reset password for user ID {user_id}')
        return {'message': 'Password reset successfully.', 'temp_password': new_password}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Reset password error: {exc}")
        return {'error': 'Operation failed.'}, 500
    finally:
        cursor.close()
        connection.close()


def toggle_user_status(user_id, session):
    """Switch one account between active and inactive. Return the JSON payload and status."""
    connection, cursor = _cursor()
    try:
        row = fetch_user_status(cursor, user_id)
        if not row:
            return {'error': 'User not found.'}, 404
        if row['role'] == 'Super Admin':
            return {'error': 'Cannot change status for Super Admin.'}, 403
        new_status = 'inactive' if row['status'] == 'active' else 'active'
        is_active_flag = 1 if new_status == 'active' else 0
        update_user_status(cursor, new_status, user_id)
        if row['role'] == 'Teacher':
            update_faculty_active_flag(cursor, is_active_flag, user_id)
        elif row['role'] == 'Student':
            update_student_active_flag(cursor, is_active_flag, user_id)
        connection.commit()
        log_activity(session['user_id'], 'toggle_status', f'User ID {user_id} -> {new_status}')
        return {'message': 'Status updated.', 'status': new_status}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Toggle status error: {exc}")
        return {'error': 'Operation failed.'}, 500
    finally:
        cursor.close()
        connection.close()


def export_user_rows(role_filter, status_filter, search):
    """Return user export rows. The connection stays open."""
    connection, cursor = _cursor()
    rows = fetch_users_for_export(cursor, role_filter, status_filter, search)
    cursor.close()
    return rows


def export_activity_rows():
    """Return activity export rows. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        return fetch_activity_for_export(cursor)
    finally:
        cursor.close()
        connection.close()
