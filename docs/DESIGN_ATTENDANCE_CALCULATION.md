# Attendance calculation foundation (design, approved)

Status: approved 8 Nov 2026 with the recommended default for every open question in section 6. Phases 0–3 (section 7) are implemented: `attendance_calc/`, revision `0007_lecture_sessions`, `services/lecture_sessions.py`, `flask attendance close-day` / `backfill-sessions`, the close-day worker, teacher and admin cancel endpoints, proxy marking, the slot-delete guard, the loader (`data_access/attendance_calc.py`, `services/attendance_calc.py`), the student, home, overview, defaulter and export consumers with their React screens, (Phase 3) the teacher's per-lecture report, the admin statistics, charts, overview export and report dataset, the mobile roster and marker checks, and the close-day absent fill, and (Phase 4) revision `0008_attendance_views`. Phase 5 is not started. Live-database facts below come from read-only `SELECT COUNT` queries on 8 Nov 2026.

## 1. How attendance is computed today

Six independent computations exist. None of them knows whether a lecture was held, so none has a correct denominator.

### 1.1 The `attendance_summary` view (per student x subject)

- **Roster**: `students s JOIN timetable t WHERE t.course_id = s.course_id AND t.class_id = s.class_id AND t.division_id = s.division_id`. A slot with `division_id NULL` never matches (`NULL = x` is not true), and a student with `division_id NULL` matches nothing. Every slot of the cohort counts, including retired slots (`is_active` is ignored), every `timetable_type`, and every semester.
- **Denominator**: `COUNT(DISTINCT t.id)` = the number of **weekly slots** for the subject, not the number of lectures held. The numerator `COUNT(DISTINCT a.id WHERE status IN ('Present','Late'))` counts rows across every date. After the first week the percentage exceeds 100 %. The live database shows no row above 100 % only because it holds a single marked session.
- **Electives**: every student of the cohort appears for every elective slot; students who did not choose the subject show 0 %.
- **Holidays / cancellations / unmarked lectures**: not represented. A cancelled or unmarked lecture has no rows, which does not change the slot-count denominator.

### 1.2 The `student_overall_attendance` view (per student)

- **Roster**: `students JOIN classes JOIN divisions` (inner), so the one live student with `division_id NULL` disappears from every defaulter list. `LEFT JOIN timetable` on the cohort again requires `t.division_id = s.division_id`, so whole-class slots never contribute.
- **Denominator**: `COUNT(DISTINCT t.id WHERE a.attendance_date <= CURDATE())` = the number of **distinct slots in which this student has at least one row** of any status. Numerator = Present/Late rows across all dates. A slot marked four times with the student present three times gives 300 %. A slot in which the student was never marked (the teacher skipped them) is not in the denominator at all.
- **Electives / no-division / holidays**: as 1.1.

### 1.3 Teacher report (`data_access/teacher_attendance.fetch_attendance_summary`)

- **Roster**: students of the chosen class + division (`fetch_lecture_filters` needs a division, so no-division lectures are unreachable).
- **Denominator**: `COUNT(DISTINCT a.id)` = marked rows only. The filter `(t.subject_id = %s OR a.id IS NULL) AND t.faculty_id = %s` makes the `a.id IS NULL` branch impossible (`t.faculty_id` is NULL when there is no row), so students who were never marked vanish from the report instead of showing 0.
- Unmarked, cancelled, holiday: not counted; only marked rows exist.

### 1.4 Admin report and export (`services/reports_admin/attendance.py`, `dataset.py`)

- **Roster**: students (inner join divisions) `LEFT JOIN attendance ON s.id = a.student_id`. There is no timetable join: the rows of **every subject**, in every cohort the student ever belonged to, are pooled. Course/class/division filters apply to the student, not the slot. With a date filter, students with no rows in the range drop out (the condition is in `WHERE`).
- **Denominator**: `COUNT(a.id)` marked rows. `s.id AS roll_number` shows the student id as the roll number.

### 1.5 Defaulter list, overview, charts (`services/attendance_admin/*`, `api/web/attendance.py`)

- Defaulters (`attendance_defaulters`, `attendance_overview` count, `api/web/attendance.overview`) read view 1.2 with `overall_percentage < threshold`.
- **`export_defaulters` is dead**: it selects `st.full_name`, `soa.total_classes`, `soa.present_count`, `soa.absent_count`, `soa.late_count`, `soa.attendance_percentage`. None exist (the view has `total_lectures`, `total_present`, `total_absent`, `total_late`, `overall_percentage`; students has `name`). Every call raises "Unknown column" and returns 500.
- Overview statistics, `export_overview`, `charts_data`: Present+Late rows / all rows in the last 30 days (marked rows). Class-level grouping inner-joins divisions.

### 1.6 Student portal (`data_access/student_portal.py`, `api/web/student.py`, `api/web/attendance.student`, `api/web/portal_actions.py`)

