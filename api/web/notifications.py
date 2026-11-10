"""Notification settings (per tenant SMTP account and trigger switches) and the outbox view.

GET  /api/notifications/settings   settings without the password, delivery status, queue counts
PUT  /api/notifications/settings   save; `smtp_password` sets a new one, `clear_password` removes it
POST /api/notifications/test       queue a test message to an address
GET  /api/notifications            the most recent outbox rows
"""

import re

from flask import current_app, session

from api.web.access import InputError, allowed, body, close, optional_text, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from extensions import get_db_connection
from security import log_activity
from services import notifications

_MESSAGES = {
    'notifications_unavailable': 'Notification settings could not be loaded.',
    'notifications_invalid': 'Check the SMTP fields and try again.',
    'notifications_no_key': 'The SMTP password cannot be stored: no encryption key is configured on the server.',
    'invalid_body': 'The request could not be accepted.',
}
_FIELDS = frozenset((*notifications.SETTING_FIELDS, 'smtp_password', 'clear_password'))
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_SWITCHES = frozenset(('enabled', 'smtp_starttls', *notifications.SWITCHES))


def register_notification_routes(blueprint):
    blueprint.add_url_rule('/notifications/settings', 'notification_settings', _settings, methods=['GET'])
    blueprint.add_url_rule('/notifications/settings', 'notification_settings_save', _save, methods=['PUT'])
    blueprint.add_url_rule('/notifications/test', 'notification_test', _test, methods=['POST'])
    blueprint.add_url_rule('/notifications', 'notification_list', _list, methods=['GET'])


def _view_denied():
    if allowed('notifications_view') or allowed('admin_view_settings'):
        return None
    return permission_denied('notifications_view', 'notifications_unavailable', _MESSAGES['notifications_unavailable'])


def _change_denied():
    if allowed('notifications_change') or allowed('admin_change_settings'):
        return None
    return permission_denied('notifications_change', 'notifications_unavailable', _MESSAGES['notifications_unavailable'])


def _public(settings):
    return {
        'enabled': bool(settings.get('enabled')),
        'smtp_host': safe_text(settings.get('smtp_host') or '', 190),
        'smtp_port': safe_count(settings.get('smtp_port')) or None,
        'smtp_user': safe_text(settings.get('smtp_user') or '', 190),
        'smtp_from': safe_text(settings.get('smtp_from') or '', 190),
        'smtp_starttls': bool(settings.get('smtp_starttls', True)),
        'reply_to': safe_text(settings.get('reply_to') or '', 190),
        'has_password': bool(settings.get('has_password')),
        **{switch: bool(settings.get(switch, True)) for switch in notifications.SWITCHES},
    }


def _payload(cursor):
    settings = notifications.load_settings(cursor)
    return {
        'settings': _public(settings),
        'status': notifications.status(cursor),
        'can_change': allowed('notifications_change') or allowed('admin_change_settings'),
    }


def _settings():
    denied = _view_denied()
    if denied:
        return denied
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        return json_ok(_payload(cursor))
    except Exception:
        current_app.logger.exception('Notification settings failed')
        return json_error(_MESSAGES['notifications_unavailable'], 500, 'notifications_unavailable')
    finally:
        close(cursor, connection)


def _clean(payload):
    values = {}
    for key in ('smtp_host', 'smtp_user', 'smtp_from', 'reply_to'):
        if key in payload:
            values[key] = optional_text(payload.get(key), 190, 'notifications_invalid') or None
    for key in ('smtp_from', 'reply_to'):
        if values.get(key) and not _EMAIL.match(values[key]):
            raise InputError('notifications_invalid')
    if 'smtp_port' in payload:
        port = payload.get('smtp_port')
        if port in (None, ''):
            values['smtp_port'] = None
        else:
            if isinstance(port, bool) or not isinstance(port, (int, str)) or not str(port).isdigit() or not 1 <= int(port) <= 65535:
                raise InputError('notifications_invalid')
            values['smtp_port'] = int(port)
    for key in _SWITCHES:
        if key in payload:
            if not isinstance(payload[key], bool):
                raise InputError('notifications_invalid')
            values[key] = payload[key]
    password = payload.get('smtp_password')
    if password is not None and (not isinstance(password, str) or len(password) > 200):
        raise InputError('notifications_invalid')
    clear = payload.get('clear_password')
    if clear is not None and not isinstance(clear, bool):
        raise InputError('notifications_invalid')
    return values, (password or None), bool(clear)


def _save():
    denied = _change_denied()
    if denied:
        return denied
    connection = cursor = None
    try:
        values, password, clear = _clean(body(_FIELDS))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            notifications.save_settings(cursor, values, session.get('user_id'), password=password, clear_password=clear)
        except RuntimeError:
            connection.rollback()
            return json_error(_MESSAGES['notifications_no_key'], 400, 'notifications_no_key')
        log_activity(
            session.get('user_id'), 'notification_settings_changed', 'Notification settings changed',
            entity_type='notification_settings', entity_id=1,
            new_values={key: value for key, value in values.items() if key != 'smtp_password'} | {'password_changed': bool(password or clear)},
            cursor=cursor,
        )
        connection.commit()
        return json_ok({'saved': True, **_payload(cursor)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Notification settings save failed')
        return json_error(_MESSAGES['notifications_unavailable'], 500, 'notifications_unavailable')
    finally:
        close(cursor, connection)


def _test():
    denied = _change_denied()
    if denied:
        return denied
    connection = cursor = None
    try:
        payload = body(frozenset(('to',)))
        to = optional_text(payload.get('to'), 190, 'notifications_invalid')
        if not to or not _EMAIL.match(to):
            raise InputError('notifications_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        queued_id = notifications.queue_test_message(cursor, to=to, user_id=session.get('user_id'))
        connection.commit()
        return json_ok({'queued': bool(queued_id), 'id': safe_count(queued_id), 'status': notifications.status(cursor)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Notification test failed')
        return json_error(_MESSAGES['notifications_unavailable'], 500, 'notifications_unavailable')
    finally:
        close(cursor, connection)


def _list():
    denied = _view_denied()
    if denied:
        return denied
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        rows = notifications.recent(cursor, limit=200) if notifications.table_exists(cursor) else []
        return json_ok({
            'notifications': [
                {
                    'id': safe_count(row['id']), 'kind': safe_text(row['kind'], 40),
                    'recipient_email': safe_text(row.get('recipient_email') or '', 190),
                    'subject': safe_text(row.get('subject') or '', 200), 'status': safe_text(row['status'], 20),
                    'attempts': safe_count(row.get('attempts')), 'last_error': safe_text(row.get('last_error') or '', 200),
                    'created_at': safe_stamp(row.get('created_at')), 'sent_at': safe_stamp(row.get('sent_at')),
                }
                for row in rows
            ],
            'status': notifications.status(cursor),
        })
    except Exception:
        current_app.logger.exception('Notification list failed')
        return json_error(_MESSAGES['notifications_unavailable'], 500, 'notifications_unavailable')
    finally:
        close(cursor, connection)
