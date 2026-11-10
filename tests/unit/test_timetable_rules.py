"""Soft timetable rules (services/timetable/rules.py): the registry and the legacy set, validation,
the evaluator rule by rule, the quality model thresholds, the joint solver paying for rules and
preferences, and revision 0016. No live database."""

import importlib.util
from datetime import time
from pathlib import Path

import pytest

from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision
from services.timetable import rules as rule_set


def _row(day, start, end, faculty=100, subject=1, room=None, kind='Theory', batch=None, name='T'):
    return {
        'day': day, 'start_time': start, 'end_time': end, 'faculty_id': faculty, 'faculty_name': name,
        'subject_id': subject, 'subject_name': f'S{subject}', 'room_id': room, 'session_type': kind, 'lab_batch_group_id': batch,
    }


SLOTS = ['09:00', '10:00', '11:00', '12:00', '13:00', '14:00']


def _only(name, weight=1, **params):
    rules = {key: {**values, 'weight': 0} for key, values in rule_set.default_rules().items()}
    rules[name]['weight'] = weight
    rules[name].update(params)
    return rules


# registry and rule sets

def test_defaults_are_complete_and_legacy_is_the_old_objective():
    defaults = rule_set.default_rules()
    assert set(defaults) == set(rule_set.NAMES)
    assert defaults['max_consecutive_hours'] == {'weight': 6, 'hours': 3}
    legacy = rule_set.legacy_rules()
    assert {name: values['weight'] for name, values in legacy.items() if values['weight']} == {'spread_subject': 10, 'prefer_early': 1}


def test_clean_rules_validates_weights_and_params():
    full = rule_set.clean_rules({'spread_subject': {'weight': 0}})
    assert full['spread_subject']['weight'] == 0 and full['prefer_early']['weight'] == 1   # the rest default
    partial = rule_set.clean_rules({'lunch_window': {'start': '12:30', 'end': '13:30'}}, partial=True)
    assert partial == {'lunch_window': {'weight': 3, 'start': '12:30', 'end': '13:30'}}
    for bad in ({'nope': {'weight': 1}}, {'spread_subject': {'weight': 21}}, {'spread_subject': {'weight': True}},
                {'max_hours_per_day': {'hours': 0}}, {'lunch_window': {'start': '25:00'}}, {'spread_subject': 3}, 'x'):
        with pytest.raises(ValueError):
            rule_set.clean_rules(bad)
    assert rule_set.merge_rules(rule_set.default_rules(), partial)['lunch_window']['start'] == '12:30'


def test_clean_preferences_validates_windows():
    good = rule_set.clean_preferences([{'day': 'Monday', 'start_time': '09:00', 'end_time': '11:00', 'kind': 'avoid', 'weight': 4}])
    assert good == [{'day': 'Monday', 'start_time': '09:00', 'end_time': '11:00', 'kind': 'avoid', 'weight': 4, 'note': ''}]
    for bad in ([{'day': 'Funday', 'start_time': '09:00', 'end_time': '10:00', 'kind': 'avoid'}],
                [{'day': 'Monday', 'start_time': '10:00', 'end_time': '09:00', 'kind': 'avoid'}],
                [{'day': 'Monday', 'start_time': '09:00', 'end_time': '10:00', 'kind': 'maybe'}],
                [{'day': 'Monday', 'start_time': '09:00', 'end_time': '10:00', 'kind': 'avoid', 'weight': 9}],
                [{'day': 'Monday', 'start_time': '09:00', 'end_time': '10:00', 'kind': 'avoid', 'extra': 1}], 'x'):
        with pytest.raises(ValueError):
            rule_set.clean_preferences(bad)


# evaluate

def test_hours_per_day_and_consecutive_hours_count_the_excess():
    rows = [_row('Monday', SLOTS[i], SLOTS[i + 1]) for i in range(5)]      # 09-14, five back to back
    report = rule_set.evaluate(rows, _only('max_hours_per_day', 6, hours=4), slot_starts=SLOTS)
    assert report['cost'] == 6 and report['violations'][0]['detail'] == '5 hours on Monday (limit 4)'
    report = rule_set.evaluate(rows, _only('max_consecutive_hours', 2, hours=3), slot_starts=SLOTS)
    assert report['cost'] == 4 and report['violations'][0]['rule'] == 'max_consecutive_hours'
    # External load of the same teacher counts: two of ours plus three elsewhere.
    ours, theirs = rows[:2], [{**row, 'subject_id': 9} for row in rows[2:]]
    report = rule_set.evaluate(ours, _only('max_hours_per_day', 1, hours=4), slot_starts=SLOTS, external=theirs)
    assert report['cost'] == 1


def test_idle_gaps_for_students_and_faculty():
    rows = [_row('Monday', '09:00', '10:00'), _row('Monday', '12:00', '13:00')]
    assert rule_set.evaluate(rows, _only('idle_gaps_students', 4), slot_starts=SLOTS)['cost'] == 8
    assert rule_set.evaluate(rows, _only('idle_gaps_faculty', 2), slot_starts=SLOTS)['cost'] == 4
    # A different teacher in between leaves the students' gap but not the teachers'.
    rows.append(_row('Monday', '10:00', '11:00', faculty=200))
    assert rule_set.evaluate(rows, _only('idle_gaps_students', 1), slot_starts=SLOTS)['cost'] == 1
    assert rule_set.evaluate(rows, _only('idle_gaps_faculty', 1), slot_starts=SLOTS)['cost'] == 2


