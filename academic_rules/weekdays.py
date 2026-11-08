"""Weekday names and the 1–7 numbers stored on faculty availability.

Monday is 1 and Sunday is 7, matching faculty_availability.day_of_week.
Timetable rows store the English name instead. Comparisons must use one form.
"""

from datetime import date, datetime

NAMES = {
    1: 'Monday',
    2: 'Tuesday',
    3: 'Wednesday',
    4: 'Thursday',
    5: 'Friday',
    6: 'Saturday',
    7: 'Sunday',
}
NUMBERS = {name: number for number, name in NAMES.items()}


def weekday_number(value):
    """Return 1–7, or None when the value is not a known weekday."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value in NAMES else None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoweekday()
    if isinstance(value, datetime):
        return value.date().isoweekday()
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return weekday_number(int(text))
        return NUMBERS.get(text[:1].upper() + text[1:].lower()) if text else None
    return None


def weekday_name(value):
    """Return the English weekday, or None when the value is not recognized."""
    number = weekday_number(value)
    if number is None:
        return None
    return NAMES[number]
