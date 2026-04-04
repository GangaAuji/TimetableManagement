"""Mobile attendance sync routes."""

import json
import math
import os
from datetime import datetime, timedelta, timezone

import decimal

from flask import Blueprint, current_app, g, jsonify, request, url_for
from werkzeug.utils import secure_filename

from config import Config
from database import get_db_connection
from .security import authenticate_mobile_request

mobile_sync_bp = Blueprint("mobile_sync", __name__, url_prefix="/mobile-sync/v1")

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
ALLOWED_STATUSES = {"Present", "Absent", "Late"}
EXPECTED_FACE_TEMPLATE_LENGTH = 192
DEFAULT_FACE_TEMPLATE_VERSION = "mobilefacenet_192_l2_v1"
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
FACULTY_CUSTOM_SHIFT_KEY_PREFIX = 1000000
FACULTY_SHIFT_LATE_GRACE_MINUTES = int(getattr(Config, "FACULTY_SHIFT_LATE_GRACE_MINUTES", 15) or 15)


def _json_error(message, status=400):
    return jsonify({"success": False, "error": message}), status


def _parse_iso_datetime(raw_value):
    if not raw_value:
        return None

    value = str(raw_value).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    return datetime.fromisoformat(value)


def _pick(data, *keys, default=None):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return default


def _normalize_status(raw_status):
    if raw_status is None:
        return None
    candidate = str(raw_status).strip().lower()
    if candidate == "present":
        return "Present"
    if candidate == "absent":
        return "Absent"
    if candidate == "late":
        return "Late"
    return str(raw_status)


def _normalize_attendance_date(raw_value):
    if raw_value is None:
        return None

    if hasattr(raw_value, "strftime"):
        return raw_value.strftime("%Y-%m-%d")

    value = str(raw_value).strip()
    if not value:
        return None

    if "T" in value:
        try:
            return _parse_iso_datetime(value).date().isoformat()
        except ValueError:
            pass

    return value


def _normalize_time_hhmmss(raw_value):
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if not value:
        return None

    parts = value.split(":")
    if len(parts) == 2:
        value = f"{parts[0]}:{parts[1]}:00"

    try:
        parsed = datetime.strptime(value, "%H:%M:%S")
        return parsed.strftime("%H:%M:%S")
    except ValueError:
        return None


def _seconds_from_hhmmss(raw_value):
    normalized = _normalize_time_hhmmss(raw_value)
    if not normalized:
        return None
    hh, mm, ss = normalized.split(":")
    return int(hh) * 3600 + int(mm) * 60 + int(ss)


def _to_iso_string(raw_value):
    if raw_value is None:
        return None
    if hasattr(raw_value, "isoformat"):
        return raw_value.isoformat()
    return str(raw_value)


def _server_time_context():
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc.astimezone(IST_TIMEZONE)
    return {
        "server_time_utc": now_utc.isoformat(),
        "serverTimeUtc": now_utc.isoformat(),
        "server_time_ist": now_ist.isoformat(),
        "serverTimeIst": now_ist.isoformat(),
        "server_timezone": "Asia/Kolkata",
        "serverTimezone": "Asia/Kolkata",
        "server_date_ist": now_ist.date().isoformat(),
        "serverDateIst": now_ist.date().isoformat(),
        "server_time_only_ist": now_ist.strftime("%H:%M:%S"),
        "serverTimeOnlyIst": now_ist.strftime("%H:%M:%S"),
    }


def _column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (Config.MYSQL_DB, table_name, column_name),
    )
    return cursor.fetchone() is not None


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (Config.MYSQL_DB, table_name),
    )
    return cursor.fetchone() is not None


def _safe_json_loads(raw_value, default=None):
    if raw_value is None:
        return default
    try:
        return json.loads(raw_value)
    except Exception:
        return default


