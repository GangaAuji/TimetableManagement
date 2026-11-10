"""Authenticator enrollment, the sign-in code, and one-time recovery codes.

The capability is `two_factor`. While it is off, or while `user_second_factors`
is missing, every function here leaves sign-in alone. The base32 secret is
stored only as a Fernet token. Recovery codes are stored only as hashes and
returned in plaintext once, to the person who just confirmed them.

A password that is correct does not open a session when a code is still
required. The pending sign-in lives in the signed session cookie under
``pending_2fa`` and expires after five minutes. It never carries the secret.
"""

import json
import re
import time

from flask import current_app, has_app_context

from core import capabilities
from services import totp
from services.secrets_at_rest import decrypt_text, encrypt_text

TABLE = 'user_second_factors'
PENDING_KEY = 'pending_2fa'
PENDING_SECONDS = 300
SETUP_SECONDS = 600
MAX_ATTEMPTS = 5
ADMIN_ROLES = frozenset({'Super Admin', 'Admin', 'HOD'})
_AMR = frozenset({'mfa', 'otp', 'totp', 'hwk', 'sms'})

_ROW = """
SELECT user_id, secret_enc, next_secret_enc, confirmed_at, last_step, recovery_hashes,
       TIMESTAMPDIFF(SECOND, created_at, NOW()) AS age_seconds,
       TIMESTAMPDIFF(SECOND, next_secret_at, NOW()) AS next_age
FROM user_second_factors WHERE user_id = %s
"""


class FactorRejected(Exception):
    def __init__(self, code):
        self.code = code


def role_requires(mode, role):
    """Whether this role must enroll before a session opens."""
    if mode == 'everyone':
        return True
    if mode == 'staff':
        return role in ADMIN_ROLES
    return False


def idp_asserts_mfa(claims):
    """True when the identity provider says it already performed a second factor."""
    if not isinstance(claims, dict):
        return False
    amr = claims.get('amr')
    if isinstance(amr, (list, tuple)) and any(str(item).lower() in _AMR for item in amr):
        return True
    acr = claims.get('acr')
    return isinstance(acr, str) and 'mfa' in acr.lower()


def active(cursor):
    """The feature is on and its table is present. Any lookup error is off."""
    if not capabilities.flag_on('two_factor'):
        return False
    try:
        if not capabilities.enabled(cursor, 'two_factor'):
            return False
        return capabilities.table_exists(cursor, TABLE)
    except Exception:
        if has_app_context():
            current_app.logger.exception('Second factor check failed')
        return False


def must_enroll(cursor, role):
    if not active(cursor):
        return False
    mode = capabilities.settings(cursor, 'two_factor').get('required', 'optional')
    return role_requires(mode, role)


def _fetch(cursor, user_id):
    cursor.execute(_ROW, (int(user_id),))
    return cursor.fetchone()


def _age(row):
    try:
        return int(row.get('age_seconds') or 0)
    except (TypeError, ValueError):
        return SETUP_SECONDS + 1


def _last_step(row):
    value = row.get('last_step') if row else None
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hash_list(raw):
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str)], json.dumps(raw, separators=(',', ':'))
    if not isinstance(raw, str) or not raw:
        return [], '[]'
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return [], raw
    if not isinstance(parsed, list):
        return [], raw
    return [item for item in parsed if isinstance(item, str)], raw


def issuer_name():
    raw = ''
    if has_app_context():
        value = current_app.config.get('INSTITUTION_SHORT_NAME')
        if isinstance(value, str):
            raw = value.strip()
    cleaned = ''.join(ch for ch in raw if ch.isascii() and (ch.isalnum() or ch in ' -'))[:40].strip()
    return cleaned or 'Timetable'


def _shown(secret, username):
    account = totp.account_name(username)
    return {
        'secret': secret,
        'otpauth_uri': totp.otpauth_uri(secret, account, issuer_name()),
        'account': account,
    }


