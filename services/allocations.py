"""Faculty-allocation reads and saves. This module does not read the request."""


from models.db import get_db_connection as _shared_connection
from data_access.allocations import (
    delete_allocation,
    fetch_active_batches,
    fetch_active_faculty,
    fetch_allocations,
    fetch_divisions,
    fetch_faculty_user_id,
    fetch_subjects_by_name,
    insert_allocation,
    update_allocation,
)
from data_access.subjects import (
    fetch_active_courses,
    fetch_classes_by_display_order,
    fetch_semesters_by_number,
)


def _connect():
    """Open the same direct connection the academic screens use."""
    return _shared_connection()


def _normalize_allocations(allocations):
    """Turn hour and workload decimals into floats for the page."""
    try:
        import decimal as _decimal
        for allocation in allocations:
            for key in ('allocated_hours', 'workload_percentage'):
                if key in allocation and isinstance(allocation[key], _decimal.Decimal):
                    allocation[key] = float(allocation[key])
    except Exception:
        pass


def list_allocations(class_id, faculty_id, course_id):
    """Return allocations and the menus for the allocation page."""
    connection = _connect()
    cursor = connection.cursor(dictionary=True)
    try:
        allocations = fetch_allocations(cursor, class_id, faculty_id, course_id)
        _normalize_allocations(allocations)
        return (
            allocations,
            fetch_active_faculty(cursor),
            fetch_subjects_by_name(cursor),
            fetch_classes_by_display_order(cursor),
            fetch_divisions(cursor),
            fetch_semesters_by_number(cursor),
            fetch_active_batches(cursor),
            fetch_active_courses(cursor),
        )
    finally:
        cursor.close()
        connection.close()


def _faculty_user_id(cursor, faculty_id):
    """Return faculty.user_id, or None when the faculty row is missing."""
    faculty_row = fetch_faculty_user_id(cursor, faculty_id)
    if not faculty_row:
        return None
    return faculty_row[0]


def create_allocation(faculty_id, subject_id, class_id, division_id, semester_id, course_batch_id, allocated_hours, workload_percentage, is_primary, allocation_type, start_date, end_date, notes):
    """Insert an allocation. Return invalid_faculty, an error string, or None."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        faculty_user_id = _faculty_user_id(cursor, faculty_id)
        if faculty_user_id is None:
            return 'invalid_faculty'
        insert_allocation(cursor, (
            faculty_user_id, subject_id, class_id, division_id, semester_id, course_batch_id,
            allocated_hours, workload_percentage, is_primary, allocation_type,
            start_date, end_date, notes,
        ))
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def change_allocation(allocation_id, faculty_id, subject_id, class_id, division_id, semester_id, course_batch_id, allocated_hours, workload_percentage, is_primary, allocation_type, start_date, end_date, notes):
    """Update an allocation. Return invalid_faculty, an error string, or None."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        faculty_user_id = _faculty_user_id(cursor, faculty_id)
        if faculty_user_id is None:
            return 'invalid_faculty'
        update_allocation(cursor, (
            faculty_user_id, subject_id, class_id, division_id, semester_id, course_batch_id,
            allocated_hours, workload_percentage, is_primary, allocation_type,
            start_date, end_date, notes, allocation_id,
        ))
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()


def remove_allocation(allocation_id):
    """Delete an allocation. Return an error string when the delete fails."""
    connection = _connect()
    cursor = connection.cursor()
    try:
        delete_allocation(cursor, allocation_id)
        connection.commit()
        return None
    except Exception as exc:
        connection.rollback()
        return str(exc)
    finally:
        cursor.close()
        connection.close()
