"""Faculty-specific mobile sync routes.

Routes are registered on the shared `mobile_sync_bp` blueprint imported from
`sync_routes.py`.
"""

import json

from flask import current_app, g, jsonify, request

from database import get_db_connection
from .sync_attendance import (
    _day_of_week_from_date,
    _json_error,
    _normalize_attendance_date,
    _normalize_time_hhmmss,
    _parse_iso_datetime,
    _pick,
    _promote_log_to_faculty_attendance,
    _resolve_faculty_attendance_status,
    _resolve_faculty_record_by_reference,
    _resolve_faculty_shift_context,
    _server_time_context,
    _table_exists,
    mobile_sync_bp,
)


@mobile_sync_bp.route("/faculty-shifts/resolve", methods=["GET"])
def resolve_faculty_shift_session():
    """Resolve active faculty shift context for shift-based attendance."""
    faculty_reference = (
        request.args.get("faculty_user_id")
        or request.args.get("facultyUserId")
        or request.args.get("faculty_id")
        or request.args.get("facultyId")
    )
    if faculty_reference in (None, ""):
        return _json_error("faculty_user_id/facultyUserId is required.")

    date_value = request.args.get("date") or request.args.get("attendanceDate")
    at_time = request.args.get("at_time") or request.args.get("atTime")
    at_time_norm = _normalize_time_hhmmss(at_time)

    if at_time and not at_time_norm:
        return _json_error("Invalid at_time/atTime. Use HH:MM or HH:MM:SS.")

    time_ctx = _server_time_context()
    attendance_date = _normalize_attendance_date(date_value) or time_ctx.get("server_date_ist")
    day_of_week = _day_of_week_from_date(attendance_date)
    if day_of_week is None:
        return _json_error("Invalid date format. Use YYYY-MM-DD.")

    if not at_time_norm and attendance_date == time_ctx.get("server_date_ist"):
        at_time_norm = time_ctx.get("server_time_only_ist")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        faculty_row = _resolve_faculty_record_by_reference(cursor, faculty_reference)
        if not faculty_row:
            return _json_error("Faculty profile not found for the supplied identifier.", 404)

        shift_ctx = _resolve_faculty_shift_context(
            cursor,
            faculty_user_id=faculty_row.get("user_id"),
            day_of_week=day_of_week,
            captured_time=at_time_norm,
        )

        if not shift_ctx:
            payload = {
                "success": True,
                "resolved": False,
                "message": "No active shift availability found for the faculty on this date.",
                "faculty_id": faculty_row.get("id"),
                "facultyId": faculty_row.get("id"),
                "faculty_user_id": faculty_row.get("user_id"),
                "facultyUserId": faculty_row.get("user_id"),
                "attendance_date": attendance_date,
                "attendanceDate": attendance_date,
                "day_of_week": day_of_week,
                "dayOfWeek": day_of_week,
            }
            payload.update(time_ctx)
            return jsonify(payload)

        payload = {
            "success": True,
            "resolved": True,
            "faculty_id": faculty_row.get("id"),
            "facultyId": faculty_row.get("id"),
            "faculty_user_id": faculty_row.get("user_id"),
            "facultyUserId": faculty_row.get("user_id"),
            "attendance_date": attendance_date,
            "attendanceDate": attendance_date,
            "day_of_week": day_of_week,
            "dayOfWeek": day_of_week,
            "shift_key": shift_ctx.get("shift_key"),
            "shiftKey": shift_ctx.get("shift_key"),
            "shift_pattern_id": shift_ctx.get("shift_pattern_id"),
            "shiftPatternId": shift_ctx.get("shift_pattern_id"),
            "shift_name": shift_ctx.get("shift_name"),
            "shiftName": shift_ctx.get("shift_name"),
            "shift_code": shift_ctx.get("shift_code"),
            "shiftCode": shift_ctx.get("shift_code"),
            "shift_start_time": shift_ctx.get("shift_start_time"),
            "shiftStartTime": shift_ctx.get("shift_start_time"),
            "shift_end_time": shift_ctx.get("shift_end_time"),
            "shiftEndTime": shift_ctx.get("shift_end_time"),
        }
        payload.update(time_ctx)
        return jsonify(payload)
    finally:
        cursor.close()
        connection.close()


