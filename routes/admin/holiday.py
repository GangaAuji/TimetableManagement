
from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify
from werkzeug.security import generate_password_hash
from security import has_permission
from database import get_db_connection


holiday_bp = Blueprint('holiday', __name__, url_prefix='/admin/holiday')
# --- Holiday Management ---
@holiday_bp.route('/')
@has_permission('holidays_view')
def holidays_index():
    """List holidays and show add form."""
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
    rows = cursor.fetchall()
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
    return render_template('admin/holidays.html', holidays=items)


@holiday_bp.route('/add', methods=['POST'])
@has_permission('holidays_add')
def holidays_add():
    """Add a date-specific or recurring weekly holiday."""
    name = (request.form.get('name') or '').strip()
    applies_to_program = request.form.get('applies_to_program') or 'Both'
    holiday_type = request.form.get('holiday_type') or 'date'
    holiday_date = (request.form.get('holiday_date') or '').strip()
    day_of_week = request.form.get('day_of_week') or None

    if not name:
        flash('Holiday name is required.', 'danger')
        return redirect(url_for('admin.holidays_index'))

    if applies_to_program not in ('UG', 'PG', 'Both'):
        flash('Invalid program selection.', 'danger')
        return redirect(url_for('admin.holidays_index'))

    is_recurring = 1 if holiday_type == 'weekly' else 0

    # Validate fields by type
    if is_recurring:
        if day_of_week not in ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'):
            flash('Please select a valid day of week for recurring holiday.', 'danger')
            return redirect(url_for('admin.holidays_index'))
        insert_sql = (
            "INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)"
            " VALUES (NULL, %s, %s, %s, 1)"
        )
        params = (day_of_week, name, applies_to_program)
    else:
        if not holiday_date:
            flash('Please select a holiday date.', 'danger')
            return redirect(url_for('admin.holidays_index'))
        insert_sql = (
            "INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)"
            " VALUES (%s, NULL, %s, %s, 0)"
        )
        params = (holiday_date, name, applies_to_program)

    connection = get_db_connection()


    cursor = connection.cursor(dictionary=True)
    try:
        # Avoid duplicates for weekly recurring: same day/program
        if is_recurring:
            cursor.execute(
                "SELECT id FROM institution_holidays WHERE is_recurring = 1 AND day_of_week = %s AND applies_to_program = %s",
                (day_of_week, applies_to_program),
            )
            if cursor.fetchone():
                flash('A recurring holiday for this day and program already exists.', 'warning')
                cursor.close()
                return redirect(url_for('admin.holidays_index'))

        cursor.execute(insert_sql, params)
        connection.commit()
        flash('Holiday added.', 'success')
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error adding holiday: {str(e)}")
        flash('Failed to add holiday.', 'danger')
    finally:

        cursor.close()

        connection.close()
    return redirect(url_for('admin.holidays_index'))


@holiday_bp.route('/delete/<int:holiday_id>', methods=['POST'])
@has_permission('holidays_delete')
def holidays_delete(holiday_id):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("DELETE FROM institution_holidays WHERE id = %s", (holiday_id,))
        connection.commit()
        flash('Holiday deleted.', 'success')
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error deleting holiday: {str(e)}")
        flash('Failed to delete holiday.', 'danger')
    finally:

        cursor.close()

        connection.close()
    return redirect(url_for('admin.holidays_index'))

@holiday_bp.route('/edit/<int:holiday_id>', methods=['POST'])
@has_permission('holidays_change')
def holidays_edit(holiday_id):
    """Edit an existing holiday (name/program/type-specific fields)."""
    name = (request.form.get('name') or '').strip()
    applies_to_program = request.form.get('applies_to_program') or 'Both'
    holiday_type = request.form.get('holiday_type') or 'date'
    holiday_date = (request.form.get('holiday_date') or '').strip()
    day_of_week = request.form.get('day_of_week') or None

    if not name:
        flash('Holiday name is required.', 'danger')
        return redirect(url_for('admin.holidays_index'))

    if applies_to_program not in ('UG', 'PG', 'Both'):
        flash('Invalid program selection.', 'danger')
        return redirect(url_for('admin.holidays_index'))

    is_recurring = 1 if holiday_type == 'weekly' else 0

    connection = get_db_connection()


    cursor = connection.cursor(dictionary=True)
    try:
        # Validate by type and build update
        if is_recurring:
            if day_of_week not in ('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'):
                flash('Please select a valid day of week for recurring holiday.', 'danger')
                cursor.close()
                return redirect(url_for('admin.holidays_index'))

            # Avoid duplicates: same day/program but different id
            cursor.execute(
                """
                SELECT id FROM institution_holidays
                WHERE is_recurring = 1 AND day_of_week = %s AND applies_to_program = %s AND id != %s
                """,
                (day_of_week, applies_to_program, holiday_id),
            )
            if cursor.fetchone():
                flash('Another recurring holiday exists for this day and program.', 'warning')
                cursor.close()
                return redirect(url_for('admin.holidays_index'))

            cursor.execute(
                """
                UPDATE institution_holidays
                SET name = %s,
                    applies_to_program = %s,
                    is_recurring = 1,
                    day_of_week = %s,
                    holiday_date = NULL
                WHERE id = %s
                """,
                (name, applies_to_program, day_of_week, holiday_id),
            )
        else:
            if not holiday_date:
                flash('Please provide a holiday date.', 'danger')
                cursor.close()
                return redirect(url_for('admin.holidays_index'))

            cursor.execute(
                """
                UPDATE institution_holidays
                SET name = %s,
                    applies_to_program = %s,
                    is_recurring = 0,
                    holiday_date = %s,
                    day_of_week = NULL
                WHERE id = %s
                """,
                (name, applies_to_program, holiday_date, holiday_id),
            )

        connection.commit()
        flash('Holiday updated.', 'success')
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error editing holiday: {str(e)}")
        flash('Failed to update holiday.', 'danger')
    finally:

        cursor.close()

        connection.close()
    return redirect(url_for('admin.holidays_index'))
