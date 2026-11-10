from flask import Blueprint, current_app, flash, get_flashed_messages, jsonify, redirect, request, session, url_for
from ui.pages import render_template
from utils.forms import LoginForm, RegistrationForm
from extensions import get_db
from services.login import finish_pending, sign_in, sign_in_admin, sign_out
from services.registration import load_invitation, register_account

auth_bp = Blueprint('auth', __name__)
@auth_bp.route('/')
def home():
    if 'user_id' in session:
        return '', 204
    return '', 401

def _wants_json():
    accept = request.headers.get('Accept') or ''
    return 'application/json' in accept and 'text/html' not in accept


def _failure_message():
    messages = get_flashed_messages()
    if messages:
        return messages[-1]
    return 'Sign in failed. Check your username and password.'


def _login_result(outcome, form, template):
    """HTML form sign-in stays a redirect. The React page asks for JSON and may get a second step."""
    if _wants_json():
        if outcome == 'redirect':
            return jsonify({'ok': True})
        if outcome in ('totp', 'enroll'):
            try:
                _db, cursor = get_db()
                from services.second_factor import pending_view
                payload = pending_view(session, cursor)
            except Exception:
                current_app.logger.exception('Second factor status failed')
                payload = {'pending': outcome}
            return jsonify({'ok': True, **payload})
        return jsonify({'ok': False, 'message': _failure_message()}), 401
    if outcome == 'redirect':
        return redirect(url_for('auth.home'))
    if outcome in ('totp', 'enroll'):
        flash('Continue on the sign-in page and enter the code from your authenticator app.', 'warning')
    return render_template(template, form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    outcome = None
    if form.validate_on_submit():
        outcome = sign_in(
            form.username.data,
            form.password.data,
            request.remote_addr,
            request.user_agent.string,
            session,
        )
    return _login_result(outcome, form, 'legacy/login.html')

@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = LoginForm()
    outcome = None
    if form.validate_on_submit():
        outcome = sign_in_admin(
            form.username.data,
            form.password.data,
            request.remote_addr,
            request.user_agent.string,
            session,
        )
    return _login_result(outcome, form, 'admin_login.html')


@auth_bp.route('/login/pending', methods=['GET'])
def login_pending():
    """The code step after a correct password. Empty when there is nothing waiting."""
    if session.get('user_id'):
        return jsonify({'pending': None})
    try:
        _db, cursor = get_db()
        from services.second_factor import pending_view
        payload = pending_view(session, cursor)
    except Exception:
        current_app.logger.exception('Second factor status failed')
        payload = {'pending': None}
    return jsonify(payload)


@auth_bp.route('/login/second-factor', methods=['POST'])
def login_second_factor():
    """Check the authenticator or recovery code and only then open the session."""
    if not _wants_json():
        return redirect(url_for('auth.login'))
    code = request.form.get('code', '')
    if not isinstance(code, str):
        code = ''
    result = finish_pending(code.strip(), request.remote_addr, request.user_agent.string, session)
    body = {'ok': bool(result.get('ok'))}
    if result.get('message'):
        body['message'] = result['message']
    if result.get('cleared'):
        body['cleared'] = True
    if result.get('ok') and result.get('recovery_codes'):
        body['recovery_codes'] = result['recovery_codes']
    return jsonify(body), (200 if body['ok'] else 401)

@auth_bp.route('/logout')
def logout():
    sign_out(session)
    flash("You have been logged out.", "success")
    return redirect(url_for('auth.login'))

_SSO_MESSAGES = {
    'sso_disabled': 'Single sign-on is not enabled.',
    'sso_incomplete': 'Single sign-on is not fully configured. Contact the administrator.',
    'sso_provider_unavailable': 'The sign-in provider could not be reached. Try again later.',
    'sso_provider_denied': 'The sign-in provider did not complete the sign-in.',
    'sso_state_mismatch': 'The sign-in request expired or did not start here. Try again.',
    'sso_token_failed': 'The sign-in provider rejected the request. Contact the administrator.',
    'sso_token_invalid': 'The sign-in provider returned an invalid token. Contact the administrator.',
    'sso_email_unverified': 'Your provider account has no verified email address.',
    'sso_domain_not_allowed': 'Your email domain is not allowed to sign in here.',
    'sso_no_account': 'No staff account matches your sign-in. Contact the administrator.',
    'sso_account_locked': 'Your account has been locked. Contact the administrator.',
    'sso_account_inactive': 'Your account has been deactivated. Contact the administrator.',
    'sso_second_factor': 'The authenticator could not be started. Contact the administrator.',
}


def _sso_redirect_uri():
    from flask import current_app
    base = current_app.config.get('SSO_REDIRECT_BASE_URL') or request.url_root.rstrip('/')
    return f'{base}/auth/sso/callback'


def _sso_failed(exc):
    from services.sso import log_failure
    log_failure(exc)
    flash(_SSO_MESSAGES.get(exc.code, 'Sign in failed.'), 'danger')
    return redirect(f'/admin/login?sso_error={exc.code}')


@auth_bp.route('/auth/sso/start')
def sso_start():
    """Send the browser to the configured OpenID Connect provider."""
    from services.sso import SsoError, begin
    if 'user_id' in session:
        return redirect('/')
    db, cursor = get_db()
    try:
        return redirect(begin(cursor, session, _sso_redirect_uri()))
    except SsoError as exc:
        return _sso_failed(exc)
    except Exception as exc:
        from flask import current_app
        current_app.logger.exception('SSO start failed')
        return _sso_failed(SsoError('sso_provider_unavailable', str(exc)))


@auth_bp.route('/auth/sso/callback')
def sso_callback():
    """The provider sends the browser back here with a code; verify it and open the session."""
    from services.sso import SsoError, complete, landing_path
    db, cursor = get_db()
    try:
        user = complete(cursor, session, request.args, _sso_redirect_uri(), ip_address=request.remote_addr, user_agent=request.user_agent.string)
        db.commit()
    except SsoError as exc:
        db.rollback()
        return _sso_failed(exc)
    except Exception as exc:
        db.rollback()
        current_app.logger.exception('SSO callback failed')
        return _sso_failed(SsoError('sso_provider_unavailable', str(exc)))
    pending = session.get('pending_2fa')
    if isinstance(pending, dict) and pending.get('step') in ('totp', 'enroll'):
        target = '/admin/login' if pending.get('kind') == 'admin' else '/'
        return redirect(f'{target}?pending=1')
    return redirect(landing_path(user))


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

