"""Workload norms (J5): the document, the per-designation lookup, the `workload_max` rule and the solvers' cap.

Database-free: the norms document is validated in memory, `rules.evaluate` is fed rows directly and
the joint solver takes a hand-built Problem with `workload` limits.
"""

from datetime import time

import pytest

from services import workload
from services.timetable import rules as rule_set


def _row(day, start, end, faculty=100, subject=1):
    return {
        'day': day, 'start_time': start, 'end_time': end, 'faculty_id': faculty, 'faculty_name': f'T{faculty}',
        'subject_id': subject, 'subject_name': f'S{subject}', 'room_id': None, 'session_type': 'Theory', 'lab_batch_group_id': None,
    }


def _only(name, weight=1):
    rules = {key: {**values, 'weight': 0} for key, values in rule_set.default_rules().items()}
    rules[name]['weight'] = weight
    return rules


SLOTS = ['09:00', '10:00', '11:00', '12:00', '13:00']


# The norms document ------------------------------------------------------------------------------

def test_clean_norms_normalises_and_rejects_bad_hours():
    good = workload.clean_norms({'default': {'min': 12, 'max': 18.0}, 'by_designation': {' Professor ': {'max': 14}, 'Guest': {}}})
    assert good == {'default': {'min': 12, 'max': 18}, 'by_designation': {'Professor': {'min': None, 'max': 14}}}
    assert workload.clean_norms({}) == {'default': {'min': None, 'max': None}, 'by_designation': {}}
    for bad in ({'default': {'min': 20, 'max': 10}}, {'default': {'max': 61}}, {'default': {'max': -1}},
                {'default': {'max': True}}, {'default': {'hours': 3}}, {'by_designation': {'': {'max': 1}}},
                {'by_designation': {'x' * 51: {'max': 1}}}, {'by_designation': [1]}, {'other': 1}, 'x',
                {'by_designation': {f'D{i}': {'max': 1} for i in range(41)}}):
        with pytest.raises(ValueError):
            workload.clean_norms(bad)


def test_norm_for_prefers_the_designation_case_insensitively_then_the_default():
    norms = {'default': {'min': 12, 'max': 18}, 'by_designation': {'Professor': {'min': 8, 'max': 14}}}
    assert workload.norm_for(norms, 'professor') == (8, 14)
    assert workload.norm_for(norms, 'Assistant Professor') == (12, 18)
    assert workload.norm_for(norms, None) == (12, 18)
    assert workload.norm_for({'default': {'min': None, 'max': None}, 'by_designation': {}}, 'Professor') == (None, None)


def test_status_of_flags_under_and_over_and_knows_when_there_is_no_norm():
    assert workload.status_of(10, 12, 18) == 'under'
    assert workload.status_of(18, 12, 18) == 'ok'
    assert workload.status_of(18.5, 12, 18) == 'over'
    assert workload.status_of(0, None, 18) == 'ok'
    assert workload.status_of(30, None, None) == 'no_norm'


def test_rules_loader_ignores_private_documents_and_saving_keeps_them():
    """`_workload` lives in the same JSON row as the rules; neither side may clobber the other."""
    class Cursor:
        def __init__(self):
            self.saved = None
            self.row = {'rules_json': '{"spread_subject": {"weight": 4}, "_workload": {"default": {"max": 16}}}'}

        def execute(self, sql, params=()):
            self.sql, self.params = ' '.join(sql.split()), params
            if self.sql.startswith('INSERT'):
                self.saved = params[1]

        def fetchone(self):
            if 'information_schema' in self.sql:
                return {'n': 1}
            return self.row

    cursor = Cursor()
    rules, stored = rule_set.load_rules(cursor, 1)
    assert stored and rules['spread_subject']['weight'] == 4 and '_workload' not in rules
    rule_set.save_rules(cursor, 1, rule_set.clean_rules({'spread_subject': {'weight': 7}}), 5)
    assert '"_workload": {"default": {"max": 16}}' in cursor.saved and '"spread_subject": {"weight": 7}' in cursor.saved
    norms, stored = workload.load_norms(cursor, 1)
    assert stored and norms['default'] == {'min': None, 'max': 16}
    with pytest.raises(ValueError):
        rule_set.save_private(cursor, 1, 'workload', {})


