"""Timetable view and generation. Generation is queued; the generator itself is unchanged."""

import json
import re
from datetime import date

from flask import current_app, request, session

from extensions import get_db_connection
from api.web.access import InputError, allowed, body, close, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_text
from security import log_activity
from services.timetable_jobs import allocated_targets, enqueue_job, ensure_worker, load_job

_DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
_TIME = re.compile(r'^\d{2}:\d{2}$')
_MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'timetable_unavailable': 'The page could not be loaded.',
    'timetable_selection_invalid': 'Choose a course, class, and division.',
    'timetable_generate_failed': 'The timetable could not be generated.',
    'timetable_targets_empty': 'No class with a faculty allocation matches that choice.',
    'timetable_too_many': 'More than 1000 classes match. Generate one course at a time.',
    'timetable_job_not_found': 'That generation was not found.',
}
_SCOPES = frozenset(('one', 'course', 'all'))


def register_timetable_routes(blueprint):
    blueprint.add_url_rule('/timetable', 'timetable_view', _view, methods=['GET'])
    blueprint.add_url_rule('/timetable/generate', 'timetable_generate', _generate, methods=['POST'])
    blueprint.add_url_rule('/timetable/jobs/<int:job_id>', 'timetable_job', _job, methods=['GET'])


def _option_id(name):
    raw = request.args.get(name, '')
    if raw in ('', None):
        return None
    if not str(raw).isdigit():
        raise InputError('timetable_selection_invalid')
    return int(raw)