- Overall from view 1.2, per subject from view 1.1, monthly breakdown from marked rows (`COUNT(*)` per month), recent records filtered by `t.division_id = st.division_id` (whole-class lectures invisible). Today's classes and the weekly timetable require `t.division_id = %s`, so a whole-class lecture is not shown to the student.

### 1.7 Mobile sync (`api/mobile/v1/student_sync.py`, `sync_attendance.py`)

- Computes no percentages. It **writes** rows: one `attendance` row per uploaded event (face-detected student), `ON DUPLICATE KEY UPDATE`. Students the device did not detect get **no row**, so they are neither present nor absent anywhere.
- Slot resolution: a strict day/time match, then `_resolve_timetable_id_relaxed`, which ignores the day and time and picks the newest active slot of the cohort (and subject when given). An event can therefore be attached to a different lecture of the same cohort. `_timetable_matches_student_context` requires division equality when the student has one, so a whole-class slot is rejected.
- The roster the device receives from `sync_timetable` is the division roster (no electives). The upload path validates status and ids; I found no check that `attendance_date` is today or the slot's weekday (the teacher form has both checks). The only live session, 10 Feb 2026, is on a different weekday from its slot.

### 1.8 Related facts that shape the design

- `attendance.marked_by` references `faculty.id`; `timetable.faculty_id` references `faculty.user_id`. The app keeps them equal by convention.
- `attendance.timetable_id` is `ON DELETE CASCADE`. The generator retires slots (`is_active = 0`) and inserts new ones, so history survives regeneration, but the single-slot delete in `data_access/admin_timetable.py:102` runs `DELETE FROM timetable` and **erases that slot's attendance history**.
- `timetable.semester_id` and `academic_year_id` are NULL on all 147 live rows. Nothing can be scoped by semester from the slot today.
- `institution_holidays` (dated or recurring weekday, per program UG/PG/Both) is used by the generator and the availability rules, never by attendance. Live: 1 dated, 1 recurring.
- Substitution lives in `proxy_log(timetable_id, absence_date, proxy_faculty_id, status ASSIGNED/UNASSIGNED, approval_status)`. `proxy_assignments` has no `timetable_id` and 0 live rows. The teacher form refuses a proxy teacher (`t.faculty_id = user`); mobile derives `marked_by` from the slot when the device omits it.
- Live counts: attendance 4 rows (1 session), timetable 147 (57 active, 0 with NULL division), subjects 36 (7 elective), selections 0, students 50 (1 with NULL division), proxy_log 3 (1 approved), attendance_logs 0, semesters 4 (1 current).

### 1.9 One student, five answers

Cohort FY A. Physics has two weekly slots (Mon, Thu), three weeks, 5 lectures held plus one holiday. Student Asha: P, P, P, A, P. German is an elective (Tue) she did not choose; the 10 choosers were marked three times. Environmental Studies (EVS) is a whole-class lecture (division NULL), Asha present 3 of 3.

| Source | Physics | German | EVS | Overall |
| --- | --- | --- | --- | --- |
| `attendance_summary` (portal subject list, admin student page) | 4 present / 2 slots = **200 %** | 0 present / 1 slot = **0 %** | not listed | — |
| `student_overall_attendance` (defaulter list, portal, student home) | — | ignored (no rows) | ignored | 4 / 2 slots = **200 %** |
| Teacher report | 4 / 5 marked = **80 %** | Asha not listed | unreachable (needs a division) | — |
| Admin report / dataset export | — | — | counted | (4+3) / (5+3) = **87.5 %** |
| Admin overview (30 days) | — | — | counted | 7 / 8 = **87.5 %** |
| Correct answer (held lectures, chosen subjects) | 4 / 5 = **80 %** | not her subject | 3 / 3 = **100 %** | 7 / 8 = **87.5 %** |

With one more week of marks the two views exceed 200 % while the others stay below 100 %.

## 2. One calculation module

Package `attendance_calc/` (pure Python, no Flask, no SQL). `data_access/attendance_calc.py` loads the inputs; `services/attendance_calc.py` is the only entry point screens, exports and notifications call. The pure functions are unit-tested with hand-calculated golden values; the loader is tested once against the test database.

### 2.1 Inputs

