"""Public, versioned JSON API at /api/v1, authenticated by API key.

    Authorization: Bearer ttk_<prefix>_<secret>

Keys are created on the Integrations screen (services/api_keys.py) with the
scopes they may use. Every route declares its scope with `operation(...)`
(api/v1/registry.py), which also produces /api/v1/openapi.json. The
blueprint is read-only: writes stay on the signed-in /api and the mobile
sync API. CSRF does not apply (no cookies are read); the key is the only
credential, and a per-key rate limit protects the database.
"""

from flask import Blueprint, current_app, g, request

from api.web.responses import json_error
from api.web.security import API_SECURITY_HEADERS

public_api_bp = Blueprint('public_api', __name__, url_prefix='/api/v1')

_OPEN_PATHS = frozenset(('/api/v1/openapi.json', '/api/v1'))


def _bearer():
    header = request.headers.get('Authorization') or ''
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        return None
    return token.strip()


def _rate_limited(prefix):
    from security.rate_limit import allow_bucket

    limit = int(current_app.config.get('PUBLIC_API_LIMIT_PER_MINUTE', 600) or 600)
    return not allow_bucket(f'api-key:{prefix}', limit, 60)


@public_api_bp.before_request
def authenticate_key():
    path = (request.path or '').rstrip('/')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        return json_error('This API is read-only.', 405, 'method_not_allowed')
    if path in _OPEN_PATHS:
        return None
    presented = _bearer()
    if presented is None:
        return json_error('Send the API key as "Authorization: Bearer <key>".', 401, 'unauthorized')
    from extensions import get_db_connection
    from services import api_keys

    parsed = api_keys.split_key(presented)
    if parsed is None:
        return json_error('The API key is not valid.', 401, 'unauthorized')
    if _rate_limited(parsed[0]):
        return json_error('Too many requests for this key. Wait a moment and try again.', 429, 'rate_limited')
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            key = api_keys.authenticate(cursor, presented)
            connection.commit()
        finally:
            cursor.close()
    finally:
        connection.close()
    if key is None:
        return json_error('The API key is not valid.', 401, 'unauthorized')
    g.api_key = key
    operation = getattr(current_app.view_functions.get(request.endpoint), '__operation__', None)
    if operation is not None and operation.scope and not api_keys.has_scope(key, operation.scope):
        return json_error(f'This key lacks the "{operation.scope}" scope.', 403, 'forbidden')
    return None


@public_api_bp.after_request
def security_headers(response):
    for name, value in API_SECURITY_HEADERS.items():
        response.headers[name] = value
    response.headers['Vary'] = 'Authorization'
    if 'Cross-Origin-Resource-Policy' in response.headers:
        response.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
    return response


from api.v1 import routes  # noqa: E402,F401  (registers the views on the blueprint)

__all__ = ['public_api_bp']
