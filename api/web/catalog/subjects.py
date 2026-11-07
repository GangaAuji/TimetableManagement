"""Subject API. Rules match the existing admin subject screen."""

from flask import current_app
from mysql.connector import IntegrityError

from extensions import get_db_connection
from core.db import transaction
from api.web.access import (
    InputError,
    allowed,
    as_number,
    body,
    close,
    decimal_number,
    flag,
    optional_id,
    optional_text,
    permission_denied,
    reject_input,
    required_text,
    whole_number,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

COURSE_TYPES = ('Core', 'Elective', 'Core Practical', 'Project')
MODES = ('Theory', 'Practical', 'Both')
FIELDS = frozenset((
    'name', 'course_code', 'course_id', 'class_id', 'semester_id', 'course_type',
    'theory_practical', 'credits', 'theory_credits', 'practical_credits', 'marks',
    'theory_marks', 'practical_marks', 'lectures_per_week', 'practical_hours_per_week',
    'is_elective', 'description', 'syllabus_url',
))
MESSAGES = {
    'invalid_body': 'The subject could not be saved.',
    'subject_name_invalid': 'Enter a subject name up to 150 characters.',
    'subject_code_invalid': 'Enter a subject code up to 20 characters.',
    'subject_course_invalid': 'Choose a course.',
    'subject_class_invalid': 'Choose a valid class, or leave it empty.',
    'subject_semester_invalid': 'Choose a semester that belongs to this course.',
    'subject_type_invalid': 'Choose a valid subject type.',
    'subject_mode_invalid': 'Choose Theory, Practical, or Both.',
    'subject_credits_invalid': 'Credits and marks must be zero or greater.',
    'subject_url_invalid': 'Syllabus link must be an http or https address.',
    'subject_not_found': 'That subject was not found.',
    'subject_in_use': 'This subject is in use, so it cannot be deleted.',
    'subjects_unavailable': 'The subject list could not be loaded.',
}


def _url(value):
    text = optional_text(value, 500, 'subject_url_invalid')
    lowered = text.lower()
    if not text:
        return ''
    if lowered.startswith(('javascript:', 'data:')) or ' ' in text:
        raise InputError('subject_url_invalid')
    if not lowered.startswith(('http://', 'https://')):
        raise InputError('subject_url_invalid')
    return text


def _public(row):
    mode = row.get('theory_practical') if row.get('theory_practical') in MODES else ''
    course_type = row.get('course_type') if row.get('course_type') in COURSE_TYPES else ''
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 150),
        'course_code': safe_text(row.get('course_code'), 20),
        'course_id': safe_count(row.get('course_id')),
        'course_name': safe_text(row.get('course_name'), 100),
        'program': safe_text(row.get('program'), 20),
        'class_id': safe_count(row.get('class_id')) or None,
        'class_name': safe_text(row.get('class_name'), 100),
        'semester_id': safe_count(row.get('semester_id')) or None,
        'semester_name': safe_text(row.get('semester_name'), 100),
        'course_type': course_type,
        'theory_practical': mode,
        'credits': as_number(row.get('credits')),
        'theory_credits': as_number(row.get('theory_credits')),
        'practical_credits': as_number(row.get('practical_credits')),
        'marks': safe_count(row.get('marks')),
        'theory_marks': safe_count(row.get('theory_marks')),
        'practical_marks': safe_count(row.get('practical_marks')),
        'lectures_per_week': safe_count(row.get('lectures_per_week')),
        'practical_hours_per_week': safe_count(row.get('practical_hours_per_week')),
        'is_elective': bool(row.get('is_elective')),
        'description': safe_text(row.get('description'), 4000),
        'syllabus_url': safe_text(row.get('syllabus_url'), 500),
        'faculty_names': safe_text(row.get('faculty_names'), 500),
    }


