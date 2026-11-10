"""Syllabus units and coverage (capability `syllabus`).

GET /api/syllabus                 subjects in scope, and one subject's units and coverage
PUT /api/syllabus/<subject_id>    subjects_change_subject; replaces that subject's units

404 `capability_off` while the capability is off. A unit that already has a lesson log
cannot be removed (409 `syllabus_in_use`).
"""

from flask import current_app, request, session

from api.web.access import InputError, allowed, body, close, optional_id, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core import capabilities
from extensions import get_db_connection
from security import log_activity
from services import syllabus

_FIELDS = frozenset(('units',))
_STATUS = {
    'syllabus_invalid': 400,
    'subject_not_found': 404,
    'syllabus_in_use': 409,
    'syllabus_unavailable': 409,
    'capability_off': 404,
}
_MESSAGES = dict(syllabus.MESSAGES)


def register_syllabus_routes(blueprint):
    blueprint.add_url_rule('/syllabus', 'syllabus', _page, methods=['GET'])
    blueprint.add_url_rule('/syllabus/<int:subject_id>', 'syllabus_save', _save, methods=['PUT'])


def _hours(value):
    return None if value is None else float(value)


def _unit(row):
    return {
        'id': safe_count(row.get('id')),
        'unit_no': safe_count(row.get('unit_no')),
        'title': safe_text(row.get('title'), 120),
        'planned_hours': _hours(row.get('planned_hours')),
        'delivered_hours': _hours(row.get('delivered_hours')),
        'percent': _hours(row.get('percent')),
        'expected_hours': _hours(row.get('expected_hours')),
        'pace': safe_text(row.get('pace') or '', 20),
    }


def _coverage(report):
    if not report:
        return None
    return {
        'subject_id': safe_count(report['subject_id']),
        'subject_name': safe_text(report['subject_name'], 100),
        'course_code': safe_text(report['course_code'], 20),
        'elapsed_weeks': report['elapsed_weeks'],
        'total_weeks': report['total_weeks'],
        'units': [_unit(row) for row in report['units']],
    }


def _rejected(exc):
    return json_error(_MESSAGES.get(exc.code, _MESSAGES['syllabus_invalid']), _STATUS.get(exc.code, 400), exc.code)


def _open():
    if allowed('syllabus_view') or allowed('subjects_view_subject'):
        denied = None
    else:
        denied = permission_denied('syllabus_view', 'syllabus_unavailable', _MESSAGES['syllabus_unavailable'])
    if denied:
        return denied
    off = capabilities.require_capability(syllabus.CAPABILITY)
    if off:
        return off
    return None


def _page():
    denied = _open()
    if denied:
        return denied
    connection = cursor = None
    try:
        subject_id = optional_id(request.args.get('subject_id'), 'syllabus_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not syllabus.tables_ready(cursor):
            return json_error(_MESSAGES['syllabus_unavailable'], 409, 'syllabus_unavailable')
        subjects = [
            {'id': safe_count(row['id']), 'name': safe_text(row['name'], 140)}
            for row in syllabus.subject_choices(cursor)
            if safe_count(row.get('id'))
        ]
        if subject_id is None and subjects:
            subject_id = subjects[0]['id']
        report = syllabus.coverage_for(cursor, subject_id, scoped=True) if subject_id else None
        if subject_id and report is None:
            return json_error(_MESSAGES['subject_not_found'], 404, 'subject_not_found')
        return json_ok({
            'subjects': subjects,
            'coverage': _coverage(report),
            'permissions': {'change': allowed('syllabus_change') or allowed('subjects_change_subject')},
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Syllabus page failed')
        return json_error(_MESSAGES['syllabus_unavailable'], 500, 'syllabus_unavailable')
    finally:
        close(cursor, connection)


def _save(subject_id):
    if allowed('syllabus_change') or allowed('subjects_change_subject'):
        denied = None
    else:
        denied = permission_denied('syllabus_change', 'syllabus_unavailable', _MESSAGES['syllabus_unavailable'])
    if denied:
        return denied
    off = capabilities.require_capability(syllabus.CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        payload = body(_FIELDS)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            syllabus.replace_units(cursor, subject_id, payload.get('units'))
        except syllabus.LessonRejected as exc:
            connection.rollback()
            return _rejected(exc)
        log_activity(
            session.get('user_id'), 'syllabus_saved', f'Syllabus saved for subject {subject_id}',
            entity_type='subject', entity_id=subject_id, new_values={'units': len(payload.get('units') or [])}, cursor=cursor,
        )
        connection.commit()
        report = syllabus.coverage_for(cursor, subject_id, scoped=True)
        return json_ok({'coverage': _coverage(report)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Syllabus save failed')
        return json_error(_MESSAGES['syllabus_unavailable'], 500, 'syllabus_unavailable')
    finally:
        close(cursor, connection)
