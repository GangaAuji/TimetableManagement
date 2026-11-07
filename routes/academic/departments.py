"""Academic departments."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify
from ui.pages import render_template
from security import has_permission
from services.departments import (
    change_department,
    create_department,
    list_departments,
    remove_department,
)

from routes.academic.blueprint import academic_bp

@academic_bp.route('/departments')
@has_permission('departments_view')
def manage_departments():
    """Display Departments Management Page"""
    departments = list_departments()
    return render_template('legacy/admin/manage_departments.html',
                         departments=departments)


@academic_bp.route('/departments/add', methods=['POST'])
@has_permission('departments_add')
def add_department():
    """Add new department"""
    name = request.form.get('name')
    code = request.form.get('code')
    description = request.form.get('description', '')
    head_of_department = request.form.get('head_of_department', '')
    is_active = 1 if request.form.get('is_active') else 0
    error = create_department(name, code, description, head_of_department, is_active)
    if error:
        flash(f'Error adding department: {error}', 'danger')
    else:
        flash(f'Department {name} added successfully!', 'success')
    return redirect(url_for('academic.manage_departments'))


@academic_bp.route('/departments/edit/<int:id>', methods=['POST'])
@has_permission('departments_change')
def edit_department(id):
    """Edit department"""
    name = request.form.get('name')
    code = request.form.get('code')
    description = request.form.get('description', '')
    head_of_department = request.form.get('head_of_department', '')
    is_active = 1 if request.form.get('is_active') else 0
    error = change_department(id, name, code, description, head_of_department, is_active)
    if error:
        flash(f'Error updating department: {error}', 'danger')
    else:
        flash(f'Department {name} updated successfully!', 'success')
    return redirect(url_for('academic.manage_departments'))


@academic_bp.route('/departments/delete/<int:id>', methods=['POST'])
@has_permission('departments_delete')
def delete_department(id):
    """Delete department"""
    error = remove_department(id)
    if error:
        flash(f'Error deleting department: {error}', 'danger')
    else:
        flash('Department deleted successfully!', 'success')
    return redirect(url_for('academic.manage_departments'))
