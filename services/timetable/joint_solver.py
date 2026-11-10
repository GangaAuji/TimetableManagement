"""Joint timetable solving for a group of cohorts (CP-SAT via ortools).

The greedy generator (services/timetable/generator.py) schedules one
division at a time, so a teacher shared by two divisions, or an elective
whose students come from several divisions, is placed by whoever runs
first and blocked for everyone after. This module builds one constraint
model over every target of a generation job and solves it at once:

- every demand (one weekly hour of a subject for a cohort, or for one lab
  batch of it) is placed exactly once on a working day and slot;
- a cohort has at most one whole-cohort session per slot; different lab
  batches of the cohort may share a slot (their students are disjoint), as
  may different elective subjects (a student takes one of them), but a
  whole-cohort session excludes both;
- an elective subject taught to several cohorts is one session: its demands
  are shared across those cohorts, so the slot is common to all of them;
- a teacher teaches at most one session per slot across every cohort, and
  never in a slot where an existing timetable row outside the job, an
  absence or an explicit unavailability window has them;
- per slot there are no more practicals than free labs and no more theory
  sessions than free rooms; rooms are then assigned greedily by capacity;
- a subject meets at most twice a day for one cohort.

The objective places everything first, then pays the weighted soft rules of
services/timetable/rules.py (faculty preferences, hours per day, consecutive
hours, idle gaps, contiguous labs, lunch window, subject spread, early slots).
With capability `timetable_preferences` off the rule set is the legacy one:
one meeting of a subject per day and earlier slots. The quality model
(services/timetable_quality_service) stays the scorer: the result of each
cohort is scored and persisted like a greedy run, and `rules.evaluate()`
explains the remaining violations.

`solve(problem)` is pure and takes a Problem built from plain rows, so
tests do not need a database; `solve_targets` loads, solves and persists.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from academic_rules.clashes import times_overlap
from data_access.institutions import candidate_rooms_clause
from services.timetable.rules import BY_NAME as RULE_BY_NAME, NAMES as RULE_NAMES, legacy_rules

WEEKDAY_ORDER = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
DEFAULT_TIME_LIMIT = 20.0


class SolverUnavailable(RuntimeError):
    """ortools is not installed."""


@dataclass
class Demand:
    """One weekly hour to place. `cohorts` is every cohort key whose students attend (several for a shared elective)."""

    key: int
    cohorts: tuple
    subject_id: int
    subject_name: str
    kind: str                       # 'Theory' or 'Practical'
    faculty_options: tuple          # user ids that may teach it, preferred first
    faculty_names: dict = field(default_factory=dict)
    is_elective: bool = False
    lab_batch_group_id: int | None = None
    lab_batch_name: str | None = None
    group_size: int | None = None
    days: tuple = ()                # working days for this demand (the cohort's); empty means every problem day
    room_ids: frozenset | None = None   # rooms the cohort's institution may use; None means any room


@dataclass
class Problem:
    demands: list
    days: tuple                     # day names in order
    slots: tuple                    # (start time, end time) per slot index
    faculty_busy: dict = field(default_factory=dict)   # faculty id -> {day -> set(slot index)}
    labs: list = field(default_factory=list)            # [{'id', 'room_number', 'capacity'}]
    rooms: list = field(default_factory=list)
    room_busy: dict = field(default_factory=dict)       # room id -> {day -> set(slot index)}
    time_limit: float = DEFAULT_TIME_LIMIT
    rules: dict = field(default_factory=dict)           # services.timetable.rules weights; empty -> legacy objective
    preferences: dict = field(default_factory=dict)     # faculty id -> [preference windows]
    workload: dict = field(default_factory=dict)        # faculty id -> {'max_hours', 'fixed_hours'} (services.workload)
    workload_hard: bool = False                         # True: the max is a constraint, not a cost


def _slot_minutes(slots):
    """Length of a slot in minutes (the first slot's; slots share a grid)."""
    if not slots:
        return 60
    start, end = slots[0]
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


@dataclass
class Placement:
    demand: Demand
    day: str
    slot: int
    faculty_id: int
    room: dict | None = None


def _require_ortools():
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SolverUnavailable('ortools is not installed; run pip install ortools') from exc
    return cp_model


def solve(problem: Problem):
    """Place every demand. Returns (placements, unplaced demands, status string)."""
    cp_model = _require_ortools()
    model = cp_model.CpModel()
    days = list(problem.days)
    slot_count = len(problem.slots)
    if not days or not slot_count or not problem.demands:
        return [], list(problem.demands), 'EMPTY'

    x = {}            # (demand key, day, slot, faculty) -> BoolVar
    placed = {}       # demand key -> BoolVar (1 when placed somewhere)
    by_cell = defaultdict(list)          # (day, slot) -> [(demand, faculty, var)]
    for demand in problem.demands:
        allowed_days = [day for day in days if not demand.days or day in demand.days]
        options = []
        for day in allowed_days:
            for slot in range(slot_count):
                for faculty_id in demand.faculty_options:
                    if slot in problem.faculty_busy.get(faculty_id, {}).get(day, set()):
                        continue
                    var = model.NewBoolVar(f'x_{demand.key}_{day[:3]}_{slot}_{faculty_id}')
                    x[(demand.key, day, slot, faculty_id)] = var
                    by_cell[(day, slot)].append((demand, faculty_id, var))
                    options.append(var)
        placed_var = model.NewBoolVar(f'placed_{demand.key}')
        placed[demand.key] = placed_var
        if options:
            model.Add(sum(options) == placed_var)
        else:
            model.Add(placed_var == 0)

    # Faculty: one session per slot.
    for (day, slot), entries in by_cell.items():
        per_faculty = defaultdict(list)
        for _demand, faculty_id, var in entries:
            per_faculty[faculty_id].append(var)
        for variables in per_faculty.values():
            if len(variables) > 1:
                model.Add(sum(variables) <= 1)

    # Cohort exclusivity.
    for (day, slot), entries in by_cell.items():
        per_cohort = defaultdict(lambda: {'whole': [], 'elective': defaultdict(list), 'batch': defaultdict(list)})
        for demand, _faculty_id, var in entries:
            for cohort in demand.cohorts:
                bucket = per_cohort[cohort]
                if demand.lab_batch_group_id is not None:
                    bucket['batch'][demand.lab_batch_group_id].append(var)
                elif demand.is_elective:
                    bucket['elective'][demand.subject_id].append(var)
                else:
                    bucket['whole'].append(var)
        for cohort, bucket in per_cohort.items():
            any_elective = model.NewBoolVar(f'e_{cohort}_{day[:3]}_{slot}')
            any_batch = model.NewBoolVar(f'b_{cohort}_{day[:3]}_{slot}')
            for variables in bucket['elective'].values():
                model.Add(sum(variables) <= 1)
                for var in variables:
                    model.AddImplication(var, any_elective)
            for variables in bucket['batch'].values():
                model.Add(sum(variables) <= 1)
                for var in variables:
                    model.AddImplication(var, any_batch)
            if not bucket['elective']:
                model.Add(any_elective == 0)
            if not bucket['batch']:
                model.Add(any_batch == 0)
            model.Add(sum(bucket['whole']) + any_elective + any_batch <= 1)

    # Rooms: aggregate capacity per slot, per set of rooms a demand may use
    # (demands from different institutions see different pools).
    for (day, slot), entries in by_cell.items():
        if not (problem.labs or problem.rooms):
            continue
        groups = defaultdict(lambda: {'practical': [], 'theory': []})
        for demand, _f, var in entries:
            groups[demand.room_ids]['practical' if demand.kind == 'Practical' else 'theory'].append(var)
        for room_ids, bucket in groups.items():
            labs = _pool(problem.labs, room_ids)
            rooms = _pool(problem.rooms, room_ids)
            free_labs = sum(1 for room in labs if slot not in problem.room_busy.get(room['id'], {}).get(day, set()))
            free_rooms = sum(1 for room in rooms if slot not in problem.room_busy.get(room['id'], {}).get(day, set()))
            if bucket['practical'] and labs:
                model.Add(sum(bucket['practical']) <= free_labs)
            if bucket['theory'] and rooms:
                model.Add(sum(bucket['theory']) <= free_rooms)

    # Same subject at most twice a day per cohort; prefer once.
    repeats = []
    per_subject_day = defaultdict(list)
    demand_by_key = {demand.key: demand for demand in problem.demands}
    for (key, day, _slot, _faculty_id), var in x.items():
        demand = demand_by_key[key]
        for cohort in demand.cohorts:
            per_subject_day[(cohort, demand.subject_id, demand.lab_batch_group_id, day)].append(var)
    for (cohort, subject_id, batch_id, day), variables in per_subject_day.items():
        if len(variables) <= 1:
            continue
        model.Add(sum(variables) <= 2)
        extra = model.NewBoolVar(f'rep_{cohort}_{subject_id}_{batch_id}_{day[:3]}')
        model.Add(sum(variables) - 1 <= extra)
        repeats.append(extra)

    # Objective: place everything, then the weighted soft rules (services/timetable/rules.py).
    rules = problem.rules or legacy_rules()
    weight = {name: int((rules.get(name) or {}).get('weight') or 0) for name in RULE_NAMES}
    penalty = []                                            # linear terms (coefficient * var)
    penalty.extend(weight['spread_subject'] * var for var in repeats)
    penalty.extend(weight['prefer_early'] * slot * var for (_key, _day, slot, _f), var in x.items())
    penalty.extend(_soft_terms(model, problem, x, by_cell, demand_by_key, rules, weight, days, slot_count))
    model.Maximize(1000 * sum(placed.values()) - sum(penalty))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(problem.time_limit or DEFAULT_TIME_LIMIT)
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], list(problem.demands), status_name

    placements = []
    unplaced = []
    for demand in problem.demands:
        if not solver.Value(placed[demand.key]):
            unplaced.append(demand)
            continue
        for (key, day, slot, faculty_id), var in x.items():
            if key == demand.key and solver.Value(var):
                placements.append(Placement(demand=demand, day=day, slot=slot, faculty_id=faculty_id))
                break
    _assign_rooms(problem, placements)
    return placements, unplaced, status_name


