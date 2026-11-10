"""Who may pass while MAINTENANCE_MODE is on.

Students, teachers, and signed-out visitors get the maintenance page.
The admin panel stays open for Admin, Super Admin, and HOD, including the
admin sign-in call. The page wording comes from branding settings.
"""

from flask import jsonify

_DEFAULT_NOTICE = {
    'title': "We'll be back shortly",
    'message': 'The timetable is temporarily unavailable while maintenance is in progress.',
    'site_title': 'Timetable Management System',
    'support_email': '',
    'support_phone': '',
    'logo': '',
}
_NOTICE_KEYS = (
    'maintenance_title', 'maintenance_message', 'site_title',
    'support_email', 'support_phone', 'login_logo', 'site_logo',
)

STAFF_ROLES = frozenset(('Super Admin', 'Admin', 'HOD'))
_PUBLIC_GET = frozenset(('/api/branding', '/api/csrf-token', '/api/session', '/api/sso'))


def _path(path):
    return (path or '/').rstrip('/') or '/'


def maintenance_allows(path, method, role, signed_in):
    """True when this request may continue during maintenance."""
    path = _path(path)
    method = (method or 'GET').upper()
    if path in ('/health', '/favicon.ico') or path.startswith('/static/'):
        return True
    if method in ('GET', 'HEAD', 'OPTIONS') and path in _PUBLIC_GET:
        return True
    if path == '/admin/login' or path.startswith('/auth/sso/'):
        return True
    if path in ('/logout', '/api/session/logout'):
        return True
    if signed_in and role in STAFF_ROLES and (path == '/admin' or path.startswith('/admin/') or path.startswith('/api/')):
        return True
    return False


def maintenance_notice():
    """The heading and message configured in Settings, or the built-in wording."""
    notice = dict(_DEFAULT_NOTICE)
    try:
        from flask import has_app_context

        if not has_app_context():
            return notice
        from api.web.security import safe_asset_path, safe_text
        from extensions import get_db_connection

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT setting_key, setting_value FROM branding_settings WHERE setting_key IN ({})".format(
                    ','.join(['%s'] * len(_NOTICE_KEYS))
                ),
                _NOTICE_KEYS,
            )
            stored = {row.get('setting_key'): row.get('setting_value') for row in cursor.fetchall()}
        finally:
            cursor.close()
            connection.close()
        title = safe_text(stored.get('maintenance_title'), 120)
        message = safe_text(stored.get('maintenance_message'), 400)
        site = safe_text(stored.get('site_title'), 80)
        if title:
            notice['title'] = title
        if message:
            notice['message'] = message
        if site:
            notice['site_title'] = site
        notice['support_email'] = safe_text(stored.get('support_email'), 160)
        notice['support_phone'] = safe_text(stored.get('support_phone'), 30)
        notice['logo'] = safe_asset_path(stored.get('login_logo')) or safe_asset_path(stored.get('site_logo'))
    except Exception:
        return dict(_DEFAULT_NOTICE)
    return notice


def maintenance_response(path):
    path = _path(path)
    if path.startswith('/api') or path.startswith('/admin/api') or path.startswith('/mobile-sync'):
        return jsonify({
            'success': False,
            'error': {'code': 'maintenance', 'message': 'The system is temporarily unavailable.'},
        }), 503
    from ui.errors import maintenance_document
    return maintenance_document()
