"""User Management roles."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify, session
from ui.pages import render_template
from utils.forms import UserForm, EmptyForm, RoleForm, UserFilterForm
from services.roles import (
    change_role,
    copy_role,
    create_role,
    export_role_rows,
    find_role,
    list_roles,
    load_permission_name_rows,
    load_permissions_by_module,
    load_role_permission_page,
    load_role_statistics,
    permission_form_choices,
    remove_role,
    replace_role_permissions,
    update_many_role_permissions,
    users_for_role,
)
from security import check_user_permission, grant_user_permission, has_permission, revoke_user_permission

from routes.user_management.blueprint import user_mgmt_bp
from routes.user_management.csv_response import _csv_response

@user_mgmt_bp.route('/roles')
@has_permission('roles_change_role')
def manage_roles():
    form = RoleForm()
    permissions, roles, role_users = list_roles()
    form.permissions.choices = [(p['id'], f"{p['module']} - {p['name']}") for p in permissions]
    return render_template(
        'admin/manage_roles.html',
        roles=roles,
        role_users=role_users,
        form=form,
        permissions=permissions
    )


@user_mgmt_bp.route('/roles/add', methods=['POST'])
@has_permission('roles_add_role')
def add_role():
    form = RoleForm()
    form.permissions.choices = permission_form_choices()
    if form.validate_on_submit():
        name = form.name.data.strip()
        description = form.description.data
        permissions = form.permissions.data or []
        create_role(name, description, permissions, session)
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    return redirect(url_for('user_mgmt_bp.manage_roles'))


@user_mgmt_bp.route('/roles/delete/<int:role_id>', methods=['POST'])
@has_permission('roles_delete_role')
def delete_role(role_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        flash('Invalid request (CSRF).', 'danger')
        return redirect(url_for('user_mgmt_bp.manage_roles'))
    remove_role(role_id, session)
    return redirect(url_for('user_mgmt_bp.manage_roles'))


@user_mgmt_bp.route('/roles/edit/<int:role_id>', methods=['POST'])
@has_permission('roles_change_role')
def edit_role(role_id):
    form = RoleForm()
    form.permissions.choices = permission_form_choices()
    if form.validate_on_submit():
        name = form.name.data.strip()
        description = form.description.data
        permissions = form.permissions.data or []
        change_role(role_id, name, description, permissions, session)
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    return redirect(url_for('user_mgmt_bp.manage_roles'))


@user_mgmt_bp.route('/roles/get/<int:role_id>')
@has_permission('roles_change_role')
def get_role(role_id):
    payload, status = find_role(role_id)
    return jsonify(payload), status


@user_mgmt_bp.route('/roles/users/<int:role_id>')
@has_permission('users_view_user')
def get_role_users(role_id):
    return jsonify(users_for_role(role_id))


@user_mgmt_bp.route('/roles/<int:role_id>/permissions')
@has_permission('roles_change_role')
def manage_role_permissions(role_id):
    """Manage permissions for a specific role"""
    page = load_role_permission_page(role_id)
    if page is None:
        flash('Role not found.', 'danger')
        return redirect(url_for('user_mgmt_bp.manage_roles'))
    return render_template('admin/manage_role_permissions.html', **page)


@user_mgmt_bp.route('/roles/<int:role_id>/permissions/update', methods=['POST'])
@has_permission('roles_change_role')
def update_role_permissions(role_id):
    """Update permissions for a role"""
    result = replace_role_permissions(role_id, request.form.getlist('permission_ids'), session)
    if result == 'ok':
        flash('Role permissions updated successfully.', 'success')
        return redirect(url_for('user_mgmt_bp.manage_role_permissions', role_id=role_id))
    flash('Error updating role permissions.', 'danger')
    return redirect(url_for('user_mgmt_bp.manage_roles'))


@user_mgmt_bp.route('/roles/export')
@has_permission('roles_change_role')
def export_roles():
    rows = export_role_rows()
    return _csv_response(
        ['ID', 'Role', 'Description', 'Permissions'],
        [[r['id'], r['name'], r['description'] or '', r['permissions_list'] or ''] for r in rows],
        'roles.csv',
    )


@user_mgmt_bp.route('/roles/clone/<int:role_id>', methods=['POST'])
@has_permission('roles_change_role')
def clone_role(role_id):
    """Clone an existing role with all its permissions"""
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    payload, status = copy_role(role_id, session)
    return jsonify(payload), status


@user_mgmt_bp.route('/roles/bulk_permissions', methods=['POST'])
@has_permission('roles_change_role')
def bulk_permissions():
    """Add or remove permissions from multiple roles at once"""
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    action = request.form.get('action')
    role_ids = request.form.getlist('role_ids[]') or request.form.getlist('role_ids')
    perm_ids = request.form.getlist('permission_ids[]') or request.form.getlist('permission_ids')
    if not role_ids or not perm_ids:
        return jsonify({'error': 'No roles or permissions selected.'}), 400
    payload, status = update_many_role_permissions(action, role_ids, perm_ids, session)
    return jsonify(payload), status


@user_mgmt_bp.route('/roles/stats')
@has_permission('roles_change_role')
def role_stats():
    """Get statistics about roles and their usage"""
    payload, status = load_role_statistics()
    return jsonify(payload), status


@user_mgmt_bp.route('/roles/permissions_by_module')
@has_permission('roles_change_role')
def permissions_by_module():
    """Get permissions grouped by module for better UI organization"""
    payload, status = load_permissions_by_module()
    return jsonify(payload), status
