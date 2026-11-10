"""Internal assessment (capability `assessments`).

GET  /api/assessments                              scheme, outcomes and attainment for one subject
PUT  /api/assessments/subjects/<id>/outcomes       replace course outcomes
PUT  /api/assessments/subjects/<id>/components     replace components and their CO links
PUT  /api/assessments/subjects/<id>/map            replace CO–PO levels
PUT  /api/assessments/courses/<id>/outcomes        replace program outcomes
GET  /api/assessments/components/<id>/marks        roster and marks
PUT  /api/assessments/components/<id>/marks        save marks
POST /api/assessments/components/<id>/import       CSV, worksheet or rows of roll_number, marks
POST /api/assessments/components/<id>/lock         lock (students may then see the marks)
POST /api/assessments/components/<id>/unlock

GET /api/portal/student/assessments                the signed-in student's locked marks
GET /api/portal/teacher/assessments                subjects the signed-in teacher is allocated

Reading needs `assessments_view` or `subjects_view_subject`. Changing the scheme needs
`assessments_change` or `subjects_change_subject`. Locking needs `assessments_lock` or
`subjects_change_subject`. A teacher allocated to the subject may read and save its marks.
404 `capability_off` while the capability is off.
"""

import base64

from flask import current_app, session

from api.web.access import InputError, allowed, body, close, optional_id, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core import capabilities
from extensions import get_db_connection
from security import log_activity
from services import assessment

_STATUS = {
    'assessment_invalid': 400,
    'assessment_marks_invalid': 400,
    'assessment_import_invalid': 400,
    'assessment_locked': 409,
    'assessment_in_use': 409,
    'assessment_unavailable': 409,
    'subject_not_found': 404,
    'component_not_found': 404,
    'capability_off': 404,
}
_MESSAGES = dict(assessment.MESSAGES)
_OUTCOME_FIELDS = frozenset(('outcomes',))
_COMPONENT_FIELDS = frozenset(('components',))
_MAP_FIELDS = frozenset(('links',))
_MARK_FIELDS = frozenset(('marks',))
_IMPORT_FIELDS = frozenset(('csv', 'rows', 'xlsx_base64'))


def register_assessment_routes(blueprint):
    blueprint.add_url_rule('/assessments', 'assessments', _page, methods=['GET'])
    blueprint.add_url_rule('/assessments/subjects/<int:subject_id>/outcomes', 'assessment_outcomes', _save_outcomes, methods=['PUT'])
    blueprint.add_url_rule('/assessments/subjects/<int:subject_id>/components', 'assessment_components', _save_components, methods=['PUT'])
    blueprint.add_url_rule('/assessments/subjects/<int:subject_id>/map', 'assessment_map', _save_map, methods=['PUT'])
    blueprint.add_url_rule('/assessments/courses/<int:course_id>/outcomes', 'assessment_program_outcomes', _save_program, methods=['PUT'])
    blueprint.add_url_rule('/assessments/components/<int:component_id>/marks', 'assessment_marks', _marks, methods=['GET'])
    blueprint.add_url_rule('/assessments/components/<int:component_id>/marks', 'assessment_marks_save', _save_marks, methods=['PUT'])
    blueprint.add_url_rule('/assessments/components/<int:component_id>/import', 'assessment_import', _import, methods=['POST'])
    blueprint.add_url_rule('/assessments/components/<int:component_id>/lock', 'assessment_lock', lambda component_id: _lock(component_id, True), methods=['POST'])
    blueprint.add_url_rule('/assessments/components/<int:component_id>/unlock', 'assessment_unlock', lambda component_id: _lock(component_id, False), methods=['POST'])
    blueprint.add_url_rule('/portal/student/assessments', 'portal_student_assessments', _student, methods=['GET'])
    blueprint.add_url_rule('/portal/teacher/assessments', 'portal_teacher_assessments', _teacher, methods=['GET'])


def _view_denied():
    if allowed('assessments_view') or allowed('subjects_view_subject'):
        return None
    return permission_denied('assessments_view', 'assessment_unavailable', _MESSAGES['assessment_unavailable'])


def _change_denied():
    if allowed('assessments_change') or allowed('subjects_change_subject'):
        return None
    return permission_denied('assessments_change', 'assessment_unavailable', _MESSAGES['assessment_unavailable'])


def _lock_denied():
    if allowed('assessments_lock') or allowed('subjects_change_subject'):
        return None
    return permission_denied('assessments_lock', 'assessment_unavailable', _MESSAGES['assessment_unavailable'])


