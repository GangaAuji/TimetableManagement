from flask import Blueprint, make_response, redirect, url_for, session, request, flash, jsonify
from ui.pages import render_template
import csv
import io

from security import has_permission
from services.faculty_admin import (
    add_faculty_member,
    approve_faculty_absence,
    approve_faculty_proxy,
    change_faculty,
    deactivate_selected_faculty,
    find_faculty_form,
    find_faculty_header,
    list_faculty,
    load_faculty_absences,
    load_faculty_proxy_log,
    load_faculty_timetable,
    load_faculty_timetable_download,
    reject_faculty_absence,
    reject_faculty_proxy,
    remove_faculty_absence,
    save_or_load_availability_api,
    save_or_load_managed_availability,
    add_faculty_absence,
)
from utils.dates import format_hhmm

faculty_bp = Blueprint('faculty', __name__, url_prefix='/admin/faculty')

# --- Faculty Management (NEW CRUD) ---
@faculty_bp.route('/')
@has_permission('faculty_view_faculty')
def manage_faculty():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    department_filter = request.args.get('department_filter', '', type=str)
    page_data = list_faculty(page, search, department_filter, session.get('user_id'))
    return render_template(
        'legacy/admin/manage_faculty.html',
        faculty=page_data['faculty'],
        departments=page_data['departments'],
        page=page,
        total_pages=page_data['total_pages'],
        search=search,
        total_active_faculty=page_data['total_active_faculty'],
        total_inactive_faculty=page_data['total_inactive_faculty'],
        total=page_data['total'],
    )

@faculty_bp.route('/add', methods=['POST'])
@has_permission('faculty_add_faculty')
def add_faculty():
    username = request.form.get('username')
    password = request.form.get('password')
    name = request.form.get('name')
    if not username or not password or not name:
        flash('Username, password, and name are required.', 'danger')
        return redirect(url_for('faculty.manage_faculty'))
    add_faculty_member(
        username,
        password,
        name,
        request.form.get('email'),
        request.form.get('department_id'),
        request.form.get('phone', ''),
        request.form.get('designation', ''),
        request.form.get('is_active', '1') == '1',
        request.form.get('employee_id', '').strip(),
    )
    return redirect(url_for('faculty.manage_faculty'))

@faculty_bp.route('/get/<int:faculty_id>')
@has_permission('faculty_view_faculty')
def get_faculty(faculty_id):
    faculty_member = find_faculty_form(faculty_id)
    if faculty_member:
        return jsonify({
            'name': faculty_member['name'],
            'email': faculty_member['email'],
            'department_id': faculty_member['department_id'],
            'username': faculty_member['username'] or '',
            'phone': faculty_member['phone'] or '',
            'employee_id': faculty_member['employee_id'] or '',
            'designation': faculty_member['designation'] or '',
            'is_active': bool(faculty_member['is_active'])
        })
    return jsonify({'error': 'Faculty not found'}), 404

@faculty_bp.route('/update/<int:faculty_id>', methods=['POST'])
@has_permission('faculty_change_faculty')
def update_faculty(faculty_id):
    change_faculty(
        faculty_id,
        request.form.get('name'),
        request.form.get('email'),
        request.form.get('department_id'),
        request.form.get('phone', ''),
        request.form.get('designation', ''),
        request.form.get('is_active', '1') == '1',
        request.form.get('password'),
    )
    return redirect(url_for('faculty.manage_faculty'))

@faculty_bp.route('/bulk_delete', methods=['POST'])
@has_permission('faculty_delete_faculty')
def bulk_delete_faculty():
    ids_to_delete = request.form.getlist('faculty_ids')
    if not ids_to_delete:
        flash('No faculty members selected for deletion.', 'warning')
        return redirect(url_for('faculty.manage_faculty'))
    deactivate_selected_faculty(ids_to_delete)
    return redirect(url_for('faculty.manage_faculty'))


@faculty_bp.route('/<int:faculty_id>/details')
@has_permission('faculty_view_faculty')
def faculty_details(faculty_id):
    """Details dashboard for a faculty member (timetable, availability, absences, proxy log)."""
    fac = find_faculty_header(faculty_id)
    if not fac:
        flash('Faculty not found.', 'danger')
        return redirect(url_for('faculty.manage_faculty'))
    return render_template('admin/faculty_details.html', faculty_id=faculty_id, faculty_name=fac['name'], faculty_email=fac['email'])


@faculty_bp.route('/<int:faculty_id>/timetable/data')
@has_permission('faculty_view_faculty')
def faculty_timetable_data(faculty_id):
    data = load_faculty_timetable(faculty_id)
    if data == 'missing':
        return jsonify({'data': []})
    return jsonify({'data': data})


@faculty_bp.route('/<int:faculty_id>/timetable/download')
@has_permission('faculty_view_faculty')
def faculty_timetable_download(faculty_id):
    loaded = load_faculty_timetable_download(faculty_id)
    if loaded == 'missing':
        flash('Faculty not found.', 'danger')
        return redirect(url_for('faculty.manage_faculty'))
    rows, has_room = loaded
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Day', 'Start', 'End', 'Subject', 'Class', 'Division', 'Room'])
    for row in rows:
        room = row['room_number'] if has_room else ''
        writer.writerow([
            row['day_of_week'], format_hhmm(row['start_time']), format_hhmm(row['end_time']),
            row['subject_name'], row['class_name'], row['division_name'], room,
        ])
    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = f'attachment; filename=faculty_{faculty_id}_timetable.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp


