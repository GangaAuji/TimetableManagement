"""Exam timetable (capability `exams`).

GET  /api/exams                         exams, subjects, rooms, terms and one exam's sessions
POST /api/exams                         create an exam
POST /api/exams/<id>/solve              place papers, seats and invigilators
DELETE /api/exams/<id>
GET  /api/exams/<id>/seating            seating plan PDF
GET  /api/exams/<id>/hall-tickets       hall tickets PDF
GET  /api/portal/teacher/exams          the signed-in teacher's invigilation duties

Reading needs `exams_view` or `timetable_generate`. Solving and deleting need
`exams_change` or `timetable_generate`. 404 `capability_off` while off.
"""

import os
import tempfile

from flask import Response, current_app, session

from api.web.access import InputError, allowed, body, close, optional_id, permission_denied, reject_input, required_text
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core import capabilities
from extensions import get_db_connection
from security import log_activity
from services import exams

_STATUS = {
    'exam_invalid': 400,
    'exam_no_students': 400,
    'exam_no_room': 400,
    'exam_no_invigilator': 400,
    'exam_unsolved': 409,
    'exam_unavailable': 409,
    'exam_not_found': 404,
    'subject_not_found': 404,
    'capability_off': 404,
}
_MESSAGES = dict(exams.MESSAGES)
_MESSAGES['invalid_body'] = _MESSAGES['exam_invalid']
_CREATE_FIELDS = frozenset(('name', 'kind', 'term_id'))
_SOLVE_FIELDS = frozenset(('subject_ids', 'papers', 'dates', 'slots', 'room_ids', 'seating_gap', 'students_per_room'))
_SEATING_FIELDS = (
    'room_number', 'seat_no', 'roll_number', 'student_name', 'course_code', 'subject_name', 'exam_date', 'start_time', 'end_time',
)
_TICKET_FIELDS = (
    'roll_number', 'student_name', 'course_code', 'subject_name', 'exam_date', 'start_time', 'end_time', 'room_number', 'seat_no',
)


def register_exam_routes(blueprint):
    blueprint.add_url_rule('/exams', 'exams', _page, methods=['GET'])
    blueprint.add_url_rule('/exams', 'exams_create', _create, methods=['POST'])
    blueprint.add_url_rule('/exams/<int:exam_id>/solve', 'exams_solve', _solve, methods=['POST'])
    blueprint.add_url_rule('/exams/<int:exam_id>', 'exams_delete', _delete, methods=['DELETE'])
    blueprint.add_url_rule('/exams/<int:exam_id>/seating', 'exams_seating', lambda exam_id: _pdf(exam_id, 'seating'), methods=['GET'])
    blueprint.add_url_rule('/exams/<int:exam_id>/hall-tickets', 'exams_tickets', lambda exam_id: _pdf(exam_id, 'tickets'), methods=['GET'])
    blueprint.add_url_rule('/portal/teacher/exams', 'portal_teacher_exams', _teacher, methods=['GET'])


def _view_denied():
    if allowed('exams_view') or allowed('timetable_generate'):
        return None
    return permission_denied('exams_view', 'exam_unavailable', _MESSAGES['exam_unavailable'])


def _change_denied():
    if allowed('exams_change') or allowed('timetable_generate'):
        return None
    return permission_denied('exams_change', 'exam_unavailable', _MESSAGES['exam_unavailable'])


def _off():
    return capabilities.require_capability(exams.CAPABILITY)


def _rejected(exc):
    message = str(exc) if exc.code == 'exam_unsolved' else _MESSAGES.get(exc.code, _MESSAGES['exam_invalid'])
    return json_error(message, _STATUS.get(exc.code, 400), exc.code)


def _ready(cursor):
    if not exams.tables_ready(cursor):
        return json_error(_MESSAGES['exam_unavailable'], 409, 'exam_unavailable')
    return None


def _open():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    missing = _ready(cursor)
    if missing:
        close(cursor, connection)
        return None, None, missing
    return connection, cursor, None


def _fail(connection, exc):
    if connection is not None:
        connection.rollback()
    if isinstance(exc, exams.ExamError):
        return _rejected(exc)
    if isinstance(exc, InputError):
        return reject_input(_MESSAGES, exc.code)
    current_app.logger.exception('Exam request failed')
    return json_error(_MESSAGES['exam_unavailable'], 500, 'exam_unavailable')


