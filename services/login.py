"""Sign-in for students, teachers, and admin roles. The route chooses the HTTP response.

An unknown username and a wrong password get the same message, and both run
one password hash. Failures are recorded on their own connection; a
successful sign-in writes its session, counter reset, and audit rows in one
transaction.
"""

import math
import secrets
import uuid
from datetime import datetime, timedelta

from flask import current_app, flash
from data_access.login import (
    deactivate_user_session,
    fetch_admin_login_user,
    fetch_faculty_links,
    fetch_login_user,
    fetch_student_links,
    fetch_user_profile,
    insert_user_session,
    update_last_login,
    update_password_hash,
)
from extensions import get_db
from security import log_activity, log_login_attempt
from security.lockout import clear_after_sign_in, record_failed_sign_in
from security.passwords import hash_password, password_matches, upgraded_hash
from security.rate_limit import count_unknown_username

_FAILED = 'Sign in failed.'
_LOCKED = 'Too many failed sign-in attempts. Try again in {minutes} minutes.'
_UNKNOWN_HASH = []


def _record_failure(user_id):
    try:
        record_failed_sign_in(user_id)
    except Exception:
        current_app.logger.exception('Could not record a failed sign-in')


def _count_unknown(ip_address):
    try:
        count_unknown_username(ip_address)
    except Exception:
        current_app.logger.exception('Could not count an unknown username')


def _spend_one_hash(password):
    """Check against a throwaway hash so an unknown username costs what a wrong password does."""
    if not _UNKNOWN_HASH:
        _UNKNOWN_HASH.append(hash_password(secrets.token_urlsafe(24)))
    try:
        password_matches(_UNKNOWN_HASH[0], password)
    except Exception:
        pass


def _password_ok(user, password):
    try:
        return password_matches(user['password'], password)
    except Exception:
        current_app.logger.exception('Sign-in could not check the password')
        return None


def _linked_record(cursor, user):
    """Return the one linked profile, or a denial message when the link is not exact."""
    if user['role'] == 'Student':
        rows = fetch_student_links(cursor, user['id'])
        if len(rows) != 1:
            return None, 'This account is not linked to a student record.'
        return rows[0], None
    if user['role'] == 'Teacher':
        rows = fetch_faculty_links(cursor, user['id'])
        if len(rows) != 1:
            return None, 'This account is not linked to a faculty record.'
        return rows[0], None
    return None, None


def _apply_profile(session, user_id, cursor):
    user_details = fetch_user_profile(cursor, user_id)
    if user_details:
        session['department_id'] = user_details['department_id']
        session['is_hod'] = user_details['is_hod']
        session['profile_photo'] = user_details['profile_photo'] if user_details['profile_photo'] else 'default-avatar.svg'
    else:
        session['department_id'] = None
        session['is_hod'] = False
        session['profile_photo'] = 'default-avatar.svg'


def _open_session(cursor, user, username, password, ip_address, user_agent, session):
    replacement = upgraded_hash(user['password'], password)
    if replacement:
        update_password_hash(cursor, replacement, user['id'])
    session['user_id'] = user['id']
    session['username'] = username
    session['role'] = user['role']
    session_id = str(uuid.uuid4())
    session['session_id'] = session_id
    expires_at = datetime.now() + timedelta(days=7)
    insert_user_session(cursor, session_id, user['id'], ip_address, user_agent, expires_at)
    update_last_login(cursor, user['id'])
    return session_id


def _checked(user, username, password, ip_address, invalid_reason):
    """Return the user when the password is right and the account is not locked. Otherwise flash and log."""
    if user is None:
        _spend_one_hash(password)
        _count_unknown(ip_address)
        log_login_attempt(username, 'failed', 'Unknown account')
        flash(_FAILED, 'danger')
        return None
    password_ok = _password_ok(user, password)
    if password_ok is None:
        flash(_FAILED, 'danger')
        return None
    if user.get('locked_now'):
        log_login_attempt(username, 'failed', 'Account locked')
        if password_ok:
            minutes = max(1, math.ceil(int(user.get('lock_seconds') or 0) / 60))
            flash(_LOCKED.format(minutes=minutes), 'danger')
        else:
            flash(_FAILED, 'danger')
        return None
    if not password_ok:
        _record_failure(user['id'])
        log_login_attempt(username, 'failed', invalid_reason)
        flash(_FAILED, 'danger')
        return None
    return user


def _commit_sign_in(db, cursor, user, username, password, ip_address, user_agent, session, activity, description):
    _open_session(cursor, user, username, password, ip_address, user_agent, session)
    clear_after_sign_in(cursor, user)
    log_login_attempt(username, 'success', cursor=cursor)
    log_activity(user['id'], activity, description, cursor=cursor)
    db.commit()


def sign_in(username, password, ip_address, user_agent, session):
    """Sign in a student or teacher. Return 'redirect' or 'render'."""
    db, cursor = get_db()
    user = _checked(fetch_login_user(cursor, username), username, password, ip_address, 'Invalid password')
    if user is None:
        return 'render'

    if user['status'] == 'locked':
        log_login_attempt(username, 'failed', 'Account locked')
        flash('Your account has been locked due to security reasons. Please contact the administrator.', 'danger')
        return 'render'
    if user['status'] == 'inactive':
        log_login_attempt(username, 'failed', 'Account inactive')
        flash('Your account has been deactivated. Please contact the administrator for assistance.', 'warning')
        return 'render'

    linked, denial = _linked_record(cursor, user)
    if denial:
        log_login_attempt(username, 'failed', denial)
        flash(denial, 'danger')
        return 'render'

    _commit_sign_in(db, cursor, user, username, password, ip_address, user_agent, session,
                    'login', f'User {username} logged in as {user["role"]}')
    _apply_profile(session, user['id'], cursor)

    if user['role'] == 'Student' and linked:
        session['student_id'] = linked['id']
        session['name'] = linked['name']
        session['email'] = linked['email']
        session['course_id'] = linked['course_id']
        session['class_id'] = linked['class_id']
        session['division_id'] = linked['division_id']
    elif user['role'] == 'Teacher' and linked:
        session['faculty_id'] = linked['id']
        session['name'] = linked['name']
        session['email'] = linked['email']
        session['department_id'] = linked['department_id']
    return 'redirect'


def sign_in_admin(username, password, ip_address, user_agent, session):
    """Sign in an admin, super admin, or HOD. Return 'redirect' or 'render'."""
    db, cursor = get_db()
    user = _checked(fetch_admin_login_user(cursor, username), username, password, ip_address, 'Invalid admin password')
    if user is None:
        return 'render'

    if user.get('status') == 'locked':
        log_login_attempt(username, 'failed', 'Account locked')
        flash('Your admin account has been locked due to security reasons. Please contact the system administrator.', 'danger')
        return 'render'
    if user.get('status') == 'inactive':
        log_login_attempt(username, 'failed', 'Account inactive')
        flash('Your admin account has been deactivated. Please contact the system administrator.', 'warning')
        return 'render'

    _commit_sign_in(db, cursor, user, username, password, ip_address, user_agent, session,
                    'admin_login', f'Admin {username} logged in with role {user["role"]}')
    _apply_profile(session, user['id'], cursor)
    session['name'] = username
    return 'redirect'


def sign_out(session):
    """Record logout, deactivate that session, then clear it."""
    if 'user_id' in session:
        db, cursor = get_db()
        if 'session_id' in session:
            deactivate_user_session(cursor, session['session_id'])
        log_activity(session['user_id'], 'logout', f"User {session.get('username', 'unknown')} logged out", cursor=cursor)
        db.commit()
        cursor.close()
    session.clear()
