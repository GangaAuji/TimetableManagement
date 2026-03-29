"""Mobile attendance sync routes."""

import json
import math
import os
from datetime import datetime

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


def _to_iso_string(raw_value):
    if raw_value is None:
        return None
    if hasattr(raw_value, "isoformat"):
        return raw_value.isoformat()
    return str(raw_value)


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


def _resolve_faculty_id_by_user(cursor, user_id):
    cursor.execute("SELECT id FROM faculty WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    return row["id"] if row else None


def _resolve_timetable_faculty_user_id(cursor, timetable_id):
    cursor.execute("SELECT faculty_id FROM timetable WHERE id = %s", (timetable_id,))
    row = cursor.fetchone()
    return row.get("faculty_id") if row else None


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
    # 1) Direct students.id
    if raw_student_id is not None:
        exists = _student_exists(cursor, raw_student_id)
        if exists:
            return exists

        # 2) Some clients send users.id instead of students.id
        cursor.execute("SELECT id FROM students WHERE user_id = %s LIMIT 1", (raw_student_id,))
        row = cursor.fetchone()
        if row:
            return row.get("id")

    # 3) Enrollment/admission identifiers
    enrollment_code = _pick(event, "enrollment_code", "enrollmentCode", "admission_id", "admissionId")
    if enrollment_code:
        cursor.execute("SELECT id FROM students WHERE admission_id = %s LIMIT 1", (str(enrollment_code).strip(),))
        row = cursor.fetchone()
        if row:
            return row.get("id")

    # 4) Roll number fallback
    roll_number = _pick(event, "roll_number", "rollNumber")
    if roll_number:
        cursor.execute("SELECT id FROM students WHERE roll_number = %s LIMIT 1", (str(roll_number).strip(),))
        row = cursor.fetchone()
        if row:
            return row.get("id")

    return None


def _resolve_recent_timetable_for_student(cursor, student_id, faculty_user_id=None, subject_id=None):
    where_parts = ["a.student_id = %s"]
    params = [student_id]

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
                "t.subject_id = %s",
                "t.class_id = %s",
                "t.division_id = %s",
            ],
            [faculty_user_id, subject_id, class_id, division_id],
        ),
        (
            [
                "COALESCE(t.is_active, 1) = 1",
                "t.faculty_id = %s",
                "t.class_id = %s",
                "t.division_id = %s",
            ],
            [faculty_user_id, class_id, division_id],
        ),
        (
            [
                "COALESCE(t.is_active, 1) = 1",
                "t.subject_id = %s",
                "t.class_id = %s",
                "t.division_id = %s",
            ],
            [subject_id, class_id, division_id],
        ),
        (
            [
                "COALESCE(t.is_active, 1) = 1",
                "t.class_id = %s",
                "t.division_id = %s",
            ],
            [class_id, division_id],
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
            has_valid_template = isinstance(template_embedding, list) and len(template_embedding) == EXPECTED_FACE_TEMPLATE_LENGTH
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


@mobile_sync_bp.route("/timetable", methods=["GET"])
def sync_timetable():
    date_value = request.args.get("date") or request.args.get("attendanceDate")
    faculty_user_id = request.args.get("faculty_user_id", type=int)
    if faculty_user_id is None:
        faculty_user_id = request.args.get("facultyUserId", type=int)

    if not date_value:
        return _json_error("date query param is required (YYYY-MM-DD).")

    try:
        schedule_date = datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError:
        return _json_error("Invalid date format. Use YYYY-MM-DD.")

    day_name = schedule_date.strftime("%A")

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

            response_rows.append(
                {
                    "timetable_id": lecture["timetable_id"],
                    "timetableId": lecture["timetable_id"],
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
                    "start_time": str(lecture["start_time"]),
                    "startTime": str(lecture["start_time"]),
                    "end_time": str(lecture["end_time"]),
                    "endTime": str(lecture["end_time"]),
                    "students": students,
                }
            )

        return jsonify(
            {
                "success": True,
                "date": schedule_date.isoformat(),
                "attendanceDate": schedule_date.isoformat(),
                "day_of_week": day_name,
                "dayOfWeek": day_name,
                "count": len(response_rows),
                "lectures": response_rows,
            }
        )
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
            return jsonify(
                {
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
            )

        resolved = matches[0]
        candidates = []
        for row in matches:
            candidates.append(
                {
                    "timetable_id": row["timetable_id"],
                    "timetableId": row["timetable_id"],
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
                    "end_time": str(row["end_time"]),
                    "endTime": str(row["end_time"]),
                    "day_of_week": row["day_of_week"],
                    "dayOfWeek": row["day_of_week"],
                }
            )

        return jsonify(
            {
                "success": True,
                "resolved": True,
                "timetable_id": resolved["timetable_id"],
                "timetableId": resolved["timetable_id"],
                "date": schedule_date.isoformat(),
                "attendanceDate": schedule_date.isoformat(),
                "day_of_week": day_name,
                "dayOfWeek": day_name,
                "candidate_count": len(candidates),
                "candidateCount": len(candidates),
                "candidates": candidates,
            }
        )
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
                        f"student_id={original_student_id}, enrollment={_pick(event, 'enrollment_code', 'enrollmentCode', 'admission_id', 'admissionId')}, "
                        f"roll={_pick(event, 'roll_number', 'rollNumber')}"
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

            if timetable_id <= 0:
                timetable_id = (
                    _resolve_timetable_id_from_event(
                        cursor,
                        attendance_date=attendance_date,
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

            faculty_id = _resolve_faculty_id_by_user(cursor, marked_by_user_id)
            if not faculty_id:
                _record_failure(event_uuid, f"No faculty profile found for marked_by_user_id={marked_by_user_id}")
                continue

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
