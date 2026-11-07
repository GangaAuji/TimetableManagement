"""User list, lookup, creation, and edits. This module does not read the request."""

from datetime import datetime

from flask import current_app, flash
from werkzeug.security import generate_password_hash

from data_access.users import (
    deactivate_faculty,
    deactivate_students,
    fetch_course_department_id,
    fetch_default_course_id,
    fetch_default_department_id,
    fetch_faculty_contact,
    fetch_faculty_profile,
    fetch_first_course_for_department,
    fetch_other_user_by_email,
    fetch_other_user_by_username,
    fetch_role_names,
    fetch_student_contact,
    fetch_student_profile,
    fetch_user_for_edit,
    fetch_user_id_by_username,
    fetch_user_identity,
    fetch_user_record,
    fetch_users,
    insert_faculty_profile,
    insert_student_profile,
    insert_user,
    mark_user_inactive,
    set_faculty_active,
    set_student_active,
    update_faculty_profile,
    update_student_profile,
    update_user_with_password,
    update_user_without_password,
)
from extensions import get_db_connection
from security import log_activity


def list_users(role_filter, status_filter, search):
    """Return the user rows and the role names for the user list."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    roles = fetch_role_names(cursor)
    users = fetch_users(cursor, role_filter, status_filter, search)
    cursor.close()
    return users, roles


def create_user(username, password, role, status, _email, session):
    """Create one user. A taken username is reported without rolling back."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if fetch_user_id_by_username(cursor, username):
            flash('Username already exists.', 'danger')
            return
        hashed = generate_password_hash(password) if password else ''
        user_id = insert_user(cursor, username, hashed, role, status)
        log_activity(
            session['user_id'],
            'create_user',
            f'Created new user: {username} with role {role}',
        )
        connection.commit()
        flash('User created successfully.', 'success')
        return user_id
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error creating user: {str(exc)}")
        flash('Error creating user. Please try again.', 'danger')
    finally:
        cursor.close()
        connection.close()