def _normalize_face_template(raw_template):
    """Return an L2-normalized 192-d template list or None if invalid."""
    if raw_template is None:
        return None

    candidate = raw_template
    if isinstance(raw_template, str):
        candidate = _safe_json_loads(raw_template)

    if not isinstance(candidate, list) or len(candidate) != EXPECTED_FACE_TEMPLATE_LENGTH:
        return None

    normalized_values = []
    sum_sq = 0.0
    for value in candidate:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        normalized_values.append(number)
        sum_sq += number * number

    norm = math.sqrt(sum_sq)
    if norm <= 0.0:
        return None

    return [value / norm for value in normalized_values]


def _quality_threshold():
    try:
        return float(getattr(Config, "FACE_TEMPLATE_MIN_QUALITY", 0.55) or 0.55)
    except (TypeError, ValueError):
        return 0.55


def _has_acceptable_template_quality(raw_quality):
    if raw_quality is None:
        return True
    try:
        return float(raw_quality) >= _quality_threshold()
    except (TypeError, ValueError):
        return False


def _load_face_templates(cursor, user_ids, updated_after_dt=None):
    if not user_ids:
        return {}

    if not _table_exists(cursor, "mobile_face_templates"):
        return {}

    placeholders = ",".join(["%s"] * len(user_ids))
    params = list(user_ids)
    updated_filter = ""

    if updated_after_dt and _column_exists(cursor, "mobile_face_templates", "updated_at"):
        updated_filter = " AND updated_at > %s"
        params.append(updated_after_dt)

    cursor.execute(
        f"""
        SELECT
            user_id,
            embedding_json,
            image_path,
            quality_score,
            embedding_version,
            updated_at
        FROM mobile_face_templates
        WHERE is_active = 1
          AND user_id IN ({placeholders})
          {updated_filter}
        ORDER BY updated_at DESC
        """,
        tuple(params),
    )

    rows = cursor.fetchall() or []
    by_user = {}
    for row in rows:
        user_id = row.get("user_id")
        if user_id in by_user:
            continue
        normalized_embedding = _normalize_face_template(row.get("embedding_json"))
        by_user[user_id] = {
            "embedding": normalized_embedding,
            "image_path": row.get("image_path"),
            "quality_score": row.get("quality_score"),
            "embedding_version": row.get("embedding_version") or DEFAULT_FACE_TEMPLATE_VERSION,
            "updated_at": _to_iso_string(row.get("updated_at")),
        }

    return by_user


def _build_photo_url(photo_path):
    if not photo_path:
        return None

    normalized = str(photo_path).strip()
    if not normalized:
        return None

    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized

    normalized = normalized.lstrip("/\\")
    return url_for("static", filename=normalized, _external=True)


def _is_allowed_filename(filename):
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _resolve_faculty_record_by_reference(cursor, faculty_reference):
    if faculty_reference in (None, ""):
        return None

    try:
        candidate_id = int(faculty_reference)
    except (TypeError, ValueError):
        return None

    cursor.execute("SELECT id, user_id FROM faculty WHERE user_id = %s LIMIT 1", (candidate_id,))
    row = cursor.fetchone()
    if row:
        return row

    cursor.execute("SELECT id, user_id FROM faculty WHERE id = %s LIMIT 1", (candidate_id,))
    row = cursor.fetchone()
    if row:
        return row

    return None


def _resolve_faculty_id_by_user(cursor, user_id):
    faculty_row = _resolve_faculty_record_by_reference(cursor, user_id)
    return faculty_row.get("id") if faculty_row else None


def _resolve_timetable_faculty_user_id(cursor, timetable_id):
    cursor.execute("SELECT faculty_id FROM timetable WHERE id = %s", (timetable_id,))
    row = cursor.fetchone()
    return row.get("faculty_id") if row else None


def _resolve_timetable_record(cursor, timetable_id):
    cursor.execute(
        "SELECT id, faculty_id, course_id, class_id, division_id, subject_id FROM timetable WHERE id = %s LIMIT 1",
        (timetable_id,),
    )
    return cursor.fetchone()


def _resolve_student_class_division(cursor, student_id):
    cursor.execute("SELECT course_id, class_id, division_id FROM students WHERE id = %s", (student_id,))
    row = cursor.fetchone() or {}
    return row.get("course_id"), row.get("class_id"), row.get("division_id")


