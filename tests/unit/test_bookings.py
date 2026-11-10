"""Room bookings (Phase J4): the date and weekday rules, the week usage the solvers read, the conflict
rules and revision 0018 — on hand-built rows, no database."""

import importlib.util
from datetime import date, time, timedelta
from pathlib import Path

import pytest

from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision
from services import bookings


class _Cursor:
    """Answers `execute` from a {substring: rows} table; anything else returns no rows."""

    def __init__(self, rows=None):
        self.rows = rows or {}
        self.statements = []
        self._result = []

    def execute(self, statement, params=()):
        flat = ' '.join(statement.split())
        self.statements.append((flat, tuple(params)))
        key = next((key for key in self.rows if key in flat), None)
        self._result = list(self.rows[key]) if key else []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


def _booking(*, room=5, title='Seminar', booking_date=None, day=None, until=None, start=time(10, 0), end=time(12, 0), bid=1):
    return {
        'id': bid, 'room_id': room, 'title': title, 'kind': 'event', 'booking_date': booking_date, 'day_of_week': day,
        'repeat_until': until, 'start_time': start, 'end_time': end,
    }


def _on(monkeypatch, active=True):
    monkeypatch.setattr(bookings, 'active', lambda cursor: active)


# Date rules ------------------------------------------------------------------------------------

def test_applies_on_handles_dated_and_weekly_bookings_with_a_window():
    monday = date(2026, 11, 9)
    assert bookings.applies_on(_booking(booking_date=monday), monday)
    assert not bookings.applies_on(_booking(booking_date=monday), monday + timedelta(days=7))
    weekly = _booking(day='Monday', until=date(2026, 11, 16))
    assert bookings.applies_on(weekly, monday) and bookings.applies_on(weekly, monday + timedelta(days=7))
    assert not bookings.applies_on(weekly, monday + timedelta(days=14)), 'past repeat_until'
    assert not bookings.applies_on(weekly, monday + timedelta(days=1)), 'other weekday'
    assert bookings.applies_on(_booking(day='Monday'), monday + timedelta(days=700)), 'open-ended'


def test_as_time_accepts_the_shapes_mysql_and_json_use():
    assert bookings.as_time(timedelta(hours=9, minutes=30)) == time(9, 30)
    assert bookings.as_time('14:05:00') == time(14, 5) and bookings.as_time('14:05') == time(14, 5)
    assert bookings.hhmm(time(8, 0)) == '08:00'
    with pytest.raises(ValueError):
        bookings.as_time('noon')


# Week usage for the solvers ----------------------------------------------------------------------

def test_room_usage_for_week_merges_dated_and_weekly_bookings_per_day(monkeypatch):
    _on(monkeypatch)
    week = {'Monday': date(2026, 11, 9), 'Tuesday': date(2026, 11, 10), 'Wednesday': date(2026, 11, 11)}
    cursor = _Cursor({'FROM bookings b WHERE': [
        _booking(room=5, day='Monday'),                                               # weekly, open
        _booking(room=6, day='Tuesday', until=date(2026, 11, 3), bid=2),              # weekly, expired
        _booking(room=7, booking_date=date(2026, 11, 11), start=time(13, 0), end=time(15, 0), bid=3),   # dated in week
        _booking(room=8, booking_date=date(2026, 11, 18), bid=4),                      # dated next week
        _booking(room=5, booking_date=date(2026, 11, 9), start=time(14, 0), end=time(16, 0), bid=5),    # same room, same day
    ]})
    usage = bookings.room_usage_for_week(cursor, week)
    assert usage == {
        'Monday': {5: [(time(10, 0), time(12, 0)), (time(14, 0), time(16, 0))]},
        'Wednesday': {7: [(time(13, 0), time(15, 0))]},
    }
    statement, params = cursor.statements[-1]
    assert "b.status = 'approved'" in statement and set(week) <= set(params) and date(2026, 11, 9) in params


def test_room_usage_is_empty_and_reads_nothing_when_bookings_are_off(monkeypatch):
    _on(monkeypatch, active=False)
    cursor = _Cursor({'FROM bookings b WHERE': [_booking(day='Monday')]})
    assert bookings.room_usage_for_week(cursor, {'Monday': date(2026, 11, 9)}) == {}
    assert cursor.statements == []
    assert bookings.booked_room(cursor, 5, 'Monday', '10:00:00', '11:00:00') is None


