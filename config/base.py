import os
from datetime import timedelta
from dotenv import load_dotenv
from MySQLdb.cursors import DictCursor

basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
load_dotenv(os.path.join(basedir, '.env'))


def _first_existing_path(*candidates: str) -> str:
    """Return the first existing file path, else the first candidate."""
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[0]


def _path_from_env(name: str, *candidates: str) -> str:
    """Use the env path when that file exists. Otherwise use a moved default."""
    configured = os.environ.get(name)
    if configured and os.path.exists(configured):
        return configured
    return _first_existing_path(*candidates)


def _feature(name: str) -> bool:
    """FEATURE_<NAME> from the environment; on unless set to 0/false/no/off."""
    return os.environ.get(f'FEATURE_{name}', 'true').strip().lower() not in ('0', 'false', 'no', 'off')


class Config:
    """Set Flask configuration from environment variables."""

    # General Config
    SECRET_KEY = os.environ.get('SECRET_KEY')
    DEBUG = os.environ.get('DEBUG', 'False') == 'True'
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')

    # Base URL for production
    BASE_URL = os.environ.get('BASE_URL')
    
    # Database
    MYSQL_HOST = os.environ.get('MYSQL_HOST')
    MYSQL_USER = os.environ.get('MYSQL_USER')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
    MYSQL_DB = os.environ.get('MYSQL_DB')
    # One database per college. When set, this registry database's `tenants` table maps each
    # hostname to a tenant database and MYSQL_DB is not used; see docs/TENANCY.md.
    TENANT_REGISTRY_DB = os.environ.get('TENANT_REGISTRY_DB') or None
    TENANT_CACHE_SECONDS = int(os.environ.get('TENANT_CACHE_SECONDS', 30))
    # At startup and on /health, require the database to be at the newest migration.
    REQUIRE_MIGRATED_DB = os.environ.get('REQUIRE_MIGRATED_DB', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
    # MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))  # Flask-MySQLdb doesn't use this
    MYSQL_CURSORCLASS = DictCursor  # Must be a class, not a string!

    
    # Logging
    LOG_FILE = os.environ.get('LOG_FILE')

    # Timetable quality model
    QUALITY_MODEL_PATH = _path_from_env(
        'QUALITY_MODEL_PATH',
        os.path.join(basedir, 'ml_models', 'models', 'timetable_quality_model.json'),
        os.path.join(basedir, 'ml', 'models', 'timetable_quality_model.json'),
    )
    QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES = int(os.environ.get('QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES', 5))

    # File Uploads
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    
    # Session / CSRF settings (safe defaults for local development)
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_NAME = 'session'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # In development keep SESSION_COOKIE_SECURE False; set to True in production (HTTPS)
    SESSION_COOKIE_SECURE = False  # Must be False for HTTP (non-HTTPS)
    # CSRF settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = True
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 12
    WTF_CSRF_SSL_STRICT = False  # Disable SSL check for development
    WTF_CSRF_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']
    
    # Maintenance Mode
    MAINTENANCE_MODE = os.environ.get('MAINTENANCE_MODE', 'False') == 'True'
    
    # Institution Details
    INSTITUTION_NAME = os.environ.get('INSTITUTION_NAME')
    INSTITUTION_SHORT_NAME = os.environ.get('INSTITUTION_SHORT_NAME')
    INSTITUTION_EMAIL = os.environ.get('INSTITUTION_EMAIL')
    INSTITUTION_PHONE = os.environ.get('INSTITUTION_PHONE')
    INSTITUTION_ADDRESS = os.environ.get('INSTITUTION_ADDRESS')

    # Mobile sync integration
    MOBILE_SYNC_API_KEY = os.environ.get('MOBILE_SYNC_API_KEY')
    MOBILE_SYNC_ALLOW_LEGACY_API_KEY = os.environ.get('MOBILE_SYNC_ALLOW_LEGACY_API_KEY', 'False') == 'True'
    MOBILE_SYNC_SIGNATURE_WINDOW_SECONDS = int(os.environ.get('MOBILE_SYNC_SIGNATURE_WINDOW_SECONDS', 300))
    MOBILE_SYNC_DEFAULT_RATE_LIMIT_PER_MINUTE = int(os.environ.get('MOBILE_SYNC_DEFAULT_RATE_LIMIT_PER_MINUTE', 120))
    MOBILE_SYNC_ATTENDANCE_RATE_LIMIT_MULTIPLIER = int(os.environ.get('MOBILE_SYNC_ATTENDANCE_RATE_LIMIT_MULTIPLIER', 5))

    # Face embedding generation (registration/backend ML)
    MOBILE_FACE_EMBEDDING_ENABLED = os.environ.get('MOBILE_FACE_EMBEDDING_ENABLED', 'True') == 'True'
    MOBILE_FACE_EMBEDDING_REQUIRE_SUCCESS = os.environ.get('MOBILE_FACE_EMBEDDING_REQUIRE_SUCCESS', 'True') == 'True'
    MOBILEFACENET_MODEL_PATH = _path_from_env(
        'MOBILEFACENET_MODEL_PATH',
        os.path.join(basedir, 'ml_models', 'models', 'face-recognition', 'mobilefacenet.tflite'),
        os.path.join(basedir, 'ml', 'models', 'face-recognition', 'mobilefacenet.tflite'),
        os.path.join(basedir, 'assets', 'mobilefacenet.tflite'),
    )
    YOLO_FACE_DETECTOR_MODEL_PATH = _path_from_env(
        'YOLO_FACE_DETECTOR_MODEL_PATH',
        os.path.join(basedir, 'ml_models', 'models', 'face-recognition', 'yolov8n_float32.tflite'),
        os.path.join(basedir, 'ml', 'models', 'face-recognition', 'yolov8n_float32.tflite'),
        os.path.join(basedir, 'assets', 'yolov8n_float32.tflite'),
    )
    FACE_DETECT_CONF_THRESHOLD = float(os.environ.get('FACE_DETECT_CONF_THRESHOLD') or 0.5)
    FACE_DETECT_IOU_THRESHOLD = float(os.environ.get('FACE_DETECT_IOU_THRESHOLD') or 0.45)
    FACE_TEMPLATE_MIN_QUALITY = float(os.environ.get('FACE_TEMPLATE_MIN_QUALITY') or 0.55)

    # Face data safeguards (docs/FACE_ATTENDANCE.md). Templates are encrypted at rest with FACE_TEMPLATE_KEY
    # (a Fernet key from `flask face generate-key`); FACE_TEMPLATE_KEY_PREVIOUS is read during `flask face rotate-key`.
    FACE_TEMPLATE_KEY = os.environ.get('FACE_TEMPLATE_KEY') or None
    FACE_TEMPLATE_KEY_PREVIOUS = os.environ.get('FACE_TEMPLATE_KEY_PREVIOUS') or None
    # Enrolment and recognition need an active face_consents row for the person and this notice version.
    FACE_CONSENT_REQUIRED = os.environ.get('FACE_CONSENT_REQUIRED', 'True').strip().lower() not in ('0', 'false', 'no', 'off')
    FACE_CONSENT_NOTICE_VERSION = (os.environ.get('FACE_CONSENT_NOTICE_VERSION') or '2026-01').strip()
    # Templates of people who withdrew consent or left (inactive users) are deleted by the nightly job after this many
    # days; 0 deletes them on the next pass.
    FACE_RETENTION_DAYS = int(os.environ.get('FACE_RETENTION_DAYS', 30))
    # Passive liveness: recognitions below this confidence, below this liveness score (when the device sends one),
    # repeating a frame hash seen within FACE_DUPLICATE_FRAME_SECONDS, or matched against a template older than
    # FACE_TEMPLATE_MAX_AGE_DAYS (0 = no limit) are logged and rejected.
    FACE_MIN_CONFIDENCE = float(os.environ.get('FACE_MIN_CONFIDENCE') or 0.70)
    FACE_MIN_LIVENESS = float(os.environ.get('FACE_MIN_LIVENESS') or 0.50)
    FACE_DUPLICATE_FRAME_SECONDS = int(os.environ.get('FACE_DUPLICATE_FRAME_SECONDS', 600))
    FACE_TEMPLATE_MAX_AGE_DAYS = int(os.environ.get('FACE_TEMPLATE_MAX_AGE_DAYS', 730))
    # Devices can only mark a lecture the teacher opened (lecture_sessions.session_code) when this is on.
    FACE_REQUIRE_SESSION_CODE = os.environ.get('FACE_REQUIRE_SESSION_CODE', 'False').strip().lower() in ('1', 'true', 'yes', 'on')
    FACE_SESSION_CODE_MINUTES = int(os.environ.get('FACE_SESSION_CODE_MINUTES', 90))

    # Export and timetable queue workers, close-day and the retrainer inside this process. Set False on the
    # gunicorn web tier and run `flask workers run` as its own service (docs/RUNBOOK.md).
    BACKGROUND_WORKERS = os.environ.get('BACKGROUND_WORKERS', 'True').strip().lower() not in ('0', 'false', 'no', 'off')
    # Running job rows whose heartbeat is older than this are requeued by the next worker pass.
    JOB_STALE_SECONDS = int(os.environ.get('JOB_STALE_SECONDS', 900))
    # The worker process writes this file every WORKERS_HEARTBEAT_SECONDS; /health reports it, and with
    # REQUIRE_WORKERS=true answers 503 when it is missing or older than WORKERS_STALE_SECONDS.
    WORKERS_HEARTBEAT_FILE = os.environ.get('WORKERS_HEARTBEAT_FILE') or None
    WORKERS_HEARTBEAT_SECONDS = int(os.environ.get('WORKERS_HEARTBEAT_SECONDS', 30))
    WORKERS_STALE_SECONDS = int(os.environ.get('WORKERS_STALE_SECONDS', 180))
    REQUIRE_WORKERS = os.environ.get('REQUIRE_WORKERS', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    # /health answers 503 when the upload volume has less free space than this (0 turns the check off).
    HEALTH_MIN_FREE_MB = int(os.environ.get('HEALTH_MIN_FREE_MB', 500))
    # Root log handlers app_factory installs. LOG_FORMAT=json writes one JSON object per line with the request id.
    CONFIGURE_LOGGING = True
    LOG_FORMAT = (os.environ.get('LOG_FORMAT') or 'text').strip().lower()
    LOG_LEVEL = (os.environ.get('LOG_LEVEL') or 'INFO').strip().upper()
    # Error alerting: ERROR and above are posted as JSON to ALERT_WEBHOOK_URL and/or mailed to ALERT_MAIL_TO
    # (comma separated) through SMTP_*. The same message is sent at most once per ALERT_QUIET_SECONDS.
    ALERT_WEBHOOK_URL = os.environ.get('ALERT_WEBHOOK_URL') or None
    ALERT_MAIL_TO = os.environ.get('ALERT_MAIL_TO') or None
    ALERT_QUIET_SECONDS = int(os.environ.get('ALERT_QUIET_SECONDS', 600))
    # Outgoing mail (alerts now, notifications later).
    SMTP_HOST = os.environ.get('SMTP_HOST') or None
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USER = os.environ.get('SMTP_USER') or None
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD') or None
    SMTP_FROM = os.environ.get('SMTP_FROM') or None
    SMTP_STARTTLS = os.environ.get('SMTP_STARTTLS', 'true').strip().lower() not in ('0', 'false', 'no', 'off')

    # Notifications outbox (docs/NOTIFICATIONS.md). Mail goes through the tenant's SMTP account from the
    # settings page when one is set, else SMTP_* above. Stored SMTP passwords are encrypted with
    # SETTINGS_ENCRYPTION_KEY (a Fernet key), else FACE_TEMPLATE_KEY, else a key derived from SECRET_KEY.
    NOTIFICATIONS_ENABLED = os.environ.get('NOTIFICATIONS_ENABLED', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
    NOTIFICATION_MAX_ATTEMPTS = int(os.environ.get('NOTIFICATION_MAX_ATTEMPTS', 5))
    NOTIFICATION_RETRY_SECONDS = int(os.environ.get('NOTIFICATION_RETRY_SECONDS', 300))
    NOTIFICATION_POLL_SECONDS = int(os.environ.get('NOTIFICATION_POLL_SECONDS', 15))
    SETTINGS_ENCRYPTION_KEY = os.environ.get('SETTINGS_ENCRYPTION_KEY') or None

    # Integrations (docs/INTEGRATIONS.md): the public /api/v1 is authenticated by per-tenant API keys and rate
    # limited per key; webhooks are delivered from the webhook_deliveries outbox with signed retries. Endpoint
    # secrets and the SSO client secret are encrypted at rest like SMTP passwords.
    PUBLIC_API_LIMIT_PER_MINUTE = int(os.environ.get('PUBLIC_API_LIMIT_PER_MINUTE', 600))
    WEBHOOKS_ENABLED = os.environ.get('WEBHOOKS_ENABLED', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
    WEBHOOK_MAX_ATTEMPTS = int(os.environ.get('WEBHOOK_MAX_ATTEMPTS', 8))
    WEBHOOK_POLL_SECONDS = int(os.environ.get('WEBHOOK_POLL_SECONDS', 10))
    WEBHOOK_TIMEOUT_SECONDS = int(os.environ.get('WEBHOOK_TIMEOUT_SECONDS', 10))
    WEBHOOK_ALLOW_HTTP = os.environ.get('WEBHOOK_ALLOW_HTTP', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    WEBHOOK_ALLOW_PRIVATE = os.environ.get('WEBHOOK_ALLOW_PRIVATE', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    # OIDC SSO is configured per tenant from the Integrations page; this is the redirect URL base when the
    # request's host should not be trusted (behind a proxy without X-Forwarded-Host).
    SSO_REDIRECT_BASE_URL = os.environ.get('SSO_REDIRECT_BASE_URL') or None

    # Joint timetable solver (CP-SAT): wall-clock budget per generation job.
    TIMETABLE_SOLVER_SECONDS = float(os.environ.get('TIMETABLE_SOLVER_SECONDS', 20))

    # Capabilities (docs/DESIGN_CAPABILITIES.md): optional features. Each is on only when its server flag
    # FEATURE_<NAME> is on (the operator's kill switch, default on) AND the tenant turned it on from
    # Settings -> Capabilities (or its registry default is on and no row was saved). FEATURE_<NAME>=false
    # hides the feature for every tenant on this server regardless of their choice.
    FEATURE_TIMETABLE_PREFERENCES = _feature('TIMETABLE_PREFERENCES')
    FEATURE_TIMETABLE_VERSIONS = _feature('TIMETABLE_VERSIONS')
    FEATURE_TIMETABLE_GRID = _feature('TIMETABLE_GRID')
    FEATURE_BOOKINGS = _feature('BOOKINGS')
    FEATURE_WORKLOAD_NORMS = _feature('WORKLOAD_NORMS')
    FEATURE_ACADEMIC_TERMS = _feature('ACADEMIC_TERMS')
    FEATURE_SYLLABUS = _feature('SYLLABUS')
    FEATURE_ASSESSMENTS = _feature('ASSESSMENTS')
    FEATURE_EXAMS = _feature('EXAMS')
    FEATURE_TWO_FACTOR = _feature('TWO_FACTOR')
    FEATURE_PRIVACY_TOOLS = _feature('PRIVACY_TOOLS')
    FEATURE_CHANNELS = _feature('CHANNELS')
    FEATURE_GUARDIANS = _feature('GUARDIANS')
    FEATURE_CALENDAR_FEEDS = _feature('CALENDAR_FEEDS')
    FEATURE_ATTENDANCE_POLICIES = _feature('ATTENDANCE_POLICIES')

    # Optional SQL run on every new app connection (mysql-connector init_command).
    MYSQL_INIT_COMMAND = None

    # Sign-in lock, per account: this many wrong passwords within the window lock it for SIGN_IN_LOCK_MINUTES.
    SIGN_IN_MAX_FAILED_ATTEMPTS = int(os.environ.get('SIGN_IN_MAX_FAILED_ATTEMPTS', 5))
    SIGN_IN_FAILURE_WINDOW_MINUTES = int(os.environ.get('SIGN_IN_FAILURE_WINDOW_MINUTES', 15))
    SIGN_IN_LOCK_MINUTES = int(os.environ.get('SIGN_IN_LOCK_MINUTES', 15))
    # Sign-in POSTs per 10 minutes, per address and username and per address, and unknown usernames
    # per address per SIGN_IN_FAILURE_WINDOW_MINUTES.
    SIGN_IN_LIMIT_PER_ACCOUNT = int(os.environ.get('SIGN_IN_LIMIT_PER_ACCOUNT', 10))
    SIGN_IN_LIMIT_PER_ADDRESS = int(os.environ.get('SIGN_IN_LIMIT_PER_ADDRESS', 300))
    SIGN_IN_UNKNOWN_LIMIT_PER_ADDRESS = int(os.environ.get('SIGN_IN_UNKNOWN_LIMIT_PER_ADDRESS', 20))
    # Reverse proxies in front of the app whose X-Forwarded-For and X-Forwarded-Proto are trusted. 0 trusts none.
    TRUSTED_PROXY_COUNT = int(os.environ.get('TRUSTED_PROXY_COUNT', 0))
    # Local hour at which the close-day worker records not_marked for yesterday's unmarked lectures. -1 turns it off.
    ATTENDANCE_CLOSE_DAY_HOUR = int(os.environ.get('ATTENDANCE_CLOSE_DAY_HOUR', 1))
    # Minimum attendance percentage. Students below it are defaulters; "classes needed" aims at it.
    ATTENDANCE_THRESHOLD_PERCENT = os.environ.get('ATTENDANCE_THRESHOLD_PERCENT', '75')
    # Offline license (docs/RUNBOOK.md). Off by default: a server with no license file is unchanged.
    LICENSE_REQUIRED = os.environ.get('LICENSE_REQUIRED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    LICENSE_FILE = os.environ.get('LICENSE_FILE') or os.path.join(basedir, 'license.json')
    # Tests inject the matching public key. Production uses the key embedded in core/license.py.
    LICENSE_PUBLIC_KEY = os.environ.get('LICENSE_PUBLIC_KEY') or None


