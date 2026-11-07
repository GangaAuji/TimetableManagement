"""User edits and permission assignment for the React users screens.

Each action uses the same permission name as the old user-management screen.
"""

from flask import current_app, session

from api.web.access import InputError, allowed, body, close, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from data_access.user_actions import fetch_users_for_export
from data_access.user_permissions import fetch_departments
from extensions import get_db_connection
from security import grant_user_permission, revoke_user_permission
from services.user_actions import apply_bulk_user_action, reset_user_password, toggle_user_status
from services.user_permissions import assign_permission_group, load_user_permission_page, unassign_permission_group
from services.users import change_user, find_user, normalize_role

_ROLES = frozenset(('Super Admin', 'Admin', 'Teacher', 'Student'))
_BULK = frozenset(('activate', 'deactivate', 'delete'))
_MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'users_unavailable': 'The page could not be loaded.',
    'user_not_found': 'That user was not found.',
    'user_username_invalid': 'Enter a username of at least 3 characters.',
    'user_password_invalid': 'A new password must be at least 8 characters.',
    'user_role_invalid': 'Choose Super Admin, Admin, Teacher, or Student.',
    'user_status_invalid': 'Choose a valid status.',
    'user_username_taken': 'That username is already in use.',
    'user_email_taken': 'That email is already in use.',
    'user_protected': 'That account cannot be changed this way.',
    'user_permission_invalid': 'Choose a permission.',
    'user_permission_failed': 'That permission could not be changed.',
    'user_group_invalid': 'Choose a permission group.',
    'user_bulk_invalid': 'Choose users and an action.',
}


