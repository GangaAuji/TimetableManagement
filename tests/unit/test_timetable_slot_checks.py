"""check_slot() is the one rule book for a manual slot: add_slot must refuse exactly what it reports first,
and the grid's pre-check (first_only=False) must list every rule the slot breaks, in the same order."""

import pytest

from services import timetable_slots as slots
from services.timetable import versions


class _Cursor:
    """Answers `execute` from a {substring: rows} table; anything else returns no rows."""

    def __init__(self, rows=None):
        self.rows = rows or {}
        self.statements = []
        self._result = []

    def execute(self, statement, params=()):
        self.statements.append((' '.join(statement.split()), tuple(params)))
        key = next((key for key in self.rows if key in statement), None)
        self._result = list(self.rows[key]) if key else []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


SLOT = {
    'course_id': 1, 'class_id': 2, 'division_id': 3, 'subject_id': 4, 'day': 'Monday',
    'start_time': '10:00:00', 'end_time': '11:00:00', 'faculty_id': 9, 'room_id': 5,
}


def _arrange(monkeypatch, *, allocated=True, holiday=False, class_busy=False, faculty_busy=False, unavailable=None, room_busy=False):
    monkeypatch.setattr(slots, 'fetch_allocated_faculty', lambda cursor, class_id, division_id, subject_id: {'faculty_id': 9} if allocated else None)
    monkeypatch.setattr(slots, 'fetch_course_program', lambda cursor, course_id: {'program': 'UG'})
    monkeypatch.setattr(slots, 'recurring_holiday_blocks_day', lambda cursor, program, day: holiday)
    monkeypatch.setattr(slots, 'fetch_class_overlap', lambda cursor, *args, exclude_id=None, **kwargs: class_busy)
    monkeypatch.setattr(slots, 'fetch_faculty_overlap', lambda cursor, *args, exclude_id=None: faculty_busy)
    monkeypatch.setattr(slots, 'manual_add_availability_block', lambda cursor, faculty_id, day, start, end: unavailable)
    rows = {'lab_batch_groups': [{'course_id': 99, 'class_id': 2, 'division_id': 3, 'is_active': 1}]}
    if room_busy:
        rows['room_id = %s'] = [{'1': 1}]
    return _Cursor(rows)


CASES = [
    pytest.param({}, {}, [], id='clean'),
    pytest.param({'start_time': '11:00:00', 'end_time': '10:00:00'}, {'class_busy': True}, ['slot_time_invalid'], id='time-order-stops-early'),
    pytest.param({'faculty_id': None}, {'allocated': False, 'class_busy': True}, ['slot_no_faculty'], id='no-teacher-stops-early'),
    pytest.param({}, {'holiday': True, 'class_busy': True}, ['slot_holiday', 'slot_class_busy'], id='holiday-and-class'),
    pytest.param(
        {'lab_batch_group_id': 7},
        {'class_busy': True, 'faculty_busy': True, 'unavailable': 'On leave.', 'room_busy': True},
        ['slot_batch_invalid', 'slot_batch_busy', 'slot_faculty_busy', 'slot_faculty_unavailable', 'slot_room_busy'],
        id='everything-wrong',
    ),
    pytest.param({}, {'room_busy': True}, ['slot_room_busy'], id='room-only'),
]


@pytest.mark.parametrize('overrides, arrangement, expected', CASES)
def test_check_slot_lists_every_broken_rule_and_add_slot_raises_the_first(monkeypatch, overrides, arrangement, expected):
    cursor = _arrange(monkeypatch, **arrangement)
    slot = {**SLOT, **overrides}

    faculty_id, errors = slots.check_slot(cursor, **slot)
    assert [err.code for err in errors] == expected
    assert all(isinstance(err, slots.SlotError) and str(err) for err in errors)
    if expected != ['slot_no_faculty']:
        assert faculty_id == 9, 'the allocated teacher is used when none is given'

    _first, first_errors = slots.check_slot(cursor, **slot, first_only=True)
    assert [err.code for err in first_errors] == expected[:1]

    inserted = []
    monkeypatch.setattr(slots, 'insert_timetable_session', lambda cursor, values, batch, room, version_id=None: inserted.append((values, batch, room, version_id)) or 77)
    monkeypatch.setattr(versions, 'active', lambda cursor: False)
    import services.webhooks as webhooks

    monkeypatch.setattr(webhooks, 'on_timetable_published', lambda *args, **kwargs: None)
    if expected:
        with pytest.raises(slots.SlotError) as caught:
            slots.add_slot(cursor, **slot)
        assert caught.value.code == expected[0]
        assert inserted == []
    else:
        assert slots.add_slot(cursor, **slot) == 77
        assert inserted == [((1, 2, 3, 4, 9, 'Monday', '10:00:00', '11:00:00'), None, 5, None)]


