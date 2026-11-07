"""Browser and API error responses. Page HTML is served by the React app."""

from flask import Blueprint, current_app, request
from werkzeug.exceptions import HTTPException

from core.exceptions import AppError
from api.web.responses import json_error
from ui.pages import page_response

error_handlers_bp = Blueprint('errors', __name__)


def error_response(status, message='The page could not be loaded.', code=None):
    """Return the current JSON error for API paths and the React response for pages."""
    path = request.path or ''
    if path.startswith('/api') or path.startswith('/admin/api') or path.startswith('/mobile-sync'):
        resolved = code if code is not None else (
            'not_found' if status == 404 else 'forbidden' if status == 403 else 'unavailable'
        )
        return json_error(message, status, resolved)
    return page_response()


def _app_error_response(error: AppError):
    """Map an application error onto the current response."""
    return error_response(error.status, error.message, error.code)


@error_handlers_bp.app_errorhandler(404)
def not_found_error(_error):
    return error_response(404)


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
    return error_response(500)
