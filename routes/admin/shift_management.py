"""
Faculty Shift Management Routes
Manages faculty work shifts and availability patterns for timetable generation
"""

from flask import Blueprint, request, redirect, url_for, flash, jsonify, session
from ui.pages import render_template
from security import has_permission
from services.shift_management import (
    add_shift_pattern,
    bulk_set_day_availability,
    edit_shift_pattern,
    faculty_availability_api,
    get_db_connection,
    load_change_requests,
    load_faculty_availability,
    load_shift_dashboard,
    remove_shift_pattern,
    respond_change_request,
    set_day_availability,
    shift_patterns_api,
)

shift_bp = Blueprint('shifts', __name__, url_prefix='/admin/shifts')

# ============================================================================
# SHIFT PATTERNS MANAGEMENT
# ============================================================================

@shift_bp.route('/')
@has_permission('shifts_view')
def manage_shifts():
    """Display Shift Management Dashboard"""
    page = load_shift_dashboard()
    return render_template('admin/manage_shifts.html',
                         shift_patterns=page['shift_patterns'],
                         active_shifts_count=page['active_shifts_count'],
                         faculty_with_shifts_count=page['faculty_with_shifts_count'])

@shift_bp.route('/add', methods=['POST'])
@has_permission('shifts_add')
def add_shift():
    """Add new shift pattern"""
    add_shift_pattern(
        request.form.get('shift_name'),
        request.form.get('shift_code'),
        request.form.get('start_time'),
        request.form.get('end_time'),
        request.form.get('shift_order', 1),
        request.form.get('description', ''),
        1 if request.form.get('is_active') else 0,
    )
    return redirect(url_for('shifts.manage_shifts'))

@shift_bp.route('/edit/<int:id>', methods=['POST'])
@has_permission('shifts_change')
def edit_shift(id):
    """Edit shift pattern"""
    edit_shift_pattern(
        id,
        request.form.get('shift_name'),
        request.form.get('shift_code'),
        request.form.get('start_time'),
        request.form.get('end_time'),
        request.form.get('shift_order'),
        request.form.get('description', ''),
        1 if request.form.get('is_active') else 0,
    )
    return redirect(url_for('shifts.manage_shifts'))

@shift_bp.route('/delete/<int:id>', methods=['POST'])
@has_permission('shifts_delete')
def delete_shift(id):
    """Delete shift pattern"""
    remove_shift_pattern(id)
    return redirect(url_for('shifts.manage_shifts'))

# ============================================================================
# FACULTY AVAILABILITY MANAGEMENT
# ============================================================================

@shift_bp.route('/faculty-availability')
@has_permission('shifts_view')
def faculty_availability():
    """Manage faculty availability and shift assignments"""
    page = load_faculty_availability()
    return render_template('admin/faculty_availability.html',
                         faculty_list=page['faculty_list'],
                         shift_patterns=page['shift_patterns'],
                         departments=page['departments'])

@shift_bp.route('/set-availability', methods=['POST'])
@has_permission('shifts_change')
def set_faculty_availability():
    """Set or update faculty availability for a specific day"""
    data = request.get_json()
    result = set_day_availability(data)
    status = result.pop('status', 200)
    return jsonify(result), status

@shift_bp.route('/bulk-set-availability', methods=['POST'])
@has_permission('shifts_change')
def bulk_set_availability():
    """Set availability for multiple faculty and days at once"""
    faculty_user_ids = request.form.getlist('faculty_ids')
    days = request.form.getlist('days')
    if not faculty_user_ids or not days:
        flash('Please select at least one faculty member and one day.', 'warning')
        return redirect(url_for('shifts.faculty_availability'))
    bulk_set_day_availability(
        faculty_user_ids,
        request.form.get('shift_pattern_id') or None,
        days,
        1 if request.form.get('is_available') else 0,
        request.form.get('notes', ''),
    )
    return redirect(url_for('shifts.faculty_availability'))

# ============================================================================
# API ENDPOINTS
# ============================================================================

@shift_bp.route('/api/faculty/<int:faculty_user_id>/availability')
@has_permission('shifts_view')
def get_faculty_availability_api(faculty_user_id):
    """Get faculty availability for timetable generation (uses user_id)"""
    return jsonify({
        'success': True,
        'availability': faculty_availability_api(faculty_user_id)
    })

@shift_bp.route('/api/shift-patterns')
@has_permission('shifts_view')
def get_shift_patterns_api():
    """Get all active shift patterns"""
    return jsonify({
        'success': True,
        'patterns': shift_patterns_api()
    })

# ============================================================================
# SHIFT CHANGE REQUESTS MANAGEMENT
# ============================================================================

@shift_bp.route('/change-requests')
@has_permission('shifts_view')
def view_change_requests():
    """View all shift change requests from faculty"""
    page = load_change_requests()
    return render_template('admin/shift_change_requests.html',
                         requests=page['requests'],
                         pending_count=page['pending_count'])

@shift_bp.route('/change-requests/<int:request_id>/respond', methods=['POST'])
@has_permission('shifts_change')
def respond_to_change_request(request_id):
    """Approve or reject a shift change request"""
    action = request.form.get('action')
    if action not in ['approve', 'reject']:
        flash('Invalid action.', 'danger')
        return redirect(url_for('shifts.view_change_requests'))
    respond_change_request(
        request_id,
        action,
        request.form.get('admin_response', ''),
        session.get('user_id'),
    )
    return redirect(url_for('shifts.view_change_requests'))
