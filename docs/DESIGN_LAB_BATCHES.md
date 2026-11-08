# Lab batches (proposal for timetable v2)

Status: proposal. Nothing here exists in the schema yet.

## The gap

A practical is usually taught to part of a division at a time: division A
splits into batches A1, A2 and A3, and each batch has its own lab slot,
room and sometimes teacher. The schema cannot say this:

- `course_batches` is an intake cohort (a course's 2026–2029 students), not
  a lab group. `timetable.course_batch_id` and `students.course_batch_id`
  point at it.
- No table says which students are in which lab group, and no timetable
  column says that a slot belongs to one group.

So the attendance roster for a lab slot is the whole division, and a
teacher can mark a student from another batch. The strict xfail
`test_batch_lecture_refuses_a_student_in_another_batch` in
`tests/integration/test_teacher_attendance.py` records this.

## Proposed tables

### `lab_batch_groups`: the batches a division is split into

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int PK | |
| `course_id` | int FK `courses.id` | |
| `class_id` | int FK `classes.id` | |
| `division_id` | int FK `divisions.id` NULL | NULL splits the whole class (no divisions) |
| `academic_year_id` | int FK `academic_years.id` | Batches are re-formed each year |
| `semester_id` | int FK `semesters.id` NULL | NULL means the same split all year |
| `name` | varchar(20) | "A1", "Batch 2" |
| `capacity` | int NULL | Lab seats; the generator can respect it |
| `is_active` | tinyint(1) | |

Unique key: (`course_id`, `class_id`, `division_id`, `academic_year_id`,
`semester_id`, `name`).

### `lab_batch_members`: which batch a student is in

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int PK | |
| `lab_batch_group_id` | int FK `lab_batch_groups.id` ON DELETE CASCADE | |
| `student_id` | int FK `students.id` ON DELETE CASCADE | |
| `added_at` | timestamp | |

Unique key: (`lab_batch_group_id`, `student_id`). A student is in at most
one batch per (division, academic year, semester). The service enforces
that rule because a single unique key cannot express it.

### Timetable link

Add `timetable.lab_batch_group_id` (int FK `lab_batch_groups.id`, NULL).
NULL means the slot is for the whole division (or the whole class when
`division_id` is NULL). `timetable.course_batch_id` keeps its current
meaning (intake cohort).

Index: (`lab_batch_group_id`), plus the existing timetable indexes.

## Roster rule once the tables exist

For a timetable row:

1. Start from students in the slot's course and class, narrowed to its
   division when it has one (what `fetch_lecture_roster` does today).
2. If the subject is an elective, keep students with a
   `student_subject_selections` row for it (also done today).
3. If `lab_batch_group_id` is set, keep students with a
   `lab_batch_members` row in that group.

## Modules each change touches

| Change | Modules |
| --- | --- |
| `lab_batch_groups`, `lab_batch_members` tables | New Alembic revision (idempotent, with downgrade); `core/schema` comparison (new tables in the baseline diff); new admin CRUD: a `data_access`/`services` pair plus an `api/web` route and a React screen to create batches and assign students; `seeders` (none needed by default) |
| `timetable.lab_batch_group_id` | Same revision; `data_access/admin_timetable.py` and `api/web/timetable.py` (manual create/edit, conflict checks: two batches of one division may share a time slot, but one batch cannot be in two places); `services/timetable_jobs.py` and the generator in `academic_rules` / `ml_models` (schedule each batch's practical hours, respect `capacity` against `rooms.capacity`); timetable exports in `services/reports_admin/timetable.py` and `dataset.py` |
| Attendance roster | `data_access/teacher_attendance.py` `fetch_lecture_roster` (step 3 above); `data_access/teacher_portal.py` `fetch_class_students` and `fetch_teaching_class_counts`; `api/mobile/v1/student_sync.py` (`sync_timetable` per-lecture roster, `resolve_timetable`); `api/mobile/v1/sync_attendance.py` (`_resolve_timetable_id_from_event`, `_has_active_timetable_for_group`) |
| Student timetable and percentages | `data_access/student_portal.py` (today's classes, timetable: show only the student's batch slots); the `attendance_summary` and `student_overall_attendance` views (the denominator should count only the slots the student belongs to) and every consumer of them: `services/attendance_admin/students.py`, `services/attendance_admin/exports.py`, `api/web/attendance.py`, `api/web/student.py` |
| Faculty load | `data_access/admin_faculty.py`, `api/web/people/faculty.py` (a batch slot is a full teaching hour for the teacher, though it covers only part of the division) |
| Tests | Turn the batch xfail into a passing test; add roster tests for batch slots, a whole-class slot, and a student who changes batch mid-semester |

## Migration of existing data

None is required: every existing timetable row gets `lab_batch_group_id`
NULL, so it stays a whole-division slot. Colleges then create batches and
re-point practical slots at them.
