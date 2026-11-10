"""The operations of /api/v1. Each one is declared with `operation(...)` so the OpenAPI document matches the routes."""

from datetime import date

from flask import current_app, g, jsonify, request

from api.v1 import public_api_bp
from api.v1.registry import PARAMS, openapi_document, operation
from api.web.responses import json_error
from api.web.security import safe_clock, safe_count, safe_stamp, safe_text
from data_access import public_api as rows
from extensions import get_db_connection
from services.api_keys import SCOPES
from services.attendance_calc import defaulters as find_defaulters
from services.attendance_calc import parse_threshold, percent_value, student_report

_DAYS = frozenset(PARAMS['day']['schema']['enum'])
_STATUSES = frozenset(PARAMS['status']['schema']['enum'])
_MAX_LIMIT = 500


class BadParameter(ValueError):
    pass


def _ok(data, page=None):
    body = {'success': True, 'data': data}
    if page is not None:
        body['page'] = page
    return jsonify(body), 200


def _int_arg(name, *, lower=1, upper=1000000, default=None):
    raw = request.args.get(name)
    if raw in (None, ''):
        return default
    if not str(raw).isdigit() or not lower <= int(raw) <= upper:
        raise BadParameter(name)
    return int(raw)


def _date_arg(name):
    raw = request.args.get(name)
    if raw in (None, ''):
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise BadParameter(name) from exc


def _choice_arg(name, choices):
    raw = request.args.get(name)
    if raw in (None, ''):
        return None
    if raw not in choices:
        raise BadParameter(name)
    return raw


def _paging():
    return _int_arg('limit', lower=1, upper=_MAX_LIMIT, default=100), _int_arg('offset', lower=0, upper=10**9, default=0)


def _page(limit, offset, items, has_more):
    return {'limit': limit, 'offset': offset, 'count': len(items), 'has_more': has_more}


def _date(value):
    return value.isoformat() if hasattr(value, 'isoformat') else None


def _with_cursor(handler):
    """Run `handler(cursor)` and turn bad parameters and failures into API errors."""
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        return handler(cursor)
    except BadParameter as exc:
        return json_error(f'The "{exc}" parameter is not valid.', 400, 'invalid_parameter')
    except Exception:
        current_app.logger.exception('Public API request failed')
        return json_error('The request could not be completed.', 500, 'unavailable')
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# Document and key ---------------------------------------------------------

@public_api_bp.route('/openapi.json', methods=['GET'])
def openapi():
    server = request.url_root.rstrip('/') + '/api/v1'
    return jsonify(openapi_document(server, SCOPES)), 200


@public_api_bp.route('', methods=['GET'], strict_slashes=False)
def index():
    return _ok({'name': 'Timetable Management public API', 'version': 'v1', 'openapi': request.url_root.rstrip('/') + '/api/v1/openapi.json'})


@public_api_bp.route('/me', methods=['GET'])
@operation('/me', scope=None, summary='The key making the call', tag='General',
           description='Name, scopes and expiry of the key in the Authorization header. Works with any valid key.',
           response={'type': 'object', 'properties': {'name': {'type': 'string'}, 'scopes': {'type': 'array', 'items': {'type': 'string'}}, 'expires_at': {'type': ['string', 'null'], 'format': 'date-time'}}})
def me():
    key = g.api_key
    return _ok({'name': safe_text(key.get('name'), 100), 'scopes': list(key.get('scopes', ())), 'expires_at': safe_stamp(key.get('expires_at')) or None})


# Catalog --------------------------------------------------------------------

_ITEM = {'type': 'object', 'properties': {'id': {'type': 'integer'}, 'name': {'type': 'string'}}}


@public_api_bp.route('/departments', methods=['GET'])
@operation('/departments', scope='catalog:read', summary='Departments', tag='Catalog', params=('limit', 'offset'), paginated=True,
           response={'type': 'array', 'items': _ITEM})
