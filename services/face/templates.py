"""Face templates at rest: encrypted with FACE_TEMPLATE_KEY, readable with the previous key during rotation.

A stored value is either the legacy plaintext JSON list or
`enc:v1:<Fernet token>`. `encode_template` always produces the encrypted
form when a key is configured; `decode_template` reads both, so a database
with a mix of old and new rows keeps working and `flask face
encrypt-templates` converts the rest. Key rotation: set FACE_TEMPLATE_KEY to
the new key and FACE_TEMPLATE_KEY_PREVIOUS to the old one, run `flask face
rotate-key`, then drop the previous key from the environment.

Without a key the app stores plaintext and reports `face_key: missing` on
/health. Production should always set one (`flask face generate-key`).
"""

import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from flask import current_app, has_app_context

PREFIX = 'enc:v1:'


def _setting(name):
    if not has_app_context():
        return None
    value = current_app.config.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _fernet(key):
    try:
        return Fernet(key.encode('utf-8') if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f'FACE_TEMPLATE_KEY is not a valid Fernet key: {exc}') from exc


def key_problem(config=None):
    """None when a usable FACE_TEMPLATE_KEY is configured, otherwise why not."""
    value = (config or (current_app.config if has_app_context() else {})).get('FACE_TEMPLATE_KEY')
    if not value:
        return 'FACE_TEMPLATE_KEY is not set; face templates are stored in plaintext.'
    try:
        _fernet(value)
    except RuntimeError as exc:
        return str(exc)
    return None


def _multi():
    """Encrypts with the current key, decrypts with the current and the previous one. None without a key."""
    current = _setting('FACE_TEMPLATE_KEY')
    if not current:
        return None
    keys = [_fernet(current)]
    previous = _setting('FACE_TEMPLATE_KEY_PREVIOUS')
    if previous and previous != current:
        keys.append(_fernet(previous))
    return MultiFernet(keys)


def is_encrypted(stored):
    return isinstance(stored, str) and stored.startswith(PREFIX)


def encode_template(values):
    """A list of floats -> the string to store (encrypted when a key is configured)."""
    plain = json.dumps([float(value) for value in values], separators=(',', ':'))
    fernet = _multi()
    if fernet is None:
        return plain
    return PREFIX + fernet.encrypt(plain.encode('utf-8')).decode('ascii')


def decode_template(stored):
    """The stored string (either form) -> list of floats, or None when it cannot be read."""
    if stored is None:
        return None
    if isinstance(stored, (bytes, bytearray)):
        stored = stored.decode('utf-8', 'replace')
    if not isinstance(stored, str):
        return None
    text = stored
    if is_encrypted(stored):
        fernet = _multi()
        if fernet is None:
            return None
        try:
            text = fernet.decrypt(stored[len(PREFIX):].encode('ascii')).decode('utf-8')
        except (InvalidToken, UnicodeError, ValueError):
            return None
    try:
        values = json.loads(text)
    except ValueError:
        return None
    if not isinstance(values, list):
        return None
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError):
        return None


def needs_rewrite(stored):
    """True when the row is plaintext, or encrypted with a key other than the current one."""
    if not is_encrypted(stored):
        return True
    current = _setting('FACE_TEMPLATE_KEY')
    if not current:
        return False
    try:
        _fernet(current).decrypt(stored[len(PREFIX):].encode('ascii'))
        return False
    except (InvalidToken, ValueError):
        return True


def reencrypt_all(cursor, batch=500):
    """Rewrite every template with the current key. Returns {'rewritten', 'unreadable', 'already'}."""
    if _multi() is None:
        raise RuntimeError(key_problem())
    counts = {'rewritten': 0, 'unreadable': 0, 'already': 0}
    last_id = 0
    while True:
        cursor.execute(
            'SELECT id, embedding_json FROM mobile_face_templates WHERE id > %s ORDER BY id LIMIT %s', (last_id, batch),
        )
        rows = cursor.fetchall()
        if not rows:
            break
        for row in rows:
            row_id, stored = (row['id'], row['embedding_json']) if isinstance(row, dict) else (row[0], row[1])
            last_id = row_id
            if not needs_rewrite(stored):
                counts['already'] += 1
                continue
            values = decode_template(stored)
            if values is None:
                counts['unreadable'] += 1
                continue
            cursor.execute(
                'UPDATE mobile_face_templates SET embedding_json = %s WHERE id = %s', (encode_template(values), row_id),
            )
            counts['rewritten'] += 1
    return counts
