"""Exam timetable (CP-SAT via ortools).

`solve(problem)` is pure. It places each paper on one slot so that:

- two papers that share a student never share a slot (a core paper and a
  shared elective, or two cores of the same cohort);
- the rooms given to a paper cover its students after the seating gap
  (usable seats = capacity // (gap + 1), then an optional per-room cap);
- a room is used by one paper per slot;
- each used room has one invigilator who is free that slot, and nobody
  invigilates two rooms at once.

The objective spreads duties (lowest maximum) and prefers earlier slots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time

DEFAULT_TIME_LIMIT = 10.0


class SolverUnavailable(RuntimeError):
    """ortools is not installed."""


@dataclass
class Paper:
    key: int
    name: str
    students: frozenset


@dataclass
class Slot:
    index: int
    on: date
    start: time
    end: time


@dataclass
class Room:
    id: int
    capacity: int


@dataclass
class ExamProblem:
    papers: list
    slots: list
    rooms: list
    invigilators: list
    seating_gap: int = 0
    students_per_room: int | None = None
    unavailable: dict = field(default_factory=dict)   # faculty id -> set of slot indexes
    time_limit: float = DEFAULT_TIME_LIMIT


@dataclass
class Sitting:
    paper_key: int
    slot: int
    rooms: tuple                    # (room id, faculty id)


def usable_seats(capacity, gap, per_room=None):
    """Seats that may be filled. A gap of 1 leaves every other seat empty."""
    seats = int(capacity) // (max(0, int(gap)) + 1)
    if per_room:
        seats = min(seats, int(per_room))
    return max(0, seats)


def _require_ortools():
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SolverUnavailable('ortools is not installed; run pip install ortools') from exc
    return cp_model


def solve(problem: ExamProblem):
    """Place every paper. Returns (sittings, status). Status is OPTIMAL, FEASIBLE, or a reason code."""
    if not problem.papers or not problem.slots:
        return [], 'EMPTY'
    if not problem.invigilators:
        return [], 'NO_INVIGILATOR'
    gap = max(0, int(problem.seating_gap or 0))
    rooms = []
    seats = {}
    for room in problem.rooms:
        count = usable_seats(room.capacity, gap, problem.students_per_room)
        if count > 0:
            rooms.append(room)
            seats[room.id] = count
    if not rooms:
        return [], 'CAPACITY'
    total = sum(seats.values())
    for paper in problem.papers:
        if max(len(paper.students), 1) > total:
            return [], 'CAPACITY'

    cp_model = _require_ortools()
    model = cp_model.CpModel()
    slots = list(problem.slots)
    faculty = list(dict.fromkeys(problem.invigilators))
    x = {}
    y = {}
    d = {}
    for paper in problem.papers:
        for slot in slots:
            x[paper.key, slot.index] = model.NewBoolVar(f'p{paper.key}_s{slot.index}')
            for room in rooms:
                y[paper.key, slot.index, room.id] = model.NewBoolVar(f'p{paper.key}_s{slot.index}_r{room.id}')
    for person in faculty:
        blocked = problem.unavailable.get(person, ())
        for slot in slots:
            for room in rooms:
                var = model.NewBoolVar(f'd{person}_s{slot.index}_r{room.id}')
                d[person, slot.index, room.id] = var
                if slot.index in blocked:
                    model.Add(var == 0)

    for paper in problem.papers:
        model.Add(sum(x[paper.key, slot.index] for slot in slots) == 1)
        needed = max(len(paper.students), 1)
        for slot in slots:
            model.Add(sum(seats[room.id] * y[paper.key, slot.index, room.id] for room in rooms) >= needed * x[paper.key, slot.index])
            for room in rooms:
                model.Add(y[paper.key, slot.index, room.id] <= x[paper.key, slot.index])

    papers = list(problem.papers)
    for index, left in enumerate(papers):
        for right in papers[index + 1:]:
            if left.students & right.students:
                for slot in slots:
                    model.Add(x[left.key, slot.index] + x[right.key, slot.index] <= 1)

    for slot in slots:
        for room in rooms:
            model.Add(sum(y[paper.key, slot.index, room.id] for paper in papers) <= 1)
            model.Add(
                sum(d[person, slot.index, room.id] for person in faculty)
                == sum(y[paper.key, slot.index, room.id] for paper in papers)
            )
        for person in faculty:
            model.Add(sum(d[person, slot.index, room.id] for room in rooms) <= 1)

    max_duty = model.NewIntVar(0, len(slots), 'max_duty')
    for person in faculty:
        model.Add(max_duty >= sum(d[person, slot.index, room.id] for slot in slots for room in rooms))
    early = sum(slot.index * x[paper.key, slot.index] for paper in papers for slot in slots)
    used = sum(y[paper.key, slot.index, room.id] for paper in papers for slot in slots for room in rooms)
    model.Minimize(max_duty * 1000 + early * 10 + used)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(problem.time_limit or DEFAULT_TIME_LIMIT)
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], solver.StatusName(status)

    sittings = []
    for paper in papers:
        chosen = next(slot.index for slot in slots if solver.Value(x[paper.key, slot.index]))
        assigned = []
        for room in rooms:
            if not solver.Value(y[paper.key, chosen, room.id]):
                continue
            person = next(person for person in faculty if solver.Value(d[person, chosen, room.id]))
            assigned.append((room.id, person))
        sittings.append(Sitting(paper_key=paper.key, slot=chosen, rooms=tuple(assigned)))
    return sittings, solver.StatusName(status)
