"""Permission catalog. A new module permission is added here by name."""

import re

from flask import current_app, session
from mysql.connector import IntegrityError

from extensions import get_db_connection
from api.web.access import InputError, allowed, body, close, optional_text, permission_denied, reject_input, required_text
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from security import log_activity

_NAME = re.compile(r'^[a-z][a-z0-9_]{0,48}$')
_MODULE = re.compile(r'^[A-Za-z][A-Za-z0-9 &/_-]{0,49}$')
_MESSAGES = {
    'permissions_unavailable': 'The page could not be loaded.',
    'permission_name_invalid': 'Use a name like courses_view_course, up to 50 characters.',
    'permission_module_invalid': 'Enter a module name up to 50 characters.',
    'permission_description_invalid': 'Description must be 200 characters or fewer.',
    'permission_name_taken': 'That permission name already exists.',
    'invalid_body': 'The request could not be accepted.',
}


def register_permission_routes(blueprint):
    blueprint.add_url_rule('/permissions', 'permissions_list', _list, methods=['GET'])
    blueprint.add_url_rule('/permissions', 'permissions_create', _create, methods=['POST'])


def _view_denied():
    viewed = permission_denied('roles_view_role', 'permissions_unavailable', _MESSAGES['permissions_unavailable'])
    if viewed is None:
        return None
    return permission_denied('roles_change_role', 'permissions_unavailable', _MESSAGES['permissions_unavailable'])


def _change_denied():
    return permission_denied('roles_change_role', 'permissions_unavailable', _MESSAGES['permissions_unavailable'])


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
            SELECT id, name, module, description
            FROM permissions
            ORDER BY module, name
            """
        )
        rows = [
            {
                'id': safe_count(row.get('id')),
                'name': safe_text(row.get('name'), 50),
                'module': safe_text(row.get('module') or 'General', 50),
                'description': safe_text(row.get('description') or '', 200),
            }
            for row in cursor.fetchall()
            if safe_count(row.get('id')) > 0 and safe_text(row.get('name'), 50)
        ]
        return json_ok({'permissions': rows, 'can_add': allowed('roles_change_role')})
    except Exception:
        current_app.logger.exception('Permission list failed')
        return json_error(_MESSAGES['permissions_unavailable'], 500, 'permissions_unavailable')
    finally:
        close(cursor, connection)


def _create():
    denied = _change_denied()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(frozenset(('name', 'module', 'description')))
        name = required_text(payload.get('name'), 50, 'permission_name_invalid').lower()
        if not _NAME.match(name):
            raise InputError('permission_name_invalid')
        module = required_text(payload.get('module'), 50, 'permission_module_invalid')
        if not _MODULE.match(module):
            raise InputError('permission_module_invalid')
        description = optional_text(payload.get('description'), 200, 'permission_description_invalid')
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            'INSERT INTO permissions (name, module, description) VALUES (%s, %s, %s)',
            (name, module, description),
        )
        permission_id = cursor.lastrowid
        log_activity(session.get('user_id'), 'add_permission', f'Added permission {name}',
                     entity_type='permission', entity_id=permission_id, cursor=cursor)
        connection.commit()
        return json_ok({'id': safe_count(permission_id), 'name': name, 'module': module}, 201)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        return json_error(_MESSAGES['permission_name_taken'], 400, 'permission_name_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Permission create failed')
        return json_error(_MESSAGES['permissions_unavailable'], 500, 'permissions_unavailable')
    finally:
        close(cursor, connection)
