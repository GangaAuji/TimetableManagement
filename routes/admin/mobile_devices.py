"""Admin routes for managing mobile API devices and rotating keys."""

import secrets
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from database import get_db_connection
from routes.admin_utils import admin_required

mobile_devices_bp = Blueprint("mobile_devices", __name__, url_prefix="/admin/mobile-devices")


def _generate_device_secret():
    return secrets.token_urlsafe(48)


@mobile_devices_bp.route("/", methods=["GET"])
@admin_required
def manage_mobile_devices():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT md.id, md.device_id, md.device_name, md.platform, md.owner_user_id,
                   md.is_active, md.rate_limit_per_minute, md.last_used_at, md.created_at,
                   u.username AS owner_username
            FROM mobile_devices md
            LEFT JOIN users u ON u.id = md.owner_user_id
            ORDER BY md.created_at DESC
            """
        )
        devices = cursor.fetchall()

        cursor.execute("SELECT id, username, role FROM users WHERE status = 'active' ORDER BY username")
        users = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    new_secret = session.pop("new_mobile_device_secret", None)
    new_secret_device = session.pop("new_mobile_device_for", None)

    return render_template(
        "admin/mobile_devices.html",
        devices=devices,
        users=users,
        new_secret=new_secret,
        new_secret_device=new_secret_device,
    )


@mobile_devices_bp.route("/create", methods=["POST"])
@admin_required
def create_mobile_device():
    device_id = (request.form.get("device_id") or "").strip()
    device_name = (request.form.get("device_name") or "").strip()
    platform = (request.form.get("platform") or "").strip()
    owner_user_id = request.form.get("owner_user_id")
    rate_limit_per_minute = request.form.get("rate_limit_per_minute", type=int) or 120

    if not device_id:
        flash("Device ID is required.", "danger")
        return redirect(url_for("mobile_devices.manage_mobile_devices"))

    if rate_limit_per_minute < 10:
        flash("Rate limit must be at least 10 req/min.", "danger")
        return redirect(url_for("mobile_devices.manage_mobile_devices"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        api_key_secret = _generate_device_secret()
        cursor.execute(
            """
            INSERT INTO mobile_devices (
                device_id, device_name, platform, owner_user_id,
                api_key_secret, is_active, rate_limit_per_minute, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
            """,
            (
                device_id,
                device_name or None,
                platform or None,
                int(owner_user_id) if owner_user_id else None,
                api_key_secret,
                rate_limit_per_minute,
                session.get("user_id"),
            ),
        )
        connection.commit()

        session["new_mobile_device_secret"] = api_key_secret
        session["new_mobile_device_for"] = device_id
        flash("Mobile device created successfully.", "success")
    except Exception as e:
        connection.rollback()
        flash(f"Failed to create device: {str(e)}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("mobile_devices.manage_mobile_devices"))


@mobile_devices_bp.route("/<int:device_pk>/rotate", methods=["POST"])
@admin_required
def rotate_mobile_device_key(device_pk):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT device_id FROM mobile_devices WHERE id = %s", (device_pk,))
        row = cursor.fetchone()
        if not row:
            flash("Device not found.", "danger")
            return redirect(url_for("mobile_devices.manage_mobile_devices"))

        new_secret = _generate_device_secret()
        cursor.execute(
            "UPDATE mobile_devices SET api_key_secret = %s, updated_at = NOW() WHERE id = %s",
            (new_secret, device_pk),
        )
        connection.commit()

        session["new_mobile_device_secret"] = new_secret
        session["new_mobile_device_for"] = row["device_id"]
        flash("Device key rotated successfully.", "success")
    except Exception as e:
        connection.rollback()
        flash(f"Failed to rotate key: {str(e)}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("mobile_devices.manage_mobile_devices"))


@mobile_devices_bp.route("/<int:device_pk>/toggle", methods=["POST"])
@admin_required
def toggle_mobile_device(device_pk):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("SELECT is_active FROM mobile_devices WHERE id = %s", (device_pk,))
        row = cursor.fetchone()
        if not row:
            flash("Device not found.", "danger")
            return redirect(url_for("mobile_devices.manage_mobile_devices"))

        next_state = 0 if int(row["is_active"]) == 1 else 1
        cursor.execute("UPDATE mobile_devices SET is_active = %s, updated_at = NOW() WHERE id = %s", (next_state, device_pk))
        connection.commit()

        flash("Device status updated.", "success")
    except Exception as e:
        connection.rollback()
        flash(f"Failed to update device: {str(e)}", "danger")
    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("mobile_devices.manage_mobile_devices"))
