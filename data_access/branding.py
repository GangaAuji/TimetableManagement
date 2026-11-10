"""Branding settings. Callers pass a cursor where noted."""

DEFAULT_SETTINGS = [
    ('site_title', 'Timetable Management System', 'text'),
    ('login_title', 'Welcome Back', 'text'),
    ('admin_title', 'Admin Dashboard', 'text'),
    ('student_title', 'Student Portal', 'text'),
    ('teacher_title', 'Teacher Portal', 'text'),
    ('tagline', 'Efficient Scheduling Made Simple', 'text'),
    ('copyright_text', '© 2025', 'text'),
    ('welcome_message', 'Welcome to our academic management system', 'text'),
    ('support_email', 'support@institution.edu', 'text'),
    ('support_phone', '+1 234 567 8900', 'text'),
    ('footer_text', 'Powered by Timetable Management System', 'text'),
    ('maintenance_title', "We'll be back shortly", 'text'),
    ('maintenance_message', 'The timetable is temporarily unavailable while maintenance is in progress.', 'text'),
    ('site_logo', '', 'image'),
    ('login_logo', '', 'image'),
    ('favicon', '', 'image'),
    ('login_background', '', 'image'),
    ('admin_login_background', '', 'image'),
    ('register_background', '', 'image'),
    ('primary_color', '#059669', 'color'),
    ('secondary_color', '#10b981', 'color'),
    ('accent_color', '#047857', 'color'),
    ('sidebar_bg', '#111827', 'color'),
    ('header_bg', '#ffffff', 'color'),
]

DEFAULT_VALUES = {
    'site_title': 'Timetable Management System',
    'login_title': 'Welcome Back',
    'admin_title': 'Admin Dashboard',
    'student_title': 'Student Portal',
    'teacher_title': 'Teacher Portal',
    'tagline': 'Efficient Scheduling Made Simple',
    'copyright_text': '© 2025',
    'welcome_message': 'Welcome to our academic management system',
    'support_email': 'support@institution.edu',
    'support_phone': '+1 234 567 8900',
    'footer_text': 'Powered by Timetable Management System',
    'maintenance_title': "We'll be back shortly",
    'maintenance_message': 'The timetable is temporarily unavailable while maintenance is in progress.',
    'primary_color': '#059669',
    'secondary_color': '#10b981',
    'accent_color': '#047857',
    'sidebar_bg': '#111827',
    'header_bg': '#ffffff',
}

TEXT_SETTINGS = [
    'site_title', 'login_title', 'admin_title',
    'student_title', 'teacher_title', 'tagline',
    'copyright_text', 'welcome_message', 'support_email',
    'support_phone', 'footer_text', 'maintenance_title', 'maintenance_message',
]

COLOR_SETTINGS = [
    'primary_color', 'secondary_color', 'accent_color',
    'sidebar_bg', 'header_bg',
]

FILE_SETTINGS = ['site_logo', 'login_logo', 'favicon', 'login_background', 'admin_login_background', 'register_background']


def insert_default_setting(cursor, key, value, setting_type):
    """Insert a default organization setting when the key is new."""
    cursor.execute(
        "INSERT IGNORE INTO branding_settings (setting_key, setting_value, setting_type) VALUES (%s, %s, %s)",
        (key, value, setting_type),
    )


def scope_ready(cursor):
    """True once branding_settings.institution_id exists. Cached for this request."""
    from flask import g, has_request_context
    if has_request_context() and hasattr(g, '_branding_scope'):
        return g._branding_scope
    cursor.execute(
        """
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'branding_settings' AND COLUMN_NAME = 'institution_id'
        LIMIT 1
        """
    )
    ready = cursor.fetchone() is not None
    if has_request_context():
        g._branding_scope = ready
    return ready


def fetch_branding_settings(cursor, institution_id=None):
    """Return branding rows for the organization, or for one institution when given."""
    if not scope_ready(cursor):
        cursor.execute("SELECT setting_key, setting_value, setting_type FROM branding_settings ORDER BY setting_key")
        return cursor.fetchall()
    if institution_id is None:
        cursor.execute(
            "SELECT setting_key, setting_value, setting_type FROM branding_settings "
            "WHERE institution_id IS NULL ORDER BY setting_key"
        )
        return cursor.fetchall()
    cursor.execute(
        "SELECT setting_key, setting_value, setting_type FROM branding_settings "
        "WHERE institution_id = %s ORDER BY setting_key",
        (institution_id,),
    )
    return cursor.fetchall()


def fetch_branding_overlay(cursor, institution_id):
    """Organization rows, plus one institution's overrides when an id is given."""
    if not scope_ready(cursor):
        cursor.execute("SELECT setting_key, setting_value, setting_type FROM branding_settings ORDER BY setting_key")
        return cursor.fetchall()
    if institution_id is None:
        cursor.execute(
            "SELECT setting_key, setting_value, setting_type, institution_id FROM branding_settings "
            "WHERE institution_id IS NULL ORDER BY setting_key"
        )
        return cursor.fetchall()
    cursor.execute(
        """
        SELECT setting_key, setting_value, setting_type, institution_id
        FROM branding_settings
        WHERE institution_id IS NULL OR institution_id = %s
        ORDER BY setting_key
        """,
        (institution_id,),
    )
    return cursor.fetchall()


def update_branding_value(cursor, value, key, institution_id=None):
    """Store one branding value on the organization row, or upsert an institution override."""
    if institution_id is not None and scope_ready(cursor):
        setting_type = next((kind for name, _default, kind in DEFAULT_SETTINGS if name == key), 'text')
        cursor.execute(
            """
            INSERT INTO branding_settings (setting_key, setting_value, setting_type, institution_id)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
            """,
            (key, value, setting_type, institution_id),
        )
        return
    if scope_ready(cursor):
        cursor.execute(
            "UPDATE branding_settings SET setting_value = %s WHERE setting_key = %s AND institution_id IS NULL",
            (value, key),
        )
        return
    cursor.execute(
        "UPDATE branding_settings SET setting_value = %s WHERE setting_key = %s",
        (value, key),
    )


def delete_institution_branding(cursor, institution_id):
    """Remove one institution's overrides so the organization branding shows through."""
    cursor.execute("DELETE FROM branding_settings WHERE institution_id = %s", (institution_id,))
