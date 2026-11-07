"""
Student Management Routes
Handles all CRUD operations for students
"""

from flask import Blueprint, redirect, url_for, session, request, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.admin_students import (
    add_student as save_student,
    change_student,
    deactivate_selected_students,
    find_student,
    invite_form_choices,
    invite_students,
    list_students,
)

students_bp = Blueprint('students', __name__, url_prefix='/admin/students')


# --- Student Management (CRUD) ---
@students_bp.route('/')
@has_permission('students_view_student')
def manage_students():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    course_filter = request.args.get('course_filter', '', type=str)
    sort_by = request.args.get('sort_by', 's.name', type=str)
    sort_order = request.args.get('sort_order', 'ASC', type=str)
    per_page = 10
    page_data = list_students(page, search, course_filter, sort_by, sort_order, session.get('user_id'), per_page)
    return render_template(
        'legacy/admin/manage_students.html',
        students=page_data['students'],
        courses=page_data['courses'],
        classes=page_data['classes'],
        divisions=page_data['divisions'],
        page=page,
        total_pages=page_data['total_pages'],
        total=page_data['total'],
        total_active_students=page_data['total_active_students'],
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )

@students_bp.route('/add', methods=['POST'])
@has_permission('students_add_student')
def add_student():
    # Admin endpoint to add a new student (used by Manage Students modal)
    username = request.form.get('username')
    password = request.form.get('password')
    name = request.form.get('name')
    if not username or not password or not name:
        flash('Username, password, and name are required.', 'danger')
        return redirect(url_for('students.manage_students'))
    save_student(
        username,
        password,
        name,
        request.form.get('email'),
        request.form.get('phone'),
        request.form.get('roll_number'),
        request.form.get('course_id'),
        request.form.get('class_id'),
        request.form.get('division_id'),
    )
    return redirect(url_for('students.manage_students'))


@students_bp.route('/get/<int:student_id>')
@has_permission('students_view_student')
def get_student(student_id):
    student = find_student(student_id)
    if student:
        return jsonify({
            'name': student['name'], 'email': student['email'], 'phone': student['phone'], 'roll_number': student['roll_number'],
            'course_id': student['course_id'], 'class_id': student['class_id'], 'division_id': student['division_id'], 'username': student['username']
        })
    return jsonify({'error': 'Student not found'}), 404

@students_bp.route('/update/<int:student_id>', methods=['POST'])
@has_permission('students_change_student')
def update_student(student_id):
    change_student(
        student_id,
        request.form.get('name'),
        request.form.get('email'),
        request.form.get('phone'),
        request.form.get('roll_number'),
        request.form.get('course_id'),
        request.form.get('class_id'),
        request.form.get('division_id'),
        request.form.get('password'),
    )
    return redirect(url_for('students.manage_students'))

@students_bp.route('/bulk_delete', methods=['POST'])
@has_permission('students_delete_student')
def bulk_delete_students():
    ids_to_delete = request.form.getlist('student_ids')
    if not ids_to_delete:
        flash('No students selected for deletion.', 'warning')
        return redirect(url_for('students.manage_students'))
    deactivate_selected_students(ids_to_delete)
    return redirect(url_for('students.manage_students'))

@students_bp.route('/bulk-invite', methods=['GET', 'POST'])
@has_permission('students_bulk_invite')
def bulk_invite_students():
    """Bulk student invitation via CSV/Excel upload or form"""
    if request.method == 'POST':
        result = invite_students(request.files, request.form)
        if result == 'manage':
            return redirect(url_for('students.manage_students'))
        if result == 'invite':
            return redirect(url_for('students.bulk_invite_students'))
    choices = invite_form_choices()
    return render_template('admin/bulk_invite_students.html',
                         courses=choices['courses'], classes=choices['classes'], divisions=choices['divisions'])