def begin(cursor, user_id, username):
    """Store a new unconfirmed secret. ``'confirmed'`` when one is already active."""
    row = _fetch(cursor, user_id)
    if row and row.get('confirmed_at'):
        return 'confirmed'
    secret = totp.generate_secret()
    try:
        stored = encrypt_text(secret)
    except Exception:
        if has_app_context():
            current_app.logger.exception('Second factor secret could not be stored')
        return None
    if row:
        cursor.execute(
            """
            UPDATE user_second_factors
            SET secret_enc = %s, next_secret_enc = NULL, next_secret_at = NULL, recovery_hashes = '[]',
                confirmed_at = NULL, last_step = NULL, created_at = NOW()
            WHERE user_id = %s AND confirmed_at IS NULL
            """,
            (stored, int(user_id)),
        )
        if cursor.rowcount != 1:
            return 'confirmed' if (_fetch(cursor, user_id) or {}).get('confirmed_at') else None
    else:
        cursor.execute(
            """
            INSERT INTO user_second_factors (user_id, secret_enc, recovery_hashes, created_at)
            VALUES (%s, %s, '[]', NOW())
            """,
            (int(user_id), stored),
        )
    return _shown(secret, username)


def show_enrollment(cursor, user_id, username):
    """The unconfirmed secret, while it is still inside the setup window."""
    row = _fetch(cursor, user_id)
    if not row or row.get('confirmed_at') or _age(row) > SETUP_SECONDS:
        return None
    secret = decrypt_text(row.get('secret_enc'))
    if not secret or totp.decode_secret(secret) is None:
        return None
    return _shown(secret, username)


def prepare(cursor, user, username):
    """``None`` (sign in), ``totp``, ``enroll``, or ``failed`` (do not open a session)."""
    if not active(cursor):
        return None
    try:
        user_id = int(user['id'])
    except (TypeError, ValueError, KeyError):
        return None
    row = _fetch(cursor, user_id)
    if row and row.get('confirmed_at'):
        return 'totp'
    if not role_requires(capabilities.settings(cursor, 'two_factor').get('required', 'optional'), user.get('role')):
        return None
    started = begin(cursor, user_id, username)
    if started == 'confirmed':
        return 'totp'
    if not started:
        return 'failed'
    return 'enroll'


def sso_prepare(cursor, user, claims):
    """SSO skips the code only when the provider asserts it already did one."""
    if idp_asserts_mfa(claims):
        return None
    return prepare(cursor, user, user.get('username') or '')


def _confirm_secret(cursor, user_id, secret_enc, code, *, last_step=None):
    secret = decrypt_text(secret_enc)
    if not secret:
        return None
    step = totp.matching_step(secret, totp.normalize_totp(code) or '', time.time(), last_step=last_step)
    if step is None:
        return None
    codes = totp.new_recovery_codes()
    cursor.execute(
        """
        UPDATE user_second_factors
        SET secret_enc = %s, next_secret_enc = NULL, next_secret_at = NULL, confirmed_at = NOW(),
            last_step = %s, recovery_hashes = %s
        WHERE user_id = %s
        """,
        (secret_enc, step, json.dumps(totp.hash_recovery(codes), separators=(',', ':')), int(user_id)),
    )
    return codes if cursor.rowcount == 1 else None


def confirm(cursor, user_id, code):
    """Confirm a new authenticator. Returns the recovery codes once, or None."""
    row = _fetch(cursor, user_id)
    if not row:
        return None
    if row.get('next_secret_enc'):
        try:
            next_age = int(row.get('next_age'))
        except (TypeError, ValueError):
            next_age = SETUP_SECONDS + 1
        if next_age > SETUP_SECONDS:
            return None
        return _confirm_secret(cursor, user_id, row['next_secret_enc'], code, last_step=None)
    if row.get('confirmed_at') or _age(row) > SETUP_SECONDS:
        return None
    return _confirm_secret(cursor, user_id, row.get('secret_enc'), code, last_step=None)