def departments():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_departments(cursor, limit, offset)
        return _ok([
            {'id': safe_count(r['id']), 'name': safe_text(r['name'], 100), 'code': safe_text(r.get('code') or '', 20), 'is_active': bool(r['is_active'])}
            for r in items
        ], _page(limit, offset, items, more))
    return _with_cursor(handle)


@public_api_bp.route('/courses', methods=['GET'])
@operation('/courses', scope='catalog:read', summary='Courses (programmes)', tag='Catalog', params=('limit', 'offset'), paginated=True,
           response={'type': 'array', 'items': _ITEM})
def courses():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_courses(cursor, limit, offset)
        return _ok([
            {
                'id': safe_count(r['id']), 'name': safe_text(r['name'], 100), 'code': safe_text(r.get('code') or '', 20),
                'program': safe_text(r.get('program') or '', 10), 'duration_years': safe_count(r.get('duration_years')),
                'total_semesters': safe_count(r.get('total_semesters')), 'department_id': safe_count(r.get('department_id')),
                'department_name': safe_text(r.get('department_name'), 100), 'is_active': bool(r['is_active']),
            }
            for r in items
        ], _page(limit, offset, items, more))
    return _with_cursor(handle)


@public_api_bp.route('/classes', methods=['GET'])
@operation('/classes', scope='catalog:read', summary='Classes (years of study)', tag='Catalog', response={'type': 'array', 'items': _ITEM})
def classes():
    return _with_cursor(lambda cursor: _ok([
        {'id': safe_count(r['id']), 'name': safe_text(r['name'], 50), 'display_order': safe_count(r.get('display_order'))}
        for r in rows.fetch_classes(cursor)
    ]))


@public_api_bp.route('/divisions', methods=['GET'])
@operation('/divisions', scope='catalog:read', summary='Divisions', tag='Catalog', response={'type': 'array', 'items': _ITEM})
def divisions():
    return _with_cursor(lambda cursor: _ok([
        {'id': safe_count(r['id']), 'name': safe_text(r['name'], 10), 'capacity': safe_count(r.get('capacity'))}
        for r in rows.fetch_divisions(cursor)
    ]))


@public_api_bp.route('/academic-years', methods=['GET'])
@operation('/academic-years', scope='catalog:read', summary='Academic years', tag='Catalog', response={'type': 'array', 'items': _ITEM})
def academic_years():
    return _with_cursor(lambda cursor: _ok([
        {
            'id': safe_count(r['id']), 'name': safe_text(r['name'], 20), 'start_date': _date(r.get('start_date')),
            'end_date': _date(r.get('end_date')), 'is_current': bool(r.get('is_current')),
        }
        for r in rows.fetch_academic_years(cursor)
    ]))


@public_api_bp.route('/rooms', methods=['GET'])
@operation('/rooms', scope='catalog:read', summary='Rooms and labs', tag='Catalog', params=('limit', 'offset'), paginated=True,
           response={'type': 'array', 'items': _ITEM})
def rooms():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_rooms(cursor, limit, offset)
        return _ok([
            {
                'id': safe_count(r['id']), 'room_number': safe_text(r['room_number'], 20), 'room_type': safe_text(r.get('room_type') or '', 30),
                'capacity': safe_count(r.get('capacity')), 'building': safe_text(r.get('building') or '', 50),
                'floor': safe_count(r.get('floor')) if r.get('floor') is not None else None,
                'department_id': safe_count(r.get('department_id')) or None, 'is_available': bool(r['is_available']),
            }
            for r in items
        ], _page(limit, offset, items, more))
    return _with_cursor(handle)


@public_api_bp.route('/subjects', methods=['GET'])
@operation('/subjects', scope='catalog:read', summary='Subjects', tag='Catalog', params=('course_id', 'class_id', 'limit', 'offset'), paginated=True,
           response={'type': 'array', 'items': _ITEM})
