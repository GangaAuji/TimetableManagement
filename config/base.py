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

    # Export and timetable queue workers, and the root log handlers app_factory installs.
    BACKGROUND_WORKERS = True
    CONFIGURE_LOGGING = True

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