```python
@dataclass(frozen=True)
class Slot:          # one timetable row
    id: int; subject_id: int; course_id: int; class_id: int; division_id: int | None
    component: str   # 'Theory' | 'Practical', from subjects.theory_practical / course_type
    is_elective: bool; semester_id: int | None; academic_year_id: int | None
    faculty_user_id: int; is_active: bool

@dataclass(frozen=True)
class Session:       # one lecture_sessions row
    id: int; slot_id: int; date: date
    status: str      # 'held' | 'cancelled' | 'not_marked'
    taught_by: int | None

@dataclass(frozen=True)
class Mark:          # one attendance row
    session_id: int; student_id: int; status: str   # 'Present' | 'Absent' | 'Late'

@dataclass(frozen=True)
class Student:
    id: int; course_id: int; class_id: int; division_id: int | None
    enrolled_from: date | None; enrolled_to: date | None   # see open question 5
    chosen_subjects: frozenset[tuple[int, int | None, int | None]]  # (subject_id, semester_id, academic_year_id) from student_subject_selections, not Withdrawn
    batch_ids: frozenset[int] = frozenset()                # lab batches, later

@dataclass(frozen=True)
class Excuse:        # one attendance_excuses row (open question 3)
    student_id: int; date_from: date; date_to: date; subject_id: int | None

@dataclass(frozen=True)
class Policy:
    unmarked_counts_as_absent: bool = False   # open question 1
    late_counts_as_present: bool = True        # open question 2
    excused_mode: str = 'exclude'              # 'exclude' | 'present'   (open question 3)
    threshold: Decimal = Decimal('75')         # open question 7
```

### 2.2 Functions

```python
def in_roster(slot: Slot, student: Student, on: date) -> bool
```
True when the student belongs to the slot's cohort on that date: same course and class; same division when the slot has one (a slot with no division takes the whole class); for an elective slot, a `chosen_subjects` entry for the subject whose semester and year match the slot's when the slot has them; when lab batches exist (see `DESIGN_LAB_BATCHES.md`), the slot's batch must be in `student.batch_ids`; and `enrolled_from <= on <= enrolled_to` when those are set. This is the one roster rule; `data_access/teacher_attendance.fetch_lecture_roster` becomes its SQL twin and a test keeps the two in step.

```python
def countable_sessions(sessions, slot, student, excuses, policy) -> list[Session]
```
Sessions of the slot the student is in the roster for, `status = 'held'`, plus `not_marked` when `policy.unmarked_counts_as_absent`; minus sessions covered by an excuse when `excused_mode == 'exclude'`. Cancelled sessions never count. Holidays have no session row (section 3.4) so they never count.

**Mark rule (as implemented).** A mark the teacher saved for a student on a session is evidence that the student was in that lecture, so it counts even when the roster rule says otherwise that day (a division transfer, an enrolment date, or an elective choice recorded late never hides saved marks). Only a cancelled session ignores its marks, and cancelling a marked session is refused unless the admin clears them.

**Excuse rule (as implemented).** An excuse excuses an absence, nothing else. A session in an excuse's date range is `excused` only when the student has an `Absent` mark, no mark on a held lecture, or the lecture is `not_marked`. A `Present` or `Late` mark on an excused date still counts as attended, so a student who came in during sick leave is not penalised for it. A held lecture with no mark for a rostered student is `unrecorded`; it is governed by `unmarked_counts_as_absent` exactly like `not_marked`.

```python
def summarise(student, slots, sessions, marks, excuses, policy) -> StudentSummary
```
Returns per subject, per component (Theory, Practical) and overall:

| Field | Meaning |
| --- | --- |
| `held` | held sessions in the student's roster |
| `countable` | denominator after policy |
| `present`, `late`, `absent`, `excused`, `not_marked`, `unrecorded` | counts |
| `attended` | `present + late` when late counts, else `present`; plus `excused` when `excused_mode == 'present'` |
| `percentage` | `attended * 100 / countable`, 2 dp, **`None` when `countable == 0`** (shown as "—", never 0 and never above 100) |
| `classes_needed`, `classes_that_can_be_missed` | on the summary, from the overall figures; **`None` when `countable == 0`**, like the percentage |

Overall and per-component figures are **pooled** (sum of attended / sum of countable), not the mean of subject percentages (open question 8).

```python
def classes_needed(attended, countable, threshold) -> int
```
Smallest `n >= 0` with `(attended + n) / (countable + n) >= threshold / 100`:
`n = max(0, ceil((threshold * countable - 100 * attended) / (100 - threshold)))`. For 75 %: `n = max(0, 3 * countable - 4 * attended)`.

```python
def classes_that_can_be_missed(attended, countable, threshold) -> int
```
`max(0, floor(100 * attended / threshold - countable))`.

```python
def can_still_reach(attended, countable, threshold, remaining) -> bool
```
`(attended + remaining) / (countable + remaining) >= threshold / 100`, where `remaining` = planned future sessions of the student's slots in the term: for each active slot, the number of its weekdays from tomorrow to the term end that are working days for the slot's course program (`academic_rules.holidays`). Returns `None` when the term end is unknown.

```python
def unmarked_report(sessions, slots) -> list[UnmarkedLecture]   # for the admin "not marked" screen
```

### 2.3 Contract rules

- Pure functions, deterministic, no clock: the caller passes `today`.
- Every number a screen shows comes from `StudentSummary`; no SQL aggregate computes a percentage anywhere else.
- Percentages are `Decimal`, rounded once at the end.

