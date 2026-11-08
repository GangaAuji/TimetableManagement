"""Shift patterns, change requests, and faculty availability."""

import re

from flask import current_app, get_flashed_messages, session

from extensions import get_db_connection
from data_access.admin_shifts import count_shift_usage, delete_shift_pattern
from api.web.access import InputError, allowed, body, close, flag, optional_id, permission_denied, reject_input, required_text, whole_number
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_stamp, safe_text
from services.shift_management import (
    add_shift_pattern,
    bulk_set_day_availability,
    edit_shift_pattern,
    load_change_requests,
    load_faculty_availability,
    load_shift_dashboard,
    respond_change_request,
    set_day_availability,
)

_DAYS = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday', 7: 'Sunday'}
_SHIFT_CODE = re.compile(r'^[A-Z0-9][A-Z0-9_-]{0,19}$')
_CLOCK = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
_MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'shifts_unavailable': 'The page could not be loaded.',
    'shift_request_invalid': 'Choose approve or reject.',
    'shift_request_missing': 'That request was not found.',
    'availability_invalid': 'The availability could not be accepted.',
    'availability_selection_invalid': 'Select at least one faculty member and one day.',
    'availability_save_failed': 'The availability could not be saved.',
    'shift_name_invalid': 'Enter a shift name up to 80 characters.',
    'shift_code_invalid': 'Enter a shift code using letters, numbers, _ or -.',
    'shift_time_invalid': 'Enter a start and end time.',
    'shift_order_invalid': 'Shift order must be between 1 and 99.',
    'shift_in_use': 'This shift is assigned to faculty, so it cannot be deleted.',
    'shift_save_failed': 'The shift could not be saved.',
}


def register_shift_routes(blueprint):
    blueprint.add_url_rule('/shifts', 'shifts_list', patterns, methods=['GET'])
    blueprint.add_url_rule('/shifts', 'shifts_create', create_pattern, methods=['POST'])
    blueprint.add_url_rule('/shifts/<int:shift_id>', 'shifts_update', update_pattern, methods=['POST'])
    blueprint.add_url_rule('/shifts/<int:shift_id>/delete', 'shifts_delete', remove_pattern, methods=['POST'])
    blueprint.add_url_rule('/shift-requests', 'shift_requests', requests, methods=['GET'])
    blueprint.add_url_rule('/shift-requests/<int:request_id>', 'shift_request_respond', respond, methods=['POST'])
    blueprint.add_url_rule('/availability', 'shift_availability', availability, methods=['GET'])
    blueprint.add_url_rule('/availability/day', 'shift_availability_day', set_day, methods=['POST'])
    blueprint.add_url_rule('/availability/bulk', 'shift_availability_bulk', set_bulk, methods=['POST'])
    blueprint.add_url_rule('/portal/shifts', 'teacher_shifts', teacher, methods=['GET'])
    blueprint.add_url_rule('/portal/availability', 'teacher_availability', teacher, methods=['GET'])


def _day(value):
    if isinstance(value, bool):
        return ''
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        return _DAYS.get(int(value), safe_text(value, 12))
    return safe_text(value, 12)


def _submitted(value):
    if hasattr(value, 'strftime'):
        return value.strftime('%b %d, %Y')
    return safe_stamp(value)[:10]


def _reviewed(value):
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%b %d, %Y %H:%M')
    return safe_stamp(value)


def _note(value, limit):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise InputError('invalid_body')
    text = ''.join(ch for ch in value if ch in '\n\r\t' or ord(ch) >= 32)
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if len(text) > limit:
        raise InputError('invalid_body')
    return text


def request_view(page, can_respond):
    """Shape one change-request page the way the review screen reads it."""
    rows = []
    for row in page.get('requests') or []:
        rows.append({
            'id': safe_count(row.get('id')),
            'faculty': safe_text(row.get('faculty_name'), 100),
            'department': safe_text(row.get('department_name') or '', 100),
            'day': _day(row.get('day_of_week')),
            'current_shift': safe_text(row.get('current_shift_name') or '', 80),
            'requested_shift': safe_text(row.get('requested_shift_name') or '', 80),
            'reason': safe_text(row.get('reason') or '', 500),
            'status': safe_text(row.get('status') or '', 20).lower(),
            'response': safe_text(row.get('admin_response') or '', 1000),
            'submitted': _submitted(row.get('created_at')),
            'reviewer': safe_text(row.get('reviewed_by_name') or '', 80),
            'reviewed_at': _reviewed(row.get('reviewed_at')),
        })
    return {
        'requests': rows,
        'pending_count': safe_count(page.get('pending_count')),
        'can_respond': bool(can_respond),
    }


