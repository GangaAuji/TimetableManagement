"""Capabilities: the optional-feature switches for this tenant (docs/DESIGN_CAPABILITIES.md).

GET /api/capabilities                 every registered capability: flag, tenant state, effective, settings
PUT /api/capabilities/<name>          {"enabled": bool?, "settings": {...}?}

Reading needs capabilities_view or admin_view_settings. Changing needs capabilities_change or
admin_change_settings. The effective map every signed-in user needs is on GET /api/session.
"""

from flask import current_app, session

from api.web.access import InputError, allowed, body, close, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from core import capabilities
from extensions import get_db_connection
from security import log_activity

_MESSAGES = {
    'capabilities_unavailable': 'Capabilities could not be loaded.',
    'capability_invalid': 'Check the capability settings and try again.',
    'capability_unknown': 'That capability does not exist.',
    'capabilities_table_missing': 'The capabilities table is missing; apply the database migrations first.',
    'invalid_body': 'The request could not be accepted.',
}
_FIELDS = frozenset(('enabled', 'settings'))


def register_capability_routes(blueprint):
    blueprint.add_url_rule('/capabilities', 'capabilities_list', _list, methods=['GET'])
    blueprint.add_url_rule('/capabilities/<name>', 'capabilities_save', _save, methods=['PUT'])


def _view_denied():
    if allowed('capabilities_view') or allowed('admin_view_settings'):
        return None
    return permission_denied('capabilities_view', 'capabilities_unavailable', _MESSAGES['capabilities_unavailable'])


def _change_denied():
    if allowed('capabilities_change') or allowed('admin_change_settings'):
        return None
    return permission_denied('capabilities_change', 'capabilities_unavailable', _MESSAGES['capabilities_unavailable'])


def _payload(cursor):
    return {**capabilities.describe(cursor), 'can_change': allowed('capabilities_change') or allowed('admin_change_settings')}


def _list():
    denied = _view_denied()
    if denied:
        return denied
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        return json_ok(_payload(cursor))
    except Exception:
        current_app.logger.exception('Capabilities list failed')
        return json_error(_MESSAGES['capabilities_unavailable'], 500, 'capabilities_unavailable')
    finally:
        close(cursor, connection)


def _save(name):
    denied = _change_denied()
    if denied:
        return denied
    if not isinstance(name, str) or name not in capabilities.BY_NAME:
        return json_error(_MESSAGES['capability_unknown'], 404, 'capability_unknown')
    connection = cursor = None
    try:
        payload = body(_FIELDS)
        enabled_value = payload.get('enabled')
        if enabled_value is not None and not isinstance(enabled_value, bool):
            raise InputError('capability_invalid')
        settings_values = payload.get('settings')
        if settings_values is not None and not isinstance(settings_values, dict):
            raise InputError('capability_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            capabilities.save(
                cursor, name, enabled_value=enabled_value, settings_values=settings_values, updated_by=session.get('user_id'),
            )
        except ValueError as exc:
            raise InputError(str(exc))
        except RuntimeError:
            connection.rollback()
            return json_error(_MESSAGES['capabilities_table_missing'], 409, 'capabilities_table_missing')
        log_activity(
            session.get('user_id'), 'capability_changed', f'Capability {name} changed',
            entity_type='capability', entity_id=None,
            new_values={'capability': name, 'enabled': enabled_value, 'settings': settings_values},
            cursor=cursor,
        )
        connection.commit()
        capabilities.forget()
        return json_ok({'saved': True, **_payload(cursor)})
    except InputError as exc:
        if connection is not None:
            connection.rollback()
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Capability save failed')
        return json_error(_MESSAGES['capabilities_unavailable'], 500, 'capabilities_unavailable')
    finally:
        close(cursor, connection)