def subjects():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_subjects(cursor, course_id=_int_arg('course_id'), class_id=_int_arg('class_id'), limit=limit, offset=offset)
        return _ok([
            {
                'id': safe_count(r['id']), 'name': safe_text(r['name'], 100), 'code': safe_text(r.get('code') or '', 20),
                'course_id': safe_count(r.get('course_id')), 'class_id': safe_count(r.get('class_id')) or None,
                'semester_id': safe_count(r.get('semester_id')) or None, 'course_type': safe_text(r.get('course_type') or '', 30),
                'kind': safe_text(r.get('theory_practical') or '', 10), 'credits': float(r['credits']) if r.get('credits') is not None else None,
                'lectures_per_week': safe_count(r.get('lectures_per_week')), 'practical_hours_per_week': safe_count(r.get('practical_hours_per_week')),
                'is_elective': bool(r.get('is_elective')),
            }
            for r in items
        ], _page(limit, offset, items, more))
    return _with_cursor(handle)


@public_api_bp.route('/subjects/<int:subject_id>/coverage', methods=['GET'])
@operation(
    '/subjects/<int:subject_id>/coverage', scope='catalog:read', summary='Syllabus coverage of one subject', tag='Catalog',
    params=('subject_id_path',),
    description='Planned hours, delivered hours and pace for each unit. 404 while capability `syllabus` is off.',
    response={'type': 'object'},
)
def subject_coverage(subject_id):
    from core import capabilities
    from services import syllabus

    off = capabilities.require_capability('syllabus')
    if off:
        return off

    def handle(cursor):
        if not syllabus.tables_ready(cursor):
            return json_error('The syllabus tables are missing; apply the database migrations first.', 409, 'syllabus_unavailable')
        report = syllabus.coverage_for(cursor, subject_id, scoped=False)
        if report is None:
            return json_error('No such subject.', 404, 'subject_not_found')
        return _ok({
            'subject_id': safe_count(report['subject_id']),
            'name': safe_text(report['subject_name'], 100),
            'code': safe_text(report['course_code'], 20),
            'elapsed_weeks': report['elapsed_weeks'],
            'total_weeks': report['total_weeks'],
            'units': [
                {
                    'unit_no': safe_count(row['unit_no']),
                    'title': safe_text(row['title'], 120),
                    'planned_hours': float(row['planned_hours']),
                    'delivered_hours': float(row['delivered_hours']),
                    'percent': None if row['percent'] is None else float(row['percent']),
                    'expected_hours': None if row['expected_hours'] is None else float(row['expected_hours']),
                    'pace': row['pace'],
                }
                for row in report['units']
            ],
        })
    return _with_cursor(handle)


@public_api_bp.route('/subjects/<int:subject_id>/internals', methods=['GET'])
@operation(
    '/subjects/<int:subject_id>/internals', scope='catalog:read', summary='Locked internal marks of one subject', tag='Catalog',
    params=('subject_id_path',),
    description='Components that have been locked, with each student mark. 404 while capability `assessments` is off. Unlocked marks are omitted.',
    response={'type': 'object'},
)
def subject_internals(subject_id):
    from core import capabilities
    from services import assessment

    off = capabilities.require_capability('assessments')
    if off:
        return off

    def handle(cursor):
        if not assessment.tables_ready(cursor):
            return json_error('The assessment tables are missing; apply the database migrations first.', 409, 'assessment_unavailable')
        report = assessment.locked_internals(cursor, subject_id)
        if report is None:
            return json_error('No such subject.', 404, 'subject_not_found')
        return _ok({
            'subject_id': safe_count(report['subject_id']),
            'name': safe_text(report['name'], 100),
            'code': safe_text(report['code'], 20),
            'components': [
                {
                    'name': safe_text(row['name'], 80),
                    'kind': safe_text(row['kind'], 20),
                    'max_marks': float(row['max_marks']),
                    'marks': [
                        {'roll_number': safe_text(mark['roll_number'], 50), 'marks': float(mark['marks'])}
                        for mark in row['marks']
                    ],
                }
                for row in report['components']
            ],
        })
    return _with_cursor(handle)


