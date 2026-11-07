"""Holiday API. Rules match the existing admin holiday screen."""

from flask import current_app
from mysql.connector import IntegrityError

from extensions import get_db_connection
from core.db import transaction
from academic_rules.holidays import recurring_holiday_taken
from api.web.access import InputError, allowed, as_date, body, close, permission_denied, reject_input, required_text
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

PROGRAMS = ('UG', 'PG', 'Both')
DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
FIELDS = frozenset(('name', 'applies_to_program', 'holiday_type', 'holiday_date', 'day_of_week'))
MESSAGES = {
    'invalid_body': 'The holiday could not be saved.',
    'holiday_name_invalid': 'Enter a holiday name up to 120 characters.',
    'holiday_program_invalid': 'Choose UG, PG, or Both.',
    'holiday_day_invalid': 'Choose a day for a weekly holiday.',
    'holiday_date_invalid': 'Choose a holiday date.',
    'holiday_taken': 'A recurring holiday for this day and program already exists.',
    'holiday_not_found': 'That holiday was not found.',
    'holidays_unavailable': 'The holiday list could not be loaded.',
}


def _public(row):
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 120),
        'holiday_date': as_date(row.get('holiday_date')),
        'day_of_week': row.get('day_of_week') if row.get('day_of_week') in DAYS else '',
        'applies_to_program': row.get('applies_to_program') if row.get('applies_to_program') in PROGRAMS else '',
        'is_recurring': bool(row.get('is_recurring')),
    }


def _save(payload, holiday_id):
    connection = None
    cursor = None
    try:
        name = required_text(payload.get('name'), 120, 'holiday_name_invalid')
        program = payload.get('applies_to_program')
        if program not in PROGRAMS:
            raise InputError('holiday_program_invalid')
        holiday_type = payload.get('holiday_type')
        if holiday_type not in ('date', 'weekly'):
            raise InputError('invalid_body')
        recurring = holiday_type == 'weekly'
        holiday_date = payload.get('holiday_date') or ''
        day = payload.get('day_of_week') or ''
        if recurring:
            if day not in DAYS:
                raise InputError('holiday_day_invalid')
            holiday_date = None
        else:
            from api.web.access import iso_date
            holiday_date = iso_date(holiday_date, 'holiday_date_invalid')
            day = None
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if holiday_id is not None:
            cursor.execute('SELECT 1 FROM institution_holidays WHERE id = %s', (holiday_id,))
            if cursor.fetchone() is None:
                return reject_input(MESSAGES, 'holiday_not_found')
        if recurring and recurring_holiday_taken(cursor, day, program, holiday_id):
            raise InputError('holiday_taken')
        if holiday_id is None:
            cursor.execute(
                """
                INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (holiday_date, day, name, program, 1 if recurring else 0),
            )
            saved_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE institution_holidays
                SET holiday_date = %s, day_of_week = %s, name = %s, applies_to_program = %s, is_recurring = %s
                WHERE id = %s
                """,
                (holiday_date, day, name, program, 1 if recurring else 0, holiday_id),
            )
            saved_id = holiday_id
        with transaction(connection):
            pass
        cursor.execute(
            'SELECT id, holiday_date, day_of_week, name, applies_to_program, is_recurring FROM institution_holidays WHERE id = %s',
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
        current_app.logger.exception('Holiday save conflict')
        return reject_input(MESSAGES, 'holiday_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Holiday save failed')
        return json_error('The holiday could not be saved.', 500, 'holidays_unavailable')
    finally:
        close(cursor, connection)


def register_holiday_routes(blueprint):
    @blueprint.route('/holidays', methods=['GET'])
    def list_holidays():
        denied = permission_denied('holidays_view', 'holidays_unavailable', 'The holiday list could not be loaded.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id, holiday_date, day_of_week, name, applies_to_program, is_recurring
                FROM institution_holidays
                ORDER BY is_recurring DESC,
                         CASE WHEN holiday_date IS NULL THEN 1 ELSE 0 END,
                         holiday_date ASC,
                         FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')
                """
            )
            return json_ok({
                'holidays': [_public(row) for row in cursor.fetchall() if safe_count(row.get('id'))],
                'permissions': {
                    'add': allowed('holidays_add'),
                    'change': allowed('holidays_change'),
                    'delete': allowed('holidays_delete'),
                },
            })
        except Exception:
            current_app.logger.exception('Holiday list failed')
            return json_error('The holiday list could not be loaded.', 500, 'holidays_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/holidays', methods=['POST'])
    def create_holiday():
        denied = permission_denied('holidays_add', 'holidays_unavailable', 'The holiday could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, None)

    @blueprint.route('/holidays/<int:holiday_id>', methods=['PUT'])
    def update_holiday(holiday_id):
        denied = permission_denied('holidays_change', 'holidays_unavailable', 'The holiday could not be saved.')
        if denied is not None:
            return denied
        try:
            payload = body(FIELDS)
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        return _save(payload, holiday_id)

    @blueprint.route('/holidays/<int:holiday_id>', methods=['DELETE'])
    def delete_holiday(holiday_id):
        denied = permission_denied('holidays_delete', 'holidays_unavailable', 'The holiday could not be deleted.')
        if denied is not None:
            return denied
        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute('DELETE FROM institution_holidays WHERE id = %s', (holiday_id,))
            if cursor.rowcount == 0:
                return reject_input(MESSAGES, 'holiday_not_found')
            with transaction(connection):
                pass
            return json_ok({'deleted': True})
        except Exception:
            if connection is not None:
                connection.rollback()
            current_app.logger.exception('Holiday delete failed')
            return json_error('The holiday could not be deleted.', 500, 'holidays_unavailable')
        finally:
            close(cursor, connection)
