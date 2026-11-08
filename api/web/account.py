"""Signed-in account profile and password change."""

from flask import current_app, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import get_db_connection
from api.web.access import InputError, body, close, iso_date, optional_text, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_asset_path, safe_stamp, safe_text
from security import log_activity
from services.profile import load_profile, save_profile

_MESSAGES = {
    'invalid_body': 'The profile could not be saved.',
    'account_unavailable': 'The page could not be loaded.',
    'account_email_invalid': 'Enter a valid email address.',
    'account_phone_invalid': 'Phone must be 20 characters or fewer.',
    'account_bio_invalid': 'Bio must be 500 characters or fewer.',
    'account_address_invalid': 'Address must be 500 characters or fewer.',
    'account_birth_invalid': 'Enter a valid birth date.',
    'account_photo_invalid': 'Profile photo must be a PNG, JPG, or GIF.',
    'account_password_invalid': 'Enter the current password and a new password of 8 to 128 characters.',
    'account_password_mismatch': 'The current password is incorrect.',
}


def register_account_routes(blueprint):
    blueprint.add_url_rule('/account', 'account_view', _view, methods=['GET'])
    blueprint.add_url_rule('/account', 'account_update', _update, methods=['PUT'])
    blueprint.add_url_rule('/account', 'account_update_form', _update_form, methods=['POST'])
    blueprint.add_url_rule('/account/password', 'account_password', _password, methods=['POST'])


def _date_text(value):
    if value is None or value == '':
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()[:10]
    return safe_text(value, 10)


def _profile_payload(user):
    photo = safe_asset_path(user.get('profile_photo')) or 'default-avatar.svg'
    return {
        'username': safe_text(user.get('username'), 50),
        'role': safe_text(user.get('role'), 50),
        'email': safe_text(user.get('email') or '', 100),
        'phone': safe_text(user.get('phone') or '', 20),
        'address': safe_text(user.get('address') or '', 500),
        'bio': safe_text(user.get('bio') or '', 500),
        'status': safe_text(user.get('status') or 'active', 20),
        'department_name': safe_text(user.get('department_name') or '', 100),
        'created_at': safe_stamp(user.get('created_at')),
        'last_login': safe_stamp(user.get('last_login')),
        'date_of_birth': _date_text(user.get('date_of_birth')),
        'profile_photo': photo,
    }


def _kept(current, source, key):
    if key not in source:
        value = current.get(key)
        if key == 'date_of_birth':
            return _date_text(value) or None
        return value or None
    text = source.get(key)
    return None if text in (None, '') else text


def _store_profile(email, phone, address, bio, date_of_birth, photo_file):
    result = save_profile(session, email, phone, address, bio, date_of_birth, photo_file)
    if result == 'invalid_file':
        return json_error(_MESSAGES['account_photo_invalid'], 400, 'account_photo_invalid')
    if result != 'ok':
        current_app.logger.error('Account update failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    photo = safe_asset_path(session.get('profile_photo')) or 'default-avatar.svg'
    return json_ok({'saved': True, 'profile_photo': photo})


def _signed_in():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    return None


def _view():
    denied = _signed_in()
    if denied:
        return denied
    try:
        user = load_profile(session)
    except Exception:
        current_app.logger.exception('Account view failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    if not user:
        return json_error(_MESSAGES['account_unavailable'], 404, 'account_unavailable')
    return json_ok(_profile_payload(user))


def _fields(source, current):
    email = optional_text(_kept(current, source, 'email') or '', 100, 'account_email_invalid')
    if email and '@' not in email:
        raise InputError('account_email_invalid')
    phone = optional_text(_kept(current, source, 'phone') or '', 20, 'account_phone_invalid') or None
    address = optional_text(_kept(current, source, 'address') or '', 500, 'account_address_invalid') or None
    bio = optional_text(_kept(current, source, 'bio') or '', 500, 'account_bio_invalid') or None
    birth = _kept(current, source, 'date_of_birth')
    date_of_birth = iso_date(birth, 'account_birth_invalid', required=False) if birth else None
    return email, phone, address, bio, date_of_birth


def _update():
    denied = _signed_in()
    if denied:
        return denied
    try:
        current = load_profile(session)
        if not current:
            return json_error(_MESSAGES['account_unavailable'], 404, 'account_unavailable')
        payload = body(frozenset(('email', 'phone', 'address', 'bio', 'date_of_birth')))
        return _store_profile(*_fields(payload, current), None)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Account update failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')


def _update_form():
    denied = _signed_in()
    if denied:
        return denied
    try:
        current = load_profile(session)
        if not current:
            return json_error(_MESSAGES['account_unavailable'], 404, 'account_unavailable')
        source = {key: request.form.get(key) for key in ('email', 'phone', 'address', 'bio', 'date_of_birth') if key in request.form}
        photo = request.files.get('profile_photo') if 'profile_photo' in request.files else None
        return _store_profile(*_fields(source, current), photo)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Account update failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')


def _password():
    denied = _signed_in()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(frozenset(('current_password', 'new_password')))
        current_password = payload.get('current_password')
        new_password = payload.get('new_password')
        if not isinstance(current_password, str) or not isinstance(new_password, str):
            raise InputError('account_password_invalid')
        if len(new_password) < 8 or len(new_password) > 128 or len(current_password) > 128:
            raise InputError('account_password_invalid')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT password FROM users WHERE id = %s', (session.get('user_id'),))
        row = cursor.fetchone()
        if not row or not check_password_hash(row.get('password') or '', current_password):
            return json_error(_MESSAGES['account_password_mismatch'], 400, 'account_password_mismatch')
        cursor.execute(
            'UPDATE users SET password = %s WHERE id = %s',
            (generate_password_hash(new_password), session.get('user_id')),
        )
        log_activity(session.get('user_id'), 'change_password', 'Changed password', cursor=cursor)
        connection.commit()
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Password change failed')
        return json_error(_MESSAGES['account_unavailable'], 500, 'account_unavailable')
    finally:
        close(cursor, connection)
