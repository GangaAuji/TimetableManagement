"""Mobile device registration and key rotation."""

import secrets

from flask import flash

from data_access.mobile_devices import (
    fetch_active_users,
    fetch_device_active,
    fetch_device_id,
    fetch_mobile_devices,
    insert_mobile_device,
    update_device_active,
    update_device_secret,
)
from extensions import get_db_connection


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _secret():
    return secrets.token_urlsafe(48)


def list_mobile_devices():
    """Return devices and active users. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        return fetch_mobile_devices(cursor), fetch_active_users(cursor)
    finally:
        cursor.close()
        connection.close()


def create_mobile_device(device_id, device_name, platform, owner_user_id, rate_limit, session):
    """Create a device. Return the new secret, or None when the save fails."""
    connection, cursor = _cursor()
    try:
        api_key_secret = _secret()
        insert_mobile_device(cursor, (
            device_id,
            device_name or None,
            platform or None,
            int(owner_user_id) if owner_user_id else None,
            api_key_secret,
            rate_limit,
            session.get("user_id"),
        ))
        connection.commit()
        session["new_mobile_device_secret"] = api_key_secret
        session["new_mobile_device_for"] = device_id
        flash("Mobile device created successfully.", "success")
        return api_key_secret
    except Exception as exc:
        connection.rollback()
        flash(f"Failed to create device: {str(exc)}", "danger")
        return None
    finally:
        cursor.close()
        connection.close()


def rotate_mobile_device(device_pk, session):
    """Replace a device secret. A missing device does not roll back."""
    connection, cursor = _cursor()
    try:
        row = fetch_device_id(cursor, device_pk)
        if not row:
            flash("Device not found.", "danger")
            return 'missing'
        new_secret = _secret()
        update_device_secret(cursor, new_secret, device_pk)
        connection.commit()
        session["new_mobile_device_secret"] = new_secret
        session["new_mobile_device_for"] = row["device_id"]
        flash("Device key rotated successfully.", "success")
        return 'ok'
    except Exception as exc:
        connection.rollback()
        flash(f"Failed to rotate key: {str(exc)}", "danger")
        return 'error'
    finally:
        cursor.close()
        connection.close()


def toggle_mobile_device(device_pk):
    """Flip a device between active and inactive."""
    connection, cursor = _cursor()
    try:
        row = fetch_device_active(cursor, device_pk)
        if not row:
            flash("Device not found.", "danger")
            return 'missing'
        next_state = 0 if int(row["is_active"]) == 1 else 1
        update_device_active(cursor, next_state, device_pk)
        connection.commit()
        flash("Device status updated.", "success")
        return 'ok'
    except Exception as exc:
        connection.rollback()
        flash(f"Failed to update device: {str(exc)}", "danger")
        return 'error'
    finally:
        cursor.close()
        connection.close()
