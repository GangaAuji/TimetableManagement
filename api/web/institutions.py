"""Organization and institutions API.

Reading needs `institutions_view` or `admin_view_settings`. Changing needs
`institutions_change` or `admin_change_settings`.

See docs/DESIGN_INSTITUTIONS.md. There is one organization row; institutions
are the colleges / schools inside it. Deleting an institution is not offered:
deactivate it instead, so the departments and rooms that point at it keep
their history.
"""

import re

from flask import current_app, request, session
from mysql.connector import IntegrityError

from api.web.access import InputError, allowed, close, flag, optional_text, permission_denied, required_text, whole_number
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core.db import transaction
from core.scope import forget as forget_scope
from data_access import institutions as store
from extensions import get_db_connection

_CODE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,19}$')
INSTITUTION_FIELDS = frozenset(('name', 'code', 'short_name', 'is_active', 'sort_order'))
ORGANIZATION_FIELDS = frozenset(('name', 'short_name'))

_MESSAGES = {
    'invalid_body': 'The institution could not be saved.',
    'institution_name_invalid': 'Enter an institution name up to 150 characters.',
    'institution_code_invalid': 'Enter a code of up to 20 letters, digits, hyphens or underscores.',
    'institution_short_name_invalid': 'Short name must be 40 characters or fewer.',
    'institution_code_taken': 'An institution with this code already exists.',
    'institution_not_found': 'That institution was not found.',
    'institution_last_active': 'At least one institution must stay active.',
    'organization_name_invalid': 'Enter an organization name up to 150 characters.',
    'institutions_unavailable': 'The institutions could not be loaded.',
    'license_required': 'A valid license is required before another institution can be added.',
    'license_institutions': 'The license does not allow another institution.',
}


def _denied(permission_name):
    return permission_denied(
        permission_name, 'institutions_unavailable', 'The institutions could not be loaded.',
        log_message='Institution permission check failed',
    )


def _view_denied():
    if allowed('institutions_view') or allowed('admin_view_settings'):
        return None
    return _denied('institutions_view')


def _change_denied():
    if allowed('institutions_change') or allowed('admin_change_settings'):
        return None
    return _denied('institutions_change')


def _public_institution(row, usage=None):
    item = {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 150),
        'code': safe_text(row.get('code'), 20),
        'short_name': safe_text(row.get('short_name'), 40),
        'is_active': bool(row.get('is_active')),
        'sort_order': safe_count(row.get('sort_order')),
    }
    if usage is not None:
        item.update({key: safe_count(value) for key, value in usage.items()})
    return item


