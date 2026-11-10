"""RFC 6238 TOTP (SHA-1, 6 digits, 30-second step) and one-time recovery codes.

No Flask and no database. Callers encrypt the base32 secret before storing it
and store only hashes of recovery codes. Nothing here is written to a log.
"""

import base64
import hashlib
import hmac
import re
import secrets
import struct
from urllib.parse import quote, urlencode

from werkzeug.security import check_password_hash, generate_password_hash

DIGITS = 6
STEP = 30
WINDOW = 1
RECOVERY_COUNT = 8


def generate_secret():
    """A base32 secret (no padding) for an authenticator app."""
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def decode_secret(secret):
    """Base32 text -> key bytes, or None when it is not a secret we would have issued."""
    if not isinstance(secret, str):
        return None
    cleaned = secret.strip().upper().replace(' ', '')
    if not re.fullmatch(r'[A-Z2-7]{16,64}', cleaned):
        return None
    padded = cleaned + '=' * ((8 - len(cleaned) % 8) % 8)
    try:
        return base64.b32decode(padded, casefold=True)
    except (ValueError, TypeError):
        return None


def hotp(key, counter, digits=DIGITS):
    """HOTP (RFC 4226) for one counter, as a zero-padded digit string."""
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f'{binary % 10 ** digits:0{digits}d}'


def matching_step(secret, code, now, *, step=STEP, window=WINDOW, last_step=None):
    """The time-step a 6-digit code matches, or None.

    ``last_step`` is the newest step already accepted for this secret, so a
    code cannot be used twice. ``window`` allows one step of clock drift.
    """
    key = decode_secret(secret)
    if key is None or not isinstance(code, str) or not re.fullmatch(r'\d{6}', code):
        return None
    if not isinstance(now, (int, float)) or isinstance(now, bool):
        return None
    counter = int(now // step)
    floor = int(last_step) if last_step is not None else None
    for offset in (0, -1, 1):
        candidate = counter + offset
        if candidate < 0 or (floor is not None and candidate <= floor):
            continue
        if hmac.compare_digest(hotp(key, candidate), code):
            return candidate
    return None


def account_name(username):
    cleaned = ''.join(ch for ch in str(username) if ch.isascii() and (ch.isalnum() or ch in '._-@'))[:64]
    return cleaned or 'user'


def otpauth_uri(secret, account, issuer):
    """The otpauth URI an authenticator imports as a time-based 6-digit account."""
    label = f'{quote(issuer, safe="")}:{quote(account, safe="")}'
    query = urlencode({
        'secret': secret,
        'issuer': issuer,
        'algorithm': 'SHA1',
        'digits': str(DIGITS),
        'period': str(STEP),
    })
    return f'otpauth://totp/{label}?{query}'


def normalize_totp(presented):
    if not isinstance(presented, str) or len(presented) > 16:
        return None
    compact = re.sub(r'\s', '', presented)
    return compact if re.fullmatch(r'\d{6}', compact) else None


def new_recovery_codes():
    """Eight single-use codes, shown once as ``XXXX-XXXX``."""
    codes = []
    while len(codes) < RECOVERY_COUNT:
        token = secrets.token_hex(4).upper()
        code = f'{token[:4]}-{token[4:]}'
        if code not in codes:
            codes.append(code)
    return codes


def hash_recovery(codes):
    return [generate_password_hash(code.replace('-', '')) for code in codes]


def match_recovery(hashes, presented):
    """The remaining hashes after the presented code matches one of them, else None.

    Every hash is checked. The matching one is left out of the returned list.
    """
    if not isinstance(presented, str) or len(presented) > 32:
        return None
    normalized = re.sub(r'[\s-]', '', presented).upper()
    if not re.fullmatch(r'[0-9A-F]{8}', normalized):
        return None
    found = False
    kept = []
    for hashed in hashes or []:
        matched = False
        if isinstance(hashed, str):
            try:
                matched = bool(check_password_hash(hashed, normalized))
            except (TypeError, ValueError):
                matched = False
        if matched and not found:
            found = True
            continue
        kept.append(hashed)
    return kept if found else None
