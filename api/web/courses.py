"""Course API. Rules match the existing admin course screen."""

import re

from flask import current_app, request
from mysql.connector import IntegrityError

from extensions import get_db_connection
from core.db import transaction
from api.web.access import InputError, allowed, optional_text, permission_denied, required_text
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

PROGRAMS = ('UG', 'PG')
COURSE_FIELDS = frozenset((
    'name', 'code', 'program', 'department_id', 'duration_years',
    'total_semesters', 'description', 'is_active',
))
_CODE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 .&/_-]{0,19}$')

_ERROR_MESSAGES = {
    'invalid_body': 'The course could not be saved.',
    'course_name_invalid': 'Enter a course name up to 100 characters.',
    'course_code_invalid': 'Enter a course code up to 20 characters.',
    'course_program_invalid': 'Choose UG or PG.',
    'course_department_invalid': 'Choose a department.',
    'course_duration_invalid': 'Duration must be between 1 and 20 years.',
    'course_semesters_invalid': 'Total semesters must be between 1 and 40.',
    'description_invalid': 'Description must be 4000 characters or fewer.',
    'course_code_taken': 'A course with this code already exists.',
    'course_not_found': 'That course was not found.',
    'course_in_use': 'This course is used by students or timetable settings, so it cannot be deleted.',
    'courses_unavailable': 'The course list could not be loaded.',
}


class _CourseInputError(Exception):
    def __init__(self, code):
        self.code = code


def _permission_error(permission_name):
    return permission_denied(
        permission_name,
        'courses_unavailable',
        'The course list could not be loaded.',
        log_message='Course permission check failed',
    )


def _can(permission_name):
    return allowed(permission_name)


def _input_error(code):
    return json_error(_ERROR_MESSAGES.get(code, 'The course could not be saved.'), 400, code)


def _required_text(value, limit, code):
    try:
        return required_text(value, limit, code)
    except InputError as exc:
        raise _CourseInputError(exc.code) from None


def _optional_text(value, limit, code):
    try:
        return optional_text(value, limit, code)
    except InputError as exc:
        raise _CourseInputError(exc.code) from None


def _code(value):
    if value is None or value == '':
        return None
    text = _required_text(value, 20, 'course_code_invalid')
    if not _CODE.match(text):
        raise _CourseInputError('course_code_invalid')
    return text


def _program(value):
    if value not in PROGRAMS:
        raise _CourseInputError('course_program_invalid')
    return value


def _whole_number(value, limit, code):
    number = safe_count(value)
    if isinstance(value, bool) or number < 1 or number > limit or safe_text(value, 6) != str(number):
        raise _CourseInputError(code)
    return number


def _active(value):
    if not isinstance(value, bool):
        raise _CourseInputError('invalid_body')
    return value


def _payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - COURSE_FIELDS:
        return _input_error('invalid_body')
    return payload


def _public_course(row):
    program = row.get('program') if row.get('program') in PROGRAMS else ''
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 100),
        'code': safe_text(row.get('code'), 20),
        'program': program,
        'department_id': safe_count(row.get('department_id')),
        'department_name': safe_text(row.get('department_name'), 100),
        'duration_years': safe_count(row.get('duration_years')),
        'total_semesters': safe_count(row.get('total_semesters')),
        'description': safe_text(row.get('description'), 4000),
        'is_active': bool(row.get('is_active')),
        'subject_count': safe_count(row.get('subject_count')),
        'batch_count': safe_count(row.get('batch_count')),
    }


def _close(cursor, connection):
    if cursor is not None:
        cursor.close()
    if connection is not None:
        connection.close()


def _department_id(cursor, value):
    department_id = safe_count(value)
    if isinstance(value, bool) or department_id < 1 or safe_text(value, 12) != str(department_id):
        raise _CourseInputError('course_department_invalid')
    cursor.execute('SELECT 1 FROM departments WHERE id = %s', (department_id,))
    if cursor.fetchone() is None:
        raise _CourseInputError('course_department_invalid')
    return department_id


def _reject_code_conflict(cursor, code, course_id):
    if not code:
        return
    cursor.execute('SELECT id FROM courses WHERE code = %s', (code,))
    row = cursor.fetchone()
    if row is not None and row.get('id') != course_id:
        raise _CourseInputError('course_code_taken')


