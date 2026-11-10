# Generating timetables

Generation runs as a background job (`timetable_jobs`, claimed by `flask
workers run`; see [RUNBOOK.md](RUNBOOK.md)). The Generate page queues the job
with `POST /api/timetable/generate` and polls `GET /api/timetable/jobs/<id>`.
Two solvers are available; the request chooses one with `solver`.

## Inputs both solvers share

- Scope: one class (course, class, division), one course, or every class.
- Working days, day start and end, lecture length, an optional break.
- Subjects of the course with their weekly hours, split into theory and
  practical sessions; electives come from `student_subject_selections`.
- Faculty from `faculty_subject_allocations`, their absences
  (`faculty_absences`) and unavailability (`faculty_unavailability`).
- Rooms: labs (any `room_type` containing "lab") for practicals, the rest
  for theory, with `capacity` checked against the group size.
- Lab batches (`lab_batch_groups`, [DESIGN_LAB_BATCHES.md](DESIGN_LAB_BATCHES.md)):
  every practical becomes one session per active batch of the division for
  the academic year that contains the week start date.
- Existing rows in `timetable` outside the job's scope, so a teacher or a
  room already booked by another class is not booked again.

## `greedy`: class by class (default)

`services/timetable/generator.py`. Classes in the job run one after another.
For each class the generator orders sessions, tries each free slot, and picks
the first teacher and room that fit; it keeps several candidates and ranks
them with the quality model (`timetable_quality_service`, score 0–100 with
clash risk, faculty fatigue, room overuse and load balance). Lab batches are
placed in parallel: once one batch's practical lands in a slot,
`fill_parallel_batches` puts the other batches in the same slot with a
different teacher and lab when it can, otherwise they take their own slots.

Strengths: fast, no extra dependency, good when classes rarely share staff.
Weakness: a teacher taken by the first class is simply unavailable to the
next, so later classes in the run get the leftovers.

## `joint`: all selected classes in one model

`services/timetable/joint_solver.py`, a CP-SAT model built with
[OR-Tools](https://developers.google.com/optimization) (`ortools` in
`requirements.txt`). `load_problem` turns the targets into demands, one per
session that must be placed; `solve` places them; `persist_cohort` archives
the old rows, retires them and inserts the new timetable with
`lab_batch_group_id` set for batch sessions.

Hard rules:

- A demand is placed at most once (placing everything is the main objective).
- A teacher gives one session per slot across all cohorts in the job, and
  none in slots already booked outside the job or marked absent/unavailable.
- Cohort exclusivity per slot: a whole-division session excludes everything
  else for that division; electives of different subjects may run together;
  different lab batches may run together; the same elective subject or the
  same batch appears at most once per slot.
- Shared electives: a subject chosen across several divisions is one demand
  with several cohorts, so it lands in one slot for all of them.
- Room capacity per slot: no more practicals than free labs and no more
  theory sessions than free rooms. Exact rooms are assigned afterwards by
  `_assign_rooms`, largest group first.
- The same subject at most twice a day per cohort (and per batch).