def _slot(slot):
    grouped = slot.get('all_slots') or []
    extra = max(0, len(grouped) - 1) if isinstance(grouped, list) else 0
    shift_id = safe_count(slot.get('shift_pattern_id'))
    return {
        'is_available': bool(slot.get('is_available')),
        'shift_pattern_id': shift_id or None,
        'shift_code': safe_text(slot.get('shift_code') or '', 20),
        'display_text': safe_text(slot.get('display_text') or '', 40),
        'time_range': safe_text(slot.get('time_range') or '', 40),
        'notes': safe_text(slot.get('notes') or '', 300),
        'extra': extra,
    }


def availability_view(page, can_change):
    """Shape the weekly faculty grid. Day keys are 1 (Monday) through 7 (Sunday)."""
    faculty = []
    for item in page.get('faculty_list') or []:
        person = item.get('faculty') or {}
        days = {}
        for day, slot in (item.get('availability') or {}).items():
            if isinstance(day, bool):
                continue
            if not (isinstance(day, int) or (isinstance(day, str) and str(day).isdigit())):
                continue
            number = int(day)
            if isinstance(slot, dict) and 1 <= number <= 7:
                days[str(number)] = _slot(slot)
        department_id = safe_count(person.get('department_id'))
        faculty.append({
            'user_id': safe_count(person.get('user_id')),
            'name': safe_text(person.get('name'), 100),
            'department_id': department_id or None,
            'department': safe_text(person.get('department_name') or '', 100),
            'days': days,
        })
    patterns = []
    for row in page.get('shift_patterns') or []:
        patterns.append({
            'id': safe_count(row.get('id')),
            'name': safe_text(row.get('shift_name'), 80),
            'code': safe_text(row.get('shift_code') or '', 20),
            'start_time': safe_clock(row.get('start_time')),
            'end_time': safe_clock(row.get('end_time')),
        })
    departments = []
    for row in page.get('departments') or []:
        departments.append({
            'id': safe_count(row.get('id')),
            'name': safe_text(row.get('name'), 100),
        })
    return {
        'faculty': faculty,
        'patterns': patterns,
        'departments': departments,
        'can_change': bool(can_change),
    }


def day_change(payload):
    """Build one day write. A missing shift keeps the saved shift; null clears it."""
    data = {
        'faculty_id': whole_number(payload.get('faculty_id'), 1000000, 'availability_invalid', lower=1),
        'day_of_week': whole_number(payload.get('day_of_week'), 7, 'availability_invalid', lower=1),
        'is_available': flag(payload.get('is_available')),
    }
    if 'shift_pattern_id' in payload:
        data['shift_pattern_id'] = optional_id(payload.get('shift_pattern_id'), 'availability_invalid')
    if 'notes' in payload:
        data['notes'] = _note(payload.get('notes'), 300)
    return data


def _id_list(value, code, upper):
    if not isinstance(value, list) or not value or len(value) > upper:
        raise InputError(code)
    numbers = []
    for item in value:
        number = whole_number(item, 1000000, code, lower=1)
        if number not in numbers:
            numbers.append(number)
    return numbers


def bulk_change(payload):
    """Build the bulk write. Days stay in the Monday-to-Sunday range."""
    faculty_ids = _id_list(payload.get('faculty_ids'), 'availability_selection_invalid', 2000)
    days = _id_list(payload.get('days'), 'availability_selection_invalid', 7)
    if any(day > 7 for day in days):
        raise InputError('availability_invalid')
    shift_pattern_id = None
    if 'shift_pattern_id' in payload:
        shift_pattern_id = optional_id(payload.get('shift_pattern_id'), 'availability_invalid')
    return (
        faculty_ids,
        shift_pattern_id,
        days,
        1 if flag(payload.get('is_available')) else 0,
        _note(payload.get('notes'), 300),
    )


def _view():
    return permission_denied('shifts_view', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])


def _total(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return safe_count(number)


def pattern_row(row):
    """Shape one shift pattern the way the manage screen reads it."""
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('shift_name'), 80),
        'code': safe_text(row.get('shift_code') or '', 20),
        'start_time': safe_clock(row.get('start_time')),
        'end_time': safe_clock(row.get('end_time')),
        'shift_order': safe_count(row.get('shift_order')) or 1,
        'description': safe_text(row.get('description') or '', 200),
        'is_active': bool(row.get('is_active')),
        'faculty_count': _total(row.get('faculty_count')),
    }


def shift_form(payload):
    """Validate a shift pattern form. Times stay as HH:MM."""
    name = required_text(payload.get('name'), 80, 'shift_name_invalid')
    code = required_text(payload.get('code'), 20, 'shift_code_invalid').upper()
    if not _SHIFT_CODE.match(code):
        raise InputError('shift_code_invalid')
    start = payload.get('start_time')
    end = payload.get('end_time')
    if not isinstance(start, str) or not isinstance(end, str) or not _CLOCK.match(start) or not _CLOCK.match(end):
        raise InputError('shift_time_invalid')
    order = whole_number(payload.get('shift_order') if payload.get('shift_order') not in (None, '') else 1, 99, 'shift_order_invalid', lower=1)
    description = _note(payload.get('description'), 200)
    active = 1 if flag(payload.get('is_active')) else 0
    return name, code, start, end, order, description, active