def test_booked_room_matches_a_weekly_slot_only_against_weekly_bookings_in_force(monkeypatch):
    _on(monkeypatch)
    rows = [
        _booking(room=5, booking_date=date.today() + timedelta(days=7), bid=1),                     # dated: not for a weekly slot
        _booking(room=5, day='Monday', until=date.today() - timedelta(days=1), bid=2),             # weekly, expired
        _booking(room=5, day='Monday', start=time(12, 0), end=time(13, 0), bid=3),                  # weekly, no overlap
        _booking(room=5, day='Monday', title='Staff meeting', bid=4),                              # weekly, overlaps
    ]
    cursor = _Cursor({'FROM bookings b WHERE': rows})
    found = bookings.booked_room(cursor, 5, 'Monday', '11:00:00', '11:45:00')
    assert found['title'] == 'Staff meeting'
    assert bookings.booked_room(cursor, 5, 'Monday', '13:00:00', '14:00:00') is None
    # With a date, the dated booking on that date counts too.
    dated = _Cursor({'FROM bookings b WHERE': [rows[0]]})
    assert bookings.booked_room(dated, 5, 'Monday', '10:00:00', '11:00:00', on_date=date.today() + timedelta(days=7)) is not None
    assert bookings.booked_room(dated, 5, 'Monday', '10:00:00', '11:00:00', on_date=date.today()) is None


# Conflicts between bookings --------------------------------------------------------------------------

def test_booking_conflicts_apply_the_window_rules_in_both_directions():
    monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)   # next Monday
    rows = [
        _booking(room=5, day='Monday', bid=1),                                       # weekly open
        _booking(room=5, booking_date=monday, start=time(11, 0), end=time(13, 0), bid=2),
        _booking(room=5, day='Monday', until=date.today() - timedelta(days=1), bid=3),   # weekly, already over
        _booking(room=5, booking_date=monday - timedelta(days=14), bid=4),           # dated, in the past
    ]
    cursor = _Cursor({'FROM bookings b WHERE': rows})
    dated = bookings.booking_conflicts(cursor, 5, day='Monday', start_time='10:00', end_time='11:30', booking_date=monday)
    assert [row['id'] for row in dated] == [1, 2]
    weekly = bookings.booking_conflicts(cursor, 5, day='Monday', start_time='10:00', end_time='11:30')
    assert [row['id'] for row in weekly] == [1, 2], 'a new weekly booking meets the open weekly one and the future dated one'
    bounded = bookings.booking_conflicts(cursor, 5, day='Monday', start_time='10:00', end_time='11:30', repeat_until=monday - timedelta(days=1))
    assert [row['id'] for row in bounded] == [1], 'a weekly booking that ends before the dated one does not meet it'
    excluded = bookings.booking_conflicts(cursor, 5, day='Monday', start_time='10:00', end_time='11:30', booking_date=monday, exclude_id=1)
    assert [row['id'] for row in excluded] == [2]
    assert bookings.booking_conflicts(cursor, 5, day='Monday', start_time='13:00', end_time='14:00', booking_date=monday) == []


def test_create_validates_before_touching_the_database():
    cursor = _Cursor()
    base = {'institution_id': 1, 'room_id': 5, 'title': 'X', 'kind': 'event', 'start_time': '10:00', 'end_time': '11:00'}
    with pytest.raises(bookings.BookingError) as both:
        bookings.create(cursor, **base, booking_date=date(2026, 11, 9), day_of_week='Monday')
    assert both.value.code == 'booking_when_invalid'
    with pytest.raises(bookings.BookingError) as neither:
        bookings.create(cursor, **base)
    assert neither.value.code == 'booking_when_invalid'
    with pytest.raises(bookings.BookingError) as kind:
        bookings.create(cursor, **{**base, 'kind': 'party'}, day_of_week='Monday')
    assert kind.value.code == 'booking_kind_invalid'
    with pytest.raises(bookings.BookingError) as order:
        bookings.create(cursor, **{**base, 'end_time': '09:00'}, day_of_week='Monday')
    assert order.value.code == 'booking_time_invalid'
    assert cursor.statements == []
    with pytest.raises(bookings.BookingError) as room:
        bookings.create(cursor, **base, day_of_week='Monday')
    assert room.value.code == 'booking_room_invalid' and room.value.alternatives == []


# Revision 0018 -------------------------------------------------------------------------------------

def test_0018_follows_0017_and_creates_only_what_is_missing():
    assert head_revision() >= '0018_bookings'
    path = Path(MIGRATIONS_DIR) / 'versions' / '0018_bookings.py'
    spec = importlib.util.spec_from_file_location('revision_0018', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == '0017_timetable_versions'
    assert [name for name, _, _ in module.OBJECTS] == ['bookings']
    [create] = module.upgrade_statements(set())
    assert 'CREATE TABLE bookings' in create and 'fk_bookings_room' in create and "status enum('requested','approved','rejected','cancelled')" in create
    assert module.upgrade_statements({'bookings'}) == []
    assert module.downgrade_statements({'bookings'}) == ['DROP TABLE bookings']


def test_capability_registry_has_bookings_off_by_default_with_approval_setting():
    from core.capabilities import BY_NAME

    capability = BY_NAME['bookings']
    assert capability.default is False and capability.phase == 'J4'
    assert capability.settings['requires_approval'] == ('bool', True)


def test_notification_kinds_include_booking_messages():
    from services.notifications import KINDS

    assert {'booking_request', 'booking_decision'} <= set(KINDS)
