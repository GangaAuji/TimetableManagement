"""Faculty and student portal actions. Writes go through the existing portal services."""

import re

from flask import current_app, session

from extensions import get_db_connection
from api.web.access import InputError, body, close, iso_date, optional_id, optional_text, reject_input, whole_number
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_stamp, safe_text
from services.student_portal import load_student_attendance, load_subject_attendance
from services.teacher_attendance import load_attendance_history, load_attendance_index, load_mark_page, save_teacher_attendance
from services.teacher_portal import (
    load_availability,
    load_my_classes,
    load_my_shifts,
    load_proxy_page,
    save_availability,
    submit_proxy_request,
    submit_shift_change,
)

_CLOCK = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
_DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
_STATUSES = frozenset(('Present', 'Late', 'Absent'))
_STUDENT_ERRORS = frozenset((
    'Your profile is not fully set up. Please contact an administrator.',
    'Student profile not found.',
    'No attendance records found for this subject.',
    'An error occurred while fetching attendance data.',
))
_MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'portal_unavailable': 'The page could not be loaded.',
    'portal_missing': 'Faculty profile not found.',
    'portal_invalid': 'Check the form and try again.',
    'portal_denied': 'You do not have permission to do that.',
    'portal_date': 'Enter a valid date.',
}


def register_portal_action_routes(blueprint):
    blueprint.add_url_rule('/portal/availability/slots', 'portal_availability', _availability, methods=['GET', 'POST'])
    blueprint.add_url_rule('/portal/shifts/mine', 'portal_shifts', _shifts, methods=['GET', 'POST'])
    blueprint.add_url_rule('/portal/proxy/mine', 'portal_proxy', _proxy, methods=['GET', 'POST'])
    blueprint.add_url_rule('/portal/classes/roster', 'portal_classes', _classes, methods=['GET'])
    blueprint.add_url_rule('/portal/attendance/lectures', 'portal_lectures', _lectures, methods=['GET'])
    blueprint.add_url_rule('/portal/attendance/mark/<int:timetable_id>', 'portal_mark', _mark, methods=['GET', 'POST'])
    blueprint.add_url_rule('/portal/attendance/history/<int:timetable_id>', 'portal_history', _history, methods=['GET'])
    blueprint.add_url_rule('/portal/student/attendance', 'portal_student_attendance', _student_attendance, methods=['GET'])
    blueprint.add_url_rule('/portal/student/attendance/<int:subject_id>', 'portal_subject_attendance', _subject_attendance, methods=['GET'])


def _teacher():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Teacher':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    return None


def _student():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Student':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    return None


