"""Role list and the permissions granted to a role."""

import re

from flask import current_app, session
from mysql.connector import IntegrityError

from extensions import get_db_connection
from api.web.access import InputError, allowed, body, close, optional_text, permission_denied, reject_input, required_text, whole_number
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from security import log_activity
from security.authority import role_level_by_id, role_permission_ids, role_problem

_ROLE_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9 _-]{0,49}$')
_MESSAGES = {
    'roles_unavailable': 'The page could not be loaded.',
    'role_not_found': 'That role was not found.',
    'permission_ids_invalid': 'Choose permissions from the list.',
    'invalid_body': 'The request could not be accepted.',
    'role_name_invalid': 'Enter a role name up to 50 characters.',
    'role_description_invalid': 'Description must be 400 characters or fewer.',
    'role_level_invalid': 'Hierarchy level must be a number from 1 to 99.',
    'role_name_taken': 'A role with this name already exists.',
    'role_name_locked': 'The Super Admin role cannot be renamed.',
    'role_protected': 'You cannot change a role senior to your own or make a role senior to yours.',
    'role_permission_unheld': 'You can only grant permissions you hold yourself.',
}


def _role_denied(problem):
    if problem == 'unheld':
        return json_error(_MESSAGES['role_permission_unheld'], 403, 'role_permission_unheld')
    return json_error(_MESSAGES['role_protected'], 403, 'role_protected')


def register_role_routes(blueprint):
    blueprint.add_url_rule('/roles', 'roles_list', _list, methods=['GET'])
    blueprint.add_url_rule('/roles', 'roles_create', _create, methods=['POST'])
    blueprint.add_url_rule('/roles/<int:role_id>', 'roles_update', _update, methods=['PUT'])
    blueprint.add_url_rule('/roles/<int:role_id>/users', 'role_users', _users, methods=['GET'])
    blueprint.add_url_rule('/roles/<int:role_id>/permissions', 'role_permissions', _permissions, methods=['GET'])
    blueprint.add_url_rule('/roles/<int:role_id>/permissions', 'role_permissions_replace', _replace, methods=['PUT'])


def _role_fields(payload):
    name = required_text(payload.get('name'), 50, 'role_name_invalid')
    if not _ROLE_NAME.match(name):
        raise InputError('role_name_invalid')
    description = optional_text(payload.get('description'), 400, 'role_description_invalid')
    level = whole_number(payload.get('hierarchy_level'), 99, 'role_level_invalid', lower=1)
    return name, description, level


def _view_denied():
    viewed = permission_denied('roles_view_role', 'roles_unavailable', _MESSAGES['roles_unavailable'])
    if viewed is None:
        return None
    return permission_denied('roles_change_role', 'roles_unavailable', _MESSAGES['roles_unavailable'])


def _change_denied():
    return permission_denied('roles_change_role', 'roles_unavailable', _MESSAGES['roles_unavailable'])


def _permission_ids(payload):
    raw = payload.get('permission_ids')
    if not isinstance(raw, list) or len(raw) > 500:
        raise InputError('permission_ids_invalid')
    ids = []
    seen = set()
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int) or item < 1 or item > 1000000:
            raise InputError('permission_ids_invalid')
        if item not in seen:
            seen.add(item)
            ids.append(item)
    return ids


