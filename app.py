from flask import Flask, session
from flask_mysqldb import MySQL
from flask_wtf.csrf import CSRFProtect, CSRFError
from config import Config
import logging
from logging.handlers import RotatingFileHandler
import os
import secrets
from datetime import timedelta

# Initialize extensions
mysql = MySQL()
csrf = CSRFProtect()

def format_time_filter(time_obj):
    """Jinja filter to format time/timedelta objects to HH:MM string"""
    if time_obj is None:
        return ''
    if isinstance(time_obj, timedelta):
        # Convert timedelta to hours:minutes
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}'
    elif hasattr(time_obj, 'strftime'):
        # datetime.time or datetime.datetime object
        return time_obj.strftime('%H:%M')
    else:
        return str(time_obj)

def format_time_12hr_filter(time_obj):
    """Jinja filter to format time/timedelta objects to 12-hour format (HH:MM AM/PM)"""
    if time_obj is None:
        return ''
    if isinstance(time_obj, timedelta):
        # Convert timedelta to hours:minutes
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        # Convert to 12-hour format
        period = 'AM' if hours < 12 else 'PM'
        display_hour = hours % 12
        if display_hour == 0:
            display_hour = 12
        return f'{display_hour:02d}:{minutes:02d} {period}'
    elif hasattr(time_obj, 'strftime'):
        # datetime.time or datetime.datetime object
        return time_obj.strftime('%I:%M %p')
    else:
        return str(time_obj)

def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Ensure we have a secret key
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = secrets.token_hex(32)

    # Ensure the upload folder exists by checking for 'UPLOAD_FOLDER'
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    # Initialize extensions
    mysql.init_app(app)
    csrf.init_app(app)

    # Register custom Jinja filters
    app.jinja_env.filters['format_time'] = format_time_filter
    app.jinja_env.filters['format_time_12hr'] = format_time_12hr_filter

    # Register global template functions
    @app.template_global()
    def has_user_permission(permission_name, department_id=None):
        """Check if current user has a specific permission"""
        if 'user_id' not in session:
            return False
        
        user_id = session.get('user_id')
        user_role = session.get('role')
        
        # Super Admin has all permissions
        if user_role == 'Super Admin':
            return True
        
        from security import check_user_permission
        has_perm, _, _ = check_user_permission(user_id, permission_name, department_id)
        return has_perm
    
    @app.template_global()
    def get_user_accessible_departments():
        """Get departments the current user can access"""
        if 'user_id' not in session:
            return []
        
        from security import get_accessible_departments
        return get_accessible_departments(session.get('user_id'))

    # Setup Logging
    log_file = app.config.get('LOG_FILE', 'app.log')
    handler = RotatingFileHandler(log_file, maxBytes=10000, backupCount=3)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    with app.app_context():
        # Import and register blueprints
        from routes.auth_routes import auth_bp
        from routes.admin_routes import admin_bp
        from routes.academic_routes import academic_bp
        from routes.teacher_routes import teacher_bp
        from routes.student_routes import student_bp
        from routes.user_management_routes import user_mgmt_bp
        from routes.profile_routes import profile_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(admin_bp)
        app.register_blueprint(academic_bp)
        app.register_blueprint(teacher_bp)
        app.register_blueprint(student_bp)
        app.register_blueprint(user_mgmt_bp)
        app.register_blueprint(profile_bp)
        
        app.logger.info("Blueprints registered successfully.")

    # Handle CSRF errors with a friendly message and log diagnostics
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        # Log diagnostic information to help debug missing/invalid tokens
        app.logger.warning('CSRF Error: %s', getattr(e, 'description', repr(e)))
        try:
            from flask import request
            app.logger.debug('Request cookies: %s', request.cookies)
            app.logger.debug('Request form: %s', request.form)
            app.logger.debug('Request headers: %s', dict(request.headers))
        except Exception as log_exc:
            app.logger.debug('Error logging request details: %s', log_exc)

        # Redirect user back to the login page with a flash message
        from flask import flash, redirect, url_for
        flash('Session expired or invalid request (CSRF token). Please try again.', 'danger')
        return redirect(url_for('auth.login'))

    app.logger.info("College Timetable Management System application created.")
    return app

if __name__ == '__main__':
    app = create_app()
    # Make the app accessible on the local network and change port to 8080
    app.run(host='0.0.0.0', port=8080, debug=True)
    app.logger.info("Application started on port 8080.")

