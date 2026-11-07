from flask import Blueprint, request, redirect, url_for, flash, session
from ui.pages import render_template
from security import login_required

from services.profile import change_password as save_new_password
from services.profile import load_profile, load_profile_form, save_profile

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')


@profile_bp.route('/')
@login_required
def view_profile():
    """View current user's profile"""
    user = load_profile(session)
    if user is None:
        flash('User not found', 'error')
        return redirect(url_for('auth.login'))
    return render_template('profile/user_profile.html', user=user)


@profile_bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit current user's profile"""
    if request.method == 'POST':
        photo_file = request.files['profile_photo'] if 'profile_photo' in request.files else None
        result = save_profile(
            session,
            request.form.get('email'),
            request.form.get('phone'),
            request.form.get('address'),
            request.form.get('bio'),
            request.form.get('date_of_birth'),
            photo_file,
        )
        if result == 'invalid_file':
            flash('Invalid file type. Only PNG, JPG, JPEG, and GIF images are allowed.', 'danger')
            return redirect(url_for('profile.view_profile'))
        if result == 'ok':
            flash('Profile updated successfully', 'success')
            return redirect(url_for('profile.view_profile'))
        flash(f'Error updating profile: {result}', 'error')

    user = load_profile_form(session)
    if user is None:
        flash('User not found', 'error')
        return redirect(url_for('auth.login'))
    return render_template('profile/edit.html', user=user)


@profile_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('profile.change_password'))
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return redirect(url_for('profile.change_password'))
        result = save_new_password(session, current_password, new_password)
        if result == 'wrong':
            flash('Current password is incorrect', 'error')
            return redirect(url_for('profile.change_password'))
        if result == 'ok':
            flash('Password changed successfully', 'success')
            return redirect(url_for('profile.view_profile'))
        flash(f'Error changing password: {result}', 'error')
    return render_template('profile/change_password.html')
