from flask import Flask, session, send_from_directory
from flask_wtf.csrf import CSRFError
from config import Config
from core.runtime import loaded_for_cli_command
from core.schema.cli import register_commands as register_schema_commands
from core.schema.status import database_reason
from extensions import close_db, configure_migrations, csrf, get_db_connection
import logging
from logging.handlers import RotatingFileHandler
import os
import secrets
import threading
import time
from datetime import timedelta

from utils.dates import format_hhmm


def _start_quality_model_retrainer(app):
    """Run periodic quality-model retraining in a background daemon thread."""

    interval_minutes = int(app.config.get('QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES', 180))
    if interval_minutes <= 0:
        app.logger.info('Quality model retrainer disabled (interval=%s).', interval_minutes)
        return

    model_path = app.config.get('QUALITY_MODEL_PATH')

    def retrain_loop():
        while True:
            try:
                with app.app_context():
                    from ml_models.scoring.learned_predictor import train_quality_model_from_database

                    result = train_quality_model_from_database(
                        model_path=model_path,
                        logger=app.logger,
                    )
                    if result.get('status') == 'trained':
                        app.logger.info(
                            'Quality model retrained: samples=%s acc=%s path=%s',
                            result.get('sample_count'),
                            result.get('training_accuracy'),
                            result.get('model_path'),
                        )
                    else:
                        app.logger.debug('Quality model retrain skipped: %s', result)
            except Exception as retrain_error:
                app.logger.warning('Periodic quality model retrain failed: %s', str(retrain_error))

            time.sleep(max(60, interval_minutes * 60))

    worker = threading.Thread(target=retrain_loop, name='quality-model-retrainer', daemon=True)
    worker.start()
    # app.logger.info('Started quality model retrainer thread (interval=%d min).', interval_minutes)

def format_time_filter(time_obj):
    """Jinja filter to format time/timedelta objects to HH:MM string"""
    return format_hhmm(time_obj)

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

def _configure_logging(app):
    """Capture all log output to LOG_FILE and the console. Replaces the root logger's handlers."""
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


