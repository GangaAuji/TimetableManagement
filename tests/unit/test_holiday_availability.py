"""Holiday and availability helpers keep the generator and manual-add rules apart."""

from datetime import date, time

from academic_rules.availability import faculty_is_available, manual_add_availability_block
from academic_rules.holidays import holidays_for_week, recurring_holiday_blocks_day, recurring_holiday_taken


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.sql = ''
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)

    def fetchall(self):
        rows = self.rows
        self.rows = []
        return rows


def test_holiday_queries_keep_their_parameters():
    week = _Cursor([{'day_of_week': 'Sunday', 'holiday_date': None, 'name': 'Weekly', 'is_recurring': 1}])
    start = date(2026, 10, 26)
    end = date(2026, 11, 1)
    assert holidays_for_week(week, 'UG', start, end)[0]['name'] == 'Weekly'
    assert week.params == ('UG', start, end, 'UG')
    assert 'BETWEEN %s AND %s' in week.sql

    blocked = _Cursor([{'x': 1}])
    assert recurring_holiday_blocks_day(blocked, 'PG', 'Sunday') is True
    assert blocked.params == ('Sunday', 'PG')
    assert "applies_to_program = 'Both'" in blocked.sql

    added = _Cursor([{'id': 3}])
    assert recurring_holiday_taken(added, 'Monday', 'UG', None) is True
    assert added.params == ('Monday', 'UG', None, None)

    edited = _Cursor([])
    assert recurring_holiday_taken(edited, 'Monday', 'UG', 9) is False
    assert edited.params == ('Monday', 'UG', 9, 9)


def test_generation_treats_shift_windows_as_preferences():
    day = date(2026, 10, 26)
    afternoon = [(time(14, 0), time(15, 0))]
    morning_shift = [{'start': time(9, 0), 'end': time(12, 0), 'is_available': True}]
    assert faculty_is_available(1, 'Monday', afternoon, day, {}, {1: {'Monday': morning_shift}}, set()) == (True, None)

    blocked = [{'start': time(14, 0), 'end': time(16, 0), 'is_available': False}]
    assert faculty_is_available(1, 'Monday', afternoon, day, {}, {1: {'Monday': blocked}}, set()) == (False, 'not_available')
    assert faculty_is_available(1, 'Monday', afternoon, day, {}, {}, {(1, day)}) == (False, 'absent')
    busy = {1: {'Monday': [(time(14, 30), time(15, 30))]}}
    assert faculty_is_available(1, 'Monday', afternoon, day, busy, {}, set()) == (False, 'conflict')


def test_manual_add_requires_a_covering_window():
    outside = _Cursor([{'cnt': 1}, None, None])
    assert manual_add_availability_block(outside, 4, 'Monday', time(14, 0), time(15, 0)) == (
        "Selected time is outside the faculty's available hours for this day."
    )
    unmarked = _Cursor([{'cnt': 1}, {'x': 1}])
    assert manual_add_availability_block(unmarked, 4, 'Monday', time(14, 0), time(15, 0)) == (
        'Faculty is marked unavailable during the selected time.'
    )
    no_rows = _Cursor([{'cnt': 0}])
    assert manual_add_availability_block(no_rows, 4, 'Monday', time(14, 0), time(15, 0)) is None