def _may_change_scheme():
    return allowed('assessments_change') or allowed('subjects_change_subject')


def _may_enter(cursor, component):
    if _may_change_scheme():
        return True
    return session.get('role') == 'Teacher' and assessment.teaches(cursor, session.get('user_id'), component['subject_id'])


def _may_read_marks(cursor, component):
    if allowed('assessments_view') or allowed('subjects_view_subject'):
        return True
    return session.get('role') == 'Teacher' and assessment.teaches(cursor, session.get('user_id'), component['subject_id'])


def _rejected(exc):
    return json_error(_MESSAGES.get(exc.code, _MESSAGES['assessment_invalid']), _STATUS.get(exc.code, 400), exc.code)


def _off():
    return capabilities.require_capability(assessment.CAPABILITY)


def _ready(cursor):
    if not assessment.tables_ready(cursor):
        return json_error(_MESSAGES['assessment_unavailable'], 409, 'assessment_unavailable')
    return None


def _num(value):
    if value is None:
        return None
    return float(value)


def _component(row):
    return {
        'id': safe_count(row['id']),
        'name': safe_text(row['name'], 80),
        'max_marks': _num(row['max_marks']),
        'weight': _num(row['weight']),
        'kind': row['kind'] if row['kind'] in assessment.KINDS else 'IA',
        'locked': bool(row.get('locked')),
        'outcome_codes': [safe_text(code, 12) for code in row.get('outcome_codes') or []],
    }


def _outcome(row):
    return {'id': safe_count(row['id']), 'code': safe_text(row['code'], 12), 'statement': safe_text(row['statement'], 300)}


def _public_page(cursor, subject_id):
    loaded = assessment.page(cursor, subject_id)
    if loaded is None:
        return None
    return {
        'subjects': [
            {'id': safe_count(row['id']), 'name': safe_text(row['name'], 140), 'course_id': safe_count(row.get('course_id')) or None}
            for row in loaded['subjects'] if safe_count(row.get('id'))
        ],
        'subject': None if loaded['subject'] is None else {
            'id': safe_count(loaded['subject']['id']),
            'name': safe_text(loaded['subject']['name'], 100),
            'course_id': safe_count(loaded['subject']['course_id']) or None,
            'course_code': safe_text(loaded['subject']['course_code'], 20),
        },
        'components': [_component(row) for row in loaded['components']],
        'outcomes': [_outcome(row) for row in loaded['outcomes']],
        'program_outcomes': [_outcome(row) for row in loaded['program_outcomes']],
        'co_po': [
            {'co_code': safe_text(row['co_code'], 12), 'po_code': safe_text(row['po_code'], 12), 'level': safe_count(row['level'])}
            for row in loaded['co_po']
        ],
        'attainment': loaded['attainment'],
        'kinds': list(assessment.KINDS),
        'permissions': {
            'change': _may_change_scheme(),
            'lock': allowed('assessments_lock') or allowed('subjects_change_subject'),
        },
    }


def _marks_payload(cursor, component):
    return {
        'component': {
            'id': safe_count(component['id']),
            'name': safe_text(component['name'], 80),
            'max_marks': _num(component['max_marks']),
            'kind': component['kind'] if component['kind'] in assessment.KINDS else 'IA',
            'locked': bool(component['locked']),
        },
        'students': [
            {
                'student_id': safe_count(row['student_id']),
                'name': safe_text(row['name'], 100),
                'roll_number': safe_text(row['roll_number'], 50),
                'marks': None if row['marks'] is None else _num(row['marks']),
            }
            for row in assessment.marks_grid(cursor, component)
        ],
        'can_change': _may_enter(cursor, component) and not component['locked'],
        'can_lock': allowed('assessments_lock') or allowed('subjects_change_subject'),
    }


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
    if isinstance(exc, assessment.AssessmentError):
        return _rejected(exc)
    if isinstance(exc, InputError):
        return reject_input(_MESSAGES, exc.code)
    current_app.logger.exception('Assessment request failed')
    return json_error(_MESSAGES['assessment_unavailable'], 500, 'assessment_unavailable')


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
        subject_id = optional_id(request_subject(), 'assessment_invalid')
        if subject_id is None:
            choices = assessment.subject_choices(cursor)
            if choices:
                subject_id = int(choices[0]['id'])
        loaded = _public_page(cursor, subject_id)
        if subject_id and loaded is None:
            return json_error(_MESSAGES['subject_not_found'], 404, 'subject_not_found')
        return json_ok(loaded)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Assessment page failed')
        return json_error(_MESSAGES['assessment_unavailable'], 500, 'assessment_unavailable')
    finally:
        close(cursor, connection)


