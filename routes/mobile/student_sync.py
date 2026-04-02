"""Student-specific mobile sync routes.

Routes are registered on the shared `mobile_sync_bp` blueprint imported from
`sync_routes.py`.
"""

import json
from datetime import datetime

from flask import current_app, g, jsonify, request

from database import get_db_connection
from .sync_attendance import (
    ALLOWED_STATUSES,
    _has_active_timetable_for_group,
    _json_error,
    _normalize_attendance_date,
    _normalize_status,
    _normalize_time_hhmmss,
    _parse_iso_datetime,
    _pick,
    _promote_log_to_attendance,
    _resolve_faculty_record_by_reference,
    _resolve_recent_timetable_for_student,
    _resolve_student_class_division,
    _resolve_student_id_from_event,
    _resolve_timetable_faculty_user_id,
    _resolve_timetable_id_from_event,
    _resolve_timetable_id_relaxed,
    _resolve_timetable_record,
    _seconds_from_hhmmss,
    _server_time_context,
    mobile_sync_bp,
)


@mobile_sync_bp.route("/timetable", methods=["GET"])
def sync_timetable():
    date_value = request.args.get("date") or request.args.get("attendanceDate")
    at_time = request.args.get("at_time") or request.args.get("atTime")
    at_time_norm = _normalize_time_hhmmss(at_time)
    faculty_user_id = request.args.get("faculty_user_id", type=int)
    if faculty_user_id is None:
        faculty_user_id = request.args.get("facultyUserId", type=int)

    if not date_value:
        return _json_error("date query param is required (YYYY-MM-DD).")

    try:
        schedule_date = datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError:
        return _json_error("Invalid date format. Use YYYY-MM-DD.")

    if at_time and not at_time_norm:
        return _json_error("Invalid at_time/atTime. Use HH:MM or HH:MM:SS.")

    day_name = schedule_date.strftime("%A")
    time_ctx = _server_time_context()
    reference_time = at_time_norm
    if not reference_time and schedule_date.isoformat() == time_ctx.get("server_date_ist"):
        reference_time = time_ctx.get("server_time_only_ist")
    reference_seconds = _seconds_from_hhmmss(reference_time) if reference_time else None

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        where_parts = ["t.day_of_week = %s", "COALESCE(t.is_active, 1) = 1"]
        params = [day_name]

        if faculty_user_id:
            where_parts.append("t.faculty_id = %s")
            params.append(faculty_user_id)

        cursor.execute(
            f"""
            SELECT
                t.id AS timetable_id,
                t.faculty_id AS faculty_user_id,
                t.subject_id,
                s.name AS subject_name,
                t.course_id,
                c.name AS class_name,
                t.class_id,
                d.name AS division_name,
                t.division_id,
                t.start_time,
                t.end_time,
                t.day_of_week
            FROM timetable t
            JOIN subjects s ON s.id = t.subject_id
            JOIN classes c ON c.id = t.class_id
            JOIN divisions d ON d.id = t.division_id
            WHERE {" AND ".join(where_parts)}
            ORDER BY t.start_time
            """,
            tuple(params),
        )
        lectures = cursor.fetchall()

        response_rows = []
        active_rows = []
        for lecture in lectures:
            cursor.execute(
                """
                SELECT id, user_id, name, roll_number, admission_id
                FROM students
                WHERE course_id = %s
                  AND class_id = %s
                  AND division_id = %s
                  AND COALESCE(is_active, 1) = 1
                ORDER BY roll_number, name
                """,
                (lecture["course_id"], lecture["class_id"], lecture["division_id"]),
            )
            students = cursor.fetchall()

            start_time_str = str(lecture["start_time"])
            end_time_str = str(lecture["end_time"])
            start_seconds = _seconds_from_hhmmss(start_time_str)
            end_seconds = _seconds_from_hhmmss(end_time_str)
            is_active_now = bool(
                reference_seconds is not None
                and start_seconds is not None
                and end_seconds is not None
                and start_seconds <= reference_seconds <= end_seconds
            )

            row_payload = {
                "timetable_id": lecture["timetable_id"],
                "timetableId": lecture["timetable_id"],
                "id": lecture["timetable_id"],
                "faculty_user_id": lecture["faculty_user_id"],
                "facultyUserId": lecture["faculty_user_id"],
                "subject_id": lecture["subject_id"],
                "subjectId": lecture["subject_id"],
                "subject_name": lecture["subject_name"],
                "subjectName": lecture["subject_name"],
                "course_id": lecture["course_id"],
                "courseId": lecture["course_id"],
                "class_id": lecture["class_id"],
                "classId": lecture["class_id"],
                "class_name": lecture["class_name"],
                "className": lecture["class_name"],
                "division_id": lecture["division_id"],
                "divisionId": lecture["division_id"],
                "division_name": lecture["division_name"],
                "divisionName": lecture["division_name"],
                "day_of_week": lecture["day_of_week"],
                "dayOfWeek": lecture["day_of_week"],
                "start_time": start_time_str,
                "startTime": start_time_str,
                "start": start_time_str,
                "end_time": end_time_str,
                "endTime": end_time_str,
                "end": end_time_str,
                "students": students,
                "roster": students,
                "is_active_now": is_active_now,
                "isActiveNow": is_active_now,
            }
            response_rows.append(row_payload)
            if is_active_now:
                active_rows.append(row_payload)

        next_row = None
        if reference_seconds is not None:
            upcoming = []
            for row in response_rows:
                start_seconds = _seconds_from_hhmmss(row.get("start_time"))
                if start_seconds is not None and start_seconds >= reference_seconds:
                    upcoming.append((start_seconds, row))
            if upcoming:
                upcoming.sort(key=lambda item: item[0])
                next_row = upcoming[0][1]

        response_payload = {
            "success": True,
            "date": schedule_date.isoformat(),
            "attendanceDate": schedule_date.isoformat(),
            "day_of_week": day_name,
            "dayOfWeek": day_name,
            "count": len(response_rows),
            "lectures": response_rows,
            "sessions": response_rows,
            "entries": response_rows,
            "timetables": response_rows,
            "reference_time": reference_time,
            "referenceTime": reference_time,
            "active_lectures": active_rows,
            "activeLectures": active_rows,
            "active_count": len(active_rows),
            "activeCount": len(active_rows),
            "next_lecture": next_row,
            "nextLecture": next_row,
        }
        response_payload.update(time_ctx)
        return jsonify(response_payload)
    finally:
        cursor.close()
        connection.close()