## 3. The `lecture_sessions` table

One row per lecture occurrence: "slot X on date D happened / was cancelled / was never marked."

```sql
CREATE TABLE lecture_sessions (
  id              INT NOT NULL AUTO_INCREMENT,
  timetable_id    INT NOT NULL,
  session_date    DATE NOT NULL,
  status          ENUM('held','cancelled','not_marked') NOT NULL,
  taught_by       INT NULL,           -- faculty.user_id: the approved proxy, else the slot's faculty
  marked_by       INT NULL,           -- faculty.id of the first marker
  marked_at       DATETIME NULL,
  cancelled_by    INT NULL,           -- users.id
  cancelled_at    DATETIME NULL,
  cancel_reason   ENUM('faculty_absent','institution','exam','other') NULL,
  source          ENUM('teacher','mobile','admin','close_day','backfill') NOT NULL,
  session_code    VARCHAR(16) NULL,   -- face-attendance pairing code, later
  session_code_expires_at DATETIME NULL,
  notes           VARCHAR(255) NULL,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_lecture_session (timetable_id, session_date),
  KEY idx_lecture_session_date (session_date),
  KEY idx_lecture_session_status (status),
  CONSTRAINT fk_lecture_session_slot FOREIGN KEY (timetable_id) REFERENCES timetable(id) ON DELETE RESTRICT,
  CONSTRAINT fk_lecture_session_taught_by FOREIGN KEY (taught_by) REFERENCES faculty(user_id) ON DELETE SET NULL,
  CONSTRAINT fk_lecture_session_marked_by FOREIGN KEY (marked_by) REFERENCES faculty(id) ON DELETE SET NULL,
  CONSTRAINT fk_lecture_session_cancelled_by FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE attendance ADD COLUMN session_id INT NULL AFTER timetable_id,
  ADD KEY idx_attendance_session (session_id),
  ADD CONSTRAINT fk_attendance_session FOREIGN KEY (session_id) REFERENCES lecture_sessions(id) ON DELETE RESTRICT;
```

`ON DELETE RESTRICT` on purpose: a slot with sessions cannot be deleted (the admin single-slot delete must retire it instead), and a session with marks cannot be deleted. `attendance.session_id` stays nullable in 0007 and becomes `NOT NULL` in 0008 after the backfill has run on every database. The existing unique key `(student_id, timetable_id, attendance_date)` stays; `(timetable_id, attendance_date)` is also the session's key, so the two agree.

No `scheduled` status: future lectures have no row. A row appears when something is known about the date.

### 3.1 Rows created on first marking

`save_teacher_attendance` and `_promote_log_to_attendance` (mobile) run, in the same transaction as the marks:

```sql
INSERT INTO lecture_sessions (timetable_id, session_date, status, taught_by, marked_by, marked_at, source)
VALUES (%s, %s, 'held', %s, %s, NOW(), %s)
ON DUPLICATE KEY UPDATE status = 'held', marked_by = COALESCE(marked_by, VALUES(marked_by)),
                        marked_at = COALESCE(marked_at, VALUES(marked_at));
```

then set `attendance.session_id` on every upserted row. Marking a `not_marked` session turns it into `held`. Marking a `cancelled` session is refused (the admin must un-cancel first).

### 3.2 Rows created by the nightly close-day job

`flask attendance close-day [--date YYYY-MM-DD] [--dry-run]`, also run by the existing background worker after midnight. For the given date (default yesterday):

