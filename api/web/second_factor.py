"""Profile enrollment for an authenticator app. Sign-in itself stays on routes/auth.py.

The secret and the recovery codes are returned once, in the response to the
person who just proved their password or their current code. They are not
written to the audit log.
"""

from flask import current_app, session

from api.web.access import InputError, body, close, reject_input, required_text
from api.web.responses import json_error, json_ok
from extensions import get_db_connection
from security import log_activity
from security.passwords import password_matches
from services.second_factor import TABLE, FactorRejected
from services import second_factor as factor
from core import capabilities

_MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'account_unavailable': 'The page could not be loaded.',
    'account_password_mismatch': 'The current password is incorrect.',
    'capability_off': 'This feature is switched off for your institution.',
    'second_factor_unavailable': 'Second factor is not available until the database migration is applied.',
    'second_factor_invalid': 'That code was not accepted.',
    'second_factor_enrolled': 'An authenticator is already set up.',
    'second_factor_required': 'Your role must keep an authenticator app.',
}


def register_second_factor_routes(blueprint):
    blueprint.add_url_rule('/account/second-factor', 'second_factor_view', _view, methods=['GET'])
    blueprint.add_url_rule('/account/second-factor', 'second_factor_start', _start, methods=['POST'])
    blueprint.add_url_rule('/account/second-factor/confirm', 'second_factor_confirm', _confirm, methods=['POST'])
    blueprint.add_url_rule('/account/second-factor/replace', 'second_factor_replace', _replace, methods=['POST'])
    blueprint.add_url_rule('/account/second-factor/recovery', 'second_factor_recovery', _recovery, methods=['POST'])
    blueprint.add_url_rule('/account/second-factor/disable', 'second_factor_disable', _disable, methods=['POST'])


def _signed_in():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    return None


def _user_id():
    raw = session.get('user_id')
    if isinstance(raw, bool):
        return None
    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        return None
    return user_id if user_id > 0 else None


def _role():
    role = session.get('role')
    return role if isinstance(role, str) else ''


def _username():
    username = session.get('username')
    return username if isinstance(username, str) and username else 'user'


def _rollback(connection):
    if connection is not None:
        try:
            connection.rollback()
        except Exception:
            pass


def _open():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _gate(cursor):
    if not capabilities.flag_on('two_factor') or not capabilities.enabled(cursor, 'two_factor'):
        return json_error(_MESSAGES['capability_off'], 404, 'capability_off')
    if not capabilities.table_exists(cursor, TABLE):
        return json_error(_MESSAGES['second_factor_unavailable'], 409, 'second_factor_unavailable')
    return None


def _password_ok(cursor, user_id, password):
    cursor.execute('SELECT password FROM users WHERE id = %s', (user_id,))
    row = cursor.fetchone()
    if not row:
        return False
    try:
        return bool(password_matches(row.get('password') or '', password))
    except Exception:
        current_app.logger.exception('Second factor could not check the password')
        return False


def _code(payload):
    return required_text(payload.get('code'), 32, 'second_factor_invalid')


