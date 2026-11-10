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
    delete_institution_branding,
    fetch_branding_settings,
    insert_default_setting,
    scope_ready,
    update_branding_value,
)


class BrandingError(Exception):
    def __init__(self, code):
        self.code = code
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


def _rows_to_settings(rows):
    settings = {}
    for row in rows:
        settings[row['setting_key']] = {
            'value': row['setting_value'],
            'type': row['setting_type'],
        }
    return settings


def load_branding_settings(institution_id=None):
    """Return branding settings keyed by name. An institution view is the organization values with overrides on top."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if institution_id is None or not scope_ready(cursor):
            return _rows_to_settings(fetch_branding_settings(cursor, None if scope_ready(cursor) else None))
        merged = _rows_to_settings(fetch_branding_settings(cursor, None))
        merged.update(_rows_to_settings(fetch_branding_settings(cursor, institution_id)))
        return merged
    except Exception as exc:
        current_app.logger.error(f"Error fetching branding settings: {str(exc)}")
        return {}
    finally:
        cursor.close()
        connection.close()


def save_branding_settings(form, files, institution_id=None):
    """Save text, color, and uploaded branding values. The connection stays open."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if institution_id is not None and not scope_ready(cursor):
            raise BrandingError('branding_scope_unavailable')
        seed_branding_defaults(cursor)
        for setting in TEXT_SETTINGS:
            update_branding_value(cursor, form.get(setting, '').strip(), setting, institution_id)
        for setting in COLOR_SETTINGS:
            update_branding_value(cursor, form.get(setting, '').strip(), setting, institution_id)
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
                    update_branding_value(cursor, relative_path, setting, institution_id)
        with transaction(connection):
            pass
        flash('Branding settings updated successfully!', 'success')
    except BrandingError:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error updating branding settings: {str(exc)}")
        flash('Error updating branding settings. Please try again.', 'danger')
    finally:
        cursor.close()


def reset_branding_settings(institution_id=None):
    """Restore organization text and colors, or drop one institution's overrides."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if institution_id is not None:
            if not scope_ready(cursor):
                raise BrandingError('branding_scope_unavailable')
            delete_institution_branding(cursor, institution_id)
            with transaction(connection):
                pass
            flash('This institution now uses the organization branding.', 'success')
            return
        seed_branding_defaults(cursor)
        for key, value in DEFAULT_VALUES.items():
            update_branding_value(cursor, value, key, None)
        with transaction(connection):
            pass
        flash('Branding settings reset to defaults!', 'success')
    except BrandingError:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error resetting branding: {str(exc)}")
        flash('Error resetting branding settings.', 'danger')
    finally:
        cursor.close()