def _has_active_timetable_for_group(cursor, class_id, division_id):
    if not class_id or not division_id:
        return False
    cursor.execute(
        """
        SELECT 1
        FROM timetable
        WHERE COALESCE(is_active, 1) = 1
          AND class_id = %s
          AND division_id = %s
        LIMIT 1
        """,
        (class_id, division_id),
    )
    return cursor.fetchone() is not None


def _student_exists(cursor, student_id):
    cursor.execute("SELECT id FROM students WHERE id = %s LIMIT 1", (student_id,))
    row = cursor.fetchone()
    return row.get("id") if row else None


def _resolve_student_id_from_event(cursor, raw_student_id, event):
    candidate_ids = []
    for raw_value in (
        raw_student_id,
        _pick(event, "person_id", "personId"),
        _pick(event, "user_id", "userId"),
    ):
        if raw_value in (None, ""):
            continue
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in candidate_ids:
            candidate_ids.append(parsed)

    # 1) Direct students.id and 2) students.user_id candidates
    for candidate_id in candidate_ids:
        exists = _student_exists(cursor, candidate_id)
        if exists:
            return exists

        cursor.execute("SELECT id FROM students WHERE user_id = %s LIMIT 1", (candidate_id,))
        row = cursor.fetchone()
        if row:
            return row.get("id")

    # 3) Enrollment/admission identifiers
    enrollment_code = _pick(
        event,
        "enrollment_code",
        "enrollmentCode",
        "enrollment",
        "enrollment_no",
        "enrollmentNo",
        "admission_id",
        "admissionId",
        "admission_no",
        "admissionNo",
    )
    if enrollment_code:
        cursor.execute("SELECT id FROM students WHERE admission_id = %s LIMIT 1", (str(enrollment_code).strip(),))
        row = cursor.fetchone()
        if row:
            return row.get("id")

    # 4) Roll number fallback
    roll_number = _pick(event, "roll_number", "rollNumber", "roll", "rollNo", "roll_no")
    if roll_number:
        cursor.execute("SELECT id FROM students WHERE roll_number = %s LIMIT 1", (str(roll_number).strip(),))
        row = cursor.fetchone()
        if row:
            return row.get("id")

    return None