1. Skip the date entirely when it is not a working day for a program (`institution_holidays`, dated or recurring, `applies_to_program` matching the slot's course program).
2. For every active slot whose `day_of_week` is that weekday and whose course program has a working day, and whose current semester (open question 6) includes the date, and that has no `lecture_sessions` row: insert `status = 'not_marked', source = 'close_day', taught_by = <proxy or slot faculty>`.
3. Idempotent: re-running for the same date inserts nothing. Accepts a date range for catching up after downtime.
4. Writes one `audit_logs` row with the counts.

The job never creates `held` rows and never touches a row that exists.

### 3.3 Rows created by cancellation

`POST /api/portal/attendance/cancel/<timetable_id>` (date, reason, note) for the slot's teacher or the approved proxy for that date; `POST /api/attendance/sessions/<id>/cancel` for admins with `attendance_manage`. Both upsert `status = 'cancelled'`, `cancelled_by`, `cancelled_at`, `cancel_reason`. Refused when the session has marks (`attendance.session_id = id`) unless the admin passes `clear_marks = true`, which deletes the marks in the same transaction and is audited. Un-cancel sets the row back to `not_marked` (or `held` if marks exist). Every change is written to `audit_logs` with the request's cursor.

A faculty absence (`faculty_absences`) with no approved proxy does **not** cancel automatically; close-day still writes `not_marked`, and the admin "not marked" screen shows the absence beside it (open question 4).

### 3.4 Holidays

A holiday is the absence of a session: close-day creates no row for it, so it is in no denominator. A lecture marked on a holiday (a makeup class) gets a `held` row on first marking and counts. Recurring weekday holidays and dated holidays are both honoured through `academic_rules.holidays`. A new pure helper `is_working_day(date, program, holidays)` is added there and shared with the generator.

### 3.5 Substitution

`taught_by` is resolved from `proxy_log WHERE timetable_id = slot AND absence_date = date AND status = 'ASSIGNED' AND approval_status = 'APPROVED'`, else the slot's `faculty_id`. Marking permission for a date becomes "slot owner **or** `taught_by` for that date" in `fetch_owned_lecture_detail` and the mobile upload path. Percentages do not depend on who taught. `proxy_assignments` (no `timetable_id`, 0 live rows) is not used.

### 3.6 Backfill of historical rows

`flask attendance backfill-sessions [--dry-run]`:

1. For every `DISTINCT (timetable_id, attendance_date)` in `attendance` with no session row: insert `status = 'held', source = 'backfill', marked_by = <most frequent marked_by>, marked_at = MIN(marked_at), taught_by = <proxy_log or slot faculty>`.
2. Set `attendance.session_id` for every row with `session_id IS NULL`.
3. Never create `not_marked` rows for the past: nothing records which past lectures were held, so the backfill invents no lectures. Percentages for the period before Phase 1 therefore use marked lectures only, which is what every current report does.
4. The dry run prints: sessions to create, rows to link, and anomalies, each with counts and ids: sessions whose weekday differs from the slot's `day_of_week` (1 in the live database), sessions on retired slots, marks whose student is outside the slot's roster, marks whose `marked_by` is not the slot's faculty or an approved proxy, and marks on dates that are institution holidays. Anomalies are reported, not fixed; the apply run links them like every other row and records the anomaly list in `audit_logs`.
5. The live database needs 1 session and 4 links.

## 4. The two existing views

**Deprecate both and drop them in 0008.** They cannot be made correct without the sessions table, and a rebuilt view would again freeze one policy (unmarked, late, excused) into SQL that every consumer shares blindly. Phase 1 (0007) leaves them in place so nothing breaks while consumers move; Phase 4 (0008) drops them once no code reads them. `test_live_schema_revisions.py`, `test_migration_baseline.py` and `docs/DATABASE.md` list the dropped views as expected differences.

Consumers that must change (every one moves to `services/attendance_calc`):

| Consumer | Reads today |
| --- | --- |
| `services/attendance_admin/students.py` overview count, `attendance_defaulters`, `student_attendance_details` | both views |
| `services/attendance_admin/exports.py` `export_defaulters` (broken), `export_overview`, `charts_data` | view 1.2; marked rows |
| `api/web/attendance.py` `overview`, `student` | both views |
| `api/web/student.py` home | view 1.2 |
| `data_access/student_portal.py` `fetch_overall_attendance`, `fetch_attendance_totals`, `fetch_subject_attendance`, `fetch_subject_stats`, `fetch_monthly_attendance`, `fetch_recent_attendance`, `fetch_today_classes`, `fetch_student_timetable` | both views; marked rows; division-only cohort |
| `services/reports_admin/attendance.py`, `dataset.py` | marked rows, all subjects pooled |
| `data_access/teacher_attendance.py` `fetch_attendance_summary`, `fetch_lecture_filters` | marked rows; needs a division |
| `api/mobile/v1/student_sync.py` roster served to the device, slot resolution | division roster; relaxed resolver |
| `frontend/src/features/attendance/pages/AttendancePage.tsx` | gains "—" for no data, excused and not-marked counts, "classes needed" |

## 5. Migration and test plan

### 5.1 Revision `0007_lecture_sessions`

- Creates `lecture_sessions` (3.0) and `attendance_excuses` if open question 3 is answered "table" (`id, student_id, date_from, date_to, subject_id NULL, reason, approved_by, created_at`).
- Adds `attendance.session_id` (nullable), its index and foreign key.
- Idempotent: checks `information_schema` before each statement, like 0006. Downgrade drops the foreign key, the column and the tables, only when they exist.
- Does not touch the views.

### 5.2 Revision `0008_attendance_views` (Phase 4)

- `attendance.session_id` → `NOT NULL` (refuses to run when any row is NULL and prints the backfill command).
- Drops `attendance_summary` and `student_overall_attendance`. Downgrade recreates them from the baseline text and makes the column nullable again.

### 5.3 Commands

- `flask attendance backfill-sessions [--dry-run]` (3.6).
- `flask attendance close-day [--date] [--from --to] [--dry-run]` (3.2).
- Both print counts only, never names, and write one audit row when applying.

### 5.4 Golden tests (`tests/unit/test_attendance_calc.py`, no database)

Fixture: cohort FY A, three weeks, Mon 2 Mar – Fri 20 Mar 2026. Slots: Physics (Theory) Mon and Thu; Lab (Practical) Wed; German (elective, Theory) Tue; EVS (Theory, division NULL) Fri. Dated holiday Thu 12 Mar. Policy: unmarked excluded, late = present, excused excluded, threshold 75. Students: Asha (division A, no German), Ben (division A, chose German), Chen (division A, enrolled from Mon 9 Mar), Dev (division B).

| # | Scenario | Sessions | Marks | Expected |
| --- | --- | --- | --- | --- |
| 1 | Normal lecture | Physics: 2 Mar held, 5 Mar held, 9 Mar held, 12 Mar holiday (no row), 16 Mar held, 19 Mar cancelled | Asha P, A, P, P | held 4, countable 4, attended 3, **75.00 %**, needed 0, can miss 0 |
| 2 | Elective | German: 3 Mar held, 10 Mar held, 17 Mar not_marked | Ben P, L | Ben **100.00 %** (2/2); with `unmarked_counts_as_absent` **66.67 %** (2/3). Asha: German absent from her summary; her overall unchanged |
| 3 | No division | EVS: 6, 13, 20 Mar held | Asha P, P, A; Dev P, P, P | Asha **66.67 %**; Dev (division B) **100.00 %**, EVS in both summaries |
| 4 | Cancelled | Physics 19 Mar cancelled | none | not in `held` or `countable`; cancelling a session with marks is refused |
| 5 | Holiday | 12 Mar | none | close-day creates no row; a mark on 12 Mar creates a `held` row that counts (Physics becomes 5 held) |
| 6 | Excused | Asha excused 4–6 Mar (medical) | as #1 and #3 | Physics: the 5 Mar absence is excused → 3/3 = **100.00 %** (excluded mode), 4/4 = **100.00 %** (present mode), `excused` = 1. EVS 6 Mar: Asha was marked Present, so the mark counts and nothing is excused → 2/3 = **66.67 %**. Lab 4 Mar: Present, counts. Overall 7/9 = **77.78 %** |
| 7 | Mid-semester | Chen from 9 Mar | Physics 9 Mar P, 16 Mar A | countable 2 (2 and 5 Mar outside enrolment, 19 Mar cancelled), **50.00 %**, needed 2 |
| 8 | Unmarked | German 17 Mar not_marked | — | excluded by default; `not_marked` = 1 in Ben's German row; appears in `unmarked_report` with the slot teacher |

Pooled totals for Asha (without #6): Physics 3/4, Lab (4 Mar P, 11 Mar P, 18 Mar A) 2/3, EVS 2/3 → Theory 5/7 = **71.43 %**, Practical 2/3 = **66.67 %**, overall 7/10 = **70.00 %** (the mean of subject percentages would be 69.44 %, which the module does not report). `classes_needed(7, 10, 75) = 2`: (7+2)/(10+2) = 75 %. `can_still_reach(7, 10, 75, remaining=0)` is False; with `remaining = 2` True. `percentage` is `None` for a student with no countable sessions.

### 5.5 Integration tests (live, `tests/integration`)

- `test_lecture_sessions.py`: marking creates a `held` row in the same transaction (a failed mark leaves no session); mobile promotion creates one; close-day creates `not_marked` only for working days of the right weekday and is idempotent; cancel/un-cancel rules; holiday creates no row; proxy teacher may mark on the proxy date and not on others; deleting a slot with sessions is refused.
- `test_attendance_calc_live.py`: builds scenarios 1–3 and 7 through the factory, calls the API endpoints and asserts the same numbers as the golden tests; `fetch_lecture_roster` agrees with `in_roster` for the normal, elective and no-division cases.
- `test_attendance_backfill.py`: on a scratch database with the live-shaped dump plus synthetic rows: dry-run changes nothing and reports the right counts and anomalies; apply creates the sessions and links; a second apply changes nothing.
- 0007 and 0008 upgrade/downgrade in `test_live_schema_revisions.py` and `test_migration_baseline.py`.

## 6. Open questions

Recommended default in bold.

1. **Unmarked lecture**: counts against the student (absent), is **excluded from the percentage and shown as a count**, or counts as held with no mark? Should the admin be able to switch per institution?
2. **Late**: **counts as present** (current behaviour everywhere) or as a separate state with its own threshold?
3. **Excused absence**: a new `attendance.status` value `Excused` (touches the enum, the mobile contract and the admin form) or **a separate `attendance_excuses` table with date ranges and an approver**? Does an excused session leave the denominator (**recommended**) or count as present?
4. **Faculty absent, no approved proxy by day end**: auto-cancel, or **`not_marked` plus a flag on the admin screen** for a human decision?
5. **Mid-semester students**: where does `enrolled_from` / `enrolled_to` come from? Options: **`students.created_at` as `enrolled_from` and `is_active` → `updated_at` as `enrolled_to` for Phase 1**, with a proper `student_enrolments` table (course, class, division, batch, from, to) in a later phase so division transfers keep history.
6. **Term scoping**: `timetable.semester_id` is NULL on every live slot. Should the percentage window be the current semester's dates (**recommended, with the admin setting `semester_id` on slots during generation**), the academic year, or all time? Who maintains semesters?
7. **Threshold**: fixed 75 %, **an institution setting (default 75)**, or per course/program? Separate thresholds for Theory and Practical?
8. **Overall figure**: **pooled** (sum/sum) or the mean of subject percentages? Report Theory and Practical separately?
9. **Holidays**: `institution_holidays` is per program (UG/PG/Both). Are class- or course-specific no-lecture days needed (exam weeks, `timetable_type = 'Exam'`)?
10. **Mobile**: should the device, or close-day, write `Absent` for roster students the device did not detect (**yes, at session close, so a face-marked lecture has a full roster**)? Should mobile keep accepting marks for dates other than today, and should the relaxed slot resolver stay?
11. **Retired slots**: their past sessions keep counting (**yes**). Should the single-slot admin delete become "retire" when the slot has sessions (**yes**)?
12. **Cancellation rights**: slot teacher for own lectures, HOD for the department, admin for all (**recommended**)? Can a `held` session be cancelled after marks exist?
13. **Display with no data**: "—" (**recommended**) or 0 %?
14. The 4 live rows on 10 Feb 2026 (weekday mismatch): backfill as `held` (**recommended; it is what was marked**) or leave unlinked for review?
15. Lab batches stay out of scope until `DESIGN_LAB_BATCHES.md` is built; `in_roster` already has the `batch_ids` hook.

## 7. Phased plan

Each phase ships and is tested on its own; the suite stays green between phases.

| Phase | Ships | Depends on | Tests | Visible change |
| --- | --- | --- | --- | --- |
| **0. Pure module** | `attendance_calc/` with `in_roster`, `countable_sessions`, `summarise`, `classes_needed`, `classes_that_can_be_missed`, `can_still_reach`, `unmarked_report`; `academic_rules.holidays.is_working_day` | answers to Q1–3, 7, 8 | golden tests 5.4 | none |
| **1. Sessions recorded** | 0007; session upsert in teacher and mobile marking; cancel/un-cancel endpoints; `close-day`; `backfill-sessions` with dry run; proxy may mark; slot delete refuses when sessions exist | Phase 0, Q4, Q6, Q11, Q12, Q14 | 5.5 first three files, 0007 up/down | new rows accumulate; cancel button for teachers; admin "not marked" list |
| **2. Student and defaulter screens** | `services/attendance_calc` loader; student portal, student home, `api/web/attendance.student`, defaulter list, overview defaulter count, `export_defaulters` rewritten; frontend shows "—", excused, not-marked, classes needed | Phase 1, Q5, Q13 | live scenario tests; old-vs-new comparison on fixtures | percentages change (and can no longer exceed 100 %); whole-class and elective lectures correct |
| **3. Reports and exports** | admin report, dataset export, teacher report (whole-class reachable, unmarked students shown), overview statistics, charts; mobile roster from `in_roster`; undetected students written `Absent` at close (Q10) | Phase 2 | report tests | reports agree with the portal |
| **4. Cleanup** | 0008: `session_id NOT NULL`, drop both views; remove old queries; `DATABASE.md`; permission canon updates | Phase 3 run everywhere | schema tests updated | none |
| **5. Later** | `student_enrolments`, excuses UI and approval, projections in notifications, lab batches, face session codes | Phase 4 | — | — |

Phase 0 needs only the policy answers and can start as soon as they arrive; Phase 1 is the first schema change.

Phase 1 as shipped differed from the table in one place: the mobile upload path recorded sessions but its permission check was unchanged (the device still derived the teacher from the slot); Phase 3 closed that.

Phase 2 as shipped: `data_access/attendance_calc.py` loads the rows and `services/attendance_calc.py` is the entry point (`student_report`, `cohort_reports`, `defaulters`, `monthly_breakdown`). Q5 is the Phase 1 option: `enrolled_from = DATE(students.created_at)`, `enrolled_to = DATE(students.updated_at)` once `is_active = 0`; the mark rule in 2.2 keeps saved marks visible whatever those dates say. Q6: a slot with `semester_id` counts only sessions inside the semester's dates; a slot without one counts every session. Q7: `ATTENDANCE_THRESHOLD_PERCENT` (default 75), overridable per call with `?threshold=`. Consumers moved: `/api/portal/student/attendance` (+ `/<subject_id>`), `/api/portal/student` (whose timetable now shows whole-class slots and only chosen electives), `/api/portal/attendance`, `/api/attendance/overview` (defaulters, `defaulter_count`, `not_marked_count`, `threshold`), and `/admin/attendance/export/defaulters` (which works again). The legacy `services/attendance_admin/students.py` functions only serve the React page, so their view queries were removed rather than rewritten. React: the student attendance and subject pages show "—", excused, not-marked, Theory/Practical pooled figures and the classes-needed advice; the student home shows "—"; the admin attendance page shows the threshold, a richer defaulter table and the "lectures nobody marked" list with a cancel action for `attendance_manage`; the teacher mark page has the cancel / undo control. `test_attendance_calc_live.py` covers scenarios 1–3, 6 (cancelled), 7, semester scoping, the admin list, the export and the roster agreement. No code reads `attendance_summary` or `student_overall_attendance` any more.

Phase 3 as shipped. **Teacher report**: folded into the existing history endpoint rather than a new route. `GET /api/portal/attendance/history/<timetable_id>[?from=&to=]` now lists every `lecture_sessions` row of the slot (held, cancelled with its reason, not marked) with the marks on each, plus `students`: every roster student of the slot (so a whole-class or elective lecture is reachable and a never-marked student is shown with "—") with their figures for the slot's **subject** pooled over all of the teacher's slots of it, and the `threshold`. The slot's teacher or an approved proxy may see it. The old `fetch_attendance_summary` / `fetch_lecture_filters` / `load_attendance_report` (division required, marked rows only) are deleted; the legacy `/teacher/attendance/report/attendance-report` route only renders the shell. **Admin**: `/api/attendance/overview` reports the last 30 days from `period_statistics` (`total_students` with something countable, `total_lectures`, `total_records` = countable, present/late/absent/excused/not_marked, pooled `percentage`); `/admin/attendance/charts/data` builds the trend (now with Excused and Not marked series) and the per-class distribution from report outcomes; `/admin/attendance/export/overview` lists today's cohorts with pooled figures; the `attendance` report dataset (`services/reports_admin/dataset.py`) is `cohort_reports` over the chosen cohort and dates with columns `student_id, roll_number, full_name, course_name, class_name, division_name, held, total_classes (countable), present, late, absent, excused, not_marked, attendance_percentage (empty when nothing is countable), classes_needed`, listing the whole cohort; `services/reports_admin/attendance.py` only renders the shell. **Mobile** (Q10): `GET /timetable` and `/timetable/resolve` include whole-class slots (`LEFT JOIN divisions`) and the roster comes from `fetch_lecture_roster` (electives by selection); `_promote_log_to_attendance` refuses (`MarkRefused`, the log row is marked failed) a student outside the slot's roster or a marker who is neither the slot's teacher nor the approved proxy for the date. The device still accepts dates other than today and the relaxed resolver stays, as the question left open. **Close-day**: after writing `not_marked` rows, for every `held` session of the day with `source = 'mobile'`, roster students without a mark get an `Absent` row (`marked_by` = the session's first marker, remark "Not detected by the attendance device"), reported as `absent_filled`; teacher-marked sessions are left alone, because a teacher's form says who it covers while a device only says who it saw. The SQL roster (`roster_clauses`) now also excludes inactive students, as the mobile roster always did. Tests: `test_attendance_calc_live.py` (period statistics, overview keys, charts, overview export, dataset, history with cancelled/not-marked rows and roster figures, date range, access) and `test_lecture_sessions.py` (absent fill incl. dry run, idempotence and inactive students; no fill for teacher sessions; roster and marker refusals; proxy accepted).

Phase 4 as shipped: `0008_attendance_views` is 5.2 as written: `attendance.session_id` → `NOT NULL`, both views dropped, a `RuntimeError` naming the backfill command (and the cancelled-lecture marks the backfill leaves for review) when any row is unlinked, downgrade recreating the views from the baseline text under `SET NAMES utf8mb4` so they match the originals byte for byte; each direction changes only what still needs it. Because `flask db upgrade` now stops at 0008 on a database with unlinked marks, `flask attendance backfill-sessions` accepts a database at 0007 or later (`core.schema.status.revisions_from`; every other command still needs head); the deployment order is upgrade, backfill, upgrade (`docs/DATABASE.md`). The admin "reprocess mobile logs" promoter in `services/attendance_admin/_common.py`, the last writer of marks without a session, now delegates to the device upload's promoter (session recorded, roster and marker checked). The close-day CLI prints the device-absence count Phase 3 added. `test_migration_baseline.py` named in section 4 does not exist; the equivalent coverage is `tests/unit/test_attendance_views_revision.py` (statements and the refusal), `test_live_schema_revisions.py` (0008 up and down on the live-schema copy, recreated views identical to the live ones) and `test_attendance_backfill.py`, whose module steps the test database down to 0007 and checks that 0008 refuses while marks are unlinked and runs once they are linked. The permission canon needed no change: Phase 3 added no permission, and the teacher report stays behind the portal's teacher check. On 9 Nov 2026 `college_timetable_db` was at 0007 with every mark linked (read-only check); 0008 has not been applied to it.
