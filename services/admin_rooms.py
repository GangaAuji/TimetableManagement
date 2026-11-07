"""Admin room list and saves. This module does not read the request."""

from flask import current_app, flash

from data_access.admin_rooms import (
    delete_room_row,
    fetch_other_room_number,
    fetch_room,
    fetch_room_number,
    fetch_room_schedule,
    fetch_room_timetable_use,
    fetch_room_utilization,
    fetch_rooms,
    insert_room,
    update_room_row,
)
from data_access.departments import fetch_department_choices
from extensions import get_db_connection
from utils.dates import format_hhmm


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def list_rooms():
    """Return rooms and department choices. The connection stays open."""
    connection, cursor = _cursor()
    departments = [{'id': row['id'], 'name': row['name']} for row in fetch_department_choices(cursor)]
    rooms = []
    for row in fetch_rooms(cursor):
        rooms.append({
            'id': row['id'],
            'room_number': row['room_number'],
            'room_type': row['room_type'],
            'capacity': row['capacity'],
            'department_id': row['department_id'],
            'department_name': row['department_name'],
        })
    cursor.close()
    return rooms, departments


def find_room(room_id):
    """Return a room payload and status. The connection stays open."""
    connection, cursor = _cursor()
    row = fetch_room(cursor, room_id)
    cursor.close()
    if not row:
        return {'ok': False, 'error': 'Room not found'}, 404
    return {
        'id': row['id'],
        'room_number': row['room_number'],
        'room_type': row['room_type'],
        'capacity': row['capacity'],
        'department_id': row['department_id'],
    }, 200


def _clean_room(room_number, room_type, capacity, department_id):
    room_number = (room_number or '').strip() if room_number is not None else ''
    room_type = (room_type or '').strip() if room_type is not None else ''
    department_id = department_id or None
    if not room_number or not room_type or not capacity:
        return None, ({'ok': False, 'error': 'Room number, type, and capacity are required.'}, 400)
    try:
        capacity = int(capacity)
        if capacity < 1:
            raise ValueError()
    except ValueError:
        return None, ({'ok': False, 'error': 'Capacity must be a positive number.'}, 400)
    return (room_number, room_type, capacity, department_id), None


def create_room(room_number, room_type, capacity, department_id):
    """Create a room. A duplicate number is returned without rolling back."""
    cleaned, error = _clean_room(room_number, room_type, capacity, department_id)
    if error:
        return error
    room_number, room_type, capacity, department_id = cleaned
    connection, cursor = _cursor()
    try:
        if fetch_room_number(cursor, room_number):
            return {'ok': False, 'error': 'Room number already exists.'}, 400
        insert_room(cursor, room_number, room_type, capacity, department_id)
        connection.commit()
        flash('Room added successfully.', 'success')
        return {'ok': True}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error creating room: {str(exc)}")
        return {'ok': False, 'error': 'Failed to create room.'}, 500
    finally:
        cursor.close()
        connection.close()


def change_room(room_id, room_number, room_type, capacity, department_id):
    """Update a room. A duplicate number is returned without rolling back."""
    cleaned, error = _clean_room(room_number, room_type, capacity, department_id)
    if error:
        return error
    room_number, room_type, capacity, department_id = cleaned
    connection, cursor = _cursor()
    try:
        if fetch_other_room_number(cursor, room_number, room_id):
            return {'ok': False, 'error': 'Room number already exists.'}, 400
        update_room_row(cursor, room_number, room_type, capacity, department_id, room_id)
        connection.commit()
        flash('Room updated successfully.', 'success')
        return {'ok': True}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error updating room: {str(exc)}")
        return {'ok': False, 'error': 'Failed to update room.'}, 500
    finally:
        cursor.close()
        connection.close()


def remove_room(room_id):
    """Delete a room that is not used by the timetable."""
    connection, cursor = _cursor()
    try:
        if fetch_room_timetable_use(cursor, room_id):
            return {'ok': False, 'error': 'Cannot delete room: it is used in timetable entries.'}, 400
        delete_room_row(cursor, room_id)
        connection.commit()
        flash('Room deleted successfully.', 'success')
        return {'ok': True}, 200
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error deleting room: {str(exc)}")
        return {'ok': False, 'error': 'Failed to delete room.'}, 500
    finally:
        cursor.close()
        connection.close()


def room_schedule(room_id):
    """Return the formatted schedule for one room."""
    connection, cursor = _cursor()
    try:
        schedule = []
        for row in fetch_room_schedule(cursor, room_id):
            schedule.append({
                'day': row['day_of_week'],
                'start_time': format_hhmm(row['start_time']),
                'end_time': format_hhmm(row['end_time']),
                'subject_name': row['subject_name'],
                'class_name': row['class_name'],
                'division_name': row['division_name'],
                'faculty_name': row['faculty_name'] or '',
            })
        return {'ok': True, 'schedule': schedule}, 200
    except Exception as exc:
        current_app.logger.error(f"Error fetching room schedule: {str(exc)}")
        return {'ok': False, 'error': 'Failed to fetch schedule.'}, 500
    finally:
        cursor.close()
        connection.close()


def room_utilization_rows():
    """Return utilization rows, or an empty list when the query fails."""
    connection, cursor = _cursor()
    try:
        try:
            rows = fetch_room_utilization(cursor)
            has_rooms = True
        except Exception:
            rows = []
            has_rooms = False
    finally:
        cursor.close()
        connection.close()
    return rows, has_rooms
