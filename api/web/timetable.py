"""Timetable view and generation. Generation is queued; the generator itself is unchanged."""

import json
import re
from datetime import date

from flask import current_app, request, session

from extensions import get_db_connection
from api.web.access import InputError, allowed, body, close, optional_id, permission_denied, reject_input, whole_number
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_text
from core.db import transaction
from core.scope import current_scope
from data_access import institutions as institutions_store
from security import log_activity
from services.timetable_jobs import allocated_targets, enqueue_job, ensure_worker, load_job
from services.timetable_slots import SlotError, add_slot, check_slot, remove_slot, slot_cost

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
    'timetable_solver_invalid': 'Choose the greedy or the joint solver.',
    'slot_invalid': 'Enter a subject, a day and a start and end time (HH:MM).',
    'slot_time_invalid': 'The end time must be after the start time.',
    'slot_no_faculty': 'No faculty is allocated for this subject. Assign faculty first or choose one.',
    'slot_batch_invalid': 'That lab batch does not belong to this class and division.',
    'slot_holiday': 'Cannot add a session on a weekly holiday for this program.',
    'slot_class_busy': 'Overlaps with an existing session for this class/division.',
    'slot_batch_busy': 'This batch, or the whole division, already has a session at that time.',
    'slot_faculty_busy': 'Selected faculty is busy at that time.',
    'slot_faculty_unavailable': 'The faculty member is not available at that time.',
    'slot_room_busy': 'That room is in use at that time.',
    'slot_room_not_shared': 'That room belongs to another institution and is not shared with this one.',
    'slot_faculty_not_shared': 'That faculty member belongs to another institution and is not shared with this one.',
    'slot_not_found': 'That slot was not found.',
    'slot_failed': 'The slot could not be saved.',
}
_SCOPES = frozenset(('one', 'course', 'all'))
_SOLVERS = frozenset(('greedy', 'joint'))
_SLOT_FIELDS = frozenset((
    'course_id', 'class_id', 'division_id', 'subject_id', 'faculty_id', 'lab_batch_group_id', 'room_id',
    'day', 'start_time', 'end_time',
))
_CHECK_FIELDS = _SLOT_FIELDS | {'exclude_id'}


def register_timetable_routes(blueprint):
    blueprint.add_url_rule('/timetable', 'timetable_view', _view, methods=['GET'])
    blueprint.add_url_rule('/timetable/generate', 'timetable_generate', _generate, methods=['POST'])
    blueprint.add_url_rule('/timetable/jobs/<int:job_id>', 'timetable_job', _job, methods=['GET'])
    blueprint.add_url_rule('/timetable/slots', 'timetable_slot_add', _add_slot, methods=['POST'])
    blueprint.add_url_rule('/timetable/check', 'timetable_slot_check', _check_slot, methods=['POST'])
    blueprint.add_url_rule('/timetable/slots/<int:timetable_id>', 'timetable_slot_remove', _remove_slot, methods=['DELETE'])


def _option_id(name):
    raw = request.args.get(name, '')
    if raw in ('', None):
        return None
    if not str(raw).isdigit():
        raise InputError('timetable_selection_invalid')
    return int(raw)


