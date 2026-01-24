"""
Error handlers for admin routes
"""

from flask import Blueprint, render_template, request
from werkzeug.exceptions import HTTPException

error_handlers_bp = Blueprint('errors', __name__)


@error_handlers_bp.app_errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    return render_template('admin/errors/404.html'), 404


@error_handlers_bp.app_errorhandler(403)
def forbidden_error(error):
    """Handle 403 errors"""
    return render_template('admin/errors/403.html'), 403


@error_handlers_bp.app_errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return render_template('admin/errors/500.html'), 500


@error_handlers_bp.app_errorhandler(Exception)
def handle_exception(error):
    """Handle all other exceptions"""
    # Log the error
    import traceback
    from flask import current_app
    
    current_app.logger.error(f"Unhandled exception: {str(error)}")
    current_app.logger.error(traceback.format_exc())
    
    # Return 500 for non-HTTP exceptions
    if isinstance(error, HTTPException):
        return error
    
    return render_template('admin/errors/500.html', error=str(error)), 500
