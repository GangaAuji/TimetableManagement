"""Institution holiday list and saves. This module does not read the request."""

from flask import current_app, flash

from academic_rules.holidays import recurring_holiday_taken
from data_access.institution_holidays import (
    delete_holiday,
    fetch_holidays,
    insert_dated_holiday,
    insert_weekly_holiday,
    update_dated_holiday,
    update_weekly_holiday,
)
from extensions import get_db_connection

_WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def list_holidays():
    """Return the holiday rows for the admin page. The connection stays open."""
    connection, cursor = _cursor()
    rows = fetch_holidays(cursor)
    cursor.close()
    items = []
    for row in rows:
        items.append({
            'id': row['id'],
            'holiday_date': row['holiday_date'].strftime('%Y-%m-%d') if row['holiday_date'] and hasattr(row['holiday_date'], 'strftime') else (row['holiday_date'] or ''),
            'day_of_week': row['day_of_week'] or '',
            'name': row['name'],
            'applies_to_program': row['applies_to_program'],
            'is_recurring': bool(row['is_recurring']),
        })
    return items


def add_holiday(name, applies_to_program, holiday_type, holiday_date, day_of_week):
    """Add a holiday. Invalid input is flashed before a connection is opened."""
    name = (name or '').strip()
    applies_to_program = applies_to_program or 'Both'
    holiday_type = holiday_type or 'date'
    holiday_date = (holiday_date or '').strip()
    day_of_week = day_of_week or None
    if not name:
        flash('Holiday name is required.', 'danger')
        return
    if applies_to_program not in ('UG', 'PG', 'Both'):
        flash('Invalid program selection.', 'danger')
        return
    is_recurring = 1 if holiday_type == 'weekly' else 0
    if is_recurring:
        if day_of_week not in _WEEKDAYS:
            flash('Please select a valid day of week for recurring holiday.', 'danger')
            return
    elif not holiday_date:
        flash('Please select a holiday date.', 'danger')
        return

    connection, cursor = _cursor()
    try:
        if is_recurring and recurring_holiday_taken(cursor, day_of_week, applies_to_program, None):
            flash('A recurring holiday for this day and program already exists.', 'warning')
            cursor.close()
            return
        if is_recurring:
            insert_weekly_holiday(cursor, day_of_week, name, applies_to_program)
        else:
            insert_dated_holiday(cursor, holiday_date, name, applies_to_program)
        connection.commit()
        flash('Holiday added.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error adding holiday: {str(exc)}")
        flash('Failed to add holiday.', 'danger')
    finally:
        cursor.close()
        connection.close()


def remove_holiday(holiday_id):
    """Delete a holiday."""
    connection, cursor = _cursor()
    try:
        delete_holiday(cursor, holiday_id)
        connection.commit()
        flash('Holiday deleted.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error deleting holiday: {str(exc)}")
        flash('Failed to delete holiday.', 'danger')
    finally:
        cursor.close()
        connection.close()


def change_holiday(holiday_id, name, applies_to_program, holiday_type, holiday_date, day_of_week):
    """Update a holiday. Invalid input is flashed before a connection is opened when it can be."""
    name = (name or '').strip()
    applies_to_program = applies_to_program or 'Both'
    holiday_type = holiday_type or 'date'
    holiday_date = (holiday_date or '').strip()
    day_of_week = day_of_week or None
    if not name:
        flash('Holiday name is required.', 'danger')
        return
    if applies_to_program not in ('UG', 'PG', 'Both'):
        flash('Invalid program selection.', 'danger')
        return
    is_recurring = 1 if holiday_type == 'weekly' else 0
    connection, cursor = _cursor()
    try:
        if is_recurring:
            if day_of_week not in _WEEKDAYS:
                flash('Please select a valid day of week for recurring holiday.', 'danger')
                cursor.close()
                return
            if recurring_holiday_taken(cursor, day_of_week, applies_to_program, holiday_id):
                flash('Another recurring holiday exists for this day and program.', 'warning')
                cursor.close()
                return
            update_weekly_holiday(cursor, name, applies_to_program, day_of_week, holiday_id)
        else:
            if not holiday_date:
                flash('Please provide a holiday date.', 'danger')
                cursor.close()
                return
            update_dated_holiday(cursor, name, applies_to_program, holiday_date, holiday_id)
        connection.commit()
        flash('Holiday updated.', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error editing holiday: {str(exc)}")
        flash('Failed to update holiday.', 'danger')
    finally:
        cursor.close()
        connection.close()
