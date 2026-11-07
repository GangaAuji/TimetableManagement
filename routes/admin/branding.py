from flask import Blueprint, request, redirect, url_for, flash, current_app, session
from ui.pages import render_template
from flask_mysqldb import MySQL
from datetime import datetime
from functools import wraps
from services.branding import (
    allowed_file,
    init_branding_settings,
    load_branding_settings,
    reset_branding_settings,
    save_branding_settings,
)

branding_bp = Blueprint('branding', __name__, url_prefix='/admin/branding')
mysql = MySQL()

def has_permission(permission_name):
    """Decorator to check if user has specific permission"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'danger')
                return redirect(url_for('auth.login'))
            
            user_role = session.get('role')
            if user_role == 'Super Admin':
                return f(*args, **kwargs)
            
            from security import check_user_permission
            user_id = session.get('user_id')
            has_perm, _, _ = check_user_permission(user_id, permission_name)
            
            if not has_perm:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('auth.dashboard'))
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

@branding_bp.route('/')
@has_permission('admin_view_settings')
def manage_branding():
    """Display branding settings page"""
    return render_template('admin/manage_branding.html', settings=load_branding_settings())

@branding_bp.route('/update', methods=['POST'])
@has_permission('admin_change_settings')
def update_branding():
    """Update branding settings"""
    save_branding_settings(request.form, request.files)
    return redirect(url_for('branding.manage_branding'))

@branding_bp.route('/reset', methods=['POST'])
@has_permission('admin_change_settings')
def reset_branding():
    """Reset branding to default values"""
    reset_branding_settings()
    return redirect(url_for('branding.manage_branding'))

# Initialize settings on module load
_initialized = False

def init_app(app):
    """Initialize branding module with app"""
    @app.before_request
    def ensure_branding_initialized():
        """Ensure branding settings are initialized on first request"""
        global _initialized
        if not _initialized:
            try:
                init_branding_settings()
                _initialized = True
            except Exception as e:
                app.logger.error(f"Error during branding initialization: {str(e)}")
                # Don't fail requests if branding init fails
