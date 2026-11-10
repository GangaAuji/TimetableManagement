"""Department API. Rules match the existing admin department screen."""

import re

from flask import current_app, request
from mysql.connector import IntegrityError

from extensions import get_db_connection
from core.db import transaction
from core.scope import current_scope
from data_access import institutions as institutions_store
from api.web.access import InputError, allowed, institution_input, optional_text, permission_denied, required_text
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

DEPARTMENT_FIELDS = frozenset(('name', 'code', 'description', 'head_of_department', 'is_active', 'institution_id'))
_CODE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 .&/_-]{0,19}$')

_ERROR_MESSAGES = {
    'invalid_body': 'The department could not be saved.',
    'institution_invalid': 'Choose an institution you manage.',
    'department_not_owned': 'Only the institution that owns this department can change it.',
    'department_name_invalid': 'Enter a department name up to 100 characters.',
    'department_code_invalid': 'Enter a department code up to 20 characters.',
    'department_head_invalid': 'Head of department must be 100 characters or fewer.',
    'description_invalid': 'Description must be 4000 characters or fewer.',
    'department_name_taken': 'A department with this name already exists.',
    'department_code_taken': 'A department with this code already exists.',
    'department_not_found': 'That department was not found.',
    'department_in_use': 'This department has courses or faculty, so it cannot be deleted.',
    'departments_unavailable': 'The department list could not be loaded.',
}


class _DepartmentInputError(Exception):
    def __init__(self, code):
        self.code = code


def _permission_error(permission_name):
    return permission_denied(
        permission_name,
        'departments_unavailable',
        'The department list could not be loaded.',
        log_message='Department permission check failed',
    )


def _can(permission_name):
    return allowed(permission_name)


def _input_error(code):
    return json_error(_ERROR_MESSAGES.get(code, 'The department could not be saved.'), 400, code)


def _required_text(value, limit, code):
    try:
        return required_text(value, limit, code)
    except InputError as exc:
        raise _DepartmentInputError(exc.code) from None


def _optional_text(value, limit, code):
    try:
        return optional_text(value, limit, code)
    except InputError as exc:
        raise _DepartmentInputError(exc.code) from None


def _name(value):
    return _required_text(value, 100, 'department_name_invalid')


def _code(value):
    text = _required_text(value, 20, 'department_code_invalid')
    if not _CODE.match(text):
        raise _DepartmentInputError('department_code_invalid')
    return text


def _active(value):
    if not isinstance(value, bool):
        raise _DepartmentInputError('invalid_body')
    return value


def _payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - DEPARTMENT_FIELDS:
        return _input_error('invalid_body')
    return payload


def _public_department(row):
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 100),
        'code': safe_text(row.get('code'), 20),
        'description': safe_text(row.get('description'), 4000),
        'head_of_department': safe_text(row.get('head_of_department'), 100),
        'is_active': bool(row.get('is_active')),
        'course_count': safe_count(row.get('course_count')),
        'institution_id': safe_count(row.get('institution_id')) or None,
        'institution_name': safe_text(row.get('institution_name'), 150),
    }


_DEPARTMENT_SELECT = """
    SELECT d.id, d.name, d.code, d.description, d.head_of_department, d.is_active, d.institution_id,
           i.name AS institution_name, COUNT(c.id) AS course_count
    FROM departments d
    JOIN institutions i ON i.id = d.institution_id
    LEFT JOIN courses c ON d.id = c.department_id
"""


def _owned(cursor, department_id, scope):
    """The department row when the scope may change it; a JSON error otherwise."""
    cursor.execute('SELECT id, institution_id FROM departments WHERE id = %s', (department_id,))
    row = cursor.fetchone()
    if row is None:
        return _input_error('department_not_found')
    if not scope.allows(row.get('institution_id')):
        return json_error(_ERROR_MESSAGES['department_not_owned'], 403, 'department_not_owned')
    return row


def _close(cursor, connection):
    if cursor is not None:
        cursor.close()
    if connection is not None:
        connection.close()


def _reject_conflict(cursor, name, code, department_id):
    cursor.execute(
        'SELECT id, name, code FROM departments WHERE name = %s OR code = %s',
        (name, code),
    )
    for row in cursor.fetchall():
        if department_id is not None and row.get('id') == department_id:
            continue
        if row.get('name') == name:
            raise _DepartmentInputError('department_name_taken')
        if row.get('code') == code:
            raise _DepartmentInputError('department_code_taken')


