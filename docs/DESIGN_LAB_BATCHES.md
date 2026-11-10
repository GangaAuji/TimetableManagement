# Lab batches

Status: implemented in revision `0012_lab_batches`. This page describes what
exists; the original gap and the choices made are kept for context.

## The gap this closes

A practical is usually taught to part of a division at a time: division A
splits into batches A1, A2 and A3, and each batch has its own lab slot,
room and sometimes teacher. Before 0012 the schema could not say this:

- `course_batches` is an intake cohort (a course's 2026–2029 students), not
  a lab group. `timetable.course_batch_id` and `students.course_batch_id`
  point at it and keep that meaning.
- No table said which students were in which lab group, and no timetable
  column said that a slot belonged to one group.

So the attendance roster for a lab slot was the whole division, and a
teacher could mark a student from another batch.

## Tables

### `lab_batch_groups`: the batches a division is split into

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int PK | |
| `course_id` | int FK `courses.id` CASCADE | |
| `class_id` | int FK `classes.id` CASCADE | |
| `division_id` | int FK `divisions.id` CASCADE, NULL | NULL splits the whole class (no divisions) |
| `academic_year_id` | int FK `academic_years.id` CASCADE | Batches are re-formed each year |
| `semester_id` | int FK `semesters.id` CASCADE, NULL | NULL means the same split all year |
| `name` | varchar(20) | "A1", "Batch 2" |
| `capacity` | int NULL | Lab seats; the generator and the member screen respect it |
| `is_active` | tinyint(1) | Inactive groups are left out of splits and generation |
| `created_at`, `updated_at` | timestamp | |

Unique key `uq_lab_batch_group` (`course_id`, `class_id`, `division_id`,
`academic_year_id`, `semester_id`, `name`). MariaDB treats NULLs as distinct
in unique keys, so `services/lab_batches.py` also checks for a same-named
group before inserting or renaming (`lab_batch_exists`).

### `lab_batch_members`: which batch a student is in, and when

| Column | Type | Notes |
| --- | --- | --- |
| `id` | int PK | |
| `lab_batch_group_id` | int FK `lab_batch_groups.id` CASCADE | |
| `student_id` | int FK `students.id` CASCADE | |
| `added_at` | date NOT NULL | First day the student belongs to the batch |
| `ended_at` | date NULL | Last day; NULL while current |

Unique key `uq_lab_batch_member` (`lab_batch_group_id`, `student_id`).

Memberships are dated rather than deleted. When a student moves from A1 to
A2 on 1 March, the A1 row gets `ended_at = 28 Feb` and an A2 row starts on
1 March. A student is current in at most one batch per split (same cohort,
year and semester); `set_members` enforces that, since one unique key cannot.

### Timetable link

`timetable.lab_batch_group_id` (int FK `lab_batch_groups.id` ON DELETE SET
NULL, NULL). NULL means the slot is for the whole division (or whole class
when `division_id` is NULL). Deleting a group turns its slots back into
whole-division slots; attendance is never deleted. Index
`idx_timetable_lab_batch`.

## Roster rule

For a timetable row on a given date:

1. Start from students in the slot's course and class, narrowed to its
   division when it has one.
2. If the subject is an elective, keep students with a
   `student_subject_selections` row for it.
3. If `lab_batch_group_id` is set, keep students with a `lab_batch_members`
   row in that group where `added_at <= date` and (`ended_at IS NULL OR
   ended_at >= date`).

`data_access/teacher_attendance.roster_clauses(lecture, on_date)` is the
single SQL form of this rule, used by the teacher mark screen, the history
screen, mobile sync and the mark endpoints. `attendance_calc/roster.py`
applies the same rule in Python for percentages: `Student.batch_memberships`
holds the dated rows, so a session before a student's `added_at` or after
`ended_at` is OUTSIDE the roster and is not counted against them. A saved
mark is roster evidence, so marks taken before a move keep counting.

## Clash rule

`academic_rules/clashes.cohort_slots_clash(batch_a, batch_b)`: a
whole-division slot (NULL) clashes with everything in the division; two
slots of the same batch clash; slots of different batches do not, so A1 and
A2 can run practicals at the same time with different teachers and labs.
Faculty and room clashes are unchanged (one person or room, one place).

## Where it is used

| Area | Modules |
| --- | --- |
| CRUD and members | `data_access/lab_batches.py`, `services/lab_batches.py`, `api/web/catalog/lab_batches.py` (`/api/lab-batches`, `/members`, `/split`), React `features/academics/pages/LabBatchesPage.tsx`. Permissions are the course-batch ones (`batches_view/add/change/delete`). |
| Manual slots | `services/timetable_slots.py` (`add_slot`, `remove_slot`), `POST /api/timetable/slots`, `DELETE /api/timetable/slots/<id>`; the timetable page shows a batch label per session and an add-slot form. Removing a slot that already has attendance or sessions retires it (`is_active = 0`) instead of deleting it. |
| Generation | `services/timetable/generator.py` expands each practical into one session per active batch (`load_lab_batches`), sizes rooms by batch, and fills the other batches into the same slot with a different teacher and lab (`fill_parallel_batches`). `services/timetable/joint_solver.py` models batches as separate demands with the cohort exclusivity rule above. See [TIMETABLE.md](TIMETABLE.md). |
| Attendance roster | `data_access/teacher_attendance.py`, `services/teacher_attendance.py`, `services/lecture_sessions.py`, `api/mobile/v1/sync_attendance.py`, `api/mobile/v1/student_sync.py` (payloads carry `lab_batch_group_id` and `lab_batch_name`). |
| Percentages | `data_access/attendance_calc.fetch_batch_memberships`, `services/attendance_calc.to_student`, `attendance_calc/roster.py`. |
| Student and teacher portals | `data_access/student_portal.STUDENT_SLOT_FILTER` shows only the student's own batch slots; `data_access/teacher_portal.fetch_teaching_class_counts` counts a batch's members. |
| Notifications | `services/notifications.py` addresses batch slots to batch members only and names the batch in the cohort label. |
| Tests | `tests/unit/test_lab_batches.py`, `tests/integration/test_lab_batches_live.py`, the batch cases in `tests/integration/test_teacher_attendance.py`; `tests/factories.py` has `lab_batches()` and `enrol_in_batch()`. |

## Migration of existing data

None is required: every existing timetable row has `lab_batch_group_id`
NULL, so it stays a whole-division slot. Colleges create batches on the Lab
batches page, assign students (or "deal by roll number"), and either add
batch slots by hand or regenerate the timetable.