def _page():
    denied = _view_denied()
    if denied:
        return denied
    off = _off()
    if off:
        return off
    connection = cursor = None
    try:
        connection, cursor, missing = _open()
        if missing:
            return missing
        exam_id = optional_id(request_exam(), 'exam_invalid')
        return json_ok(_public_page(cursor, exam_id))
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Exam page failed')
        return json_error(_MESSAGES['exam_unavailable'], 500, 'exam_unavailable')
    finally:
        close(cursor, connection)


def request_exam():
    from flask import request
    return request.args.get('exam_id')


def _create():
    denied = _change_denied()
    if denied:
        return denied
    off = _off()
    if off:
        return off
    connection = None
    try:
        payload = body(_CREATE_FIELDS)
        connection, cursor, missing = _open()
        if missing:
            return missing
        exam_id = exams.create_exam(
            cursor,
            name=required_text(payload.get('name'), 80, 'exam_invalid'),
            kind=payload.get('kind'),
            term_id=optional_id(payload.get('term_id'), 'exam_invalid'),
            created_by=session.get('user_id'),
        )
        log_activity(session.get('user_id'), 'exam_created', f'Exam {exam_id} created', entity_type='exam', entity_id=exam_id, cursor=cursor)
        connection.commit()
        return json_ok(_public_page(cursor, exam_id))
    except (exams.ExamError, InputError) as exc:
        return _fail(connection, exc)
    except Exception:
        return _fail(connection, None)


def _solve(exam_id):
    denied = _change_denied()
    if denied:
        return denied
    off = _off()
    if off:
        return off
    connection = None
    try:
        payload = body(_SOLVE_FIELDS)
        connection, cursor, missing = _open()
        if missing:
            return missing
        summary = exams.solve_into(cursor, exam_id, payload)
        log_activity(
            session.get('user_id'), 'exam_solved', f'Exam {exam_id} solved ({summary["sessions"]} papers)',
            entity_type='exam', entity_id=exam_id, cursor=cursor,
        )
        connection.commit()
        page = _public_page(cursor, exam_id)
        page['solved'] = summary
        return json_ok(page)
    except (exams.ExamError, InputError) as exc:
        return _fail(connection, exc)
    except Exception:
        return _fail(connection, None)


def _delete(exam_id):
    denied = _change_denied()
    if denied:
        return denied
    off = _off()
    if off:
        return off
    connection = None
    try:
        connection, cursor, missing = _open()
        if missing:
            return missing
        exams.delete_exam(cursor, exam_id)
        log_activity(session.get('user_id'), 'exam_deleted', f'Exam {exam_id} deleted', entity_type='exam', entity_id=exam_id, cursor=cursor)
        connection.commit()
        return json_ok(_public_page(cursor, None))
    except (exams.ExamError, InputError) as exc:
        return _fail(connection, exc)
    except Exception:
        return _fail(connection, None)


def _pdf(exam_id, kind):
    denied = _view_denied()
    if denied:
        return denied
    off = _off()
    if off:
        return off
    connection = cursor = None
    try:
        connection, cursor, missing = _open()
        if missing:
            return missing
        exam = exams.load_exam(cursor, exam_id)
        if exam is None:
            return json_error(_MESSAGES['exam_not_found'], 404, 'exam_not_found')
        if kind == 'seating':
            rows = exams.seating_rows(cursor, exam_id)
            fields = _SEATING_FIELDS
            filename = 'seating-plan.pdf'
            title = f"Seating plan — {exam['name']}"
        else:
            rows = exams.hall_ticket_rows(cursor, exam_id)
            fields = _TICKET_FIELDS
            filename = 'hall-tickets.pdf'
            title = f"Hall tickets — {exam['name']}"
        if not rows:
            return json_error('Solve the timetable before downloading.', 409, 'exam_invalid')
        return _pdf_response(filename, fields, rows, title)
    except Exception:
        current_app.logger.exception('Exam PDF failed')
        return json_error(_MESSAGES['exam_unavailable'], 500, 'exam_unavailable')
    finally:
        close(cursor, connection)


