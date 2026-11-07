"""Department reads and saves for the academic screen. This module does not read the request."""

import mysql.connector

from config import Config
from data_access.departments import (
    delete_department,
    fetch_departments,
    insert_department,
    update_department,
)


def _connect():
    """Open the same direct connection the academic screens use."""
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
    )


def list_departments():
    """Return departments with their course counts."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        return fetch_departments(cursor)
    finally:
        cursor.close()
        connection.close()


def create_department(name, code, description, head_of_department, is_active):
    """Insert a department. Return an error string when the save fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        insert_department(cursor, name, code, description, head_of_department, is_active)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def change_department(department_id, name, code, description, head_of_department, is_active):
    """Update a department. Return an error string when the save fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        update_department(cursor, department_id, name, code, description, head_of_department, is_active)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def remove_department(department_id):
    """Delete a department. Return an error string when the delete fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        delete_department(cursor, department_id)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()
