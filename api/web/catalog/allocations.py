"""Faculty allocation API. faculty_allocations.faculty_id stores faculty.user_id."""

from flask import current_app
from mysql.connector import IntegrityError

from extensions import get_db_connection
from core.db import transaction
from api.web.access import (
    InputError,
    allowed,
    as_date,
    as_number,
    body,
    close,
    decimal_number,
    flag,
    iso_date,
    optional_id,
    optional_text,
    permission_denied,
    reject_input,
    whole_number,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

ALLOCATION_TYPES = ('Regular', 'Tutorial', 'Lab', 'Guest')
FIELDS = frozenset((
    'faculty_id', 'subject_id', 'class_id', 'division_id', 'semester_id', 'course_batch_id',
    'allocated_hours', 'workload_percentage', 'is_primary', 'allocation_type',
    'start_date', 'end_date', 'notes',
))
MESSAGES = {
    'invalid_body': 'The allocation could not be saved.',
    'allocation_faculty_invalid': 'Choose a faculty member.',
    'allocation_subject_invalid': 'Choose a subject.',
    'allocation_class_invalid': 'Choose a valid class, or leave it empty.',
    'allocation_division_invalid': 'Choose a valid division, or leave it empty.',
    'allocation_semester_invalid': 'Choose a valid semester, or leave it empty.',
    'allocation_batch_invalid': 'Choose a valid batch, or leave it empty.',
    'allocation_hours_invalid': 'Allocated hours must be between 0 and 80.',
    'allocation_workload_invalid': 'Workload must be between 0 and 100.',
    'allocation_type_invalid': 'Choose a valid allocation type.',
    'allocation_date_invalid': 'Enter a valid start and end date.',
    'allocation_not_found': 'That allocation was not found.',
    'allocation_in_use': 'This allocation is in use, so it cannot be deleted.',
    'allocations_unavailable': 'The allocation list could not be loaded.',
}


def _public(row):
    allocation_type = row.get('allocation_type') if row.get('allocation_type') in ALLOCATION_TYPES else ''
    return {
        'id': safe_count(row.get('id')),
        'faculty_id': safe_count(row.get('faculty_table_id')),
        'faculty_name': safe_text(row.get('faculty_name'), 160),
        'subject_id': safe_count(row.get('subject_id')),
        'subject_name': safe_text(row.get('subject_name'), 150),
        'course_code': safe_text(row.get('course_code'), 20),
        'course_name': safe_text(row.get('course_name'), 100),
        'class_id': safe_count(row.get('class_id')) or None,
        'class_name': safe_text(row.get('class_name'), 100),
        'division_id': safe_count(row.get('division_id')) or None,
        'division_name': safe_text(row.get('division_name'), 80),
        'semester_id': safe_count(row.get('semester_id')) or None,
        'semester_name': safe_text(row.get('semester_name'), 100),
        'course_batch_id': safe_count(row.get('course_batch_id')) or None,
        'batch_name': safe_text(row.get('batch_name'), 100),
        'allocated_hours': as_number(row.get('allocated_hours')),
        'workload_percentage': as_number(row.get('workload_percentage')),
        'is_primary': bool(row.get('is_primary')),
        'allocation_type': allocation_type,
        'start_date': as_date(row.get('start_date')),
        'end_date': as_date(row.get('end_date')),
        'notes': safe_text(row.get('notes'), 500),
    }


def _exists(cursor, table, record_id, code):
    if record_id is None:
        return None
    cursor.execute(f'SELECT 1 FROM {table} WHERE id = %s', (record_id,))
    if cursor.fetchone() is None:
        raise InputError(code)
    return record_id


def _save(payload, allocation_id):
    connection = None
    cursor = None
    try:
        faculty_id = whole_number(payload.get('faculty_id'), 1000000, 'allocation_faculty_invalid', lower=1)
        subject_id = whole_number(payload.get('subject_id'), 1000000, 'allocation_subject_invalid', lower=1)
        class_id = optional_id(payload.get('class_id'), 'allocation_class_invalid')
        division_id = optional_id(payload.get('division_id'), 'allocation_division_invalid')
        semester_id = optional_id(payload.get('semester_id'), 'allocation_semester_invalid')
        batch_id = optional_id(payload.get('course_batch_id'), 'allocation_batch_invalid')
        hours = decimal_number(payload.get('allocated_hours', 0), 80, 'allocation_hours_invalid')
        workload = decimal_number(payload.get('workload_percentage', 100), 100, 'allocation_workload_invalid')
        is_primary = flag(payload.get('is_primary'))
        allocation_type = payload.get('allocation_type')
        if allocation_type not in ALLOCATION_TYPES:
            raise InputError('allocation_type_invalid')
        start_date = iso_date(payload.get('start_date'), 'allocation_date_invalid', required=False)
        end_date = iso_date(payload.get('end_date'), 'allocation_date_invalid', required=False)
        if start_date and end_date and end_date < start_date:
            raise InputError('allocation_date_invalid')
        notes = optional_text(payload.get('notes', ''), 500, 'invalid_body')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT user_id FROM faculty WHERE id = %s', (faculty_id,))
        faculty_row = cursor.fetchone()
        if faculty_row is None or not faculty_row.get('user_id'):
            raise InputError('allocation_faculty_invalid')
        faculty_user_id = faculty_row['user_id']
        _exists(cursor, 'subjects', subject_id, 'allocation_subject_invalid')
        _exists(cursor, 'classes', class_id, 'allocation_class_invalid')
        _exists(cursor, 'divisions', division_id, 'allocation_division_invalid')
        _exists(cursor, 'semesters', semester_id, 'allocation_semester_invalid')
        _exists(cursor, 'course_batches', batch_id, 'allocation_batch_invalid')
        if allocation_id is not None:
            cursor.execute('SELECT 1 FROM faculty_allocations WHERE id = %s', (allocation_id,))
            if cursor.fetchone() is None:
                return reject_input(MESSAGES, 'allocation_not_found')
        values = (
            faculty_user_id, subject_id, class_id, division_id, semester_id, batch_id,
            hours, workload, 1 if is_primary else 0, allocation_type, start_date, end_date, notes,
        )
        if allocation_id is None:
            cursor.execute(
                """
                INSERT INTO faculty_allocations
                    (faculty_id, subject_id, class_id, division_id, semester_id, course_batch_id,
                     allocated_hours, workload_percentage, is_primary, allocation_type,
                     start_date, end_date, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                values,
            )
            saved_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE faculty_allocations
                SET faculty_id = %s, subject_id = %s, class_id = %s, division_id = %s,
                    semester_id = %s, course_batch_id = %s, allocated_hours = %s,
                    workload_percentage = %s, is_primary = %s, allocation_type = %s,
                    start_date = %s, end_date = %s, notes = %s
                WHERE id = %s
                """,
                (*values, allocation_id),
            )
            saved_id = allocation_id
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
        current_app.logger.exception('Allocation save conflict')
        return reject_input(MESSAGES, 'invalid_body')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Allocation save failed')
        return json_error('The allocation could not be saved.', 500, 'allocations_unavailable')
    finally:
        close(cursor, connection)


_LIST_SQL = """
    SELECT fa.id, f.id AS faculty_table_id, f.name AS faculty_name,
           fa.subject_id, s.name AS subject_name, s.course_code, c.name AS course_name,
           fa.class_id, cl.name AS class_name, fa.division_id, d.name AS division_name,
           fa.semester_id, sem.semester_name, fa.course_batch_id, cb.batch_name,
           fa.allocated_hours, fa.workload_percentage, fa.is_primary, fa.allocation_type,
           fa.start_date, fa.end_date, fa.notes
    FROM faculty_allocations fa
    JOIN faculty f ON fa.faculty_id = f.user_id
    JOIN subjects s ON fa.subject_id = s.id
    JOIN courses c ON s.course_id = c.id
    LEFT JOIN classes cl ON fa.class_id = cl.id
    LEFT JOIN divisions d ON fa.division_id = d.id
    LEFT JOIN semesters sem ON fa.semester_id = sem.id
    LEFT JOIN course_batches cb ON fa.course_batch_id = cb.id
"""


def _read(allocation_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(_LIST_SQL + ' WHERE fa.id = %s', (allocation_id,))
        row = cursor.fetchone()
        if row is None:
            return reject_input(MESSAGES, 'allocation_not_found')
        return json_ok(_public(row))
    finally:
        close(cursor, connection)


def _options(cursor, sql):
    cursor.execute(sql)
    rows = []
    for row in cursor.fetchall():
        record_id = safe_count(row.get('id'))
        name = safe_text(row.get('name'), 160)
        if record_id and name:
            rows.append({'id': record_id, 'name': name})
    return rows


def register_allocation_routes(blueprint):
    @blueprint.route('/allocations', methods=['GET'])
    def list_allocations():
        denied = permission_denied('allocations_view', 'allocations_unavailable', 'The allocation list could not be loaded.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            faculty = _options(cursor, 'SELECT id, name FROM faculty WHERE is_active = TRUE ORDER BY name')
            subjects = _options(cursor, "SELECT id, CONCAT(name, ' (', course_code, ')') AS name FROM subjects ORDER BY name")
            classes = _options(cursor, 'SELECT id, name FROM classes ORDER BY display_order, name')
            divisions = _options(cursor, 'SELECT id, name FROM divisions ORDER BY name')
            semesters = _options(cursor, 'SELECT id, semester_name AS name FROM semesters ORDER BY semester_number')
            batches = _options(cursor, 'SELECT id, batch_name AS name FROM course_batches WHERE is_active = TRUE ORDER BY batch_name')
            cursor.execute(_LIST_SQL + ' ORDER BY cl.display_order, c.name, f.name, s.name')
            return json_ok({
                'allocations': [_public(row) for row in cursor.fetchall() if safe_count(row.get('id'))],
                'faculty': faculty,
                'subjects': subjects,
                'classes': classes,
                'divisions': divisions,
                'semesters': semesters,
                'batches': batches,
                'permissions': {
                    'add': allowed('allocations_add'),
                    'change': allowed('allocations_change'),
                    'delete': allowed('allocations_delete'),
                },
            })
        except Exception:
            current_app.logger.exception('Allocation list failed')
            return json_error('The allocation list could not be loaded.', 500, 'allocations_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/allocations', methods=['POST'])
    def create_allocation():
        denied = permission_denied('allocations_add', 'allocations_unavailable', 'The allocation could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, None)

    @blueprint.route('/allocations/<int:allocation_id>', methods=['PUT'])
    def update_allocation(allocation_id):
        denied = permission_denied('allocations_change', 'allocations_unavailable', 'The allocation could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, allocation_id)

    @blueprint.route('/allocations/<int:allocation_id>', methods=['DELETE'])
    def delete_allocation(allocation_id):
        denied = permission_denied('allocations_delete', 'allocations_unavailable', 'The allocation could not be deleted.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute('DELETE FROM faculty_allocations WHERE id = %s', (allocation_id,))
            if cursor.rowcount == 0:
                return reject_input(MESSAGES, 'allocation_not_found')
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except IntegrityError:
            if connection is not None:
                connection.rollback()
            return reject_input(MESSAGES, 'allocation_in_use')
        except Exception:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Allocation delete failed')
            return json_error('The allocation could not be deleted.', 500, 'allocations_unavailable')
        finally:
            close(cursor, connection)