def request_subject():
    from flask import request
    return request.args.get('subject_id')


def _save_outcomes(subject_id):
    return _write_subject(subject_id, _OUTCOME_FIELDS, lambda cursor, payload: assessment.replace_outcomes(cursor, subject_id, payload.get('outcomes')))


def _save_components(subject_id):
    return _write_subject(subject_id, _COMPONENT_FIELDS, lambda cursor, payload: assessment.replace_components(cursor, subject_id, payload.get('components')))


def _save_map(subject_id):
    def work(cursor, payload):
        subject = assessment.subject_in_scope(cursor, subject_id)
        if subject is None:
            raise assessment.AssessmentError('subject_not_found')
        assessment.replace_map(cursor, subject_id, subject['course_id'], payload.get('links'))
    return _write_subject(subject_id, _MAP_FIELDS, work)


def _write_subject(subject_id, fields, work):
    denied = _change_denied()
    if denied:
        return denied
    off = _off()
    if off:
        return off
    connection = cursor = None
    try:
        payload = body(fields)
        connection, cursor, missing = _open()
        if missing:
            return missing
        if assessment.subject_in_scope(cursor, subject_id) is None:
            return json_error(_MESSAGES['subject_not_found'], 404, 'subject_not_found')
        work(cursor, payload)
        log_activity(
            session.get('user_id'), 'assessment_saved', f'Assessment scheme saved for subject {subject_id}',
            entity_type='subject', entity_id=subject_id, cursor=cursor,
        )
        connection.commit()
        return json_ok(_public_page(cursor, subject_id))
    except (assessment.AssessmentError, InputError) as exc:
        return _fail(connection, exc)
    except Exception as exc:
        return _fail(connection, exc)
    finally:
        close(cursor, connection)


def _save_program(course_id):
    denied = _change_denied()
    if denied:
        return denied
    off = _off()
    if off:
        return off
    connection = cursor = None
    try:
        payload = body(_OUTCOME_FIELDS)
        connection, cursor, missing = _open()
        if missing:
            return missing
        if assessment.course_in_scope(cursor, course_id) is None:
            return json_error(_MESSAGES['subject_not_found'], 404, 'subject_not_found')
        assessment.replace_program_outcomes(cursor, course_id, payload.get('outcomes'))
        log_activity(
            session.get('user_id'), 'assessment_saved', f'Program outcomes saved for course {course_id}',
            entity_type='course', entity_id=course_id, cursor=cursor,
        )
        connection.commit()
        return json_ok({'program_outcomes': [_outcome(row) for row in assessment._program_outcomes(cursor, course_id)]})
    except (assessment.AssessmentError, InputError) as exc:
        return _fail(connection, exc)
    except Exception as exc:
        return _fail(connection, exc)
    finally:
        close(cursor, connection)


def _load_component(cursor, component_id):
    component = assessment.component_in_scope(cursor, component_id)
    if component is None:
        return None, json_error(_MESSAGES['component_not_found'], 404, 'component_not_found')
    return component, None


def _marks(component_id):
    off = _off()
    if off:
        return off
    connection = cursor = None
    try:
        connection, cursor, missing = _open()
        if missing:
            return missing
        component, missing = _load_component(cursor, component_id)
        if missing:
            return missing
        if not _may_read_marks(cursor, component):
            return permission_denied('assessments_view', 'assessment_unavailable', _MESSAGES['assessment_unavailable'])
        return json_ok(_marks_payload(cursor, component))
    except Exception:
        current_app.logger.exception('Assessment marks failed')
        return json_error(_MESSAGES['assessment_unavailable'], 500, 'assessment_unavailable')
    finally:
        close(cursor, connection)


def _save_marks(component_id):
    return _mark_write(component_id, _MARK_FIELDS, lambda cursor, component, payload: assessment.save_marks(
        cursor, component, payload.get('marks'), session.get('user_id'),
    ))


def _import(component_id):
    return _mark_write(component_id, _IMPORT_FIELDS, lambda cursor, component, payload: assessment.import_marks(
        cursor, component, _import_rows(payload), session.get('user_id'),
    ))


