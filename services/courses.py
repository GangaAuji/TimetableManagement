"""Course reads and saves for the academic screen. This module does not read the request."""

import mysql.connector

from config import Config
from data_access.courses import (
    count_active_courses,
    delete_course,
    fetch_active_departments,
    fetch_courses,
    insert_course,
    update_course,
)


def _connect():
    """Open the same direct connection the academic screens use."""
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB,
    )


def list_courses():
    """Return courses, active departments, and the active course count."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        course_count = count_active_courses(cursor)
        courses = fetch_courses(cursor)
        departments = fetch_active_departments(cursor)
        return courses, departments, course_count
    finally:
        cursor.close()
        connection.close()


def create_course(name, code, program, department_id, duration_years, total_semesters, description, is_active):
    """Insert a course. Return an error string when the save fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        insert_course(
            cursor, name, code, program, department_id, duration_years, total_semesters, description, is_active,
        )
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def change_course(course_id, name, code, program, department_id, duration_years, total_semesters, description, is_active):
    """Update a course. Return an error string when the save fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        update_course(
            cursor, course_id, name, code, program, department_id, duration_years,
            total_semesters, description, is_active,
        )
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def remove_course(course_id):
    """Delete a course. Return an error string when the delete fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        delete_course(cursor, course_id)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()
