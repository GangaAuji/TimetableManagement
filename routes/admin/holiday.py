
from flask import Blueprint, redirect, url_for, session, request, flash, current_app, jsonify
from ui.pages import render_template
from werkzeug.security import generate_password_hash
from security import has_permission
from services.institution_holidays import add_holiday, change_holiday, list_holidays, remove_holiday


holiday_bp = Blueprint('holiday', __name__, url_prefix='/admin/holiday')
# --- Holiday Management ---
@holiday_bp.route('/')
@has_permission('holidays_view')
def holidays_index():
    """List holidays and show add form."""
    return render_template('legacy/admin/holidays.html', holidays=list_holidays())


@holiday_bp.route('/add', methods=['POST'])
@has_permission('holidays_add')
def holidays_add():
    """Add a date-specific or recurring weekly holiday."""
    add_holiday(
        request.form.get('name'),
        request.form.get('applies_to_program'),
        request.form.get('holiday_type'),
        request.form.get('holiday_date'),
        request.form.get('day_of_week'),
    )
    return redirect(url_for('admin.holidays_index'))


@holiday_bp.route('/delete/<int:holiday_id>', methods=['POST'])
@has_permission('holidays_delete')
def holidays_delete(holiday_id):
    remove_holiday(holiday_id)
    return redirect(url_for('admin.holidays_index'))


@holiday_bp.route('/edit/<int:holiday_id>', methods=['POST'])
@has_permission('holidays_change')
def holidays_edit(holiday_id):
    """Edit an existing holiday (name/program/type-specific fields)."""
    change_holiday(
        holiday_id,
        request.form.get('name'),
        request.form.get('applies_to_program'),
        request.form.get('holiday_type'),
        request.form.get('holiday_date'),
        request.form.get('day_of_week'),
    )
    return redirect(url_for('admin.holidays_index'))