def _import_rows(payload):
    if isinstance(payload.get('rows'), list):
        rows = []
        for row in payload['rows']:
            if not isinstance(row, dict):
                raise assessment.AssessmentError('assessment_import_invalid')
            roll = str(row.get('roll_number') or '').strip()
            if not roll:
                raise assessment.AssessmentError('assessment_import_invalid')
            marks = row.get('marks')
            rows.append({'roll_number': roll, 'marks': '' if marks is None else str(marks).strip()})
        if not rows:
            raise assessment.AssessmentError('assessment_import_invalid')
        return rows
    if isinstance(payload.get('csv'), str):
        return assessment.parse_import_csv(payload['csv'])
    encoded = payload.get('xlsx_base64')
    if isinstance(encoded, str) and encoded.strip():
        try:
            blob = base64.b64decode(encoded, validate=True)
        except Exception:
            raise assessment.AssessmentError('assessment_import_invalid')
        return assessment.parse_import_xlsx(blob)
    raise assessment.AssessmentError('assessment_import_invalid')


def _mark_write(component_id, fields, work):
    off = _off()
    if off:
        return off
    connection = cursor = None
    try:
        payload = body(fields)
        connection, cursor, missing = _open()
        if missing:
            return missing
        component, missing = _load_component(cursor, component_id)
        if missing:
            return missing
        if not _may_enter(cursor, component):
            return permission_denied('assessments_change', 'assessment_unavailable', _MESSAGES['assessment_unavailable'])
        result = work(cursor, component, payload)
        log_activity(
            session.get('user_id'), 'assessment_marks_saved', f'Marks saved for component {component_id}',
            entity_type='assessment_component', entity_id=component_id, cursor=cursor,
        )
        connection.commit()
        fresh = assessment.component_in_scope(cursor, component_id)
        body_out = _marks_payload(cursor, fresh)
        if isinstance(result, dict):
            body_out['import'] = {'saved': result['saved'], 'unknown': [safe_text(roll, 50) for roll in result['unknown']]}
        return json_ok(body_out)
    except (assessment.AssessmentError, InputError) as exc:
        return _fail(connection, exc)
    except Exception as exc:
        return _fail(connection, exc)
    finally:
        close(cursor, connection)


def _lock(component_id, locked):
    denied = _lock_denied()
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
        component, missing = _load_component(cursor, component_id)
        if missing:
            return missing
        assessment.set_locked(cursor, component, locked, session.get('user_id'))
        log_activity(
            session.get('user_id'), 'assessment_locked' if locked else 'assessment_unlocked',
            f"{'Locked' if locked else 'Unlocked'} assessment component {component_id}",
            entity_type='assessment_component', entity_id=component_id, cursor=cursor,
        )
        connection.commit()
        fresh = assessment.component_in_scope(cursor, component_id)
        return json_ok(_marks_payload(cursor, fresh))
    except (assessment.AssessmentError, InputError) as exc:
        return _fail(connection, exc)
    except Exception as exc:
        return _fail(connection, exc)
    finally:
        close(cursor, connection)


def _student():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Student':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    off = _off()
    if off:
        return off
    connection = cursor = None
    try:
        connection, cursor, missing = _open()
        if missing:
            return missing
        subjects = []
        for row in assessment.student_results(cursor, session.get('user_id')):
            subjects.append({
                'subject_id': safe_count(row['subject_id']),
                'name': safe_text(row['name'], 100),
                'code': safe_text(row['code'], 20),
                'components': [
                    {
                        'name': safe_text(item['name'], 80),
                        'kind': item['kind'] if item['kind'] in assessment.KINDS else 'IA',
                        'max_marks': _num(item['max_marks']),
                        'marks': _num(item['marks']),
                    }
                    for item in row['components']
                ],
            })
        return json_ok({'subjects': subjects})
    except Exception:
        current_app.logger.exception('Student assessments failed')
        return json_error(_MESSAGES['assessment_unavailable'], 500, 'assessment_unavailable')
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
        subjects = []
        for row in assessment.allocated_subjects(cursor, session.get('user_id')):
            subjects.append({
                'id': safe_count(row['id']),
                'name': safe_text(row['name'], 140),
                'components': [_component(item) for item in assessment._components(cursor, row['id'])],
            })
        return json_ok({'subjects': subjects})
    except Exception:
        current_app.logger.exception('Teacher assessments failed')
        return json_error(_MESSAGES['assessment_unavailable'], 500, 'assessment_unavailable')
    finally:
        close(cursor, connection)