def find_user(user_id):
    """Return the lookup payload and status. Roles are loaded only for a found user."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        user = fetch_user_record(cursor, user_id)
        if not user:
            return {'error': 'User not found'}, 404
        available_roles = [role['name'] for role in fetch_role_names(cursor)]
        return {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'status': user['status'],
            'display_name': user['username'],
            'email': user.get('email'),
            'is_hod': user['is_hod'],
            'department_id': user['department_id'],
            'available_roles': available_roles,
        }, 200
    finally:
        cursor.close()
        connection.close()


def normalize_role(role):
    """Map a role label to the value stored on the user."""
    role_aliases = {
        'teachers': 'Teacher',
        'teacher': 'Teacher',
        'faculty': 'Teacher',
        'faculties': 'Teacher',
        'students': 'Student',
        'student': 'Student',
        'admins': 'Admin',
        'admin': 'Admin',
        'super admins': 'Super Admin',
        'super admin': 'Super Admin',
    }
    return role_aliases.get(role.lower(), role)


def _fallback_email(username, user_id):
    return f"{username}.{user_id}@local.invalid"


def _generate_employee_id(user_id):
    return f"EMP{datetime.now().year}{user_id:06d}"


def _generate_admission_id(user_id):
    return f"ADM{datetime.now().year}{user_id:06d}"


def _default_department_id(cursor):
    row = fetch_default_department_id(cursor)
    return row['id'] if row else None


def _default_course_id(cursor):
    row = fetch_default_course_id(cursor)
    return row['id'] if row else None


def _ensure_faculty_profile(cursor, user_id, username, email, department_id=None):
    existing = fetch_faculty_profile(cursor, user_id)
    profile_name = username
    profile_phone = None
    student_course_id = None
    student_row = fetch_student_contact(cursor, user_id)
    if student_row:
        profile_name = student_row.get('name') or profile_name
        profile_phone = student_row.get('phone')
        student_course_id = student_row.get('course_id')

    if existing:
        target_department_id = department_id or existing.get('department_id')
        if not target_department_id and student_course_id:
            course_row = fetch_course_department_id(cursor, student_course_id)
            target_department_id = course_row.get('department_id') if course_row else None
        target_department_id = target_department_id or _default_department_id(cursor)
        if not target_department_id:
            raise ValueError("Cannot assign Teacher role: no department available.")
        update_faculty_profile(cursor, [
            user_id,
            existing.get('name') or profile_name,
            email or existing.get('email') or _fallback_email(username, user_id),
            existing.get('phone') or profile_phone,
            target_department_id,
            existing['id'],
        ])
        return

    target_department_id = department_id
    if not target_department_id and student_course_id:
        course_row = fetch_course_department_id(cursor, student_course_id)
        target_department_id = course_row.get('department_id') if course_row else None
    target_department_id = target_department_id or _default_department_id(cursor)
    if not target_department_id:
        raise ValueError("Cannot assign Teacher role: no department available.")

    insert_faculty_profile(cursor, [
        user_id,
        user_id,
        profile_name,
        email or _fallback_email(username, user_id),
        target_department_id,
        _generate_employee_id(user_id),
        profile_phone,
    ])


def _ensure_student_profile(cursor, user_id, username, email):
    existing = fetch_student_profile(cursor, user_id)
    if existing:
        update_student_profile(cursor, [
            user_id,
            email or existing.get('email') or _fallback_email(username, user_id),
            existing['id'],
        ])
        return

    faculty_row = fetch_faculty_contact(cursor, user_id)
    profile_name = faculty_row.get('name') if faculty_row else username
    profile_phone = faculty_row.get('phone') if faculty_row else None
    department_id = faculty_row.get('department_id') if faculty_row else None

    course_id = None
    if department_id:
        course_row = fetch_first_course_for_department(cursor, department_id)
        course_id = course_row.get('id') if course_row else None
    course_id = course_id or _default_course_id(cursor)
    if not course_id:
        raise ValueError("Cannot assign Student role: no course available.")

    insert_student_profile(cursor, [
        user_id,
        user_id,
        profile_name or username,
        email or _fallback_email(username, user_id),
        profile_phone,
        course_id,
        _generate_admission_id(user_id),
    ])


def _sync_role_profiles(cursor, user_id, target_role, username, email, department_id):
    if target_role == 'Teacher':
        _ensure_faculty_profile(cursor, user_id, username, email, department_id)
        deactivate_students(cursor, user_id)
    elif target_role == 'Student':
        _ensure_student_profile(cursor, user_id, username, email)
        deactivate_faculty(cursor, user_id)
    else:
        deactivate_students(cursor, user_id)
        deactivate_faculty(cursor, user_id)


def change_user(user_id, username, password, role, status, email, department_id, is_hod, session):
    """Update one user. Return missing, username, email, ok, or error."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        current_user = fetch_user_for_edit(cursor, user_id)
        if not current_user:
            return 'missing'
        if fetch_other_user_by_username(cursor, username, user_id):
            return 'username'
        if email:
            if fetch_other_user_by_email(cursor, email, user_id):
                return 'email'
        dept_id = int(department_id) if department_id and department_id != '' else None
        stored_email = email or None
        if password:
            hashed = generate_password_hash(password)
            update_user_with_password(cursor, [
                username, stored_email, hashed, role, status, dept_id, is_hod, user_id,
            ])
        else:
            update_user_without_password(cursor, [
                username, stored_email, role, status, dept_id, is_hod, user_id,
            ])
        _sync_role_profiles(cursor, user_id, role, username, stored_email, dept_id)
        profile_active = 1 if status == 'active' else 0
        if role == 'Teacher':
            set_faculty_active(cursor, profile_active, user_id)
        elif role == 'Student':
            set_student_active(cursor, profile_active, user_id)
        log_activity(
            session['user_id'],
            'edit_user',
            f'Updated user {username} (ID: {user_id})',
        )
        connection.commit()
        return 'ok'
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error updating user: {str(exc)}")
        return 'error'
    finally:
        cursor.close()
        connection.close()


def soft_delete_user_relations(cursor, user_id, role):
    """Mark the account inactive and deactivate the matching profile."""
    mark_user_inactive(cursor, user_id)
    if role == 'Teacher':
        deactivate_faculty(cursor, user_id)
    elif role == 'Student':
        deactivate_students(cursor, user_id)


def deactivate_user(user_id, session):
    """Deactivate one user. Return missing, protected, ok, or error."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        user = fetch_user_identity(cursor, user_id)
        if not user:
            return 'missing'
        username = user['username']
        role = user['role']
        if role == 'Super Admin':
            return 'protected'
        soft_delete_user_relations(cursor, user_id, role)
        log_activity(
            session['user_id'],
            'delete_user',
            f'Soft-deleted user {username} (ID: {user_id})',
        )
        connection.commit()
        return 'ok'
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error deleting user: {str(exc)}")
        return 'error'
    finally:
        cursor.close()
        connection.close()
