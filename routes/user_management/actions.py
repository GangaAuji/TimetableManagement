"""User Management actions."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify, session
from ui.pages import render_template
from utils.forms import UserForm, EmptyForm, RoleForm, UserFilterForm
from services.user_actions import (
    apply_bulk_user_action,
    export_activity_rows,
    export_user_rows,
    reset_user_password,
    toggle_user_status,
    unlock_user,
)
from security import check_user_permission, grant_user_permission, has_permission, revoke_user_permission

from routes.user_management.blueprint import user_mgmt_bp
from routes.user_management.csv_response import _csv_response

@user_mgmt_bp.route('/activity-log')
@has_permission('users_view_activity_log')
def activity_log():
    """Redirect to the new audit logs page with better filtering and security features"""
    return redirect(url_for('audit_logs.audit_logs_view'))


@user_mgmt_bp.route('/bulk', methods=['POST'])
@has_permission('users_change_user')
def bulk_users_action():
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    action = request.form.get('action')
    ids = request.form.getlist('user_ids[]') or request.form.getlist('user_ids')
    if not ids:
        return jsonify({'error': 'No users selected.'}), 400
    payload, status = apply_bulk_user_action(action, ids, request.form.get('new_password'), session)
    return jsonify(payload), status


@user_mgmt_bp.route('/reset_password/<int:user_id>', methods=['POST'])
@has_permission('users_change_user')
def reset_password(user_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    payload, status = reset_user_password(user_id, request.form.get('new_password'), session)
    return jsonify(payload), status


@user_mgmt_bp.route('/toggle_status/<int:user_id>', methods=['POST'])
@has_permission('users_change_user')
def toggle_status(user_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    payload, status = toggle_user_status(user_id, session)
    return jsonify(payload), status


@user_mgmt_bp.route('/unlock/<int:user_id>', methods=['POST'])
@has_permission('users_change_user')
def unlock(user_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    payload, status = unlock_user(user_id, session)
    return jsonify(payload), status


def _export_allowed(permission_name):
    """Return a 401 or 403 response, or None when this account may export."""
    if 'user_id' not in session:
        return 'Authentication required.', 401
    if session.get('role') == 'Super Admin':
        return None
    has_perm, _, _ = check_user_permission(session.get('user_id'), permission_name)
    if not has_perm:
        return 'You do not have permission to do that.', 403
    return None


@user_mgmt_bp.route('/export')
def export_users():
    denied = _export_allowed('users_export_data')
    if denied:
        return denied
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    rows = export_user_rows(role_filter, status_filter, search)
    return _csv_response(
        ['ID', 'Username', 'Role', 'Status', 'Last Login'],
        [[r['id'], r['username'], r['role'], r['status'], r['last_login']] for r in rows],
        'users_export.csv',
    )


@user_mgmt_bp.route('/activity-log/export')
def export_activity_log():
    denied = _export_allowed('users_view_activity_log')
    if denied:
        return denied
    rows = export_activity_rows()
    return _csv_response(
        ['Time', 'Username', 'Activity', 'Description', 'IP', 'User Agent'],
        [[r['created_at'], r['username'], r['activity_type'], r['description'], r['ip_address'], r['user_agent']] for r in rows],
        'activity_log.csv',
    )