def _public_organization(row):
    if row is None:
        return None
    return {'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 150), 'short_name': safe_text(row.get('short_name'), 40)}


def _institution_input(payload, *, creating):
    name = required_text(payload.get('name'), 150, 'institution_name_invalid')
    code = required_text(payload.get('code'), 20, 'institution_code_invalid').upper()
    if not _CODE.match(code):
        raise InputError('institution_code_invalid')
    short_name = optional_text(payload.get('short_name', ''), 40, 'institution_short_name_invalid') or None
    is_active = flag(payload.get('is_active', True))
    sort_order = whole_number(payload.get('sort_order', 0), 10000, 'invalid_body')
    return {'name': name, 'code': code, 'short_name': short_name, 'is_active': is_active, 'sort_order': sort_order}


def _listing(cursor):
    rows = store.fetch_institutions(cursor)
    return {
        'organization': _public_organization(store.fetch_organization(cursor)),
        'institutions': [_public_institution(row, store.institution_usage(cursor, row['id'])) for row in rows],
        'permissions': {'change': allowed('institutions_change') or allowed('admin_change_settings')},
    }


def register_institution_routes(blueprint):
    @blueprint.route('/institutions', methods=['GET'])
    def list_institutions():
        denied = _view_denied()
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            if not store.table_exists(cursor):
                return json_error('The database has not been upgraded to revision 0014.', 503, 'institutions_unavailable')
            return json_ok(_listing(cursor))
        except Exception:
            current_app.logger.exception('Institution list failed')
            return json_error(_MESSAGES['institutions_unavailable'], 500, 'institutions_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/institutions/organization', methods=['PUT'])
    def save_organization():
        denied = _change_denied()
        if denied is not None:
            return denied
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) - ORGANIZATION_FIELDS:
            return json_error(_MESSAGES['invalid_body'], 400, 'invalid_body')
        connection = cursor = None
        try:
            name = required_text(payload.get('name'), 150, 'organization_name_invalid')
            short_name = optional_text(payload.get('short_name', ''), 40, 'institution_short_name_invalid') or None
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            with transaction(connection):
                store.upsert_organization(cursor, name=name, short_name=short_name)
            return json_ok({'organization': _public_organization(store.fetch_organization(cursor))})
        except InputError as exc:
            return json_error(_MESSAGES.get(exc.code, _MESSAGES['invalid_body']), 400, exc.code)
        except Exception:
            current_app.logger.exception('Organization save failed')
            return json_error('The organization could not be saved.', 500, 'institutions_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/institutions', methods=['POST'])
    def create_institution():
        denied = _change_denied()
        if denied is not None:
            return denied
        return _save(None)

    @blueprint.route('/institutions/<int:institution_id>', methods=['PUT'])
    def update_institution(institution_id):
        denied = _change_denied()
        if denied is not None:
            return denied
        return _save(institution_id)

    @blueprint.route('/institutions/<int:institution_id>/members', methods=['GET'])
    def list_members(institution_id):
        denied = _view_denied()
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            if store.fetch_institution(cursor, institution_id) is None:
                return json_error(_MESSAGES['institution_not_found'], 404, 'institution_not_found')
            members = [{
                'user_id': safe_count(row.get('user_id')),
                'username': safe_text(row.get('username'), 80),
                'email': safe_text(row.get('email'), 150),
                'role': safe_text(row.get('role'), 50),
                'department_id': safe_count(row.get('department_id')) or None,
                'is_primary': bool(row.get('is_primary')),
            } for row in store.fetch_members(cursor, institution_id)]
            return json_ok({'members': members})
        except Exception:
            current_app.logger.exception('Institution members failed')
            return json_error(_MESSAGES['institutions_unavailable'], 500, 'institutions_unavailable')
        finally:
            close(cursor, connection)


def _save(institution_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - INSTITUTION_FIELDS:
        return json_error(_MESSAGES['invalid_body'], 400, 'invalid_body')
    connection = cursor = None
    try:
        values = _institution_input(payload, creating=institution_id is None)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if institution_id is not None and store.fetch_institution(cursor, institution_id) is None:
            return json_error(_MESSAGES['institution_not_found'], 404, 'institution_not_found')
        clash = store.fetch_institution_by_code(cursor, values['code'])
        if clash is not None and int(clash['id']) != (institution_id or 0):
            return json_error(_MESSAGES['institution_code_taken'], 400, 'institution_code_taken')
        if institution_id is None:
            from core.license import refuse_institution
            blocked = refuse_institution(cursor, current_app.config)
            if blocked:
                code, message = blocked
                return json_error(message, 409, code)
        if institution_id is not None and not values['is_active']:
            cursor.execute('SELECT COUNT(*) AS n FROM institutions WHERE is_active = 1 AND id <> %s', (institution_id,))
            if int(cursor.fetchone()['n']) == 0:
                return json_error(_MESSAGES['institution_last_active'], 400, 'institution_last_active')
        with transaction(connection):
            if institution_id is None:
                saved_id = store.insert_institution(cursor, **values)
            else:
                store.update_institution(cursor, institution_id, **values)
                saved_id = institution_id
        forget_scope()
        row = store.fetch_institution(cursor, saved_id)
        return json_ok(
            {'institution': _public_institution(row, store.institution_usage(cursor, saved_id))},
            201 if institution_id is None else 200,
        )
    except InputError as exc:
        return json_error(_MESSAGES.get(exc.code, _MESSAGES['invalid_body']), 400, exc.code)
    except IntegrityError:
        current_app.logger.exception('Institution save conflict')
        return json_error(_MESSAGES['institution_code_taken'], 400, 'institution_code_taken')
    except Exception:
        current_app.logger.exception('Institution save failed')
        return json_error(_MESSAGES['invalid_body'], 500, 'institutions_unavailable')
    finally:
        close(cursor, connection)
