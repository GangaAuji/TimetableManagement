"""Session and CSRF endpoints. The payload is an allowlist from security.public_session."""

import re
from datetime import datetime

from flask import current_app, request, session
from flask_wtf.csrf import generate_csrf

from extensions import get_db_connection
from api.web.access import close
from api.web.responses import json_error, json_ok
from api.web.security import public_session, safe_count, safe_text
from core import capabilities
from core.scope import choose_institution, current_scope, forget as forget_scope
from data_access import institutions as institutions_store
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


_INSTITUTION_ERRORS = {
    'institution_required': 'Choose an institution.',
    'institution_not_found': 'That institution was not found.',
    'institution_forbidden': 'You are not a member of that institution.',
}


def _public_institution(row):
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 150),
        'code': safe_text(row.get('code'), 20),
        'short_name': safe_text(row.get('short_name'), 40),
    }


def _institution_payload():
    """`institution` (chosen or null), `institutions` (switcher choices) and `organization_wide`."""
    empty = {'institution': None, 'institutions': [], 'organization_wide': session.get('role') == 'Super Admin'}
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not institutions_store.table_exists(cursor):
            return empty
        forget_scope()
        scope = current_scope(cursor)
        if not scope.multiple:
            return empty
        rows = institutions_store.fetch_institutions(cursor, active_only=True)
        if not scope.organization_wide:
            rows = [row for row in rows if int(row['id']) in scope.visible]
        chosen = next((row for row in rows if scope.institution_id is not None and int(row['id']) == scope.institution_id), None)
        return {
            'institution': _public_institution(chosen) if chosen else None,
            'institutions': [_public_institution(row) for row in rows],
            'organization_wide': scope.organization_wide,
        }
    except Exception:
        current_app.logger.exception('Session institutions failed')
        return empty
    finally:
        close(cursor, connection)


def _capabilities_payload():
    """{name: bool} of effective capabilities; every name off when the lookup fails."""
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        return capabilities.snapshot(cursor)
    except Exception:
        current_app.logger.exception('Session capabilities failed')
        return {name: False for name in capabilities.NAMES}
    finally:
        close(cursor, connection)


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
        payload['maintenance'] = bool(current_app.config.get('MAINTENANCE_MODE', False))
        if payload.get('authenticated'):
            payload['password_expired'] = session.get('password_expired') is True
            payload['unrestricted'] = session.get('role') == 'Super Admin'
            payload['permissions'] = [] if payload['unrestricted'] else _permission_names(session.get('user_id'))
            payload.update(_institution_payload())
            payload['capabilities'] = _capabilities_payload()
            from core.license import evaluate
            license_problem = evaluate(current_app.config)['problem']
            if license_problem and session.get('role') in ('Admin', 'Super Admin', 'HOD'):
                payload['license_problem'] = license_problem
        return json_ok(payload)

    @blueprint.route('/session/institution', methods=['POST'])
    def switch_institution():
        if 'user_id' not in session:
            return json_error('Authentication required.', 401, 'unauthorized')
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) - {'institution_id'}:
            return json_error('The institution could not be changed.', 400, 'invalid_body')
        wanted = body.get('institution_id')
        if wanted is not None and (isinstance(wanted, bool) or not isinstance(wanted, int) or wanted < 1):
            return json_error('The institution could not be changed.', 400, 'invalid_body')
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            choose_institution(cursor, session, wanted)
        except ValueError as exc:
            status = 403 if str(exc) == 'institution_forbidden' else 404 if str(exc) == 'institution_not_found' else 400
            return json_error(_INSTITUTION_ERRORS[str(exc)], status, str(exc))
        except Exception:
            current_app.logger.exception('Institution switch failed')
            return json_error('The institution could not be changed.', 500, 'institution_unavailable')
        finally:
            close(cursor, connection)
        return json_ok(_institution_payload())

    @blueprint.route('/session/logout', methods=['POST'])
    def end_session():
        try:
            sign_out(session)
        except Exception:
            current_app.logger.exception('Logout failed')
            session.clear()
        return json_ok({'ended': True})