def _soft_terms(model, problem, x, by_cell, demand_by_key, rules, weight, days, slot_count):
    """Linear penalty terms for the weighted rules that can be expressed on the placement variables.

    Rooms are assigned after the solve, so `room_changes` is only scored afterwards by rules.evaluate().
    Every term is `weight * indicator`; a weight of 0 adds nothing to the model.
    """
    terms = []
    param = lambda name, key: int((rules.get(name) or {}).get(key) or RULE_BY_NAME[name].params[key][1])  # noqa: E731
    last = slot_count - 1

    # Faculty occupancy per (faculty, day, slot): a linear expression (<= 1 by the one-session rule)
    # plus 1 for sessions already in the timetable outside this job.
    faculty_cell = defaultdict(list)
    faculty_ids = set()
    for (day, slot), entries in by_cell.items():
        for _demand, faculty_id, var in entries:
            faculty_cell[(faculty_id, day, slot)].append(var)
            faculty_ids.add(faculty_id)

    def busy(faculty_id, day, slot):
        fixed = 1 if slot in problem.faculty_busy.get(faculty_id, {}).get(day, set()) else 0
        return sum(faculty_cell.get((faculty_id, day, slot), [])) + fixed

    def busy_fixed(faculty_id, day, slot):
        return slot in problem.faculty_busy.get(faculty_id, {}).get(day, set())

    for faculty_id in faculty_ids:
        prefs = problem.preferences.get(faculty_id, []) if weight['faculty_preferences'] else []
        for day in days:
            cells = [(slot, faculty_cell.get((faculty_id, day, slot), [])) for slot in range(slot_count)]
            if not any(variables for _slot, variables in cells):
                continue
            # Preferences: avoid windows cost, preferred windows pay back.
            for slot, variables in cells:
                if not variables or not prefs:
                    continue
                start, end = problem.slots[slot]
                for pref in prefs:
                    if pref['day'] != day:
                        continue
                    p_start, p_end = _hhmm_to_time(pref['start_time']), _hhmm_to_time(pref['end_time'])
                    if start < p_end and p_start < end:
                        sign = 1 if pref['kind'] == 'avoid' else -1
                        terms.extend(sign * weight['faculty_preferences'] * pref['weight'] * var for var in variables)
            # Hours per day: over = max(0, load - limit).
            if weight['max_hours_per_day']:
                limit = param('max_hours_per_day', 'hours')
                load = sum(busy(faculty_id, day, slot) for slot in range(slot_count))
                over = model.NewIntVar(0, slot_count, f'over_{faculty_id}_{day[:3]}')
                model.Add(over >= load - limit)
                terms.append(weight['max_hours_per_day'] * over)
            # Consecutive hours: every window of limit+1 slots fully busy costs one.
            if weight['max_consecutive_hours']:
                limit = param('max_consecutive_hours', 'hours')
                for first in range(0, slot_count - limit):
                    window = range(first, first + limit + 1)
                    if all(busy_fixed(faculty_id, day, slot) for slot in window):
                        continue                      # already the case before this job; nothing to decide
                    run = model.NewBoolVar(f'run_{faculty_id}_{day[:3]}_{first}')
                    model.Add(sum(busy(faculty_id, day, slot) for slot in window) - limit <= run)
                    terms.append(weight['max_consecutive_hours'] * run)
            # Idle gaps: an empty slot with something before and after it.
            if weight['idle_gaps_faculty']:
                terms.extend(weight['idle_gaps_faculty'] * gap for gap in _gap_vars(model, f'fg_{faculty_id}_{day[:3]}', [busy(faculty_id, day, s) for s in range(slot_count)]))
        # Last slot one day, first slot the next.
        if weight['no_first_hour_after_evening'] and last > 0:
            for previous, following in zip(days, days[1:]):
                if WEEKDAY_ORDER.index(following) != WEEKDAY_ORDER.index(previous) + 1:
                    continue
                late, early = busy(faculty_id, previous, last), busy(faculty_id, following, 0)
                if isinstance(late, int) and isinstance(early, int):
                    continue
                flag = model.NewBoolVar(f'late_{faculty_id}_{previous[:3]}')
                model.Add(late + early - 1 <= flag)
                terms.append(weight['no_first_hour_after_evening'] * flag)
        # Weekly workload norm (J5): slots this job gives the teacher plus their fixed hours elsewhere.
        norm = problem.workload.get(faculty_id)
        if norm and norm.get('max_hours') is not None and (weight['workload_max'] or problem.workload_hard):
            slot_minutes = max(1, _slot_minutes(problem.slots))
            room_left = float(norm['max_hours']) * 60 - float(norm.get('fixed_hours') or 0) * 60
            max_slots = max(0, int(room_left // slot_minutes))
            own = [var for (f_id, _day, _slot), variables in faculty_cell.items() if f_id == faculty_id for var in variables]
            if not own:
                continue
            if problem.workload_hard:
                model.Add(sum(own) <= max_slots)
            elif weight['workload_max']:
                over = model.NewIntVar(0, len(own), f'wl_{faculty_id}')
                model.Add(over >= sum(own) - max_slots)
                terms.append(max(1, round(weight['workload_max'] * slot_minutes / 60)) * over)

    # Cohort rules on the cohort's own cells.
    cohort_cell = defaultdict(list)          # (cohort, day, slot) -> vars
    cohort_practicals = defaultdict(list)    # (cohort, subject, batch, day) -> [(slot, var)]
    cohorts = set()
    for (day, slot), entries in by_cell.items():
        for demand, _faculty_id, var in entries:
            for cohort in demand.cohorts:
                cohorts.add(cohort)
                cohort_cell[(cohort, day, slot)].append(var)
                if demand.kind == 'Practical':
                    cohort_practicals[(cohort, demand.subject_id, demand.lab_batch_group_id, day)].append((slot, var))
    lunch = None
    if weight['lunch_window']:
        start, end = (rules.get('lunch_window') or {}).get('start'), (rules.get('lunch_window') or {}).get('end')
        if start and end and start < end:
            lunch = (_hhmm_to_time(start), _hhmm_to_time(end))
    for cohort in cohorts:
        for day in days:
            occupied = []
            for slot in range(slot_count):
                variables = cohort_cell.get((cohort, day, slot), [])
                if not variables:
                    occupied.append(0)
                    continue
                occ = model.NewBoolVar(f'occ_{cohort}_{day[:3]}_{slot}')
                for var in variables:
                    model.AddImplication(var, occ)
                model.Add(occ <= sum(variables))
                occupied.append(occ)
                if lunch is not None:
                    s_start, s_end = problem.slots[slot]
                    if s_start < lunch[1] and lunch[0] < s_end:
                        terms.append(weight['lunch_window'] * occ)
            if weight['idle_gaps_students'] and any(not isinstance(o, int) for o in occupied):
                terms.extend(weight['idle_gaps_students'] * gap for gap in _gap_vars(model, f'cg_{cohort}_{day[:3]}', occupied))
    if weight['lab_blocks_contiguous']:
        for (cohort, subject_id, batch_id, day), cells in cohort_practicals.items():
            by_slot = defaultdict(list)
            for slot, var in cells:
                by_slot[slot].append(var)
            if len(by_slot) < 2:
                continue
            count = sum(var for _slot, var in cells)
            adjacent = []
            for slot in sorted(by_slot):
                if slot + 1 not in by_slot:
                    continue
                pair = model.NewBoolVar(f'adj_{cohort}_{subject_id}_{batch_id}_{day[:3]}_{slot}')
                model.Add(pair <= sum(by_slot[slot]))
                model.Add(pair <= sum(by_slot[slot + 1]))
                adjacent.append(pair)
            loose = model.NewIntVar(0, len(cells), f'loose_{cohort}_{subject_id}_{batch_id}_{day[:3]}')
            model.Add(loose >= count - 1 - sum(adjacent))
            terms.append(weight['lab_blocks_contiguous'] * loose)
    return terms


def _gap_vars(model, prefix, occupied):
    """Bool per slot that is 1 when the slot is empty but something is occupied before and after it."""
    gaps = []
    count = len(occupied)
    for slot in range(1, count - 1):
        before_terms = [o for o in occupied[:slot] if not isinstance(o, int) or o]
        after_terms = [o for o in occupied[slot + 1:] if not isinstance(o, int) or o]
        if not before_terms or not after_terms or (isinstance(occupied[slot], int) and occupied[slot]):
            continue
        before = model.NewBoolVar(f'{prefix}_b{slot}')
        after = model.NewBoolVar(f'{prefix}_a{slot}')
        for term in before_terms:
            model.Add(before >= term)
        model.Add(before <= sum(before_terms))
        for term in after_terms:
            model.Add(after >= term)
        model.Add(after <= sum(after_terms))
        gap = model.NewBoolVar(f'{prefix}_g{slot}')
        model.Add(gap >= before + after - occupied[slot] - 1)
        gaps.append(gap)
    return gaps


def _hhmm_to_time(value):
    return time(int(value[:2]), int(value[3:5]))


def _pool(rooms, room_ids):
    """The rooms a demand may use: all of them, or only those in `room_ids`."""
    if room_ids is None:
        return rooms
    return [room for room in rooms if room['id'] in room_ids]


def _assign_rooms(problem: Problem, placements):
    """Give each placement a free room of the right kind with enough seats, smallest surplus first."""
    used = defaultdict(set)   # (day, slot) -> room ids
    for placement in sorted(placements, key=lambda p: (p.day, p.slot, -(p.demand.group_size or 0))):
        labs = _pool(problem.labs, placement.demand.room_ids)
        rooms = _pool(problem.rooms, placement.demand.room_ids)
        pool = labs if placement.demand.kind == 'Practical' else rooms
        if not pool:
            pool = rooms or labs
        needed = placement.demand.group_size or 0
        candidates = [
            room for room in pool
            if room['id'] not in used[(placement.day, placement.slot)]
            and placement.slot not in problem.room_busy.get(room['id'], {}).get(placement.day, set())
        ]
        if not candidates:
            continue
        fitting = [room for room in candidates if not needed or not room.get('capacity') or room['capacity'] >= needed]
        chosen_pool = fitting or candidates
        chosen_pool.sort(key=lambda room: ((room.get('capacity') or 0) - needed if needed else 0, room.get('capacity') or 0))
        placement.room = chosen_pool[0]
        used[(placement.day, placement.slot)].add(chosen_pool[0]['id'])


# Loading -------------------------------------------------------------------

def _multiple_institutions(cursor):
    """True when the tenant has more than one active institution (revision 0014 onward)."""
    try:
        cursor.execute('SELECT COUNT(*) AS n FROM institutions WHERE is_active = 1')
        row = cursor.fetchone()
        return int((row or {}).get('n') or 0) > 1
    except Exception:
        return False


def _allowed_rooms(cursor, department_id):
    """Room ids the department's institution may timetable; None when the department is unknown."""
    if not department_id:
        return None
    cursor.execute('SELECT institution_id FROM departments WHERE id = %s', (department_id,))
    row = cursor.fetchone()
    if not row or row.get('institution_id') is None:
        return None
    clause, params = candidate_rooms_clause(int(row['institution_id']), 'r')
    cursor.execute(f'SELECT r.id FROM rooms r WHERE {clause}', params)
    return frozenset(int(r['id']) for r in cursor.fetchall())


def _coerce_time(value):
    if isinstance(value, time):
        return value
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        return time(hour=(seconds // 3600) % 24, minute=(seconds % 3600) // 60)
    if isinstance(value, str):
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
    if hasattr(value, 'hour'):
        return time(value.hour, value.minute)
    return time(0, 0)


def _slot_indexes(slots, start, end):
    return {index for index, (slot_start, slot_end) in enumerate(slots) if times_overlap(slot_start, slot_end, start, end)}


def cohort_key(target):
    return f"{target['course_id']}:{target['class_id']}:{target['division_id']}"


def load_problem(cursor, targets, settings, *, time_limit=DEFAULT_TIME_LIMIT):
    """Build the Problem for the job's targets from the database. Returns (problem, notes) where notes are per-target messages."""
    from academic_rules.holidays import holidays_for_week
    from academic_rules.weekdays import weekday_name
    from services.timetable.generator import _parse_time, build_time_slots, load_lab_batches

    start = _parse_time(settings.get('day_start') or '09:00', 'start time')
    end = _parse_time(settings.get('day_end') or '15:00', 'end time')
    break_window = None
    if settings.get('break_start') and settings.get('break_duration'):
        break_window = {'start': _parse_time(settings['break_start'], 'break start time'), 'duration': int(settings['break_duration'])}
    slots = tuple(build_time_slots(start, end, int(settings.get('lecture_minutes') or 45), break_window))
    week_start = settings.get('week_start_date')
    week_start = date.fromisoformat(week_start) if isinstance(week_start, str) else (week_start or date.today())
    week_end = week_start + timedelta(days=6)
    working = [day for day in WEEKDAY_ORDER if day in (settings.get('working_days') or WEEKDAY_ORDER[:6])]

    notes = {}
    demands = []
    key = 0
    elective_demands = {}   # (subject_id, hour index, kind) -> Demand shared across cohorts
    cohort_days = {}
    cohort_rooms = {}   # cohort -> frozenset of room ids its institution may use, or None for any
    scope_clauses = []
    scope_params = []
    multi_institution = _multiple_institutions(cursor)
    for target in targets:
        cohort = cohort_key(target)
        course_id, class_id, division_id = target['course_id'], target['class_id'], target['division_id']
        scope_clauses.append('(course_id = %s AND class_id = %s AND division_id = %s)')
        scope_params.extend((course_id, class_id, division_id))
        cursor.execute('SELECT program, department_id FROM courses WHERE id = %s', (course_id,))
        row = cursor.fetchone()
        program = (row or {}).get('program') or 'UG'
        cohort_rooms[cohort] = _allowed_rooms(cursor, (row or {}).get('department_id')) if multi_institution else None
        holiday_rows = holidays_for_week(cursor, program, week_start, week_end)
        weekly_off = {r['day_of_week'] for r in holiday_rows if r['day_of_week'] and r['is_recurring']}
        date_off = {r['holiday_date'] for r in holiday_rows if r['holiday_date']}
        institution_id = 1
        if (row or {}).get('department_id'):
            cursor.execute('SELECT institution_id FROM departments WHERE id = %s', (row['department_id'],))
            institution_id = int((cursor.fetchone() or {}).get('institution_id') or 1)
        open_days = []
        for offset in range(7):
            current = week_start + timedelta(days=offset)
            name = current.strftime('%A')
            if name in working and name not in weekly_off and current not in date_off:
                open_days.append((name, current))
        from services.academic_calendar import teaching_dates

        kept = teaching_dates(cursor, institution_id, [current for _name, current in open_days])
        days = [name for name, current in open_days if current in kept]
        cohort_days[cohort] = tuple(days)
        if not days:
            notes[cohort] = 'None of the selected days fall in a teaching term.' if len(kept) < len(open_days) else 'All selected days fall on holidays for the chosen week.'
            continue

        cursor.execute(
            """
            SELECT DISTINCT s.id, s.name, COALESCE(s.lectures_per_week, 0) AS lectures_per_week,
                   COALESCE(s.practical_hours_per_week, 0) AS practical_hours_per_week,
                   COALESCE(s.is_elective, 0) AS is_elective, s.course_type
            FROM subjects s
            JOIN faculty_allocations fa ON fa.subject_id = s.id
            WHERE s.course_id = %s AND (fa.class_id IS NULL OR fa.class_id = %s) AND (fa.division_id IS NULL OR fa.division_id = %s)
            ORDER BY s.name
            """,
            (course_id, class_id, division_id),
        )
        subjects = cursor.fetchall()
        if not subjects:
            notes[cohort] = 'No subjects are allocated to the selected class/division.'
            continue
        subject_ids = [s['id'] for s in subjects]
        marks = ','.join(['%s'] * len(subject_ids))
        cursor.execute(
            f"""
            SELECT fa.subject_id, fa.faculty_id, COALESCE(fa.is_primary, 1) AS is_primary, f.name
            FROM faculty_allocations fa
            JOIN faculty f ON f.user_id = fa.faculty_id
            WHERE fa.subject_id IN ({marks}) AND (fa.class_id IS NULL OR fa.class_id = %s) AND (fa.division_id IS NULL OR fa.division_id = %s)
            ORDER BY fa.subject_id, is_primary DESC, f.name
            """,
            (*subject_ids, class_id, division_id),
        )
        teachers = defaultdict(list)
        names = {}
        for r in cursor.fetchall():
            teachers[r['subject_id']].append(r['faculty_id'])
            names[r['faculty_id']] = r['name']
        missing = [s['name'] for s in subjects if not teachers.get(s['id'])]
        if missing:
            notes[cohort] = f"Faculty allocations missing for: {', '.join(missing)}."
            continue
        batches = load_lab_batches(cursor, course_id, class_id, division_id, week_start)
        for subject in subjects:
            is_elective = bool(subject['is_elective']) or 'Elective' in (subject.get('course_type') or '')
            options = tuple(dict.fromkeys(teachers[subject['id']]))
            for hour in range(int(subject['lectures_per_week'] or 0)):
                if is_elective:
                    shared = elective_demands.get((subject['id'], hour, 'Theory'))
                    if shared is not None:
                        shared.cohorts = tuple(dict.fromkeys(shared.cohorts + (cohort,)))
                        shared.faculty_options = tuple(dict.fromkeys(shared.faculty_options + options))
                        shared.faculty_names.update(names)
                        continue
                key += 1
                demand = Demand(
                    key=key, cohorts=(cohort,), subject_id=subject['id'], subject_name=subject['name'], kind='Theory',
                    faculty_options=options, faculty_names=dict(names), is_elective=is_elective, days=tuple(days),
                    room_ids=cohort_rooms.get(cohort),
                )
                demands.append(demand)
                if is_elective:
                    elective_demands[(subject['id'], hour, 'Theory')] = demand
            for hour in range(int(float(subject['practical_hours_per_week'] or 0))):
                for batch in (batches or [None]):
                    key += 1
                    demands.append(Demand(
                        key=key, cohorts=(cohort,), subject_id=subject['id'], subject_name=subject['name'], kind='Practical',
                        faculty_options=options, faculty_names=dict(names), is_elective=is_elective, days=tuple(days),
                        lab_batch_group_id=batch['id'] if batch else None, lab_batch_name=batch['name'] if batch else None,
                        group_size=batch['size'] if batch else None, room_ids=cohort_rooms.get(cohort),
                    ))
    # Shared electives meet on days every cohort works, in rooms every cohort may use.
    for demand in demands:
        if len(demand.cohorts) > 1:
            common = [day for day in working if all(day in cohort_days.get(c, ()) for c in demand.cohorts)]
            demand.days = tuple(common)
            pools = [cohort_rooms.get(c) for c in demand.cohorts if cohort_rooms.get(c) is not None]
            if pools:
                shared_rooms = frozenset.intersection(*pools)
                demand.room_ids = shared_rooms or frozenset().union(*pools)

    # Faculty busy from rows outside the job, absences and unavailability windows.
    faculty_busy = defaultdict(lambda: defaultdict(set))
    scope = ' OR '.join(scope_clauses) or '0'
    cursor.execute(
        f"""
        SELECT faculty_id, day_of_week, start_time, end_time FROM timetable
        WHERE faculty_id IS NOT NULL AND COALESCE(is_active, 1) = 1 AND NOT ({scope})
        """,
        tuple(scope_params),
    )
    for r in cursor.fetchall():
        faculty_busy[r['faculty_id']][r['day_of_week']] |= _slot_indexes(slots, _coerce_time(r['start_time']), _coerce_time(r['end_time']))
    cursor.execute('SELECT faculty_id, absence_date FROM faculty_absences WHERE absence_date BETWEEN %s AND %s', (week_start, week_end))
    for r in cursor.fetchall():
        faculty_busy[r['faculty_id']][r['absence_date'].strftime('%A')] |= set(range(len(slots)))
    cursor.execute(
        """
        SELECT fa.faculty_id, fa.day_of_week, fa.is_available, sp.start_time, sp.end_time
        FROM faculty_availability fa
        LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
        WHERE (sp.is_active = 1 OR fa.shift_pattern_id IS NULL) AND fa.is_available = 0
        """
    )
    for r in cursor.fetchall():
        day = weekday_name(r['day_of_week'])
        if not day:
            continue
        if r['start_time'] and r['end_time']:
            faculty_busy[r['faculty_id']][day] |= _slot_indexes(slots, _coerce_time(r['start_time']), _coerce_time(r['end_time']))
        else:
            faculty_busy[r['faculty_id']][day] |= set(range(len(slots)))

    labs, rooms = [], []
    cursor.execute('SELECT id, room_number, room_type, capacity FROM rooms')
    for r in cursor.fetchall():
        kind = (r.get('room_type') or '').lower()
        entry = {'id': int(r['id']), 'room_number': r.get('room_number'), 'capacity': r.get('capacity')}
        (labs if 'lab' in kind else rooms).append(entry)
    room_busy = defaultdict(lambda: defaultdict(set))
    cursor.execute(
        f"""
        SELECT room_id, day_of_week, start_time, end_time FROM timetable
        WHERE room_id IS NOT NULL AND COALESCE(is_active, 1) = 1 AND NOT ({scope})
        """,
        tuple(scope_params),
    )
    for r in cursor.fetchall():
        room_busy[int(r['room_id'])][r['day_of_week']] |= _slot_indexes(slots, _coerce_time(r['start_time']), _coerce_time(r['end_time']))
    # Approved room bookings for the week share the ledger (services/bookings.py; empty when the capability is off).
    from services import bookings as bookings_store

    week_dates = {(week_start + timedelta(days=offset)).strftime('%A'): week_start + timedelta(days=offset) for offset in range(7)}
    for day, per_room in bookings_store.room_usage_for_week(cursor, week_dates).items():
        for room_id, spans in per_room.items():
            for span_start, span_end in spans:
                room_busy[int(room_id)][day] |= _slot_indexes(slots, span_start, span_end)

    all_days = tuple(day for day in working if any(day in days for days in cohort_days.values()))

    # Soft rules of the first target's institution (a job spans one institution in practice) and the
    # preferences of every teacher who may be placed. Capability off -> legacy objective, no preferences.
    from services.timetable import rules as rule_set

    institution_id = rule_set.institution_for_course(cursor, targets[0]['course_id']) if targets else 1
    rules, preferences_on = rule_set.effective_rules(cursor, institution_id, settings)
    preferences = {}
    if preferences_on:
        preferences = rule_set.load_preferences(cursor, {fid for demand in demands for fid in demand.faculty_options})

    # Workload norms (J5): max weekly hours per teacher and the hours they already teach outside this job.
    from services import workload as workload_norms

    candidate_ids = {fid for demand in demands for fid in demand.faculty_options}
    workload_max = workload_norms.max_hours(cursor, institution_id=institution_id, faculty_ids=candidate_ids) if candidate_ids else {}
    workload, workload_hard = {}, False
    if workload_max:
        job_scope = ' OR '.join('(t.course_id = %s AND t.class_id = %s AND t.division_id = %s)' for _ in targets) or '0'
        fixed = workload_norms.weekly_hours(cursor, workload_max, exclude_clause=job_scope, exclude_params=scope_params)
        workload = {fid: {'max_hours': limit, 'fixed_hours': fixed.get(fid, 0.0)} for fid, limit in workload_max.items()}
        workload_hard = workload_norms.enforcement(cursor) == 'hard'

    problem = Problem(
        demands=demands, days=all_days, slots=slots, faculty_busy=faculty_busy, labs=labs, rooms=rooms,
        room_busy=room_busy, time_limit=time_limit, rules=rules, preferences=preferences,
        workload=workload, workload_hard=workload_hard,
    )
    return problem, notes, cohort_days


# Results and persistence -----------------------------------------------------

def _entries_for(cohort, placements, problem, unplaced, cohort_days):
    """The greedy generator's result dict for one cohort, from the joint placements."""
    assigned = []
    for placement in placements:
        if cohort not in placement.demand.cohorts:
            continue
        start, end = problem.slots[placement.slot]
        demand = placement.demand
        assigned.append({
            'day': placement.day,
            'start_time': start.strftime('%H:%M'),
            'end_time': end.strftime('%H:%M'),
            'subject_id': demand.subject_id,
            'subject_name': demand.subject_name,
            'faculty_id': placement.faculty_id,
            'faculty_name': demand.faculty_names.get(placement.faculty_id, ''),
            'session_type': demand.kind,
            'room_id': placement.room['id'] if placement.room else None,
            'room_number': placement.room.get('room_number') if placement.room else None,
            'lab_batch_group_id': demand.lab_batch_group_id,
            'lab_batch_name': demand.lab_batch_name,
            'is_proxy': False,
            'shared': len(demand.cohorts) > 1,
        })
    assigned.sort(key=lambda e: (WEEKDAY_ORDER.index(e['day']), e['start_time'], e.get('lab_batch_name') or ''))
    unassigned = [
        {'day': '', 'start_time': '', 'end_time': '', 'reason': f"No slot for {d.subject_name} ({d.kind}{' ' + d.lab_batch_name if d.lab_batch_name else ''})"}
        for d in unplaced if cohort in d.cohorts
    ]
    needs_room = [
        {'day': e['day'], 'start_time': e['start_time'], 'end_time': e['end_time'], 'subject_id': e['subject_id'],
         'subject_name': e['subject_name'], 'faculty_id': e['faculty_id'], 'faculty_name': e['faculty_name'],
         'session_type': e['session_type'], 'reason': 'No room available'}
        for e in assigned if not e['room_id'] and (problem.rooms or problem.labs)
    ]
    return assigned, unassigned, needs_room


def _explain(cohort, assigned, placements, problem):
    """rules.evaluate() for one cohort, with every other placement as the teachers' external load."""
    from services.timetable import rules as rule_set

    external = []
    for placement in placements:
        if cohort in placement.demand.cohorts:
            continue
        start, end = problem.slots[placement.slot]
        external.append({'day': placement.day, 'start_time': start.strftime('%H:%M'), 'end_time': end.strftime('%H:%M'), 'faculty_id': placement.faculty_id})
    # Teaching hours for the workload rule: other placements plus the fixed hours outside the job
    # (faculty_busy also holds absences and unavailability, which are not teaching).
    norms = {fid: entry['max_hours'] for fid, entry in problem.workload.items() if entry.get('max_hours') is not None} or None
    norm_external = list(external)
    norm_fixed = {fid: float(entry.get('fixed_hours') or 0) for fid, entry in problem.workload.items()}
    for faculty_id, days in problem.faculty_busy.items():
        for day, slots in days.items():
            for slot in slots:
                if slot < len(problem.slots):
                    start, end = problem.slots[slot]
                    external.append({'day': day, 'start_time': start.strftime('%H:%M'), 'end_time': end.strftime('%H:%M'), 'faculty_id': faculty_id})
    try:
        report = rule_set.evaluate(
            assigned, problem.rules or legacy_rules(), problem.preferences,
            slot_starts=[start.strftime('%H:%M') for start, _end in problem.slots], external=external, cohort_label=cohort,
            norms=norms, norm_external=norm_external, norm_fixed_hours=norm_fixed,
        )
    except Exception:
        return {'violations': [], 'rule_cost': 0, 'rule_costs': {}}
    return {'violations': report['violations'], 'rule_cost': report['cost'], 'rule_costs': report['by_rule']}


def _score(assigned, unassigned, needs_room, slots_per_day, rules=None):
    from services.timetable_quality_service import score_timetable_candidate

    try:
        info = score_timetable_candidate(assigned=assigned, unassigned=unassigned, proxy_suggestions=[], needs_room=needs_room, slots_per_day=slots_per_day, rules=rules)
    except Exception:
        return {'quality_score': 0.0, 'baseline_quality_score': 0.0, 'model_source': 'rule_fallback', 'score_breakdown': {}, 'warnings': ['Quality scoring failed.']}
    return {
        'quality_score': round(float(info.get('quality_score', 0.0)), 2),
        'baseline_quality_score': round(float(info.get('baseline_quality_score', info.get('quality_score', 0.0))), 2),
        'model_source': str(info.get('model_source', 'rule_fallback')),
        'score_breakdown': info.get('score_breakdown', {}),
        'warnings': info.get('warnings', []),
    }


def persist_cohort(cursor, course_id, class_id, division_id, assigned, version_id=None):
    """Archive and retire the cohort's active rows, then insert the new ones (same shape as the greedy generator).

    With `version_id` the rows are a draft (`is_active = 0`) and the live timetable is left alone;
    publishing happens in services/timetable/versions.py.
    """
    if version_id is not None:
        for entry in assigned:
            cursor.execute(
                """
                INSERT INTO timetable (course_id, class_id, division_id, day_of_week, start_time, end_time, subject_id, faculty_id,
                                       room_id, lab_batch_group_id, is_active, version_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
                """,
                (
                    course_id, class_id, division_id, entry['day'], entry['start_time'], entry['end_time'], entry['subject_id'],
                    entry['faculty_id'], entry.get('room_id'), entry.get('lab_batch_group_id'), int(version_id),
                ),
            )
        return
    try:
        cursor.execute(
            """
            INSERT INTO timetable_history
            (course_id, class_id, division_id, day_of_week, start_time, end_time, subject_id, faculty_id, room_id, archived_at)
            SELECT course_id, class_id, division_id, day_of_week, start_time, end_time, subject_id, faculty_id, room_id, NOW()
            FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s AND COALESCE(is_active, 1) = 1
            """,
            (course_id, class_id, division_id),
        )
    except Exception:
        pass
    cursor.execute(
        'UPDATE timetable SET is_active = 0 WHERE course_id = %s AND class_id = %s AND division_id = %s AND COALESCE(is_active, 1) = 1',
        (course_id, class_id, division_id),
    )
    for entry in assigned:
        cursor.execute(
            """
            INSERT INTO timetable (course_id, class_id, division_id, day_of_week, start_time, end_time, subject_id, faculty_id,
                                   room_id, lab_batch_group_id, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """,
            (
                course_id, class_id, division_id, entry['day'], entry['start_time'], entry['end_time'], entry['subject_id'],
                entry['faculty_id'], entry.get('room_id'), entry.get('lab_batch_group_id'),
            ),
        )
    from services.webhooks import on_timetable_published

    on_timetable_published(
        cursor, course_id=course_id, class_id=class_id, division_id=division_id, reason='generated',
        slot_count=len(assigned), solver='joint',
    )


def solve_targets(connection, targets, settings, *, created_by=None, preview_only=False, time_limit=None, version_id=None):
    """Solve every target jointly and persist each cohort. Returns {cohort key: result dict} in the generator's shape.

    `version_id` writes the result as a draft of that timetable version instead of replacing live rows.
    """
    from flask import current_app
    from uuid import uuid4

    cursor = connection.cursor(dictionary=True)
    try:
        limit = float(time_limit or current_app.config.get('TIMETABLE_SOLVER_SECONDS') or DEFAULT_TIME_LIMIT)
        problem, notes, cohort_days = load_problem(cursor, targets, settings, time_limit=limit)
        placements, unplaced, status = solve(problem)
        current_app.logger.info('Joint solver: %s, %d placed, %d unplaced, %d cohorts', status, len(placements), len(unplaced), len(targets))
        results = {}
        for target in targets:
            cohort = cohort_key(target)
            if cohort in notes:
                results[cohort] = {'status': 'error', 'message': notes[cohort], 'assigned': [], 'unassigned': []}
                continue
            if status not in ('OPTIMAL', 'FEASIBLE'):
                results[cohort] = {'status': 'error', 'message': f'The joint solver found no timetable ({status}).', 'assigned': [], 'unassigned': []}
                continue
            assigned, unassigned, needs_room = _entries_for(cohort, placements, problem, unplaced, cohort_days)
            slots_per_day = {day: len(problem.slots) for day in cohort_days.get(cohort, ())}
            score = _score(assigned, unassigned, needs_room, slots_per_day, problem.rules)
            score.update(_explain(cohort, assigned, placements, problem))
            if not preview_only:
                persist_cohort(cursor, target['course_id'], target['class_id'], target['division_id'], assigned, version_id=version_id)
                connection.commit()
                try:
                    breakdown = score.get('score_breakdown') or {}
                    cursor.execute(
                        """
                        INSERT INTO timetable_quality_runs
                        (run_id, course_id, class_id, division_id, week_start, quality_score, clash_risk, faculty_fatigue, room_overuse,
                         student_load_imbalance, candidate_count, selected_candidate_index, created_by, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 1, %s, NOW())
                        """,
                        (
                            str(uuid4()), target['course_id'], target['class_id'], target['division_id'], settings.get('week_start_date'),
                            score['quality_score'], breakdown.get('clash_risk', 1.0), breakdown.get('faculty_fatigue', 1.0),
                            breakdown.get('room_overuse', 1.0), breakdown.get('student_load_imbalance', 1.0), created_by,
                        ),
                    )
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    current_app.logger.warning('Could not persist timetable_quality_runs for the joint run: %s', exc)
            message = f"Scheduled {len(assigned)} session(s) jointly across {len(cohort_days.get(cohort, ()))} day(s) ({status.lower()})."
            if unassigned:
                message += f' {len(unassigned)} session(s) could not be placed.'
            results[cohort] = {
                'status': 'success' if assigned else 'warning',
                'message': message,
                'assigned': assigned,
                'unassigned': unassigned,
                'proxy_suggestions': [],
                'needs_room': needs_room,
                'skipped_holidays': [],
                'solver': 'joint',
                'solver_status': status,
                'candidate_count': 1,
                'selected_candidate_index': 1,
                'top_candidates': [{'candidate_index': 1, 'quality_score': score['quality_score'], 'assigned_count': len(assigned), 'unassigned_count': len(unassigned), 'needs_room_count': len(needs_room)}],
                'version_id': int(version_id) if (version_id is not None and not preview_only) else None,
                **score,
            }
        return results
    finally:
        cursor.close()