def _save(payload, course_id):
    connection = None
    cursor = None
    try:
        name = _required_text(payload.get('name'), 100, 'course_name_invalid')
        code = _code(payload.get('code'))
        program = _program(payload.get('program'))
        duration_years = _whole_number(payload.get('duration_years'), 20, 'course_duration_invalid')
        total_semesters = _whole_number(payload.get('total_semesters'), 40, 'course_semesters_invalid')
        description = _optional_text(payload.get('description', ''), 4000, 'description_invalid')
        is_active = _active(payload.get('is_active'))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        department_id = _department_id(cursor, payload.get('department_id'))
        if course_id is not None:
            cursor.execute('SELECT 1 FROM courses WHERE id = %s', (course_id,))
            if cursor.fetchone() is None:
                return _input_error('course_not_found')
        _reject_code_conflict(cursor, code, course_id)
        values = (name, code, program, department_id, duration_years, total_semesters, description, 1 if is_active else 0)
        if course_id is None:
            cursor.execute(
                """
                INSERT INTO courses
                    (name, code, program, department_id, duration_years, total_semesters, description, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                values,
            )
            saved_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE courses
                SET name = %s, code = %s, program = %s, department_id = %s,
                    duration_years = %s, total_semesters = %s, description = %s, is_active = %s
                WHERE id = %s
                """,
                (*values, course_id),
            )
            saved_id = course_id
        with transaction(connection):
            pass
        return _read(saved_id)
    except _CourseInputError as exc:
        if connection is not None:
            connection.rollback()
        return _input_error(exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Course save conflict')
        return _input_error('course_code_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Course save failed')
        return json_error('The course could not be saved.', 500, 'courses_unavailable')
    finally:
        _close(cursor, connection)


_LIST_SQL = """
    SELECT c.id, c.name, c.code, c.program, c.department_id, c.duration_years,
           c.total_semesters, c.description, c.is_active, d.name AS department_name,
           COUNT(DISTINCT s.id) AS subject_count,
           COUNT(DISTINCT cb.id) AS batch_count
    FROM courses c
    JOIN departments d ON c.department_id = d.id
    LEFT JOIN subjects s ON c.id = s.course_id
    LEFT JOIN course_batches cb ON c.id = cb.course_id
"""


def _read(course_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(_LIST_SQL + ' WHERE c.id = %s GROUP BY c.id', (course_id,))
        row = cursor.fetchone()
        if row is None or not safe_count(row.get('id')):
            return _input_error('course_not_found')
        return json_ok(_public_course(row))
    except Exception:
        current_app.logger.exception('Course lookup failed')
        return json_error('The course could not be loaded.', 500, 'courses_unavailable')
    finally:
        _close(cursor, connection)


def register_course_routes(blueprint):
    @blueprint.route('/courses', methods=['GET'])
    def list_courses():
        denied = _permission_error('courses_view_course')
        if denied is not None:
            return denied

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT id, name FROM departments WHERE is_active = TRUE ORDER BY name')
            departments = []
            for row in cursor.fetchall():
                name = safe_text(row.get('name'), 100)
                department_id = safe_count(row.get('id'))
                if department_id and name:
                    departments.append({'id': department_id, 'name': name})
            cursor.execute(_LIST_SQL + ' GROUP BY c.id ORDER BY c.program, c.name')
            courses = [_public_course(row) for row in cursor.fetchall() if safe_count(row.get('id'))]
            return json_ok({
                'courses': courses,
                'departments': departments,
                'permissions': {
                    'add': _can('courses_add_course'),
                    'change': _can('courses_change_course'),
                    'delete': _can('courses_delete_course'),
                },
            })
        except Exception:
            current_app.logger.exception('Course list failed')
            return json_error('The course list could not be loaded.', 500, 'courses_unavailable')
        finally:
            _close(cursor, connection)

    @blueprint.route('/courses/<int:course_id>', methods=['GET'])
    def get_course(course_id):
        denied = _permission_error('courses_view_course')
        if denied is not None:
            return denied
        return _read(course_id)

    @blueprint.route('/courses', methods=['POST'])
    def create_course():
        denied = _permission_error('courses_add_course')
        if denied is not None:
            return denied
        payload = _payload()
        if isinstance(payload, tuple):
            return payload
        return _save(payload, None)

    @blueprint.route('/courses/<int:course_id>', methods=['PUT'])
    def update_course(course_id):
        denied = _permission_error('courses_change_course')
        if denied is not None:
            return denied
        payload = _payload()
        if isinstance(payload, tuple):
            return payload
        return _save(payload, course_id)

    @blueprint.route('/courses/<int:course_id>', methods=['DELETE'])
    def delete_course(course_id):
        denied = _permission_error('courses_delete_course')
        if denied is not None:
            return denied

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute('SELECT 1 FROM courses WHERE id = %s', (course_id,))
            if cursor.fetchone() is None:
                return _input_error('course_not_found')
            for table in (
                'students',
                'timetable_generation_settings',
                'timetable_quality_runs',
                'timetable_session_targets',
            ):
                cursor.execute(f'SELECT 1 FROM {table} WHERE course_id = %s LIMIT 1', (course_id,))
                if cursor.fetchone() is not None:
                    return _input_error('course_in_use')
            cursor.execute('DELETE FROM courses WHERE id = %s', (course_id,))
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except IntegrityError:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Course delete blocked')
            return _input_error('course_in_use')
        except Exception:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Course delete failed')
            return json_error('The course could not be deleted.', 500, 'courses_unavailable')
        finally:
            _close(cursor, connection)
