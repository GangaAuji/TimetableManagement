from flask import session, redirect, url_for, flash, request
from ui.pages import render_template
from .teacher import teacher_bp, teacher_required
from services.teacher_portal import load_my_shifts, submit_shift_change

@teacher_bp.route('/my-shifts')
@teacher_required
def my_shifts():
    """View assigned shifts and availability"""
    page = load_my_shifts(session.get('faculty_id'))
    if page == 'missing' or not isinstance(page, dict):
        return redirect(url_for('teacher.dashboard'))
    return render_template('teacher/my_shifts.html',
                         faculty_info=page['faculty_info'],
                         schedule=page['schedule'],
                         day_names=page['day_names'],
                         change_requests=page['change_requests'])

@teacher_bp.route('/request-shift-change', methods=['POST'])
@teacher_required
def request_shift_change():
    """Submit a shift change request"""
    day_of_week = request.form.get('day_of_week')
    requested_shift_name = request.form.get('requested_shift_name')
    if not day_of_week or not requested_shift_name:
        flash('Please provide all required information.', 'warning')
        return redirect(url_for('teacher.my_shifts'))
    submit_shift_change(
        session.get('faculty_id'),
        day_of_week,
        request.form.get('current_shift_name', 'Not Assigned'),
        requested_shift_name,
        request.form.get('reason', ''),
    )
    return redirect(url_for('teacher.my_shifts'))
