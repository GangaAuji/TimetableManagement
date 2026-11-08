"""Invitation registration. The route chooses the HTTP response."""

import base64
import binascii
import json
import math
import os
from datetime import datetime

from flask import current_app, flash
from werkzeug.security import generate_password_hash

from data_access.registration import (
    fetch_faculty_id_by_email,
    fetch_invitation,
    fetch_student_id_by_email,
    fetch_user_id_by_username,
    insert_faculty,
    insert_student,
    insert_user,
    mark_invitation_expired,
    mark_invitation_used,
    save_face_template,
    table_exists,
    update_profile_photo,
)
from extensions import get_db

EXPECTED_FACE_TEMPLATE_LENGTH = 192
DEFAULT_FACE_TEMPLATE_VERSION = 'mobilefacenet_192_l2_v1'


def _parse_face_template_json(raw_json):
    if not raw_json:
        return None

    try:
        parsed = json.loads(raw_json)
    except Exception:
        return None

    if not isinstance(parsed, list) or len(parsed) != EXPECTED_FACE_TEMPLATE_LENGTH:
        return None

    normalized = []
    sum_sq = 0.0
    for value in parsed:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        normalized.append(number)
        sum_sq += number * number

    norm = math.sqrt(sum_sq)
    if norm <= 0.0:
        return None

    return [value / norm for value in normalized]


def _parse_optional_float(raw_value):
    if raw_value in (None, ""):
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _meets_face_quality_threshold(quality_score):
    if quality_score is None:
        return False
    try:
        min_quality = float(current_app.config.get('FACE_TEMPLATE_MIN_QUALITY', 0.55) or 0.55)
    except (TypeError, ValueError):
        min_quality = 0.55
    return quality_score >= min_quality


def _decode_captured_face_data(data_url):
    if not data_url or not isinstance(data_url, str):
        return None

    if not data_url.startswith('data:image/'):
        return None

    parts = data_url.split(',', 1)
    if len(parts) != 2:
        return None

    header, encoded = parts
    if ';base64' not in header:
        return None

    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return None


def _generate_employee_id(user_id):
    return f"EMP{datetime.now().year}{user_id:06d}"


def describe_invitation(token):
    """Return 'open', 'used', 'expired', or 'invalid', and the invitation when it can be used."""
    db, cursor = get_db()
    invitation = fetch_invitation(cursor, token)
    if not invitation:
        return 'invalid', None
    if invitation['status'] == 'used':
        return 'used', None
    if datetime.now() > invitation['expires_at']:
        mark_invitation_expired(cursor, invitation['id'])
        db.commit()
        return 'expired', None
    return 'open', invitation


def load_invitation(token):
    """Return the invitation and 'form', or None and 'login' when the link cannot be used."""
    state, invitation = describe_invitation(token)
    if state == 'invalid':
        flash("Invalid registration link. Please contact your administrator.", "danger")
        return None, 'login'
    if state == 'used':
        flash("This invitation has already been used.", "warning")
        return None, 'login'
    if state == 'expired':
        flash("This invitation has expired. Please request a new one.", "danger")
        return None, 'login'
    return invitation, 'form'


