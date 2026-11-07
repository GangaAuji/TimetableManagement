"""User accounts for the React users screen."""

import re

from flask import current_app, request, session
from mysql.connector import IntegrityError
from werkzeug.security import generate_password_hash

from core.pagination import bounded_page_size, page_bounds
from extensions import get_db_connection
from api.web.access import InputError, allowed, body, close, permission_denied, reject_input, required_text
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from security import log_activity

_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_STATUSES = frozenset(('active', 'inactive', 'locked'))
_USER_SORTS = {
    'username': 'u.username',
    'role': 'u.role',
    'status': 'u.status',
    'last_login': 'u.last_login',
}
_MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'users_unavailable': 'The page could not be loaded.',
    'user_username_invalid': 'Enter a username up to 50 characters.',
    'user_password_invalid': 'Enter a password up to 128 characters.',
    'user_role_invalid': 'Choose a role.',
    'user_status_invalid': 'Choose a valid status.',
    'user_username_taken': 'That username is already in use.',
    'user_not_found': 'That user was not found.',
    'user_protected': 'That account cannot be changed this way.',
}


def register_user_routes(blueprint):
    blueprint.add_url_rule('/users', 'users_list', _list, methods=['GET'])
    blueprint.add_url_rule('/users', 'users_create', _create, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>/deactivate', 'users_deactivate', _deactivate, methods=['POST'])
    from api.web.user_access import register_user_access_routes
    register_user_access_routes(blueprint)


def _denied(permission_name):
    return permission_denied(permission_name, 'users_unavailable', _MESSAGES['users_unavailable'])


def _search():
    raw = request.args.get('search', '')
    if not isinstance(raw, str) or _CONTROL.search(raw) or len(raw) > 100:
        raise InputError('invalid_body')
    return raw.strip()


def _list():
    denied = _denied('users_view_user')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        search = _search()
        role = request.args.get('role', '')
        status = request.args.get('status', '')
        if role and (not isinstance(role, str) or len(role) > 50 or _CONTROL.search(role)):
            raise InputError('user_role_invalid')
        if status and (not isinstance(status, str) or len(status) > 20 or _CONTROL.search(status)):
            raise InputError('user_status_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        where = ['u.role NOT IN (%s, %s)']
        params = ['Teacher', 'Student']
        if role:
            where.append('u.role LIKE %s')
            params.append(f'%{role}%')
        if status:
            where.append('u.status LIKE %s')
            params.append(f'%{status}%')
        if search:
            where.append('(u.username LIKE %s OR u.role LIKE %s OR u.status LIKE %s OR CAST(u.last_login AS CHAR) LIKE %s)')
            like = f'%{search}%'
            params.extend([like, like, like, like])
        username = request.args.get('username', '')
        if isinstance(username, str) and username.strip() and len(username) <= 50 and not _CONTROL.search(username):
            where.append('u.username LIKE %s')
            params.append('%' + username.replace('%', '').replace('_', '').strip() + '%')
        last_login = request.args.get('last_login', '')
        if last_login not in ('', None):
            if not isinstance(last_login, str) or _CONTROL.search(last_login) or len(last_login) > 19:
                raise InputError('invalid_body')
            last_login = last_login.strip()
            if last_login:
                where.append('CAST(u.last_login AS CHAR) LIKE %s')
                params.append(f'%{last_login}%')
        sort = request.args.get('sort', 'username')
        if sort not in _USER_SORTS:
            sort = 'username'
        order = 'DESC' if request.args.get('order', 'ASC').upper() == 'DESC' else 'ASC'
        clause = ' WHERE ' + ' AND '.join(where)
        page_raw = request.args.get('page', '1')
        page = 1 if not str(page_raw).isdigit() else min(max(int(page_raw), 1), 10000)
        per_page = bounded_page_size(request.args.get('per_page'))
        bound = tuple(params)
        cursor.execute(f'SELECT COUNT(u.id) AS total FROM users u {clause}', bound)
        total = safe_count(cursor.fetchone()['total'])
        offset, total_pages = page_bounds(page, per_page, total)
        cursor.execute(
            f"""
            SELECT u.id, u.username, u.role, u.status, u.last_login
            FROM users u
            {clause}
            ORDER BY {_USER_SORTS[sort]} {order}
            LIMIT %s OFFSET %s
            """,
            bound + (per_page, offset),
        )
        users = [
            {
                'id': safe_count(row['id']),
                'username': safe_text(row.get('username'), 50),
                'role': safe_text(row.get('role'), 50),
                'status': safe_text(row.get('status') or 'active', 20),
                'last_login': safe_stamp(row.get('last_login')),
            }
            for row in cursor.fetchall()
        ]
        cursor.execute('SELECT name FROM roles ORDER BY name')
        roles = [
            safe_text(row['name'], 50)
            for row in cursor.fetchall()
            if row.get('name') and row['name'] not in ('Teacher', 'Student')
        ]
        return json_ok({
            'users': users,
            'page': page,
            'total_pages': total_pages,
            'total': total,
            'roles': roles,
            'permissions': {
                'add': allowed('users_add_user'),
                'change': allowed('users_change_user'),
                'delete': allowed('users_delete_user'),
                'manage': allowed('users_manage_permissions'),
                'password': allowed('users_change_password'),
                'export': allowed('users_export_data'),
            },
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('User list failed')
        return json_error(_MESSAGES['users_unavailable'], 500, 'users_unavailable')
    finally:
        close(cursor, connection)


def _create():
    denied = _denied('users_add_user')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(frozenset(('username', 'password', 'role', 'status')))
        username = required_text(payload.get('username'), 50, 'user_username_invalid')
        password = payload.get('password')
        if not isinstance(password, str) or _CONTROL.search(password) or not password.strip() or len(password) > 128:
            raise InputError('user_password_invalid')
        role = required_text(payload.get('role'), 50, 'user_role_invalid')
        status = payload.get('status') or 'active'
        if status not in _STATUSES:
            raise InputError('user_status_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT id FROM roles WHERE name = %s', (role,))
        if not cursor.fetchone():
            raise InputError('user_role_invalid')
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            return json_error(_MESSAGES['user_username_taken'], 400, 'user_username_taken')
        cursor.execute(
            'INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)',
            (username, generate_password_hash(password), role, status),
        )
        user_id = cursor.lastrowid
        log_activity(session.get('user_id'), 'create_user', f'Created new user: {username} with role {role}')
        connection.commit()
        return json_ok({'id': safe_count(user_id)}, 201)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        return json_error(_MESSAGES['user_username_taken'], 400, 'user_username_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('User create failed')
        return json_error(_MESSAGES['users_unavailable'], 500, 'users_unavailable')
    finally:
        close(cursor, connection)


def _deactivate(user_id):
    denied = _denied('users_delete_user')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT username, role FROM users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        if not user:
            return json_error(_MESSAGES['user_not_found'], 404, 'user_not_found')
        if user.get('role') == 'Super Admin' or user_id == session.get('user_id'):
            return json_error(_MESSAGES['user_protected'], 403, 'user_protected')
        cursor.execute("UPDATE users SET status = 'inactive' WHERE id = %s", (user_id,))
        if user.get('role') == 'Teacher':
            cursor.execute('UPDATE faculty SET is_active = 0 WHERE user_id = %s', (user_id,))
        elif user.get('role') == 'Student':
            cursor.execute('UPDATE students SET is_active = 0 WHERE user_id = %s', (user_id,))
        log_activity(session.get('user_id'), 'delete_user', f"Soft-deleted user {user.get('username')}")
        connection.commit()
        return json_ok({'id': safe_count(user_id)})
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('User deactivate failed')
        return json_error(_MESSAGES['users_unavailable'], 500, 'users_unavailable')
    finally:
        close(cursor, connection)
