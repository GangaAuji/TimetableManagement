"""Shift patterns, change requests, and faculty availability."""

from flask import current_app, session

from extensions import get_db_connection
from api.web.access import InputError, allowed, body, close, optional_text, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_stamp, safe_text

_DAYS = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday', 7: 'Sunday'}
_MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'shifts_unavailable': 'The page could not be loaded.',
    'shift_request_invalid': 'Choose approve or reject.',
}


def register_shift_routes(blueprint):
    blueprint.add_url_rule('/shifts', 'shifts_list', patterns, methods=['GET'])
    blueprint.add_url_rule('/shift-requests', 'shift_requests', requests, methods=['GET'])
    blueprint.add_url_rule('/shift-requests/<int:request_id>', 'shift_request_respond', respond, methods=['POST'])
    blueprint.add_url_rule('/availability', 'shift_availability', availability, methods=['GET'])
    blueprint.add_url_rule('/portal/shifts', 'teacher_shifts', teacher, methods=['GET'])
    blueprint.add_url_rule('/portal/availability', 'teacher_availability', teacher, methods=['GET'])


def _day(value):
    if isinstance(value, bool):
        return ''
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        return _DAYS.get(int(value), safe_text(value, 12))
    return safe_text(value, 12)


def _view():
    return permission_denied('shifts_view', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])


def patterns():
    denied = _view()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, shift_name, shift_code, start_time, end_time, description, is_active
            FROM shift_patterns
            ORDER BY shift_order, shift_name
            """
        )
        shifts = [
            {
                'id': safe_count(row['id']),
                'name': safe_text(row.get('shift_name'), 80),
                'code': safe_text(row.get('shift_code') or '', 20),
                'start_time': safe_clock(row.get('start_time')),
                'end_time': safe_clock(row.get('end_time')),
                'description': safe_text(row.get('description') or '', 200),
                'is_active': bool(row.get('is_active')),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'shifts': shifts})
    except Exception:
        current_app.logger.exception('Shift list failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')
    finally:
        close(cursor, connection)


def requests():
    denied = _view()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT scr.id, scr.day_of_week, scr.current_shift_name, scr.requested_shift_name,
                   scr.reason, scr.status, scr.admin_response, scr.created_at,
                   f.name AS faculty_name, d.name AS department_name
            FROM shift_change_requests scr
            JOIN faculty f ON scr.faculty_id = f.user_id
            LEFT JOIN departments d ON f.department_id = d.id
            ORDER BY scr.created_at DESC
            LIMIT 80
            """
        )
        rows = [
            {
                'id': safe_count(row['id']),
                'faculty': safe_text(row.get('faculty_name'), 100),
                'department': safe_text(row.get('department_name') or '', 100),
                'day': _day(row.get('day_of_week')),
                'current_shift': safe_text(row.get('current_shift_name') or '', 80),
                'requested_shift': safe_text(row.get('requested_shift_name') or '', 80),
                'reason': safe_text(row.get('reason') or '', 300),
                'status': safe_text(row.get('status') or '', 20),
                'response': safe_text(row.get('admin_response') or '', 300),
                'created_at': safe_stamp(row.get('created_at')),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'requests': rows, 'can_respond': allowed('shifts_change')})
    except Exception:
        current_app.logger.exception('Shift requests failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')
    finally:
        close(cursor, connection)


def respond(request_id):
    denied = permission_denied('shifts_change', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(frozenset(('action', 'note')))
        action = payload.get('action')
        if action not in ('approve', 'reject'):
            raise InputError('shift_request_invalid')
        note = optional_text(payload.get('note'), 300, 'invalid_body')
        status = 'approved' if action == 'approve' else 'rejected'
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT faculty_id, day_of_week, requested_shift_name, status FROM shift_change_requests WHERE id = %s',
            (request_id,),
        )
        current = cursor.fetchone()
        if not current or current.get('status') != 'pending':
            return json_error('That request was not found.', 404, 'shifts_unavailable')
        cursor.execute(
            """
            UPDATE shift_change_requests
            SET status = %s, admin_response = %s, reviewed_by = %s, reviewed_at = NOW()
            WHERE id = %s AND status = 'pending'
            """,
            (status, note, session.get('user_id'), request_id),
        )
        if action == 'approve':
            requested = str(current.get('requested_shift_name') or '')
            needle = requested.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            cursor.execute(
                """
                SELECT id FROM shift_patterns
                WHERE shift_name LIKE %s OR shift_code LIKE %s
                LIMIT 1
                """,
                (f'%{needle}%', f'%{needle}%'),
            )
            shift = cursor.fetchone()
            cursor.execute(
                """
                INSERT INTO faculty_availability (faculty_id, day_of_week, is_available, shift_pattern_id, notes)
                VALUES (%s, %s, 1, %s, 'Approved shift change request')
                ON DUPLICATE KEY UPDATE
                    shift_pattern_id = VALUES(shift_pattern_id),
                    is_available = 1,
                    notes = 'Approved shift change request'
                """,
                (current['faculty_id'], current['day_of_week'], shift['id'] if shift else None),
            )
        connection.commit()
        return json_ok({'id': safe_count(request_id), 'status': status})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Shift request response failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')
    finally:
        close(cursor, connection)


def availability():
    denied = _view()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT f.name AS faculty_name, d.name AS department_name, fa.day_of_week,
                   fa.is_available, sp.shift_name,
                   COALESCE(fa.start_time, sp.start_time) AS start_time,
                   COALESCE(fa.end_time, sp.end_time) AS end_time
            FROM faculty_availability fa
            JOIN faculty f ON f.user_id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN shift_patterns sp ON sp.id = fa.shift_pattern_id
            ORDER BY f.name, fa.day_of_week
            LIMIT 200
            """
        )
        rows = [
            {
                'faculty': safe_text(row.get('faculty_name'), 100),
                'department': safe_text(row.get('department_name') or '', 100),
                'day': _day(row.get('day_of_week')),
                'shift': safe_text(row.get('shift_name') or '', 80),
                'start_time': safe_clock(row.get('start_time')),
                'end_time': safe_clock(row.get('end_time')),
                'available': 'Yes' if row.get('is_available') else 'No',
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'rows': rows})
    except Exception:
        current_app.logger.exception('Availability list failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')
    finally:
        close(cursor, connection)


def teacher():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Teacher':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT user_id FROM faculty WHERE id = %s OR user_id = %s LIMIT 1',
            (session.get('faculty_id') or 0, session.get('user_id')),
        )
        faculty = cursor.fetchone()
        if not faculty:
            return json_error(_MESSAGES['shifts_unavailable'], 404, 'shifts_unavailable')
        cursor.execute(
            """
            SELECT fa.day_of_week, fa.is_available, sp.shift_name,
                   COALESCE(fa.start_time, sp.start_time) AS start_time,
                   COALESCE(fa.end_time, sp.end_time) AS end_time
            FROM faculty_availability fa
            LEFT JOIN shift_patterns sp ON sp.id = fa.shift_pattern_id
            WHERE fa.faculty_id = %s
            ORDER BY fa.day_of_week
            """,
            (faculty['user_id'],),
        )
        rows = [
            {
                'day': _day(row.get('day_of_week')),
                'shift': safe_text(row.get('shift_name') or '', 80),
                'start_time': safe_clock(row.get('start_time')),
                'end_time': safe_clock(row.get('end_time')),
                'available': 'Yes' if row.get('is_available') else 'No',
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'shifts': rows})
    except Exception:
        current_app.logger.exception('Teacher shifts failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')
    finally:
        close(cursor, connection)
