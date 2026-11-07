"""Course-batch reads and saves for the academic screen. This module does not read the request."""

import mysql.connector

from config import Config
from data_access.academic_years import fetch_academic_years
from data_access.batches import delete_batch, fetch_batches, insert_batch, update_batch
from data_access.subjects import fetch_active_courses


def _connect():
    """Open the same direct connection the academic screens use."""
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
    )


def list_batches():
    """Return batches, active courses, and academic years."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        return fetch_batches(cursor), fetch_active_courses(cursor), fetch_academic_years(cursor)
    finally:
        cursor.close()
        connection.close()


def create_batch(course_id, batch_name, academic_year_id, start_year, end_year, total_students, current_semester, is_active):
    """Insert a batch. Return an error string when the save fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        insert_batch(
            cursor, course_id, batch_name, academic_year_id, start_year, end_year,
            total_students, current_semester, is_active,
        )
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def change_batch(batch_id, course_id, batch_name, academic_year_id, start_year, end_year, total_students, current_semester, is_active):
    """Update a batch. Return an error string when the save fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        update_batch(
            cursor, batch_id, course_id, batch_name, academic_year_id, start_year, end_year,
            total_students, current_semester, is_active,
        )
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def remove_batch(batch_id):
    """Delete a batch. Return an error string when the delete fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        delete_batch(cursor, batch_id)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()
