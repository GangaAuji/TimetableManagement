"""Public branding fields for the sign-in screen and admin shell."""

from flask import current_app

from extensions import get_db_connection
from api.web.responses import json_ok
from api.web.security import safe_asset_path, safe_color, safe_text

PUBLIC_BRANDING_KEYS = (
    'site_title',
    'login_title',
    'admin_title',
    'tagline',
    'copyright_text',
    'welcome_message',
    'footer_text',
    'site_logo',
    'login_logo',
    'favicon',
    'primary_color',
    'secondary_color',
    'accent_color',
    'sidebar_bg',
    'header_bg',
)


def _branding_value(current, key, value):
    if key in ('primary_color', 'secondary_color', 'accent_color', 'sidebar_bg', 'header_bg'):
        return safe_color(value, current)
    if key in ('site_logo', 'login_logo', 'favicon'):
        return safe_asset_path(value)
    limits = {
        'site_title': 80,
        'login_title': 80,
        'admin_title': 80,
        'tagline': 160,
        'copyright_text': 120,
        'welcome_message': 240,
        'footer_text': 160,
    }
    cleaned = safe_text(value, limits.get(key, 160))
    return cleaned or current


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
            'site_logo': '',
            'login_logo': '',
            'favicon': '',
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
                cursor.execute(
                    "SELECT setting_key, setting_value FROM branding_settings WHERE setting_key IN ({})".format(
                        ','.join(['%s'] * len(PUBLIC_BRANDING_KEYS))
                    ),
                    PUBLIC_BRANDING_KEYS,
                )
                for row in cursor.fetchall():
                    key = row.get('setting_key')
                    if key in PUBLIC_BRANDING_KEYS and row.get('setting_value') is not None:
                        settings[key] = _branding_value(settings[key], key, row['setting_value'])
        except Exception as exc:
            current_app.logger.warning('Branding API fell back to defaults: %s', exc)
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()

        return json_ok(settings)