@public_api_bp.route('/lab-batches', methods=['GET'])
@operation('/lab-batches', scope='catalog:read', summary='Lab batches (active)', tag='Catalog',
           params=('course_id', 'class_id', 'division_id', 'limit', 'offset'), paginated=True, response={'type': 'array', 'items': _ITEM})
def lab_batches():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_lab_batches(
            cursor, course_id=_int_arg('course_id'), class_id=_int_arg('class_id'), division_id=_int_arg('division_id'), limit=limit, offset=offset,
        )
        return _ok([
            {
                'id': safe_count(r['id']), 'name': safe_text(r['name'], 20), 'course_id': safe_count(r['course_id']), 'class_id': safe_count(r['class_id']),
                'division_id': safe_count(r.get('division_id')) or None, 'academic_year_id': safe_count(r.get('academic_year_id')),
                'semester_id': safe_count(r.get('semester_id')) or None, 'capacity': safe_count(r.get('capacity')) or None,
                'member_count': safe_count(r.get('member_count')),
            }
            for r in items
        ], _page(limit, offset, items, more))
    return _with_cursor(handle)


# Timetable ------------------------------------------------------------------

_SLOT = {
    'type': 'object',
    'properties': {
        'id': {'type': 'integer'}, 'day': {'type': 'string'}, 'start_time': {'type': 'string'}, 'end_time': {'type': 'string'},
        'subject': _ITEM, 'faculty': {'oneOf': [_ITEM, {'type': 'null'}]}, 'room': {'type': ['string', 'null']},
        'lab_batch': {'oneOf': [_ITEM, {'type': 'null'}]},
    },
}


def _slot(r):
    return {
        'id': safe_count(r['id']), 'course_id': safe_count(r['course_id']), 'class_id': safe_count(r['class_id']),
        'division_id': safe_count(r.get('division_id')) or None, 'day': safe_text(r['day_of_week'], 10),
        'start_time': safe_clock(r.get('start_time')), 'end_time': safe_clock(r.get('end_time')),
        'subject': {'id': safe_count(r['subject_id']), 'name': safe_text(r['subject_name'], 100), 'kind': safe_text(r.get('theory_practical') or '', 10)},
        'faculty': {'id': safe_count(r['faculty_id']), 'name': safe_text(r['faculty_name'], 100)} if r.get('faculty_id') else None,
        'room': safe_text(r.get('room_number') or '', 20) or None,
        'lab_batch': {'id': safe_count(r['lab_batch_group_id']), 'name': safe_text(r.get('lab_batch_name'), 20)} if r.get('lab_batch_group_id') else None,
        'academic_year_id': safe_count(r.get('academic_year_id')) or None, 'semester_id': safe_count(r.get('semester_id')) or None,
    }


@public_api_bp.route('/timetable', methods=['GET'])
@operation('/timetable', scope='timetable:read', summary='Active timetable slots', tag='Timetable',
           description='Every active slot, filterable by cohort and weekday. A slot with `lab_batch` is for that batch only; without it, the whole division.',
           params=('course_id', 'class_id', 'division_id', 'day', 'limit', 'offset'), paginated=True, response={'type': 'array', 'items': _SLOT})
def timetable():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_timetable(
            cursor, course_id=_int_arg('course_id'), class_id=_int_arg('class_id'), division_id=_int_arg('division_id'),
            day=_choice_arg('day', _DAYS), limit=limit, offset=offset,
        )
        return _ok([_slot(r) for r in items], _page(limit, offset, items, more))
    return _with_cursor(handle)


# People ---------------------------------------------------------------------

def _student(r):
    return {
        'id': safe_count(r['id']), 'name': safe_text(r['name'], 100), 'roll_number': safe_text(r.get('roll_number') or '', 50),
        'admission_id': safe_text(r.get('admission_id') or '', 20), 'course_id': safe_count(r.get('course_id')),
        'class_id': safe_count(r.get('class_id')) or None, 'division_id': safe_count(r.get('division_id')) or None,
        'admission_year': safe_count(r.get('admission_year')) or None,
    }