def _save(payload, department_id):
    connection = None
    cursor = None
    try:
        name = _name(payload.get('name'))
        code = _code(payload.get('code'))
        description = _optional_text(payload.get('description', ''), 4000, 'description_invalid')
        head = _optional_text(payload.get('head_of_department', ''), 100, 'department_head_invalid')
        is_active = _active(payload.get('is_active'))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        scope = current_scope(cursor)
        existing = None
        if department_id is not None:
            existing = _owned(cursor, department_id, scope)
            if isinstance(existing, tuple):
                return existing
        institution_id = institution_input(
            cursor, scope, payload.get('institution_id'), existing=existing['institution_id'] if existing else None,
        )
        _reject_conflict(cursor, name, code, department_id)
        values = (name, code, description, head, 1 if is_active else 0, institution_id)
        if department_id is None:
            cursor.execute(
                """
                INSERT INTO departments (name, code, description, head_of_department, is_active, institution_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                values,
            )
            saved_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE departments
                SET name = %s, code = %s, description = %s, head_of_department = %s, is_active = %s, institution_id = %s
                WHERE id = %s
                """,
                (*values, department_id),
            )
            saved_id = department_id
        with transaction(connection):
            pass
        return _read(saved_id)
    except (_DepartmentInputError, InputError) as exc:
        if connection is not None:
            connection.rollback()
        return _input_error(exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Department save conflict')
        return _input_error('department_name_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Department save failed')
        return json_error('The department could not be saved.', 500, 'departments_unavailable')
    finally:
        _close(cursor, connection)


def _read(department_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f'{_DEPARTMENT_SELECT} WHERE d.id = %s GROUP BY d.id', (department_id,))
        row = cursor.fetchone()
        if row is None or not safe_count(row.get('id')) or not current_scope(cursor).allows(row.get('institution_id')):
            return _input_error('department_not_found')
        return json_ok(_public_department(row))
    except Exception:
        current_app.logger.exception('Department lookup failed')
        return json_error('The department could not be loaded.', 500, 'departments_unavailable')
    finally:
        _close(cursor, connection)


def register_department_routes(blueprint):
    @blueprint.route('/departments', methods=['GET'])
    def list_departments():
        denied = _permission_error('departments_view')
        if denied is not None:
            return denied

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            scope = current_scope(cursor)
            clause, params = scope.clause('d.institution_id')
            cursor.execute(f'{_DEPARTMENT_SELECT} WHERE {clause} GROUP BY d.id ORDER BY d.name', params)
            departments = [_public_department(row) for row in cursor.fetchall() if safe_count(row.get('id'))]
            institutions = []
            if scope.multiple:
                institutions = [
                    {'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 150), 'short_name': safe_text(row.get('short_name'), 40)}
                    for row in institutions_store.fetch_institutions(cursor, active_only=True)
                    if scope.allows(row.get('id'))
                ]
            return json_ok({
                'departments': departments,
                'institutions': institutions,
                'institution_id': scope.institution_id,
                'permissions': {
                    'add': _can('departments_add'),
                    'change': _can('departments_change'),
                    'delete': _can('departments_delete'),
                    'invite': _can('users_add_user'),
                },
            })
        except Exception:
            current_app.logger.exception('Department list failed')
            return json_error('The department list could not be loaded.', 500, 'departments_unavailable')
        finally:
            _close(cursor, connection)

    @blueprint.route('/departments/<int:department_id>', methods=['GET'])
    def get_department(department_id):
        denied = _permission_error('departments_view')
        if denied is not None:
            return denied
        return _read(department_id)

    @blueprint.route('/departments', methods=['POST'])
    def create_department():
        denied = _permission_error('departments_add')
        if denied is not None:
            return denied
        payload = _payload()
        if isinstance(payload, tuple):
            return payload
        return _save(payload, None)

    @blueprint.route('/departments/<int:department_id>', methods=['PUT'])
    def update_department(department_id):
        denied = _permission_error('departments_change')
        if denied is not None:
            return denied
        payload = _payload()
        if isinstance(payload, tuple):
            return payload
        return _save(payload, department_id)

    @blueprint.route('/departments/<int:department_id>', methods=['DELETE'])
    def delete_department(department_id):
        denied = _permission_error('departments_delete')
        if denied is not None:
            return denied

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            owned = _owned(cursor, department_id, current_scope(cursor))
            if isinstance(owned, tuple):
                return owned
            cursor.execute('SELECT 1 FROM courses WHERE department_id = %s LIMIT 1', (department_id,))
            courses_used = cursor.fetchone() is not None
            cursor.execute('SELECT 1 FROM faculty WHERE department_id = %s LIMIT 1', (department_id,))
            faculty_used = cursor.fetchone() is not None
            if courses_used or faculty_used:
                return _input_error('department_in_use')
            cursor.execute('DELETE FROM departments WHERE id = %s', (department_id,))
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except IntegrityError:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Department delete blocked')
            return _input_error('department_in_use')
        except Exception:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Department delete failed')
            return json_error('The department could not be deleted.', 500, 'departments_unavailable')
        finally:
            _close(cursor, connection)
