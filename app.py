from flask import Flask, app, session, send_from_directory
from flask_wtf.csrf import CSRFProtect, CSRFError
from config import Config
from database import get_db_connection, close_db
import logging
from logging.handlers import RotatingFileHandler
import os
import secrets
from datetime import timedelta

# Initialize extensions
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
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable cache for static files
    app.config.from_object(Config)
    
    # Ensure we have a secret key
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = secrets.token_hex(32)

    # Ensure the upload folder exists by checking for 'UPLOAD_FOLDER'
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    # Initialize extensions
    csrf.init_app(app)
    
    # Register database teardown
    app.teardown_appcontext(close_db)
    
    # Test MySQL connection
    app.logger.info(f"MySQL Config - HOST: {app.config.get('MYSQL_HOST')}, USER: {app.config.get('MYSQL_USER')}, DB: {app.config.get('MYSQL_DB')}")
    
    @app.before_first_request
    def test_mysql_connection():
        """Test database connection on first request"""
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT 1 AS test")
            result = cursor.fetchone()
            cursor.close()
            connection.close()
            app.logger.info(f"[OK] MySQL connection successful - Test result: {result}")
        except Exception as e:
            app.logger.error(f"[ERROR] MySQL connection failed: {str(e)}")
            import traceback
            app.logger.error(f"Traceback: {traceback.format_exc()}")


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
    
    @app.context_processor
    def inject_branding():
        """Make branding settings and user profile available to all templates"""
        branding_settings = {}
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT setting_key, setting_value FROM branding_settings")
            settings = cursor.fetchall()
            for row in settings:
                branding_settings[row['setting_key']] = row['setting_value']
            cursor.close()
            connection.close()
        except:
            pass  # If table doesn't exist yet, use defaults
        
        # Ensure session always has current profile_photo from database
        if 'user_id' in session and 'profile_photo' not in session:
            try:
                connection = get_db_connection()
                cursor = connection.cursor(dictionary=True)
                cursor.execute("SELECT profile_photo FROM users WHERE id = %s", (session['user_id'],))
                result = cursor.fetchone()
                if result and result['profile_photo']:
                    session['profile_photo'] = result['profile_photo']
                else:
                    session['profile_photo'] = 'default-avatar.svg'
                cursor.close()
                connection.close()
            except:
                pass
        
        return dict(branding=branding_settings)

    # Setup Logging - Capture ALL terminal output to app.log
    log_file = app.config.get('LOG_FILE', 'app.log')
    
    # Ensure logs directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # File handler for all logs
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=3)  # 10MB per file
    file_handler.setLevel(logging.DEBUG)  # Capture everything
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Console handler for terminal output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Configure root logger (captures everything from all modules)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels
    
    # Clear any existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Add handlers to root logger only (all child loggers will inherit)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Set specific logger levels (they inherit handlers from root)
    app.logger.setLevel(logging.DEBUG)
    logging.getLogger('werkzeug').setLevel(logging.INFO)  # Flask dev server
    logging.getLogger('MySQLdb').setLevel(logging.WARNING)  # Only warnings/errors from DB

    # Setup session activity tracking
    @app.before_request
    def ensure_session_cookie():
        """Ensure Flask creates a session cookie on every request"""
        if not session.get('_csrf_initialized'):
            session['_csrf_initialized'] = True
            session.modified = True
    
    @app.before_request
    def track_session_activity():
        from session_manager import session_activity_tracker
        session_activity_tracker()
    
    # Maintenance mode middleware
    @app.before_request
    def check_maintenance_mode():
        from flask import request, render_template, session
        
        # Skip maintenance check for static files and health check
        if request.path.startswith('/static/') or request.path == '/health':
            return None
        
        # Check if maintenance mode is enabled
        if app.config.get('MAINTENANCE_MODE', False):
            # Allow Super Admin access during maintenance
            if session.get('role') == 'Super Admin':
                return None
            
            # Show maintenance page for all other users
            return render_template('maintenance.html'), 503
        
        return None
    
    # Make BASE_URL and institution details available in all templates
    @app.context_processor
    def inject_globals():
        return {
            'base_url': app.config.get('BASE_URL', ''),
            'institution_name': app.config.get('INSTITUTION_NAME', 'Institution'),
            'institution_short_name': app.config.get('INSTITUTION_SHORT_NAME', 'INST'),
            'institution_email': app.config.get('INSTITUTION_EMAIL', ''),
            'institution_phone': app.config.get('INSTITUTION_PHONE', ''),
        }
    
    with app.app_context():
        from routes.auth_routes import auth_bp
        from routes.academic_routes import academic_bp
        from routes.user_management_routes import user_mgmt_bp
        from routes.profile_routes import profile_bp
        from routes.faculty import teacher_bp
        from routes.faculty.attendance import attendance_bp
        from routes.students import student_bp
        
        # Import modular admin routes
        from routes.admin import (
            students_bp as admin_students_bp, 
            faculty_bp as admin_faculty_bp, 
            rooms_bp, 
            timetable_bp, 
            holiday_bp, 
            invitations_bp, 
            proxy_bp,
            audit_logs_bp,
            dashboard_bp,
            departments_bp,
            api_bp,
            permissions_bp,
            shift_management,
            branding
        )
        from routes.admin.attendance_admin import attendance_admin_bp
        from routes.admin.reports import reports_bp

        # Register core blueprints
        app.register_blueprint(auth_bp)
        app.register_blueprint(academic_bp)
        app.register_blueprint(user_mgmt_bp)
        app.register_blueprint(profile_bp)
        
        # Register role-specific blueprints
        app.register_blueprint(teacher_bp)
        app.register_blueprint(attendance_bp)
        app.register_blueprint(student_bp)
        
        # Register modular admin blueprints
        app.register_blueprint(admin_students_bp)
        app.register_blueprint(admin_faculty_bp)
        app.register_blueprint(rooms_bp)
        app.register_blueprint(timetable_bp)
        app.register_blueprint(holiday_bp)
        app.register_blueprint(invitations_bp)
        app.register_blueprint(proxy_bp)
        app.register_blueprint(shift_management.shift_bp)
        app.register_blueprint(attendance_admin_bp)
        app.register_blueprint(reports_bp)
        
        # Register security and utility admin blueprints
        app.register_blueprint(audit_logs_bp)
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(departments_bp)
        app.register_blueprint(api_bp)
        app.register_blueprint(permissions_bp)
        app.register_blueprint(branding.branding_bp)
        
        # Initialize branding settings
        branding.init_app(app)
        
        # Register error handlers
        from routes.admin.error_handlers import error_handlers_bp
        app.register_blueprint(error_handlers_bp)
        
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

    # Register template helpers for permission checks
    from template_helpers import register_template_helpers
    register_template_helpers(app)
    
    # Health check endpoint (bypasses maintenance mode)
    @app.route('/favicon.ico')
    def favicon():
        """Serve favicon from branding setting when available, otherwise fallback file."""
        favicon_file = 'favicon.png'

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT setting_value FROM branding_settings WHERE setting_key = 'favicon' LIMIT 1"
            )
            result = cursor.fetchone()
            cursor.close()
            connection.close()

            if result and result.get('setting_value'):
                candidate = str(result.get('setting_value')).lstrip('/\\')
                static_root = os.path.abspath(app.static_folder)
                candidate_path = os.path.abspath(os.path.join(static_root, candidate))

                # Ensure resolved path stays inside static folder.
                if candidate_path.startswith(static_root) and os.path.isfile(candidate_path):
                    favicon_file = candidate
        except Exception:
            pass

        return send_from_directory(app.static_folder, favicon_file)

    # Health check endpoint (bypasses maintenance mode)
    @app.route('/health')
    def health_check():
        from datetime import datetime
        from flask import jsonify
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "maintenance_mode": app.config.get('MAINTENANCE_MODE', False),
            "base_url": app.config.get('BASE_URL', ''),
            "institution": app.config.get('INSTITUTION_NAME', '')
        })
    
    app.logger.info("College Timetable Management System application created.")
    return app

if __name__ == '__main__':
    app = create_app()
    # Run locally for development
    app.run(host='127.0.0.1', port=5000, debug=app.config['DEBUG'])
    app.logger.info("Application started on port 5000.")

