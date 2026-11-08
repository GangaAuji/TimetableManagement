"""Semester reads and saves. Callers pass values; this module does not read the request."""


from models.db import get_db_connection as _shared_connection
from data_access.academic_years import fetch_academic_years
from data_access.semesters import (
    delete_semester,
    fetch_classes,
    fetch_semesters,
    insert_semester,
    update_semester,
)


def _connect():
    """Open the same direct connection the academic screens use."""
    return _shared_connection()


def _normalize_semesters(semesters):
    """Make credit and date fields safe for the semester page."""
    try:
        import decimal as _decimal
        from datetime import date, datetime
        for semester in semesters:
            for key in ('min_credits', 'max_credits'):
                if key in semester and isinstance(semester[key], _decimal.Decimal):
                    semester[key] = float(semester[key])
            for key in ('start_date', 'end_date'):
                value = semester.get(key)
                if isinstance(value, (date, datetime)):
                    semester[key] = value.isoformat()
    except Exception:
        pass
    try:
        import decimal as _decimal
        for semester in semesters:
            for key in ('min_credits', 'max_credits'):
                if key in semester and isinstance(semester[key], _decimal.Decimal):
                    semester[key] = float(semester[key])
    except Exception:
        pass


def list_semesters():
    """Return semesters, academic years, and classes for the semester page."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        semesters = fetch_semesters(cursor)
        _normalize_semesters(semesters)
        return semesters, fetch_academic_years(cursor), fetch_classes(cursor)
    finally:
        cursor.close()
        connection.close()


def create_semester(academic_year_id, semester_number, semester_name, start_date, end_date, class_id, is_current, min_credits, max_credits):
    """Insert a semester. Several semesters may stay current. Return an error string on failure."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        insert_semester(
            cursor, academic_year_id, semester_number, semester_name, start_date, end_date,
            class_id, is_current, min_credits, max_credits,
        )
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def change_semester(semester_id, academic_year_id, semester_number, semester_name, start_date, end_date, class_id, is_current, min_credits, max_credits):
    """Update a semester without clearing other current rows. Return an error string on failure."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        update_semester(
            cursor, semester_id, academic_year_id, semester_number, semester_name, start_date, end_date,
            class_id, is_current, min_credits, max_credits,
        )
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def remove_semester(semester_id):
    """Delete a semester. Return an error string when the delete fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        delete_semester(cursor, semester_id)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()
