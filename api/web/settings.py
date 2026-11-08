"""Branding settings. The save and reset actions call the existing branding service."""

import re

from flask import current_app, get_flashed_messages, request

from api.web.access import allowed, permission_denied
from api.web.responses import json_error, json_ok
from api.web.security import safe_asset_path, safe_color, safe_text
from data_access.branding import COLOR_SETTINGS, FILE_SETTINGS, TEXT_SETTINGS
from services.branding import allowed_file, load_branding_settings, reset_branding_settings, save_branding_settings

_MESSAGES = {
    'settings_unavailable': 'The page could not be loaded.',
    'settings_invalid': 'Check the branding fields and try again.',
    'settings_file_invalid': 'Images must be PNG, JPG, GIF, or SVG.',
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


def _list():
    denied = _view_denied()
    if denied:
        return denied
    try:
        return json_ok({
            'settings': _public_settings(load_branding_settings()),
            'can_change': allowed('admin_change_settings'),
        })
    except Exception:
        current_app.logger.exception('Settings list failed')
        return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')


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
        valid = _fields_valid()
        if valid is None:
            return json_error(_MESSAGES['settings_file_invalid'], 400, 'settings_file_invalid')
        if not valid:
            return json_error(_MESSAGES['settings_invalid'], 400, 'settings_invalid')
        save_branding_settings(request.form, request.files)
        if _consume_flash():
            return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')
        return json_ok({'saved': True, 'settings': _public_settings(load_branding_settings())})
    except Exception:
        current_app.logger.exception('Settings save failed')
        return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')


def _reset():
    denied = _change_denied()
    if denied:
        return denied
    try:
        reset_branding_settings()
        if _consume_flash():
            return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')
        return json_ok({'saved': True, 'settings': _public_settings(load_branding_settings())})
    except Exception:
        current_app.logger.exception('Settings reset failed')
        return json_error(_MESSAGES['settings_unavailable'], 500, 'settings_unavailable')