def _normalize(payload):
    mode = payload.get('theory_practical')
    if mode not in MODES:
        raise InputError('subject_mode_invalid')
    theory_credits = decimal_number(payload.get('theory_credits', 0), 100, 'subject_credits_invalid')
    practical_credits = decimal_number(payload.get('practical_credits', 0), 100, 'subject_credits_invalid')
    theory_marks = whole_number(payload.get('theory_marks', 0), 1000, 'subject_credits_invalid')
    practical_marks = whole_number(payload.get('practical_marks', 0), 1000, 'subject_credits_invalid')
    if mode == 'Theory':
        practical_credits = 0.0
        practical_marks = 0
    elif mode == 'Practical':
        theory_credits = 0.0
        theory_marks = 0
    credits = round(theory_credits + practical_credits, 1)
    marks = theory_marks + practical_marks
    return mode, theory_credits, practical_credits, theory_marks, practical_marks, credits, marks


def _save(payload, subject_id):
    connection = None
    cursor = None
    try:
        name = required_text(payload.get('name'), 150, 'subject_name_invalid')
        course_code = required_text(payload.get('course_code'), 20, 'subject_code_invalid')
        course_id = whole_number(payload.get('course_id'), 1000000, 'subject_course_invalid', lower=1)
        class_id = optional_id(payload.get('class_id'), 'subject_class_invalid')
        semester_id = optional_id(payload.get('semester_id'), 'subject_semester_invalid')
        course_type = payload.get('course_type')
        if course_type not in COURSE_TYPES:
            raise InputError('subject_type_invalid')
        mode, theory_credits, practical_credits, theory_marks, practical_marks, credits, marks = _normalize(payload)
        lectures = whole_number(payload.get('lectures_per_week', 3), 40, 'subject_credits_invalid')
        practical_hours = whole_number(payload.get('practical_hours_per_week', 0), 40, 'subject_credits_invalid')
        is_elective = flag(payload.get('is_elective'))
        description = optional_text(payload.get('description', ''), 4000, 'invalid_body')
        syllabus_url = _url(payload.get('syllabus_url', ''))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT name, program, total_semesters FROM courses WHERE id = %s', (course_id,))
        course_row = cursor.fetchone()
        if course_row is None:
            raise InputError('subject_course_invalid')
        if class_id is not None:
            cursor.execute('SELECT 1 FROM classes WHERE id = %s', (class_id,))
            if cursor.fetchone() is None:
                raise InputError('subject_class_invalid')
        if semester_id is not None:
            cursor.execute('SELECT semester_number FROM semesters WHERE id = %s', (semester_id,))
            semester_row = cursor.fetchone()
            if semester_row is None:
                raise InputError('subject_semester_invalid')
            max_semesters = int(course_row.get('total_semesters') or 0)
            if not max_semesters:
                program = (course_row.get('program') or '').upper()
                max_semesters = 4 if program == 'PG' else 6
                if 'engineer' in (course_row.get('name') or '').lower():
                    max_semesters = max(max_semesters, 8)
            if int(semester_row['semester_number']) > max_semesters:
                raise InputError('subject_semester_invalid')
        if subject_id is not None:
            cursor.execute('SELECT 1 FROM subjects WHERE id = %s', (subject_id,))
            if cursor.fetchone() is None:
                return reject_input(MESSAGES, 'subject_not_found')
        values = (
            name, course_code, course_id, class_id, semester_id, course_type, mode,
            credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
            lectures, practical_hours, 1 if is_elective else 0, description, syllabus_url,
        )
        if subject_id is None:
            cursor.execute(
                """
                INSERT INTO subjects
                    (name, course_code, course_id, class_id, semester_id, course_type, theory_practical,
                     credits, theory_credits, practical_credits, marks, theory_marks, practical_marks,
                     lectures_per_week, practical_hours_per_week, is_elective, description, syllabus_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                values,
            )
            saved_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE subjects
                SET name = %s, course_code = %s, course_id = %s, class_id = %s, semester_id = %s,
                    course_type = %s, theory_practical = %s, credits = %s, theory_credits = %s,
                    practical_credits = %s, marks = %s, theory_marks = %s, practical_marks = %s,
                    lectures_per_week = %s, practical_hours_per_week = %s, is_elective = %s,
                    description = %s, syllabus_url = %s
                WHERE id = %s
                """,
                (*values, subject_id),
            )
            saved_id = subject_id
        with transaction(connection):
            pass
        return _read(saved_id)
    except InputError as exc:
        if connection is not None:
            connection.rollback()
        return reject_input(MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Subject save conflict')
        return reject_input(MESSAGES, 'subject_code_invalid')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Subject save failed')
        return json_error('The subject could not be saved.', 500, 'subjects_unavailable')
    finally:
        close(cursor, connection)


_LIST_SQL = """
    SELECT s.id, s.name, s.course_code, s.course_id, c.name AS course_name, c.program,
           s.class_id, cl.name AS class_name, s.semester_id, sem.semester_name,
           s.course_type, s.theory_practical, s.credits, s.theory_credits, s.practical_credits,
           s.marks, s.theory_marks, s.practical_marks, s.lectures_per_week, s.practical_hours_per_week,
           s.is_elective, s.description, s.syllabus_url,
           GROUP_CONCAT(DISTINCT CONCAT(f.name, ' (',
               CASE WHEN fa.is_primary THEN 'Primary' ELSE 'Secondary' END, ')')
               SEPARATOR ', ') AS faculty_names
    FROM subjects s
    JOIN courses c ON s.course_id = c.id
    LEFT JOIN classes cl ON s.class_id = cl.id
    LEFT JOIN semesters sem ON s.semester_id = sem.id
    LEFT JOIN faculty_allocations fa ON s.id = fa.subject_id
    LEFT JOIN faculty f ON fa.faculty_id = f.user_id
"""


def _read(subject_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(_LIST_SQL + ' WHERE s.id = %s GROUP BY s.id', (subject_id,))
        row = cursor.fetchone()
        if row is None:
            return reject_input(MESSAGES, 'subject_not_found')
        return json_ok(_public(row))
    finally:
        close(cursor, connection)


def register_subject_routes(blueprint):
    @blueprint.route('/subjects', methods=['GET'])
    def list_subjects():
        denied = permission_denied('subjects_view_subject', 'subjects_unavailable', 'The subject list could not be loaded.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT id, name, program FROM courses WHERE is_active = TRUE ORDER BY name')
            courses = [
                {'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 100), 'program': safe_text(row.get('program'), 20)}
                for row in cursor.fetchall()
            ]
            cursor.execute('SELECT id, name FROM classes ORDER BY display_order, name')
            classes = [{'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 100)} for row in cursor.fetchall()]
            cursor.execute('SELECT id, semester_name, semester_number FROM semesters ORDER BY semester_number')
            semesters = [
                {'id': safe_count(row.get('id')), 'name': safe_text(row.get('semester_name'), 100), 'semester_number': safe_count(row.get('semester_number'))}
                for row in cursor.fetchall()
            ]
            cursor.execute(_LIST_SQL + ' GROUP BY s.id ORDER BY cl.display_order, c.name, s.name')
            return json_ok({
                'subjects': [_public(row) for row in cursor.fetchall() if safe_count(row.get('id'))],
                'courses': [row for row in courses if row['id'] and row['name']],
                'classes': [row for row in classes if row['id'] and row['name']],
                'semesters': [row for row in semesters if row['id'] and row['name']],
                'permissions': {
                    'add': allowed('subjects_add_subject'),
                    'change': allowed('subjects_change_subject'),
                    'delete': allowed('subjects_delete_subject'),
                },
            })
        except Exception:
            current_app.logger.exception('Subject list failed')
            return json_error('The subject list could not be loaded.', 500, 'subjects_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/subjects', methods=['POST'])
    def create_subject():
        denied = permission_denied('subjects_add_subject', 'subjects_unavailable', 'The subject could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, None)

    @blueprint.route('/subjects/<int:subject_id>', methods=['PUT'])
    def update_subject(subject_id):
        denied = permission_denied('subjects_change_subject', 'subjects_unavailable', 'The subject could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, subject_id)

    @blueprint.route('/subjects/<int:subject_id>', methods=['DELETE'])
    def delete_subject(subject_id):
        denied = permission_denied('subjects_delete_subject', 'subjects_unavailable', 'The subject could not be deleted.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute('DELETE FROM subjects WHERE id = %s', (subject_id,))
            if cursor.rowcount == 0:
                return reject_input(MESSAGES, 'subject_not_found')
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except IntegrityError:
            if connection is not None:
                connection.rollback()
            return reject_input(MESSAGES, 'subject_in_use')
        except Exception:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Subject delete failed')
            return json_error('The subject could not be deleted.', 500, 'subjects_unavailable')
        finally:
            close(cursor, connection)
