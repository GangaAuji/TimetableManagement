"""Session and CSRF endpoints. The payload is an allowlist from security.public_session."""

import re
from datetime import datetime

from flask import current_app, session
from flask_wtf.csrf import generate_csrf

from extensions import get_db_connection
from api.web.access import close
from api.web.responses import json_error, json_ok
from api.web.security import public_session
from security import get_user_permissions
from services.login import sign_out

_PERMISSION_NAME = re.compile(r'^[a-z0-9_]{1,80}$')


def _permission_names(user_id):
    try:
        rows = get_user_permissions(user_id) or []
    except Exception:
        current_app.logger.exception('Session permissions failed')
        return []
    names = []
    seen = set()
    for row in rows:
        name = row.get('name') if isinstance(row, dict) else None
        if not isinstance(name, str) or not _PERMISSION_NAME.match(name) or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= 400:
            break
    return names


def _browser_session_open():
    """False when this login row was ended or has expired. A lookup error keeps the cookie."""
    session_id = session.get('session_id')
    if not isinstance(session_id, str) or not session_id or len(session_id) > 80:
        return True
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT is_active, expires_at FROM user_sessions WHERE session_id = %s',
            (session_id,),
        )
        row = cursor.fetchone()
    except Exception:
        current_app.logger.exception('Session check failed')
        return True
    finally:
        close(cursor, connection)
    if not row or not row.get('is_active'):
        return False
    expires = row.get('expires_at')
    if expires is not None and hasattr(expires, 'timestamp') and expires < datetime.now():
        return False
    return True


def register_session_routes(blueprint):
    @blueprint.route('/csrf-token', methods=['GET'])
    def csrf_token():
        token = generate_csrf()
        if not isinstance(token, str) or not token or len(token) > 500:
            return json_error('The security token could not be issued.', 500, 'csrf_unavailable')
        return json_ok({'csrf_token': token})

    @blueprint.route('/session', methods=['GET'])
    def current_session():
        if 'user_id' in session and not _browser_session_open():
            session.clear()
        payload = public_session(session)
        if payload.get('authenticated'):
            payload['unrestricted'] = session.get('role') == 'Super Admin'
            payload['permissions'] = [] if payload['unrestricted'] else _permission_names(session.get('user_id'))
        return json_ok(payload)

    @blueprint.route('/session/logout', methods=['POST'])
    def end_session():
        try:
            sign_out(session)
        except Exception:
            current_app.logger.exception('Logout failed')
            session.clear()
        return json_ok({'ended': True})
