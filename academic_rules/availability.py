"""Availability rules. Generation and manual add stay separate."""

from datetime import date, time

from academic_rules.clashes import times_overlap
from academic_rules.weekdays import weekday_number


def faculty_is_available(
    faculty_id: int,
    day_name: str,
    slot_group: list[tuple[time, time]],
    day_date: date,
    faculty_busy_state: dict,
    availability_map: dict,
    faculty_absences: set,
) -> tuple[bool, str | None]:
    """Return whether generation may place this faculty, and a reason when it may not."""
    # Check if faculty is absent on this date
    if (faculty_id, day_date) in faculty_absences:
        return False, 'absent'

    # Check for scheduling conflicts with already assigned classes
    for busy_start, busy_end in faculty_busy_state.get(faculty_id, {}).get(day_name, []):
        if any(times_overlap(busy_start, busy_end, start, end) for start, end in slot_group):
            return False, 'conflict'

    # Check availability/shift patterns
    availability = availability_map.get(faculty_id, {}).get(day_name)
    if availability:
        # Only block if faculty is EXPLICITLY marked as unavailable
        # Shift patterns are treated as preferences, not hard restrictions
        # This allows faculty to teach both UG (morning) and PG (afternoon) courses
        for start, end in slot_group:
            # Check for explicit unavailability (is_available=0)
            blocked = any(
                not window['is_available'] and times_overlap(window['start'], window['end'], start, end)
                for window in availability
            )
            if blocked:
                return False, 'not_available'

            # NOTE: We do NOT enforce shift time windows strictly
            # Faculty can teach outside their primary shift if allocated to the subject
            # This enables flexibility for faculty teaching multiple courses (UG + PG)
    # If no availability records or no explicit blocks, treat as available

    return True, None


def manual_add_availability_block(cursor, faculty_id, day_name, start_time, end_time) -> str | None:
    """Return the manual-add message when recorded availability blocks the slot."""
    day_number = weekday_number(day_name)
    if day_number is None:
        return 'Faculty availability could not be checked for that day.'
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM faculty_availability WHERE faculty_id = %s AND day_of_week = %s",
        (faculty_id, day_number),
    )
    cnt = cursor.fetchone()['cnt']
    if cnt and int(cnt) > 0:
        # Any explicit unavailability overlapping the slot blocks the add
        cursor.execute(
            """
            SELECT 1 FROM faculty_availability
            WHERE faculty_id = %s AND day_of_week = %s AND is_available = 0
              AND NOT (end_time <= %s OR start_time >= %s)
            LIMIT 1
            """,
            (faculty_id, day_number, start_time, end_time),
        )
        if cursor.fetchone():
            return 'Faculty is marked unavailable during the selected time.'
        # Require an available window that fully covers the slot
        cursor.execute(
            """
            SELECT 1 FROM faculty_availability
            WHERE faculty_id = %s AND day_of_week = %s AND is_available = 1
              AND start_time <= %s AND end_time >= %s
            LIMIT 1
            """,
            (faculty_id, day_number, start_time, end_time),
        )
        if not cursor.fetchone():
            return "Selected time is outside the faculty's available hours for this day."
    return None
