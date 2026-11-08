"""
Database connection utility using mysql-connector-python.
Production-grade database connection management.

Connection settings come from the active Flask app's config when there is an
app context, so create_app(config) selects the database. Outside an app
context the module-level Config is used.
"""
import mysql.connector
from mysql.connector import Error
from flask import current_app, g, has_app_context
from config import Config
import logging

logger = logging.getLogger(__name__)


def connection_settings():
    """Return host, user, password and database from the active config, plus MYSQL_INIT_COMMAND when set."""
    if has_app_context():
        read = current_app.config.get
    else:
        def read(name):
            return getattr(Config, name, None)
    settings = {
        'host': read('MYSQL_HOST'),
        'user': read('MYSQL_USER'),
        'password': read('MYSQL_PASSWORD'),
        'database': read('MYSQL_DB'),
    }
    if read('MYSQL_INIT_COMMAND'):
        settings['init_command'] = read('MYSQL_INIT_COMMAND')
    return settings


def get_db_connection():
    """
    Get a new database connection using mysql-connector-python.
    This creates a fresh connection for each call - suitable for long-running operations.
    
    Returns:
        mysql.connector.connection.MySQLConnection: Database connection
        
    Raises:
        Error: If connection fails
    """
    try:
        connection = mysql.connector.connect(**connection_settings(), autocommit=False)
        return connection
    except Error as e:
        logger.error(f"Database connection failed: {e}")
        raise


def get_db():
    """
    Get database connection from Flask's g object (request-scoped).
    Connection is reused within the same request.
    
    Returns:
        tuple: (connection, cursor)
    """
    if 'db' not in g:
        try:
            g.db = mysql.connector.connect(**connection_settings(), autocommit=False)
            g.cursor = g.db.cursor(dictionary=True)
        except Error as e:
            logger.error(f"Database connection failed: {e}")
            raise
    return g.db, g.cursor


def close_db(e=None):
    """Close database connection stored in Flask's g object."""
    cursor = g.pop('cursor', None)
    db = g.pop('db', None)
    if cursor:
        cursor.close()
    if db:
        db.close()