@faculty_bp.route('/<int:faculty_id>/availability/manage', methods=['GET', 'POST'])
@has_permission('faculty_change_faculty')
def manage_faculty_availability(faculty_id):
    """Admin UI for managing faculty availability (same interface as teacher panel)"""
    page = save_or_load_managed_availability(faculty_id, request.method, request.form)
    if page == 'missing':
        return redirect(url_for('faculty.manage_faculty'))
    if page == 'saved':
        return redirect(url_for('faculty.faculty_details', faculty_id=faculty_id))
    if page == 'error':
        return redirect(url_for('faculty.manage_faculty_availability', faculty_id=faculty_id))
    return render_template('admin/manage_availability.html',
                         faculty_id=faculty_id,
                         faculty_name=page['faculty_name'],
                         avail_all_slots=page['avail_all_slots'],
                         shift_patterns=page['shift_patterns'])


@faculty_bp.route('/<int:faculty_id>/availability', methods=['GET', 'POST'])
@has_permission('faculty_change_faculty')
def faculty_availability_admin(faculty_id):
    page = save_or_load_availability_api(faculty_id, request.method, request.form, request.get_json(silent=True))
    if page == 'missing':
        return jsonify({'ok': False, 'error': 'Faculty not found'}), 404
    if page == 'json_saved':
        return jsonify({'ok': True, 'message': 'Availability updated successfully.'})
    if page == 'form_saved':
        return redirect(url_for('faculty.faculty_details', faculty_id=faculty_id))
    return jsonify(page)


@faculty_bp.route('/<int:faculty_id>/absences', methods=['GET', 'POST'])
@has_permission('faculty_change_faculty')
def faculty_absences_admin(faculty_id):
    if request.method == 'GET':
        return jsonify({'data': load_faculty_absences(faculty_id)})
    data = request.get_json(silent=True) or {}
    result = add_faculty_absence(
        faculty_id,
        data.get('absence_date') or request.form.get('absence_date'),
        data.get('reason') or request.form.get('reason'),
    )
    if result == 'date':
        return jsonify({'ok': False, 'error': 'absence_date required'}), 400
    return jsonify({'ok': True})


@faculty_bp.route('/<int:faculty_id>/absences/<int:absence_id>', methods=['DELETE'])
@has_permission('faculty_delete_faculty')
def faculty_absence_delete_admin(faculty_id, absence_id):
    result = remove_faculty_absence(faculty_id, absence_id)
    if result == 'missing':
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    if result == 'processed':
        return jsonify({'ok': False, 'error': 'Cannot delete processed absence'}), 400
    return jsonify({'ok': True})


@faculty_bp.route('/<int:faculty_id>/absences/<int:absence_id>/approve', methods=['POST'])
@has_permission('faculty_change_faculty')
def faculty_absence_approve_admin(faculty_id, absence_id):
    result = approve_faculty_absence(faculty_id, absence_id)
    if result == 'missing':
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    return jsonify({'ok': True})


@faculty_bp.route('/<int:faculty_id>/absences/<int:absence_id>/reject', methods=['POST'])
@has_permission('faculty_change_faculty')
def faculty_absence_reject_admin(faculty_id, absence_id):
    reject_faculty_absence(faculty_id, absence_id)
    return jsonify({'ok': True})


@faculty_bp.route('/<int:faculty_id>/proxy-log')
@has_permission('faculty_view_faculty')
def faculty_proxy_log_admin(faculty_id):
    return jsonify({'data': load_faculty_proxy_log(faculty_id)})


@faculty_bp.route('/<int:faculty_id>/proxy-log/<int:proxy_id>/approve', methods=['POST'])
@has_permission('faculty_change_faculty')
def faculty_proxy_approve_admin(faculty_id, proxy_id):
    data = request.get_json(silent=True) or {}
    result, proxy_faculty_id = approve_faculty_proxy(
        faculty_id, proxy_id, data.get('proxy_faculty_id'), session.get('user_id'),
    )
    if result == 'missing':
        return jsonify({'ok': False, 'error': 'Faculty not found'}), 404
    if result == 'not_found':
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    if result == 'already':
        return jsonify({'ok': True})
    return jsonify({'ok': True, 'proxy_faculty_id': proxy_faculty_id})


@faculty_bp.route('/<int:faculty_id>/proxy-log/<int:proxy_id>/reject', methods=['POST'])
@has_permission('faculty_change_faculty')
def faculty_proxy_reject_admin(faculty_id, proxy_id):
    result = reject_faculty_proxy(faculty_id, proxy_id, session.get('user_id'))
    if result == 'missing':
        return jsonify({'ok': False, 'error': 'Faculty not found'}), 404
    return jsonify({'ok': True})