def test_room_changes_spread_and_contiguous_labs():
    rows = [_row('Monday', '09:00', '10:00', room=1), _row('Monday', '10:00', '11:00', room=2, subject=2), _row('Monday', '11:00', '12:00', room=2, subject=3)]
    assert rule_set.evaluate(rows, _only('room_changes', 1), slot_starts=SLOTS)['cost'] == 1
    twice = [_row('Monday', '09:00', '10:00'), _row('Monday', '11:00', '12:00')]
    assert rule_set.evaluate(twice, _only('spread_subject', 10), slot_starts=SLOTS)['cost'] == 10
    labs = [_row('Monday', '09:00', '10:00', kind='Practical'), _row('Monday', '11:00', '12:00', kind='Practical')]
    assert rule_set.evaluate(labs, _only('lab_blocks_contiguous', 4), slot_starts=SLOTS)['cost'] == 4
    labs[1]['start_time'], labs[1]['end_time'] = '10:00', '11:00'
    assert rule_set.evaluate(labs, _only('lab_blocks_contiguous', 4), slot_starts=SLOTS)['cost'] == 0


def test_late_then_early_lunch_window_and_prefer_early():
    rows = [_row('Monday', '14:00', '15:00'), _row('Tuesday', '09:00', '10:00')]
    report = rule_set.evaluate(rows, _only('no_first_hour_after_evening', 3), slot_starts=SLOTS)
    assert report['cost'] == 3 and report['violations'][0]['day'] == 'Tuesday'
    rows = [_row('Monday', '12:00', '13:00'), _row('Monday', '09:00', '10:00')]
    report = rule_set.evaluate(rows, _only('lunch_window', 3, start='12:30', end='13:30'), slot_starts=SLOTS)
    assert report['cost'] == 3 and report['violations'][0]['start_time'] == '12:00'
    assert rule_set.evaluate(rows, _only('lunch_window', 3), slot_starts=SLOTS)['cost'] == 0    # no window: off
    assert rule_set.evaluate(rows, _only('prefer_early', 1), slot_starts=SLOTS) == {'cost': 3, 'by_rule': {'prefer_early': 3}, 'bonus': 0, 'violations': []}


def test_preferences_cost_for_avoid_and_pay_back_for_preferred():
    rows = [_row('Monday', '09:00', '10:00'), _row('Monday', '13:00', '14:00')]
    prefs = {100: [
        {'day': 'Monday', 'start_time': '08:00', 'end_time': '10:00', 'kind': 'avoid', 'weight': 4, 'note': 'school run'},
        {'day': 'Monday', 'start_time': '13:00', 'end_time': '15:00', 'kind': 'preferred', 'weight': 2, 'note': ''},
    ]}
    report = rule_set.evaluate(rows, _only('faculty_preferences', 5), prefs, slot_starts=SLOTS)
    assert report['by_rule'] == {'faculty_preferences': 20} and report['bonus'] == 10 and report['cost'] == 10
    assert report['violations'][0]['detail'] == 'Asked to avoid 08:00-10:00 (school run)'
    assert rule_set.evaluate(rows, _only('faculty_preferences', 5), {}, slot_starts=SLOTS)['cost'] == 0


def test_evaluate_derives_slots_from_the_rows_when_not_given():
    rows = [_row('Monday', '09:00', '10:00'), _row('Monday', '11:00', '12:00', subject=2)]
    assert rule_set.evaluate(rows, _only('idle_gaps_students', 1))['cost'] == 0    # 10:00 is not a known slot


# quality model thresholds

def test_quality_model_takes_its_fatigue_thresholds_from_the_rules():
    from ml_models.features.timetable_features import extract_timetable_features

    rows = [_row('Monday', SLOTS[i], SLOTS[i + 1]) for i in range(4)]        # four back to back
    historical = extract_timetable_features(rows, [], [], [], {'Monday': 6})['faculty_fatigue']
    strict = extract_timetable_features(rows, [], [], [], {'Monday': 6}, rules=_only('max_consecutive_hours', 6, hours=2))['faculty_fatigue']
    relaxed = extract_timetable_features(rows, [], [], [], {'Monday': 6}, rules=_only('max_consecutive_hours', 6, hours=6))['faculty_fatigue']
    assert strict > historical > relaxed
    off = extract_timetable_features(rows, [], [], [], {'Monday': 6}, rules=_only('max_consecutive_hours', 0, hours=2))['faculty_fatigue']
    assert off == historical


# the joint solver pays for the rules

def _solver():
    pytest.importorskip('ortools')
    from services.timetable.joint_solver import Demand, Problem, solve
    return Demand, Problem, solve


