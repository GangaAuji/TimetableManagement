"""Academic courses."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.courses import (
    change_course,
    create_course,
    list_courses,
    remove_course,
)

from routes.academic.blueprint import academic_bp

@academic_bp.route('/courses')
@has_permission('courses_view_course')
def manage_courses():
    """Display Courses Management Page"""
    courses, departments, course_count = list_courses()
    return render_template('legacy/admin/manage_courses.html',
                         courses=courses,
                         departments=departments,course_count=course_count)


@academic_bp.route('/courses/add', methods=['POST'])
@has_permission('courses_add_course')
def add_course():
    """Add new course"""
    name = request.form.get('name')
    code = request.form.get('code')
    program = request.form.get('program')
    department_id = request.form.get('department_id')
    duration_years = request.form.get('duration_years', 3)
    total_semesters = request.form.get('total_semesters', 6)
    description = request.form.get('description', '')
    is_active = 1 if request.form.get('is_active') else 0
    error = create_course(
        name, code, program, department_id, duration_years, total_semesters, description, is_active,
    )
    if error:
        flash(f'Error adding course: {error}', 'danger')
    else:
        flash(f'Course {name} added successfully!', 'success')
    return redirect(url_for('academic.manage_courses'))


@academic_bp.route('/courses/edit/<int:id>', methods=['POST'])
@has_permission('courses_change_course')
def edit_course(id):
    """Edit course"""
    name = request.form.get('name')
    code = request.form.get('code')
    program = request.form.get('program')
    department_id = request.form.get('department_id')
    duration_years = request.form.get('duration_years')
    total_semesters = request.form.get('total_semesters')
    description = request.form.get('description', '')
    is_active = 1 if request.form.get('is_active') else 0
    error = change_course(
        id, name, code, program, department_id, duration_years, total_semesters, description, is_active,
    )
    if error:
        flash(f'Error updating course: {error}', 'danger')
    else:
        flash(f'Course {name} updated successfully!', 'success')
    return redirect(url_for('academic.manage_courses'))


@academic_bp.route('/courses/delete/<int:id>', methods=['POST'])
@has_permission('courses_delete_course')
def delete_course(id):
    """Delete course"""
    error = remove_course(id)
    if error:
        flash(f'Error deleting course: {error}', 'danger')
    else:
        flash('Course deleted successfully!', 'success')
    return redirect(url_for('academic.manage_courses'))
