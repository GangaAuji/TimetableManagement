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
from security.authority import account_problem, removes_last_super_admin
from security.lockout import unlock_account
from services.users import soft_delete_user_relations


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _temp_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _bulk_refused(cursor, ids, session):
    """True when any selected account is one the actor may not manage, or is the actor."""
    actor_id = session['user_id']
    for raw in ids:
        try:
            target = int(raw)
        except (TypeError, ValueError):
            return True
        if target == actor_id or account_problem(cursor, actor_id, target) == 'protected':
            return True
    return False


def apply_bulk_user_action(action, ids, new_password, session):
    """Apply one bulk action. Return the JSON payload and status.

    Super Admin accounts are never touched by a bulk action, and the whole
    request is refused when it names an account the actor may not manage.
    """
    connection, cursor = _cursor()
    try:
        if _bulk_refused(cursor, ids, session):
            return {'error': 'You cannot change one or more of the selected accounts.'}, 403
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
            log_activity(session['user_id'], f'bulk_{action}_users', f"Affected IDs: {','.join(ids)}", cursor=cursor)
            connection.commit()
            return {'message': f"Users {action}d successfully."}, 200
        if action == 'delete':
            rows = fetch_bulk_targets(cursor, ids)
            for row in rows:
                soft_delete_user_relations(cursor, row['id'], row['role'])
            log_activity(session['user_id'], 'bulk_delete_users', f"Deactivated IDs: {','.join(ids)}", cursor=cursor)
            connection.commit()
            return {'message': 'Users deactivated successfully.'}, 200
        if action == 'reset_password':
            if new_password and len(new_password) < 8:
                return {'error': 'New password must be at least 8 characters.'}, 400
            if not new_password:
                new_password = _temp_password()
            target_ids = [row['id'] for row in fetch_bulk_targets(cursor, ids)]
            if target_ids:
                update_bulk_passwords(cursor, generate_password_hash(new_password), target_ids)
            log_activity(session['user_id'], 'bulk_reset_password', f"Affected IDs: {','.join(ids)}", cursor=cursor)
            connection.commit()
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
        if account_problem(cursor, session['user_id'], user_id):
            return {'error': 'You cannot reset the password for that account.'}, 403
        update_user_password(cursor, hashed, user_id)
        log_activity(session['user_id'], 'reset_password', f'Reset password for user ID {user_id}',
                     entity_type='user', entity_id=user_id, cursor=cursor)
        connection.commit()
        return {'message': 'Password reset successfully.', 'temp_password': new_password}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Reset password error: {exc}")
        return {'error': 'Operation failed.'}, 500
    finally:
        cursor.close()
        connection.close()


def toggle_user_status(user_id, session):
    """Switch one account between active and inactive. Return the JSON payload and status.

    Reactivating a locked account also clears its sign-in lock and counter.
    """
    connection, cursor = _cursor()
    try:
        row = fetch_user_status(cursor, user_id)
        if not row:
            return {'error': 'User not found.'}, 404
        new_status = 'inactive' if row['status'] == 'active' else 'active'
        if (user_id == session['user_id']
                or account_problem(cursor, session['user_id'], user_id)
                or removes_last_super_admin(cursor, user_id, row['role'], new_status)):
            return {'error': 'You cannot change the status of that account.'}, 403
        is_active_flag = 1 if new_status == 'active' else 0
        if new_status == 'active':
            unlock_account(cursor, user_id, session['user_id'])
        update_user_status(cursor, new_status, user_id)
        if row['role'] == 'Teacher':
            update_faculty_active_flag(cursor, is_active_flag, user_id)
        elif row['role'] == 'Student':
            update_student_active_flag(cursor, is_active_flag, user_id)
        log_activity(session['user_id'], 'toggle_status', f'User ID {user_id} -> {new_status}',
                     entity_type='user', entity_id=user_id, old_values={'status': row['status']},
                     new_values={'status': new_status}, cursor=cursor)
        connection.commit()
        return {'message': 'Status updated.', 'status': new_status}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Toggle status error: {exc}")
        return {'error': 'Operation failed.'}, 500
    finally:
        cursor.close()
        connection.close()


def unlock_user(user_id, session):
    """Clear one account's sign-in lock and failed-attempt counter. Return the JSON payload and status."""
    connection, cursor = _cursor()
    try:
        problem = account_problem(cursor, session['user_id'], user_id)
        if problem == 'missing':
            return {'error': 'User not found.'}, 404
        if problem:
            return {'error': 'You cannot unlock that account.'}, 403
        unlock_account(cursor, user_id, session['user_id'])
        connection.commit()
        return {'message': 'Account unlocked.'}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Unlock error: {exc}")
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
