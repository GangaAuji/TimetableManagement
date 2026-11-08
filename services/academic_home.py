"""Academic home reads. This module does not read the request."""


from models.db import get_db_connection as _shared_connection
from data_access.academic_home import fetch_academic_home


def _connect():
    """Open the same direct connection the academic screens use."""
    return _shared_connection()


def academic_home():
    """Return the academic home counts and the current year and semester."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        return fetch_academic_home(cursor)
    finally:
        cursor.close()
        connection.close()