def register_account(invitation, username, password, form):
    """Create the account. Return 'login' or 'form'."""
    db, cursor = get_db()

    if fetch_user_id_by_username(cursor, username):
        flash("Username already exists. Please choose a different one.", "danger")
        return 'form'

    if invitation['role'] == 'Student':
        existing_email = fetch_student_id_by_email(cursor, invitation['email'])
    else:
        existing_email = fetch_faculty_id_by_email(cursor, invitation['email'])

    if existing_email:
        flash("This email is already registered. Please contact your administrator.", "danger")
        return 'form'

    hashed_password = generate_password_hash(password)

    try:
        face_image_path = None
        face_capture_data = (form.get('face_capture_data') or '').strip()
        captured_bytes = _decode_captured_face_data(face_capture_data)

        raw_face_template = (
            form.get('face_template_json')
            or form.get('face_template')
            or form.get('embedding')
            or form.get('face_embedding')
            or form.get('face_embeddings')
            or form.get('embedding_vector')
            or form.get('face_vector')
            or form.get('face_descriptor')
            or ''
        ).strip()

        face_template = _parse_face_template_json(raw_face_template)
        if raw_face_template and face_template is None:
            flash(
                "Invalid face embedding format. Expected 192 numeric values from mobilefacenet.tflite.",
                "danger"
            )
            return 'form'

        if face_template and quality_score is not None and not _meets_face_quality_threshold(quality_score):
            flash(
                f"Face quality is too low ({quality_score:.3f}). Please recapture in better lighting.",
                "danger"
            )
            return 'form'

        embedding_version = (
            form.get('face_template_version')
            or form.get('embedding_version')
            or form.get('face_embedding_version')
            or DEFAULT_FACE_TEMPLATE_VERSION
        ).strip()
        quality_score = _parse_optional_float(
            form.get('face_template_quality') or form.get('quality_score')
        )

        if not face_template and current_app.config['MOBILE_FACE_EMBEDDING_ENABLED']:
            try:
                from services.face.face_embedding import get_face_pipeline

                pipeline = get_face_pipeline(
                    detector_model_path=current_app.config['YOLO_FACE_DETECTOR_MODEL_PATH'],
                    embedder_model_path=current_app.config['MOBILEFACENET_MODEL_PATH'],
                    detector_conf_threshold=current_app.config['FACE_DETECT_CONF_THRESHOLD'],
                    detector_iou_threshold=current_app.config['FACE_DETECT_IOU_THRESHOLD'],
                )
                generated = pipeline.generate(captured_bytes)
                face_template = generated.embedding
                quality_score = generated.quality_score
                embedding_version = generated.embedding_version

                if not _meets_face_quality_threshold(quality_score):
                    if quality_score is None:
                        raise ValueError("No detectable face found in capture")
                    raise ValueError(
                        f"Detected face quality too low ({quality_score:.3f}); minimum is {current_app.config['FACE_TEMPLATE_MIN_QUALITY']:.3f}"
                    )
            except Exception as generation_error:
                current_app.logger.exception(
                    "Failed to generate face template during registration: %s",
                    str(generation_error)
                )
                if current_app.config['MOBILE_FACE_EMBEDDING_REQUIRE_SUCCESS']:
                    flash(
                        (
                            "Unable to generate face embedding. Check runtime installation and model paths: "
                            f"embedder={current_app.config['MOBILEFACENET_MODEL_PATH']}, "
                            f"detector={current_app.config['YOLO_FACE_DETECTOR_MODEL_PATH']}"
                        ),
                        "danger"
                    )
                    return 'form'

        if not face_template and current_app.config['MOBILE_FACE_EMBEDDING_REQUIRE_SUCCESS']:
            flash(
                "Face template is required for recognition. Please retry capture.",
                "danger"
            )
            return 'form'

        if not captured_bytes:
            flash("Face capture is required. Please open camera and capture your face image.", "danger")
            return 'form'

        user_id = insert_user(cursor, username, hashed_password, invitation['role'])

        upload_root = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
        os.makedirs(upload_root, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        final_name = f"{user_id}_{timestamp}_captured.jpg"
        target_path = os.path.join(upload_root, final_name)

        with open(target_path, 'wb') as out_file:
            out_file.write(captured_bytes)

        face_image_path = f"uploads/profiles/{final_name}"
        update_profile_photo(cursor, face_image_path, user_id)

        if invitation['role'] == 'Student':
            admission_id = f"STU{datetime.now().strftime('%Y%m%d')}{user_id:04d}"
            insert_student(cursor, (
                user_id, user_id, admission_id, invitation['name'], invitation['email'],
                invitation['course_id'], invitation['class_id'], invitation['division_id'],
            ))
        elif invitation['role'] in ('Teacher', 'Faculty'):
            employee_id = _generate_employee_id(user_id)
            insert_faculty(cursor, (
                user_id,
                user_id,
                invitation['name'],
                invitation['email'],
                invitation['department_id'],
                employee_id,
            ))

        if face_image_path and table_exists(cursor, 'mobile_face_templates'):
            save_face_template(cursor, (
                user_id,
                json.dumps(face_template) if face_template else None,
                face_image_path,
                quality_score,
                embedding_version if face_template else None,
            ))

        mark_invitation_used(cursor, invitation['id'])

        db.commit()
        flash(f"Registration successful! You can now log in as {invitation['role']}.", "success")
        return 'login'

    except Exception as exc:
        db.rollback()
        current_app.logger.error(f"Registration error: {str(exc)}")
        flash("An error occurred during registration. Please try again.", "danger")
        return 'form'
