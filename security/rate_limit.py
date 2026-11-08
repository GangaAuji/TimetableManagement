"""Request limits for sign-in and the JSON API.

Counters live in rate_limit_counters so every worker shares one window.
A storage failure falls back to this process only.

The client address is request.remote_addr. With TRUSTED_PROXY_COUNT above 0,
app_factory wraps the app in werkzeug's ProxyFix, which sets remote_addr from
that many X-Forwarded-For hops; with 0 the headers are ignored.

A sign-in POST is limited per address and username, so one shared address
(a classroom behind NAT) is not throttled as a whole, and by a generous
ceiling per address. Usernames that do not exist are counted per address
only and stop all sign-ins from that address once the limit is reached,
so the answer never depends on whether a username exists.
"""

import hashlib
import threading
import time

from flask import current_app, jsonify, request, session

_LOCK = threading.Lock()
_HITS = {}
_SIGN_IN_PATHS = frozenset(('/login', '/admin/login'))
_AUTH_LIMIT = 10
_AUTH_WINDOW = 600
_PUBLIC_API_LIMIT = 60
_SIGNED_IN_API_LIMIT = 300
_API_WINDOW = 60
_NO_LIMIT = 2 ** 31


def allow(bucket, limit, window, now=None):
    """Record one hit in this process. Return False when the bucket is already full."""
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


def local_hits(bucket, window, now=None):
    moment = time.monotonic() if now is None else now
    with _LOCK:
        return sum(1 for stamp in _HITS.get(bucket, ()) if moment - stamp < window)


def record_fixed_window(store, bucket, limit, window, now):
    """Share one fixed window across callers. store is a dict guarded by store_lock."""
    lock = store.setdefault('_lock', threading.Lock())
    with lock:
        start, count = store.get(bucket, (now, 0))
        if now - start >= window:
            start, count = now, 0
        if count >= limit:
            store[bucket] = (start, count)
            return False
        store[bucket] = (start, count + 1)
        return True


_UPSERT = """
INSERT INTO rate_limit_counters (bucket, hits, window_start)
VALUES (%s, 1, UTC_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE
    hits = IF(window_start <= UTC_TIMESTAMP(6) - INTERVAL %s SECOND, 1, hits + 1),
    window_start = IF(window_start <= UTC_TIMESTAMP(6) - INTERVAL %s SECOND, UTC_TIMESTAMP(6), window_start)
"""


def shared_allow(cursor, bucket, limit, window):
    """Atomic increment in the shared table. Return False when the window is full."""
    cursor.execute(_UPSERT, (bucket, int(window), int(window)))
    cursor.execute('SELECT hits FROM rate_limit_counters WHERE bucket = %s', (bucket,))
    row = cursor.fetchone()
    hits = row['hits'] if isinstance(row, dict) else row[0]
    return int(hits) <= int(limit)


def shared_hits(cursor, bucket, window):
    """Hits in the bucket's current window, without adding one."""
    cursor.execute(
        'SELECT hits FROM rate_limit_counters WHERE bucket = %s '
        'AND window_start > UTC_TIMESTAMP(6) - INTERVAL %s SECOND',
        (bucket, int(window)),
    )
    row = cursor.fetchone()
    if row is None:
        return 0
    return int(row['hits'] if isinstance(row, dict) else row[0])


def _with_cursor(action, fallback):
    try:
        from extensions import get_db_connection

        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            result = action(cursor)
            connection.commit()
            return result
        finally:
            cursor.close()
            connection.close()
    except Exception:
        current_app.logger.exception('Shared rate limit storage failed')
        return fallback()


def _shared_or_local(bucket, limit, window):
    return _with_cursor(
        lambda cursor: shared_allow(cursor, bucket, limit, window),
        lambda: allow(bucket, limit, window),
    )


def _hits(bucket, window):
    return _with_cursor(lambda cursor: shared_hits(cursor, bucket, window), lambda: local_hits(bucket, window))


def _setting(name, default):
    try:
        value = int(current_app.config.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _unknown_window():
    return _setting('SIGN_IN_FAILURE_WINDOW_MINUTES', 15) * 60


def _unknown_bucket(address):
    return f'auth-unknown:{address or "local"}'


def count_unknown_username(address):
    """Record a sign-in for a username that does not exist, against the address only."""
    _shared_or_local(_unknown_bucket(address), _NO_LIMIT, _unknown_window())


def _account_bucket(address, username):
    digest = hashlib.sha256(username.strip().lower().encode('utf-8')).hexdigest()[:32]
    return f'auth:{address}:{digest}'


def _sign_in_limited(address):
    if _hits(_unknown_bucket(address), _unknown_window()) >= _setting('SIGN_IN_UNKNOWN_LIMIT_PER_ADDRESS', 20):
        return True
    if not _shared_or_local(f'auth-address:{address}', _setting('SIGN_IN_LIMIT_PER_ADDRESS', 300), _AUTH_WINDOW):
        return True
    username = request.form.get('username', '')
    if not isinstance(username, str):
        username = ''
    bucket = _account_bucket(address, username[:100])
    return not _shared_or_local(bucket, _setting('SIGN_IN_LIMIT_PER_ACCOUNT', _AUTH_LIMIT), _AUTH_WINDOW)


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
    if request.method == 'POST' and path in _SIGN_IN_PATHS:
        return _limited(path) if _sign_in_limited(address) else None
    if request.method == 'POST' and path.startswith('/register/'):
        if not _shared_or_local(f'auth:{address}', _AUTH_LIMIT, _AUTH_WINDOW):
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
        if not _shared_or_local(bucket, limit, _API_WINDOW):
            return _limited(path)
    return None
