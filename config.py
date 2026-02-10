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


