"""Academic batches."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.batches import (
    change_batch,
    create_batch,
    list_batches,
    remove_batch,
)

from routes.academic.blueprint import academic_bp

@academic_bp.route('/batches')
@has_permission('batches_view')
def manage_batches():
    """Display Course Batches Management Page"""
    batches, courses, academic_years = list_batches()
    return render_template('legacy/admin/manage_batches.html',
                         batches=batches,
                         courses=courses,
                         academic_years=academic_years)


@academic_bp.route('/batches/add', methods=['POST'])
@has_permission('batches_add')
def add_batch():
    """Add new course batch"""
    course_id = request.form.get('course_id')
    batch_name = request.form.get('batch_name')
    academic_year_id = request.form.get('academic_year_id') or None
    start_year = request.form.get('start_year')
    end_year = request.form.get('end_year')
    total_students = int(request.form.get('total_students', 0))
    current_semester = int(request.form.get('current_semester', 1))
    is_active = 1 if request.form.get('is_active') else 0
    error = create_batch(
        course_id, batch_name, academic_year_id, start_year, end_year,
        total_students, current_semester, is_active,
    )
    if error:
        flash(f'Error adding batch: {error}', 'danger')
    else:
        flash(f'Batch {batch_name} added successfully!', 'success')
    return redirect(url_for('academic.manage_batches'))


@academic_bp.route('/batches/edit/<int:id>', methods=['POST'])
@has_permission('batches_change')
def edit_batch(id):
    """Edit course batch"""
    course_id = request.form.get('course_id')
    batch_name = request.form.get('batch_name')
    academic_year_id = request.form.get('academic_year_id') or None
    start_year = request.form.get('start_year')
    end_year = request.form.get('end_year')
    total_students = int(request.form.get('total_students'))
    current_semester = int(request.form.get('current_semester'))
    is_active = 1 if request.form.get('is_active') else 0
    error = change_batch(
        id, course_id, batch_name, academic_year_id, start_year, end_year,
        total_students, current_semester, is_active,
    )
    if error:
        flash(f'Error updating batch: {error}', 'danger')
    else:
        flash(f'Batch {batch_name} updated successfully!', 'success')
    return redirect(url_for('academic.manage_batches'))


@academic_bp.route('/batches/delete/<int:id>', methods=['POST'])
@has_permission('batches_delete')
def delete_batch(id):
    """Delete course batch"""
    error = remove_batch(id)
    if error:
        flash(f'Error deleting batch: {error}', 'danger')
    else:
        flash('Batch deleted successfully!', 'success')
    return redirect(url_for('academic.manage_batches'))