@mobile_sync_bp.route("/timetable/resolve", methods=["GET"])
def resolve_timetable_session():
    """Resolve a single timetable session for attendance marking.

    Supports both snake_case and camelCase query parameters.
    """
    date_value = request.args.get("date") or request.args.get("attendanceDate")
    faculty_user_id = request.args.get("faculty_user_id", type=int)
    if faculty_user_id is None:
        faculty_user_id = request.args.get("facultyUserId", type=int)

    subject_id = request.args.get("subject_id", type=int)
    if subject_id is None:
        subject_id = request.args.get("subjectId", type=int)

    class_id = request.args.get("class_id", type=int)
    if class_id is None:
        class_id = request.args.get("classId", type=int)

    division_id = request.args.get("division_id", type=int)
    if division_id is None:
        division_id = request.args.get("divisionId", type=int)

    at_time = request.args.get("at_time") or request.args.get("atTime")
    at_time_norm = _normalize_time_hhmmss(at_time)

    if not date_value:
        return _json_error("date or attendanceDate query param is required (YYYY-MM-DD).")

    try:
        schedule_date = datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError:
        return _json_error("Invalid date format. Use YYYY-MM-DD.")

    day_name = schedule_date.strftime("%A")

    if at_time and not at_time_norm:
        return _json_error("Invalid at_time/atTime. Use HH:MM or HH:MM:SS.")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        where_parts = ["t.day_of_week = %s", "COALESCE(t.is_active, 1) = 1"]
        params = [day_name]

        if faculty_user_id:
            where_parts.append("t.faculty_id = %s")
            params.append(faculty_user_id)
        if subject_id:
            where_parts.append("t.subject_id = %s")
            params.append(subject_id)
        if class_id:
            where_parts.append("t.class_id = %s")
            params.append(class_id)
        if division_id:
            where_parts.append("t.division_id = %s")
            params.append(division_id)
        if at_time_norm:
            where_parts.append("%s BETWEEN t.start_time AND t.end_time")
            params.append(at_time_norm)

        cursor.execute(
            f"""
            SELECT
                t.id AS timetable_id,
                t.faculty_id AS faculty_user_id,
                t.subject_id,
                s.name AS subject_name,
                t.course_id,
                t.class_id,
                c.name AS class_name,
                t.division_id,
                d.name AS division_name,
                t.start_time,
                t.end_time,
                t.day_of_week
            FROM timetable t
            JOIN subjects s ON s.id = t.subject_id
            JOIN classes c ON c.id = t.class_id
            JOIN divisions d ON d.id = t.division_id
            WHERE {" AND ".join(where_parts)}
            ORDER BY t.start_time
            LIMIT 5
            """,
            tuple(params),
        )
        matches = cursor.fetchall()

        if not matches:
            response_payload = {
                "success": True,
                "resolved": False,
                "message": "No timetable session matched the given filters.",
                "filters": {
                    "date": schedule_date.isoformat(),
                    "dayOfWeek": day_name,
                    "facultyUserId": faculty_user_id,
                    "subjectId": subject_id,
                    "classId": class_id,
                    "divisionId": division_id,
                    "atTime": at_time_norm,
                },
                "candidates": [],
            }
            response_payload.update(_server_time_context())
            return jsonify(response_payload)

        resolved = matches[0]
        candidates = []
        for row in matches:
            candidates.append(
                {
                    "timetable_id": row["timetable_id"],
                    "timetableId": row["timetable_id"],
                    "id": row["timetable_id"],
                    "faculty_user_id": row["faculty_user_id"],
                    "facultyUserId": row["faculty_user_id"],
                    "subject_id": row["subject_id"],
                    "subjectId": row["subject_id"],
                    "subject_name": row["subject_name"],
                    "subjectName": row["subject_name"],
                    "course_id": row["course_id"],
                    "courseId": row["course_id"],
                    "class_id": row["class_id"],
                    "classId": row["class_id"],
                    "class_name": row["class_name"],
                    "className": row["class_name"],
                    "division_id": row["division_id"],
                    "divisionId": row["division_id"],
                    "division_name": row["division_name"],
                    "divisionName": row["division_name"],
                    "start_time": str(row["start_time"]),
                    "startTime": str(row["start_time"]),
                    "start": str(row["start_time"]),
                    "end_time": str(row["end_time"]),
                    "endTime": str(row["end_time"]),
                    "end": str(row["end_time"]),
                    "day_of_week": row["day_of_week"],
                    "dayOfWeek": row["day_of_week"],
                }
            )

        response_payload = {
            "success": True,
            "resolved": True,
            "timetable_id": resolved["timetable_id"],
            "timetableId": resolved["timetable_id"],
            "session_id": resolved["timetable_id"],
            "sessionId": resolved["timetable_id"],
            "date": schedule_date.isoformat(),
            "attendanceDate": schedule_date.isoformat(),
            "day_of_week": day_name,
            "dayOfWeek": day_name,
            "candidate_count": len(candidates),
            "candidateCount": len(candidates),
            "candidates": candidates,
            "sessions": candidates,
            "entries": candidates,
        }
        response_payload.update(_server_time_context())
        return jsonify(response_payload)
    finally:
        cursor.close()
        connection.close()