@public_api_bp.route('/students', methods=['GET'])
@operation('/students', scope='people:read', summary='Active students', tag='People',
           description='Names, roll numbers and cohort. No contact details or credentials.',
           params=('course_id', 'class_id', 'division_id', 'limit', 'offset'), paginated=True, response={'type': 'array', 'items': _ITEM})
def students():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_students(
            cursor, course_id=_int_arg('course_id'), class_id=_int_arg('class_id'), division_id=_int_arg('division_id'), limit=limit, offset=offset,
        )
        return _ok([_student(r) for r in items], _page(limit, offset, items, more))
    return _with_cursor(handle)


@public_api_bp.route('/faculty', methods=['GET'])
@operation('/faculty', scope='people:read', summary='Active faculty', tag='People', params=('department_id', 'limit', 'offset'), paginated=True,
           response={'type': 'array', 'items': _ITEM})
def faculty():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_faculty(cursor, department_id=_int_arg('department_id'), limit=limit, offset=offset)
        return _ok([
            {
                'id': safe_count(r['id']), 'name': safe_text(r['name'], 100), 'employee_id': safe_text(r.get('employee_id') or '', 20),
                'designation': safe_text(r.get('designation') or '', 50), 'department_id': safe_count(r.get('department_id')),
                'department_name': safe_text(r.get('department_name'), 100),
            }
            for r in items
        ], _page(limit, offset, items, more))
    return _with_cursor(handle)


# Attendance -----------------------------------------------------------------

def _session(r):
    return {
        'id': safe_count(r['id']), 'timetable_id': safe_count(r['timetable_id']), 'date': _date(r.get('session_date')),
        'status': safe_text(r['status'], 20), 'cancel_reason': safe_text(r.get('cancel_reason') or '', 30) or None,
        'marked_at': safe_stamp(r.get('marked_at')) or None, 'source': safe_text(r.get('source') or '', 20),
        'course_id': safe_count(r['course_id']), 'class_id': safe_count(r['class_id']), 'division_id': safe_count(r.get('division_id')) or None,
        'subject': {'id': safe_count(r['subject_id']), 'name': safe_text(r['subject_name'], 100)},
        'day': safe_text(r.get('day_of_week'), 10), 'start_time': safe_clock(r.get('start_time')), 'end_time': safe_clock(r.get('end_time')),
        'faculty': {'id': safe_count(r['faculty_id']), 'name': safe_text(r['faculty_name'], 100)} if r.get('faculty_id') else None,
        'lab_batch': {'id': safe_count(r['lab_batch_group_id']), 'name': safe_text(r.get('lab_batch_name'), 20)} if r.get('lab_batch_group_id') else None,
        'marks': safe_count(r.get('marks')),
    }


@public_api_bp.route('/attendance/sessions', methods=['GET'])
@operation('/attendance/sessions', scope='attendance:read', summary='Lecture sessions', tag='Attendance',
           description='One row per lecture occurrence: held, cancelled, or not marked. `marks` is the number of attendance rows on it.',
           params=('from', 'to', 'status', 'course_id', 'class_id', 'division_id', 'subject_id', 'limit', 'offset'), paginated=True,
           response={'type': 'array', 'items': {'type': 'object'}})
def sessions():
    def handle(cursor):
        limit, offset = _paging()
        items, more = rows.fetch_sessions(
            cursor, date_from=_date_arg('from'), date_to=_date_arg('to'), status=_choice_arg('status', _STATUSES),
            course_id=_int_arg('course_id'), class_id=_int_arg('class_id'), division_id=_int_arg('division_id'),
            subject_id=_int_arg('subject_id'), limit=limit, offset=offset,
        )
        return _ok([_session(r) for r in items], _page(limit, offset, items, more))
    return _with_cursor(handle)


@public_api_bp.route('/attendance/sessions/<int:session_id>/marks', methods=['GET'])
@operation('/attendance/sessions/<int:session_id>/marks', scope='attendance:read', summary='Marks of one session', tag='Attendance',
           params=('session_id',), response={'type': 'object'})
