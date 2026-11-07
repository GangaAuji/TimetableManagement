"""Room inventory API. Rules match the existing admin rooms screens."""

import re

from flask import current_app, request

from extensions import get_db_connection
from core.db import transaction
from routes.admin_utils import format_time
from api.web.access import allowed, permission_denied
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

ROOM_TYPES = ('Classroom', 'Laboratory', 'Conference', 'Auditorium')
ROOM_FIELDS = frozenset(('room_number', 'room_type', 'capacity', 'department_id'))
_ROOM_NUMBER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ./-]{0,19}$')

_ERROR_MESSAGES = {
    'invalid_body': 'The room could not be saved.',
    'room_number_invalid': 'Enter a room number using letters, numbers, spaces, or - / .',
    'room_type_invalid': 'Choose a valid room type.',
    'capacity_invalid': 'Capacity must be a positive number.',
    'department_invalid': 'Choose a valid department, or leave the room shared.',
    'room_number_taken': 'Room number already exists.',
    'room_not_found': 'That room was not found.',
    'room_in_use': 'Cannot delete room: it is used in timetable entries.',
}


class _RoomInputError(Exception):
    def __init__(self, code):
        self.code = code


def _permission_error(permission_name):
    return permission_denied(
        permission_name,
        'rooms_unavailable',
        'The room list could not be loaded.',
        log_message='Room permission check failed: %s',
        include_error=True,
    )


def _can(permission_name):
    return allowed(permission_name)


def _input_error(code):
    return json_error(_ERROR_MESSAGES.get(code, 'The room could not be saved.'), 400, code)


def _room_number(value):
    number = safe_text(value, 20)
    if not _ROOM_NUMBER.match(number):
        raise _RoomInputError('room_number_invalid')
    return number


def _room_type(value):
    if value not in ROOM_TYPES:
        raise _RoomInputError('room_type_invalid')
    return value


def _capacity(value):
    number = safe_count(value)
    if isinstance(value, bool) or number < 1 or number > 10000 or safe_text(value, 6) != str(number):
        raise _RoomInputError('capacity_invalid')
    return number


def _department_id(cursor, value):
    if value in (None, '', 0):
        return None
    department_id = safe_count(value)
    if department_id < 1 or safe_text(value, 12) != str(department_id):
        raise _RoomInputError('department_invalid')
    cursor.execute('SELECT 1 FROM departments WHERE id = %s', (department_id,))
    if cursor.fetchone() is None:
        raise _RoomInputError('department_invalid')
    return department_id


def _public_room(row):
    return {
        'id': safe_count(row.get('id')),
        'room_number': safe_text(row.get('room_number'), 20),
        'room_type': row.get('room_type') if row.get('room_type') in ROOM_TYPES else '',
        'capacity': safe_count(row.get('capacity')),
        'department_id': safe_count(row.get('department_id')) or None,
        'department_name': safe_text(row.get('department_name'), 120),
    }


