"""Academic allocations."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.allocations import (
    change_allocation,
    create_allocation,
    list_allocations,
    remove_allocation,
)

from routes.academic.blueprint import academic_bp

@academic_bp.route('/allocations')
@has_permission('allocations_view')
def manage_allocations():
    """Display Faculty Allocations Management Page with class-based filtering"""
    filter_class_id = request.args.get('class_id', type=int)
    filter_faculty_id = request.args.get('faculty_id', type=int)
    filter_course_id = request.args.get('course_id', type=int)
    (
        allocations, faculty, subjects, classes, divisions, semesters, batches, courses,
    ) = list_allocations(filter_class_id, filter_faculty_id, filter_course_id)
    return render_template('legacy/admin/manage_allocations.html',
                         allocations=allocations,
                         faculty=faculty,
                         subjects=subjects,
                         classes=classes,
                         divisions=divisions,
                         semesters=semesters,
                         batches=batches,
                         courses=courses,
                         filter_class_id=filter_class_id,
                         filter_faculty_id=filter_faculty_id,
                         filter_course_id=filter_course_id)


@academic_bp.route('/allocations/add', methods=['POST'])
@has_permission('allocations_add')
def add_allocation():
    """Add new faculty allocation"""
    faculty_id_from_form = request.form.get('faculty_id')
    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id') or None
    division_id = request.form.get('division_id') or None
    semester_id = request.form.get('semester_id') or None
    course_batch_id = request.form.get('course_batch_id') or None
    allocated_hours = float(request.form.get('allocated_hours', 0))
    workload_percentage = float(request.form.get('workload_percentage', 100.0))
    is_primary = 1 if request.form.get('is_primary') else 0
    allocation_type = request.form.get('allocation_type', 'Regular')
    start_date = request.form.get('start_date') or None
    end_date = request.form.get('end_date') or None
    notes = request.form.get('notes', '')
    result = create_allocation(
        faculty_id_from_form, subject_id, class_id, division_id, semester_id, course_batch_id,
        allocated_hours, workload_percentage, is_primary, allocation_type, start_date, end_date, notes,
    )
    if result == 'invalid_faculty':
        flash('Invalid faculty selection.', 'danger')
    elif result:
        flash(f'Error adding allocation: {result}', 'danger')
    else:
        flash('Faculty allocation added successfully!', 'success')
    return redirect(url_for('academic.manage_allocations'))


@academic_bp.route('/allocations/edit/<int:id>', methods=['POST'])
@has_permission('allocations_change')
def edit_allocation(id):
    """Edit faculty allocation"""
    faculty_id_from_form = request.form.get('faculty_id')
    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id') or None
    division_id = request.form.get('division_id') or None
    semester_id = request.form.get('semester_id') or None
    course_batch_id = request.form.get('course_batch_id') or None
    allocated_hours = float(request.form.get('allocated_hours'))
    workload_percentage = float(request.form.get('workload_percentage'))
    is_primary = 1 if request.form.get('is_primary') else 0
    allocation_type = request.form.get('allocation_type')
    start_date = request.form.get('start_date') or None
    end_date = request.form.get('end_date') or None
    notes = request.form.get('notes', '')
    result = change_allocation(
        id, faculty_id_from_form, subject_id, class_id, division_id, semester_id, course_batch_id,
        allocated_hours, workload_percentage, is_primary, allocation_type, start_date, end_date, notes,
    )
    if result == 'invalid_faculty':
        flash('Invalid faculty selection.', 'danger')
    elif result:
        flash(f'Error updating allocation: {result}', 'danger')
    else:
        flash('Faculty allocation updated successfully!', 'success')
    return redirect(url_for('academic.manage_allocations'))


@academic_bp.route('/allocations/delete/<int:id>', methods=['POST'])
@has_permission('allocations_delete')
def delete_allocation(id):
    """Delete faculty allocation"""
    error = remove_allocation(id)
    if error:
        flash(f'Error deleting allocation: {error}', 'danger')
    else:
        flash('Faculty allocation deleted successfully!', 'success')
    return redirect(url_for('academic.manage_allocations'))
