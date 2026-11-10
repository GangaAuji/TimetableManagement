"""Small secrets stored in the database (an SMTP password, an API client secret) are Fernet-encrypted.

The key is SETTINGS_ENCRYPTION_KEY, else FACE_TEMPLATE_KEY, else one derived
from SECRET_KEY (SHA-256 of it, base64url) so a plain install still never
stores the value in clear. Rotating whichever key is in use makes the
stored secrets unreadable: `decrypt_text` returns None and the setting has
to be entered again.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, has_app_context

PREFIX = 'enc:v1:'


def _config_value(name):
    if not has_app_context():
        return None
    value = current_app.config.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def key_source():
    """Which setting the key comes from: 'SETTINGS_ENCRYPTION_KEY', 'FACE_TEMPLATE_KEY', 'SECRET_KEY' or None."""
    for name in ('SETTINGS_ENCRYPTION_KEY', 'FACE_TEMPLATE_KEY'):
        if _config_value(name):
            return name
    return 'SECRET_KEY' if _config_value('SECRET_KEY') else None


def _fernet():
    source = key_source()
    if source is None:
        return None
    value = _config_value(source)
    if source == 'SECRET_KEY':
        value = base64.urlsafe_b64encode(hashlib.sha256(value.encode('utf-8')).digest()).decode('ascii')
    try:
        return Fernet(value.encode('utf-8'))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f'{source} is not a valid Fernet key: {exc}') from exc


def encrypt_text(text):
    """A string -> `enc:v1:<token>`. Raises RuntimeError when no key is available."""
    fernet = _fernet()
    if fernet is None:
        raise RuntimeError('No encryption key: set SETTINGS_ENCRYPTION_KEY (or FACE_TEMPLATE_KEY, or SECRET_KEY).')
    return PREFIX + fernet.encrypt(str(text).encode('utf-8')).decode('ascii')


def decrypt_text(stored):
    """The stored token -> the string, or None when empty or unreadable with the current key."""
    if not stored:
        return None
    if not isinstance(stored, str) or not stored.startswith(PREFIX):
        return None
    try:
        fernet = _fernet()
    except RuntimeError:
        return None
    if fernet is None:
        return None
    try:
        return fernet.decrypt(stored[len(PREFIX):].encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return None