def _saved(outcome):
    get_flashed_messages()
    if outcome != 'ok':
        current_app.logger.error('Shift pattern save failed')
        return json_error(_MESSAGES['shift_save_failed'], 500, 'shift_save_failed')
    return json_ok({'saved': True})


def patterns():
    denied = _view()
    if denied:
        return denied
    try:
        page = load_shift_dashboard()
        return json_ok({
            'shifts': [pattern_row(row) for row in page.get('shift_patterns') or []],
            'active_count': _total(page.get('active_shifts_count')),
            'faculty_count': _total(page.get('faculty_with_shifts_count')),
            'can_add': allowed('shifts_add'),
            'can_change': allowed('shifts_change'),
            'can_delete': allowed('shifts_delete'),
        })
    except Exception:
        current_app.logger.exception('Shift list failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')


def create_pattern():
    denied = permission_denied('shifts_add', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset(('name', 'code', 'start_time', 'end_time', 'shift_order', 'description', 'is_active')))
        return _saved(add_shift_pattern(*shift_form(payload)))
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Shift pattern create failed')
        return json_error(_MESSAGES['shift_save_failed'], 500, 'shift_save_failed')


def update_pattern(shift_id):
    denied = permission_denied('shifts_change', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset(('name', 'code', 'start_time', 'end_time', 'shift_order', 'description', 'is_active')))
        values = shift_form(payload)
        return _saved(edit_shift_pattern(shift_id, *values))
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Shift pattern update failed')
        return json_error(_MESSAGES['shift_save_failed'], 500, 'shift_save_failed')


def remove_pattern(shift_id):
    """Delete an unused pattern. The usage count uses a dictionary cursor."""
    denied = permission_denied('shifts_delete', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        body(frozenset())
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        usage = count_shift_usage(cursor, shift_id)
        if _total((usage or {}).get('count')):
            return json_error(_MESSAGES['shift_in_use'], 409, 'shift_in_use')
        delete_shift_pattern(cursor, shift_id)
        connection.commit()
        return json_ok({'deleted': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Shift pattern delete failed')
        return json_error(_MESSAGES['shift_save_failed'], 500, 'shift_save_failed')
    finally:
        close(cursor, connection)


def requests():
    denied = _view()
    if denied:
        return denied
    try:
        page = load_change_requests()
        return json_ok(request_view(page, allowed('shifts_change')))
    except Exception:
        current_app.logger.exception('Shift requests failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')


def respond(request_id):
    denied = permission_denied('shifts_change', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset(('action', 'note')))
        action = payload.get('action')
        if action not in ('approve', 'reject'):
            raise InputError('shift_request_invalid')
        note = _note(payload.get('note'), 300)
        outcome = respond_change_request(request_id, action, note, session.get('user_id'))
        get_flashed_messages()
        if outcome == 'missing':
            return json_error(_MESSAGES['shift_request_missing'], 404, 'shift_request_missing')
        if outcome != 'ok':
            current_app.logger.error('Shift request response failed')
            return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')
        status = 'approved' if action == 'approve' else 'rejected'
        return json_ok({'id': safe_count(request_id), 'status': status})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Shift request response failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')


def availability():
    denied = _view()
    if denied:
        return denied
    try:
        page = load_faculty_availability()
        return json_ok(availability_view(page, allowed('shifts_change')))
    except Exception:
        current_app.logger.exception('Availability list failed')
        return json_error(_MESSAGES['shifts_unavailable'], 500, 'shifts_unavailable')


def set_day():
    denied = permission_denied('shifts_change', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset(('faculty_id', 'day_of_week', 'is_available', 'shift_pattern_id', 'notes')))
        result = set_day_availability(day_change(payload))
        if not result.get('success'):
            current_app.logger.error('Availability save failed')
            return json_error(_MESSAGES['availability_save_failed'], 500, 'availability_save_failed')
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Availability save failed')
        return json_error(_MESSAGES['availability_save_failed'], 500, 'availability_save_failed')


def set_bulk():
    denied = permission_denied('shifts_change', 'shifts_unavailable', _MESSAGES['shifts_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset(('faculty_ids', 'days', 'shift_pattern_id', 'is_available', 'notes')))
        outcome = bulk_set_day_availability(*bulk_change(payload))
        get_flashed_messages()
        if outcome != 'ok':
            current_app.logger.error('Bulk availability save failed')
            return json_error(_MESSAGES['availability_save_failed'], 500, 'availability_save_failed')
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Bulk availability save failed')
        return json_error(_MESSAGES['availability_save_failed'], 500, 'availability_save_failed')


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
