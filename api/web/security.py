"""Shared guards for /api JSON responses.

Responses stay on an allowlist: no account ids, email addresses, session
secrets, database errors, or unsanitized branding values that could be
placed into a URL or a CSS color.
"""

import re
from datetime import date, datetime
from urllib.parse import urlparse

from flask import current_app, request, session

from api.web.responses import json_error

_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]')
_ROLE_NAME = re.compile(r'^[A-Za-z][A-Za-z0-9 _-]{0,49}$')
_HEX_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')
_ASSET_PATH = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$')

KNOWN_ROLES = frozenset(('Super Admin', 'Admin', 'HOD', 'Teacher', 'Student'))
ADMIN_ROLES = frozenset(('Admin', 'Super Admin', 'HOD'))

API_SECURITY_HEADERS = {
    'Cache-Control': 'no-store',
    'Pragma': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    'Cross-Origin-Resource-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
    'X-Permitted-Cross-Domain-Policies': 'none',
}


def apply_api_security_headers(response):
    for name, value in API_SECURITY_HEADERS.items():
        response.headers[name] = value
    response.headers['Vary'] = 'Cookie'
    return response
_MAX_BODY_BYTES = 65536
_DEV_FRONTEND_HOSTS = frozenset(('127.0.0.1:5173', 'localhost:5173'))


def _allowed_source_hosts():
    hosts = {request.host}
    if current_app.debug:
        hosts.update(_DEV_FRONTEND_HOSTS)
    configured = current_app.config.get('API_ALLOWED_ORIGINS') or ''
    for item in str(configured).split(','):
        item = item.strip()
        if not item:
            continue
        parsed = urlparse(item if '://' in item else 'https://' + item)
        if parsed.netloc:
            hosts.add(parsed.netloc)
    return hosts


def _multipart_upload(path):
    content_type = (request.content_type or '').split(';', 1)[0].strip().lower()
    return request.method == 'POST' and request.path.rstrip('/') == path and content_type == 'multipart/form-data'


def _profile_photo_upload():
    return _multipart_upload('/api/account')


def _settings_upload():
    return _multipart_upload('/api/settings')


_PUBLIC_GET = frozenset(('/api/branding', '/api/csrf-token', '/api/session'))


def api_is_public():
    """True only for the calls the sign-in and invitation screens need."""
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        return False
    path = (request.path or '/').rstrip('/') or '/'
    if path in _PUBLIC_GET:
        return True
    return path.startswith('/api/register/') and path != '/api/register'


def require_authenticated_api():
    """Reject an API call that has no signed-in account.

    Public sign-in helpers stay open. Every other route still applies its
    own permission or role check after this gate.
    """
    if api_is_public():
        return None
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    role = session.get('role')
    if not isinstance(role, str) or not role.strip():
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    return None


def reject_unsafe_request():
    """Block oversized bodies and cross-site writes before a route runs."""
    upload = _profile_photo_upload() or _settings_upload()
    if _settings_upload():
        limit = 8 * 1024 * 1024
    elif upload:
        limit = 2 * 1024 * 1024
    else:
        limit = _MAX_BODY_BYTES
    if request.content_length is not None and request.content_length > limit:
        return json_error('The request was blocked.', 413, 'blocked')

    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return None

    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.content_length not in (None, 0):
        content_type = (request.content_type or '').split(';', 1)[0].strip().lower()
        if not upload and content_type != 'application/json':
            return json_error('The request was blocked.', 415, 'blocked')

    source = request.headers.get('Origin') or request.headers.get('Referer') or ''
    parsed = urlparse(source)
    if parsed.scheme not in ('http', 'https') or parsed.netloc not in _allowed_source_hosts():
        return json_error('The request was blocked.', 403, 'blocked')
    return None




def safe_text(value, limit):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ''
    text = _CONTROL_CHARS.sub('', str(value)).strip()
    return text[:limit]


def safe_stamp(value):
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, datetime):
        return safe_text(value.isoformat(sep=' ', timespec='minutes'), 19)
    if isinstance(value, date):
        return safe_text(value.isoformat(), 10)
    if hasattr(value, 'isoformat'):
        try:
            text = value.isoformat(sep=' ', timespec='minutes')
        except TypeError:
            text = value.isoformat()
        return safe_text(text, 19)
    return safe_text(value, 19)


def safe_clock(value):
    from datetime import timedelta
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) % 86400
        hours, remainder = divmod(total, 3600)
        minutes, _seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}'
    if hasattr(value, 'strftime'):
        return value.strftime('%H:%M')
    return safe_text(value, 8)


def safe_color(value, fallback):
    text = safe_text(value, 7)
    if _HEX_COLOR.match(text):
        return text
    return fallback


def safe_asset_path(value):
    text = safe_text(value, 180)
    if (
        not text
        or text.startswith('/')
        or '\\' in text
        or '..' in text
        or '://' in text
        or not _ASSET_PATH.match(text)
    ):
        return ''
    return text


def safe_count(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    if number < 0:
        return 0
    return min(number, 1000000)


def public_session(session_data):
    if 'user_id' not in session_data:
        return {'authenticated': False}

    role = session_data.get('role')
    photo = safe_asset_path(session_data.get('profile_photo')) or 'default-avatar.svg'
    return {
        'authenticated': True,
        'username': safe_text(session_data.get('username'), 80),
        'role': role if isinstance(role, str) and _ROLE_NAME.match(role) else '',
        'profile_photo': photo,
    }
