"""Holiday lookups. Each query function keeps the query it was moved from; is_working_day is pure."""

from datetime import date

from academic_rules.weekdays import weekday_name


def _applies(row, program) -> bool:
    scope = row.get('applies_to_program') if isinstance(row, dict) else getattr(row, 'applies_to_program', None)
    return program is None or scope in (None, 'Both', program)


def _field(row, name):
    return row.get(name) if isinstance(row, dict) else getattr(row, name, None)


def is_working_day(day: date, program: str | None, holidays) -> bool:
    """Return whether lectures of a program take place on this date.

    `holidays` are institution_holidays rows (dicts or objects with
    holiday_date, day_of_week, is_recurring, applies_to_program). A recurring
    row blocks its weekday; a dated row blocks its date. A row for 'Both' blocks
    every program; program None asks whether any program is blocked.
    """
    name = weekday_name(day)
    for row in holidays:
        if not _applies(row, program):
            continue
        if _field(row, 'is_recurring') and weekday_name(_field(row, 'day_of_week')) == name:
            return False
        holiday_date = _field(row, 'holiday_date')
        if holiday_date is not None and not _field(row, 'is_recurring') and holiday_date == day:
            return False
    return True


def holidays_for_range(cursor, date_from, date_to):
    """Load every recurring holiday and every dated holiday in the range, for all programs."""
    cursor.execute(
        """
        SELECT day_of_week, holiday_date, name, is_recurring, applies_to_program
        FROM institution_holidays
        WHERE (is_recurring = 1 AND day_of_week IS NOT NULL)
           OR (holiday_date BETWEEN %s AND %s)
        """,
        (date_from, date_to),
    )
    return cursor.fetchall()


def holidays_for_week(cursor, program: str, week_start, week_end):
    """Load recurring and dated holidays for one program and week."""
    cursor.execute(
        """
        SELECT day_of_week, holiday_date, name, is_recurring
        FROM institution_holidays
        WHERE (is_recurring = 1 AND day_of_week IS NOT NULL AND (applies_to_program = %s OR applies_to_program = 'Both'))
           OR (holiday_date BETWEEN %s AND %s AND (applies_to_program = %s OR applies_to_program = 'Both'))
        """,
        (program, week_start, week_end, program),
    )
    return cursor.fetchall()


def recurring_holiday_blocks_day(cursor, program: str, day_name: str) -> bool:
    """Return whether a recurring holiday blocks this weekday for the program."""
    cursor.execute(
        """
        SELECT 1 FROM institution_holidays
        WHERE is_recurring = 1 AND day_of_week = %s AND (applies_to_program = %s OR applies_to_program = 'Both')
        LIMIT 1
        """,
        (day_name, program),
    )
    return cursor.fetchone() is not None


def recurring_holiday_taken(cursor, day_name: str, program: str, ignore_id: int | None) -> bool:
    """Return whether this weekday and program already have a recurring holiday."""
    cursor.execute(
        """
        SELECT id FROM institution_holidays
        WHERE is_recurring = 1 AND day_of_week = %s AND applies_to_program = %s
          AND (%s IS NULL OR id != %s)
        """,
        (day_name, program, ignore_id, ignore_id),
    )
    return cursor.fetchone() is not None
