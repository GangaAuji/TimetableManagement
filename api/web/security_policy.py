"""Security policy. Viewing needs security_policy_view or admin_view_settings.

Changing needs security_policy_change or admin_change_settings. The rules are
stored whether or not the capability is on; they are enforced only while
`security_policy` is on. An empty admin network list allows every address,
and a list that excludes the person saving it is refused.
"""

from flask import current_app, request, session

from api.web.access import InputError, allowed, body, close, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_text
from core.capabilities import enabled
from extensions import get_db_connection
from security import log_activity
from services.security_policy import DEFAULTS, ip_in_list, load, normalize_allowlist, table_ready

_MESSAGES = {
    'security_policy_unavailable': 'Apply the database upgrade before saving the security policy.',
    'security_policy_invalid': 'Check the security policy and try again.',
    'security_policy_lockout': 'Include the network you are using, or leave the list empty.',
    'invalid_body': 'The request could not be accepted.',
}
_FIELDS = frozenset((
    'min_length', 'max_length', 'require_upper', 'require_lower', 'require_digit', 'require_symbol',
    'expiry_days', 'idle_minutes', 'max_sessions', 'admin_ip_allowlist', 'sign_in_notice',
))


def register_security_policy_routes(blueprint):
    blueprint.add_url_rule('/security-policy', 'security_policy', _read, methods=['GET'])
    blueprint.add_url_rule('/security-policy', 'security_policy_save', _save, methods=['PUT'])


def _view_denied():
    if allowed('security_policy_view') or allowed('admin_view_settings'):
        return None
    return permission_denied('security_policy_view', 'security_policy_unavailable', _MESSAGES['security_policy_unavailable'])


def _change_denied():
    if allowed('security_policy_change') or allowed('admin_change_settings'):
        return None
    return permission_denied('security_policy_change', 'security_policy_unavailable', _MESSAGES['security_policy_unavailable'])


def _flag(value):
    return value if isinstance(value, bool) else None


def _number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or value < low or value > high:
        return None
    return value


def _clean(payload):
    min_length = _number(payload.get('min_length'), 8, 64)
    max_length = _number(payload.get('max_length'), 8, 128)
    expiry_days = _number(payload.get('expiry_days'), 0, 365)
    idle_minutes = _number(payload.get('idle_minutes'), 0, 720)
    max_sessions = _number(payload.get('max_sessions'), 0, 20)
    flags = [_flag(payload.get(name)) for name in ('require_upper', 'require_lower', 'require_digit', 'require_symbol', 'sign_in_notice')]
    allowlist = payload.get('admin_ip_allowlist')
    if not isinstance(allowlist, str) or len(allowlist) > 2000:
        raise InputError('security_policy_invalid')
    normalized = normalize_allowlist(allowlist)
    if None in (min_length, max_length, expiry_days, idle_minutes, max_sessions, normalized) or None in flags or max_length < min_length:
        raise InputError('security_policy_invalid')
    if normalized and not ip_in_list(request.remote_addr, normalized):
        raise InputError('security_policy_lockout')
    return {
        'min_length': min_length,
        'max_length': max_length,
        'require_upper': flags[0],
        'require_lower': flags[1],
        'require_digit': flags[2],
        'require_symbol': flags[3],
        'expiry_days': expiry_days,
        'idle_minutes': idle_minutes,
        'max_sessions': max_sessions,
        'admin_ip_allowlist': normalized,
        'sign_in_notice': flags[4],
    }


def _public(rules, ready):
    source = rules or DEFAULTS
    return {
        'ready': ready,
        'enabled': False,
        'can_change': allowed('security_policy_change') or allowed('admin_change_settings'),
        'current_ip': safe_text(request.remote_addr, 45),
        'settings': {
            'min_length': source['min_length'],
            'max_length': source['max_length'],
            'require_upper': source['require_upper'],
            'require_lower': source['require_lower'],
            'require_digit': source['require_digit'],
            'require_symbol': source['require_symbol'],
            'expiry_days': source['expiry_days'],
            'idle_minutes': source['idle_minutes'],
            'max_sessions': source['max_sessions'],
            'admin_ip_allowlist': source['admin_ip_allowlist'],
            'sign_in_notice': source['sign_in_notice'],
        },
    }


def _read():
    denied = _view_denied()
    if denied:
        return denied
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        ready = table_ready(cursor)
        payload = _public(load(cursor) if ready else None, ready)
        payload['enabled'] = enabled(cursor, 'security_policy')
        return json_ok(payload)
    except Exception:
        current_app.logger.exception('Security policy could not be loaded')
        return json_error(_MESSAGES['security_policy_unavailable'], 500, 'security_policy_unavailable')
    finally:
        close(cursor, connection)


def _save():
    denied = _change_denied()
    if denied:
        return denied
    connection = cursor = None
    try:
        values = _clean(body(_FIELDS))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not table_ready(cursor):
            return json_error(_MESSAGES['security_policy_unavailable'], 409, 'security_policy_unavailable')
        cursor.execute(
            """
            INSERT INTO security_settings (
                id, min_length, max_length, require_upper, require_lower, require_digit, require_symbol,
                expiry_days, idle_minutes, max_sessions, admin_ip_allowlist, sign_in_notice
            ) VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                min_length = VALUES(min_length), max_length = VALUES(max_length),
                require_upper = VALUES(require_upper), require_lower = VALUES(require_lower),
                require_digit = VALUES(require_digit), require_symbol = VALUES(require_symbol),
                expiry_days = VALUES(expiry_days), idle_minutes = VALUES(idle_minutes),
                max_sessions = VALUES(max_sessions), admin_ip_allowlist = VALUES(admin_ip_allowlist),
                sign_in_notice = VALUES(sign_in_notice)
            """,
            (
                values['min_length'], values['max_length'],
                1 if values['require_upper'] else 0, 1 if values['require_lower'] else 0,
                1 if values['require_digit'] else 0, 1 if values['require_symbol'] else 0,
                values['expiry_days'], values['idle_minutes'], values['max_sessions'],
                values['admin_ip_allowlist'] or None, 1 if values['sign_in_notice'] else 0,
            ),
        )
        log_activity(session.get('user_id'), 'security_policy_change', 'Updated the security policy', cursor=cursor)
        connection.commit()
        payload = _public(load(cursor), True)
        payload['enabled'] = enabled(cursor, 'security_policy')
        return json_ok(payload)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Security policy could not be saved')
        return json_error(_MESSAGES['security_policy_unavailable'], 500, 'security_policy_unavailable')
    finally:
        close(cursor, connection)