def _sessions(cursor, where, params, scope=None):
    """Active slots matching `where` (aliases: t timetable, c course), with the ids the grid needs to move a slot."""
    scope_sql = ''
    scope_params = ()
    if scope is not None and scope.multiple:
        scope_sql, scope_params = scope.course_clause('c')
        scope_sql = f' AND {scope_sql}'
    cursor.execute(
        f"""
        SELECT t.id, t.course_id, t.class_id, t.division_id, t.day_of_week, t.start_time, t.end_time, t.subject_id, t.faculty_id,
               t.room_id, t.lab_batch_group_id, lbg.name AS lab_batch_name, s.name AS subject_name,
               COALESCE(f.name, '') AS faculty_name, r.room_number,
               COALESCE(c.name, '') AS course_name, COALESCE(cl.name, '') AS class_name, COALESCE(d.name, '') AS division_name
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN courses c ON c.id = t.course_id
        LEFT JOIN classes cl ON cl.id = t.class_id
        LEFT JOIN divisions d ON d.id = t.division_id
        LEFT JOIN faculty f ON f.user_id = t.faculty_id
        LEFT JOIN rooms r ON r.id = t.room_id
        LEFT JOIN lab_batch_groups lbg ON lbg.id = t.lab_batch_group_id
        WHERE {where} AND COALESCE(t.is_active, 1) = 1{scope_sql}
        ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time, lbg.name
        LIMIT 2000
        """,
        tuple(params) + tuple(scope_params),
    )
    return [
        {
            'id': safe_count(row.get('id')),
            'course_id': safe_count(row.get('course_id')),
            'class_id': safe_count(row.get('class_id')),
            'division_id': safe_count(row.get('division_id')),
            'cohort': ' / '.join(part for part in (
                safe_text(row.get('course_name'), 100), safe_text(row.get('class_name'), 100), safe_text(row.get('division_name'), 100),
            ) if part),
            'day': safe_text(row.get('day_of_week'), 12),
            'start_time': safe_clock(row.get('start_time')),
            'end_time': safe_clock(row.get('end_time')),
            'subject_id': safe_count(row.get('subject_id')),
            'subject': safe_text(row.get('subject_name'), 100),
            'faculty_id': safe_count(row.get('faculty_id')) or None,
            'faculty': safe_text(row.get('faculty_name') or '', 100),
            'room_id': safe_count(row.get('room_id')) or None,
            'room': safe_text(row.get('room_number') or '', 20),
            'lab_batch_group_id': safe_count(row.get('lab_batch_group_id')) or None,
            'lab_batch': safe_text(row.get('lab_batch_name') or '', 20),
        }
        for row in cursor.fetchall()
    ]


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
        scope = current_scope(cursor)
        course_clause, course_params = scope.course_clause('c')
        cursor.execute(f'SELECT c.id, c.name FROM courses c WHERE {course_clause} ORDER BY c.name', course_params)
        courses = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
        if course_id and not scope.allows(institutions_store.institution_of_course(cursor, course_id)):
            raise InputError('timetable_selection_invalid')
        cursor.execute('SELECT id, name FROM classes ORDER BY name')
        classes = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
        cursor.execute('SELECT id, name FROM divisions ORDER BY name')
        divisions = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
        sessions = []
        lab_batches = []
        subjects = []
        faculty_view = _option_id('faculty')
        room_view = _option_id('room')
        view = 'class'
        if course_id and class_id and division_id:
            sessions = _sessions(cursor, 't.course_id = %s AND t.class_id = %s AND t.division_id = %s', (course_id, class_id, division_id))
        elif faculty_view:
            # Every class this teacher meets, one week grid; the same rows the clash checks use.
            view = 'faculty'
            sessions = _sessions(cursor, 't.faculty_id = %s', (faculty_view,), scope=scope)
        elif room_view:
            view = 'room'
            sessions = _sessions(cursor, 't.room_id = %s', (room_view,), scope=scope)
        # Candidates follow the course's institution (or the caller's current one): own people and
        # rooms plus what is shared to it. Loaded without a class too, for the faculty and room views.
        institution_id = None
        if scope.multiple:
            institution_id = institutions_store.institution_of_course(cursor, course_id) if course_id else scope.institution_id
        faculty_clause, faculty_params = institutions_store.candidate_faculty_clause(institution_id, 'f', 'fd')
        cursor.execute(
            f'SELECT f.user_id, f.name, fd.institution_id, i.short_name AS institution_short_name FROM faculty f '
            f'LEFT JOIN departments fd ON fd.id = f.department_id LEFT JOIN institutions i ON i.id = fd.institution_id '
            f'WHERE f.user_id IS NOT NULL AND {faculty_clause} ORDER BY f.name',
            faculty_params,
        )
        faculty = [
            {
                'id': safe_count(row['user_id']), 'name': safe_text(row['name'], 100),
                'shared': institution_id is not None and safe_count(row.get('institution_id')) != institution_id,
                'institution': safe_text(row.get('institution_short_name') or '', 40),
            }
            for row in cursor.fetchall()
        ]
        rooms_clause, rooms_params = institutions_store.candidate_rooms_clause(institution_id, 'r')
        cursor.execute(
            f'SELECT r.id, r.room_number, r.room_type, r.capacity, r.institution_id, i.short_name AS institution_short_name '
            f'FROM rooms r JOIN institutions i ON i.id = r.institution_id WHERE {rooms_clause} ORDER BY r.room_number',
            rooms_params,
        )
        rooms = [
            {
                'id': safe_count(row['id']), 'name': safe_text(row['room_number'], 20),
                'kind': safe_text(row.get('room_type') or '', 30), 'capacity': safe_count(row.get('capacity')),
                'shared': institution_id is not None and safe_count(row.get('institution_id')) != institution_id,
                'institution': safe_text(row.get('institution_short_name') or '', 40),
            }
            for row in cursor.fetchall()
        ]
        if course_id and class_id and division_id:
            cursor.execute(
                """
                SELECT id, name, capacity FROM lab_batch_groups
                WHERE course_id = %s AND class_id = %s AND (division_id = %s OR division_id IS NULL) AND is_active = 1
                ORDER BY name
                """,
                (course_id, class_id, division_id),
            )
            lab_batches = [
                {'id': safe_count(row['id']), 'name': safe_text(row['name'], 20), 'capacity': safe_count(row.get('capacity')) or None}
                for row in cursor.fetchall()
            ]
            cursor.execute(
                "SELECT id, name, theory_practical FROM subjects WHERE course_id = %s AND (class_id IS NULL OR class_id = %s) ORDER BY name",
                (course_id, class_id),
            )
            subjects = [
                {'id': safe_count(row['id']), 'name': safe_text(row['name'], 100), 'kind': safe_text(row.get('theory_practical') or '', 20)}
                for row in cursor.fetchall()
            ]
        return json_ok({
            'courses': courses,
            'classes': classes,
            'divisions': divisions,
            'view': view,
            'sessions': sessions,
            'lab_batches': lab_batches,
            'subjects': subjects,
            'faculty': faculty,
            'rooms': rooms,
            'can_generate': allowed('timetable_generate'),
            'can_edit': allowed('timetable_change'),
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
            'lecture_minutes', 'break_start', 'break_duration', 'working_days', 'solver', 'rules_override', 'label',
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
    solver = payload.get('solver') or 'greedy'
    if solver not in _SOLVERS:
        raise InputError('timetable_solver_invalid')
    settings = {
        'week_start_date': week,
        'day_start': day_start,
        'day_end': day_end,
        'lecture_minutes': lecture,
        'break_start': break_start or None,
        'break_duration': break_duration,
        'working_days': ordered,
        'solver': solver,
    }
    override = payload.get('rules_override')
    if override not in (None, {}):
        # Per-run weight changes (services/timetable/rules.py); applied only while the capability is on.
        from services.timetable import rules as rule_set

        try:
            settings['rules_override'] = rule_set.clean_rules(override, partial=True)
        except ValueError:
            raise InputError('invalid_body')
    label = payload.get('label')
    if label not in (None, ''):
        # Name for the draft version (capability `timetable_versions`); ignored while it is off.
        if not isinstance(label, str) or len(label.strip()) > 120:
            raise InputError('invalid_body')
        settings['label'] = safe_text(label.strip(), 120)
    return settings


def _hhmm(value):
    if not isinstance(value, str) or not _TIME.match(value):
        raise InputError('slot_invalid')
    hours, minutes = int(value[:2]), int(value[3:])
    if hours > 23 or minutes > 59:
        raise InputError('slot_invalid')
    return f'{value}:00'


def _slot_body(fields):
    """Parse a slot payload into the keyword arguments `add_slot`/`check_slot` take."""
    payload = body(fields)
    day = payload.get('day')
    if day not in _DAYS:
        raise InputError('slot_invalid')
    slot = {
        'course_id': whole_number(payload.get('course_id'), 1000000, 'timetable_selection_invalid', lower=1),
        'class_id': whole_number(payload.get('class_id'), 1000000, 'timetable_selection_invalid', lower=1),
        'division_id': whole_number(payload.get('division_id'), 1000000, 'timetable_selection_invalid', lower=1),
        'subject_id': whole_number(payload.get('subject_id'), 1000000, 'slot_invalid', lower=1),
        'faculty_id': optional_id(payload.get('faculty_id'), 'slot_invalid'),
        'lab_batch_group_id': optional_id(payload.get('lab_batch_group_id'), 'slot_batch_invalid'),
        'room_id': optional_id(payload.get('room_id'), 'slot_invalid'),
        'day': day,
        'start_time': _hhmm(payload.get('start_time')),
        'end_time': _hhmm(payload.get('end_time')),
    }
    return slot, payload


def _add_slot():
    denied = permission_denied('timetable_change', 'timetable_unavailable', _MESSAGES['timetable_unavailable'])
    if denied:
        return denied
    connection = cursor = None
    try:
        slot, _payload = _slot_body(_SLOT_FIELDS)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        scope = current_scope(cursor)
        if scope.multiple and not scope.allows(institutions_store.institution_of_course(cursor, slot['course_id'])):
            raise InputError('timetable_selection_invalid')
        with transaction(connection):
            timetable_id = add_slot(cursor, **slot)
        try:
            log_activity(
                session.get('user_id'), 'timetable_slot_added', f'Added timetable slot #{timetable_id}',
                entity_type='timetable', entity_id=timetable_id,
                new_values={'subject_id': slot['subject_id'], 'day': slot['day'], 'start_time': slot['start_time'], 'lab_batch_group_id': slot['lab_batch_group_id']},
            )
        except Exception:
            current_app.logger.exception('Timetable slot audit failed')
        return json_ok({'id': safe_count(timetable_id)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except SlotError as exc:
        return json_error(safe_text(str(exc), 200) or _MESSAGES.get(exc.code, _MESSAGES['slot_failed']), 400, exc.code)
    except Exception:
        current_app.logger.exception('Timetable slot could not be added')
        return json_error(_MESSAGES['slot_failed'], 500, 'slot_failed')
    finally:
        close(cursor, connection)


def _check_slot():
    """Pure: the errors `POST /timetable/slots` would raise for this slot, plus the soft-rule cost. Writes nothing."""
    denied = permission_denied('timetable_change', 'timetable_unavailable', _MESSAGES['timetable_unavailable'])
    if denied:
        return denied
    connection = cursor = None
    try:
        slot, payload = _slot_body(_CHECK_FIELDS)
        exclude_id = optional_id(payload.get('exclude_id'), 'slot_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        scope = current_scope(cursor)
        if scope.multiple and not scope.allows(institutions_store.institution_of_course(cursor, slot['course_id'])):
            raise InputError('timetable_selection_invalid')
        faculty_id, errors = check_slot(cursor, **slot, exclude_id=exclude_id)
        cost = None
        if not errors and faculty_id:
            try:
                cost = slot_cost(cursor, **{**slot, 'faculty_id': faculty_id}, exclude_id=exclude_id)
            except Exception:
                current_app.logger.exception('Slot rule cost could not be computed')
                cost = None
        return json_ok({
            'ok': not errors,
            'faculty_id': safe_count(faculty_id) or None,
            'errors': [{'code': safe_text(err.code, 40), 'message': safe_text(str(err), 200)} for err in errors[:10]],
            'rule_cost': None if cost is None else {
                'before': safe_count(cost['cost_before']), 'after': safe_count(cost['cost_after']), 'delta': int(cost['delta']),
                'violations': [
                    {
                        'rule': safe_text(v.get('rule'), 40), 'title': safe_text(v.get('title'), 80), 'cost': safe_count(v.get('cost')),
                        'faculty': safe_text(v.get('faculty_name') or '', 100), 'detail': safe_text(v.get('detail') or '', 200),
                    }
                    for v in cost['violations'][:20]
                ],
            },
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Timetable slot could not be checked')
        return json_error(_MESSAGES['slot_failed'], 500, 'slot_failed')
    finally:
        close(cursor, connection)


def _remove_slot(timetable_id):
    denied = permission_denied('timetable_change', 'timetable_unavailable', _MESSAGES['timetable_unavailable'])
    if denied:
        return denied
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        scope = current_scope(cursor)
        if scope.multiple:
            cursor.execute('SELECT course_id FROM timetable WHERE id = %s', (timetable_id,))
            row = cursor.fetchone()
            if row is None or not scope.allows(institutions_store.institution_of_course(cursor, row['course_id'])):
                return json_error(_MESSAGES['slot_not_found'], 404, 'slot_not_found')
        with transaction(connection):
            outcome = remove_slot(cursor, timetable_id)
        if outcome is None:
            return json_error(_MESSAGES['slot_not_found'], 404, 'slot_not_found')
        try:
            log_activity(
                session.get('user_id'), 'timetable_slot_removed', f'{outcome.capitalize()} timetable slot #{timetable_id}',
                entity_type='timetable', entity_id=timetable_id, new_values={'outcome': outcome},
            )
        except Exception:
            current_app.logger.exception('Timetable slot audit failed')
        return json_ok({'outcome': outcome})
    except Exception:
        current_app.logger.exception('Timetable slot could not be removed')
        return json_error(_MESSAGES['slot_failed'], 500, 'slot_failed')
    finally:
        close(cursor, connection)


def _require_course_in_scope(course_id):
    """A course outside the caller's institutions reads as not chosen (no id probing)."""
    scope = current_scope()
    if not scope.multiple:
        return
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not scope.allows(institutions_store.institution_of_course(cursor, course_id)):
            raise InputError('timetable_selection_invalid')
    finally:
        close(cursor, connection)


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
        _require_course_in_scope(course_id)
        return [{'course_id': course_id, 'class_id': class_id, 'division_id': division_id, 'label': 'Selected class'}]
    course_id = None
    if scope == 'course':
        course_id = payload.get('course_id')
        if isinstance(course_id, bool) or not isinstance(course_id, int) or course_id <= 0:
            raise InputError('timetable_selection_invalid')
        _require_course_in_scope(course_id)
    targets, overflow = allocated_targets(course_id, scope=current_scope())
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
    version_id = None
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
        if isinstance(parsed, dict):
            version_id = safe_count(parsed.get('version_id')) or None
    return {
        'version_id': version_id,
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
