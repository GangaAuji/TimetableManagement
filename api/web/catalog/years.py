"""Academic year API. Rules match the existing admin screen."""

from flask import current_app
from mysql.connector import IntegrityError

from extensions import get_db_connection
from core.db import transaction
from api.web.access import (
    InputError,
    allowed,
    as_date,
    body,
    close,
    flag,
    iso_date,
    optional_text,
    permission_denied,
    reject_input,
    required_text,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

FIELDS = frozenset(('name', 'start_date', 'end_date', 'is_current', 'description'))
MESSAGES = {
    'invalid_body': 'The academic year could not be saved.',
    'year_name_invalid': 'Enter an academic year name up to 50 characters.',
    'year_date_invalid': 'Enter a valid start and end date.',
    'year_not_found': 'That academic year was not found.',
    'year_in_use': 'This academic year is in use, so it cannot be deleted.',
    'years_unavailable': 'The academic year list could not be loaded.',
}


def _public(row):
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 50),
        'start_date': as_date(row.get('start_date')),
        'end_date': as_date(row.get('end_date')),
        'is_current': bool(row.get('is_current')),
        'description': safe_text(row.get('description'), 4000),
    }


def _save(payload, year_id):
    connection = None
    cursor = None
    try:
        name = required_text(payload.get('name'), 50, 'year_name_invalid')
        start_date = iso_date(payload.get('start_date'), 'year_date_invalid')
        end_date = iso_date(payload.get('end_date'), 'year_date_invalid')
        if end_date < start_date:
            raise InputError('year_date_invalid')
        description = optional_text(payload.get('description', ''), 4000, 'invalid_body')
        is_current = flag(payload.get('is_current'))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if year_id is not None:
            cursor.execute('SELECT 1 FROM academic_years WHERE id = %s', (year_id,))
            if cursor.fetchone() is None:
                return reject_input(MESSAGES, 'year_not_found')
        if is_current:
            if year_id is None:
                cursor.execute('UPDATE academic_years SET is_current = 0')
            else:
                cursor.execute('UPDATE academic_years SET is_current = 0 WHERE id != %s', (year_id,))
        values = (name, start_date, end_date, 1 if is_current else 0, description)
        if year_id is None:
            cursor.execute(
                """
                INSERT INTO academic_years (name, start_date, end_date, is_current, description)
                VALUES (%s, %s, %s, %s, %s)
                """,
                values,
            )
            saved_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE academic_years
                SET name = %s, start_date = %s, end_date = %s, is_current = %s, description = %s
                WHERE id = %s
                """,
                (*values, year_id),
            )
            saved_id = year_id
        with transaction(connection):
            pass
        cursor.execute('SELECT * FROM academic_years WHERE id = %s', (saved_id,))
        return json_ok(_public(cursor.fetchone()))
    except InputError as exc:
        if connection is not None:
            connection.rollback()
        return reject_input(MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Academic year save conflict')
        return reject_input(MESSAGES, 'year_name_invalid')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Academic year save failed')
        return json_error('The academic year could not be saved.', 500, 'years_unavailable')
    finally:
        close(cursor, connection)


def register_year_routes(blueprint):
    @blueprint.route('/academic-years', methods=['GET'])
    def list_years():
        denied = permission_denied('academicyears_view', 'years_unavailable', 'The academic year list could not be loaded.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute('SELECT id, name, start_date, end_date, is_current, description FROM academic_years ORDER BY start_date DESC')
            return json_ok({
                'years': [_public(row) for row in cursor.fetchall() if safe_count(row.get('id'))],
                'permissions': {
                    'add': allowed('academicyears_add'),
                    'change': allowed('academicyears_change'),
                    'delete': allowed('academicyears_delete'),
                },
            })
        except Exception:
            current_app.logger.exception('Academic year list failed')
            return json_error('The academic year list could not be loaded.', 500, 'years_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/academic-years', methods=['POST'])
    def create_year():
        denied = permission_denied('academicyears_add', 'years_unavailable', 'The academic year could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, None)

    @blueprint.route('/academic-years/<int:year_id>', methods=['PUT'])
    def update_year(year_id):
        denied = permission_denied('academicyears_change', 'years_unavailable', 'The academic year could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, year_id)

    @blueprint.route('/academic-years/<int:year_id>', methods=['DELETE'])
    def delete_year(year_id):
        denied = permission_denied('academicyears_delete', 'years_unavailable', 'The academic year could not be deleted.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute('DELETE FROM academic_years WHERE id = %s', (year_id,))
            if cursor.rowcount == 0:
                return reject_input(MESSAGES, 'year_not_found')
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except IntegrityError:
            if connection is not None:
                connection.rollback()
            return reject_input(MESSAGES, 'year_in_use')
        except Exception:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Academic year delete failed')
            return json_error('The academic year could not be deleted.', 500, 'years_unavailable')
        finally:
            close(cursor, connection)