Soft rules: place every demand (1000 each) minus the weighted rule costs
described under [Rules and preferences](#rules-and-preferences). Without
the `timetable_preferences` capability only the historical two apply: avoid
a subject repeating on a day (10) and prefer earlier slots (1 per slot step).
The quality model then scores the result exactly as it does for the greedy
output, so the two solvers are comparable on the Generate page.

The solver runs for at most `TIMETABLE_SOLVER_SECONDS` (default 20; the
`.env` variable) and returns the best feasible solution found. Demands it
could not place are reported as unassigned slots with a reason. When
`ortools` is not installed the job logs a warning and falls back to the
greedy generator, so a deployment without the package still generates.

Choose `joint` when several divisions share faculty, when electives are
taken across divisions, or when lab batches must run in parallel. Choose
`greedy` for a single class or a quick draft.

## Rules and preferences

Part of the `timetable_preferences` capability (see
[DESIGN_CAPABILITIES.md](DESIGN_CAPABILITIES.md)). With it off, nothing
below exists for users and both solvers behave exactly as before.

`services/timetable/rules.py` is the single registry of soft rules. Each
rule has a weight from 0 to 20, the cost of one violation; 0 switches it
off. The rules: `faculty_preferences` (a teacher's avoid/preferred windows),
`max_hours_per_day` and `max_consecutive_hours` (per teacher, with an
`hours` threshold), `idle_gaps_students`, `idle_gaps_faculty`,
`room_changes`, `spread_subject`, `lab_blocks_contiguous`,
`no_first_hour_after_evening`, `lunch_window` (`start`/`end` HH:MM),
`prefer_early` and `workload_max` (hours beyond a teacher's weekly norm; see
"Workload norms"). `default_rules()` gives the registry defaults;
`legacy_rules()` is the pre-rules objective (spread 10, early 1) used when
the capability is off. `effective_rules(cursor, institution_id, settings)`
picks one of the two, merges a per-run `rules_override`, and says whether
preferences count.

Storage (`0016_timetable_preferences`): `timetable_rules` holds one JSON
document per institution; `faculty_preferences` holds one row per teacher
window (`faculty_id` is `faculty.user_id`, `day_of_week` 1 = Monday, `kind`
preferred or avoid, `weight` 1–5, `note`).

How the solvers use them:

- `joint` adds every weighted rule to the CP-SAT objective (`_soft_terms`),
  so the model trades placements against violations at the chosen weights.
  Room changes are scored only after room assignment.
- `greedy` ranks each cohort's candidate timetables by
  `quality_score - 0.5 * rule_cost`; the slot-by-slot placement loop is
  unchanged.
- `evaluate(entries, rules, preferences)` scores any finished timetable and
  lists the violations. Both solvers return `violations[]`, `rule_cost` and
  `rule_costs` per cohort, shown on the Generate page as "Why these slots".
- The quality model takes the `max_hours_per_day` / `max_consecutive_hours`
  thresholds for its fatigue features when those rules are on.

API (all behind the capability, 404 `capability_off` otherwise):

- `GET`/`PUT /api/timetable/rules` (`timetable_rules_view` to read, `timetable_rules_change` to write; `timetable_generate` still does both): the institution's
  rules, the registry, the defaults and `can_change`. `PUT` takes
  `{"rules": {...}}`, validated by `clean_rules`. Page: Timetable → Rules.
- `GET`/`PUT /api/faculty/<faculty_id>/preferences`
  (`faculty_view_availability` to read, `faculty_change_availability` to
  write; a Teacher may only reach their own record; institution scope
  applies). Page: Shifts → Availability, "Preferences" under each teacher.
- `GET`/`PUT /api/portal/preferences` (Teacher): the signed-in teacher's own
  windows. Page: My availability.
- `POST /api/timetable/generate` accepts `rules_override` with partial rule
  objects for one run; it is validated the same way and stored with the job.

## Workload norms

Part of the `workload_norms` capability (default off; setting `enforce`
soft or hard). `services/workload.py` owns it. A norm is a weekly teaching
range in hours (`min`–`max`, 0–60, either side optional) per designation,
with a default for designations without their own entry. Norms are stored
in the institution's `timetable_rules` row under the reserved `_workload`
key, so there is no schema beyond `0016`; `rules.load_rules` ignores
`_`-prefixed keys and `save_rules` keeps them.

`limits_for` resolves the norm per teacher from `faculty.designation`
(case-insensitive match, else the default). `weekly_hours` sums the live
timetable rows per teacher; `assess` returns every teacher with their hours
and a status `under` | `ok` | `over` | `no_norm`.

How the solvers use the maximum:

- Soft (`enforce: soft`): the `workload_max` rule (default weight 6) costs
  `weight × hours` over the norm, counting the teacher's hours across every
  cohort plus the hours they already teach outside the run. `joint` adds the
  term to the objective; `greedy` includes it in `rule_cost`. Violations
  read "N hours this week (norm M)".
- Hard (`enforce: hard`): `joint` adds `sum(slots) ≤ remaining hours` per
  teacher; `greedy` treats a teacher whose fixed hours plus the slot would
  exceed the norm as unavailable. The hours are left unassigned and the
  result says so. Nothing with a minimum is ever enforced by the solvers;
  minimums only flag.

Where the status shows:

- Faculty workload report (`faculty-workload`, docs/REPORTS.md) gains
  `designation`, `norm_min`, `norm_max` and `workload_flag` columns and an
  `outside_norm` count in its meta while the capability is on.
- The teacher dashboard shows a "My workload" card (`workload` in
  `GET /api/portal/teacher`; `null` when off).
- Timetable → Workload norms (`workload_norms_change` or `timetable_generate` to change) edits the
  norms and lists every teacher's status.

API (404 `capability_off` when off; 409 `rules_table_missing` before `0016`):

- `GET /api/timetable/workload-norms` (`workload_norms_view`, `timetable_generate` or
  `reports_view_timetable`): `norms`, `stored`, `enforce`, `designations`
  in use, `teachers[]` with status, `max_hours`, `can_change`.
- `PUT /api/timetable/workload-norms` (`workload_norms_change` or `timetable_generate`):
  `{"norms": {"default": {"min", "max"}, "by_designation": {name: {...}}}}`;
  400 `norms_invalid` for hours outside 0–60, min above max, more than 40
  designations or names over 50 characters. Audited as
  `workload_norms_changed`.

## Versions: drafts, compare, publish, rollback

Part of the `timetable_versions` capability (default on once revision
`0017_timetable_versions` is applied; `services/timetable/versions.py`).
With it off, both solvers replace the live rows directly, exactly as
before, and none of the endpoints below exist.

With it on, a generation job first creates a **draft** version covering
every class in the job (`timetable_versions` + `timetable_version_cohorts`)
and both solvers write their rows with `is_active = 0` and
`timetable.version_id` set. The live timetable is untouched, so students,
teachers, attendance, exports, the public API and webhooks keep seeing what
they saw. In a multi-class greedy job, class N treats the draft rows of
classes 1..N-1 as busy and ignores the live rows of classes the draft will
replace (`versions.busy_clause`), so the draft is clash-free once published.
The job's result carries `version_id`, the Generate page links to the
Versions page, and the job message says the result was saved as a draft.
Drafts beyond the capability's `keep_drafts` setting (default 10) are
pruned oldest first. A draft that placed nothing is dropped.

**Publish** (`versions.publish`) runs in one transaction per request: for
each class the version has rows for, the active rows are copied to
`timetable_history`, retired (`is_active = 0`), and the version's rows are
activated; classes the version has no rows for are left alone and reported
as `skipped`. Published versions that no longer have an active row become
`archived`; the new one becomes `published` with `published_by/at`. The
`timetable.published` webhook fires per class with reason `published`.
**Rollback** is publishing an archived version again. A manual slot added
through `POST /api/timetable/slots` while a version is live is tagged with
that version, so a rollback and a re-publish carry it along. Only drafts
and archived versions can be discarded; discarding deletes their inactive
rows.

**Compare** (`versions.diff`) pairs the slots of two versions per class:
same cell and session → `unchanged` (or `room_changed`), same session in
another cell → `moved`, otherwise `added` / `removed`; it also totals the
changes per teacher. The Versions page shows the two week grids side by
side with the changes shaded and lets a user with `timetable_versions_publish`
or `timetable_generate` publish, roll back, rename or discard.

API (all behind the capability, 404 `capability_off` otherwise; reading
needs `timetable_versions_view`, `timetable_change` or `timetable_generate`, changing needs
`timetable_versions_publish` or `timetable_generate`; versions are scoped to the caller's institutions):

- `GET /api/timetable/versions[?course_id&class_id&division_id&status]`
- `GET /api/timetable/versions/<id>` — the version and its slots
- `GET /api/timetable/versions/<id>/diff/<other|live>` — changes against
  another version or the live timetable
- `POST /api/timetable/versions/<id>/publish`, `PUT .../<id>` (`label`),
  `DELETE .../<id>` (409 `version_published` for the live one)
- `POST /api/timetable/generate` accepts an optional `label` for the draft.

## Manual slots

`POST /api/timetable/slots` adds one row (subject, day, start and end,
optional faculty, lab batch and room). `services/timetable_slots.add_slot`
runs the same checks as the generator: holiday, division or batch clash
(`academic_rules/clashes.cohort_slots_clash`), faculty clash and
availability, room clash. The error code names the rule that failed
(`slot_class_busy`, `slot_batch_busy`, `slot_faculty_busy`,
`slot_faculty_unavailable`, `slot_room_busy`, `slot_batch_invalid`).

`DELETE /api/timetable/slots/<id>` deletes a slot that has never been used.
A slot with attendance or lecture sessions is retired (`is_active = 0`)
instead, so marks are never lost; the response says which happened.

Both endpoints need `timetable_change`, and the timetable page shows them
to users who have it.

## Interactive grid and live checks

The rule book for a manual slot lives in one function,
`services/timetable_slots.check_slot`. It runs every check without writing
and returns `(faculty_id, errors)`; `add_slot` calls it with
`first_only=True` and raises the first error, so what the grid predicts is
exactly what a save would refuse. `exclude_id` ignores one existing row,
which is how a slot can be checked against its own new position.

`POST /api/timetable/check` (needs `timetable_change`) takes the same body
as `POST /timetable/slots` plus `exclude_id` and answers

```json
{"ok": false, "faculty_id": 12,
 "errors": [{"code": "slot_class_busy", "message": "..."}],
 "rule_cost": {"before": 14, "after": 24, "delta": 10,
               "violations": [{"rule": "spread_subject", "title": "Spread subjects", "cost": 10, "faculty": "", "detail": "..."}]}}
```

`errors` lists every hard rule the slot breaks, in the order `add_slot`
checks them. `rule_cost` (`services/timetable_slots.slot_cost`) is present
only when the slot is clean and the `timetable_preferences` capability is
on: it scores the cohort's live rows with the shared soft rules
(`services/timetable/rules.py`) without and with the candidate and lists the
violations the candidate introduces. Nothing is written.

The Timetable page uses it for drag and drop. Picking up a session
pre-checks the other cells of the week (at most 60 requests, with the
dragged row excluded) and shades them green (clean), amber (costs soft-rule
points), red (a hard rule blocks it) or grey while the answer is pending.
Dropping opens a confirmation that repeats the errors or the cost and the
violations; confirming does `DELETE /slots/<id>` then `POST /slots`, so a
slot with recorded attendance is retired rather than deleted and the marks
stay. Every move is pushed onto an undo stack ("Undo move" in the toolbar
reverses the last one the same way).

`GET /api/timetable` also serves the week of one teacher (`?faculty=<user
id>`) or one room (`?room=<id>`), across every class in the caller's scope;
the response says which `view` it is (`class`, `faculty` or `room`) and each
session carries `course_id`, `class_id`, `division_id`, `cohort` (a label),
`subject_id`, `faculty_id` and `room_id` so a move can be built from the
row alone. The faculty and room lists are loaded in every view. "Print"
prints the grid alone; the controls are hidden with `print:hidden`.

## Room bookings

Capability `bookings` (off by default) adds `bookings` (revision 0018) to
the clash ledger: a room reserved for an event, exam, maintenance or an
outside party, either on one date (`booking_date`) or every week on one
weekday (`day_of_week`, until `repeat_until`). `services/bookings.py` is the
one place that reads it:

- `room_usage_for_week(cursor, {day: date})` gives the greedy generator and
  the joint solver the approved bookings that fall in the week they schedule,
  in the same `(start, end)` shape as existing timetable rows, so a booked
  room is simply not offered for that hour.
- `booked_room(cursor, room_id, day, start, end)` lets `check_slot` refuse a
  manual weekly slot that meets a weekly booking still in force
  (`slot_room_booked`); a dated booking does not block a weekly slot, because
  the booking side already refused it if the slot existed first.
- `create` and `decide` refuse a booking that meets a live timetable slot
  (`booking_room_busy`) or another approved booking (`booking_room_booked`)
  and return `error.alternatives`: free rooms of the same type the institution
  may use at that time.

Only `approved` bookings block anything. With `requires_approval` (the
capability's setting, default true) a request waits as `requested`; the
`rooms_change_room` holders of the institution that owns the room approve or
reject it (`booking_not_owned` for anyone else), and approval re-runs the
clash checks against the ledger as it is then. A `bookings_change` or `rooms_change_room` holder
booking a room their own institution owns is approved at once. The requester
may cancel their own booking; an approver may cancel any booking of their
rooms. Sharing follows Institutions: an institution may request any room
`candidate_rooms_clause` gives it.

| Route | Needs | Does |
| --- | --- | --- |
| `GET /api/bookings?status=&room_id=&from=&to=` | `bookings_view` or `rooms_view_room` | bookings of rooms the caller may see or that their institution asked for, plus the bookable rooms, kinds, `requires_approval` and `permissions` |
| `POST /api/bookings` | `bookings_view` or `rooms_view_room` | request or book; body `room_id, title, kind, booking_date | day_of_week [+ repeat_until], start_time, end_time, notes` |
| `GET /api/bookings/free-rooms?day=|date=&start_time=&end_time=&room_type=` | `bookings_view` or `rooms_view_room` | rooms free of timetable slots and approved bookings at that time |
| `POST /api/bookings/<id>/approve`, `/reject` | `bookings_change` or `rooms_change_room` of the owner | decide, optional `note` |
| `POST /api/bookings/<id>/cancel` | requester or owner approver | withdraw a requested or approved booking |

Decisions are audited (`booking_requested`, `booking_approved`,
`booking_rejected`, `booking_cancelled`). When notifications are on, a
request is queued to the approvers (`booking_request`) and the decision to
the requester (`booking_decision`). UI: Timetable → Bookings, which offers
the free rooms inline when a request is refused.
