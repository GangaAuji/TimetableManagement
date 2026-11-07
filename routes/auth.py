from flask import Blueprint, request, redirect, url_for, session, flash
from ui.pages import render_template
from utils.forms import LoginForm, RegistrationForm
from extensions import get_db
from services.login import sign_in, sign_in_admin, sign_out
from services.registration import load_invitation, register_account

auth_bp = Blueprint('auth', __name__)
@auth_bp.route('/')
def home():
    if 'user_id' in session:
        return '', 204
    return '', 401

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        outcome = sign_in(
            form.username.data,
            form.password.data,
            request.remote_addr,
            request.user_agent.string,
            session,
        )
        if outcome == 'redirect':
            return redirect(url_for('auth.home'))
    return render_template('legacy/login.html', form=form)

@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = LoginForm()
    if form.validate_on_submit():
        outcome = sign_in_admin(
            form.username.data,
            form.password.data,
            request.remote_addr,
            request.user_agent.string,
            session,
        )
        if outcome == 'redirect':
            return redirect(url_for('auth.home'))
    return render_template('admin_login.html', form=form)

@auth_bp.route('/logout')
def logout():
    sign_out(session)
    flash("You have been logged out.", "success")
    return redirect(url_for('auth.login'))

@auth_bp.route('/register/<token>', methods=['GET', 'POST'])
def register(token):
    """Invitation-based registration - requires valid token from admin"""
    invitation, outcome = load_invitation(token)
    if outcome == 'login':
        return redirect(url_for('auth.login'))
    form = RegistrationForm()
    if form.validate_on_submit():
        outcome = register_account(invitation, form.username.data, form.password.data, request.form)
        if outcome == 'login':
            return redirect(url_for('auth.login'))
    return render_template('register.html', form=form, invitation=invitation, token=token)

