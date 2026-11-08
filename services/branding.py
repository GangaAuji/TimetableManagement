"""Branding settings seed, load, save, and reset."""

from datetime import datetime

from flask import current_app, flash

from core.db import transaction
from data_access.branding import (
    COLOR_SETTINGS,
    DEFAULT_SETTINGS,
    DEFAULT_VALUES,
    FILE_SETTINGS,
    TEXT_SETTINGS,
    fetch_branding_settings,
    insert_default_setting,
    update_branding_value,
)
from extensions import get_db_connection
from utils.uploads import save_uploaded_file

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def seed_branding_defaults(cursor):
    """Insert any missing default setting; existing values are never changed. Returns the number added."""
    added = 0
    for key, value, setting_type in DEFAULT_SETTINGS:
        insert_default_setting(cursor, key, value, setting_type)
        added += max(cursor.rowcount, 0)
    return added


def load_branding_settings():
    """Return branding settings keyed by name. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        settings = {}
        for row in fetch_branding_settings(cursor):
            settings[row['setting_key']] = {
                'value': row['setting_value'],
                'type': row['setting_type'],
            }
        return settings
    except Exception as exc:
        current_app.logger.error(f"Error fetching branding settings: {str(exc)}")
        return {}
    finally:
        cursor.close()
        connection.close()


def save_branding_settings(form, files):
    """Save text, color, and uploaded branding values. The connection stays open."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        for setting in TEXT_SETTINGS:
            update_branding_value(cursor, form.get(setting, '').strip(), setting)
        for setting in COLOR_SETTINGS:
            update_branding_value(cursor, form.get(setting, '').strip(), setting)
        for setting in FILE_SETTINGS:
            if setting in files:
                uploaded = files[setting]
                if uploaded and uploaded.filename != '' and allowed_file(uploaded.filename):
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    relative_path = save_uploaded_file(
                        uploaded,
                        'uploads/branding',
                        allowed_extensions=ALLOWED_EXTENSIONS,
                        name_prefix=setting,
                        timestamp=timestamp,
                    )
                    update_branding_value(cursor, relative_path, setting)
        with transaction(connection):
            pass
        flash('Branding settings updated successfully!', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error updating branding settings: {str(exc)}")
        flash('Error updating branding settings. Please try again.', 'danger')
    finally:
        cursor.close()


def reset_branding_settings():
    """Restore the default text and color values. The connection stays open."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        for key, value in DEFAULT_VALUES.items():
            update_branding_value(cursor, value, key)
        with transaction(connection):
            pass
        flash('Branding settings reset to defaults!', 'success')
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error resetting branding: {str(exc)}")
        flash('Error resetting branding settings.', 'danger')
    finally:
        cursor.close()
