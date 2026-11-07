"""Admin attendance screens. Shared helpers."""

from decimal import Decimal

def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None

def _decimal_to_number(value):
    if isinstance(value, Decimal):
        return int(value) if value == int(value) else float(value)
    return value

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
