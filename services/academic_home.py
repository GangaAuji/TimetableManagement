"""Academic home reads. This module does not read the request."""

import mysql.connector

from config import Config
from data_access.academic_home import fetch_academic_home


def _connect():
    """Open the same direct connection the academic screens use."""
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
    )


def academic_home():
    """Return the academic home counts and the current year and semester."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        return fetch_academic_home(cursor)
    finally:
        cursor.close()
        connection.close()
