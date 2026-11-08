"""Registered mobile devices. A new key is returned once and is not stored in the response again."""

import re

from flask import current_app, get_flashed_messages, session

from api.web.access import InputError, body, optional_id, optional_text, reject_input, required_text, whole_number
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from services.mobile_devices import create_mobile_device, list_mobile_devices, rotate_mobile_device, toggle_mobile_device

_MESSAGES = {
    'devices_unavailable': 'The page could not be loaded.',
    'invalid_body': 'The request could not be accepted.',
    'device_id_invalid': 'Enter a device ID using letters, numbers, . _ or -.',
    'device_rate_invalid': 'Rate limit must be between 10 and 1000 requests per minute.',
    'device_save_failed': 'The device could not be saved.',
    'device_missing': 'That device was not found.',
}
_DEVICE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
_DEVICE_ROLES = frozenset(('Admin', 'Super Admin'))


def register_device_routes(blueprint):
    blueprint.add_url_rule('/devices', 'devices_list', _list, methods=['GET'])
    blueprint.add_url_rule('/devices', 'devices_create', _create, methods=['POST'])
    blueprint.add_url_rule('/devices/<int:device_pk>/rotate', 'devices_rotate', _rotate, methods=['POST'])
    blueprint.add_url_rule('/devices/<int:device_pk>/toggle', 'devices_toggle', _toggle, methods=['POST'])


def _staff():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') not in _DEVICE_ROLES:
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    return None


def _take_secret():
    secret = session.pop('new_mobile_device_secret', None)
    session.pop('new_mobile_device_for', None)
    get_flashed_messages()
    return secret if isinstance(secret, str) and secret else ''


def device_form(payload):
    """Validate a new device. The key itself is created by the service."""
    device_id = required_text(payload.get('device_id'), 64, 'device_id_invalid')
    if not _DEVICE_ID.match(device_id):
        raise InputError('device_id_invalid')
    name = optional_text(payload.get('device_name'), 80, 'invalid_body')
    platform = optional_text(payload.get('platform'), 40, 'invalid_body')
    owner = optional_id(payload.get('owner_user_id'), 'invalid_body') if 'owner_user_id' in payload else None
    rate = whole_number(payload.get('rate_limit') if payload.get('rate_limit') not in (None, '') else 120, 1000, 'device_rate_invalid', lower=10)
    return device_id, name, platform, owner, rate


def device_row(row):
    return {
        'id': safe_count(row.get('id')),
        'device_id': safe_text(row.get('device_id') or '', 64),
        'name': safe_text(row.get('device_name') or '', 80),
        'platform': safe_text(row.get('platform') or '', 40),
        'owner': safe_text(row.get('owner_username') or '', 50),
        'rate_limit': safe_count(row.get('rate_limit_per_minute')) or 0,
        'is_active': bool(row.get('is_active')),
        'last_used': safe_stamp(row.get('last_used_at')),
        'created_at': safe_stamp(row.get('created_at')),
    }


def _list():
    denied = _staff()
    if denied:
        return denied
    try:
        devices, users = list_mobile_devices()
        owners = []
        for row in (users or [])[:500]:
            owners.append({
                'id': safe_count(row.get('id')),
                'username': safe_text(row.get('username') or '', 50),
            })
        return json_ok({'devices': [device_row(row) for row in devices or []], 'owners': owners})
    except Exception:
        current_app.logger.exception('Device list failed')
        return json_error(_MESSAGES['devices_unavailable'], 500, 'devices_unavailable')


def _create():
    denied = _staff()
    if denied:
        return denied
    try:
        payload = body(frozenset(('device_id', 'device_name', 'platform', 'owner_user_id', 'rate_limit')))
        device_id, name, platform, owner, rate = device_form(payload)
        created = create_mobile_device(device_id, name, platform, owner, rate, session)
        secret = _take_secret()
        if not created or not secret:
            return json_error(_MESSAGES['device_save_failed'], 500, 'device_save_failed')
        return json_ok({'saved': True, 'device_id': safe_text(device_id, 64), 'secret': secret})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        _take_secret()
        current_app.logger.exception('Device create failed')
        return json_error(_MESSAGES['device_save_failed'], 500, 'device_save_failed')


def _rotate(device_pk):
    denied = _staff()
    if denied:
        return denied
    try:
        body(frozenset())
        outcome = rotate_mobile_device(device_pk, session)
        secret = _take_secret()
        if outcome == 'missing':
            return json_error(_MESSAGES['device_missing'], 404, 'device_missing')
        if outcome != 'ok' or not secret:
            return json_error(_MESSAGES['device_save_failed'], 500, 'device_save_failed')
        return json_ok({'secret': secret})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        _take_secret()
        current_app.logger.exception('Device key rotation failed')
        return json_error(_MESSAGES['device_save_failed'], 500, 'device_save_failed')


def _toggle(device_pk):
    denied = _staff()
    if denied:
        return denied
    try:
        body(frozenset())
        outcome = toggle_mobile_device(device_pk)
        get_flashed_messages()
        if outcome == 'missing':
            return json_error(_MESSAGES['device_missing'], 404, 'device_missing')
        if outcome != 'ok':
            return json_error(_MESSAGES['device_save_failed'], 500, 'device_save_failed')
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        get_flashed_messages()
        current_app.logger.exception('Device status update failed')
        return json_error(_MESSAGES['device_save_failed'], 500, 'device_save_failed')