def _percent(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number < 0:
        return 0
    return round(min(number, 100), 1)


def _service_error(result):
    if result == 'missing':
        return json_error(_MESSAGES['portal_missing'], 404, 'portal_missing')
    if result in ('fields', 'invalid'):
        return json_error(_MESSAGES['portal_invalid'], 400, 'portal_invalid')
    if result == 'denied':
        return json_error(_MESSAGES['portal_denied'], 403, 'portal_denied')
    if result == 'date':
        return json_error(_MESSAGES['portal_date'], 400, 'portal_date')
    if result == 'student':
        return json_error('That student is not in this class.', 400, 'portal_invalid')
    return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')


def _patterns():
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT shift_name, shift_code, start_time, end_time
            FROM shift_patterns
            WHERE is_active = 1
            ORDER BY shift_order, shift_name
            """
        )
        return [
            {
                'name': safe_text(row.get('shift_name'), 80),
                'code': safe_text(row.get('shift_code') or '', 20),
                'start_time': safe_clock(row.get('start_time')),
                'end_time': safe_clock(row.get('end_time')),
            }
            for row in cursor.fetchall()
        ]
    finally:
        close(cursor, connection)


def _availability():
    denied = _teacher()
    if denied:
        return denied
    faculty_id = session.get('faculty_id')
    if request_method_post():
        return _save_slots(faculty_id)
    try:
        slots = load_availability(faculty_id)
    except Exception:
        current_app.logger.exception('Availability load failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(slots, dict):
        return _service_error(slots)
    days = []
    for day in _DAYS:
        rows = []
        for slot in slots.get(day) or []:
            rows.append({
                'available': bool(slot.get('is_available')),
                'start_time': safe_clock(slot.get('start_time')),
                'end_time': safe_clock(slot.get('end_time')),
                'notes': safe_text(slot.get('notes') or '', 200),
                'shift': safe_text(slot.get('shift_name') or '', 80),
            })
        days.append({'day': day, 'slots': rows})
    return json_ok({'days': days})


def request_method_post():
    from flask import request
    return request.method == 'POST'


def _save_slots(faculty_id):
    try:
        payload = body(frozenset(('days',)))
        days = payload.get('days')
        if not isinstance(days, list) or len(days) > 7:
            raise InputError('portal_invalid')
        form = {}
        seen = set()
        for item in days:
            if not isinstance(item, dict):
                raise InputError('portal_invalid')
            day = item.get('day')
            if day not in _DAYS or day in seen:
                raise InputError('portal_invalid')
            seen.add(day)
            available = item.get('available') is True
            if available:
                form[f'{day}-available'] = 'on'
            slots = item.get('slots') if isinstance(item.get('slots'), list) else []
            if len(slots) > 8:
                raise InputError('portal_invalid')
            for index, slot in enumerate(slots):
                if not isinstance(slot, dict):
                    raise InputError('portal_invalid')
                start = optional_text(slot.get('start'), 5, 'portal_invalid')
                end = optional_text(slot.get('end'), 5, 'portal_invalid')
                notes = optional_text(slot.get('notes'), 200, 'portal_invalid')
                if bool(start) != bool(end) or (start and not _CLOCK.match(start)) or (end and not _CLOCK.match(end)):
                    raise InputError('portal_invalid')
                if start and end:
                    form[f'{day}-start-{index}'] = start
                    form[f'{day}-end-{index}'] = end
                    form[f'{day}-notes-{index}'] = notes
        result = save_availability(faculty_id, form)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Availability save failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if result != 'ok':
        return _service_error(result)
    return json_ok({'saved': True})


def _shifts():
    denied = _teacher()
    if denied:
        return denied
    faculty_id = session.get('faculty_id')
    if request_method_post():
        return _request_shift(faculty_id)
    try:
        page = load_my_shifts(faculty_id)
        patterns = _patterns()
    except Exception:
        current_app.logger.exception('Shift page failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(page, dict):
        return _service_error(page)
    info = page.get('faculty_info') or {}
    schedule = []
    for day_num, day_name in (page.get('day_names') or {}).items():
        row = (page.get('schedule') or {}).get(day_name) or {}
        schedule.append({
            'day': safe_text(day_name, 12),
            'day_num': safe_count(row.get('day_num') or day_num),
            'available': bool(row.get('is_available')),
            'shift': safe_text(row.get('shift_name') or '', 80),
            'code': safe_text(row.get('shift_code') or '', 20),
            'start_time': safe_clock(row.get('start_time')),
            'end_time': safe_clock(row.get('end_time')),
            'notes': safe_text(row.get('notes') or '', 200),
        })
    requests = []
    for row in page.get('change_requests') or []:
        requests.append({
            'day': safe_text(row.get('day_of_week'), 12),
            'current_shift': safe_text(row.get('current_shift_name') or '', 80),
            'requested_shift': safe_text(row.get('requested_shift_name') or '', 80),
            'reason': safe_text(row.get('reason') or '', 300),
            'status': safe_text(row.get('status') or '', 20),
            'response': safe_text(row.get('admin_response') or '', 300),
            'created_at': safe_stamp(row.get('created_at')),
        })
    return json_ok({
        'name': safe_text(info.get('name') or '', 100),
        'department': safe_text(info.get('department_name') or '', 100),
        'schedule': schedule,
        'patterns': patterns,
        'requests': requests,
    })


def _request_shift(faculty_id):
    try:
        payload = body(frozenset(('day_of_week', 'current_shift_name', 'requested_shift_name', 'reason')))
        day = optional_text(payload.get('day_of_week'), 12, 'portal_invalid')
        if day not in _DAYS and day not in {str(number) for number in range(1, 8)}:
            raise InputError('portal_invalid')
        current_name = optional_text(payload.get('current_shift_name'), 80, 'portal_invalid') or 'Not Assigned'
        requested = optional_text(payload.get('requested_shift_name'), 80, 'portal_invalid')
        if not requested:
            raise InputError('portal_invalid')
        reason = optional_text(payload.get('reason'), 300, 'portal_invalid')
        result = submit_shift_change(faculty_id, day, current_name, requested, reason)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Shift request failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if result != 'ok':
        return _service_error(result)
    return json_ok({'saved': True})


def _proxy():
    denied = _teacher()
    if denied:
        return denied
    faculty_id = session.get('faculty_id')
    if request_method_post():
        return _request_proxy(faculty_id)
    try:
        page = load_proxy_page(faculty_id)
    except Exception:
        current_app.logger.exception('Proxy page failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(page, dict):
        return _service_error(page)
    lectures = []
    for row in page.get('lectures') or []:
        lectures.append({
            'id': safe_count(row.get('id')),
            'day': safe_text(row.get('day_of_week'), 12),
            'start_time': safe_clock(row.get('start_time')),
            'end_time': safe_clock(row.get('end_time')),
            'subject': safe_text(row.get('name'), 100),
        })
    people = []
    seen = set()
    for choices in (page.get('proxy_map') or {}).values():
        for person in choices or []:
            faculty = safe_count(person.get('faculty_id'))
            if not faculty or faculty in seen:
                continue
            seen.add(faculty)
            people.append({'id': faculty, 'name': safe_text(person.get('name'), 100)})
    logs = []
    for row in page.get('logs') or []:
        logs.append({
            'date': safe_stamp(row.get('absence_date'))[:10],
            'day': safe_text(row.get('day_of_week'), 12),
            'start_time': safe_clock(row.get('start_time')),
            'end_time': safe_clock(row.get('end_time')),
            'subject': safe_text(row.get('subject_name'), 100),
            'original': safe_text(row.get('original_name') or '', 100),
            'proxy': safe_text(row.get('proxy_name') or '', 100),
            'status': safe_text(row.get('status') or '', 20),
            'approval': safe_text(row.get('approval_status') or '', 20),
        })
    return json_ok({'lectures': lectures, 'proxies': people, 'logs': logs})


def _request_proxy(faculty_id):
    try:
        payload = body(frozenset(('timetable_id', 'proxy_faculty_id', 'absence_date')))
        timetable_id = whole_number(payload.get('timetable_id'), 1000000, 'portal_invalid', lower=1)
        proxy_faculty_id = optional_id(payload.get('proxy_faculty_id'), 'portal_invalid')
        absence_date = iso_date(payload.get('absence_date'), 'portal_date')
        result = submit_proxy_request(faculty_id, timetable_id, proxy_faculty_id, absence_date)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Proxy request failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if result != 'ok':
        return _service_error(result)
    return json_ok({'saved': True})


def _classes():
    denied = _teacher()
    if denied:
        return denied
    try:
        classes = load_my_classes(session.get('faculty_id'))
    except Exception:
        current_app.logger.exception('Class roster failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(classes, list):
        return _service_error(classes)
    rows = []
    for item in classes:
        students = []
        for student in item.get('students') or []:
            students.append({
                'name': safe_text(student.get('name'), 100),
                'username': safe_text(student.get('username') or '', 50),
            })
        rows.append({
            'class_name': safe_text(item.get('class_name'), 100),
            'division_name': safe_text(item.get('division_name'), 50),
            'course_name': safe_text(item.get('course_name'), 100),
            'subject': safe_text(item.get('subject_name'), 100),
            'student_count': safe_count(item.get('student_count')),
            'students': students[:300],
        })
    return json_ok({'classes': rows})


def _lectures():
    denied = _teacher()
    if denied:
        return denied
    try:
        page = load_attendance_index(session.get('user_id'))
    except Exception:
        current_app.logger.exception('Attendance lectures failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    lectures = []
    for row in page.get('lectures') or []:
        lectures.append({
            'id': safe_count(row.get('timetable_id')),
            'day': safe_text(row.get('day_of_week'), 12),
            'start_time': safe_clock(row.get('start_time')),
            'end_time': safe_clock(row.get('end_time')),
            'subject': safe_text(row.get('subject_name'), 100),
            'class_name': safe_text(row.get('class_name'), 100),
            'division_name': safe_text(row.get('division_name'), 50),
            'course_name': safe_text(row.get('course_name'), 100),
            'marked_today': bool(row.get('attendance_marked_today')),
        })
    return json_ok({
        'today': safe_text(page.get('today'), 20),
        'marked_today_count': safe_count(page.get('marked_today_count')),
        'lectures': lectures,
    })


def _mark(timetable_id):
    denied = _teacher()
    if denied:
        return denied
    if request_method_post():
        return _save_marks(timetable_id)
    try:
        page = load_mark_page(session.get('user_id'), timetable_id)
    except Exception:
        current_app.logger.exception('Attendance mark page failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(page, dict):
        return _service_error(page)
    lecture = page.get('lecture') or {}
    students = []
    for row in page.get('students') or []:
        students.append({
            'id': safe_count(row.get('id')),
            'name': safe_text(row.get('name'), 100),
            'roll_number': safe_text(row.get('roll_number') or '', 30),
            'status': safe_text(row.get('attendance_status') or '', 20),
            'remarks': safe_text(row.get('remarks') or '', 200),
        })
    return json_ok({
        'date': safe_text(page.get('attendance_date'), 10),
        'already_marked': bool(page.get('attendance_already_marked')),
        'lecture': {
            'subject': safe_text(lecture.get('subject_name'), 100),
            'class_name': safe_text(lecture.get('class_name'), 100),
            'division_name': safe_text(lecture.get('division_name'), 50),
            'day': safe_text(lecture.get('day_of_week'), 12),
            'start_time': safe_clock(lecture.get('start_time')),
            'end_time': safe_clock(lecture.get('end_time')),
        },
        'students': students[:300],
    })


def _save_marks(timetable_id):
    try:
        payload = body(frozenset(('attendance_date', 'marks')))
        attendance_date = iso_date(payload.get('attendance_date'), 'portal_date')
        marks = payload.get('marks')
        if not isinstance(marks, list) or len(marks) > 300:
            raise InputError('portal_invalid')
        form = {'attendance_date': attendance_date}
        for item in marks:
            if not isinstance(item, dict):
                raise InputError('portal_invalid')
            student_id = whole_number(item.get('student_id'), 1000000, 'portal_invalid', lower=1)
            status = item.get('status')
            if status not in _STATUSES:
                raise InputError('portal_invalid')
            remarks = optional_text(item.get('remarks'), 200, 'portal_invalid')
            form[f'status_{student_id}'] = status
            form[f'remarks_{student_id}'] = remarks
        result = save_teacher_attendance(session.get('user_id'), timetable_id, form)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Attendance save failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(result, int):
        return _service_error(result)
    return json_ok({'saved': safe_count(result)})


def _history(timetable_id):
    denied = _teacher()
    if denied:
        return denied
    try:
        page = load_attendance_history(session.get('user_id'), timetable_id)
    except Exception:
        current_app.logger.exception('Attendance history failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(page, dict):
        return _service_error(page)
    lecture = page.get('lecture') or {}
    rows = []
    for row in page.get('history') or []:
        rows.append({
            'date': safe_stamp(row.get('attendance_date'))[:10],
            'total': safe_count(row.get('total_students')),
            'present': safe_count(row.get('present')),
            'late': safe_count(row.get('late')),
            'absent': safe_count(row.get('absent')),
            'marked_at': safe_stamp(row.get('marked_at')),
        })
    return json_ok({
        'subject': safe_text(lecture.get('subject_name'), 100),
        'class_name': safe_text(lecture.get('class_name'), 100),
        'division_name': safe_text(lecture.get('division_name'), 50),
        'history': rows,
    })


def _student_error(page):
    message = page.get('error') if isinstance(page, dict) else ''
    if message not in _STUDENT_ERRORS:
        message = _MESSAGES['portal_unavailable']
    return json_error(message, 404 if 'not found' in message.lower() or 'No attendance' in message else 500, 'portal_unavailable')


def _student_attendance():
    denied = _student()
    if denied:
        return denied
    try:
        page = load_student_attendance(session.get('user_id'))
    except Exception:
        current_app.logger.exception('Student attendance failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(page, dict) or page.get('error'):
        return _student_error(page)
    stats = page.get('overall_stats') or {}
    subjects = []
    for row in page.get('subject_wise') or []:
        subjects.append({
            'id': safe_count(row.get('subject_id')),
            'subject': safe_text(row.get('subject_name'), 100),
            'scheduled': safe_count(row.get('total_lectures')),
            'attended': safe_count(row.get('attended_lectures')),
            'present': safe_count(row.get('present_count')),
            'late': safe_count(row.get('late_count')),
            'absent': safe_count(row.get('absent_count')),
            'percentage': _percent(row.get('attendance_percentage')),
        })
    recent = []
    for row in page.get('recent_records') or []:
        recent.append({
            'date': safe_text(row.get('attendance_date'), 20),
            'subject': safe_text(row.get('subject_name'), 100),
            'class_info': safe_text(row.get('class_info') or '', 120),
            'status': safe_text(row.get('status') or '', 20),
            'remarks': safe_text(row.get('remarks') or '', 200),
            'marked_by': safe_text(row.get('marked_by_name') or '', 100),
        })
    return json_ok({
        'percentage': _percent(stats.get('attendance_percentage')),
        'scheduled': safe_count(stats.get('total_lectures_scheduled')),
        'attended': safe_count(stats.get('total_lectures_attended')),
        'present': safe_count(stats.get('present_count')),
        'late': safe_count(stats.get('late_count')),
        'absent': safe_count(stats.get('absent_count')),
        'subjects': subjects,
        'recent': recent,
    })


def _subject_attendance(subject_id):
    denied = _student()
    if denied:
        return denied
    try:
        page = load_subject_attendance(session.get('user_id'), subject_id)
    except Exception:
        current_app.logger.exception('Subject attendance failed')
        return json_error(_MESSAGES['portal_unavailable'], 500, 'portal_unavailable')
    if not isinstance(page, dict) or page.get('error'):
        return _student_error(page)
    stats = page.get('subject_stats') or {}
    records = []
    for row in page.get('attendance_records') or []:
        records.append({
            'date': safe_text(row.get('attendance_date'), 20),
            'status': safe_text(row.get('status') or '', 20),
            'start_time': safe_text(row.get('start_time'), 12),
            'end_time': safe_text(row.get('end_time'), 12),
            'remarks': safe_text(row.get('remarks') or '', 200),
            'marked_at': safe_text(row.get('marked_at'), 24),
        })
    months = []
    for row in page.get('monthly_breakdown') or []:
        months.append({
            'month': safe_text(row.get('month') or row.get('month_name') or '', 20),
            'total': safe_count(row.get('total_lectures')),
            'present': safe_count(row.get('present')),
            'late': safe_count(row.get('late')),
            'absent': safe_count(row.get('absent')),
            'percentage': _percent(row.get('percentage')),
        })
    return json_ok({
        'subject': safe_text(stats.get('subject_name'), 100),
        'percentage': _percent(stats.get('attendance_percentage')),
        'scheduled': safe_count(stats.get('total_lectures')),
        'attended': safe_count(stats.get('attended_lectures')),
        'present': safe_count(stats.get('present_count')),
        'late': safe_count(stats.get('late_count')),
        'absent': safe_count(stats.get('absent_count')),
        'records': records,
        'months': months,
    })
