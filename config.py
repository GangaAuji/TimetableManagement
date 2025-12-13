import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    """Set Flask configuration from environment variables."""

    # General Config
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key-that-is-hard-to-guess'
    
    # Database
    MYSQL_HOST = os.environ.get('MYSQL_HOST')
    MYSQL_USER = os.environ.get('MYSQL_USER')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
    MYSQL_DB = os.environ.get('MYSQL_DB')
    
    # Logging
    LOG_FILE = os.environ.get('LOG_FILE') or 'app.log'

    # File Uploads
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    
    # Session / CSRF settings (safe defaults for local development)
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    # In development keep SESSION_COOKIE_SECURE False; set to True in production (HTTPS)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
    # Disable CSRF token expiration for debugging (set a reasonable limit in production)
    WTF_CSRF_TIME_LIMIT = None

