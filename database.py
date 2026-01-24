"""
Database connection utility using mysql-connector-python.
Production-grade database connection management.
"""
import mysql.connector
from mysql.connector import Error
from flask import current_app, g
from config import Config
import logging

logger = logging.getLogger(__name__)


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
        connection = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            autocommit=False
        )
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
            g.db = mysql.connector.connect(
                host=Config.MYSQL_HOST,
                user=Config.MYSQL_USER,
                password=Config.MYSQL_PASSWORD,
                database=Config.MYSQL_DB,
                autocommit=False
            )
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