@mobile_sync_bp.route("/faculty-attendance/sync", methods=["POST"])
def upload_faculty_attendance_logs():
    payload = request.get_json(silent=True) or {}
    auth_details = getattr(g, "mobile_auth", {})
    time_ctx = _server_time_context()

    default_device_id = auth_details.get("device_id")
    device_id = str(_pick(payload, "device_id", "deviceId", default=default_device_id) or "").strip()
    events = _pick(payload, "events", "attendanceEvents")

    if not device_id:
        return _json_error("device_id is required.")
    if not isinstance(events, list) or not events:
        return _json_error("events must be a non-empty array.")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    processed = []
    accepted = 0
    duplicated = 0
    failed = 0

    def _record_failure(event_uuid, message):
        nonlocal failed
        failed += 1
        processed.append({"event_uuid": event_uuid, "eventUuid": event_uuid, "status": "failed", "message": message})
        current_app.logger.warning("Faculty mobile sync rejected: event_uuid=%s reason=%s", event_uuid, message)

    try:
        if not _table_exists(cursor, "faculty_attendance_logs") or not _table_exists(cursor, "faculty_attendance"):
            return _json_error(
                "Faculty attendance sync tables are missing. Run add_mobile_faculty_attendance_sync.sql migration.",
                503,
            )

        for event in events:
            event_uuid = str(_pick(event, "event_uuid", "eventUuid", default="") or "").strip()
            faculty_reference = _pick(
                event,
                "faculty_id",
                "facultyId",
                "person_id",
                "personId",
                "user_id",
                "userId",
                "marked_by_user_id",
                "markedByUserId",
            )
            attendance_date = _normalize_attendance_date(
                _pick(event, "attendance_date", "attendanceDate") or time_ctx.get("server_date_ist")
            )
            marked_by_user_id = _pick(event, "marked_by_user_id", "markedByUserId") or auth_details.get("owner_user_id")

            captured_time = _normalize_time_hhmmss(_pick(event, "captured_time", "capturedTime"))
            captured_at = None
            if not captured_time:
                try:
                    captured_value = _pick(event, "captured_at", "capturedAt")
                    captured_at = _parse_iso_datetime(captured_value) if captured_value else None
                    captured_time = captured_at.strftime("%H:%M:%S") if captured_at else None
                except Exception:
                    captured_time = None
            else:
                try:
                    captured_value = _pick(event, "captured_at", "capturedAt")
                    captured_at = _parse_iso_datetime(captured_value) if captured_value else None
                except Exception:
                    captured_at = None

            if not event_uuid:
                _record_failure(None, "event_uuid is required")
                continue

            if faculty_reference in (None, ""):
                _record_failure(event_uuid, "faculty_id/facultyId/person_id/personId is required")
                continue

            if not attendance_date:
                _record_failure(event_uuid, "attendance_date/attendanceDate is required")
                continue

            day_of_week = _day_of_week_from_date(attendance_date)
            if day_of_week is None:
                _record_failure(event_uuid, "attendance_date must be in YYYY-MM-DD format")
                continue

            faculty_row = _resolve_faculty_record_by_reference(cursor, faculty_reference)
            if not faculty_row:
                _record_failure(event_uuid, f"No faculty profile found for faculty reference={faculty_reference}")
                continue

            faculty_id = faculty_row.get("id")
            faculty_user_id = faculty_row.get("user_id")

            if marked_by_user_id is not None:
                try:
                    marked_by_user_id = int(marked_by_user_id)
                except (TypeError, ValueError):
                    marked_by_user_id = None
            if marked_by_user_id is None:
                marked_by_user_id = faculty_user_id

            shift_ctx = _resolve_faculty_shift_context(
                cursor,
                faculty_user_id=faculty_user_id,
                day_of_week=day_of_week,
                captured_time=captured_time,
            )
            if not shift_ctx:
                _record_failure(
                    event_uuid,
                    (
                        "No active shift availability found for this faculty on the selected date/day. "
                        f"faculty_user_id={faculty_user_id}, day_of_week={day_of_week}, attendance_date={attendance_date}, captured_time={captured_time}"
                    ),
                )
                continue

            status = _resolve_faculty_attendance_status(
                _pick(event, "status"),
                captured_time=captured_time,
                shift_start_time=shift_ctx.get("shift_start_time"),
            )

            try:
                cursor.execute(
                    """
                    INSERT INTO faculty_attendance_logs (
                        event_uuid,
                        device_id,
                        faculty_id,
                        faculty_user_id,
                        attendance_date,
                        day_of_week,
                        shift_key,
                        shift_pattern_id,
                        shift_name,
                        shift_code,
                        shift_start_time,
                        shift_end_time,
                        status,
                        marked_by_user_id,
                        captured_at,
                        confidence,
                        face_model,
                        detector_model,
                        remarks,
                        processing_status,
                        raw_payload
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        'pending', %s
                    )
                    """,
                    (
                        event_uuid,
                        device_id,
                        faculty_id,
                        faculty_user_id,
                        attendance_date,
                        day_of_week,
                        shift_ctx.get("shift_key") or 0,
                        shift_ctx.get("shift_pattern_id"),
                        shift_ctx.get("shift_name"),
                        shift_ctx.get("shift_code"),
                        shift_ctx.get("shift_start_time"),
                        shift_ctx.get("shift_end_time"),
                        status,
                        marked_by_user_id,
                        captured_at,
                        event.get("confidence"),
                        _pick(event, "face_model", "faceModel") or "mobilefacenet.tflite",
                        _pick(event, "detector_model", "detectorModel") or "yolov8n_float32.tflite",
                        event.get("remarks"),
                        json.dumps(event),
                    ),
                )
                log_id = cursor.lastrowid
                accepted += 1
            except Exception as insert_error:
                error_text = str(insert_error).lower()
                if "duplicate" in error_text or "event_uuid" in error_text:
                    duplicated += 1
                    processed.append({"event_uuid": event_uuid, "eventUuid": event_uuid, "status": "duplicate", "message": "Already synced"})
                    continue
                _record_failure(event_uuid, str(insert_error))
                continue

            try:
                cursor.execute("SELECT * FROM faculty_attendance_logs WHERE id = %s", (log_id,))
                log_row = cursor.fetchone()
                _promote_log_to_faculty_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE faculty_attendance_logs
                    SET processing_status = 'processed',
                        processed_at = NOW(),
                        error_message = NULL
                    WHERE id = %s
                    """,
                    (log_id,),
                )
                processed.append({"event_uuid": event_uuid, "eventUuid": event_uuid, "status": "processed", "message": "Synced"})
            except Exception as process_error:
                _record_failure(event_uuid, str(process_error))
                cursor.execute(
                    """
                    UPDATE faculty_attendance_logs
                    SET processing_status = 'failed',
                        error_message = %s
                    WHERE id = %s
                    """,
                    (str(process_error)[:500], log_id),
                )

        connection.commit()

        current_app.logger.info(
            "Faculty mobile attendance sync summary: device_id=%s total_events=%s accepted=%s duplicates=%s failed=%s",
            device_id,
            len(events),
            accepted,
            duplicated,
            failed,
        )

        if accepted == 0 and failed > 0:
            return jsonify(
                {
                    "success": False,
                    "device_id": device_id,
                    "deviceId": device_id,
                    "accepted": accepted,
                    "duplicates": duplicated,
                    "failed": failed,
                    "results": processed,
                    "error": "No faculty attendance events were accepted. Check results for rejection reasons.",
                }
            ), 400

        return jsonify(
            {
                "success": True,
                "device_id": device_id,
                "deviceId": device_id,
                "accepted": accepted,
                "duplicates": duplicated,
                "failed": failed,
                "results": processed,
            }
        )
    except Exception as e:
        connection.rollback()
        current_app.logger.error("Faculty attendance sync failed: %s", str(e))
        return _json_error("Faculty attendance sync failed", 500)
    finally:
        cursor.close()
        connection.close()


@mobile_sync_bp.route("/faculty-attendance/reprocess", methods=["POST"])
def reprocess_failed_faculty_logs():
    payload = request.get_json(silent=True) or {}
    limit = int(payload.get("limit", 100))
    if limit < 1:
        limit = 1
    if limit > 1000:
        limit = 1000

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    retried = 0
    succeeded = 0
    failed = 0

    try:
        if not _table_exists(cursor, "faculty_attendance_logs") or not _table_exists(cursor, "faculty_attendance"):
            return _json_error(
                "Faculty attendance sync tables are missing. Run add_mobile_faculty_attendance_sync.sql migration.",
                503,
            )

        cursor.execute(
            """
            SELECT *
            FROM faculty_attendance_logs
            WHERE processing_status IN ('pending', 'failed')
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        log_rows = cursor.fetchall()

        for log_row in log_rows:
            retried += 1
            try:
                _promote_log_to_faculty_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE faculty_attendance_logs
                    SET processing_status = 'processed',
                        processed_at = NOW(),
                        error_message = NULL
                    WHERE id = %s
                    """,
                    (log_row["id"],),
                )
                succeeded += 1
            except Exception as process_error:
                failed += 1
                cursor.execute(
                    """
                    UPDATE faculty_attendance_logs
                    SET processing_status = 'failed',
                        error_message = %s
                    WHERE id = %s
                    """,
                    (str(process_error)[:500], log_row["id"]),
                )

        connection.commit()

        return jsonify(
            {
                "success": True,
                "retried": retried,
                "processed": succeeded,
                "failed": failed,
            }
        )
    except Exception as e:
        connection.rollback()
        current_app.logger.error("Failed to reprocess faculty attendance logs: %s", str(e))
        return _json_error("Failed to reprocess faculty attendance logs", 500)
    finally:
        cursor.close()
        connection.close()