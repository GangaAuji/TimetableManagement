"""Room inventory API. Rules match the existing admin rooms screens."""

import re

from flask import current_app, request, session

from extensions import get_db_connection
from core.db import transaction
from core.scope import current_scope
from data_access import institutions as institutions_store
from utils.dates import format_hhmm as format_time
from api.web.access import InputError, allowed, id_list, institution_input, permission_denied, sharing_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

ROOM_TYPES = ('Classroom', 'Laboratory', 'Conference', 'Auditorium')
ROOM_FIELDS = frozenset(('room_number', 'room_type', 'capacity', 'department_id', 'institution_id', 'sharing', 'shared_with'))
_ROOM_NUMBER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ./-]{0,19}$')

_ERROR_MESSAGES = {
    'invalid_body': 'The room could not be saved.',
    'room_number_invalid': 'Enter a room number using letters, numbers, spaces, or - / .',
    'room_type_invalid': 'Choose a valid room type.',
    'capacity_invalid': 'Capacity must be a positive number.',
    'department_invalid': 'Choose a valid department, or leave the room shared.',
    'institution_invalid': 'Choose an institution you manage.',
    'sharing_invalid': 'Sharing must be private, listed or organization.',
    'shared_with_invalid': 'Choose the institutions this room is listed to.',
    'room_number_taken': 'Room number already exists.',
    'room_not_found': 'That room was not found.',
    'room_not_owned': 'Only the institution that owns this room can change it.',
    'room_in_use': 'Cannot delete room: it is used in timetable entries.',
}

_ROOM_SELECT = """
    SELECT r.id, r.room_number, r.room_type, r.capacity, r.department_id, r.institution_id, r.sharing,
           d.name AS department_name, i.name AS institution_name, i.short_name AS institution_short_name
    FROM rooms r
    LEFT JOIN departments d ON r.department_id = d.id
    JOIN institutions i ON i.id = r.institution_id
"""


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


def _department_id(cursor, value, institution_id):
    """A department of the room's own institution, or none for a room not tied to one."""
    if value in (None, '', 0):
        return None
    department_id = safe_count(value)
    if department_id < 1 or safe_text(value, 12) != str(department_id):
        raise _RoomInputError('department_invalid')
    cursor.execute('SELECT 1 FROM departments WHERE id = %s AND institution_id = %s', (department_id, institution_id))
    if cursor.fetchone() is None:
        raise _RoomInputError('department_invalid')
    return department_id


def _public_room(row, scope, shares=None):
    institution_id = safe_count(row.get('institution_id')) or None
    item = {
        'id': safe_count(row.get('id')),
        'room_number': safe_text(row.get('room_number'), 20),
        'room_type': row.get('room_type') if row.get('room_type') in ROOM_TYPES else '',
        'capacity': safe_count(row.get('capacity')),
        'department_id': safe_count(row.get('department_id')) or None,
        'department_name': safe_text(row.get('department_name'), 120),
        'institution_id': institution_id,
        'institution_name': safe_text(row.get('institution_name'), 150),
        'institution_short_name': safe_text(row.get('institution_short_name'), 40),
        'sharing': row.get('sharing') if row.get('sharing') in institutions_store.SHARING else 'private',
        'owned': scope.allows(institution_id),
    }
    if shares is not None:
        item['shared_with'] = [safe_count(value) for value in shares.get(item['id'], [])]
    return item


def _owned(cursor, room_id, scope):
    """The room row when the scope may change it; a JSON error otherwise."""
    cursor.execute('SELECT id, institution_id FROM rooms WHERE id = %s', (room_id,))
    row = cursor.fetchone()
    if row is None:
        return json_error(_ERROR_MESSAGES['room_not_found'], 404, 'room_not_found')
    if not scope.allows(row.get('institution_id')):
        return json_error(_ERROR_MESSAGES['room_not_owned'], 403, 'room_not_owned')
    return row


