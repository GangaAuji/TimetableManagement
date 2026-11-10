"""Resolve each request to a tenant by hostname and keep sessions bound to it.

Installed first among the before_request hooks so everything after it (rate
limits, session tracking, views) opens the right database. In single-college
mode the hook does nothing.

A browser session carries the slug it was signed in on. A cookie presented
on another college's hostname is cleared rather than honoured.
"""

from flask import g, jsonify, request, session

from core.tenancy import bind, registry_enabled
from core.tenancy.registry import Registry

SESSION_KEY = 'tenant'
_PASS_THROUGH = ('/health',)
_JSON_PREFIXES = ('/api/', '/mobile-sync')


def _wants_json(path):
    return any(path.startswith(prefix) for prefix in _JSON_PREFIXES)


def _refuse(path, status, code, message):
    if _wants_json(path):
        return jsonify({'success': False, 'error': {'code': code, 'message': message}}), status
    return message, status


def bind_session(flask_session, slug):
    """Clear a session that is not bound to `slug`. Returns True when it was cleared.

    A signed-in session must carry the slug it was opened on (stamp_session
    writes it when the sign-in response is built). One without a slug, or with
    another college's, is not trusted on this hostname.
    """
    bound = flask_session.get(SESSION_KEY)
    if bound == slug:
        return False
    if bound is not None or 'user_id' in flask_session:
        flask_session.clear()
        return True
    return False


def stamp_session(flask_session, slug):
    """After the view ran: a session that signed in during this request gets the tenant slug."""
    if 'user_id' in flask_session and flask_session.get(SESSION_KEY) != slug:
        flask_session[SESSION_KEY] = slug


def resolve_request(app):
    """The before_request hook. Returns a response to short-circuit with, or None."""
    path = request.path or '/'
    if path.startswith('/static/') or path in _PASS_THROUGH:
        return None
    registry = Registry.from_config(app.config)
    try:
        tenant = registry.resolve(request.host)
    except Exception:
        app.logger.exception('Tenant registry lookup failed')
        return _refuse(path, 503, 'registry_unavailable', 'The service is temporarily unavailable.')
    if tenant is None:
        return _refuse(path, 404, 'unknown_tenant', 'No college is served at this address.')
    if not tenant.active:
        return _refuse(path, 503, 'tenant_unavailable', 'This college is not available at the moment.')
    bind(tenant)
    g.tenant_slug = tenant.slug
    bind_session(session, tenant.slug)
    return None


def install(app):
    """Register the hook when the app has a tenant registry."""
    if not registry_enabled(app.config):
        return False

    @app.before_request
    def resolve_tenant():
        return resolve_request(app)

    @app.after_request
    def stamp_tenant_session(response):
        slug = getattr(g, 'tenant_slug', None)
        if slug is not None:
            stamp_session(session, slug)
        return response

    return True
