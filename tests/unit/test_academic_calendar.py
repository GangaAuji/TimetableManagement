"""Academic calendar arithmetic, with no database.

A date is a teaching day when a teaching term covers it and no exam, break or internship term does.
Holidays are removed by the caller. With no terms configured, nothing is dropped.
"""

from datetime import date

from services.academic_calendar import kept_dates, teaching_day_list, teaching_weeks

MONDAY = date(2026, 11, 9)
SUNDAY = date(2026, 11, 15)
WEEK = [MONDAY + __import__('datetime').timedelta(days=offset) for offset in range(7)]


def _term(kind, start, end, name=''):
    return {'kind': kind, 'start': start, 'end': end, 'name': name}


def test_an_unconfigured_calendar_keeps_every_date():
    assert kept_dates(WEEK, [], configured=False) == set(WEEK)
    assert kept_dates(WEEK, [_term('exam', MONDAY, MONDAY)], configured=False) == set(WEEK)


def test_exam_and_holiday_days_drop_out_of_a_teaching_term():
    terms = [
        _term('teaching', MONDAY, SUNDAY, 'Odd semester'),
        _term('exam', date(2026, 11, 12), date(2026, 11, 12)),   # Thursday
    ]
    holiday = date(2026, 11, 11)   # Wednesday
    assert teaching_day_list(MONDAY, SUNDAY, terms, holidays=[holiday]) == [
        MONDAY, date(2026, 11, 10), date(2026, 11, 13), date(2026, 11, 14), SUNDAY,
    ]
    weeks = teaching_weeks(terms, holidays=[holiday])
    assert weeks == [{'name': 'Odd semester', 'week_start': MONDAY, 'teaching_days': 5}]


def test_a_break_wins_over_a_teaching_term_on_the_same_dates():
    terms = [_term('teaching', MONDAY, SUNDAY), _term('break', MONDAY, date(2026, 11, 10))]
    assert kept_dates(WEEK, terms, configured=True) == set(WEEK[2:])


def test_dates_outside_every_term_are_dropped_once_the_calendar_is_configured():
    terms = [_term('teaching', MONDAY, date(2026, 11, 10))]
    assert kept_dates(WEEK, terms, configured=True) == {MONDAY, date(2026, 11, 10)}


def test_teaching_weeks_skip_a_week_an_exam_term_covers_completely():
    terms = [
        _term('teaching', date(2026, 11, 9), date(2026, 11, 20), 'Term'),
        _term('exam', date(2026, 11, 16), date(2026, 11, 20)),
    ]
    weeks = teaching_weeks(terms)
    assert [item['week_start'] for item in weeks] == [date(2026, 11, 9)]
    assert weeks[0]['teaching_days'] == 7   # Mon 9 to Sun 15; the exam week of the 16th drops out