@mobile_sync_bp.route("/attendance/sync", methods=["POST"])
def upload_attendance_logs():
    payload = request.get_json(silent=True) or {}
    auth_details = getattr(g, "mobile_auth", {})

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
        current_app.logger.warning("Mobile sync event rejected: event_uuid=%s reason=%s", event_uuid, message)

    def _timetable_matches_student_context(timetable_row, student_course_id, student_class_id, student_division_id, subject_id=None):
        if not timetable_row:
            return False
        if student_course_id and timetable_row.get("course_id") != student_course_id:
            return False
        if student_class_id and timetable_row.get("class_id") != student_class_id:
            return False
        if student_division_id and timetable_row.get("division_id") != student_division_id:
            return False
        if subject_id and timetable_row.get("subject_id") != subject_id:
            return False
        return True

    try:
        for event in events:
            event_uuid = str(_pick(event, "event_uuid", "eventUuid", default="") or "").strip()
            student_id = _pick(event, "student_id", "studentId")
            timetable_id = _pick(event, "timetable_id", "timetableId")
            attendance_date = _normalize_attendance_date(_pick(event, "attendance_date", "attendanceDate"))
            status = _normalize_status(_pick(event, "status"))
            marked_by_user_id = _pick(event, "marked_by_user_id", "markedByUserId") or auth_details.get("owner_user_id")
            subject_id = _pick(event, "subject_id", "subjectId")
            class_id = _pick(event, "class_id", "classId")
            division_id = _pick(event, "division_id", "divisionId")

            captured_time = _normalize_time_hhmmss(_pick(event, "captured_time", "capturedTime"))
            if not captured_time:
                try:
                    captured_dt_raw = _pick(event, "captured_at", "capturedAt")
                    captured_dt = _parse_iso_datetime(captured_dt_raw) if captured_dt_raw else None
                    captured_time = captured_dt.strftime("%H:%M:%S") if captured_dt else None
                except Exception:
                    captured_time = None

            if not event_uuid:
                _record_failure(None, "event_uuid is required")
                continue

            if status not in ALLOWED_STATUSES:
                _record_failure(event_uuid, "status must be Present/Absent/Late")
                continue

            if student_id is None or timetable_id is None or not attendance_date:
                _record_failure(event_uuid, "student_id, timetable_id, attendance_date are required")
                continue

            try:
                student_id = int(student_id)
                timetable_id = int(timetable_id)
            except (TypeError, ValueError):
                _record_failure(event_uuid, "student_id and timetable_id must be integers")
                continue

            original_student_id = student_id
            resolved_student_id = _resolve_student_id_from_event(cursor, student_id, event)
            if resolved_student_id is None:
                _record_failure(
                    event_uuid,
                    (
                        f"student_id could not be mapped to a valid student record. "
                        f"student_id={original_student_id}, "
                        f"person_id={_pick(event, 'person_id', 'personId')}, "
                        f"user_id={_pick(event, 'user_id', 'userId')}, "
                        f"enrollment={_pick(event, 'enrollment_code', 'enrollmentCode', 'enrollment', 'enrollment_no', 'enrollmentNo', 'admission_id', 'admissionId', 'admission_no', 'admissionNo')}, "
                        f"roll={_pick(event, 'roll_number', 'rollNumber', 'roll', 'rollNo', 'roll_no')}"
                    ),
                )
                continue
            student_id = resolved_student_id

            try:
                subject_id = int(subject_id) if subject_id not in (None, "") else None
            except (TypeError, ValueError):
                subject_id = None
            try:
                class_id = int(class_id) if class_id not in (None, "") else None
            except (TypeError, ValueError):
                class_id = None
            try:
                division_id = int(division_id) if division_id not in (None, "") else None
            except (TypeError, ValueError):
                division_id = None

            student_course_id, student_class_id, student_division_id = _resolve_student_class_division(cursor, student_id)
            if student_class_id and student_division_id:
                # Prefer server-side student mapping over potentially stale mobile cache IDs.
                class_id = student_class_id
                division_id = student_division_id
            elif class_id is None or division_id is None:
                class_id = class_id or student_class_id
                division_id = division_id or student_division_id

            if marked_by_user_id is not None:
                try:
                    marked_by_user_id = int(marked_by_user_id)
                except (TypeError, ValueError):
                    marked_by_user_id = None

            if marked_by_user_id is None:
                # Fallback: derive faculty user id from timetable if client omits marked_by_user_id.
                marked_by_user_id = _resolve_timetable_faculty_user_id(cursor, timetable_id)

            timetable_row = _resolve_timetable_record(cursor, timetable_id) if timetable_id > 0 else None
            if timetable_row and not _timetable_matches_student_context(
                timetable_row,
                student_course_id,
                student_class_id,
                student_division_id,
                subject_id=subject_id,
            ):
                current_app.logger.warning(
                    "Mobile sync timetable mismatch: event_uuid=%s timetable_id=%s student_course=%s student_class=%s student_division=%s timetable_course=%s timetable_class=%s timetable_division=%s timetable_subject=%s event_subject=%s",
                    event_uuid,
                    timetable_id,
                    student_course_id,
                    student_class_id,
                    student_division_id,
                    timetable_row.get("course_id"),
                    timetable_row.get("class_id"),
                    timetable_row.get("division_id"),
                    timetable_row.get("subject_id"),
                    subject_id,
                )
                timetable_id = 0

            if timetable_id <= 0:
                timetable_id = (
                    _resolve_timetable_id_from_event(
                        cursor,
                        attendance_date=attendance_date,
                        course_id=student_course_id,
                        faculty_user_id=marked_by_user_id,
                        subject_id=subject_id,
                        class_id=class_id,
                        division_id=division_id,
                        at_time=captured_time,
                    )
                    or 0
                )

            if timetable_id <= 0:
                timetable_id = (
                    _resolve_timetable_id_relaxed(
                        cursor,
                        course_id=student_course_id,
                        faculty_user_id=marked_by_user_id,
                        subject_id=subject_id,
                        class_id=class_id,
                        division_id=division_id,
                    )
                    or 0
                )

            if timetable_id <= 0:
                timetable_id = (
                    _resolve_recent_timetable_for_student(
                        cursor,
                        student_id=student_id,
                        course_id=student_course_id,
                        faculty_user_id=marked_by_user_id,
                        subject_id=subject_id,
                    )
                    or 0
                )

            if timetable_id <= 0:
                group_has_schedule = _has_active_timetable_for_group(cursor, class_id, division_id)
                _record_failure(
                    event_uuid,
                    (
                        "timetable_id must be greater than 0. Could not auto-resolve timetable from payload. "
                        f"Context: student_raw={original_student_id}, student_resolved={student_id}, "
                        f"course={student_course_id}, "
                        f"date={attendance_date}, faculty={marked_by_user_id}, subject={subject_id}, "
                        f"class={class_id}, division={division_id}, time={captured_time}, "
                        f"group_has_active_timetable={group_has_schedule}. "
                        "Sync timetable first and send valid timetableId."
                    ),
                )
                continue

            faculty_row = _resolve_faculty_record_by_reference(cursor, marked_by_user_id)
            if not faculty_row:
                timetable_faculty_user_id = _resolve_timetable_faculty_user_id(cursor, timetable_id)
                if timetable_faculty_user_id not in (None, marked_by_user_id):
                    faculty_row = _resolve_faculty_record_by_reference(cursor, timetable_faculty_user_id)
                    if faculty_row:
                        marked_by_user_id = faculty_row.get("user_id") or timetable_faculty_user_id

            if not faculty_row:
                _record_failure(
                    event_uuid,
                    f"No faculty profile found for marked_by_user_id={marked_by_user_id} or timetable faculty fallback",
                )
                continue

            faculty_id = faculty_row.get("id")
            marked_by_user_id = faculty_row.get("user_id") or marked_by_user_id

            try:
                captured_value = _pick(event, "captured_at", "capturedAt")
                captured_at = _parse_iso_datetime(captured_value) if captured_value else None
            except ValueError:
                captured_at = None

            try:
                cursor.execute(
                    """
                    INSERT INTO attendance_logs (
                        event_uuid,
                        device_id,
                        student_id,
                        timetable_id,
                        attendance_date,
                        status,
                        marked_by_user_id,
                        marked_by_faculty_id,
                        captured_at,
                        confidence,
                        face_model,
                        detector_model,
                        remarks,
                        processing_status,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                    """,
                    (
                        event_uuid,
                        device_id,
                        student_id,
                        timetable_id,
                        attendance_date,
                        status,
                        marked_by_user_id,
                        faculty_id,
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
                cursor.execute("SELECT * FROM attendance_logs WHERE id = %s", (log_id,))
                log_row = cursor.fetchone()
                _promote_log_to_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE attendance_logs
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
                    UPDATE attendance_logs
                    SET processing_status = 'failed',
                        error_message = %s
                    WHERE id = %s
                    """,
                    (str(process_error)[:500], log_id),
                )

        connection.commit()

        current_app.logger.info(
            "Mobile attendance sync summary: device_id=%s total_events=%s accepted=%s duplicates=%s failed=%s",
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
                    "error": "No attendance events were accepted. Check results for rejection reasons.",
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
        current_app.logger.error("Attendance sync failed: %s", str(e))
        return _json_error("Attendance sync failed", 500)
    finally:
        cursor.close()
        connection.close()


@mobile_sync_bp.route("/attendance/reprocess", methods=["POST"])
def reprocess_failed_logs():
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
        cursor.execute(
            """
            SELECT *
            FROM attendance_logs
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
                _promote_log_to_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE attendance_logs
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
                    UPDATE attendance_logs
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
        current_app.logger.error("Failed to reprocess attendance logs: %s", str(e))
        return _json_error("Failed to reprocess attendance logs", 500)
    finally:
        cursor.close()
        connection.close()