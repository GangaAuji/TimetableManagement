"""Overlap checks. No request or session state."""

from datetime import time


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def times_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """Return whether two time spans share any minute."""
    return _minutes(a_start) < _minutes(b_end) and _minutes(a_end) > _minutes(b_start)


def faculty_timetable_free(cursor, faculty_id, day, start_time, end_time, *, active_only: bool) -> bool:
    """Return whether this faculty has no timetable row in the span."""
    active_sql = " AND COALESCE(is_active, 1) = 1" if active_only else ""
    cursor.execute(
        f"""
        SELECT 1
        FROM timetable
        WHERE faculty_id = %s
          AND day_of_week = %s
          AND NOT (end_time <= %s OR start_time >= %s){active_sql}
        LIMIT 1
        """,
        (faculty_id, day, start_time, end_time),
    )
    return cursor.fetchone() is None