def session_marks(session_id):
    def handle(cursor):
        found = rows.fetch_session(cursor, session_id)
        if not found:
            return json_error('No such session.', 404, 'not_found')
        marks = [
            {
                'student_id': safe_count(m['student_id']), 'roll_number': safe_text(m.get('roll_number') or '', 50),
                'name': safe_text(m['name'], 100), 'status': safe_text(m['status'], 10), 'marked_at': safe_stamp(m.get('marked_at')) or None,
            }
            for m in rows.fetch_session_marks(cursor, session_id)
        ]
        return _ok({'session': _session({**found, 'marks': len(marks)}), 'marks': marks})
    return _with_cursor(handle)


def _figures(figures):
    return {
        'held': safe_count(figures.held), 'countable': safe_count(figures.countable), 'present': safe_count(figures.present),
        'late': safe_count(figures.late), 'absent': safe_count(figures.absent), 'excused': safe_count(figures.excused),
        'not_marked': safe_count(figures.not_marked), 'attended': safe_count(figures.attended), 'percentage': percent_value(figures.percentage),
    }


@public_api_bp.route('/attendance/students/<int:student_id>', methods=['GET'])
@operation('/attendance/students/<int:student_id>', scope='attendance:read', summary="One student's attendance", tag='Attendance',
           description='Overall and per-subject figures by the institution\'s rules (roster-aware; lab batches and electives respected). '
                       'Optional `from`/`to` limit the sessions counted.',
           params=('student_id', 'from', 'to'), response={'type': 'object'})
def student_attendance(student_id):
    def handle(cursor):
        found = rows.fetch_student(cursor, student_id)
        if not found:
            return json_error('No such student.', 404, 'not_found')
        report = student_report(cursor, student_id, date_from=_date_arg('from'), date_to=_date_arg('to'))
        if report is None:
            return json_error('No such student.', 404, 'not_found')
        subjects = []
        for subject_id, entry in report.summary.subjects.items():
            subjects.append({'id': safe_count(subject_id), 'name': safe_text(report.subject_name(subject_id), 100), **_figures(entry.figures)})
        subjects.sort(key=lambda item: (item['name'], item['id']))
        return _ok({
            'student': _student(found),
            'threshold': percent_value(report.summary.policy.threshold),
            'overall': _figures(report.overall),
            'classes_needed': None if report.summary.classes_needed is None else safe_count(report.summary.classes_needed),
            'subjects': subjects,
        })
    return _with_cursor(handle)


@public_api_bp.route('/attendance/defaulters', methods=['GET'])
@operation('/attendance/defaulters', scope='attendance:read', summary='Students below the attendance threshold', tag='Attendance',
           description='Active students whose overall percentage is below `threshold` (default: the institution setting), lowest first. '
                       'Students with nothing countable yet are not listed.',
           params=('threshold', 'course_id', 'class_id', 'division_id', 'limit', 'offset'), paginated=True,
           response={'type': 'array', 'items': {'type': 'object'}})
def defaulters():
    def handle(cursor):
        limit, offset = _paging()
        raw = request.args.get('threshold')
        threshold = None
        if raw not in (None, ''):
            threshold = parse_threshold(raw)
            if threshold is None:
                raise BadParameter('threshold')
        below, chosen = find_defaulters(
            cursor, threshold=threshold, course_id=_int_arg('course_id'), class_id=_int_arg('class_id'), division_id=_int_arg('division_id'),
        )
        window = below[offset:offset + limit]
        items = [
            {
                'student': _student(report.student), 'overall': _figures(report.overall),
                'classes_needed': None if report.summary.classes_needed is None else safe_count(report.summary.classes_needed),
            }
            for report in window
        ]
        return _ok({'threshold': percent_value(chosen.threshold), 'students': items}, _page(limit, offset, window, offset + limit < len(below)))
    return _with_cursor(handle)
