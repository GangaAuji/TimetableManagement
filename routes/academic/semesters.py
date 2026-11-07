"""Academic semesters."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.semesters import (
    change_semester,
    create_semester,
    list_semesters,
    remove_semester,
)

from routes.academic.blueprint import academic_bp

@academic_bp.route('/semesters')
@has_permission('semesters_view')
def manage_semesters():
    """Display Semesters Management Page"""
    semesters, academic_years, classes = list_semesters()
    return render_template('legacy/admin/manage_semesters.html',
                         semesters=semesters,
                         academic_years=academic_years,
                         classes=classes)


@academic_bp.route('/semesters/add', methods=['POST'])
@has_permission('semesters_add')
def add_semester():
    """Add new semester"""
    academic_year_id = request.form.get('academic_year_id')
    semester_number = request.form.get('semester_number')
    semester_name = request.form.get('semester_name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    class_id = request.form.get('class_id')
    is_current = 1 if request.form.get('is_current') else 0
    min_credits = request.form.get('min_credits', 18.0)
    max_credits = request.form.get('max_credits', 30.0)
    error = create_semester(
        academic_year_id, semester_number, semester_name, start_date, end_date,
        class_id, is_current, min_credits, max_credits,
    )
    if error:
        flash(f'Error adding semester: {error}', 'danger')
    else:
        flash(f'Semester {semester_name} added successfully!', 'success')
    return redirect(url_for('academic.manage_semesters'))


@academic_bp.route('/semesters/edit/<int:id>', methods=['POST'])
@has_permission('semesters_change')
def edit_semester(id):
    """Edit semester"""
    academic_year_id = request.form.get('academic_year_id')
    semester_number = request.form.get('semester_number')
    semester_name = request.form.get('semester_name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    class_id = request.form.get('class_id')
    is_current = 1 if request.form.get('is_current') else 0
    min_credits = request.form.get('min_credits')
    max_credits = request.form.get('max_credits')
    error = change_semester(
        id, academic_year_id, semester_number, semester_name, start_date, end_date,
        class_id, is_current, min_credits, max_credits,
    )
    if error:
        flash(f'Error updating semester: {error}', 'danger')
    else:
        flash(f'Semester {semester_name} updated successfully!', 'success')
    return redirect(url_for('academic.manage_semesters'))


@academic_bp.route('/semesters/delete/<int:id>', methods=['POST'])
@has_permission('semesters_delete')
def delete_semester(id):
    """Delete semester"""
    error = remove_semester(id)
    if error:
        flash(f'Error deleting semester: {error}', 'danger')
    else:
        flash('Semester deleted successfully!', 'success')
    return redirect(url_for('academic.manage_semesters'))
