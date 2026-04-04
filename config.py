import os
from datetime import timedelta
from dotenv import load_dotenv
from MySQLdb.cursors import DictCursor

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

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
    # MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))  # Flask-MySQLdb doesn't use this
    MYSQL_CURSORCLASS = DictCursor  # Must be a class, not a string!

    
    # Logging
    LOG_FILE = os.environ.get('LOG_FILE')

    # Timetable quality model
    QUALITY_MODEL_PATH = os.environ.get(
        'QUALITY_MODEL_PATH',
        os.path.join(basedir, 'ml', 'models', 'timetable_quality_model.json')
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
    WTF_CSRF_TIME_LIMIT = None  # Disable CSRF token expiration for debugging
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
    MOBILEFACENET_MODEL_PATH = os.environ.get(
        'MOBILEFACENET_MODEL_PATH',
        os.path.join(basedir, 'assets', 'mobilefacenet.tflite')
    )
    YOLO_FACE_DETECTOR_MODEL_PATH = os.environ.get(
        'YOLO_FACE_DETECTOR_MODEL_PATH',
        os.path.join(basedir, 'assets', 'yolov8n_float32.tflite')
    )
    FACE_DETECT_CONF_THRESHOLD = float(os.environ.get('FACE_DETECT_CONF_THRESHOLD'))
    FACE_DETECT_IOU_THRESHOLD = float(os.environ.get('FACE_DETECT_IOU_THRESHOLD'))
    FACE_TEMPLATE_MIN_QUALITY = float(os.environ.get('FACE_TEMPLATE_MIN_QUALITY'))


