"""Dropdown lookups for the academic screens. This module does not read the request."""


from models.db import get_db_connection as _shared_connection
from data_access.academic_lookups import (
    fetch_batches_by_course,
    fetch_courses_by_department,
    fetch_faculty_by_department,
    fetch_semesters_by_year,
    fetch_subjects_by_course,
)


def _connect():
    """Open the same direct connection the academic screens use."""
    return _shared_connection()


def _read(fetch, record_id):
    """Run one lookup and close the connection, even when the query fails."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        return fetch(cursor, record_id)
    finally:
        cursor.close()
        connection.close()


def courses_for_department(department_id):
    """Return active courses for a department."""
    return _read(fetch_courses_by_department, department_id)


def subjects_for_course(course_id):
    """Return subjects for a course."""
    return _read(fetch_subjects_by_course, course_id)


def faculty_for_department(department_id):
    """Return active faculty for a department."""
    return _read(fetch_faculty_by_department, department_id)


def semesters_for_year(academic_year_id):
    """Return semesters for an academic year."""
    return _read(fetch_semesters_by_year, academic_year_id)


def batches_for_course(course_id):
    """Return active batches for a course."""
    return _read(fetch_batches_by_course, course_id)