def _resolve_recent_timetable_for_student(cursor, student_id, course_id=None, faculty_user_id=None, subject_id=None):
    where_parts = ["a.student_id = %s"]
    params = [student_id]

    if course_id:
        where_parts.append("t.course_id = %s")
        params.append(course_id)
    if faculty_user_id:
        where_parts.append("t.faculty_id = %s")
        params.append(faculty_user_id)
    if subject_id:
        where_parts.append("t.subject_id = %s")
        params.append(subject_id)

    cursor.execute(
        f"""
        SELECT a.timetable_id
        FROM attendance a
        JOIN timetable t ON t.id = a.timetable_id
        WHERE {' AND '.join(where_parts)}
        ORDER BY a.marked_at DESC, a.id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    row = cursor.fetchone()
    return row.get("timetable_id") if row else None


def _resolve_timetable_id_from_event(
    cursor,
    *,
    attendance_date,
    course_id=None,
    faculty_user_id=None,
    subject_id=None,
    class_id=None,
    division_id=None,
    at_time=None,
):
    try:
        schedule_date = datetime.strptime(str(attendance_date), "%Y-%m-%d").date()
    except Exception:
        return None

    day_name = schedule_date.strftime("%A")
    where_parts = ["t.day_of_week = %s", "COALESCE(t.is_active, 1) = 1"]
    params = [day_name]

    if faculty_user_id:
        where_parts.append("t.faculty_id = %s")
        params.append(faculty_user_id)
    if course_id:
        where_parts.append("t.course_id = %s")
        params.append(course_id)
    if subject_id:
        where_parts.append("t.subject_id = %s")
        params.append(subject_id)
    if class_id:
        where_parts.append("t.class_id = %s")
        params.append(class_id)
    if division_id:
        where_parts.append("t.division_id = %s")
        params.append(division_id)
    if at_time:
        where_parts.append("%s BETWEEN t.start_time AND t.end_time")
        params.append(at_time)

    cursor.execute(
        f"""
        SELECT t.id
        FROM timetable t
        WHERE {" AND ".join(where_parts)}
        ORDER BY t.start_time
        LIMIT 1
        """,
        tuple(params),
    )
    row = cursor.fetchone()
    return row.get("id") if row else None


def _resolve_timetable_id_relaxed(
    cursor,
    *,
    course_id=None,
    faculty_user_id=None,
    subject_id=None,
    class_id=None,
    division_id=None,
):
    """Best-effort fallback timetable resolver when strict day/time matching fails."""
    strategies = [
        (
            [
                "COALESCE(t.is_active, 1) = 1",
                "t.faculty_id = %s",
                "t.course_id = %s",
                "t.subject_id = %s",
                "t.class_id = %s",
                "t.division_id = %s",
            ],
            [faculty_user_id, course_id, subject_id, class_id, division_id],
        ),
        (
            [
                "COALESCE(t.is_active, 1) = 1",
                "t.faculty_id = %s",
                "t.course_id = %s",
                "t.class_id = %s",
                "t.division_id = %s",
            ],
            [faculty_user_id, course_id, class_id, division_id],
        ),
        (
            [
                "COALESCE(t.is_active, 1) = 1",
                "t.course_id = %s",
                "t.subject_id = %s",
                "t.class_id = %s",
                "t.division_id = %s",
            ],
            [course_id, subject_id, class_id, division_id],
        ),
        (
            [
                "COALESCE(t.is_active, 1) = 1",
                "t.course_id = %s",
                "t.class_id = %s",
                "t.division_id = %s",
            ],
            [course_id, class_id, division_id],
        ),
    ]

    for where_parts, params in strategies:
        if any(param in (None, "") for param in params):
            continue

        cursor.execute(
            f"""
            SELECT t.id
            FROM timetable t
            WHERE {' AND '.join(where_parts)}
            ORDER BY t.id DESC
            LIMIT 1
            """,
            tuple(params),
        )
        row = cursor.fetchone()
        if row:
            return row.get("id")

    return None


def _day_of_week_from_date(attendance_date):
    try:
        parsed_date = datetime.strptime(str(attendance_date), "%Y-%m-%d").date()
        return parsed_date.isoweekday()
    except Exception:
        return None


def _build_custom_shift_key(shift_pattern_id, shift_start_time):
    if shift_pattern_id not in (None, ""):
        try:
            shift_id = int(shift_pattern_id)
            if shift_id > 0:
                return shift_id
        except (TypeError, ValueError):
            pass

    start_seconds = _seconds_from_hhmmss(shift_start_time)
    if start_seconds is None:
        return 0

    return FACULTY_CUSTOM_SHIFT_KEY_PREFIX + start_seconds


def _resolve_faculty_shift_context(cursor, faculty_user_id, day_of_week, captured_time=None):
    cursor.execute(
        """
        SELECT
            fa.id AS availability_id,
            fa.shift_pattern_id,
            fa.start_time AS availability_start_time,
            fa.end_time AS availability_end_time,
            fa.notes,
            sp.shift_name,
            sp.shift_code,
            sp.start_time AS shift_start_time,
            sp.end_time AS shift_end_time
        FROM faculty_availability fa
        LEFT JOIN shift_patterns sp ON sp.id = fa.shift_pattern_id
        WHERE fa.faculty_id = %s
          AND fa.day_of_week = %s
          AND COALESCE(fa.is_available, 1) = 1
        ORDER BY
            COALESCE(fa.start_time, sp.start_time),
            COALESCE(fa.end_time, sp.end_time),
            fa.id
        """,
        (faculty_user_id, day_of_week),
    )
    rows = cursor.fetchall() or []
    if not rows:
        return None

    normalized_rows = []
    for row in rows:
        shift_start_time = _normalize_time_hhmmss(
            row.get("availability_start_time") or row.get("shift_start_time")
        )
        shift_end_time = _normalize_time_hhmmss(
            row.get("availability_end_time") or row.get("shift_end_time")
        )
        shift_pattern_id = row.get("shift_pattern_id")

        shift_name = row.get("shift_name")
        if not shift_name:
            shift_name = "Custom Shift" if (shift_start_time or shift_end_time) else "General Availability"

        shift_code = row.get("shift_code")
        if not shift_code:
            shift_code = "CUSTOM" if (shift_start_time or shift_end_time) else "GENERAL"

        normalized_rows.append(
            {
                "availability_id": row.get("availability_id"),
                "shift_pattern_id": shift_pattern_id,
                "shift_key": _build_custom_shift_key(shift_pattern_id, shift_start_time),
                "shift_name": shift_name,
                "shift_code": shift_code,
                "shift_start_time": shift_start_time,
                "shift_end_time": shift_end_time,
                "notes": row.get("notes"),
            }
        )

    captured_seconds = _seconds_from_hhmmss(captured_time)
    if captured_seconds is not None:
        for row in normalized_rows:
            start_seconds = _seconds_from_hhmmss(row.get("shift_start_time"))
            end_seconds = _seconds_from_hhmmss(row.get("shift_end_time"))
            if start_seconds is None or end_seconds is None:
                continue

            # Support overnight shifts (e.g. 22:00 to 06:00) as well.
            if start_seconds <= end_seconds:
                in_window = start_seconds <= captured_seconds <= end_seconds
            else:
                in_window = captured_seconds >= start_seconds or captured_seconds <= end_seconds

            if in_window:
                return row

    return normalized_rows[0]


def _resolve_faculty_attendance_status(raw_status, captured_time, shift_start_time):
    requested_status = _normalize_status(raw_status)
    if requested_status in ALLOWED_STATUSES:
        return requested_status

    captured_seconds = _seconds_from_hhmmss(captured_time)
    start_seconds = _seconds_from_hhmmss(shift_start_time)
    if captured_seconds is None or start_seconds is None:
        return "Present"

    return "Late" if captured_seconds > (start_seconds + (FACULTY_SHIFT_LATE_GRACE_MINUTES * 60)) else "Present"


def _promote_log_to_faculty_attendance(cursor, log_row):
    cursor.execute(
        """
        INSERT INTO faculty_attendance (
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
            source,
            captured_at,
            confidence,
            remarks
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'mobile_face', %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            marked_by_user_id = VALUES(marked_by_user_id),
            captured_at = VALUES(captured_at),
            confidence = VALUES(confidence),
            remarks = VALUES(remarks),
            source = VALUES(source),
            marked_at = NOW(),
            updated_at = NOW()
        """,
        (
            log_row["faculty_id"],
            log_row["faculty_user_id"],
            log_row["attendance_date"],
            log_row["day_of_week"],
            log_row["shift_key"],
            log_row.get("shift_pattern_id"),
            log_row.get("shift_name"),
            log_row.get("shift_code"),
            log_row.get("shift_start_time"),
            log_row.get("shift_end_time"),
            log_row["status"],
            log_row["marked_by_user_id"],
            log_row.get("captured_at"),
            log_row.get("confidence"),
            log_row.get("remarks"),
        ),
    )


def _promote_log_to_attendance(cursor, log_row):
    cursor.execute(
        """
        INSERT INTO attendance (student_id, timetable_id, attendance_date, status, marked_by, remarks)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            marked_by = VALUES(marked_by),
            remarks = VALUES(remarks),
            marked_at = NOW(),
            updated_at = NOW()
        """,
        (
            log_row["student_id"],
            log_row["timetable_id"],
            log_row["attendance_date"],
            log_row["status"],
            log_row["marked_by_faculty_id"],
            log_row.get("remarks"),
        ),
    )


@mobile_sync_bp.before_request
def _mobile_auth_guard():
    return authenticate_mobile_request(allow_legacy_api_key=Config.MOBILE_SYNC_ALLOW_LEGACY_API_KEY)


@mobile_sync_bp.route("/health", methods=["GET"])
def mobile_sync_health():
    auth_mode = getattr(g, "mobile_auth", {}).get("mode")
    return jsonify({"success": True, "service": "mobile-sync", "status": "ok", "auth_mode": auth_mode})


@mobile_sync_bp.route("/users", methods=["GET"])
def sync_users():
    updated_after = request.args.get("updated_after") or request.args.get("updatedAfter")

    updated_after_dt = None
    if updated_after:
        try:
            updated_after_dt = _parse_iso_datetime(updated_after)
        except ValueError:
            return _json_error("Invalid updated_after. Use ISO-8601 datetime.")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        student_params = []
        faculty_params = []
        updated_filter_students = ""
        updated_filter_faculty = ""

        students_has_updated = _column_exists(cursor, "students", "updated_at")
        faculty_has_updated = _column_exists(cursor, "faculty", "updated_at")
        users_has_updated = _column_exists(cursor, "users", "updated_at")

        if students_has_updated and users_has_updated:
            students_updated_expr = "GREATEST(IFNULL(s.updated_at, '1970-01-01'), IFNULL(u.updated_at, '1970-01-01'))"
        elif students_has_updated:
            students_updated_expr = "IFNULL(s.updated_at, '1970-01-01')"
        elif users_has_updated:
            students_updated_expr = "IFNULL(u.updated_at, '1970-01-01')"
        else:
            students_updated_expr = "NULL"

        if faculty_has_updated and users_has_updated:
            faculty_updated_expr = "GREATEST(IFNULL(f.updated_at, '1970-01-01'), IFNULL(u.updated_at, '1970-01-01'))"
        elif faculty_has_updated:
            faculty_updated_expr = "IFNULL(f.updated_at, '1970-01-01')"
        elif users_has_updated:
            faculty_updated_expr = "IFNULL(u.updated_at, '1970-01-01')"
        else:
            faculty_updated_expr = "NULL"

        if updated_after_dt:
            if students_updated_expr != "NULL":
                updated_filter_students = f"AND {students_updated_expr} > %s"
                student_params.append(updated_after_dt)
            if faculty_updated_expr != "NULL":
                updated_filter_faculty = f"AND {faculty_updated_expr} > %s"
                faculty_params.append(updated_after_dt)

        cursor.execute(
            f"""
            SELECT
                'Student' AS role,
                s.id AS person_id,
                s.user_id AS user_id,
                s.name AS name,
                COALESCE(s.email, u.email) AS email,
                s.admission_id AS enrollment_code,
                s.roll_number AS roll_number,
                s.course_id,
                s.class_id,
                s.division_id,
                NULL AS department_id,
                u.profile_photo,
                                {students_updated_expr} AS updated_at
            FROM students s
            JOIN users u ON u.id = s.user_id
            WHERE COALESCE(s.is_active, 1) = 1
              {updated_filter_students}
            ORDER BY updated_at ASC
            """,
            tuple(student_params),
        )
        students = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT
                'Teacher' AS role,
                f.id AS person_id,
                f.user_id AS user_id,
                f.name AS name,
                COALESCE(f.email, u.email) AS email,
                NULL AS enrollment_code,
                NULL AS roll_number,
                NULL AS course_id,
                NULL AS class_id,
                NULL AS division_id,
                f.department_id,
                u.profile_photo,
                                {faculty_updated_expr} AS updated_at
            FROM faculty f
            JOIN users u ON u.id = f.user_id
            WHERE COALESCE(f.is_active, 1) = 1
              {updated_filter_faculty}
            ORDER BY updated_at ASC
            """,
            tuple(faculty_params),
        )
        teachers = cursor.fetchall()

        combined_rows = students + teachers
        user_ids = [row.get("user_id") for row in combined_rows if row.get("user_id") is not None]
        face_templates_by_user = _load_face_templates(cursor, user_ids, updated_after_dt=updated_after_dt)

        users = []
        for row in combined_rows:
            updated_value = _to_iso_string(row.get("updated_at"))
            user_id = row.get("user_id")
            profile_photo = row.get("profile_photo")
            profile_photo_url = _build_photo_url(profile_photo)
            face_template_info = face_templates_by_user.get(user_id) or {}
            template_embedding = face_template_info.get("embedding")
            quality_ok = _has_acceptable_template_quality(face_template_info.get("quality_score"))
            has_valid_template = (
                isinstance(template_embedding, list)
                and len(template_embedding) == EXPECTED_FACE_TEMPLATE_LENGTH
                and quality_ok
            )
            if not has_valid_template:
                template_embedding = None
            template_image_path = face_template_info.get("image_path")
            template_image_url = _build_photo_url(template_image_path) if template_image_path else None
            users.append(
                {
                    "role": row["role"],
                    "person_id": row["person_id"],
                    "personId": row["person_id"],
                    "user_id": user_id,
                    "userId": user_id,
                    "name": row["name"],
                    "email": row.get("email"),
                    "enrollment_code": row.get("enrollment_code"),
                    "enrollmentCode": row.get("enrollment_code"),
                    "roll_number": row.get("roll_number"),
                    "rollNumber": row.get("roll_number"),
                    "course_id": row.get("course_id"),
                    "courseId": row.get("course_id"),
                    "class_id": row.get("class_id"),
                    "classId": row.get("class_id"),
                    "division_id": row.get("division_id"),
                    "divisionId": row.get("division_id"),
                    "department_id": row.get("department_id"),
                    "departmentId": row.get("department_id"),
                    "profile_photo": profile_photo,
                    "profilePhoto": profile_photo,
                    "profile_photo_url": profile_photo_url,
                    "profilePhotoUrl": profile_photo_url,
                    "face_image_url": template_image_url or profile_photo_url,
                    "faceImageUrl": template_image_url or profile_photo_url,
                    "has_face_image": bool(template_image_url or profile_photo_url),
                    "hasFaceImage": bool(template_image_url or profile_photo_url),
                    "face_template": template_embedding,
                    "faceTemplate": template_embedding,
                    "embedding": template_embedding,
                    "face_embedding": template_embedding,
                    "face_embeddings": template_embedding,
                    "embedding_vector": template_embedding,
                    "face_vector": template_embedding,
                    "face_descriptor": template_embedding,
                    "has_face_template": has_valid_template,
                    "hasFaceTemplate": has_valid_template,
                    "face_updated_at": face_template_info.get("updated_at"),
                    "faceUpdatedAt": face_template_info.get("updated_at"),
                    "face_template_quality": face_template_info.get("quality_score"),
                    "faceTemplateQuality": face_template_info.get("quality_score"),
                    "face_template_version": face_template_info.get("embedding_version"),
                    "faceTemplateVersion": face_template_info.get("embedding_version"),
                    "updated_at": updated_value,
                    "updatedAt": updated_value,
                }
            )

        users.sort(key=lambda item: (item.get("updated_at") or "", item.get("role") or "", item.get("person_id") or 0))

        def _convert_decimals(obj):
            if isinstance(obj, list):
                return [_convert_decimals(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _convert_decimals(v) for k, v in obj.items()}
            if isinstance(obj, decimal.Decimal):
                # Use int if no fractional part, else float
                return int(obj) if obj == int(obj) else float(obj)
            return obj

        payload = {
            "success": True,
            "count": len(users),
            "users": users,
            "synced_at": datetime.utcnow().isoformat() + "Z",
        }
        return jsonify(_convert_decimals(payload))
    except Exception as e:
        current_app.logger.exception("sync_users failed: %s", str(e))
        return _json_error(f"Failed to fetch users: {str(e)}", 500)
    finally:
        cursor.close()
        connection.close()


# Split student/faculty sync endpoints into dedicated modules for easier maintenance.
from . import student_sync  # noqa: F401,E402
from . import faculty_sync  # noqa: F401,E402


@mobile_sync_bp.route("/users/<int:user_id>/face-image", methods=["POST"])
def upload_face_image(user_id):
    image_key = None
    if "image" in request.files:
        image_key = "image"
    elif "faceImage" in request.files:
        image_key = "faceImage"

    if not image_key:
        return _json_error("image file is required (multipart/form-data).")

    image_file = request.files[image_key]
    if not image_file.filename:
        return _json_error("Image filename is empty.")

    if not _is_allowed_filename(image_file.filename):
        return _json_error("Unsupported image format. Use png/jpg/jpeg/webp.")

    safe_name = secure_filename(image_file.filename)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    final_name = f"{user_id}_{timestamp}_{safe_name}"

    upload_dir = os.path.join(current_app.root_path, "static", "uploads", "profiles")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, final_name)

    image_file.save(file_path)

    relative_path = f"uploads/profiles/{final_name}"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("UPDATE users SET profile_photo = %s, updated_at = NOW() WHERE id = %s", (relative_path, user_id))
        if cursor.rowcount == 0:
            connection.rollback()
            return _json_error("User not found.", 404)

        connection.commit()

        return jsonify(
            {
                "success": True,
                "user_id": user_id,
                "userId": user_id,
                "profile_photo": relative_path,
                "profilePhoto": relative_path,
                "profile_photo_url": _build_photo_url(relative_path),
                "profilePhotoUrl": _build_photo_url(relative_path),
            }
        )
    finally:
        cursor.close()
        connection.close()


@mobile_sync_bp.route("/users/<int:user_id>/face-template", methods=["POST"])
def upload_face_template(user_id):
    payload = request.get_json(silent=True) or {}

    face_embedding = _pick(
        payload,
        "faceTemplate",
        "face_template",
        "embedding",
        "face_embedding",
        "face_embeddings",
        "embedding_vector",
        "face_vector",
        "face_descriptor",
        "faceEmbedding",
    )
    image_path = _pick(payload, "image_path", "imagePath")
    quality_score = _pick(payload, "quality_score", "qualityScore")
    embedding_version = _pick(payload, "embedding_version", "embeddingVersion")

    normalized_embedding = _normalize_face_template(face_embedding)
    if normalized_embedding is None:
        return _json_error(
            "faceTemplate/face_template must be a numeric 192-length vector (will be L2-normalized)."
        )

    if quality_score is not None:
        try:
            quality_score = float(quality_score)
        except (TypeError, ValueError):
            return _json_error("quality_score/qualityScore must be numeric.")

    embedding_version = (embedding_version or DEFAULT_FACE_TEMPLATE_VERSION).strip()

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, "mobile_face_templates"):
            return _json_error("mobile_face_templates table is missing. Run face template migration.", 503)

        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            return _json_error("User not found.", 404)

        cursor.execute(
            """
            INSERT INTO mobile_face_templates (
                user_id,
                embedding_json,
                image_path,
                quality_score,
                embedding_version,
                is_active,
                updated_at,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, 1, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                embedding_json = VALUES(embedding_json),
                image_path = VALUES(image_path),
                quality_score = VALUES(quality_score),
                embedding_version = VALUES(embedding_version),
                is_active = 1,
                updated_at = NOW()
            """,
            (
                user_id,
                json.dumps(normalized_embedding),
                image_path,
                quality_score,
                embedding_version,
            ),
        )

        connection.commit()

        return jsonify(
            {
                "success": True,
                "user_id": user_id,
                "userId": user_id,
                "has_face_template": True,
                "hasFaceTemplate": True,
                "embedding_size": len(normalized_embedding),
                "embeddingSize": len(normalized_embedding),
                "face_template_version": embedding_version,
                "faceTemplateVersion": embedding_version,
            }
        )
    except Exception as e:
        connection.rollback()
        current_app.logger.exception("upload_face_template failed: %s", str(e))
        return _json_error(f"Failed to upload face template: {str(e)}", 500)
    finally:
        cursor.close()
        connection.close()