def _list():
    denied = _view_denied()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT r.id, r.name, r.description, r.hierarchy_level,
                   COUNT(DISTINCT u.id) AS user_count,
                   COUNT(DISTINCT rp.permission_id) AS permission_count
            FROM roles r
            LEFT JOIN users u ON u.role = r.name
            LEFT JOIN role_permissions rp ON rp.role_id = r.id
            GROUP BY r.id, r.name, r.description, r.hierarchy_level
            ORDER BY r.hierarchy_level, r.name
            """
        )
        roles = [
            {
                'id': safe_count(row['id']),
                'name': safe_text(row.get('name'), 50),
                'description': safe_text(row.get('description') or '', 400),
                'hierarchy_level': safe_count(row.get('hierarchy_level')) or 50,
                'user_count': safe_count(row.get('user_count')),
                'permission_count': safe_count(row.get('permission_count')),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({
            'roles': roles,
            'can_add': allowed('roles_add_role'),
            'can_update': allowed('roles_change_role'),
        })
    except Exception:
        current_app.logger.exception('Role list failed')
        return json_error(_MESSAGES['roles_unavailable'], 500, 'roles_unavailable')
    finally:
        close(cursor, connection)


def _create():
    denied = permission_denied('roles_add_role', 'roles_unavailable', _MESSAGES['roles_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        name, description, level = _role_fields(body(frozenset(('name', 'description', 'hierarchy_level'))))
        connection = get_db_connection()
        cursor = connection.cursor()
        problem = role_problem(cursor, session.get('user_id'), new_level=level)
        if problem:
            return _role_denied(problem)
        cursor.execute(
            'INSERT INTO roles (name, description, hierarchy_level) VALUES (%s, %s, %s)',
            (name, description or None, level),
        )
        role_id = cursor.lastrowid
        log_activity(session.get('user_id'), 'create_role', f'Created new role: {name}',
                     entity_type='role', entity_id=role_id, cursor=cursor)
        connection.commit()
        return json_ok({'id': safe_count(role_id), 'name': name}, 201)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        return json_error(_MESSAGES['role_name_taken'], 400, 'role_name_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Role create failed')
        return json_error(_MESSAGES['roles_unavailable'], 500, 'roles_unavailable')
    finally:
        close(cursor, connection)


def _update(role_id):
    denied = _change_denied()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        name, description, level = _role_fields(body(frozenset(('name', 'description', 'hierarchy_level'))))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        old_name, current_level = role_level_by_id(cursor, role_id)
        if old_name is None:
            return json_error(_MESSAGES['role_not_found'], 404, 'role_not_found')
        if old_name == 'Super Admin' and name != 'Super Admin':
            return json_error(_MESSAGES['role_name_locked'], 400, 'role_name_locked')
        if old_name == 'Super Admin':
            level = 1
        problem = role_problem(cursor, session.get('user_id'), current_level=current_level, new_level=level)
        if problem:
            return _role_denied(problem)
        cursor.execute(
            'UPDATE roles SET name = %s, description = %s, hierarchy_level = %s WHERE id = %s',
            (name, description or None, level, role_id),
        )
        if old_name != name:
            cursor.execute('UPDATE users SET role = %s WHERE role = %s', (name, old_name))
        log_activity(
            session.get('user_id'), 'edit_role', f'Edited role {name} (ID: {role_id})', entity_type='role',
            entity_id=role_id, old_values={'name': old_name, 'hierarchy_level': current_level},
            new_values={'name': name, 'hierarchy_level': level}, cursor=cursor,
        )
        connection.commit()
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        return json_error(_MESSAGES['role_name_taken'], 400, 'role_name_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Role update failed')
        return json_error(_MESSAGES['roles_unavailable'], 500, 'roles_unavailable')
    finally:
        close(cursor, connection)


def _users(role_id):
    denied = _view_denied()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT name FROM roles WHERE id = %s', (role_id,))
        role = cursor.fetchone()
        if not role:
            return json_error(_MESSAGES['role_not_found'], 404, 'role_not_found')
        cursor.execute(
            """
            SELECT id, username, status, last_login
            FROM users
            WHERE role = %s
            ORDER BY username
            LIMIT 500
            """,
            (role.get('name'),),
        )
        users = [
            {
                'id': safe_count(row.get('id')),
                'username': safe_text(row.get('username'), 50),
                'status': safe_text(row.get('status') or '', 20),
                'last_login': safe_stamp(row.get('last_login')),
            }
            for row in cursor.fetchall()
            if safe_count(row.get('id')) > 0 and safe_text(row.get('username'), 50)
        ]
        role_name = safe_text(role.get('name'), 50)
        return json_ok({
            'role': role_name,
            'can_update': allowed('roles_change_role'),
            'can_delete': allowed('users_delete_user') and role_name != 'Super Admin',
            'users': users,
        })
    except Exception:
        current_app.logger.exception('Role users failed')
        return json_error(_MESSAGES['roles_unavailable'], 500, 'roles_unavailable')
    finally:
        close(cursor, connection)


def _permissions(role_id):
    denied = _view_denied()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT name, description, hierarchy_level FROM roles WHERE id = %s', (role_id,))
        role = cursor.fetchone()
        if not role:
            return json_error(_MESSAGES['role_not_found'], 404, 'role_not_found')
        cursor.execute(
            """
            SELECT p.id, p.module, p.name, p.description,
                   CASE WHEN rp.role_id IS NULL THEN 0 ELSE 1 END AS granted
            FROM permissions p
            LEFT JOIN role_permissions rp ON rp.permission_id = p.id AND rp.role_id = %s
            ORDER BY p.module, p.name
            """,
            (role_id,),
        )
        rows = [
            {
                'id': safe_count(row.get('id')),
                'module': safe_text(row.get('module') or 'General', 50),
                'name': safe_text(row.get('name'), 50),
                'description': safe_text(row.get('description') or '', 200),
                'granted': bool(row.get('granted')),
            }
            for row in cursor.fetchall()
            if safe_count(row.get('id')) > 0
        ]
        return json_ok({
            'role': safe_text(role.get('name'), 50),
            'description': safe_text(role.get('description') or '', 400),
            'hierarchy_level': safe_count(role.get('hierarchy_level')) or 50,
            'permissions': rows,
            'can_update': allowed('roles_change_role'),
        })
    except Exception:
        current_app.logger.exception('Role permissions failed')
        return json_error(_MESSAGES['roles_unavailable'], 500, 'roles_unavailable')
    finally:
        close(cursor, connection)


def _replace(role_id):
    denied = _change_denied()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        ids = _permission_ids(body(frozenset(('permission_ids',))))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        role_name, current_level = role_level_by_id(cursor, role_id)
        if role_name is None:
            return json_error(_MESSAGES['role_not_found'], 404, 'role_not_found')
        if ids:
            placeholders = ', '.join(['%s'] * len(ids))
            cursor.execute(f'SELECT id FROM permissions WHERE id IN ({placeholders})', tuple(ids))
            found = {safe_count(row.get('id')) for row in cursor.fetchall()}
            if found != set(ids):
                raise InputError('permission_ids_invalid')
        added = set(ids) - role_permission_ids(cursor, role_id)
        problem = role_problem(cursor, session.get('user_id'), current_level=current_level, added_permission_ids=added)
        if problem:
            return _role_denied(problem)
        cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', (role_id,))
        for permission_id in ids:
            cursor.execute(
                'INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)',
                (role_id, permission_id),
            )
        log_activity(session.get('user_id'), 'update_role_permissions', f'Updated permissions for role ID {role_id}',
                     entity_type='role', entity_id=role_id, new_values={'permission_ids': ids}, cursor=cursor)
        connection.commit()
        return json_ok({'saved': True, 'count': len(ids)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Role permission replace failed')
        return json_error(_MESSAGES['roles_unavailable'], 500, 'roles_unavailable')
    finally:
        close(cursor, connection)
