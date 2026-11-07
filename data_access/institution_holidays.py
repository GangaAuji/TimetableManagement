"""Institution holiday SQL. Callers pass a cursor."""


def fetch_holidays(cursor):
    """Return holidays in the admin list order."""
    cursor.execute(
        """
        SELECT id, holiday_date, day_of_week, name, applies_to_program, is_recurring
        FROM institution_holidays
        ORDER BY is_recurring DESC,
                 CASE WHEN holiday_date IS NULL THEN 1 ELSE 0 END,
                 holiday_date ASC,
                 FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')
        """
    )
    return cursor.fetchall()


def insert_weekly_holiday(cursor, day_of_week, name, applies_to_program):
    """Insert a recurring weekday holiday."""
    cursor.execute(
        "INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)"
        " VALUES (NULL, %s, %s, %s, 1)",
        (day_of_week, name, applies_to_program),
    )


def insert_dated_holiday(cursor, holiday_date, name, applies_to_program):
    """Insert a date-specific holiday."""
    cursor.execute(
        "INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)"
        " VALUES (%s, NULL, %s, %s, 0)",
        (holiday_date, name, applies_to_program),
    )


def delete_holiday(cursor, holiday_id):
    """Delete one holiday."""
    cursor.execute("DELETE FROM institution_holidays WHERE id = %s", (holiday_id,))


def update_weekly_holiday(cursor, name, applies_to_program, day_of_week, holiday_id):
    """Store a holiday as a recurring weekday."""
    cursor.execute(
        """
                UPDATE institution_holidays
                SET name = %s,
                    applies_to_program = %s,
                    is_recurring = 1,
                    day_of_week = %s,
                    holiday_date = NULL
                WHERE id = %s
                """,
        (name, applies_to_program, day_of_week, holiday_id),
    )


def update_dated_holiday(cursor, name, applies_to_program, holiday_date, holiday_id):
    """Store a holiday as a single date."""
    cursor.execute(
        """
                UPDATE institution_holidays
                SET name = %s,
                    applies_to_program = %s,
                    is_recurring = 0,
                    holiday_date = %s,
                    day_of_week = NULL
                WHERE id = %s
                """,
        (name, applies_to_program, holiday_date, holiday_id),
    )
