"""Offline installation license.

The file is JSON. ``signature`` is Ed25519 over the canonical JSON of the other
fields. The public key is embedded here; the private key stays with the vendor
and is not shipped on a college server.

``LICENSE_REQUIRED`` defaults off. An installation with no file then behaves
as it does today: sign-in, health, and creating students or institutions are
unchanged. When the flag is on, a missing, altered, or expired file is reported
by ``/health`` and blocks new students and institutions. People who already
have accounts can still sign in.
"""

import base64
import json
from datetime import date, datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Raw 32-byte Ed25519 public key. The matching private key is generated once
# for the vendor and kept outside the server (deploy/keys is gitignored).
PUBLIC_KEY_B64 = '3eoukFLVFDUFWohPEBUk6E4x2zD8XJNs8PO7Bt/eWFU='
GRACE_DAYS = 1
_FIELDS = ('capabilities', 'customer', 'edition', 'expires', 'max_institutions', 'max_students')


def _public_key(config):
    raw = str((config or {}).get('LICENSE_PUBLIC_KEY') or PUBLIC_KEY_B64).strip()
    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        return None
    if len(decoded) != 32:
        return None
    return Ed25519PublicKey.from_public_bytes(decoded)


def canonical(payload):
    """Stable bytes the signature covers. Field order does not matter on disk."""
    body = {name: payload.get(name) for name in _FIELDS}
    return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')


def _blank(required):
    return {
        'required': required,
        'state': 'not_required' if not required else 'missing',
        'customer': '',
        'edition': '',
        'expires': '',
        'max_students': None,
        'max_institutions': None,
        'capabilities': [],
        'problem': None if not required else 'A license file is required.',
    }


def _limit(value):
    """None means no cap. A whole number is a cap. Anything else is rejected."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10000000:
        raise ValueError('limit')
    return value


def _capabilities(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 40:
        raise ValueError('capabilities')
    names = []
    for item in value:
        if not isinstance(item, str) or not item.replace('_', '').isalnum() or item != item.lower() or len(item) > 40:
            raise ValueError('capabilities')
        names.append(item)
    return names


def _payload_from(document):
    if not isinstance(document, dict):
        raise ValueError('document')
    expires = document.get('expires')
    if expires is not None:
        if not isinstance(expires, str):
            raise ValueError('expires')
        date.fromisoformat(expires)
    customer = document.get('customer')
    edition = document.get('edition')
    if not isinstance(customer, str) or not customer.strip() or len(customer) > 160:
        raise ValueError('customer')
    if not isinstance(edition, str) or not edition.strip() or len(edition) > 40:
        raise ValueError('edition')
    return {
        'capabilities': _capabilities(document.get('capabilities')),
        'customer': customer.strip(),
        'edition': edition.strip(),
        'expires': expires,
        'max_institutions': _limit(document.get('max_institutions')),
        'max_students': _limit(document.get('max_students')),
    }


def sign_document(payload, private_key):
    """Return the document, including the signature, for the given private key."""
    body = _payload_from(payload)
    signature = private_key.sign(canonical(body))
    return {**body, 'signature': base64.b64encode(signature).decode('ascii')}


def _expired(expires, today):
    if not expires:
        return False
    last = date.fromisoformat(expires) + timedelta(days=GRACE_DAYS)
    return today > last


def evaluate(config, today=None):
    """The license status. ``problem`` is set only when a license is required and not acceptable."""
    required = bool((config or {}).get('LICENSE_REQUIRED'))
    status = _blank(required)
    if not required:
        return status
    path = str((config or {}).get('LICENSE_FILE') or '').strip()
    if not path:
        return status
    try:
        with open(path, encoding='utf-8') as handle:
            document = json.load(handle)
        if not isinstance(document, dict):
            raise ValueError('document')
        signature = base64.b64decode(str(document.get('signature') or ''), validate=True)
        body = _payload_from(document)
        key = _public_key(config)
        if key is None:
            raise ValueError('key')
        key.verify(signature, canonical(body))
    except FileNotFoundError:
        return status
    except (OSError, json.JSONDecodeError, ValueError, InvalidSignature):
        status['state'] = 'invalid'
        status['problem'] = 'The license file is not valid.'
        return status
    day = today or datetime.now(timezone.utc).date()
    status.update(
        customer=body['customer'],
        edition=body['edition'],
        expires=body['expires'] or '',
        max_students=body['max_students'],
        max_institutions=body['max_institutions'],
        capabilities=body['capabilities'],
    )
    if _expired(body['expires'], day):
        status['state'] = 'expired'
        status['problem'] = f"The license expired on {body['expires']}."
        return status
    status['state'] = 'ok'
    status['problem'] = None
    return status


def growth_block(config, kind, count):
    """``(code, message)`` when a new student or institution is not allowed, else None.

    Returns before any decision that needs a count when the license is not required.
    ``count`` is the number already stored. A cap of None does not limit that kind.
    """
    if not (config or {}).get('LICENSE_REQUIRED'):
        return None
    status = evaluate(config)
    if status['problem']:
        return ('license_required', status['problem'])
    cap = status['max_students'] if kind == 'students' else status['max_institutions']
    if cap is None:
        return None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return ('license_required', 'The license could not be checked.')
    if count >= cap:
        code = 'license_students' if kind == 'students' else 'license_institutions'
        noun = 'students' if kind == 'students' else 'institutions'
        return (code, f'The license allows {cap} {noun}.')
    return None


def _count(cursor, table):
    cursor.execute(f'SELECT COUNT(*) AS n FROM `{table}`')
    row = cursor.fetchone()
    value = row['n'] if isinstance(row, dict) else row[0]
    return int(value)


def refuse_student(cursor, config):
    """Block adding a student, or None. Does not query while the license is not required."""
    if not (config or {}).get('LICENSE_REQUIRED'):
        return None
    try:
        count = _count(cursor, 'students')
    except Exception:
        return ('license_required', 'The license could not be checked.')
    return growth_block(config, 'students', count)


def refuse_institution(cursor, config):
    """Block adding an institution row, or None. Does not query while the license is not required."""
    if not (config or {}).get('LICENSE_REQUIRED'):
        return None
    try:
        count = _count(cursor, 'institutions')
    except Exception:
        return ('license_required', 'The license could not be checked.')
    return growth_block(config, 'institutions', count)
