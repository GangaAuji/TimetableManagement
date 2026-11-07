"""Academic years."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.academic_years import (
    change_academic_year,
    create_academic_year,
    list_academic_years,
    remove_academic_year,
)

from routes.academic.blueprint import academic_bp

@academic_bp.route('/academic-years')
@has_permission('academicyears_view')
def manage_academic_years():
    """Display Academic Years Management Page"""
    academic_years = list_academic_years()
    return render_template('legacy/admin/manage_academic_years.html',
                         academic_years=academic_years)


@academic_bp.route('/academic-years/add', methods=['POST'])
@has_permission('academicyears_add')
def add_academic_year():
    """Add new academic year"""
    name = request.form.get('name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    is_current = 1 if request.form.get('is_current') else 0
    description = request.form.get('description', '')
    error = create_academic_year(name, start_date, end_date, is_current, description)
    if error:
        flash(f'Error adding academic year: {error}', 'danger')
    else:
        flash(f'Academic Year {name} added successfully!', 'success')
    return redirect(url_for('academic.manage_academic_years'))


@academic_bp.route('/academic-years/edit/<int:id>', methods=['POST'])
@has_permission('academicyears_change')
def edit_academic_year(id):
    """Edit academic year"""
    name = request.form.get('name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    is_current = 1 if request.form.get('is_current') else 0
    description = request.form.get('description', '')
    error = change_academic_year(id, name, start_date, end_date, is_current, description)
    if error:
        flash(f'Error updating academic year: {error}', 'danger')
    else:
        flash(f'Academic Year {name} updated successfully!', 'success')
    return redirect(url_for('academic.manage_academic_years'))


@academic_bp.route('/academic-years/delete/<int:id>', methods=['POST'])
@has_permission('academicyears_delete')
def delete_academic_year(id):
    """Delete academic year"""
    error = remove_academic_year(id)
    if error:
        flash(f'Error deleting academic year: {error}', 'danger')
    else:
        flash('Academic Year deleted successfully!', 'success')
    return redirect(url_for('academic.manage_academic_years'))
