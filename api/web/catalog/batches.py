"""Course batch API. Rules match the existing admin screen."""

from flask import current_app
from mysql.connector import IntegrityError

from extensions import get_db_connection
from core.db import transaction
from api.web.access import (
    InputError,
    allowed,
    body,
    close,
    flag,
    optional_id,
    permission_denied,
    reject_input,
    required_text,
    whole_number,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

FIELDS = frozenset((
    'course_id', 'batch_name', 'academic_year_id', 'start_year', 'end_year',
    'total_students', 'current_semester', 'is_active',
))
MESSAGES = {
    'invalid_body': 'The batch could not be saved.',
    'batch_name_invalid': 'Enter a batch name up to 100 characters.',
    'batch_course_invalid': 'Choose a course.',
    'batch_year_invalid': 'Choose a valid academic year, or leave it empty.',
    'batch_range_invalid': 'Enter a start and end year between 1990 and 2100.',
    'batch_students_invalid': 'Student count must be between 0 and 10000.',
    'batch_semester_invalid': 'Current semester must be between 1 and 40.',
    'batch_not_found': 'That batch was not found.',
    'batch_in_use': 'This batch is in use, so it cannot be deleted.',
    'batches_unavailable': 'The batch list could not be loaded.',
}


def _public(row):
    return {
        'id': safe_count(row.get('id')),
        'course_id': safe_count(row.get('course_id')),
        'course_name': safe_text(row.get('course_name'), 100),
        'program': safe_text(row.get('program'), 20),
        'batch_name': safe_text(row.get('batch_name'), 100),
        'academic_year_id': safe_count(row.get('academic_year_id')) or None,
        'academic_year_name': safe_text(row.get('academic_year_name'), 50),
        'start_year': safe_count(row.get('start_year')),
        'end_year': safe_count(row.get('end_year')),
        'total_students': safe_count(row.get('total_students')),
        'current_semester': safe_count(row.get('current_semester')),
        'is_active': bool(row.get('is_active')),
    }


def _save(payload, batch_id):
    connection = None
    cursor = None
    try:
        name = required_text(payload.get('batch_name'), 100, 'batch_name_invalid')
        course_id = whole_number(payload.get('course_id'), 1000000, 'batch_course_invalid', lower=1)
        year_id = optional_id(payload.get('academic_year_id'), 'batch_year_invalid')
        start_year = whole_number(payload.get('start_year'), 2100, 'batch_range_invalid', lower=1990)
        end_year = whole_number(payload.get('end_year'), 2100, 'batch_range_invalid', lower=1990)
        if end_year < start_year:
            raise InputError('batch_range_invalid')
        total_students = whole_number(payload.get('total_students', 0), 10000, 'batch_students_invalid')
        current_semester = whole_number(payload.get('current_semester', 1), 40, 'batch_semester_invalid', lower=1)
        is_active = flag(payload.get('is_active'))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT 1 FROM courses WHERE id = %s', (course_id,))
        if cursor.fetchone() is None:
            raise InputError('batch_course_invalid')
        if year_id is not None:
            cursor.execute('SELECT 1 FROM academic_years WHERE id = %s', (year_id,))
            if cursor.fetchone() is None:
                raise InputError('batch_year_invalid')
        if batch_id is not None:
            cursor.execute('SELECT 1 FROM course_batches WHERE id = %s', (batch_id,))
            if cursor.fetchone() is None:
                return reject_input(MESSAGES, 'batch_not_found')
        values = (course_id, name, year_id, start_year, end_year, total_students, current_semester, 1 if is_active else 0)
        if batch_id is None:
            cursor.execute(
                """
                INSERT INTO course_batches
                    (course_id, batch_name, academic_year_id, start_year, end_year,
                     total_students, current_semester, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                values,
            )
            saved_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE course_batches
                SET course_id = %s, batch_name = %s, academic_year_id = %s,
                    start_year = %s, end_year = %s, total_students = %s,
                    current_semester = %s, is_active = %s
                WHERE id = %s
                """,
                (*values, batch_id),
            )
            saved_id = batch_id
        with transaction(connection):
            pass
        cursor.execute(
            """
            SELECT cb.id, cb.course_id, c.name AS course_name, c.program, cb.batch_name,
                   cb.academic_year_id, ay.name AS academic_year_name, cb.start_year, cb.end_year,
                   cb.total_students, cb.current_semester, cb.is_active
            FROM course_batches cb
            JOIN courses c ON cb.course_id = c.id
            LEFT JOIN academic_years ay ON cb.academic_year_id = ay.id
            WHERE cb.id = %s
            """,
            (saved_id,),
        )
        return json_ok(_public(cursor.fetchone()))
    except InputError as exc:
        if connection is not None:
            connection.rollback()
        return reject_input(MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Batch save conflict')
        return reject_input(MESSAGES, 'batch_name_invalid')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Batch save failed')
        return json_error('The batch could not be saved.', 500, 'batches_unavailable')
    finally:
        close(cursor, connection)


def register_batch_routes(blueprint):
    @blueprint.route('/batches', methods=['GET'])
    def list_batches():
        denied = permission_denied('batches_view', 'batches_unavailable', 'The batch list could not be loaded.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT id, name, program FROM courses WHERE is_active = TRUE ORDER BY name')
            courses = []
            for row in cursor.fetchall():
                course_id = safe_count(row.get('id'))
                name = safe_text(row.get('name'), 100)
                if course_id and name:
                    courses.append({'id': course_id, 'name': name, 'program': safe_text(row.get('program'), 20)})
            cursor.execute('SELECT id, name FROM academic_years ORDER BY start_date DESC')
            years = [{'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 50)} for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT cb.id, cb.course_id, c.name AS course_name, c.program, cb.batch_name,
                       cb.academic_year_id, ay.name AS academic_year_name, cb.start_year, cb.end_year,
                       cb.total_students, cb.current_semester, cb.is_active
                FROM course_batches cb
                JOIN courses c ON cb.course_id = c.id
                LEFT JOIN academic_years ay ON cb.academic_year_id = ay.id
                ORDER BY cb.start_year DESC, c.name
                """
            )
            return json_ok({
                'batches': [_public(row) for row in cursor.fetchall() if safe_count(row.get('id'))],
                'courses': courses,
                'years': [row for row in years if row['id'] and row['name']],
                'permissions': {
                    'add': allowed('batches_add'),
                    'change': allowed('batches_change'),
                    'delete': allowed('batches_delete'),
                },
            })
        except Exception:
            current_app.logger.exception('Batch list failed')
            return json_error('The batch list could not be loaded.', 500, 'batches_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/batches', methods=['POST'])
    def create_batch():
        denied = permission_denied('batches_add', 'batches_unavailable', 'The batch could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, None)

    @blueprint.route('/batches/<int:batch_id>', methods=['PUT'])
    def update_batch(batch_id):
        denied = permission_denied('batches_change', 'batches_unavailable', 'The batch could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, batch_id)

    @blueprint.route('/batches/<int:batch_id>', methods=['DELETE'])
    def delete_batch(batch_id):
        denied = permission_denied('batches_delete', 'batches_unavailable', 'The batch could not be deleted.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute('DELETE FROM course_batches WHERE id = %s', (batch_id,))
            if cursor.rowcount == 0:
                return reject_input(MESSAGES, 'batch_not_found')
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except IntegrityError:
            if connection is not None:
                connection.rollback()
            return reject_input(MESSAGES, 'batch_in_use')
        except Exception:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Batch delete failed')
            return json_error('The batch could not be deleted.', 500, 'batches_unavailable')
        finally:
            close(cursor, connection)