def _teacher():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Teacher':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    off = _off()
    if off:
        return off
    connection = cursor = None
    try:
        connection, cursor, missing = _open()
        if missing:
            return missing
        duties = []
        for row in exams.teacher_duties(cursor, session.get('user_id')):
            duties.append({
                'exam_name': safe_text(row['exam_name'], 80),
                'subject_name': safe_text(row['subject_name'], 100),
                'course_code': safe_text(row.get('course_code') or '', 20),
                'date': row['exam_date'].isoformat() if hasattr(row['exam_date'], 'isoformat') else str(row['exam_date'])[:10],
                'start': exams.hhmm(row['start_time']),
                'end': exams.hhmm(row['end_time']),
                'room_number': safe_text(row['room_number'], 20),
                'role': row['role'] if row['role'] in exams.ROLES else 'invigilator',
            })
        return json_ok({'duties': duties})
    except Exception:
        current_app.logger.exception('Teacher exam duties failed')
        return json_error(_MESSAGES['exam_unavailable'], 500, 'exam_unavailable')
    finally:
        close(cursor, connection)


def _public_page(cursor, exam_id):
    listed = exams.list_exams(cursor)
    if exam_id is None and listed:
        exam_id = int(listed[0]['id'])
    current = exams.load_exam(cursor, exam_id) if exam_id else None
    return {
        'exams': [_exam(row) for row in listed],
        'exam': _exam(current) if current else None,
        'sessions': [_session(row) for row in (exams.sessions_for(cursor, current['id']) if current else [])],
        'subjects': [_subject(row) for row in exams.subject_choices(cursor)],
        'rooms': [_room(row) for row in exams.room_choices(cursor)],
        'terms': [_term(row) for row in exams.term_choices(cursor)],
        'kinds': list(exams.KINDS),
        'permissions': {'change': allowed('exams_change') or allowed('timetable_generate')},
    }


def _exam(row):
    if row is None:
        return None
    return {
        'id': safe_count(row['id']),
        'name': safe_text(row['name'], 80),
        'kind': row['kind'] if row['kind'] in exams.KINDS else 'internal',
        'term_id': safe_count(row['term_id']) if row.get('term_id') else None,
        'term_name': safe_text(row.get('term_name') or '', 80),
        'seating_gap': safe_count(row.get('seating_gap') or 0),
        'students_per_room': safe_count(row['students_per_room']) if row.get('students_per_room') else None,
    }


def _subject(row):
    label = safe_text(row['name'], 100)
    code = safe_text(row.get('course_code') or '', 20)
    class_name = safe_text(row.get('class_name') or '', 80)
    return {
        'id': safe_count(row['id']),
        'name': label,
        'course_code': code,
        'class_name': class_name,
        'elective': bool(row.get('is_elective')) or str(row.get('course_type') or '').startswith('Elective'),
    }


def _room(row):
    return {
        'id': safe_count(row['id']),
        'room_number': safe_text(row['room_number'], 20),
        'room_type': safe_text(row.get('room_type') or '', 40),
        'capacity': safe_count(row.get('capacity') or 0),
    }


def _term(row):
    return {
        'id': safe_count(row['id']),
        'name': safe_text(row['name'], 80),
        'start': row['start_date'].isoformat() if hasattr(row['start_date'], 'isoformat') else str(row['start_date'])[:10],
        'end': row['end_date'].isoformat() if hasattr(row['end_date'], 'isoformat') else str(row['end_date'])[:10],
    }


def _session(row):
    return {
        'id': safe_count(row['id']),
        'subject_name': safe_text(row['subject_name'], 100),
        'course_code': safe_text(row.get('course_code') or '', 20),
        'date': row['exam_date'].isoformat() if hasattr(row['exam_date'], 'isoformat') else str(row['exam_date'])[:10],
        'start': exams.hhmm(row['start_time']),
        'end': exams.hhmm(row['end_time']),
        'cohorts': [
            safe_text(' / '.join(part for part in (item.get('class_name'), item.get('division_name')) if part), 120)
            for item in row.get('cohorts') or []
        ],
        'rooms': [
            {
                'room_number': safe_text(item.get('room_number') or '', 20),
                'faculty_name': safe_text(item.get('faculty_name') or '', 100),
                'role': item.get('role') if item.get('role') in exams.ROLES else 'invigilator',
                'seats': safe_count(item.get('seats') or 0),
            }
            for item in row.get('rooms') or []
        ],
    }


def _pdf_response(filename, fieldnames, rows, title):
    from services.reports_admin.renderers import render

    handle = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    path = handle.name
    handle.close()
    try:
        render(path, 'pdf', fieldnames, rows, title=title)
        with open(path, 'rb') as source:
            payload = source.read()
    finally:
        os.remove(path)
    return Response(payload, mimetype='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})
