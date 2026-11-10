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


def retrain_quality_model_once(app):
    """Retrain the learned timetable-quality model for every active tenant (or the single database)."""
    from core.tenancy import scoped_model_path, tenant_context, tenants_to_serve

    model_path = app.config.get('QUALITY_MODEL_PATH')
    try:
        tenants = tenants_to_serve(app)
    except Exception as registry_error:
        app.logger.warning('Quality model retrain could not list tenants: %s', str(registry_error))
        return
    for tenant in tenants:
        try:
            from ml_models.scoring.learned_predictor import train_quality_model_from_database

            with tenant_context(app, tenant):
                result = train_quality_model_from_database(
                    model_path=scoped_model_path(model_path),
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


def _start_quality_model_retrainer(app, force=False):
    """Run periodic quality-model retraining in a background daemon thread."""

    interval_minutes = int(app.config.get('QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES', 180))
    if interval_minutes <= 0:
        app.logger.info('Quality model retrainer disabled (interval=%s).', interval_minutes)
        return
    if not force and not app.config.get('BACKGROUND_WORKERS', True):
        return

    def retrain_loop():
        while True:
            retrain_quality_model_once(app)
            time.sleep(max(60, interval_minutes * 60))

    worker = threading.Thread(target=retrain_loop, name='quality-model-retrainer', daemon=True)
    worker.start()

def _database_problem(app):
    """Why the database(s) are not ready, or None. With a registry, every active tenant must be at head."""
    if not app.config.get('TENANT_REGISTRY_DB'):
        return database_reason(get_db_connection)
    from core.tenancy import tenant_context, tenants_to_serve

    try:
        tenants = tenants_to_serve(app)
    except Exception as exc:
        return f'The tenant registry is unreachable: {exc.__class__.__name__}.'
    for tenant in tenants:
        with tenant_context(app, tenant):
            reason = database_reason(get_db_connection)
        if reason:
            return f'Tenant {tenant.slug}: {reason}'
    return None


def _operational_checks(app, checks):
    """Disk space under the upload folder and the worker heartbeat. Yields (name, problem or None) and fills `checks`."""
    import shutil

    from services.worker_process import heartbeat_problem, read_heartbeat

    minimum_mb = int(app.config.get('HEALTH_MIN_FREE_MB', 0) or 0)
    try:
        free_mb = shutil.disk_usage(app.config['UPLOAD_FOLDER']).free // (1024 * 1024)
        checks['disk_free_mb'] = free_mb
        disk_problem = f'{free_mb} MB free under {app.config["UPLOAD_FOLDER"]}; the minimum is {minimum_mb} MB.' \
            if minimum_mb and free_mb < minimum_mb else None
    except OSError as exc:
        checks['disk_free_mb'] = None
        disk_problem = f'The upload folder is unreadable: {exc.__class__.__name__}.' if minimum_mb else None
    yield 'disk', disk_problem

    beat = read_heartbeat(app)
    checks['workers'] = {
        'heartbeat_age_seconds': beat['age_seconds'],
        'worker_id': beat.get('worker_id'),
        'threads': beat.get('threads'),
    } if beat else None
    yield 'workers', heartbeat_problem(app) if app.config.get('REQUIRE_WORKERS') else None

    from services.face.templates import key_problem

    face_key = key_problem(app.config)
    checks['face_key'] = 'configured' if face_key is None else 'missing'
    # Reported, not fatal: an installation without face attendance has no key and is still healthy.
    yield 'face_key', None

    checks['notifications'] = 'disabled' if not app.config.get('NOTIFICATIONS_ENABLED', True) else (
        'server-smtp' if app.config.get('SMTP_HOST') else 'tenant-smtp-or-none'
    )
    yield 'notifications', None

    from core.license import evaluate

    license_status = evaluate(app.config)
    if not license_status['required']:
        checks['license'] = 'not required'
        yield 'license', None
    else:
        checks['license'] = 'ok' if not license_status['problem'] else license_status['problem']
        yield 'license', license_status['problem']


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
    """Write errors to LOG_FILE. The console follows LOG_LEVEL. Replaces the root logger's handlers."""
    log_file = app.config.get('LOG_FILE', 'app.log')

    # Ensure logs directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    from core.observability import ContextFilter, alert_handler_from_config, make_formatter

    formatter = make_formatter(app.config.get('LOG_FORMAT'))
    context = ContextFilter()
    console_level = getattr(logging, str(app.config.get('LOG_LEVEL') or 'INFO'), logging.INFO)

    # The log file keeps errors. Debug and request traces stay off this file.
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=3)  # 10MB per file
    file_handler.setLevel(logging.ERROR)
    file_handler.addFilter(lambda record: record.levelno >= logging.ERROR)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context)

    # Console handler for terminal output (journald under systemd)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context)

    # DEBUG stays available for a console set to LOG_LEVEL=DEBUG.
    # The file handler above is what keeps app.log to errors.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Clear any existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Add handlers to root logger only (all child loggers will inherit)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    alerts = alert_handler_from_config(app.config)
    if alerts is not None:
        alerts.addFilter(context)
        root_logger.addHandler(alerts)

    # Set specific logger levels (they inherit handlers from root)
    app.logger.setLevel(logging.INFO)
    logging.getLogger('werkzeug').setLevel(logging.INFO)  # Request lines stay on the console
    for name in ('mysql.connector', 'MySQLdb'):
        logging.getLogger(name).setLevel(logging.ERROR)


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

        for setting in ('MYSQL_DB', 'TENANT_REGISTRY_DB'):
            if setting == 'TENANT_REGISTRY_DB' and not app.config.get(setting):
                continue
            problem = test_database_problem(app.config.get(setting))
            if problem:
                raise RuntimeError(f'Refusing to create a testing app: {setting}: {problem}')
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
        if app.config.get('TENANT_REGISTRY_DB'):
            return
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

    # First hooks: a request id on every request, then (with a tenant registry) the college by hostname,
    # before anything opens a database.
    from core.observability import install_request_ids
    from core.tenancy.request import install as install_tenant_resolution

    install_request_ids(app)
    app.config['TENANCY_ENABLED'] = install_tenant_resolution(app)

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
        """Ensure Flask creates a session cookie on every request (not for the key-authenticated public API)."""
        from flask import request
        if (request.path or '').startswith('/api/v1'):
            return
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
        from ui.maintenance import maintenance_allows, maintenance_response

        if not app.config.get('MAINTENANCE_MODE', False):
            return None
        if maintenance_allows(request.path, request.method, session.get('role'), 'user_id' in session):
            return None
        return maintenance_response(request.path)
    
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
        # One request path only: sign-in/sign-out forms and the SSO
        # callback stay on ``auth_bp``; every screen is served by the
        # React bundle talking to ``/api``. Legacy page URLs are redirected
        # by ``ui.errors`` (see ``ui.pages.page_response``).
        from routes.auth import auth_bp
        from api.mobile.v1 import mobile_sync_bp
        from api.v1 import public_api_bp
        from api.web import json_api_bp
        from ui.errors import error_handlers_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(mobile_sync_bp)
        csrf.exempt(mobile_sync_bp)
        app.register_blueprint(public_api_bp)
        csrf.exempt(public_api_bp)
        app.register_blueprint(json_api_bp)
        app.register_blueprint(error_handlers_bp)

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
        payload = {"status": "healthy", "maintenance_mode": maintenance, "checks": {}}
        if app.config.get('TENANT_REGISTRY_DB'):
            payload['tenancy'] = 'registry'
        reason = _database_problem(app) if app.config.get('REQUIRE_MIGRATED_DB') else None
        payload['checks']['database'] = reason or 'ok'
        if reason:
            payload.update(status='unavailable', reason=reason)
            return jsonify(payload), 503
        for name, problem in _operational_checks(app, payload['checks']):
            if problem:
                payload.update(status='unavailable', reason=f'{name}: {problem}')
                return jsonify(payload), 503
        return jsonify(payload)

    if app.config['CLI_COMMAND']:
        return app

    if app.config.get('REQUIRE_MIGRATED_DB'):
        with app.app_context():
            reason = _database_problem(app)
        if reason:
            app.logger.error('Database schema check failed: %s /health will return 503 until this is fixed.', reason)

    # flask run with the debugger on eager-loads the app in the reloader supervisor,
    # then leaves that process running forever. Workers and their log handlers belong
    # in the child (WERKZEUG_RUN_MAIN), which is the process that actually serves.
    from flask.helpers import get_debug_flag

    reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_reloader = bool(app.config.get('DEBUG', False)) or get_debug_flag()
    should_start_worker = reloader_child or not debug_reloader
    if should_start_worker:
        _start_quality_model_retrainer(app)
        from services.attendance_jobs import ensure_worker as ensure_close_day_worker
        from services.notifications import ensure_worker as ensure_notification_worker
        from services.webhooks import ensure_worker as ensure_webhook_worker

        ensure_close_day_worker(app)
        ensure_notification_worker(app)
        ensure_webhook_worker(app)
    
    # app.logger.info("College Timetable Management System application created.")
    return app
