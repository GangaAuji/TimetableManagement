"""Tenant security policy (password rules, session limits, admin networks, sign-in notices).

The capability `security_policy` is off by default. While it is off, or revision
`0025_security_policy` has not been applied, every function here returns without
writing and without changing sign-in. Callers keep the checks they already had.
"""

import ipaddress
from datetime import datetime, timedelta

from flask import current_app, has_request_context, request, session

from core.capabilities import enabled, flag_on
from extensions import get_db_connection

TABLE = 'security_settings'
CAPABILITY = 'security_policy'
ADMIN_ROLES = frozenset(('Admin', 'Super Admin', 'HOD'))
_OPEN_WHEN_EXPIRED = frozenset(('/api/account/password', '/api/session/logout'))

DEFAULTS = {
    'min_length': 8,
    'max_length': 128,
    'require_upper': False,
    'require_lower': False,
    'require_digit': False,
    'require_symbol': False,
    'expiry_days': 0,
    'idle_minutes': 0,
    'max_sessions': 0,
    'admin_ip_allowlist': '',
    'sign_in_notice': False,
}


def _column_ready(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def table_ready(cursor):
    cursor.execute(
        """
        SELECT 1 FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        LIMIT 1
        """,
        (TABLE,),
    )
    return cursor.fetchone() is not None


def load(cursor):
    """The saved row, or the historical defaults when the row is missing. None when the table is missing."""
    if not table_ready(cursor):
        return None
    cursor.execute(
        """
        SELECT min_length, max_length, require_upper, require_lower, require_digit, require_symbol,
               expiry_days, idle_minutes, max_sessions, admin_ip_allowlist, sign_in_notice
        FROM security_settings WHERE id = 1
        """
    )
    row = cursor.fetchone()
    if not row:
        return dict(DEFAULTS)
    values = dict(DEFAULTS)
    values['min_length'] = int(row['min_length'])
    values['max_length'] = int(row['max_length'])
    values['require_upper'] = bool(row['require_upper'])
    values['require_lower'] = bool(row['require_lower'])
    values['require_digit'] = bool(row['require_digit'])
    values['require_symbol'] = bool(row['require_symbol'])
    values['expiry_days'] = int(row['expiry_days'])
    values['idle_minutes'] = int(row['idle_minutes'])
    values['max_sessions'] = int(row['max_sessions'])
    values['admin_ip_allowlist'] = (row.get('admin_ip_allowlist') or '').strip()
    values['sign_in_notice'] = bool(row['sign_in_notice'])
    return values


def _active(cursor):
    """Saved rules when the capability is on and the table exists. None leaves today's checks in place.

    Returns before any SQL when the server flag is off, including outside an application context.
    """
    if not flag_on(CAPABILITY):
        return None
    try:
        if not enabled(cursor, CAPABILITY):
            return None
        return load(cursor)
    except Exception:
        current_app.logger.exception('Security policy could not be read')
        return None


def _with_cursor(cursor):
    if cursor is not None:
        return cursor, None, None
    connection = get_db_connection()
    return connection.cursor(dictionary=True), connection, True


def enforced_problem(password, cursor=None):
    """'policy' when the capability is on and the password misses a saved rule. None otherwise.

    None means the caller keeps its existing length check. This does not query while the capability is off.
    """
    if not isinstance(password, str) or not flag_on(CAPABILITY):
        return None
    local = None
    owned = None
    try:
        local, owned, _close = _with_cursor(cursor)
        rules = _active(local)
    except Exception:
        current_app.logger.exception('Security policy could not check a password')
        rules = None
    finally:
        if owned is not None:
            local.close()
            owned.close()
    if not rules:
        return None
    length = len(password)
    if length < rules['min_length'] or length > rules['max_length']:
        return 'policy'
    if rules['require_upper'] and not any(character.isupper() for character in password):
        return 'policy'
    if rules['require_lower'] and not any(character.islower() for character in password):
        return 'policy'
    if rules['require_digit'] and not any(character.isdigit() for character in password):
        return 'policy'
    if rules['require_symbol'] and not any(not character.isalnum() for character in password):
        return 'policy'
    return None


def remember_password_change(cursor, user_id):
    """Stamp when this password was set, once the policy column exists. No-op while the capability is off."""
    if not flag_on(CAPABILITY) or user_id is None:
        return
    try:
        if not _column_ready(cursor, 'users', 'password_changed_at'):
            return
        cursor.execute('UPDATE users SET password_changed_at = NOW() WHERE id = %s', (user_id,))
        if has_request_context() and session.get('user_id') == user_id:
            session.pop('password_expired', None)
    except Exception:
        current_app.logger.exception('Could not record when the password changed')


def networks(text):
    """Parsed networks, or None when a line is not an address or a network."""
    found = []
    for raw in (text or '').replace(',', '\n').splitlines():
        piece = raw.strip()
        if not piece or piece.startswith('#'):
            continue
        if len(found) >= 40 or len(piece) > 50:
            return None
        try:
            if '/' not in piece:
                address = ipaddress.ip_address(piece)
                piece = f'{address}/{32 if address.version == 4 else 128}'
            found.append(ipaddress.ip_network(piece, strict=False))
        except ValueError:
            return None
    return found


def ip_in_list(ip_address, text):
    """True when the list is empty or contains the address. A list that cannot be parsed allows the address."""
    parsed = networks(text)
    if not parsed:
        return True
    try:
        address = ipaddress.ip_address((ip_address or '').strip())
    except ValueError:
        return False
    return any(address in network for network in parsed)


def normalize_allowlist(text):
    """One network per line, or None when a line is not an address or a network."""
    parsed = networks(text)
    if parsed is None:
        return None
    return '\n'.join(str(network) for network in parsed)


def admin_ip_ok(cursor, ip_address):
    """True when this address may open an admin session. True while the policy is off or the list is empty."""
    rules = _active(cursor)
    if not rules or not rules['admin_ip_allowlist']:
        return True
    return ip_in_list(ip_address, rules['admin_ip_allowlist'])


def _trim_sessions(cursor, user_id, limit):
    cursor.execute(
        'SELECT id FROM user_sessions WHERE user_id = %s AND is_active = 1 ORDER BY id DESC',
        (user_id,),
    )
    extra = [row['id'] for row in cursor.fetchall()][limit:]
    if not extra:
        return
    marks = ','.join(['%s'] * len(extra))
    cursor.execute(f'UPDATE user_sessions SET is_active = 0 WHERE id IN ({marks})', tuple(extra))


def _notify(cursor, user, ip_address, session_id):
    from services import notifications

    if not notifications.table_exists(cursor):
        return
    if not notifications.load_settings(cursor).get('enabled'):
        return
    when = datetime.now().strftime('%Y-%m-%d %H:%M')
    address = (ip_address or 'an unknown address').strip()
    notifications.enqueue(
        cursor,
        kind='sign_in',
        subject='New sign-in to your timetable account',
        body=f'A sign-in to your timetable account succeeded at {when} from {address}.',
        recipient_user_id=user['id'],
        dedupe_key=f'sign_in:{session_id}',
    )


def apply_sign_in(cursor, user, ip_address, flask_session, session_id):
    """Apply session limits and the sign-in notice on the login transaction. No-op while the policy is off."""
    rules = _active(cursor)
    if not rules:
        return
    try:
        if rules['max_sessions'] > 0:
            _trim_sessions(cursor, user['id'], rules['max_sessions'])
            flask_session['policy_session'] = True
        if rules['idle_minutes'] > 0:
            flask_session['policy_idle'] = int(rules['idle_minutes'])
            flask_session['policy_session'] = True
        if rules['admin_ip_allowlist'] and user.get('role') in ADMIN_ROLES:
            flask_session['policy_admin_ip'] = True
        if rules['expiry_days'] > 0 and _column_ready(cursor, 'users', 'password_changed_at'):
            cursor.execute('SELECT password_changed_at FROM users WHERE id = %s', (user['id'],))
            row = cursor.fetchone() or {}
            changed = row.get('password_changed_at')
            if isinstance(changed, datetime) and datetime.now() - changed > timedelta(days=rules['expiry_days']):
                flask_session['password_expired'] = True
        if rules['sign_in_notice']:
            _notify(cursor, user, ip_address, session_id)
    except Exception:
        current_app.logger.exception('Security policy could not be applied to this sign-in')


def _release_flags():
    session.pop('policy_session', None)
    session.pop('policy_idle', None)
    session.pop('policy_admin_ip', None)
    session.pop('password_expired', None)


def request_block():
    """A JSON denial when this signed-in request breaks an active policy, or None to continue.

    Sessions opened while the policy was off carry no flag, so this returns before any SQL.
    """
    if not session.get('policy_session') and not session.get('policy_admin_ip') and not session.get('password_expired'):
        return None
    if not flag_on(CAPABILITY):
        _release_flags()
        return None
    from api.web.responses import json_error

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        rules = _active(cursor)
        if not rules:
            _release_flags()
            return None
        path = (request.path or '/').rstrip('/') or '/'
        if session.get('policy_admin_ip') and session.get('role') in ADMIN_ROLES and rules['admin_ip_allowlist']:
            if not ip_in_list(request.remote_addr, rules['admin_ip_allowlist']):
                session.clear()
                return json_error('Sign-in is not allowed from this network.', 401, 'admin_network')
        if session.get('policy_session'):
            session_id = session.get('session_id')
            if isinstance(session_id, str) and session_id:
                cursor.execute(
                    'SELECT is_active, last_activity FROM user_sessions WHERE session_id = %s',
                    (session_id,),
                )
                row = cursor.fetchone()
                if not row or not row.get('is_active'):
                    session.clear()
                    return json_error('Your session timed out. Sign in again.', 401, 'session_idle')
                idle = session.get('policy_idle')
                last = row.get('last_activity')
                if isinstance(idle, int) and not isinstance(idle, bool) and idle > 0 and isinstance(last, datetime):
                    if datetime.now() - last > timedelta(minutes=idle):
                        cursor.execute('UPDATE user_sessions SET is_active = 0 WHERE session_id = %s', (session_id,))
                        connection.commit()
                        session.clear()
                        return json_error('Your session timed out. Sign in again.', 401, 'session_idle')
                if isinstance(idle, int) and not isinstance(idle, bool) and idle > 0:
                    cursor.execute('UPDATE user_sessions SET last_activity = NOW() WHERE session_id = %s', (session_id,))
                    connection.commit()
        if session.get('password_expired') and path not in _OPEN_WHEN_EXPIRED:
            return json_error('Change your password to continue.', 403, 'password_expired')
        return None
    except Exception:
        current_app.logger.exception('Security policy could not check this request')
        if connection is not None:
            connection.rollback()
        return None
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