def _view():
    denied = permission_denied('timetable_change', 'timetable_unavailable', _MESSAGES['timetable_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        course_id = _option_id('course')
        class_id = _option_id('class')
        division_id = _option_id('division')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT id, name FROM courses ORDER BY name')
        courses = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
        cursor.execute('SELECT id, name FROM classes ORDER BY name')
        classes = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
        cursor.execute('SELECT id, name FROM divisions ORDER BY name')
        divisions = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
        sessions = []
        if course_id and class_id and division_id:
            cursor.execute(
                """
                SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name,
                       COALESCE(f.name, '') AS faculty_name, r.room_number
                FROM timetable t
                JOIN subjects s ON s.id = t.subject_id
                LEFT JOIN faculty f ON f.user_id = t.faculty_id
                LEFT JOIN rooms r ON r.id = t.room_id
                WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s
                  AND COALESCE(t.is_active, 1) = 1
                ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
                """,
                (course_id, class_id, division_id),
            )
            sessions = [
                {
                    'day': safe_text(row.get('day_of_week'), 12),
                    'start_time': safe_clock(row.get('start_time')),
                    'end_time': safe_clock(row.get('end_time')),
                    'subject': safe_text(row.get('subject_name'), 100),
                    'faculty': safe_text(row.get('faculty_name') or '', 100),
                    'room': safe_text(row.get('room_number') or '', 20),
                }
                for row in cursor.fetchall()
            ]
        return json_ok({
            'courses': courses,
            'classes': classes,
            'divisions': divisions,
            'sessions': sessions,
            'can_generate': allowed('timetable_generate'),
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Timetable view failed')
        return json_error(_MESSAGES['timetable_unavailable'], 500, 'timetable_unavailable')
    finally:
        close(cursor, connection)


def _generate():
    denied = permission_denied('timetable_generate', 'timetable_unavailable', _MESSAGES['timetable_unavailable'])
    if denied:
        return denied
    try:
        payload = body(frozenset((
            'scope', 'course_id', 'class_id', 'division_id', 'week_start_date', 'day_start', 'day_end',
            'lecture_minutes', 'break_start', 'break_duration', 'working_days',
        )))
        settings = _settings(payload)
        targets = _targets(payload)
        settings['targets'] = targets
        job_id, attached = enqueue_job(settings, session.get('user_id'))
        if not attached:
            try:
                log_activity(
                    session.get('user_id'),
                    'timetable_generate',
                    f'Queued timetable generation #{job_id} ({len(targets)} classes)',
                    entity_type='timetable_job',
                    entity_id=job_id,
                    new_values={'classes': len(targets), 'status': 'queued'},
                )
            except Exception:
                current_app.logger.exception('Timetable job was queued but the activity log failed')
        ensure_worker(current_app._get_current_object())
        record = load_job(job_id) or {'id': job_id, 'status': 'queued', 'total_count': len(targets)}
        body_out = _job_body(record)
        body_out['attached'] = attached
        return json_ok(body_out)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Timetable generation could not be queued')
        return json_error(_MESSAGES['timetable_generate_failed'], 500, 'timetable_generate_failed')


def _job(job_id):
    denied = permission_denied('timetable_generate', 'timetable_unavailable', _MESSAGES['timetable_unavailable'])
    if denied:
        return denied
    try:
        ensure_worker(current_app._get_current_object())
        record = load_job(job_id)
        if not record:
            return json_error(_MESSAGES['timetable_job_not_found'], 404, 'timetable_job_not_found')
        return json_ok(_job_body(record))
    except Exception:
        current_app.logger.exception('Timetable job could not be loaded')
        return json_error(_MESSAGES['timetable_generate_failed'], 500, 'timetable_generate_failed')


def _settings(payload):
    week = payload.get('week_start_date') or date.today().isoformat()
    if not isinstance(week, str) or len(week) != 10:
        raise InputError('invalid_body')
    try:
        date.fromisoformat(week)
    except ValueError:
        raise InputError('invalid_body')
    day_start = payload.get('day_start') or '09:00'
    day_end = payload.get('day_end') or '15:00'
    if not isinstance(day_start, str) or not isinstance(day_end, str) or not _TIME.match(day_start) or not _TIME.match(day_end) or day_start >= day_end:
        raise InputError('invalid_body')
    days = payload.get('working_days') or list(_DAYS[:6])
    if not isinstance(days, list) or not days or len(days) > 7 or any(day not in _DAYS for day in days):
        raise InputError('invalid_body')
    lecture = payload.get('lecture_minutes')
    if lecture in (None, ''):
        lecture = 45
    break_duration = payload.get('break_duration')
    if break_duration in (None, ''):
        break_duration = 0
    if isinstance(lecture, bool) or not isinstance(lecture, int) or lecture < 15 or lecture > 180:
        raise InputError('invalid_body')
    if isinstance(break_duration, bool) or not isinstance(break_duration, int) or break_duration < 0 or break_duration > 180:
        raise InputError('invalid_body')
    break_start = payload.get('break_start') or ''
    if break_start and (not isinstance(break_start, str) or not _TIME.match(break_start)):
        raise InputError('invalid_body')
    ordered = [day for day in _DAYS if day in days]
    return {
        'week_start_date': week,
        'day_start': day_start,
        'day_end': day_end,
        'lecture_minutes': lecture,
        'break_start': break_start or None,
        'break_duration': break_duration,
        'working_days': ordered,
    }


def _targets(payload):
    scope = payload.get('scope') or 'one'
    if scope not in _SCOPES:
        raise InputError('invalid_body')
    if scope == 'one':
        course_id = payload.get('course_id')
        class_id = payload.get('class_id')
        division_id = payload.get('division_id')
        if not all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in (course_id, class_id, division_id)):
            raise InputError('timetable_selection_invalid')
        return [{'course_id': course_id, 'class_id': class_id, 'division_id': division_id, 'label': 'Selected class'}]
    course_id = None
    if scope == 'course':
        course_id = payload.get('course_id')
        if isinstance(course_id, bool) or not isinstance(course_id, int) or course_id <= 0:
            raise InputError('timetable_selection_invalid')
    targets, overflow = allocated_targets(course_id)
    if overflow:
        raise InputError('timetable_too_many')
    if not targets:
        raise InputError('timetable_targets_empty')
    return targets


def _job_body(record):
    progress = safe_count(record.get('progress'))
    if progress > 100:
        progress = 100
    summary = None
    failures = []
    raw = record.get('summary_json')
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get('assigned'), list):
            summary = parsed
        elif isinstance(parsed, dict) and isinstance(parsed.get('failures'), list):
            failures = [
                {'label': safe_text(item.get('label'), 180), 'message': safe_text(item.get('message'), 160)}
                for item in parsed['failures'][:20]
                if isinstance(item, dict)
            ]
    return {
        'id': safe_count(record.get('id')),
        'status': safe_text(record.get('status'), 20),
        'progress': progress,
        'total': safe_count(record.get('total_count')),
        'done': safe_count(record.get('done_count')),
        'assigned_count': safe_count(record.get('assigned_count')),
        'unassigned_count': safe_count(record.get('unassigned_count')),
        'failed_count': safe_count(record.get('failed_count')),
        'message': safe_text(record.get('message') or '', 300),
        'result': summary,
        'failures': failures,
    }
