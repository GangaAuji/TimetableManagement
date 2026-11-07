"""Sign-in for students, teachers, and admin roles. The route chooses the HTTP response."""

import uuid
from datetime import datetime, timedelta

from flask import current_app, flash
from werkzeug.security import check_password_hash

from data_access.login import (
    deactivate_user_session,
    fetch_admin_login_user,
    fetch_faculty_by_user,
    fetch_faculty_fallback,
    fetch_login_user,
    fetch_student_by_user,
    fetch_student_fallback,
    fetch_user_profile,
    insert_user_session,
    update_last_login,
)
from extensions import get_db
from security import log_activity, log_login_attempt


def sign_in(username, password, ip_address, user_agent, session):
    """Sign in a student or teacher. Return 'redirect' or 'render'."""
    db, cursor = get_db()
    user = fetch_login_user(cursor, username)

    if user is None:
        flash("User not found.", "danger")
        return 'render'

    if user['status'] == 'inactive':
        flash("Your account has been deactivated. Please contact the administrator for assistance.", "warning")
        return 'render'
    elif user['status'] == 'locked':
        flash("Your account has been locked due to security reasons. Please contact the administrator.", "danger")
        return 'render'

    password_ok = check_password_hash(user['password'], password)

    if password_ok:
        session['user_id'] = user['id']
        session['username'] = username
        session['role'] = user['role']

        session_id = str(uuid.uuid4())
        session['session_id'] = session_id

        expires_at = datetime.now() + timedelta(days=7)
        insert_user_session(cursor, session_id, user['id'], ip_address, user_agent, expires_at)

        log_login_attempt(username, 'success')
        log_activity(user['id'], 'login', f'User {username} logged in as {user["role"]}')

        update_last_login(cursor, user['id'])
        db.commit()

        user_details = fetch_user_profile(cursor, user['id'])
        if user_details:
            session['department_id'] = user_details['department_id']
            session['is_hod'] = user_details['is_hod']
            session['profile_photo'] = user_details['profile_photo'] if user_details['profile_photo'] else 'default-avatar.svg'
        else:
            session['department_id'] = None
            session['is_hod'] = False
            session['profile_photo'] = 'default-avatar.svg'

        if user['role'] == 'Student':
            student = None
            used_fallback = False
            try:
                student = fetch_student_by_user(cursor, user['id'])
            except Exception as exc:
                current_app.logger.warning("Student mapping by user_id failed: %s", exc)
            if not student:
                used_fallback = True
                student = fetch_student_fallback(cursor)
            if student:
                session['student_id'] = student['id']
                session['name'] = student['name']
                session['email'] = student['email']
                session['course_id'] = student['course_id']
                session['class_id'] = student['class_id']
                session['division_id'] = student['division_id']
                if used_fallback:
                    flash("Your account isn't linked to a student profile yet. Showing default student data. Ask admin to link your user.", "warning")
            else:
                session['name'] = username
        elif user['role'] == 'Teacher':
            faculty = None
            used_fallback = False
            try:
                faculty = fetch_faculty_by_user(cursor, user['id'])
            except Exception as exc:
                current_app.logger.warning("Teacher mapping by user_id failed: %s", exc)
            if not faculty:
                used_fallback = True
                faculty = fetch_faculty_fallback(cursor)
            if faculty:
                session['faculty_id'] = faculty['id']
                session['name'] = faculty['name']
                session['email'] = faculty['email']
                session['department_id'] = faculty['department_id']
                if used_fallback:
                    flash("Your account isn't linked to a teacher profile yet. Showing default teacher data. Ask admin to link your user.", "warning")
            else:
                session['name'] = username

        return 'redirect'

    log_login_attempt(username, 'failed', 'Invalid password')
    flash("Invalid credentials for Student/Teacher.", "danger")
    return 'render'


def sign_in_admin(username, password, ip_address, user_agent, session):
    """Sign in an admin, super admin, or HOD. Return 'redirect' or 'render'."""
    db, cursor = get_db()
    user = fetch_admin_login_user(cursor, username)

    if user is None:
        flash("Admin user not found or not authorized.", "danger")
        return 'render'

    if user.get('status') == 'inactive':
        flash("Your admin account has been deactivated. Please contact the system administrator.", "warning")
        return 'render'
    elif user.get('status') == 'locked':
        flash("Your admin account has been locked due to security reasons. Please contact the system administrator.", "danger")
        return 'render'

    try:
        password_ok = check_password_hash(user['password'], password)
    except Exception:
        current_app.logger.exception('Admin sign-in could not check the password')
        flash("An error occurred during login.", "danger")
        return 'render'

    if password_ok:
        session['user_id'] = user['id']
        session['username'] = username
        session['role'] = user['role']

        session_id = str(uuid.uuid4())
        session['session_id'] = session_id

        expires_at = datetime.now() + timedelta(days=7)
        insert_user_session(cursor, session_id, user['id'], ip_address, user_agent, expires_at)

        log_login_attempt(username, 'success')
        log_activity(user['id'], 'admin_login', f'Admin {username} logged in with role {user["role"]}')

        update_last_login(cursor, user['id'])
        db.commit()

        user_details = fetch_user_profile(cursor, user['id'])
        if user_details:
            session['department_id'] = user_details['department_id']
            session['is_hod'] = user_details['is_hod']
            session['profile_photo'] = user_details['profile_photo'] if user_details['profile_photo'] else 'default-avatar.svg'
        else:
            session['department_id'] = None
            session['is_hod'] = False
            session['profile_photo'] = 'default-avatar.svg'

        session['name'] = username
        return 'redirect'

    log_login_attempt(username, 'failed', 'Invalid admin password')
    flash("Invalid Admin credentials.", "danger")
    return 'render'


def sign_out(session):
    """Record logout, deactivate that session, then clear it."""
    if 'user_id' in session:
        log_activity(session['user_id'], 'logout', f"User {session.get('username', 'unknown')} logged out")
        if 'session_id' in session:
            db, cursor = get_db()
            deactivate_user_session(cursor, session['session_id'])
            db.commit()
            cursor.close()
    session.clear()
