"""Proxy log for administrators and the signed-in teacher."""

from datetime import date, timedelta

from flask import current_app, request, session

from extensions import get_db_connection
from api.web.access import InputError, allowed, body, close, iso_date, optional_id, optional_text, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from services.proxy_log import decide_proxy_request, load_proxy_choices, load_proxy_log

_MESSAGES = {
    'proxy_unavailable': 'The page could not be loaded.',
    'proxy_filters_invalid': 'Enter a valid date range.',
    'proxy_missing': 'That proxy request was not found.',
    'proxy_closed': 'This request has already been decided.',
    'proxy_choice_required': 'Choose the faculty who will take this class.',
    'proxy_choice_invalid': 'Choose a faculty member who can take this subject.',
    'proxy_busy': 'That faculty already has a class at this time.',
    'proxy_note_invalid': 'The note must be 200 characters or less.',
    'invalid_body': 'The request could not be accepted.',
}
_PROXY_STATUS = frozenset(('ASSIGNED', 'UNASSIGNED', 'PENDING', 'REJECTED'))
_APPROVAL_STATUS = frozenset(('PENDING', 'APPROVED', 'REJECTED'))


def register_proxy_routes(blueprint):
    blueprint.add_url_rule('/proxy', 'proxy_list', _list, methods=['GET'])
    blueprint.add_url_rule('/proxy/<int:proxy_id>/choices', 'proxy_choices', _choices, methods=['GET'])
    blueprint.add_url_rule('/proxy/<int:proxy_id>/approve', 'proxy_approve', _approve, methods=['POST'])
    blueprint.add_url_rule('/proxy/<int:proxy_id>/reject', 'proxy_reject', _reject, methods=['POST'])
    blueprint.add_url_rule('/portal/proxy', 'teacher_proxy', _teacher, methods=['GET'])


def _page_number(raw):
    text = '' if raw is None else str(raw).strip()
    if text.isdigit():
        number = int(text)
        if 1 <= number <= 10000:
            return number
    return 1


def proxy_filters(source):
    """Keep the substitution-log filters on the old allow-list."""
    status = source.get('status') or ''
    approval = source.get('approval_status') or ''
    if status not in _PROXY_STATUS:
        status = ''
    if approval not in _APPROVAL_STATUS:
        approval = ''
    date_from = iso_date(source.get('date_from') or '', 'proxy_filters_invalid', required=False) or ''
    date_to = iso_date(source.get('date_to') or '', 'proxy_filters_invalid', required=False) or ''
    return status, approval, date_from, date_to, _page_number(source.get('page'))


def _short_date(value):
    if hasattr(value, 'strftime'):
        return value.strftime('%d %b')
    text = safe_stamp(value)
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10]).strftime('%d %b')
        except ValueError:
            return safe_text(text, 12)
    return safe_text(text, 12)


def _clock12(value):
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, str):
        return safe_text(value, 16)
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) % 86400
        hours, remainder = divmod(total, 3600)
        minutes, _seconds = divmod(remainder, 60)
        period = 'AM' if hours < 12 else 'PM'
        display = hours % 12 or 12
        return f'{display:02d}:{minutes:02d} {period}'
    if hasattr(value, 'strftime'):
        return value.strftime('%I:%M %p')
    return safe_text(value, 16)


def _count(value):
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    if number < 0:
        return 0
    return min(number, 1000000)


def proxy_entry(row):
    """Shape one substitution row for the log table."""
    return {
        'id': safe_count(row.get('id')),
        'date': _short_date(row.get('absence_date')),
        'start_time': _clock12(row.get('start_time')),
        'end_time': _clock12(row.get('end_time')),
        'status': safe_text(row.get('status') or '', 20),
        'approval': safe_text(row.get('approval_status') or '', 20),
        'approval_notes': safe_text(row.get('approval_notes') or '', 200),
        'original_faculty': safe_text(row.get('original_faculty_name') or '', 100),
        'original_employee_id': safe_text(row.get('original_employee_id') or '', 40),
        'proxy_faculty': safe_text(row.get('proxy_faculty_name') or '', 100),
        'proxy_employee_id': safe_text(row.get('proxy_employee_id') or '', 40),
        'subject': safe_text(row.get('subject_name') or '', 100),
        'class_name': safe_text(row.get('class_name') or '', 100),
        'division_name': safe_text(row.get('division_name') or '', 50),
        'approved_by': safe_text(row.get('approved_by_username') or '', 80),
    }


def proxy_summary(stats):
    stats = stats or {}
    return {
        'total': _count(stats.get('total_records')),
        'assigned': _count(stats.get('assigned_count')),
        'unassigned': _count(stats.get('unassigned_count')),
        'pending': _count(stats.get('pending_approval')),
        'approved': _count(stats.get('approved_count')),
        'rejected': _count(stats.get('rejected_count')),
    }