def _burn_totp(cursor, row, code):
    secret = decrypt_text(row.get('secret_enc'))
    presented = totp.normalize_totp(code)
    if not secret or not presented:
        return False
    step = totp.matching_step(secret, presented, time.time(), last_step=_last_step(row))
    if step is None:
        return False
    cursor.execute(
        """
        UPDATE user_second_factors
        SET last_step = %s
        WHERE user_id = %s AND confirmed_at IS NOT NULL AND (last_step IS NULL OR last_step < %s)
        """,
        (step, int(row['user_id']), step),
    )
    return cursor.rowcount == 1


def _burn_recovery(cursor, row, code):
    hashes, raw = _hash_list(row.get('recovery_hashes'))
    kept = totp.match_recovery(hashes, code)
    if kept is None:
        return False
    cursor.execute(
        """
        UPDATE user_second_factors
        SET recovery_hashes = %s
        WHERE user_id = %s AND confirmed_at IS NOT NULL AND recovery_hashes = %s
        """,
        (json.dumps(kept, separators=(',', ':')), int(row['user_id']), raw),
    )
    return cursor.rowcount == 1


def _matches(cursor, row, code, *, burn_totp=True):
    presented = code if isinstance(code, str) else ''
    if totp.normalize_totp(presented):
        if not burn_totp:
            secret = decrypt_text(row.get('secret_enc'))
            return bool(secret and totp.matching_step(secret, totp.normalize_totp(presented), time.time(), last_step=_last_step(row)))
        return _burn_totp(cursor, row, presented)
    if _is_recovery(presented):
        return _burn_recovery(cursor, row, presented)
    return False


def _is_recovery(presented):
    if not isinstance(presented, str) or len(presented) > 32:
        return False
    compact = re.sub(r'[\s-]', '', presented)
    return bool(re.fullmatch(r'[0-9A-Fa-f]{8}', compact))


def accept_sign_in(cursor, user_id, code, *, burn_totp=True):
    """A confirmed authenticator code or a single-use recovery code."""
    row = _fetch(cursor, user_id)
    if not row or not row.get('confirmed_at'):
        return False
    return _matches(cursor, row, code, burn_totp=burn_totp)


def start_replace(cursor, user_id, username, code):
    """Prove the current factor, then stage a new secret. The old one keeps working."""
    row = _fetch(cursor, user_id)
    if not row or not row.get('confirmed_at'):
        return None
    if not _matches(cursor, row, code, burn_totp=False):
        return None
    if not totp.normalize_totp(code if isinstance(code, str) else ''):
        # A recovery code was consumed above. Reload so the hash list is current.
        row = _fetch(cursor, user_id)
    secret = totp.generate_secret()
    try:
        stored = encrypt_text(secret)
    except Exception:
        if has_app_context():
            current_app.logger.exception('Second factor secret could not be stored')
        return None
    cursor.execute(
        """
        UPDATE user_second_factors
        SET next_secret_enc = %s, next_secret_at = NOW()
        WHERE user_id = %s AND confirmed_at IS NOT NULL
        """,
        (stored, int(user_id)),
    )
    if cursor.rowcount != 1:
        return None
    return _shown(secret, username)


def regenerate(cursor, user_id, code):
    """Replace recovery codes after a current authenticator code. Returns them once."""
    row = _fetch(cursor, user_id)
    if not row or not row.get('confirmed_at'):
        return None
    if not totp.normalize_totp(code if isinstance(code, str) else '') or not _burn_totp(cursor, row, code):
        return None
    codes = totp.new_recovery_codes()
    cursor.execute(
        "UPDATE user_second_factors SET recovery_hashes = %s WHERE user_id = %s AND confirmed_at IS NOT NULL",
        (json.dumps(totp.hash_recovery(codes), separators=(',', ':')), int(user_id)),
    )
    return codes if cursor.rowcount == 1 else None


