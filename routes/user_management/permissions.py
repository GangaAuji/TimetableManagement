"""User Management permissions."""

from flask import Blueprint, request, redirect, url_for, flash, jsonify, session
from ui.pages import render_template
from services.user_permissions import (
    assign_permission_group,
    load_user_permission_page,
    unassign_permission_group,
)
from security import check_user_permission, grant_user_permission, has_permission, revoke_user_permission

from routes.user_management.blueprint import user_mgmt_bp

@user_mgmt_bp.route('/permissions/<int:user_id>')
@has_permission('users_change_user')
def manage_user_permissions(user_id):
    """Manage individual permissions for a specific user"""
    page = load_user_permission_page(user_id)
    if page is None:
        flash('User not found.', 'danger')
        return redirect(url_for('user_mgmt_bp.manage_users'))
    return render_template('admin/manage_user_permissions.html', **page)


@user_mgmt_bp.route('/permissions/<int:user_id>/grant', methods=['POST'])
@has_permission('users_change_user')
def grant_permission(user_id):
    """Grant a permission to a user"""
    permission_name = request.form.get('permission_name')
    department_id = request.form.get('department_id')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id')
    expires_at = request.form.get('expires_at')
    notes = request.form.get('notes')

    if not permission_name:
        return jsonify({'error': 'Permission name is required'}), 400

    department_id = int(department_id) if department_id else None
    course_id = int(course_id) if course_id else None
    class_id = int(class_id) if class_id else None
    expires_at = expires_at if expires_at else None

    success, message = grant_user_permission(
        user_id=user_id,
        permission_name=permission_name,
        department_id=department_id,
        course_id=course_id,
        class_id=class_id,
        granted_by=session.get('user_id'),
        expires_at=expires_at,
        notes=notes
    )

    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 400


@user_mgmt_bp.route('/permissions/<int:user_id>/revoke', methods=['POST'])
@has_permission('users_change_user')
def revoke_permission(user_id):
    """Revoke a permission from a user"""
    permission_name = request.form.get('permission_name')
    department_id = request.form.get('department_id')

    if not permission_name:
        return jsonify({'error': 'Permission name is required'}), 400

    department_id = int(department_id) if department_id else None

    success, message = revoke_user_permission(
        user_id=user_id,
        permission_name=permission_name,
        department_id=department_id,
        revoked_by=session.get('user_id')
    )

    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 400


@user_mgmt_bp.route('/permissions/<int:user_id>/grant_group', methods=['POST'])
@has_permission('users_change_user')
def grant_permission_group(user_id):
    """Grant a permission group to a user"""
    group_id = request.form.get('group_id')
    department_id = request.form.get('department_id')
    if not group_id:
        return jsonify({'error': 'Permission group is required'}), 400
    payload, status = assign_permission_group(user_id, group_id, department_id, session)
    return jsonify(payload), status


@user_mgmt_bp.route('/permissions/<int:user_id>/revoke_group', methods=['POST'])
@has_permission('users_change_user')
def revoke_permission_group(user_id):
    """Revoke a permission group from a user"""
    group_id = request.form.get('group_id')
    department_id = request.form.get('department_id')
    if not group_id:
        return jsonify({'error': 'Permission group is required'}), 400
    payload, status = unassign_permission_group(user_id, group_id, department_id, session)
    return jsonify(payload), status


@user_mgmt_bp.route('/permissions/bulk_grant', methods=['POST'])
@has_permission('users_change_user')
def bulk_grant_permissions():
    """Grant permissions to multiple users at once"""
    user_ids = request.form.getlist('user_ids[]') or request.form.getlist('user_ids')
    permission_names = request.form.getlist('permission_names[]') or request.form.getlist('permission_names')
    department_id = request.form.get('department_id')

    if not user_ids or not permission_names:
        return jsonify({'error': 'Users and permissions are required'}), 400

    department_id = int(department_id) if department_id else None
    granted_by = session.get('user_id')

    success_count = 0
    errors = []

    for user_id in user_ids:
        for permission_name in permission_names:
            success, message = grant_user_permission(
                user_id=int(user_id),
                permission_name=permission_name,
                department_id=department_id,
                granted_by=granted_by
            )
            if success:
                success_count += 1
            else:
                errors.append(f"User {user_id}, Permission {permission_name}: {message}")

    response = {'message': f'Successfully granted {success_count} permissions'}
    if errors:
        response['errors'] = errors

    return jsonify(response)


@user_mgmt_bp.route('/permissions/check', methods=['POST'])
@has_permission('users_view_user')
def check_permission():
    """Check if a user has a specific permission"""
    user_id = request.form.get('user_id')
    permission_name = request.form.get('permission_name')
    department_id = request.form.get('department_id')

    if not user_id or not permission_name:
        return jsonify({'error': 'User ID and permission name are required'}), 400

    department_id = int(department_id) if department_id else None

    has_perm, source, dept_restricted = check_user_permission(
        int(user_id), permission_name, department_id
    )

    return jsonify({
        'has_permission': has_perm,
        'source': source,
        'department_restricted': dept_restricted
    })
