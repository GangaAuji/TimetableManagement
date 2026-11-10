"""Browser and API error responses.

Pages get a status page. The exception text is included only while DEBUG is
on. API calls keep the JSON envelope; an unexpected failure stays generic
unless DEBUG is on.
"""

from html import escape

from flask import Blueprint, current_app, redirect, request
from werkzeug.exceptions import HTTPException

from api.web.responses import json_error
from core.exceptions import AppError

error_handlers_bp = Blueprint('errors', __name__)

_COPY = {
    400: ('400', 'Bad request', 'The request could not be completed.'),
    401: ('401', 'Sign in required', 'Sign in is required.'),
    403: ('403', 'Not allowed', 'You do not have permission to open this page.'),
    404: ('404', 'Page not found', 'This page does not exist.'),
    500: ('500', 'Something went wrong', 'The page could not be loaded.'),
}


def _debug_on():
    return bool(current_app.debug)


def _detail_text(error):
    """One line of the exception, only for a debug server. No traceback."""
    if error is None or not _debug_on():
        return ''
    message = getattr(error, 'message', None) or str(error)
    if isinstance(error, AppError):
        text = str(message)
    else:
        text = f'{type(error).__name__}: {message}'
    cleaned = ' '.join(''.join(ch if ch.isprintable() else ' ' for ch in text).split())
    return cleaned[:400]


def error_document(status, detail=''):
    """A status page. The detail line is omitted unless DEBUG is on."""
    code, title, body = _COPY.get(status, ('500', 'Something went wrong', 'The page could not be loaded.'))
    shown = detail if detail and _debug_on() else ''
    extra = f'<pre>{escape(shown)}</pre>' if shown else ''
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(code)} · {escape(title)}</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f3f4f6; color: #1f2937; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
  main {{ width: min(28rem, calc(100% - 2rem)); border: 1px solid #e5e7eb; border-radius: 1rem; background: #fff; padding: 2.5rem 1.5rem; text-align: center; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
  .code {{ margin: 0; font-size: 3rem; font-weight: 700; letter-spacing: -0.03em; }}
  h1 {{ margin: 0.75rem 0 0; font-size: 1.125rem; }}
  p {{ margin: 0.5rem 0 0; color: #6b7280; font-size: 0.875rem; }}
  a {{ display: inline-block; margin-top: 1.5rem; border-radius: 0.75rem; background: #111827; color: #fff; padding: 0.65rem 1rem; font-size: 0.875rem; font-weight: 700; text-decoration: none; }}
  pre {{ margin: 1rem 0 0; padding: 0.75rem; border-radius: 0.75rem; background: #f9fafb; color: #374151; font-size: 0.75rem; white-space: pre-wrap; text-align: left; }}
</style>
</head>
<body>
<main>
  <p class="code">{escape(code)}</p>
  <h1>{escape(title)}</h1>
  <p>{escape(body)}</p>
  {extra}
  <a href="/">Back to the timetable</a>
</main>
</body>
</html>'''
    return html, status, {'Content-Type': 'text/html; charset=utf-8'}


def maintenance_document(notice=None):
    """The public page shown while MAINTENANCE_MODE is on."""
    from ui.maintenance import maintenance_notice

    shown = notice or maintenance_notice()
    title = escape(shown['title'])
    message = escape(shown['message'])
    site = escape(shown['site_title'])
    email = shown['support_email']
    phone = escape(shown['support_phone'])
    logo = shown['logo']
    email_html = f'<a href="mailto:{escape(email)}">{escape(email)}</a>' if email else ''
    phone_html = f'<span>{phone}</span>' if phone else ''
    contact = ''
    if email_html or phone_html:
        contact = f'<p class="contact">{email_html}{phone_html}</p>'
    mark = f'<img src="/static/{escape(logo)}" alt="">' if logo else ''
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #0f172a; color: #0f172a; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
  body::before {{ content: ""; position: fixed; inset: 0; background: radial-gradient(circle at top, rgba(16,185,129,.22), transparent 42%); }}
  main {{ position: relative; width: min(32rem, calc(100% - 2rem)); border-radius: 1.5rem; background: #fff; padding: 3rem 2rem; text-align: center; box-shadow: 0 24px 60px rgba(0,0,0,.28); }}
  img {{ display: block; height: 3.5rem; max-width: 12rem; margin: 0 auto 1.25rem; object-fit: contain; }}
  .site {{ margin: 0; color: #9ca3af; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; }}
  h1 {{ margin: 0.75rem 0 0; font-size: 1.875rem; letter-spacing: -0.03em; }}
  .message {{ margin: 1rem 0 0; color: #4b5563; font-size: 0.95rem; line-height: 1.6; }}
  .contact {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 0.75rem 1.25rem; margin: 1.75rem 0 0; color: #374151; font-size: 0.875rem; }}
  .contact a {{ color: #047857; font-weight: 700; text-decoration: none; }}
</style>
</head>
<body>
<main>
  {mark}
  <p class="site">{site}</p>
  <h1>{title}</h1>
  <p class="message">{message}</p>
  {contact}
</main>
</body>
</html>'''
    return html, 503, {'Content-Type': 'text/html; charset=utf-8'}


def error_response(status, message='The page could not be loaded.', code=None, error=None):
    """JSON for API calls. A status page for the browser."""
    path = request.path or ''
    detail = _detail_text(error)
    if path.startswith('/api') or path.startswith('/admin/api') or path.startswith('/mobile-sync'):
        resolved = code if code is not None else (
            'not_found' if status == 404 else 'forbidden' if status == 403 else 'unavailable'
        )
        shown = detail or message
        return json_error(shown, status, resolved)
    return error_document(status, detail)


def _app_error_response(error: AppError):
    return error_response(error.status, error.message, error.code, error)


def _legacy_redirect():
    """A browser GET of an old server-rendered page goes to its React route; anything else is a 404."""
    if request.method != 'GET':
        return None
    path = (request.path or '/').rstrip('/') or '/'
    if path.startswith(('/api', '/admin/api', '/mobile-sync', '/static')):
        return None
    from ui.pages import react_path
    target = react_path(path)
    if target == '/' or target == path:
        return None
    return redirect(target)


@error_handlers_bp.app_errorhandler(404)
def not_found_error(_error):
    return _legacy_redirect() or error_response(404)


@error_handlers_bp.app_errorhandler(403)
def forbidden_error(_error):
    return error_response(403)


@error_handlers_bp.app_errorhandler(500)
def internal_error(_error):
    return error_response(500)


@error_handlers_bp.app_errorhandler(AppError)
def app_error(error):
    return _app_error_response(error)


@error_handlers_bp.app_errorhandler(Exception)
def handle_exception(error):
    if isinstance(error, AppError):
        return _app_error_response(error)
    current_app.logger.exception('Unhandled exception')
    if isinstance(error, HTTPException):
        return error
    return error_response(500, error=error)