def _list():
    denied = permission_denied('faculty_view_proxy', 'proxy_unavailable', _MESSAGES['proxy_unavailable'])
    if denied:
        return denied
    try:
        status, approval, date_from, date_to, page = proxy_filters(request.args)
        logs, stats, pagination = load_proxy_log(page, status, approval, date_from, date_to, close_connection=True)
        return json_ok({
            'entries': [proxy_entry(row) for row in logs],
            'summary': proxy_summary(stats),
            'page': safe_count(pagination.get('page')) or 1,
            'total_pages': safe_count(pagination.get('total_pages')),
            'total': safe_count(pagination.get('total')),
            'has_prev': bool(pagination.get('has_prev')),
            'has_next': bool(pagination.get('has_next')),
            'date_to': date_to,
            'can_change': allowed('faculty_approve_proxy'),
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Proxy list failed')
        return json_error(_MESSAGES['proxy_unavailable'], 500, 'proxy_unavailable')


def _choice_row(row):
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name') or '', 100),
        'employee_id': safe_text(row.get('employee_id') or '', 40),
        'free': row.get('free') is True,
    }


def _decision_error(result, sent_proxy):
    if result == 'missing':
        return json_error(_MESSAGES['proxy_missing'], 404, 'proxy_missing')
    if result == 'closed':
        return json_error(_MESSAGES['proxy_closed'], 409, 'proxy_closed')
    if result == 'busy':
        return json_error(_MESSAGES['proxy_busy'], 409, 'proxy_busy')
    if result == 'choice':
        code = 'proxy_choice_required' if not sent_proxy else 'proxy_choice_invalid'
        return json_error(_MESSAGES[code], 400, code)
    return json_error(_MESSAGES['proxy_unavailable'], 500, 'proxy_unavailable')


def _note(payload):
    text = optional_text(payload.get('note'), 200, 'proxy_note_invalid')
    return text or None


def _choices(proxy_id):
    denied = permission_denied('faculty_approve_proxy', 'proxy_unavailable', _MESSAGES['proxy_unavailable'])
    if denied:
        return denied
    try:
        page = load_proxy_choices(proxy_id)
    except Exception:
        current_app.logger.exception('Proxy choices failed')
        return json_error(_MESSAGES['proxy_unavailable'], 500, 'proxy_unavailable')
    if page == 'missing':
        return json_error(_MESSAGES['proxy_missing'], 404, 'proxy_missing')
    suggested = page.get('suggested_id')
    return json_ok({
        'pending': page.get('pending') is True,
        'suggested_id': safe_count(suggested) if suggested else None,
        'choices': [_choice_row(row) for row in page.get('choices') or []],
    })


def _approve(proxy_id):
    denied = permission_denied('faculty_approve_proxy', 'proxy_unavailable', _MESSAGES['proxy_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset(('proxy_faculty_id', 'note')))
        chosen = optional_id(payload.get('proxy_faculty_id'), 'proxy_choice_invalid')
        note = _note(payload)
        result = decide_proxy_request(proxy_id, 'approve', chosen, note, session.get('user_id'))
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Proxy approval failed')
        return json_error(_MESSAGES['proxy_unavailable'], 500, 'proxy_unavailable')
    if result != 'ok':
        return _decision_error(result, chosen)
    return json_ok({'saved': True})


def _reject(proxy_id):
    denied = permission_denied('faculty_approve_proxy', 'proxy_unavailable', _MESSAGES['proxy_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset(('note',)))
        note = _note(payload)
        result = decide_proxy_request(proxy_id, 'reject', None, note, session.get('user_id'))
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Proxy rejection failed')
        return json_error(_MESSAGES['proxy_unavailable'], 500, 'proxy_unavailable')
    if result != 'ok':
        return _decision_error(result, None)
    return json_ok({'saved': True})


def _teacher():
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
            return json_error(_MESSAGES['proxy_unavailable'], 404, 'proxy_unavailable')
        cursor.execute(
            """
            SELECT p.absence_date, p.status, p.approval_status, s.name AS subject_name,
                   ofc.name AS original_name, pfc.name AS proxy_name
            FROM proxy_log p
            JOIN timetable t ON t.id = p.timetable_id
            JOIN subjects s ON s.id = t.subject_id
            LEFT JOIN faculty ofc ON ofc.user_id = p.original_faculty_id
            LEFT JOIN faculty pfc ON pfc.user_id = p.proxy_faculty_id
            WHERE p.original_faculty_id = %s OR p.proxy_faculty_id = %s
            ORDER BY p.absence_date DESC
            LIMIT 40
            """,
            (faculty['user_id'], faculty['user_id']),
        )
        rows = [
            {
                'date': safe_stamp(row.get('absence_date'))[:10],
                'subject': safe_text(row.get('subject_name'), 100),
                'original': safe_text(row.get('original_name') or '', 100),
                'proxy': safe_text(row.get('proxy_name') or '', 100),
                'status': safe_text(row.get('status') or '', 20),
                'approval': safe_text(row.get('approval_status') or '', 20),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'entries': rows})
    except Exception:
        current_app.logger.exception('Teacher proxy failed')
        return json_error(_MESSAGES['proxy_unavailable'], 500, 'proxy_unavailable')
    finally:
        close(cursor, connection)