def _institution_choices(cursor, scope):
    if not scope.multiple:
        return []
    rows = institutions_store.fetch_institutions(cursor, active_only=True)
    return [
        {'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 150), 'short_name': safe_text(row.get('short_name'), 40)}
        for row in rows
    ]


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
            scope = current_scope(cursor)
            department_clause, department_params = scope.clause('institution_id')
            cursor.execute(
                f'SELECT id, name, institution_id FROM departments WHERE {department_clause} ORDER BY name',
                department_params,
            )
            departments = []
            for row in cursor.fetchall():
                name = safe_text(row.get('name'), 120)
                department_id = safe_count(row.get('id'))
                if department_id and name:
                    departments.append({'id': department_id, 'name': name, 'institution_id': safe_count(row.get('institution_id')) or None})

            # Own rooms plus those other institutions let this one use.
            clause, params = scope.rooms_clause('r') if scope.institution_id is not None else scope.clause('r.institution_id')
            cursor.execute(f'{_ROOM_SELECT} WHERE {clause} ORDER BY r.room_type, r.room_number', params)
            rows = [row for row in cursor.fetchall() if safe_count(row.get('id'))]
            shares = institutions_store.fetch_shares_for(cursor, 'room', [row['id'] for row in rows]) if scope.multiple else {}
            rooms = [_public_room(row, scope, shares) for row in rows]
            return json_ok({
                'rooms': rooms,
                'departments': departments,
                'institutions': _institution_choices(cursor, scope),
                'institution_id': scope.institution_id,
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
            owned = _owned(cursor, room_id, current_scope(cursor))
            if isinstance(owned, tuple):
                return owned
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
        scope = current_scope(cursor)
        # Same visibility as the list: owned rooms, plus rooms shared to the chosen institution.
        clause, params = scope.rooms_clause('r') if scope.institution_id is not None else scope.clause('r.institution_id')
        cursor.execute(f'{_ROOM_SELECT} WHERE r.id = %s AND {clause}', (room_id, *params))
        row = cursor.fetchone()
        if row is None:
            return json_error(_ERROR_MESSAGES['room_not_found'], 404, 'room_not_found')
        shares = institutions_store.fetch_shares_for(cursor, 'room', [room_id]) if scope.multiple else {}
        return json_ok(_public_room(row, scope, shares))
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
        scope = current_scope(cursor)
        room_number = _room_number(payload.get('room_number'))
        room_type = _room_type(payload.get('room_type'))
        capacity = _capacity(payload.get('capacity'))

        existing = None
        if room_id is not None:
            existing = _owned(cursor, room_id, scope)
            if isinstance(existing, tuple):
                return existing
        institution_id = institution_input(
            cursor, scope, payload.get('institution_id'), existing=existing['institution_id'] if existing else None,
        )
        department_id = _department_id(cursor, payload.get('department_id'), institution_id)
        sharing = sharing_input(payload.get('sharing'))
        shared_with = id_list(payload.get('shared_with'), 'shared_with_invalid') if sharing == 'listed' else []
        shared_with = [item for item in shared_with if item != institution_id]
        if shared_with:
            marks = ', '.join(['%s'] * len(shared_with))
            cursor.execute(f'SELECT COUNT(*) AS n FROM institutions WHERE id IN ({marks})', tuple(shared_with))
            if int(cursor.fetchone()['n']) != len(shared_with):
                raise _RoomInputError('shared_with_invalid')

        if room_id is None:
            cursor.execute('SELECT 1 FROM rooms WHERE room_number = %s', (room_number,))
        else:
            cursor.execute(
                'SELECT 1 FROM rooms WHERE room_number = %s AND id != %s',
                (room_number, room_id),
            )
        if cursor.fetchone():
            return json_error(_ERROR_MESSAGES['room_number_taken'], 400, 'room_number_taken')

        if room_id is None:
            cursor.execute(
                'INSERT INTO rooms (room_number, room_type, capacity, department_id, institution_id, sharing) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (room_number, room_type, capacity, department_id, institution_id, sharing),
            )
            room_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE rooms
                SET room_number = %s, room_type = %s, capacity = %s, department_id = %s, institution_id = %s, sharing = %s
                WHERE id = %s
                """,
                (room_number, room_type, capacity, department_id, institution_id, sharing, room_id),
            )
        institutions_store.replace_shares(cursor, 'room', room_id, shared_with, created_by=session.get('user_id'))
        connection.commit()
        return json_ok({'saved': True, 'id': safe_count(room_id)})
    except (_RoomInputError, InputError) as exc:
        if connection is not None:
            connection.rollback()
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
