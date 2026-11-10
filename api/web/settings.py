"""Branding settings. The save and reset actions call the existing branding service."""

import re

from flask import current_app, get_flashed_messages, request

from api.web.access import InputError, allowed, permission_denied
from api.web.responses import json_error, json_ok
from api.web.security import safe_asset_path, safe_color, safe_text
from core.scope import current_scope
from data_access import institutions as institutions_store
from data_access.branding import COLOR_SETTINGS, FILE_SETTINGS, TEXT_SETTINGS, scope_ready
from extensions import get_db_connection
from services.branding import BrandingError, allowed_file, load_branding_settings, reset_branding_settings, save_branding_settings

_MESSAGES = {
    'settings_unavailable': 'The page could not be loaded.',
    'settings_invalid': 'Check the branding fields and try again.',
    'settings_file_invalid': 'Images must be PNG, JPG, GIF, or SVG.',
    'branding_scope_unavailable': 'Apply the database upgrade before saving branding for one institution.',
    'branding_institution': 'That institution is not available.',
}
_TEXT_LIMITS = {
    'site_title': 80,
    'login_title': 80,
    'admin_title': 80,
    'student_title': 80,
    'teacher_title': 80,
    'tagline': 160,
    'copyright_text': 120,
    'welcome_message': 240,
    'support_email': 160,
    'support_phone': 30,
    'footer_text': 160,
    'maintenance_title': 120,
    'maintenance_message': 400,
}
_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')
_KNOWN = tuple(TEXT_SETTINGS) + tuple(COLOR_SETTINGS) + tuple(FILE_SETTINGS)


def register_settings_routes(blueprint):
    blueprint.add_url_rule('/settings', 'settings_list', _list, methods=['GET'])
    blueprint.add_url_rule('/settings', 'settings_save', _save, methods=['POST'])
    blueprint.add_url_rule('/settings/reset', 'settings_reset', _reset, methods=['POST'])


def _view_denied():
    return permission_denied('admin_view_settings', 'settings_unavailable', _MESSAGES['settings_unavailable'])


def _change_denied():
    return permission_denied('admin_change_settings', 'settings_unavailable', _MESSAGES['settings_unavailable'])


def _public_settings(stored):
    values = {}
    for key in _KNOWN:
        row = stored.get(key) or {}
        raw = row.get('value') if isinstance(row, dict) else ''
        if key in COLOR_SETTINGS:
            values[key] = safe_color(raw, '#000000')
        elif key in FILE_SETTINGS:
            values[key] = safe_asset_path(raw)
        else:
            values[key] = safe_text(raw or '', _TEXT_LIMITS.get(key, 160))
    return values


def _optional_institution(raw):
    if raw in (None, ''):
        return None
    if isinstance(raw, bool) or not (isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit())):
        raise InputError('settings_invalid')
    value = int(raw)
    if value < 1 or value > 1000000:
        raise InputError('settings_invalid')
    return value


def _institution_allowed(cursor, institution_id):
    row = institutions_store.fetch_institution(cursor, institution_id)
    if not row or not row.get('is_active'):
        return False
    scope = current_scope(cursor)
    if scope.multiple and not scope.allows(institution_id):
        return False
    return True


def _institution_choices(cursor):
    if not scope_ready(cursor) or not institutions_store.table_exists(cursor):
        return []
    scope = current_scope(cursor)
    rows = institutions_store.fetch_institutions(cursor, active_only=True)
    if scope.multiple and not scope.organization_wide:
        visible = set(scope.visible)
        rows = [row for row in rows if int(row['id']) in visible]
    return [
        {'id': int(row['id']), 'name': safe_text(row.get('name'), 150), 'code': safe_text(row.get('code'), 20)}
        for row in rows
    ]


def _prepare(institution_id):
    """None when this scope can be read, otherwise a JSON error. Also returns the institution choices."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if institution_id is not None:
            if not scope_ready(cursor):
                return json_error(_MESSAGES['branding_scope_unavailable'], 409, 'branding_scope_unavailable'), []
            if not _institution_allowed(cursor, institution_id):
                return json_error(_MESSAGES['branding_institution'], 403, 'branding_institution'), []
        return None, _institution_choices(cursor)
    finally:
        cursor.close()
        connection.close()


def _payload(institution_id, choices):
    return {
        'settings': _public_settings(load_branding_settings(institution_id)),
        'can_change': allowed('admin_change_settings'),
        'institution_id': institution_id,
        'institutions': choices,
    }


def _list():
    denied = _view_denied()
    if denied:
        return denied
    try:
        institution_id = _optional_institution(request.args.get('institution_id'))
        blocked, choices = _prepare(institution_id)
        if blocked:
            return blocked
        return json_ok(_payload(institution_id, choices))
    except InputError as exc:
        return reject_settings(exc.code)
    except Exception:
        current_app.logger.exception('Settings list failed')
        return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')


def reject_settings(code):
    return json_error(_MESSAGES.get(code, _MESSAGES['settings_invalid']), 400, code)


def _fields_valid():
    for key in TEXT_SETTINGS:
        value = request.form.get(key, '')
        if not isinstance(value, str) or len(value.strip()) > _TEXT_LIMITS.get(key, 160):
            return False
    for key in COLOR_SETTINGS:
        value = (request.form.get(key) or '').strip()
        if value and not _COLOR.match(value):
            return False
    for key in FILE_SETTINGS:
        uploaded = request.files.get(key)
        if uploaded and uploaded.filename and not allowed_file(uploaded.filename):
            return None
    return True


def _consume_flash():
    messages = get_flashed_messages(with_categories=True)
    return any(category == 'danger' for category, _message in messages)


def _save():
    denied = _change_denied()
    if denied:
        return denied
    try:
        institution_id = _optional_institution(request.form.get('institution_id'))
        blocked, choices = _prepare(institution_id)
        if blocked:
            return blocked
        valid = _fields_valid()
        if valid is None:
            return json_error(_MESSAGES['settings_file_invalid'], 400, 'settings_file_invalid')
        if not valid:
            return json_error(_MESSAGES['settings_invalid'], 400, 'settings_invalid')
        save_branding_settings(request.form, request.files, institution_id)
        if _consume_flash():
            return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')
        return json_ok({'saved': True, **_payload(institution_id, choices)})
    except InputError as exc:
        return reject_settings(exc.code)
    except BrandingError as exc:
        return json_error(_MESSAGES.get(exc.code, _MESSAGES['settings_unavailable']), 409, exc.code)
    except Exception:
        current_app.logger.exception('Settings save failed')
        return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')


def _reset():
    denied = _change_denied()
    if denied:
        return denied
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict) or set(payload) - {'institution_id'}:
            raise InputError('settings_invalid')
        institution_id = _optional_institution(payload.get('institution_id'))
        blocked, choices = _prepare(institution_id)
        if blocked:
            return blocked
        reset_branding_settings(institution_id)
        if _consume_flash():
            return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')
        return json_ok({'saved': True, **_payload(institution_id, choices)})
    except InputError as exc:
        return reject_settings(exc.code)
    except BrandingError as exc:
        return json_error(_MESSAGES.get(exc.code, _MESSAGES['settings_unavailable']), 409, exc.code)
    except Exception:
        current_app.logger.exception('Settings reset failed')
        return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')