def create_app(config=None):
    """Create and configure an instance of the Flask application.

    `config` is a config class or a mapping. Without it the module-level Config is used.
    """
    # Keep the import name "app" so static files, templates, and the logger stay where they are.
    app = Flask('app')
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable cache for static files
    if config is None:
        app.config.from_object(Config)
    elif isinstance(config, dict):
        app.config.from_object(Config)
        app.config.update(config)
    else:
        app.config.from_object(config)
    if app.config.get('TESTING'):
        from config.testing import test_database_problem

        problem = test_database_problem(app.config.get('MYSQL_DB'))
        if problem:
            raise RuntimeError(f'Refusing to create a testing app: {problem}')
    proxies = int(app.config.get('TRUSTED_PROXY_COUNT') or 0)
    if proxies > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies)
    # Set when a `flask` command other than `run` loads the app: no background workers start.
    app.config['CLI_COMMAND'] = loaded_for_cli_command()
    
    # Ensure we have a secret key
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = secrets.token_hex(32)

    # Ensure the upload folder exists by checking for 'UPLOAD_FOLDER'
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    # Initialize extensions
    csrf.init_app(app)
    configure_migrations(app)
    register_schema_commands(app)
    
    # Register database teardown
    app.teardown_appcontext(close_db)
    
    # Test MySQL connection
    # app.logger.info(f"MySQL Config - HOST: {app.config.get('MYSQL_HOST')}, USER: {app.config.get('MYSQL_USER')}, DB: {app.config.get('MYSQL_DB')}")
    
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

    if app.config.get('CONFIGURE_LOGGING', True):
        _configure_logging(app)
    if app.config['CLI_COMMAND']:
        logging.getLogger('mysql.connector').setLevel(logging.WARNING)

    @app.before_request
    def limit_request_rate():
        from security.rate_limit import enforce_rate_limit
        return enforce_rate_limit()

    @app.before_request
    def protect_admin_posts():
        """Block an unsigned admin form post. Sign-in itself stays on /admin/login."""
        from flask import request
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None
        path = (request.path or '/').rstrip('/') or '/'
        if path == '/admin/login' or path.startswith('/api/') or path.startswith('/mobile-sync'):
            return None
        if path == '/admin' or path.startswith('/admin/'):
            if 'user_id' not in session:
                return 'Authentication required.', 401
        return None

    # Setup session activity tracking
    @app.before_request
    def ensure_session_cookie():
        """Ensure Flask creates a session cookie on every request"""
        if not session.get('_csrf_initialized'):
            session['_csrf_initialized'] = True
            session.modified = True
    
    @app.before_request
    def track_session_activity():
        from security.sessions import session_activity_tracker
        session_activity_tracker()
    
    # Maintenance mode middleware
    @app.before_request
    def check_maintenance_mode():
        from flask import request, session
        
        # Skip maintenance check for static files and health check
        if request.path.startswith('/static/') or request.path == '/health':
            return None
        
        # Check if maintenance mode is enabled
        if app.config.get('MAINTENANCE_MODE', False):
            # Allow Super Admin access during maintenance
            if session.get('role') == 'Super Admin':
                return None
            
            # Show maintenance page for all other users
            return 'The system is temporarily unavailable.', 503
        
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
        from routes.auth import auth_bp
        from routes.academic import academic_bp
        from routes.user_management import user_mgmt_bp
        from routes.profile import profile_bp
        from routes.faculty import teacher_bp
        from routes.faculty.attendance import attendance_bp
        from routes.students import student_bp
        from api.mobile.v1 import mobile_sync_bp
        
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
            branding,
            mobile_devices_bp
        )
        from routes.admin.attendance_admin import attendance_admin_bp
        from routes.admin.reports import reports_bp
        from api.web import json_api_bp

        # Register core blueprints
        app.register_blueprint(auth_bp)
        app.register_blueprint(academic_bp)
        app.register_blueprint(user_mgmt_bp)
        app.register_blueprint(profile_bp)
        
        # Register role-specific blueprints
        app.register_blueprint(teacher_bp)
        app.register_blueprint(attendance_bp)
        app.register_blueprint(student_bp)
        app.register_blueprint(mobile_sync_bp)
        csrf.exempt(mobile_sync_bp)
        
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
        app.register_blueprint(mobile_devices_bp)
        app.register_blueprint(json_api_bp)
        
        # Register error handlers
        from ui.errors import error_handlers_bp
        app.register_blueprint(error_handlers_bp)
        
        # app.logger.info("Blueprints registered successfully.")

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        from flask import flash, jsonify, redirect, request, url_for
        app.logger.warning('CSRF validation failed for %s', request.path)
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'error': {'code': 'forbidden', 'message': 'The request was blocked.'},
            }), 403
        flash('Session expired or invalid request. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

    # Register template helpers for permission checks
    from utils.template_helpers import register_template_helpers
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
        from flask import jsonify
        maintenance = bool(app.config.get('MAINTENANCE_MODE', False))
        reason = database_reason(get_db_connection) if app.config.get('REQUIRE_MIGRATED_DB') else None
        if reason:
            return jsonify({"status": "unavailable", "reason": reason, "maintenance_mode": maintenance}), 503
        return jsonify({
            "status": "healthy",
            "maintenance_mode": maintenance,
        })

    if app.config['CLI_COMMAND']:
        return app

    if app.config.get('REQUIRE_MIGRATED_DB'):
        with app.app_context():
            reason = database_reason(get_db_connection)
        if reason:
            app.logger.error('Database schema check failed: %s /health will return 503 until this is fixed.', reason)

    should_start_worker = (not app.config.get('DEBUG', False)) or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if should_start_worker:
        _start_quality_model_retrainer(app)
    
    # app.logger.info("College Timetable Management System application created.")
    return app