# The workload_max rule ---------------------------------------------------------------------------

def test_workload_max_rule_counts_hours_over_the_norm_across_cohorts():
    rows = [_row('Monday', SLOTS[i], SLOTS[i + 1]) for i in range(4)]       # 4 hours here
    external = [_row('Tuesday', SLOTS[i], SLOTS[i + 1], subject=9) for i in range(3)]   # 3 more elsewhere
    rules = _only('workload_max', 6)
    assert rule_set.evaluate(rows, rules, slot_starts=SLOTS, external=external)['cost'] == 0, 'no norms -> no rule'
    report = rule_set.evaluate(rows, rules, slot_starts=SLOTS, external=external, norms={100: 5})
    assert report['cost'] == 12 and report['violations'][0]['detail'] == '7 hours this week (norm 5)'
    assert report['violations'][0]['rule'] == 'workload_max' and report['violations'][0]['faculty_id'] == 100
    # Fixed hours outside the solve are added; teaching rows can be given separately from the busy blocks.
    report = rule_set.evaluate(rows, rules, slot_starts=SLOTS, external=external, norms={100: 5}, norm_external=[], norm_fixed_hours={100: 1.5})
    assert report['cost'] == 6 and report['violations'][0]['detail'] == '5.5 hours this week (norm 5)'
    assert rule_set.evaluate(rows, rules, slot_starts=SLOTS, norms={100: 4})['cost'] == 0
    assert rule_set.evaluate(rows, rules, slot_starts=SLOTS, norms={200: 1})['cost'] == 0, 'other teachers do not matter'


# The joint solver --------------------------------------------------------------------------------

def test_joint_solver_caps_a_teacher_at_the_norm_when_hard_and_pays_when_soft():
    pytest.importorskip('ortools')
    from services.timetable.joint_solver import Demand, Problem, solve

    slots = tuple((time(9 + i), time(10 + i)) for i in range(5))
    demands = [
        Demand(key=i, cohorts=('1:1:1',), subject_id=i, subject_name=f'S{i}', kind='Theory', faculty_options=(100,), faculty_names={100: 'T'})
        for i in range(1, 5)
    ]
    hard = Problem(demands=demands, days=('Monday',), slots=slots, time_limit=5,
                   workload={100: {'max_hours': 5, 'fixed_hours': 2.5}}, workload_hard=True)
    placements, unplaced, status = solve(hard)
    assert len(placements) == 2 and len(unplaced) == 2, 'five hours minus 2.5 fixed leaves two whole slots'

    rules = _only('workload_max', 6)
    rules['spread_subject']['weight'] = 1
    soft = Problem(demands=demands, days=('Monday',), slots=slots, time_limit=5, rules=rules,
                   workload={100: {'max_hours': 5, 'fixed_hours': 2.5}})
    placements, unplaced, status = solve(soft)
    assert len(placements) == 4 and unplaced == [], 'soft: everything is placed, the excess is a cost'

    free = Problem(demands=demands, days=('Monday',), slots=slots, time_limit=5, workload={100: {'max_hours': 40, 'fixed_hours': 0}}, workload_hard=True)
    placements, unplaced, status = solve(free)
    assert len(placements) == 4


def test_registry_has_the_workload_rule_with_a_faculty_scope():
    rule = rule_set.BY_NAME['workload_max']
    assert rule.scope == 'faculty' and rule.default == 6 and 'workload_max' in rule_set.NAMES
    assert rule_set.legacy_rules()['workload_max']['weight'] == 0
