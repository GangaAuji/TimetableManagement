from flask import Blueprint, redirect, url_for, session, request, flash, jsonify
from ui.pages import render_template
from datetime import time, timedelta, datetime

from utils.forms import InvitationForm
from security import has_permission
from services.invitations import (
    create_registration_invitation,
    invitation_token,
    list_invitations,
    resend_registration_invitation,
    revoke_registration_invitation,
)


invitations_bp = Blueprint(
    'invitations',
    __name__,
    url_prefix='/admin/invitations'
)

# --- Registration Invitation Management ---
@invitations_bp.route('/')
@has_permission('users_change_user')
def manage_invitations():
    """List and manage registration invitations"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    status_filter = request.args.get('status', '', type=str)
    per_page = 15

    # Create form for CSRF protection
    form = InvitationForm()
    page_data = list_invitations(page, search, status_filter, per_page)

    return render_template('admin/manage_invitations.html',
                         form=form,
                         invitations=page_data['invitations'],
                         courses=page_data['courses'],
                         classes=page_data['classes'],
                         divisions=page_data['divisions'],
                         departments=page_data['departments'],
                         stats=page_data['stats'],
                         page=page,
                         total_pages=page_data['total_pages'],
                         search=search,
                         status_filter=status_filter)


@invitations_bp.route('/create', methods=['POST'])
@has_permission('users_add_user')
def create_invitation():
    """Generate a new registration invitation"""
    email = request.form.get('email')
    name = request.form.get('name')
    role = request.form.get('role')
    days_valid = int(request.form.get('days_valid', 7))

    if not email or not name or not role:
        flash('Email, name, and role are required.', 'danger')
        return redirect(url_for('invitations.manage_invitations'))

    course_id = request.form.get('course_id') if role == 'Student' else None
    class_id = request.form.get('class_id') if role == 'Student' else None
    division_id = request.form.get('division_id') if role == 'Student' else None
    department_id = request.form.get('department_id') if role == 'Teacher' else None
    result = create_registration_invitation(
        email, name, role, days_valid, course_id, class_id, division_id, department_id, session,
    )
    if result == 'duplicate':
        flash('A pending invitation already exists for this email.', 'warning')
    elif result == 'registered':
        flash('This email is already registered in the system.', 'warning')
    elif result == 'error':
        flash('Error creating invitation. Please try again.', 'danger')
    else:
        registration_url = url_for('auth.register', token=result, _external=True)
        flash(f'Invitation created! Registration link: {registration_url}', 'success')
    return redirect(url_for('invitations.manage_invitations'))


@invitations_bp.route('/revoke/<int:invitation_id>', methods=['POST'])
@has_permission('users_change_user')
def revoke_invitation(invitation_id):
    """Revoke/expire an invitation"""
    revoke_registration_invitation(invitation_id)
    flash('Invitation revoked successfully.', 'success')
    return redirect(url_for('invitations.manage_invitations'))


@invitations_bp.route('/resend/<int:invitation_id>', methods=['POST'])
@has_permission('users_change_user')
def resend_invitation(invitation_id):
    """Regenerate token and extend expiry for an invitation"""
    result = resend_registration_invitation(invitation_id)
    if result == 'missing':
        flash('Invitation not found.', 'danger')
        return redirect(url_for('invitations.manage_invitations'))
    if result == 'used':
        flash('Cannot resend a used invitation.', 'warning')
        return redirect(url_for('invitations.manage_invitations'))
    registration_url = url_for('auth.register', token=result, _external=True)
    flash(f'Invitation regenerated! New link: {registration_url}', 'success')
    return redirect(url_for('invitations.manage_invitations'))


@invitations_bp.route('/copy_link/<int:invitation_id>')
@has_permission('users_change_user')
def copy_invitation_link(invitation_id):
    """Get invitation link for copying"""
    token = invitation_token(invitation_id)
    if token:
        registration_url = url_for('auth.register', token=token, _external=True)
        return jsonify({'url': registration_url})
    return jsonify({'error': 'Invitation not found'}), 404
