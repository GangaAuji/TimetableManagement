"""Holiday lookups. Each function keeps the query it was moved from."""


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
