"""Public branding fields for the sign-in screen and admin shell.

Resolution is institution, then the organization row, then the built-in default.
Before sign-in, `?i=CODE` selects the institution. Afterwards the session's
institution does. A missing column keeps the organization rows only.
"""

import re

from flask import current_app, request, session

from data_access.branding import fetch_branding_overlay, scope_ready
from data_access.institutions import fetch_institution_by_code, table_exists
from extensions import get_db_connection
from api.web.responses import json_ok
from api.web.security import safe_asset_path, safe_color, safe_text

_CODE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,19}$')

PUBLIC_BRANDING_KEYS = (
    'site_title',
    'login_title',
    'admin_title',
    'tagline',
    'copyright_text',
    'welcome_message',
    'footer_text',
    'maintenance_title',
    'maintenance_message',
    'support_email',
    'support_phone',
    'site_logo',
    'login_logo',
    'favicon',
    'login_background',
    'admin_login_background',
    'register_background',
    'primary_color',
    'secondary_color',
    'accent_color',
    'sidebar_bg',
    'header_bg',
)


def _branding_value(current, key, value):
    if key in ('primary_color', 'secondary_color', 'accent_color', 'sidebar_bg', 'header_bg'):
        return safe_color(value, current)
    if key in ('site_logo', 'login_logo', 'favicon', 'login_background', 'admin_login_background', 'register_background'):
        return safe_asset_path(value)
    limits = {
        'site_title': 80,
        'login_title': 80,
        'admin_title': 80,
        'tagline': 160,
        'copyright_text': 120,
        'welcome_message': 240,
        'footer_text': 160,
        'maintenance_title': 120,
        'maintenance_message': 400,
        'support_email': 160,
        'support_phone': 30,
    }
    cleaned = safe_text(value, limits.get(key, 160))
    if key in ('support_email', 'support_phone'):
        return cleaned
    return cleaned or current


def _institution_id(cursor):
    """The institution whose branding wins, or None for the organization row."""
    if 'user_id' in session:
        chosen = session.get('institution_id')
        if isinstance(chosen, int) and not isinstance(chosen, bool) and chosen > 0:
            return chosen
        return None
    code = request.args.get('i') or ''
    if not isinstance(code, str) or not _CODE.match(code.strip()):
        return None
    if not table_exists(cursor):
        return None
    row = fetch_institution_by_code(cursor, code.strip().upper())
    if not row or not row.get('is_active'):
        return None
    return int(row['id'])


def _apply_rows(settings, rows, institution_id):
    ordered = sorted(rows, key=lambda row: 0 if row.get('institution_id') is None else 1)
    for row in ordered:
        owner = row.get('institution_id')
        if owner is not None and (institution_id is None or int(owner) != int(institution_id)):
            continue
        key = row.get('setting_key')
        if key in PUBLIC_BRANDING_KEYS and row.get('setting_value') is not None:
            settings[key] = _branding_value(settings[key], key, row['setting_value'])


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def register_branding_routes(blueprint):
    @blueprint.route('/branding', methods=['GET'])
    def branding():
        settings = {
            'site_title': 'Timetable Management System',
            'login_title': 'Welcome Back',
            'admin_title': 'Admin Dashboard',
            'tagline': 'Efficient Scheduling Made Simple',
            'copyright_text': '© 2025',
            'welcome_message': 'Welcome to our academic management system',
            'footer_text': 'Powered by Timetable Management System',
            'maintenance_title': "We'll be back shortly",
            'maintenance_message': 'The timetable is temporarily unavailable while maintenance is in progress.',
            'support_email': 'support@institution.edu',
            'support_phone': '+1 234 567 8900',
            'site_logo': '',
            'login_logo': '',
            'favicon': '',
            'login_background': '',
            'admin_login_background': '',
            'register_background': '',
            'primary_color': '#059669',
            'secondary_color': '#10b981',
            'accent_color': '#047857',
            'sidebar_bg': '#111827',
            'header_bg': '#ffffff',
            'institution_name': safe_text(current_app.config.get('INSTITUTION_NAME'), 160) or 'College Timetable System',
            'institution_short_name': safe_text(current_app.config.get('INSTITUTION_SHORT_NAME'), 40) or 'ACADEMIA',
        }

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            if _table_exists(cursor, 'branding_settings'):
                institution_id = _institution_id(cursor) if scope_ready(cursor) else None
                rows = fetch_branding_overlay(cursor, institution_id)
                wanted = set(PUBLIC_BRANDING_KEYS)
                _apply_rows(settings, [row for row in rows if row.get('setting_key') in wanted], institution_id)
        except Exception as exc:
            current_app.logger.warning('Branding API fell back to defaults: %s', exc)
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

        return json_ok(settings)
