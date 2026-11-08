"""User Management users."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify, session
from ui.pages import render_template
from utils.forms import UserForm, EmptyForm, RoleForm, UserFilterForm
from services.users import (
    change_user,
    create_user,
    deactivate_user,
    find_user,
    list_users,
    normalize_role,
)
from security import check_user_permission, grant_user_permission, has_permission, revoke_user_permission

from routes.user_management.blueprint import user_mgmt_bp

@user_mgmt_bp.route('/')
@has_permission('users_view_user')
def manage_users():
    form = UserForm()
    empty_form = EmptyForm()
    filter_form = UserFilterForm()
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    users, roles = list_users(role_filter, status_filter, search)
    filter_form.role.choices = [('', 'All')] + [(r['name'], r['name']) for r in roles]
    form.role.choices = [(r['name'], r['name']) for r in roles]
    return render_template(
        'admin/manage_users.html',
        users=users,
        roles=roles,
        form=form,
        empty_form=empty_form,
        filter_form=filter_form,
        role_filter=role_filter,
        status_filter=status_filter,
        search=search
    )


@user_mgmt_bp.route('/add', methods=['POST'])
@has_permission('users_add_user')
def add_user():
    form = UserForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        role = form.role.data
        status = form.status.data or 'active'
        email = form.email.data
        create_user(username, password, role, status, email, session)
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    return redirect(url_for('user_mgmt_bp.manage_users'))


@user_mgmt_bp.route('/get/<int:user_id>')
@has_permission('users_view_user')
def get_user(user_id):
    payload, status = find_user(user_id)
    return jsonify(payload), status


@user_mgmt_bp.route('/edit/<int:user_id>', methods=['POST'])
@has_permission('users_change_user')
def edit_user(user_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def error_response(message, status_code=400):
        if is_ajax:
            return jsonify({'error': message}), status_code
        flash(message, 'danger')
        return redirect(url_for('user_mgmt_bp.manage_users'))

    # Get form data directly from request to handle extra fields not in UserForm
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    role = normalize_role(request.form.get('role', '').strip())
    status = request.form.get('status', 'active')
    email = request.form.get('email', '').strip()
    department_id = request.form.get('department_id')
    is_hod = request.form.get('is_hod') == 'on'

    if not username or len(username) < 3:
        return error_response('Username must be at least 3 characters.')

    if not role:
        return error_response('Role is required.')

    allowed_roles = {'Super Admin', 'Admin', 'Teacher', 'Student'}
    if role not in allowed_roles:
        return error_response('Invalid role selected. Use Super Admin, Admin, Teacher, or Student.')

    if password and len(password) < 8:
        return error_response('Password must be at least 8 characters.')

    result = change_user(
        user_id, username, password, role, status, email, department_id, is_hod, session,
    )
    if result == 'missing':
        return error_response('User not found.', 404)
    if result == 'protected':
        return error_response('You cannot change that account this way.', 403)
    if result == 'username':
        return error_response('Username already exists.', 409)
    if result == 'email':
        return error_response('Email already exists.', 409)
    if result == 'ok':
        if is_ajax:
            return jsonify({'message': 'User updated successfully.'})
        flash('User updated successfully.', 'success')
    else:
        if is_ajax:
            return jsonify({'error': 'Error updating user. Please try again.'}), 500
        flash('Error updating user. Please try again.', 'danger')

    return redirect(url_for('user_mgmt_bp.manage_users'))


@user_mgmt_bp.route('/delete/<int:user_id>', methods=['POST'])
@has_permission('users_delete_user')
def delete_user(user_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'CSRF token missing or invalid'}), 400
    result = deactivate_user(user_id, session)
    if result == 'missing':
        return jsonify({'error': 'User not found'}), 404
    if result == 'protected':
        return jsonify({'error': 'You cannot deactivate that account.'}), 403
    if result == 'ok':
        return jsonify({'message': 'User deactivated successfully'})
    return jsonify({'error': 'Error deleting user'}), 500