def register_room_routes(blueprint):
    @blueprint.route('/rooms', methods=['GET'])
    def list_rooms():
        denied = _permission_error('rooms_view_room')
        if denied is not None:
            return denied

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT id, name FROM departments ORDER BY name')
            departments = []
            for row in cursor.fetchall():
                name = safe_text(row.get('name'), 120)
                department_id = safe_count(row.get('id'))
                if department_id and name:
                    departments.append({'id': department_id, 'name': name})

            cursor.execute(
                """
                SELECT r.id, r.room_number, r.room_type, r.capacity, r.department_id,
                       d.name AS department_name
                FROM rooms r
                LEFT JOIN departments d ON r.department_id = d.id
                ORDER BY r.room_type, r.room_number
                """
            )
            rooms = [_public_room(row) for row in cursor.fetchall() if safe_count(row.get('id'))]
            return json_ok({
                'rooms': rooms,
                'departments': departments,
                'permissions': {
                    'add': _can('rooms_add_room'),
                    'change': _can('rooms_change_room'),
                    'delete': _can('rooms_delete_room'),
                },
            })
        except Exception as exc:
            current_app.logger.exception('Room list failed: %s', exc)
            return json_error('The room list could not be loaded.', 500, 'rooms_unavailable')
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    @blueprint.route('/rooms/<int:room_id>', methods=['GET'])
    def get_room(room_id):
        denied = _permission_error('rooms_view_room')
        if denied is not None:
            return denied
        return _read_room(room_id)

    @blueprint.route('/rooms', methods=['POST'])
    def create_room():
        denied = _permission_error('rooms_add_room')
        if denied is not None:
            return denied
        payload = _room_payload()
        if isinstance(payload, tuple):
            return payload
        return _save_room(payload, room_id=None)

    @blueprint.route('/rooms/<int:room_id>', methods=['PUT'])
    def update_room(room_id):
        denied = _permission_error('rooms_change_room')
        if denied is not None:
            return denied
        payload = _room_payload()
        if isinstance(payload, tuple):
            return payload
        return _save_room(payload, room_id=room_id)

    @blueprint.route('/rooms/<int:room_id>', methods=['DELETE'])
    def delete_room(room_id):
        denied = _permission_error('rooms_delete_room')
        if denied is not None:
            return denied

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT 1 FROM rooms WHERE id = %s', (room_id,))
            if cursor.fetchone() is None:
                return json_error(_ERROR_MESSAGES['room_not_found'], 404, 'room_not_found')
            cursor.execute('SELECT 1 FROM timetable WHERE room_id = %s LIMIT 1', (room_id,))
            if cursor.fetchone():
                return json_error(_ERROR_MESSAGES['room_in_use'], 400, 'room_in_use')
            cursor.execute('DELETE FROM rooms WHERE id = %s', (room_id,))
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except Exception as exc:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Room delete failed: %s', exc)
            return json_error('The room could not be deleted.', 500, 'rooms_unavailable')
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

    @blueprint.route('/rooms/<int:room_id>/schedule', methods=['GET'])
    def room_schedule(room_id):
        denied = _permission_error('rooms_view_room')
        if denied is not None:
            return denied

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT room_number FROM rooms WHERE id = %s', (room_id,))
            room = cursor.fetchone()
            if room is None:
                return json_error(_ERROR_MESSAGES['room_not_found'], 404, 'room_not_found')
            cursor.execute(
                """
                SELECT t.day_of_week, t.start_time, t.end_time,
                       s.name AS subject_name,
                       c.name AS class_name,
                       d.name AS division_name,
                       f.name AS faculty_name
                FROM timetable t
                JOIN subjects s ON t.subject_id = s.id
                JOIN classes c ON t.class_id = c.id
                JOIN divisions d ON t.division_id = d.id
                LEFT JOIN faculty f ON t.faculty_id = f.id
                WHERE t.room_id = %s
                ORDER BY FIELD(t.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'),
                         t.start_time
                """,
                (room_id,),
            )
            schedule = []
            for row in cursor.fetchall():
                schedule.append({
                    'day': safe_text(row.get('day_of_week'), 20),
                    'start_time': safe_text(format_time(row.get('start_time')), 20),
                    'end_time': safe_text(format_time(row.get('end_time')), 20),
                    'subject_name': safe_text(row.get('subject_name'), 160),
                    'class_name': safe_text(row.get('class_name'), 120),
                    'division_name': safe_text(row.get('division_name'), 80),
                    'faculty_name': safe_text(row.get('faculty_name'), 160),
                })
            return json_ok({
                'room_number': safe_text(room.get('room_number'), 20),
                'schedule': schedule,
            })
        except Exception as exc:
            current_app.logger.exception('Room schedule failed: %s', exc)
            return json_error('The schedule could not be loaded.', 500, 'rooms_unavailable')
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()


def _read_room(room_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT r.id, r.room_number, r.room_type, r.capacity, r.department_id,
                   d.name AS department_name
            FROM rooms r
            LEFT JOIN departments d ON r.department_id = d.id
            WHERE r.id = %s
            """,
            (room_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return json_error(_ERROR_MESSAGES['room_not_found'], 404, 'room_not_found')
        return json_ok(_public_room(row))
    except Exception as exc:
        current_app.logger.exception('Room lookup failed: %s', exc)
        return json_error('The room could not be loaded.', 500, 'rooms_unavailable')
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def _room_payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - ROOM_FIELDS:
        return _input_error('invalid_body')
    return payload


def _save_room(payload, room_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        room_number = _room_number(payload.get('room_number'))
        room_type = _room_type(payload.get('room_type'))
        capacity = _capacity(payload.get('capacity'))
        department_id = _department_id(cursor, payload.get('department_id'))

        if room_id is None:
            cursor.execute('SELECT 1 FROM rooms WHERE room_number = %s', (room_number,))
        else:
            cursor.execute('SELECT 1 FROM rooms WHERE id = %s', (room_id,))
            if cursor.fetchone() is None:
                return json_error(_ERROR_MESSAGES['room_not_found'], 404, 'room_not_found')
            cursor.execute(
                'SELECT 1 FROM rooms WHERE room_number = %s AND id != %s',
                (room_number, room_id),
            )
        if cursor.fetchone():
            return json_error(_ERROR_MESSAGES['room_number_taken'], 400, 'room_number_taken')

        if room_id is None:
            cursor.execute(
                'INSERT INTO rooms (room_number, room_type, capacity, department_id) VALUES (%s, %s, %s, %s)',
                (room_number, room_type, capacity, department_id),
            )
        else:
            cursor.execute(
                """
                UPDATE rooms
                SET room_number = %s, room_type = %s, capacity = %s, department_id = %s
                WHERE id = %s
                """,
                (room_number, room_type, capacity, department_id, room_id),
            )
        connection.commit()
        return json_ok({'saved': True})
    except _RoomInputError as exc:
        return _input_error(exc.code)
    except Exception as exc:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Room save failed: %s', exc)
        return json_error('The room could not be saved.', 500, 'rooms_unavailable')
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
