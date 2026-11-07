"""Profile reads and saves. This module does not read the request."""

from datetime import datetime

from extensions import get_db_connection
from security import log_activity
from utils.uploads import save_uploaded_file
from werkzeug.security import check_password_hash, generate_password_hash

from data_access.profile import (
    fetch_department_name,
    fetch_faculty_email,
    fetch_password_hash,
    fetch_profile_form,
    fetch_profile_user,
    fetch_student_email,
    update_faculty_email,
    update_password,
    update_profile_with_photo,
    update_profile_without_photo,
    update_student_email,
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _connect():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def load_profile(session):
    """Return the profile dict, or None when the account row is missing."""
    connection, cursor = _connect()
    try:
        user_role = session.get('role')
        user_id = session['user_id']
        user_data = fetch_profile_user(cursor, user_id)
        if not user_data:
            return None
        user = {
            'id': user_data['id'],
            'username': user_data['username'],
            'role': user_data['role'],
            'email': user_data['email'],
            'profile_photo': user_data['profile_photo'] if user_data['profile_photo'] else 'default-avatar.svg',
            'phone': user_data['phone'],
            'address': user_data['address'],
            'bio': user_data['bio'],
            'date_of_birth': user_data['date_of_birth'],
            'status': user_data['status'] or 'active',
            'last_login': user_data['last_login'],
            'created_at': user_data['created_at'],
            'department_id': user_data['department_id'],
            'is_hod': user_data['is_hod'] or False,
            'department_name': None,
        }
        if user['department_id']:
            dept_result = fetch_department_name(cursor, user['department_id'])
            if dept_result:
                user['department_name'] = dept_result['name']
        if user_role == 'Teacher':
            faculty_data = fetch_faculty_email(cursor, user_id)
            if faculty_data and faculty_data['email'] and not user['email']:
                user['email'] = faculty_data['email']
        elif user_role == 'Student':
            student_data = fetch_student_email(cursor, user_id)
            if student_data and student_data['email'] and not user['email']:
                user['email'] = student_data['email']
        return user
    finally:
        cursor.close()
        connection.close()


def load_profile_form(session):
    """Return the edit-form dict, or None when the account row is missing."""
    connection, cursor = _connect()
    try:
        user_data = fetch_profile_form(cursor, session['user_id'])
        if not user_data:
            return None
        return {
            'id': user_data['id'],
            'username': user_data['username'],
            'email': user_data['email'],
            'role': user_data['role'],
            'phone': user_data['phone'],
            'address': user_data['address'],
            'bio': user_data['bio'],
            'date_of_birth': user_data['date_of_birth'],
            'profile_photo': user_data['profile_photo'] or 'default-avatar.png',
            'department_name': user_data['dept_name'],
        }
    finally:
        cursor.close()
        connection.close()


def save_profile(session, email, phone, address, bio, date_of_birth, photo_file):
    """Save profile fields. Return invalid_file, ok, or an error string."""
    connection, cursor = _connect()
    try:
        profile_photo = None
        if photo_file and photo_file.filename:
            if _allowed_file(photo_file.filename):
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                profile_photo = save_uploaded_file(
                    photo_file,
                    'uploads/profiles',
                    allowed_extensions=ALLOWED_EXTENSIONS,
                    name_prefix=str(session['user_id']),
                    timestamp=timestamp,
                )
            else:
                return 'invalid_file'
        user_id = session['user_id']
        user_role = session.get('role')
        if profile_photo:
            update_profile_with_photo(cursor, [
                email, phone, address, bio, date_of_birth or None, profile_photo, user_id,
            ])
        else:
            update_profile_without_photo(cursor, [
                email, phone, address, bio, date_of_birth or None, user_id,
            ])
        if user_role == 'Teacher':
            update_faculty_email(cursor, email, user_id)
        elif user_role == 'Student':
            update_student_email(cursor, email, user_id)
        connection.commit()
        if profile_photo:
            session['profile_photo'] = profile_photo
        log_activity(user_id, 'update_profile', 'Updated user profile')
        return 'ok'
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def change_password(session, current_password, new_password):
    """Replace the password. Return wrong, ok, or an error string."""
    connection, cursor = _connect()
    try:
        user_id = session['user_id']
        result = fetch_password_hash(cursor, user_id)
        if not result or not check_password_hash(result['password'], current_password):
            return 'wrong'
        update_password(cursor, generate_password_hash(new_password), user_id)
        connection.commit()
        log_activity(user_id, 'change_password', 'Changed password')
        return 'ok'
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()
