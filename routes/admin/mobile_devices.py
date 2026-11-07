"""Admin routes for managing mobile API devices and rotating keys."""

from flask import Blueprint, flash, redirect, request, session, url_for
from ui.pages import render_template

from routes.admin_utils import admin_required
from services.mobile_devices import (
    create_mobile_device as save_mobile_device,
    list_mobile_devices,
    rotate_mobile_device,
    toggle_mobile_device as set_mobile_device_active,
)

mobile_devices_bp = Blueprint("mobile_devices", __name__, url_prefix="/admin/mobile-devices")


@mobile_devices_bp.route("/", methods=["GET"])
@admin_required
def manage_mobile_devices():
    devices, users = list_mobile_devices()
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

    save_mobile_device(device_id, device_name, platform, owner_user_id, rate_limit_per_minute, session)
    return redirect(url_for("mobile_devices.manage_mobile_devices"))


@mobile_devices_bp.route("/<int:device_pk>/rotate", methods=["POST"])
@admin_required
def rotate_mobile_device_key(device_pk):
    rotate_mobile_device(device_pk, session)
    return redirect(url_for("mobile_devices.manage_mobile_devices"))


@mobile_devices_bp.route("/<int:device_pk>/toggle", methods=["POST"])
@admin_required
def toggle_mobile_device(device_pk):
    set_mobile_device_active(device_pk)
    return redirect(url_for("mobile_devices.manage_mobile_devices"))