def disable(cursor, user_id, role, code):
    """Remove the factor. Refuses while the role is required to have one."""
    if role_requires(capabilities.settings(cursor, 'two_factor').get('required', 'optional'), role):
        raise FactorRejected('second_factor_required')
    if not accept_sign_in(cursor, user_id, code):
        raise FactorRejected('second_factor_invalid')
    cursor.execute(f'DELETE FROM {TABLE} WHERE user_id = %s', (int(user_id),))


def status(cursor, user_id, role):
    """What the profile page shows. ``active`` is false while the capability is off."""
    if not capabilities.flag_on('two_factor'):
        return {'active': False, 'ready': False, 'enrolled': False, 'required': False}
    try:
        enabled = capabilities.enabled(cursor, 'two_factor')
    except Exception:
        return {'active': False, 'ready': False, 'enrolled': False, 'required': False}
    if not enabled:
        return {'active': False, 'ready': False, 'enrolled': False, 'required': False}
    try:
        ready = capabilities.table_exists(cursor, TABLE)
    except Exception:
        ready = False
    if not ready:
        return {'active': True, 'ready': False, 'enrolled': False, 'required': False}
    role_name = role if isinstance(role, str) else ''
    required = role_requires(capabilities.settings(cursor, 'two_factor').get('required', 'optional'), role_name)
    enrolled = False
    try:
        user_key = int(user_id)
    except (TypeError, ValueError):
        user_key = 0
    if user_key > 0 and not isinstance(user_id, bool):
        row = _fetch(cursor, user_key)
        enrolled = bool(row and row.get('confirmed_at'))
    return {'active': True, 'ready': True, 'enrolled': enrolled, 'required': required}


def remember(session, user, username, step, via):
    """Record a password-proven sign-in that still needs a code. No secret is stored."""
    role = user.get('role') if isinstance(user.get('role'), str) else ''
    session[PENDING_KEY] = {
        'user_id': int(user['id']),
        'username': str(username)[:80],
        'role': role,
        'kind': 'admin' if role in ADMIN_ROLES else 'portal',
        'step': step,
        'via': via if via in ('password', 'sso') else 'password',
        'expires': int(time.time()) + PENDING_SECONDS,
        'attempts': 0,
    }


def clear_pending(session):
    session.pop(PENDING_KEY, None)


def read_pending(session):
    raw = session.get(PENDING_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        user_id = raw.get('user_id')
        if isinstance(user_id, bool):
            raise ValueError
        user_id = int(user_id)
        expires = int(raw.get('expires'))
        attempts = int(raw.get('attempts') or 0)
    except (TypeError, ValueError):
        clear_pending(session)
        return None
    username = raw.get('username')
    role = raw.get('role')
    step = raw.get('step')
    kind = raw.get('kind')
    via = raw.get('via')
    if (
        user_id < 1 or not isinstance(username, str) or not username
        or not isinstance(role, str) or step not in ('totp', 'enroll')
        or kind not in ('admin', 'portal') or via not in ('password', 'sso')
        or attempts < 0 or expires < int(time.time())
    ):
        clear_pending(session)
        return None
    return {
        'user_id': user_id, 'username': username, 'role': role, 'kind': kind,
        'step': step, 'via': via, 'expires': expires, 'attempts': attempts,
    }


def save_attempts(session, pending, attempts):
    session[PENDING_KEY] = {**pending, 'attempts': attempts}


def pending_view(session, cursor):
    """The sign-in page's second step. The setup key is included only while enrolling."""
    pending = read_pending(session)
    if not pending:
        return {'pending': None}
    if session.get('user_id') or not active(cursor):
        clear_pending(session)
        return {'pending': None}
    if pending['step'] != 'enroll':
        return {'pending': 'totp'}
    shown = show_enrollment(cursor, pending['user_id'], pending['username'])
    if not shown:
        clear_pending(session)
        return {'pending': None}
    return {'pending': 'enroll', **shown}
