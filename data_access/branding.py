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
    ('site_logo', '', 'image'),
    ('login_logo', '', 'image'),
    ('favicon', '', 'image'),
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
    'support_phone', 'footer_text',
]

COLOR_SETTINGS = [
    'primary_color', 'secondary_color', 'accent_color',
    'sidebar_bg', 'header_bg',
]

FILE_SETTINGS = ['site_logo', 'login_logo', 'favicon']


def ensure_branding_table(cursor):
    """Create the branding table when it is missing."""
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS branding_settings (
                id INT PRIMARY KEY AUTO_INCREMENT,
                setting_key VARCHAR(100) UNIQUE NOT NULL,
                setting_value TEXT,
                setting_type VARCHAR(50) DEFAULT 'text',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)


def insert_default_setting(cursor, key, value, setting_type):
    """Insert a default setting when the key is new."""
    cursor.execute(
        "INSERT IGNORE INTO branding_settings (setting_key, setting_value, setting_type) VALUES (%s, %s, %s)",
        (key, value, setting_type),
    )


def fetch_branding_settings(cursor):
    """Return every branding setting."""
    cursor.execute("SELECT setting_key, setting_value, setting_type FROM branding_settings ORDER BY setting_key")
    return cursor.fetchall()


def update_branding_value(cursor, value, key):
    """Store one branding value."""
    cursor.execute(
        "UPDATE branding_settings SET setting_value = %s WHERE setting_key = %s",
        (value, key),
    )
