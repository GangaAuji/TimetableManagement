"""Semester API. Rules match the existing admin screen."""

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
    permission_denied,
    reject_input,
    required_text,
    whole_number,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

FIELDS = frozenset((
    'academic_year_id', 'semester_number', 'semester_name', 'start_date', 'end_date',
    'class_id', 'is_current', 'min_credits', 'max_credits',
))
MESSAGES = {
    'invalid_body': 'The semester could not be saved.',
    'semester_name_invalid': 'Enter a semester name up to 100 characters.',
    'semester_number_invalid': 'Semester number must be between 1 and 20.',
    'semester_date_invalid': 'Enter a valid start and end date.',
    'semester_year_invalid': 'Choose an academic year.',
    'semester_class_invalid': 'Choose a valid class, or leave it empty.',
    'semester_credits_invalid': 'Credits must be between 0 and 100, and the minimum cannot exceed the maximum.',
    'semester_not_found': 'That semester was not found.',
    'semester_in_use': 'This semester is in use, so it cannot be deleted.',
    'semesters_unavailable': 'The semester list could not be loaded.',
}


def _public(row):
    return {
        'id': safe_count(row.get('id')),
        'academic_year_id': safe_count(row.get('academic_year_id')),
        'academic_year_name': safe_text(row.get('academic_year_name'), 50),
        'semester_number': safe_count(row.get('semester_number')),
        'semester_name': safe_text(row.get('semester_name'), 100),
        'start_date': as_date(row.get('start_date')),
        'end_date': as_date(row.get('end_date')),
        'class_id': safe_count(row.get('class_id')) or None,
        'class_name': safe_text(row.get('class_name'), 100),
        'is_current': bool(row.get('is_current')),
        'min_credits': as_number(row.get('min_credits')),
        'max_credits': as_number(row.get('max_credits')),
    }


def _save(payload, semester_id):
    connection = None
    cursor = None
    try:
        name = required_text(payload.get('semester_name'), 100, 'semester_name_invalid')
        number = whole_number(payload.get('semester_number'), 20, 'semester_number_invalid', lower=1)
        start_date = iso_date(payload.get('start_date'), 'semester_date_invalid')
        end_date = iso_date(payload.get('end_date'), 'semester_date_invalid')
        if end_date < start_date:
            raise InputError('semester_date_invalid')
        year_id = whole_number(payload.get('academic_year_id'), 1000000, 'semester_year_invalid', lower=1)
        class_id = optional_id(payload.get('class_id'), 'semester_class_invalid')
        is_current = flag(payload.get('is_current'))
        min_credits = decimal_number(payload.get('min_credits', 18), 100, 'semester_credits_invalid')
        max_credits = decimal_number(payload.get('max_credits', 30), 100, 'semester_credits_invalid')
        if min_credits > max_credits:
            raise InputError('semester_credits_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT 1 FROM academic_years WHERE id = %s', (year_id,))
        if cursor.fetchone() is None:
            raise InputError('semester_year_invalid')
        if class_id is not None:
            cursor.execute('SELECT 1 FROM classes WHERE id = %s', (class_id,))
            if cursor.fetchone() is None:
                raise InputError('semester_class_invalid')
        if semester_id is not None:
            cursor.execute('SELECT 1 FROM semesters WHERE id = %s', (semester_id,))
            if cursor.fetchone() is None:
                return reject_input(MESSAGES, 'semester_not_found')
        values = (year_id, number, name, start_date, end_date, class_id, 1 if is_current else 0, min_credits, max_credits)
        if semester_id is None:
            cursor.execute(
                """
                INSERT INTO semesters
                    (academic_year_id, semester_number, semester_name, start_date, end_date,
                     class_id, is_current, min_credits, max_credits)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                values,
            )
            saved_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE semesters
                SET academic_year_id = %s, semester_number = %s, semester_name = %s,
                    start_date = %s, end_date = %s, class_id = %s, is_current = %s,
                    min_credits = %s, max_credits = %s
                WHERE id = %s
                """,
                (*values, semester_id),
            )
            saved_id = semester_id
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
        current_app.logger.exception('Semester save conflict')
        return reject_input(MESSAGES, 'semester_name_invalid')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Semester save failed')
        return json_error('The semester could not be saved.', 500, 'semesters_unavailable')
    finally:
        close(cursor, connection)


def _read(semester_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT s.id, s.academic_year_id, ay.name AS academic_year_name, s.semester_number,
                   s.semester_name, s.start_date, s.end_date, s.class_id, c.name AS class_name,
                   s.is_current, s.min_credits, s.max_credits
            FROM semesters s
            JOIN academic_years ay ON s.academic_year_id = ay.id
            LEFT JOIN classes c ON s.class_id = c.id
            WHERE s.id = %s
            """,
            (semester_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return reject_input(MESSAGES, 'semester_not_found')
        return json_ok(_public(row))
    finally:
        close(cursor, connection)


def register_semester_routes(blueprint):
    @blueprint.route('/semesters', methods=['GET'])
    def list_semesters():
        denied = permission_denied('semesters_view', 'semesters_unavailable', 'The semester list could not be loaded.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT id, name FROM academic_years ORDER BY start_date DESC')
            years = [{'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 50)} for row in cursor.fetchall()]
            cursor.execute('SELECT id, name FROM classes ORDER BY display_order, name')
            classes = [{'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 100)} for row in cursor.fetchall()]
            cursor.execute(
                """
                SELECT s.id, s.academic_year_id, ay.name AS academic_year_name, s.semester_number,
                       s.semester_name, s.start_date, s.end_date, s.class_id, c.name AS class_name,
                       s.is_current, s.min_credits, s.max_credits
                FROM semesters s
                JOIN academic_years ay ON s.academic_year_id = ay.id
                LEFT JOIN classes c ON s.class_id = c.id
                ORDER BY s.semester_number
                """
            )
            return json_ok({
                'semesters': [_public(row) for row in cursor.fetchall() if safe_count(row.get('id'))],
                'years': [row for row in years if row['id'] and row['name']],
                'classes': [row for row in classes if row['id'] and row['name']],
                'permissions': {
                    'add': allowed('semesters_add'),
                    'change': allowed('semesters_change'),
                    'delete': allowed('semesters_delete'),
                },
            })
        except Exception:
            current_app.logger.exception('Semester list failed')
            return json_error('The semester list could not be loaded.', 500, 'semesters_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/semesters', methods=['POST'])
    def create_semester():
        denied = permission_denied('semesters_add', 'semesters_unavailable', 'The semester could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, None)

    @blueprint.route('/semesters/<int:semester_id>', methods=['PUT'])
    def update_semester(semester_id):
        denied = permission_denied('semesters_change', 'semesters_unavailable', 'The semester could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, semester_id)

    @blueprint.route('/semesters/<int:semester_id>', methods=['DELETE'])
    def delete_semester(semester_id):
        denied = permission_denied('semesters_delete', 'semesters_unavailable', 'The semester could not be deleted.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute('DELETE FROM semesters WHERE id = %s', (semester_id,))
            if cursor.rowcount == 0:
                return reject_input(MESSAGES, 'semester_not_found')
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except IntegrityError:
            if connection is not None:
                connection.rollback()
            return reject_input(MESSAGES, 'semester_in_use')
        except Exception:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Semester delete failed')
            return json_error('The semester could not be deleted.', 500, 'semesters_unavailable')
        finally:
            close(cursor, connection)