def _demand(cls, key, cohort, subject, faculty=(100,), kind='Theory', **extra):
    return cls(key=key, cohorts=(cohort,), subject_id=subject, subject_name=f'S{subject}', kind=kind, faculty_options=tuple(faculty),
               faculty_names={f: f'T{f}' for f in faculty}, **extra)


def test_solver_avoids_a_teachers_avoid_window_when_the_rule_is_on():
    Demand, Problem, solve = _solver()
    slots = ((time(9), time(10)), (time(10), time(11)), (time(11), time(12)))
    demands = [_demand(Demand, 1, 'A', 1), _demand(Demand, 2, 'A', 2, faculty=(200,))]
    prefs = {100: [{'day': 'Monday', 'start_time': '09:00', 'end_time': '10:00', 'kind': 'avoid', 'weight': 5, 'note': ''}]}
    # Legacy rules: early slots win, so teacher 100 lands at 09:00 (first demand, lowest lateness).
    placements, _unplaced, status = solve(Problem(demands=demands, days=('Monday',), slots=slots, time_limit=5, rules=rule_set.legacy_rules(), preferences=prefs))
    assert status in ('OPTIMAL', 'FEASIBLE')
    by_teacher = {p.faculty_id: p.slot for p in placements}
    assert sorted(by_teacher.values()) == [0, 1]
    # With preferences weighted, teacher 100 moves off 09:00.
    rules = rule_set.default_rules()
    placements, _unplaced, status = solve(Problem(demands=demands, days=('Monday',), slots=slots, time_limit=5, rules=rules, preferences=prefs))
    assert status in ('OPTIMAL', 'FEASIBLE')
    by_teacher = {p.faculty_id: p.slot for p in placements}
    assert by_teacher[100] != 0 and by_teacher[200] == 0


def test_solver_closes_a_student_gap_when_idle_gaps_cost_more_than_lateness():
    Demand, Problem, solve = _solver()
    slots = ((time(9), time(10)), (time(10), time(11)), (time(11), time(12)))
    # Teacher 100 cannot teach at 10:00 (fixed busy); teacher 200 can teach anywhere.
    demands = [_demand(Demand, 1, 'A', 1, faculty=(100,)), _demand(Demand, 2, 'A', 2, faculty=(200,))]
    busy = {100: {'Monday': {1}}}
    rules = rule_set.default_rules()
    placements, _unplaced, status = solve(Problem(demands=demands, days=('Monday',), slots=slots, faculty_busy=busy, time_limit=5, rules=rules))
    assert status in ('OPTIMAL', 'FEASIBLE')
    assert sorted(p.slot for p in placements) == [0, 1], 'the two sessions are adjacent (no idle slot for students)'
    # Switch the gap rule off and make 09:00 forbidden for 200 as well: the solver no longer cares about the gap.
    rules['idle_gaps_students']['weight'] = 0
    rules['idle_gaps_faculty']['weight'] = 0
    busy = {100: {'Monday': {1}}, 200: {'Monday': {1}}}
    placements, _unplaced, status = solve(Problem(demands=demands, days=('Monday',), slots=slots, faculty_busy=busy, time_limit=5, rules=rules))
    assert sorted(p.slot for p in placements) == [0, 2]


def test_solver_spreads_consecutive_hours_when_the_limit_is_low():
    Demand, Problem, solve = _solver()
    slots = tuple((time(9 + i), time(10 + i)) for i in range(4))
    demands = [_demand(Demand, i, 'A', i) for i in range(1, 4)]          # one teacher, three hours
    rules = rule_set.default_rules()
    rules['max_consecutive_hours'] = {'weight': 20, 'hours': 2}
    rules['idle_gaps_students']['weight'] = 0
    rules['idle_gaps_faculty']['weight'] = 0
    placements, _unplaced, status = solve(Problem(demands=demands, days=('Monday',), slots=slots, time_limit=5, rules=rules))
    assert status in ('OPTIMAL', 'FEASIBLE')
    assert sorted(p.slot for p in placements) in ([0, 1, 3], [0, 2, 3]), 'three hours are never back to back'


# revision 0016

def _load_0016():
    path = Path(MIGRATIONS_DIR) / 'versions' / '0016_timetable_preferences.py'
    spec = importlib.util.spec_from_file_location('revision_0016', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Bind:
    def __init__(self, present):
        self.present = set(present)

    def execute(self, statement, params):
        return _Result((1,) if params['table'] in self.present else None)


def test_0016_follows_0015_and_creates_only_missing_tables(monkeypatch):
    assert head_revision() >= '0016_timetable_preferences'
    module = _load_0016()
    assert module.down_revision == '0015_capabilities'
    executed = []
    monkeypatch.setattr(module.op, 'execute', lambda statement: executed.append(statement))
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Bind({'faculty_preferences'}))
    module.upgrade()
    assert len(executed) == 1 and 'CREATE TABLE timetable_rules' in executed[0]
    executed.clear()
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Bind({'faculty_preferences', 'timetable_rules'}))
    module.upgrade()
    assert executed == []
    module.downgrade()
    assert executed == ['DROP TABLE `timetable_rules`', 'DROP TABLE `faculty_preferences`']
    assert 'REFERENCES faculty (user_id)' in module.FACULTY_PREFERENCES