def test_exclude_id_reaches_the_overlap_queries_and_the_room_check(monkeypatch):
    seen = {}

    def class_overlap(cursor, *args, exclude_id=None, **kwargs):
        seen['class'] = exclude_id
        return False

    def faculty_overlap(cursor, *args, exclude_id=None):
        seen['faculty'] = exclude_id
        return False

    cursor = _arrange(monkeypatch)
    monkeypatch.setattr(slots, 'fetch_class_overlap', class_overlap)
    monkeypatch.setattr(slots, 'fetch_faculty_overlap', faculty_overlap)
    _faculty, errors = slots.check_slot(cursor, **SLOT, exclude_id=42)
    assert errors == [] and seen == {'class': 42, 'faculty': 42}
    [(room_query, params)] = [(statement, params) for statement, params in cursor.statements if 'room_id = %s' in statement]
    assert 'AND id <> %s' in room_query and params[-1] == 42


def test_slot_cost_is_none_when_preferences_are_off(monkeypatch):
    from services.timetable import rules

    monkeypatch.setattr(rules, 'institution_for_course', lambda cursor, course_id: 1)
    monkeypatch.setattr(rules, 'effective_rules', lambda cursor, institution_id, settings=None: (rules.default_rules(), False))
    assert slots.slot_cost(_Cursor(), **SLOT) is None


def test_slot_cost_reports_only_the_violations_the_candidate_introduces(monkeypatch):
    from services.timetable import rules

    monkeypatch.setattr(rules, 'institution_for_course', lambda cursor, course_id: 1)
    monkeypatch.setattr(rules, 'effective_rules', lambda cursor, institution_id, settings=None: (rules.default_rules(), True))
    monkeypatch.setattr(rules, 'load_preferences', lambda cursor, faculty_ids: {})
    from datetime import time

    existing = {
        'id': 1, 'day_of_week': 'Monday', 'start_time': time(9, 0), 'end_time': time(10, 0), 'subject_id': 4, 'faculty_id': 9,
        'room_id': 5, 'lab_batch_group_id': None, 'subject_name': 'Physics', 'session_type': 'Theory', 'faculty_name': 'T',
    }
    cursor = _Cursor({
        't.course_id = %s AND t.class_id = %s AND t.division_id = %s': [existing],
        'FROM subjects WHERE id': [{'name': 'Physics', 'subject_type': 'Theory'}],
        'FROM faculty WHERE user_id': [{'name': 'T'}],
    })
    # Physics again on Monday: a repeat of the subject for the same class on one day.
    cost = slots.slot_cost(cursor, **{**SLOT, 'start_time': '11:00:00', 'end_time': '12:00:00'})
    assert cost['cost_after'] > cost['cost_before'] and cost['delta'] == cost['cost_after'] - cost['cost_before']
    rules_hit = {violation['rule'] for violation in cost['violations']}
    assert 'spread_subject' in rules_hit
    assert all(violation['day'] == 'Monday' for violation in cost['violations'])

    # The same hour on Tuesday introduces no cohort violation beyond the slot-index nudge.
    clean = slots.slot_cost(cursor, **{**SLOT, 'day': 'Tuesday', 'start_time': '09:00:00', 'end_time': '10:00:00'})
    assert clean['delta'] <= cost['delta'] and 'spread_subject' not in {violation['rule'] for violation in clean['violations']}


def test_hhmm_accepts_the_shapes_mysql_returns():
    from datetime import time, timedelta

    assert slots._hhmm(timedelta(hours=9, minutes=5)) == '09:05'
    assert slots._hhmm(time(14, 30)) == '14:30'
    assert slots._hhmm('08:00:00') == '08:00'
    assert slots._hhmm(None) == ''
