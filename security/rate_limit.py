"""In-process request limits for sign-in and the JSON API.

The window is per process. A second Flask process keeps its own counters.
Limits are high enough for the signed-in screens, including job polling,
and low enough that a public sign-in form cannot be hammered.
"""

import threading
import time

from flask import jsonify, request, session

_LOCK = threading.Lock()
_HITS = {}
_AUTH_PATHS = frozenset(('/login', '/admin/login'))
_AUTH_LIMIT = 10
_AUTH_WINDOW = 600
_PUBLIC_API_LIMIT = 60
_SIGNED_IN_API_LIMIT = 300
_API_WINDOW = 60


def allow(bucket, limit, window, now=None):
    """Record one hit. Return False when the bucket is already full."""
    moment = time.monotonic() if now is None else now
    with _LOCK:
        recent = [stamp for stamp in _HITS.get(bucket, ()) if moment - stamp < window]
        if len(recent) >= limit:
            _HITS[bucket] = recent
            return False
        recent.append(moment)
        _HITS[bucket] = recent
        if len(_HITS) > 4000:
            stale = [key for key, stamps in _HITS.items() if not stamps or moment - stamps[-1] >= window]
            for key in stale:
                _HITS.pop(key, None)
    return True


def _limited(path):
    if path.startswith('/api/'):
        return jsonify({
            'success': False,
            'error': {'code': 'rate_limited', 'message': 'Too many requests. Wait a moment and try again.'},
        }), 429
    return 'Too many attempts. Wait a few minutes and try again.', 429


def enforce_rate_limit():
    """Return a 429 response, or None when the request may continue."""
    path = (request.path or '/').rstrip('/') or '/'
    if path.startswith('/static/') or path == '/favicon.ico':
        return None
    address = request.remote_addr or 'local'
    if request.method == 'POST' and (path in _AUTH_PATHS or path.startswith('/register/')):
        if not allow(f'auth:{address}', _AUTH_LIMIT, _AUTH_WINDOW):
            return _limited(path)
        return None
    if path == '/health' or path.startswith('/api/'):
        user_id = session.get('user_id')
        if user_id:
            bucket = f'api-user:{user_id}'
            limit = _SIGNED_IN_API_LIMIT
        else:
            bucket = f'api-public:{address}'
            limit = _PUBLIC_API_LIMIT
        if not allow(bucket, limit, _API_WINDOW):
            return _limited(path)
    return None
