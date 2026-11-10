"""Room bookings: request, approve, reject, cancel (docs/TIMETABLE.md, "Room bookings").

All routes sit behind capability `bookings`. `bookings_view` or `rooms_view_room` may
request one of the rooms their institution owns or is given; `bookings_change` or
`rooms_change_room` holders of the room's owning institution approve or reject. A booking that meets a live timetable slot or an
approved booking is refused with the free rooms of the same type at that time.
"""

from datetime import date

from flask import current_app, jsonify, request, session

from api.web.access import (
    InputError, allowed, body, close, institution_input, iso_date, optional_id, optional_text, permission_denied,
    reject_input, required_text, whole_number,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core import capabilities
from core.db import transaction
from core.scope import current_scope
from extensions import get_db_connection
from security import log_activity
from services import bookings

CAPABILITY = 'bookings'
_FIELDS = frozenset((
    'room_id', 'title', 'kind', 'booking_date', 'day_of_week', 'repeat_until', 'start_time', 'end_time', 'notes', 'institution_id',
))
_DECISION_FIELDS = frozenset(('note',))

_MESSAGES = {
    'bookings_unavailable': 'Room bookings could not be loaded.',
    'bookings_table_missing': 'The bookings table is missing; apply the database migrations first.',
    'invalid_body': 'The request could not be accepted.',
    'booking_title_invalid': 'Give the booking a title of up to 120 characters.',
    'booking_notes_invalid': 'Notes may be up to 500 characters.',
    'booking_kind_invalid': 'Choose event, exam, maintenance or external.',
    'booking_when_invalid': 'Give either a date or a weekday for the booking.',
    'booking_time_invalid': 'Enter start and end times as HH:MM with the end after the start.',
    'booking_room_invalid': 'That room is not available to this institution.',
    'booking_room_busy': 'That room is timetabled at that time.',
    'booking_room_booked': 'That room is already booked at that time.',
    'booking_not_found': 'That booking was not found.',
    'booking_not_owned': 'Only the institution that owns the room can decide this booking.',
    'booking_decided': 'That booking has already been decided.',
    'booking_filter_invalid': 'The filter is not valid.',
    'institution_invalid': 'Choose an institution you manage.',
}


def register_booking_routes(blueprint):
    blueprint.add_url_rule('/bookings', 'bookings_list', _list, methods=['GET'])
    blueprint.add_url_rule('/bookings', 'bookings_create', _create, methods=['POST'])
    blueprint.add_url_rule('/bookings/free-rooms', 'bookings_free_rooms', _free_rooms, methods=['GET'])
    blueprint.add_url_rule('/bookings/<int:booking_id>/approve', 'bookings_approve', lambda booking_id: _decide(booking_id, True), methods=['POST'])
    blueprint.add_url_rule('/bookings/<int:booking_id>/reject', 'bookings_reject', lambda booking_id: _decide(booking_id, False), methods=['POST'])
    blueprint.add_url_rule('/bookings/<int:booking_id>/cancel', 'bookings_cancel', _cancel, methods=['POST'])


def _may_view():
    return allowed('bookings_view') or allowed('rooms_view_room')


def _may_decide():
    return allowed('bookings_change') or allowed('rooms_change_room')


def _gate(permission='rooms_view_room'):
    """Permission then capability. Returns an error response or None."""
    if permission == 'rooms_change_room':
        if not _may_decide():
            return permission_denied('bookings_change', 'bookings_unavailable', _MESSAGES['bookings_unavailable'])
    elif not _may_view():
        return permission_denied('bookings_view', 'bookings_unavailable', _MESSAGES['bookings_unavailable'])
    return capabilities.require_capability(CAPABILITY)


def _hhmm(value):
    text = safe_text(value, 5)
    if len(text) != 5 or text[2] != ':' or not (text[:2] + text[3:]).isdigit():
        raise InputError('booking_time_invalid')
    if int(text[:2]) > 23 or int(text[3:]) > 59:
        raise InputError('booking_time_invalid')
    return f'{text}:00'


def _as_date(value):
    if value is None:
        return None
    return value.isoformat()[:10] if hasattr(value, 'isoformat') else safe_text(value, 10)


def _public(row, scope):
    room_institution = safe_count(row.get('room_institution_id')) or None
    return {
        'id': safe_count(row.get('id')),
        'room_id': safe_count(row.get('room_id')),
        'room_number': safe_text(row.get('room_number'), 20),
        'room_type': safe_text(row.get('room_type') or '', 30),
        'room_institution': safe_text(row.get('room_institution_short_name') or '', 40),
        'institution_id': safe_count(row.get('institution_id')),
        'institution': safe_text(row.get('institution_short_name') or '', 40),
        'title': safe_text(row.get('title'), 120),
        'kind': row.get('kind') if row.get('kind') in bookings.KINDS else 'event',
        'booking_date': _as_date(row.get('booking_date')),
        'day_of_week': safe_text(row.get('day_of_week') or '', 10) or None,
        'repeat_until': _as_date(row.get('repeat_until')),
        'start_time': bookings.hhmm(row.get('start_time')),
        'end_time': bookings.hhmm(row.get('end_time')),
        'notes': safe_text(row.get('notes') or '', 500),
        'status': row.get('status') if row.get('status') in bookings.STATUSES else 'requested',
        'booked_by': safe_text(row.get('booked_by_name') or '', 100),
        'booked_by_id': safe_count(row.get('booked_by')) or None,
        'decided_by': safe_text(row.get('decided_by_name') or '', 100),
        'decided_at': row['decided_at'].isoformat(sep=' ', timespec='minutes') if row.get('decided_at') else '',
        'decision_note': safe_text(row.get('decision_note') or '', 300),
        'created_at': row['created_at'].isoformat(sep=' ', timespec='minutes') if row.get('created_at') else '',
        'can_decide': row.get('status') == 'requested' and _may_decide() and scope.allows(room_institution),
        'can_cancel': row.get('status') in ('requested', 'approved') and (
            safe_count(row.get('booked_by')) == safe_count(session.get('user_id'))
            or (_may_decide() and scope.allows(room_institution))
        ),
    }


def _public_room(row):
    return {
        'id': safe_count(row.get('id')), 'room_number': safe_text(row.get('room_number'), 20),
        'room_type': safe_text(row.get('room_type') or '', 30), 'capacity': safe_count(row.get('capacity')) or None,
    }


def _refused(exc):
    """400 with the rule that failed and, for a clash, the free rooms of the same type at that time."""
    return jsonify({
        'success': False,
        'error': {
            'code': safe_text(exc.code, 40),
            'message': safe_text(str(exc), 300) or _MESSAGES.get(exc.code, _MESSAGES['invalid_body']),
            'alternatives': [_public_room(room) for room in exc.alternatives[:8]],
        },
    }), 400


def _rooms_for(cursor, scope):
    clause, params = scope.rooms_clause('r') if scope.institution_id is not None else scope.clause('r.institution_id')
    cursor.execute(
        f'SELECT r.id, r.room_number, r.room_type, r.capacity, r.institution_id FROM rooms r WHERE {clause} ORDER BY r.room_type, r.room_number',
        params,
    )
    return [{**_public_room(row), 'institution_id': safe_count(row.get('institution_id')) or None} for row in cursor.fetchall()]


def _list():
    denied = _gate()
    if denied:
        return denied
    connection = cursor = None
    try:
        status = request.args.get('status') or None
        if status is not None and status not in bookings.STATUSES:
            raise InputError('booking_filter_invalid')
        room_id = optional_id(request.args.get('room_id'), 'booking_filter_invalid')
        from_date = iso_date(request.args.get('from'), 'booking_filter_invalid', required=False)
        to_date = iso_date(request.args.get('to'), 'booking_filter_invalid', required=False)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not bookings.table_exists(cursor):
            return json_error(_MESSAGES['bookings_table_missing'], 409, 'bookings_table_missing')
        scope = current_scope(cursor)
        rooms_clause, rooms_params = scope.rooms_clause('r') if scope.institution_id is not None else scope.clause('r.institution_id')
        institution_clause, institution_params = scope.clause('b.institution_id')
        rows = bookings.list_bookings(
            cursor, rooms_clause=rooms_clause, rooms_params=rooms_params, institution_clause=institution_clause,
            institution_params=institution_params, status=status, room_id=room_id, from_date=from_date, to_date=to_date,
        )
        return json_ok({
            'bookings': [_public(row, scope) for row in rows],
            'rooms': _rooms_for(cursor, scope),
            'kinds': list(bookings.KINDS),
            'days': list(bookings.DAYS),
            'requires_approval': bookings.requires_approval(cursor),
            'institution_id': scope.institution_id,
            'permissions': {'request': True, 'approve': _may_decide()},
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Bookings list failed')
        return json_error(_MESSAGES['bookings_unavailable'], 500, 'bookings_unavailable')
    finally:
        close(cursor, connection)


def _free_rooms():
    denied = _gate()
    if denied:
        return denied
    connection = cursor = None
    try:
        day = request.args.get('day') or None
        booking_date = iso_date(request.args.get('date'), 'booking_when_invalid', required=False)
        if booking_date:
            day = date.fromisoformat(booking_date).strftime('%A')
        if day not in bookings.DAYS:
            raise InputError('booking_when_invalid')
        start_time = _hhmm(request.args.get('start_time'))
        end_time = _hhmm(request.args.get('end_time'))
        if start_time >= end_time:
            raise InputError('booking_time_invalid')
        room_type = safe_text(request.args.get('room_type') or '', 30) or None
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not bookings.table_exists(cursor):
            return json_error(_MESSAGES['bookings_table_missing'], 409, 'bookings_table_missing')
        scope = current_scope(cursor)
        institution_id = institution_input(cursor, scope, request.args.get('institution_id'))
        rooms = bookings.free_rooms(
            cursor, institution_id=institution_id if scope.multiple else None, room_type=room_type, day=day,
            start_time=start_time, end_time=end_time, booking_date=booking_date, limit=50,
        )
        return json_ok({'rooms': [_public_room(room) for room in rooms]})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Free rooms lookup failed')
        return json_error(_MESSAGES['bookings_unavailable'], 500, 'bookings_unavailable')
    finally:
        close(cursor, connection)


def _create():
    denied = _gate()
    if denied:
        return denied
    connection = cursor = None
    try:
        payload = body(_FIELDS)
        title = required_text(payload.get('title'), 120, 'booking_title_invalid')
        notes = optional_text(payload.get('notes'), 500, 'booking_notes_invalid')
        kind = payload.get('kind') or 'event'
        if kind not in bookings.KINDS:
            raise InputError('booking_kind_invalid')
        room_id = whole_number(payload.get('room_id'), 1000000, 'booking_room_invalid', lower=1)
        booking_date = iso_date(payload.get('booking_date'), 'booking_when_invalid', required=False)
        day_of_week = payload.get('day_of_week') or None
        if day_of_week is not None and day_of_week not in bookings.DAYS:
            raise InputError('booking_when_invalid')
        if bool(booking_date) == bool(day_of_week):
            raise InputError('booking_when_invalid')
        repeat_until = iso_date(payload.get('repeat_until'), 'booking_when_invalid', required=False) if day_of_week else None
        start_time = _hhmm(payload.get('start_time'))
        end_time = _hhmm(payload.get('end_time'))
        if start_time >= end_time:
            raise InputError('booking_time_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not bookings.table_exists(cursor):
            return json_error(_MESSAGES['bookings_table_missing'], 409, 'bookings_table_missing')
        scope = current_scope(cursor)
        institution_id = institution_input(cursor, scope, payload.get('institution_id'))
        # Approved at once when the tenant does not ask for approval, or an approver books a room their institution owns.
        cursor.execute('SELECT institution_id FROM rooms WHERE id = %s', (room_id,))
        room_row = cursor.fetchone()
        owner = safe_count((room_row or {}).get('institution_id')) or None
        approve = not bookings.requires_approval(cursor) or (_may_decide() and room_row is not None and scope.allows(owner))
        with transaction(connection):
            booking_id = bookings.create(
                cursor, institution_id=institution_id, room_id=room_id, title=title, kind=kind, start_time=start_time,
                end_time=end_time, booking_date=booking_date, day_of_week=day_of_week, repeat_until=repeat_until, notes=notes,
                booked_by=session.get('user_id'), approve=approve,
            )
            if not approve:
                from services import notifications

                notifications.on_booking_request(cursor, booking_id)
        try:
            log_activity(
                session.get('user_id'), 'booking_approved' if approve else 'booking_requested',
                f"{'Booked' if approve else 'Requested'} room #{room_id} for {title}", entity_type='booking', entity_id=booking_id,
                new_values={'room_id': room_id, 'kind': kind, 'booking_date': booking_date, 'day_of_week': day_of_week,
                            'start_time': start_time, 'end_time': end_time},
            )
        except Exception:
            current_app.logger.exception('Booking audit failed')
        return json_ok({'booking': _public(bookings.load(cursor, booking_id), scope)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except bookings.BookingError as exc:
        return _refused(exc)
    except Exception:
        current_app.logger.exception('Booking could not be created')
        return json_error(_MESSAGES['bookings_unavailable'], 500, 'bookings_unavailable')
    finally:
        close(cursor, connection)


def _owned_booking(cursor, booking_id, scope):
    """The booking row when the scope may decide it (owns the room); a JSON error otherwise."""
    row = bookings.load(cursor, booking_id)
    if row is None:
        return json_error(_MESSAGES['booking_not_found'], 404, 'booking_not_found')
    if not scope.allows(safe_count(row.get('room_institution_id')) or None):
        return json_error(_MESSAGES['booking_not_owned'], 403, 'booking_not_owned')
    return row


def _decide(booking_id, approve):
    denied = _gate('rooms_change_room')
    if denied:
        return denied
    connection = cursor = None
    try:
        payload = body(_DECISION_FIELDS) if request.get_json(silent=True) else {}
        note = optional_text(payload.get('note'), 300, 'booking_notes_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not bookings.table_exists(cursor):
            return json_error(_MESSAGES['bookings_table_missing'], 409, 'bookings_table_missing')
        scope = current_scope(cursor)
        row = _owned_booking(cursor, booking_id, scope)
        if isinstance(row, tuple):
            return row
        with transaction(connection):
            outcome = bookings.decide(cursor, booking_id, approve=approve, decided_by=session.get('user_id'), note=note)
            from services import notifications

            notifications.on_booking_decision(cursor, booking_id)
        try:
            log_activity(
                session.get('user_id'), f'booking_{outcome}', f'{outcome.capitalize()} booking #{booking_id}',
                entity_type='booking', entity_id=booking_id, new_values={'status': outcome, 'note': note},
            )
        except Exception:
            current_app.logger.exception('Booking audit failed')
        return json_ok({'booking': _public(bookings.load(cursor, booking_id), scope)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except bookings.BookingError as exc:
        if exc.code == 'booking_not_found':
            return json_error(_MESSAGES['booking_not_found'], 404, exc.code)
        return _refused(exc)
    except Exception:
        current_app.logger.exception('Booking decision failed')
        return json_error(_MESSAGES['bookings_unavailable'], 500, 'bookings_unavailable')
    finally:
        close(cursor, connection)


def _cancel(booking_id):
    denied = _gate()
    if denied:
        return denied
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not bookings.table_exists(cursor):
            return json_error(_MESSAGES['bookings_table_missing'], 409, 'bookings_table_missing')
        scope = current_scope(cursor)
        row = bookings.load(cursor, booking_id)
        if row is None:
            return json_error(_MESSAGES['booking_not_found'], 404, 'booking_not_found')
        mine = safe_count(row.get('booked_by')) == safe_count(session.get('user_id'))
        approver = _may_decide() and scope.allows(safe_count(row.get('room_institution_id')) or None)
        if not (mine or approver):
            return json_error(_MESSAGES['booking_not_owned'], 403, 'booking_not_owned')
        with transaction(connection):
            previous = bookings.cancel(cursor, booking_id, cancelled_by=session.get('user_id'))
        try:
            log_activity(
                session.get('user_id'), 'booking_cancelled', f'Cancelled booking #{booking_id}',
                entity_type='booking', entity_id=booking_id, new_values={'previous_status': previous},
            )
        except Exception:
            current_app.logger.exception('Booking audit failed')
        return json_ok({'booking': _public(bookings.load(cursor, booking_id), scope)})
    except bookings.BookingError as exc:
        return json_error(safe_text(str(exc), 300), 400, exc.code)
    except Exception:
        current_app.logger.exception('Booking cancel failed')
        return json_error(_MESSAGES['bookings_unavailable'], 500, 'bookings_unavailable')
    finally:
        close(cursor, connection)
