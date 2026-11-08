"""academic_rules: the pure overlap and availability rules, then the cursor-based clash and holiday lookups.

The pure tests use no fixtures and run without --live-db. The cursor tests
use the shared test database.
"""

from datetime import date, time

import pytest

from academic_rules.availability import faculty_is_available, manual_add_availability_block
from academic_rules.clashes import faculty_timetable_free, times_overlap
from academic_rules.holidays import holidays_for_week, recurring_holiday_blocks_day, recurring_holiday_taken
from tests.factories import LECTURE_DATE

NINE, TEN, ELEVEN = time(9), time(10), time(11)
MONDAY = LECTURE_DATE


@pytest.mark.parametrize('a, b, expected', [
    ((NINE, TEN), (time(9, 30), ELEVEN), True),
    ((NINE, ELEVEN), (time(9, 30), time(9, 45)), True),
    ((NINE, TEN), (NINE, TEN), True),
    ((NINE, TEN), (TEN, ELEVEN), False),
    ((TEN, ELEVEN), (NINE, TEN), False),
    ((NINE, TEN), (time(10, 30), ELEVEN), False),
])
def test_times_overlap(a, b, expected):
    assert times_overlap(*a, *b) is expected
    assert times_overlap(*b, *a) is expected


def _available(**state):
    arguments = {'faculty_busy_state': {}, 'availability_map': {}, 'faculty_absences': set()}
    arguments.update(state)
    return faculty_is_available(7, 'Monday', [(NINE, TEN)], MONDAY, **arguments)


def test_faculty_is_available_with_no_records():
    assert _available() == (True, None)


def test_faculty_is_unavailable_when_absent():
    assert _available(faculty_absences={(7, MONDAY)}) == (False, 'absent')
    assert _available(faculty_absences={(7, date(2026, 11, 10))}) == (True, None)


def test_faculty_is_unavailable_when_already_teaching():
    assert _available(faculty_busy_state={7: {'Monday': [(time(9, 30), ELEVEN)]}}) == (False, 'conflict')
    assert _available(faculty_busy_state={7: {'Monday': [(TEN, ELEVEN)]}}) == (True, None)
    assert _available(faculty_busy_state={7: {'Tuesday': [(NINE, TEN)]}}) == (True, None)


def test_faculty_is_unavailable_only_in_an_explicit_block():
    blocked = {7: {'Monday': [{'is_available': 0, 'start': NINE, 'end': ELEVEN}]}}
    assert _available(availability_map=blocked) == (False, 'not_available')
    window = {7: {'Monday': [{'is_available': 1, 'start': time(14), 'end': time(16)}]}}
    assert _available(availability_map=window) == (True, None), 'shift windows are preferences, not limits'


@pytest.fixture
def cursor(db):
    cursor = db.cursor(dictionary=True)
    yield cursor
    cursor.close()
    db.commit()


def test_faculty_timetable_free_finds_the_lecture(cursor, factory):
    setup = factory.academic()
    teacher = setup['teacher']['faculty_id']
    assert faculty_timetable_free(cursor, teacher, 'Monday', time(9, 30), ELEVEN, active_only=True) is False
    assert faculty_timetable_free(cursor, teacher, 'Monday', TEN, ELEVEN, active_only=True) is True
    assert faculty_timetable_free(cursor, teacher, 'Tuesday', NINE, TEN, active_only=True) is True


def test_faculty_timetable_free_can_ignore_inactive_rows(cursor, factory):
    setup = factory.academic()
    factory.execute('UPDATE timetable SET is_active = 0 WHERE id = %s', (setup['timetable_id'],))
    teacher = setup['teacher']['faculty_id']
    assert faculty_timetable_free(cursor, teacher, 'Monday', NINE, TEN, active_only=True) is True
    assert faculty_timetable_free(cursor, teacher, 'Monday', NINE, TEN, active_only=False) is False


def _availability(factory, faculty_id, available, start, end, day=1):
    factory.insert('faculty_availability', faculty_id=faculty_id, day_of_week=day,
                   is_available=available, start_time=start, end_time=end)


def test_manual_add_with_no_availability_records_is_allowed(cursor, factory):
    teacher = factory.user('Teacher')
    assert manual_add_availability_block(cursor, teacher['faculty_id'], 'Monday', NINE, TEN) is None


def test_manual_add_inside_an_available_window_is_allowed(cursor, factory):
    teacher = factory.user('Teacher')
    _availability(factory, teacher['faculty_id'], 1, time(8), time(12))
    assert manual_add_availability_block(cursor, teacher['faculty_id'], 'Monday', NINE, TEN) is None


def test_manual_add_outside_the_available_window_is_blocked(cursor, factory):
    teacher = factory.user('Teacher')
    _availability(factory, teacher['faculty_id'], 1, time(14), time(16))
    message = manual_add_availability_block(cursor, teacher['faculty_id'], 'Monday', NINE, TEN)
    assert message and 'outside' in message


def test_manual_add_rejects_an_unknown_day(cursor, factory):
    teacher = factory.user('Teacher')
    assert manual_add_availability_block(cursor, teacher['faculty_id'], 'Someday', NINE, TEN)


def test_recurring_holiday_blocks_its_weekday_for_its_program(cursor, factory):
    factory.insert('institution_holidays', day_of_week='Saturday', name='Weekly off',
                   applies_to_program='UG', is_recurring=1)
    assert recurring_holiday_blocks_day(cursor, 'UG', 'Saturday') is True
    assert recurring_holiday_blocks_day(cursor, 'PG', 'Saturday') is False
    assert recurring_holiday_blocks_day(cursor, 'UG', 'Friday') is False


def test_a_holiday_for_both_programs_blocks_each(cursor, factory):
    factory.insert('institution_holidays', day_of_week='Wednesday', name='Midweek',
                   applies_to_program='Both', is_recurring=1)
    assert recurring_holiday_blocks_day(cursor, 'UG', 'Wednesday') is True
    assert recurring_holiday_blocks_day(cursor, 'PG', 'Wednesday') is True


def test_recurring_holiday_taken_ignores_the_row_being_edited(cursor, factory):
    holiday = factory.insert('institution_holidays', day_of_week='Saturday', name='Weekly off',
                             applies_to_program='PG', is_recurring=1)
    assert recurring_holiday_taken(cursor, 'Saturday', 'PG', None) is True
    assert recurring_holiday_taken(cursor, 'Saturday', 'PG', holiday) is False
    assert recurring_holiday_taken(cursor, 'Saturday', 'UG', None) is False


def test_holidays_for_week_returns_recurring_and_dated_rows(cursor, factory):
    factory.insert('institution_holidays', day_of_week='Saturday', name='Weekly off',
                   applies_to_program='Both', is_recurring=1)
    factory.insert('institution_holidays', holiday_date=date(2026, 11, 11), name='Festival',
                   applies_to_program='UG', is_recurring=0)
    factory.insert('institution_holidays', holiday_date=date(2026, 11, 20), name='Next week',
                   applies_to_program='UG', is_recurring=0)
    factory.insert('institution_holidays', holiday_date=date(2026, 11, 12), name='PG only',
                   applies_to_program='PG', is_recurring=0)
    names = {row['name'] for row in holidays_for_week(cursor, 'UG', date(2026, 11, 9), date(2026, 11, 14))}
    assert names == {'Weekly off', 'Festival'}
