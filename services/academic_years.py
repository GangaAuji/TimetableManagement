"""Academic year reads and saves. Callers pass values; this module does not read the request."""


from models.db import get_db_connection as _shared_connection
from data_access.academic_years import (
    clear_current_academic_years,
    delete_academic_year,
    fetch_academic_years,
    insert_academic_year,
    update_academic_year,
)


def _connect():
    """Open the same direct connection the academic screens use."""
    return _shared_connection()


def list_academic_years():
    """Return every academic year, newest start date first."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        return fetch_academic_years(cursor)
    finally:
        cursor.close()
        connection.close()


def create_academic_year(name, start_date, end_date, is_current, description):
    """Insert a year. Return an error string when the save fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        if is_current:
            clear_current_academic_years(cursor)
        insert_academic_year(cursor, name, start_date, end_date, is_current, description)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def change_academic_year(year_id, name, start_date, end_date, is_current, description):
    """Update a year. Return an error string when the save fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        if is_current:
            clear_current_academic_years(cursor, except_id=year_id)
        update_academic_year(cursor, year_id, name, start_date, end_date, is_current, description)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def remove_academic_year(year_id):
    """Delete a year. Return an error string when the delete fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        delete_academic_year(cursor, year_id)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()
