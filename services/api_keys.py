"""API keys for the public /api/v1.

A key looks like `ttk_<12 char prefix>_<32 char secret>`. The prefix finds
the row; the SHA-256 of the whole key is compared in constant time. The
plaintext is returned once from `create_key` and never stored or logged.
Scopes are coarse read scopes per domain; a key has only the scopes it was
created with and cannot gain one later (create a new key instead).
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from data_access import api_keys as rows

PREFIX = 'ttk'
SCOPES = {
    'catalog:read': 'Courses, classes, divisions, subjects, academic years, rooms',
    'timetable:read': 'Published timetable slots per class',
    'people:read': 'Students and faculty directory (names, roll numbers, departments; no credentials)',
    'attendance:read': 'Lecture sessions, marks and attendance percentages',
}
_PREFIX_LENGTH = 12
_SECRET_LENGTH = 32


class ApiKeyError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def parse_scopes(value):
    """Space-separated scopes string to a sorted tuple; unknown names are dropped."""
    if isinstance(value, (list, tuple, set, frozenset)):
        names = value
    else:
        names = str(value or '').split()
    return tuple(sorted({name for name in names if name in SCOPES}))


def _hash(key):
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def _random(alphabet_length):
    alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(alphabet_length))


def create_key(cursor, *, name, scopes, created_by, expires_at=None):
    """Insert a key. Returns (id, plaintext key). The plaintext cannot be recovered later."""
    clean_name = (name or '').strip()
    if not clean_name or len(clean_name) > 100:
        raise ApiKeyError('api_key_name_invalid')
    clean_scopes = parse_scopes(scopes)
    if not clean_scopes:
        raise ApiKeyError('api_key_scopes_invalid')
    for _ in range(5):
        prefix = _random(_PREFIX_LENGTH)
        if rows.fetch_by_prefix(cursor, prefix) is None:
            break
    else:  # pragma: no cover - 56^12 prefixes
        raise ApiKeyError('api_key_failed')
    plaintext = f'{PREFIX}_{prefix}_{_random(_SECRET_LENGTH)}'
    key_id = rows.insert_key(
        cursor, name=clean_name, prefix=prefix, key_hash=_hash(plaintext), scopes=' '.join(clean_scopes),
        created_by=created_by, expires_at=expires_at,
    )
    return key_id, plaintext


def revoke_key(cursor, key_id):
    if rows.fetch_key(cursor, key_id) is None:
        raise ApiKeyError('api_key_not_found')
    return rows.revoke_key(cursor, key_id) == 1


def list_keys(cursor):
    return rows.fetch_keys(cursor) if rows.table_exists(cursor) else []


def split_key(presented):
    """(prefix, key) for a well-formed key, else None. Cheap enough to run before any query."""
    if not isinstance(presented, str):
        return None
    parts = presented.strip().split('_')
    if len(parts) != 3 or parts[0] != PREFIX or len(parts[1]) != _PREFIX_LENGTH or len(parts[2]) != _SECRET_LENGTH:
        return None
    if not (parts[1].isalnum() and parts[2].isalnum()):
        return None
    return parts[1], presented.strip()


def authenticate(cursor, presented, now=None):
    """The key row for a valid, unexpired, unrevoked key, or None. Stamps last_used_at on success."""
    parsed = split_key(presented)
    if parsed is None:
        return None
    prefix, key = parsed
    row = rows.fetch_by_prefix(cursor, prefix)
    if row is None or not hmac.compare_digest(row['key_hash'], _hash(key)):
        return None
    if row.get('revoked_at') is not None:
        return None
    moment = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if row.get('expires_at') is not None and row['expires_at'] <= moment:
        return None
    rows.touch_key(cursor, row['id'])
    return {**row, 'scopes': parse_scopes(row.get('scopes'))}


def has_scope(key_row, scope):
    return scope in (key_row or {}).get('scopes', ())