def register_user_access_routes(blueprint):
    blueprint.add_url_rule('/users/export', 'users_export', _export, methods=['GET'])
    blueprint.add_url_rule('/users/bulk', 'users_bulk', _bulk, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>', 'users_detail', _detail, methods=['GET'])
    blueprint.add_url_rule('/users/<int:user_id>', 'users_update', _update, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>/status', 'users_status', _status, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>/password', 'users_password', _password, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>/access', 'users_access', _access, methods=['GET'])
    blueprint.add_url_rule('/users/<int:user_id>/permissions', 'users_grant', _grant, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>/permissions/revoke', 'users_revoke', _revoke, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>/permissions/bulk', 'users_grant_many', _grant_many, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>/groups', 'users_grant_group', _grant_group, methods=['POST'])
    blueprint.add_url_rule('/users/<int:user_id>/groups/revoke', 'users_revoke_group', _revoke_group, methods=['POST'])


def _denied(permission_name):
    return permission_denied(permission_name, 'users_unavailable', _MESSAGES['users_unavailable'])


def _service_error(payload, status):
    message = payload.get('error') or payload.get('message') or _MESSAGES['users_unavailable']
    if status == 404:
        return json_error(_MESSAGES['user_not_found'], 404, 'user_not_found')
    if status == 403:
        return json_error(_MESSAGES['user_protected'], 403, 'user_protected')
    if status == 400:
        return json_error(safe_text(message, 160), 400, 'invalid_body')
    return json_error(_MESSAGES['users_unavailable'], 500, 'users_unavailable')


def _optional_id(value):
    if value in (None, '', 0):
        return None
    number = safe_count(value)
    if isinstance(value, bool) or number < 1 or safe_text(value, 8) != str(number):
        raise InputError('invalid_body')
    return number


def _detail(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload, status = find_user(user_id)
        if status != 200:
            return json_error(_MESSAGES['user_not_found'], 404, 'user_not_found')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        departments = [
            {'id': safe_count(row['id']), 'name': safe_text(row.get('name'), 100)}
            for row in fetch_departments(cursor)
        ]
        return json_ok({
            'user': {
                'id': safe_count(payload.get('id')),
                'username': safe_text(payload.get('username'), 50),
                'email': safe_text(payload.get('email') or '', 160),
                'role': safe_text(payload.get('role'), 50),
                'status': safe_text(payload.get('status') or 'active', 20),
                'is_hod': bool(payload.get('is_hod')),
                'department_id': safe_count(payload.get('department_id')) or None,
            },
            'roles': [safe_text(name, 50) for name in payload.get('available_roles') or []],
            'departments': departments,
        })
    except Exception:
        current_app.logger.exception('User lookup failed')
        return json_error(_MESSAGES['users_unavailable'], 500, 'users_unavailable')
    finally:
        close(cursor, connection)


def _update(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    try:
        payload = body(frozenset(('username', 'password', 'role', 'status', 'email', 'department_id', 'is_hod')))
        username = payload.get('username')
        if not isinstance(username, str) or len(username.strip()) < 3 or len(username.strip()) > 50:
            raise InputError('user_username_invalid')
        password = payload.get('password') or ''
        if not isinstance(password, str) or (password and len(password) < 8):
            raise InputError('user_password_invalid')
        role = normalize_role(str(payload.get('role') or '').strip())
        if role not in _ROLES:
            raise InputError('user_role_invalid')
        status = payload.get('status') or 'active'
        if status not in ('active', 'inactive'):
            raise InputError('user_status_invalid')
        email = payload.get('email') or ''
        if not isinstance(email, str) or len(email) > 160:
            raise InputError('invalid_body')
        if not isinstance(payload.get('is_hod'), bool):
            raise InputError('invalid_body')
        department_id = _optional_id(payload.get('department_id'))
        result = change_user(
            user_id,
            username.strip(),
            password,
            role,
            status,
            email.strip(),
            '' if department_id is None else str(department_id),
            payload.get('is_hod'),
            session,
        )
        if result == 'missing':
            return json_error(_MESSAGES['user_not_found'], 404, 'user_not_found')
        if result == 'username':
            return json_error(_MESSAGES['user_username_taken'], 400, 'user_username_taken')
        if result == 'email':
            return json_error(_MESSAGES['user_email_taken'], 400, 'user_email_taken')
        if result != 'ok':
            return json_error(_MESSAGES['users_unavailable'], 500, 'users_unavailable')
        return json_ok({'id': safe_count(user_id)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('User update failed')
        return json_error(_MESSAGES['users_unavailable'], 500, 'users_unavailable')


def _status(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    payload, status = toggle_user_status(user_id, session)
    if status != 200:
        return _service_error(payload, status)
    return json_ok({'id': safe_count(user_id), 'status': safe_text(payload.get('status'), 20)})


def _password(user_id):
    denied = _denied('users_change_password')
    if denied:
        return denied
    payload, status = reset_user_password(user_id, '', session)
    if status != 200:
        return _service_error(payload, status)
    return json_ok({
        'id': safe_count(user_id),
        'temporary_password': safe_text(payload.get('temp_password'), 32),
    })


def _bulk():
    try:
        payload = body(frozenset(('action', 'ids')))
        action = payload.get('action')
        if action not in _BULK:
            raise InputError('user_bulk_invalid')
        raw_ids = payload.get('ids')
        if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
            raise InputError('user_bulk_invalid')
        ids = [str(_optional_id(item)) for item in raw_ids]
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    permission_name = 'users_delete_user' if action == 'delete' else 'users_change_user'
    denied = _denied(permission_name)
    if denied:
        return denied
    result, status = apply_bulk_user_action(action, ids, '', session)
    if status != 200:
        return _service_error(result, status)
    return json_ok({'message': safe_text(result.get('message'), 160)})


def _export():
    denied = _denied('users_export_data')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        role = request_arg('role')
        status = request_arg('status')
        search = request_arg('search')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        rows = [
            row for row in fetch_users_for_export(cursor, role, status, search)
            if row.get('role') not in ('Teacher', 'Student')
        ]
        return json_ok({
            'users': [
                {
                    'id': safe_count(row['id']),
                    'username': safe_text(row.get('username'), 50),
                    'role': safe_text(row.get('role'), 50),
                    'status': safe_text(row.get('status') or 'active', 20),
                    'last_login': safe_stamp(row.get('last_login')),
                }
                for row in rows
            ]
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('User export failed')
        return json_error(_MESSAGES['users_unavailable'], 500, 'users_unavailable')
    finally:
        close(cursor, connection)


def request_arg(name):
    from flask import request
    raw = request.args.get(name, '')
    if not isinstance(raw, str) or len(raw) > 100:
        raise InputError('invalid_body')
    return raw.strip()


def _permission_name(payload):
    name = payload.get('permission_name') or payload.get('permission_names')
    if isinstance(name, list):
        raise InputError('user_permission_invalid')
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise InputError('user_permission_invalid')
    return name.strip()


def _grant_result(success, message):
    if success:
        return json_ok({'message': 'Permission granted.'})
    if message == 'Permission not found':
        return json_error(_MESSAGES['user_permission_invalid'], 400, 'user_permission_invalid')
    if message == 'Permission already granted with these restrictions':
        return json_error(message, 400, 'user_permission_failed')
    return json_error(_MESSAGES['user_permission_failed'], 400, 'user_permission_failed')


def _access(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    page = load_user_permission_page(user_id)
    if page is None:
        return json_error(_MESSAGES['user_not_found'], 404, 'user_not_found')
    departments = {item['id']: item['name'] for item in page['departments']}
    catalog = []
    for module, permissions in page['permissions_by_module'].items():
        for perm in permissions:
            catalog.append({
                'id': safe_count(perm['id']),
                'name': safe_text(perm['name'], 80),
                'module': safe_text(module or 'General', 40),
                'description': safe_text(perm.get('description') or '', 200),
            })
    assigned = []
    for perm in page['user_permissions']:
        department_id = perm.get('department_id')
        assigned.append({
            'name': safe_text(perm.get('name'), 80),
            'module': safe_text(perm.get('module') or 'General', 40),
            'source': safe_text(perm.get('source') or '', 20),
            'department_id': safe_count(department_id) or None,
            'department_name': safe_text(departments.get(department_id) or '', 100),
        })
    groups = []
    for group in page['user_groups']:
        department_id = group.get('department_id')
        groups.append({
            'group_id': safe_count(group.get('group_id')),
            'name': safe_text(group.get('name'), 80),
            'department_id': safe_count(department_id) or None,
            'department_name': safe_text(departments.get(department_id) or '', 100),
        })
    user = page['user']
    return json_ok({
        'user': {
            'id': safe_count(user.get('id')),
            'username': safe_text(user.get('username'), 50),
            'role': safe_text(user.get('role'), 50),
            'department_name': safe_text(user.get('department_name') or '', 100),
        },
        'assigned': assigned,
        'catalog': catalog,
        'departments': [
            {'id': safe_count(item['id']), 'name': safe_text(item['name'], 100)}
            for item in page['departments']
        ],
        'groups': [
            {'id': safe_count(item['id']), 'name': safe_text(item['name'], 80)}
            for item in page['permission_groups']
        ],
        'assigned_groups': groups,
        'can_change': allowed('users_change_user'),
    })


def _grant(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    try:
        payload = body(frozenset(('permission_name', 'department_id')))
        permission_name = _permission_name(payload)
        department_id = _optional_id(payload.get('department_id'))
        success, message = grant_user_permission(
            user_id=user_id,
            permission_name=permission_name,
            department_id=department_id,
            granted_by=session.get('user_id'),
        )
        return _grant_result(success, message)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Permission grant failed')
        return json_error(_MESSAGES['user_permission_failed'], 500, 'user_permission_failed')


def _revoke(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    try:
        payload = body(frozenset(('permission_name', 'department_id')))
        permission_name = _permission_name(payload)
        department_id = _optional_id(payload.get('department_id'))
        success, message = revoke_user_permission(
            user_id=user_id,
            permission_name=permission_name,
            department_id=department_id,
            revoked_by=session.get('user_id'),
        )
        if success:
            return json_ok({'message': 'Permission revoked.'})
        if message == 'Permission not found':
            return json_error(_MESSAGES['user_permission_invalid'], 400, 'user_permission_invalid')
        return json_error(_MESSAGES['user_permission_failed'], 400, 'user_permission_failed')
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Permission revoke failed')
        return json_error(_MESSAGES['user_permission_failed'], 500, 'user_permission_failed')


def _grant_many(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    try:
        payload = body(frozenset(('permission_names', 'department_id')))
        names = payload.get('permission_names')
        if not isinstance(names, list) or not names or len(names) > 100:
            raise InputError('user_permission_invalid')
        department_id = _optional_id(payload.get('department_id'))
        granted = 0
        for name in names:
            if not isinstance(name, str) or not name.strip() or len(name) > 80:
                raise InputError('user_permission_invalid')
            success, _message = grant_user_permission(
                user_id=user_id,
                permission_name=name.strip(),
                department_id=department_id,
                granted_by=session.get('user_id'),
            )
            if success:
                granted += 1
        return json_ok({'granted': granted})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Bulk permission grant failed')
        return json_error(_MESSAGES['user_permission_failed'], 500, 'user_permission_failed')


def _grant_group(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    try:
        payload = body(frozenset(('group_id', 'department_id')))
        group_id = _optional_id(payload.get('group_id'))
        if group_id is None:
            raise InputError('user_group_invalid')
        department_id = _optional_id(payload.get('department_id'))
        result, status = assign_permission_group(user_id, group_id, department_id, session)
        if status != 200:
            return _service_error(result, status)
        return json_ok({'message': 'Permission group granted.'})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Permission group grant failed')
        return json_error(_MESSAGES['user_permission_failed'], 500, 'user_permission_failed')


def _revoke_group(user_id):
    denied = _denied('users_change_user')
    if denied:
        return denied
    try:
        payload = body(frozenset(('group_id', 'department_id')))
        group_id = _optional_id(payload.get('group_id'))
        if group_id is None:
            raise InputError('user_group_invalid')
        department_id = _optional_id(payload.get('department_id'))
        result, status = unassign_permission_group(user_id, group_id, department_id, session)
        if status != 200:
            return _service_error(result, status)
        return json_ok({'message': 'Permission group revoked.'})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Permission group revoke failed')
        return json_error(_MESSAGES['user_permission_failed'], 500, 'user_permission_failed')