def _view():
    denied = _signed_in()
    if denied:
        return denied
    connection = cursor = None
    try:
        connection, cursor = _open()
        return json_ok(factor.status(cursor, _user_id(), _role()))
    except Exception:
        current_app.logger.exception('Second factor status failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    finally:
        close(cursor, connection)


def _start():
    """Begin enrollment. The current password is required; the secret is returned once."""
    denied = _signed_in()
    if denied:
        return denied
    connection = cursor = None
    try:
        payload = body(frozenset(('current_password',)))
        password = required_text(payload.get('current_password'), 128, 'account_password_mismatch')
        user_id = _user_id()
        if user_id is None:
            return json_error(_MESSAGES['account_unavailable'], 401, 'unauthorized')
        connection, cursor = _open()
        gated = _gate(cursor)
        if gated:
            return gated
        if not _password_ok(cursor, user_id, password):
            return json_error(_MESSAGES['account_password_mismatch'], 400, 'account_password_mismatch')
        started = factor.begin(cursor, user_id, _username())
        if started == 'confirmed':
            _rollback(connection)
            return json_error(_MESSAGES['second_factor_enrolled'], 409, 'second_factor_enrolled')
        if not started:
            _rollback(connection)
            return json_error(_MESSAGES['second_factor_unavailable'], 409, 'second_factor_unavailable')
        log_activity(user_id, 'second_factor_enrollment_started', 'Authenticator enrollment started', cursor=cursor)
        connection.commit()
        return json_ok(started)
    except InputError as exc:
        _rollback(connection)
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        _rollback(connection)
        current_app.logger.exception('Second factor enrollment failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    finally:
        close(cursor, connection)


def _confirm():
    denied = _signed_in()
    if denied:
        return denied
    connection = cursor = None
    try:
        payload = body(frozenset(('code',)))
        code = _code(payload)
        user_id = _user_id()
        if user_id is None:
            return json_error(_MESSAGES['account_unavailable'], 401, 'unauthorized')
        connection, cursor = _open()
        gated = _gate(cursor)
        if gated:
            return gated
        codes = factor.confirm(cursor, user_id, code)
        if not codes:
            _rollback(connection)
            return json_error(_MESSAGES['second_factor_invalid'], 400, 'second_factor_invalid')
        log_activity(user_id, 'second_factor_enrolled', 'Authenticator enrolled', cursor=cursor)
        connection.commit()
        return json_ok({'recovery_codes': codes})
    except InputError as exc:
        _rollback(connection)
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        _rollback(connection)
        current_app.logger.exception('Second factor confirmation failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    finally:
        close(cursor, connection)


def _replace():
    denied = _signed_in()
    if denied:
        return denied
    connection = cursor = None
    try:
        payload = body(frozenset(('code',)))
        code = _code(payload)
        user_id = _user_id()
        if user_id is None:
            return json_error(_MESSAGES['account_unavailable'], 401, 'unauthorized')
        connection, cursor = _open()
        gated = _gate(cursor)
        if gated:
            return gated
        shown = factor.start_replace(cursor, user_id, _username(), code)
        if not shown:
            _rollback(connection)
            return json_error(_MESSAGES['second_factor_invalid'], 400, 'second_factor_invalid')
        connection.commit()
        return json_ok(shown)
    except InputError as exc:
        _rollback(connection)
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        _rollback(connection)
        current_app.logger.exception('Second factor replacement failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    finally:
        close(cursor, connection)


def _recovery():
    denied = _signed_in()
    if denied:
        return denied
    connection = cursor = None
    try:
        payload = body(frozenset(('code',)))
        code = _code(payload)
        user_id = _user_id()
        if user_id is None:
            return json_error(_MESSAGES['account_unavailable'], 401, 'unauthorized')
        connection, cursor = _open()
        gated = _gate(cursor)
        if gated:
            return gated
        codes = factor.regenerate(cursor, user_id, code)
        if not codes:
            _rollback(connection)
            return json_error(_MESSAGES['second_factor_invalid'], 400, 'second_factor_invalid')
        log_activity(user_id, 'second_factor_recovery', 'Recovery codes replaced', cursor=cursor)
        connection.commit()
        return json_ok({'recovery_codes': codes})
    except InputError as exc:
        _rollback(connection)
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        _rollback(connection)
        current_app.logger.exception('Second factor recovery codes failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    finally:
        close(cursor, connection)


def _disable():
    denied = _signed_in()
    if denied:
        return denied
    connection = cursor = None
    try:
        payload = body(frozenset(('current_password', 'code')))
        password = required_text(payload.get('current_password'), 128, 'account_password_mismatch')
        code = _code(payload)
        user_id = _user_id()
        if user_id is None:
            return json_error(_MESSAGES['account_unavailable'], 401, 'unauthorized')
        connection, cursor = _open()
        gated = _gate(cursor)
        if gated:
            return gated
        if not _password_ok(cursor, user_id, password):
            return json_error(_MESSAGES['account_password_mismatch'], 400, 'account_password_mismatch')
        factor.disable(cursor, user_id, _role(), code)
        log_activity(user_id, 'second_factor_disabled', 'Authenticator removed', cursor=cursor)
        connection.commit()
        return json_ok({'saved': True})
    except FactorRejected as exc:
        _rollback(connection)
        return reject_input(_MESSAGES, exc.code)
    except InputError as exc:
        _rollback(connection)
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        _rollback(connection)
        current_app.logger.exception('Second factor removal failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    finally:
        close(cursor, connection)
