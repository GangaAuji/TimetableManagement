"""The joint CP-SAT solver on small, database-free problems.

Each test builds a Problem by hand and checks the rules the model
promises: every demand once, no teacher in two places, whole-cohort
sessions exclusive, lab batches and electives in parallel, a shared
elective in one common slot, rooms by kind and capacity.
"""

from collections import Counter, defaultdict
from datetime import time

import pytest

pytest.importorskip('ortools')

from services.timetable.joint_solver import Demand, Problem, solve  # noqa: E402

DAYS = ('Monday', 'Tuesday')
SLOTS = ((time(9), time(10)), (time(10), time(11)), (time(11), time(12)))
A, B = '1:1:1', '1:1:2'


def _demand(key, cohort, subject, kind='Theory', faculty=(100,), **extra):
    return Demand(
        key=key, cohorts=(cohort,) if isinstance(cohort, str) else tuple(cohort), subject_id=subject,
        subject_name=f'S{subject}', kind=kind, faculty_options=tuple(faculty),
        faculty_names={f: f'T{f}' for f in faculty}, **extra,
    )


def _cells(placements):
    return Counter((p.day, p.slot) for p in placements)


def test_every_demand_is_placed_once_and_a_teacher_is_never_double_booked():
    demands = [_demand(i, A, 1, faculty=(100,)) for i in range(1, 4)] + [_demand(i, B, 1, faculty=(100,)) for i in range(4, 7)]
    placements, unplaced, status = solve(Problem(demands=demands, days=DAYS, slots=SLOTS, time_limit=5))
    assert status in ('OPTIMAL', 'FEASIBLE') and unplaced == []
    assert sorted(p.demand.key for p in placements) == [1, 2, 3, 4, 5, 6]
    assert max(_cells(placements).values()) == 1, 'teacher 100 teaches both cohorts, so no two sessions share a slot'


def test_whole_cohort_sessions_never_share_a_slot_but_lab_batches_do():
    demands = [
        _demand(1, A, 1, faculty=(100,)),
        _demand(2, A, 2, faculty=(101,)),
        _demand(3, A, 3, 'Practical', faculty=(102,), lab_batch_group_id=10, lab_batch_name='A1', group_size=20),
        _demand(4, A, 3, 'Practical', faculty=(103,), lab_batch_group_id=11, lab_batch_name='A2', group_size=20),
    ]
    labs = [{'id': 1, 'room_number': 'L1', 'capacity': 25}, {'id': 2, 'room_number': 'L2', 'capacity': 25}]
    problem = Problem(demands=demands, days=('Monday',), slots=SLOTS, labs=labs, rooms=[{'id': 3, 'room_number': 'R1', 'capacity': 60}], time_limit=5)
    placements, unplaced, status = solve(problem)
    assert unplaced == [], status
    by_cell = defaultdict(list)
    for p in placements:
        by_cell[(p.day, p.slot)].append(p.demand)
    # Two theory hours and two batch practicals fit in three slots only when the batches run in parallel.
    assert len(by_cell) == 3
    parallel = [cell for cell, ds in by_cell.items() if len(ds) == 2]
    assert len(parallel) == 1
    assert {d.lab_batch_group_id for d in by_cell[parallel[0]]} == {10, 11}
    rooms = {p.room['id'] for p in placements if p.demand.kind == 'Practical'}
    assert rooms == {1, 2}
    assert all(p.room['id'] == 3 for p in placements if p.demand.kind == 'Theory')


def test_a_whole_cohort_session_excludes_a_batch_in_the_same_slot():
    demands = [
        _demand(1, A, 1, faculty=(100,)),
        _demand(2, A, 3, 'Practical', faculty=(102,), lab_batch_group_id=10),
    ]
    placements, unplaced, status = solve(Problem(demands=demands, days=('Monday',), slots=SLOTS[:1], time_limit=5))
    assert len(placements) == 1 and len(unplaced) == 1, 'one slot cannot hold a whole-cohort hour and a batch'


def test_electives_run_in_parallel_and_a_shared_elective_takes_one_common_slot():
    demands = [
        _demand(1, A, 1, faculty=(100,)),
        _demand(2, B, 2, faculty=(101,)),
        _demand(3, (A, B), 50, faculty=(110,), is_elective=True),   # elective taught to both divisions together
        _demand(4, (A, B), 51, faculty=(111,), is_elective=True),   # a second elective: students pick one
    ]
    placements, unplaced, status = solve(Problem(demands=demands, days=('Monday',), slots=SLOTS[:2], time_limit=5))
    assert unplaced == [], status
    cells = {p.demand.key: (p.day, p.slot) for p in placements}
    assert cells[3] == cells[4], 'different electives may share the slot'
    assert cells[1] == cells[2] and cells[1] != cells[3], 'the core hours of A and B share the other slot'


def test_busy_faculty_and_other_cohorts_rows_are_respected():
    demands = [_demand(1, A, 1, faculty=(100,)), _demand(2, A, 2, faculty=(100,))]
    busy = {100: {'Monday': {0}}}
    placements, unplaced, status = solve(Problem(demands=demands, days=('Monday',), slots=SLOTS, faculty_busy=busy, time_limit=5))
    assert unplaced == []
    assert {p.slot for p in placements} == {1, 2}


def test_a_subject_meets_at_most_twice_a_day_and_once_when_it_can():
    demands = [_demand(i, A, 1, faculty=(100,)) for i in range(1, 4)]
    placements, unplaced, status = solve(Problem(demands=demands, days=DAYS, slots=SLOTS, time_limit=5))
    assert unplaced == []
    per_day = Counter(p.day for p in placements)
    assert max(per_day.values()) <= 2
    assert set(per_day) == set(DAYS), 'three hours over two days spread out rather than stacking'


def test_a_demand_restricted_to_its_cohort_days_stays_on_them():
    demands = [_demand(1, A, 1, faculty=(100,), days=('Tuesday',))]
    placements, unplaced, status = solve(Problem(demands=demands, days=DAYS, slots=SLOTS, time_limit=5))
    assert unplaced == [] and placements[0].day == 'Tuesday'


def test_more_practicals_than_labs_leaves_one_unplaced():
    demands = [
        _demand(1, A, 3, 'Practical', faculty=(102,), lab_batch_group_id=10),
        _demand(2, A, 3, 'Practical', faculty=(103,), lab_batch_group_id=11),
    ]
    problem = Problem(demands=demands, days=('Monday',), slots=SLOTS[:1], labs=[{'id': 1, 'room_number': 'L1', 'capacity': 30}], time_limit=5)
    placements, unplaced, status = solve(problem)
    assert len(placements) == 1 and len(unplaced) == 1
