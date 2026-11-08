"""One-way password checks. A legacy plaintext value is accepted once, then replaced."""

import hmac

from werkzeug.security import check_password_hash, generate_password_hash

_HASH_PREFIXES = ('pbkdf2:', 'scrypt:', 'argon2:')


def is_password_hash(stored):
    """Return True when the stored value is already a one-way hash."""
    return isinstance(stored, str) and stored.startswith(_HASH_PREFIXES)


def hash_password(raw):
    """Hash a new password. Werkzeug picks its strongest built-in method."""
    return generate_password_hash(raw)


def password_matches(stored, raw):
    """Return True when raw matches the stored hash or a legacy plaintext value."""
    if not isinstance(stored, str) or not isinstance(raw, str) or stored == '' or raw == '':
        return False
    if is_password_hash(stored):
        return bool(check_password_hash(stored, raw))
    if len(stored) != len(raw):
        return False
    return hmac.compare_digest(stored, raw)


def upgraded_hash(stored, raw):
    """Return a hash when a matching stored value is still plaintext."""
    if is_password_hash(stored) or not password_matches(stored, raw):
        return None
    return hash_password(raw)
