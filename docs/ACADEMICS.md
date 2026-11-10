# Academic calendar

Capability `academic_terms` (off by default). With it off, or before any term is saved, timetables, close-day and attendance behave exactly as they do today. See [DESIGN_CAPABILITIES.md](DESIGN_CAPABILITIES.md).

## Terms

`academic_terms` already existed in the baseline (a name and dates on an academic year). `0019_academic_calendar` adds the institution, an optional semester and a kind. A term is a stretch of one academic year:

| Column | Meaning |
| --- | --- |
| `kind` | `teaching`, `exam`, `break` or `internship` |
| `start_date`, `end_date` | Inclusive. Must sit inside the academic year. |
| `semester_id` | NULL means the whole year. A whole-year term overlaps every semester term. |

An exam, break or internship term wins over a teaching term on the same date. A date in no term is not a teaching day once the institution has any term. Holidays stay in `institution_holidays` and are still removed on top.

`services/academic_calendar.py` is the only reader. `teaching_weeks(terms)` is the derived week list (one row per teaching term and Monday, with the teaching days left after closed terms and holidays). There is no view.

## What changes while it is on

- The greedy generator and the joint solver place sessions only on teaching days of the chosen week. A week with none fails with "None of the selected days fall in a teaching term."
- `flask attendance close-day` does not open a `not_marked` session on a non-teaching day (`outside_term` in its counts). The nightly not-marked digest therefore does not list exam or break days.
- Saving a term, and the nightly notification pass, cancel unmarked sessions that fall in an exam, break or internship term. `cancel_reason` is `calendar`. Sessions that already have marks are left as they were. Deleting a term does not restore them.
- Marking a lecture on a non-teaching day is refused (`SessionCancelled`) unless that session was already held.
- `GET /api/academic-terms` reports, for the last 30 days, `scheduled` (active slots on teaching days that are not holidays), `conducted` (held sessions on those days) and `attended` (Present or Late marks). Attendance percentages themselves are unchanged: a cancelled session was already outside the denominator.

## API

Reading needs `academic_terms_view` or `academicyears_view`. Adding, editing and deleting need `academic_terms_change`, or the matching academic-year permission (`academicyears_add`, `_change`, `_delete`). 404 `capability_off` when off. 409 `terms_table_missing` before `0019`.

- `GET /api/academic-terms` — `terms`, `weeks`, `totals`, `years`, `semesters`, `kinds`, `permissions`.
- `POST` and `PUT /api/academic-terms/<id>` — `{name, kind, start_date, end_date, academic_year_id, semester_id}`. 400 `term_invalid` or `term_overlap`. The response includes `cancelled_sessions`.
- `DELETE /api/academic-terms/<id>`.

Page: Academics → Calendar.

## Syllabus coverage

Capability `syllabus` (off by default). With it off the mark screen has no topic field, a topic sent by the mobile app is ignored, and nothing is written to `lesson_logs`.

`syllabus_units` is the plan for one subject: unit number, title, planned hours, order. `lesson_logs` is one topic per held lecture (the session, the unit, the topic, hours from 0.5 to 3). The teacher records it on the existing mark screen, or a device sends `topic`, `unit_id` and optional `hours` on `POST /mobile-sync/v1/attendance/sync`. Hours default to 1. An invalid topic rejects that event before the mark is stored.

Coverage is delivered hours of held lectures divided by planned hours. When the institution's academic calendar is configured, expected hours are planned × elapsed teaching weeks / total teaching weeks (a week counts once its Monday is today or earlier). Delivered more than half an hour above that is `ahead`, more than half an hour below is `behind`, otherwise `on_track`. With no calendar the pace is `no_pace` and the percentage is still shown. Attendance percentages are unchanged.

## Syllabus API

Reading needs `syllabus_view` or `subjects_view_subject`. Writing needs `syllabus_change` or `subjects_change_subject`. 404 `capability_off` when off. 409 `syllabus_unavailable` before `0020`.

- `GET /api/syllabus?subject_id=` — `subjects`, `coverage` (`units` with planned, delivered, percent, expected hours, pace, plus `elapsed_weeks` and `total_weeks`), `permissions`.
- `PUT /api/syllabus/<subject_id>` — `{units: [{id?, unit_no, title, planned_hours}]}`. 400 `syllabus_invalid`. 409 `syllabus_in_use` when a removed unit already has a lesson.
- `GET /api/v1/subjects/<id>/coverage` — same figures, scope `catalog:read`. 404 `capability_off` or `subject_not_found`.

Report type `syllabus-coverage` (Reports, permission `reports_view_attendance`) is listed only while the capability is on. It uses the same CSV, Excel and PDF renderers. Filters: `subject_id`, `department_id`.

Pages: Academics → Syllabus. The topic block on Mark attendance.

## Internal assessment

Capability `assessments` (off by default). With it off there is no Internals entry, the student and teacher tabs stay hidden, and nothing is stored.

`assessment_components` is one internal component of a subject: name, maximum marks, weight, and kind (`IA`, `assignment`, `practical`, `viva`, `project`). `assessment_marks` is one student's mark on that component. `course_outcomes` belong to a subject; `program_outcomes` belong to a course. `component_co_map` says which course outcomes a component assesses. `co_po_map` stores the correlation level, 1 to 3.

A student's percentage on a component is marks / maximum × 100. For each course outcome, a student's score is the weighted mean of those percentages on the components mapped to it (a weight of 0 on every mapped component counts them equally). Students with no mark on those components are left out. The outcome's attainment is the mean of the counted students, rounded to two decimals. The level follows the share of counted students at or above 60 percent: 3 at 70 percent or more, 2 at 60 percent, 1 at 50 percent, otherwise 0. A program outcome's attainment is the mean of the mapped course-outcome percentages weighted by the correlation level. The same bands, applied to that percentage, give its level.

Students see a mark only after the component is locked (`assessments_lock` or `subjects_change_subject`). Unlocking hides it again. The attainment figures and the report count every entered mark, locked or not. External results, grades and transcripts are not computed here.

## Assessment API

Reading the scheme needs `assessments_view` or `subjects_view_subject`. Changing it needs `assessments_change` or `subjects_change_subject`. Locking needs `assessments_lock` or `subjects_change_subject`. A teacher allocated to the subject may read and save its marks. 404 `capability_off` when off. 409 `assessment_unavailable` before `0021`.

- `GET /api/assessments?subject_id=` — subjects, components, course outcomes, program outcomes, the CO–PO map, attainment and `permissions`.
- `PUT /api/assessments/subjects/<id>/outcomes` — `{outcomes: [{code, statement}]}`.
- `PUT /api/assessments/subjects/<id>/components` — `{components: [{id?, name, max_marks, weight, kind, outcome_codes}]}`. 409 `assessment_locked` when a locked component would change or disappear. 409 `assessment_in_use` when a removed outcome is still used by a locked component.
- `PUT /api/assessments/courses/<id>/outcomes` — program outcomes, same shape.
- `PUT /api/assessments/subjects/<id>/map` — `{links: [{co_code, po_code, level}]}`.
- `GET` and `PUT /api/assessments/components/<id>/marks` — the class roster and `{marks: [{student_id, marks}]}`. Blank marks clear the row.
- `POST /api/assessments/components/<id>/import` — `{csv}`, `{rows: [{roll_number, marks}]}` or `{xlsx_base64}`. The header is `roll_number,marks`. Unknown rolls are returned and skipped.
- `POST /api/assessments/components/<id>/lock` and `/unlock`.
- `GET /api/portal/student/assessments` — locked marks for the signed-in student.
- `GET /api/portal/teacher/assessments` — components on subjects allocated to the signed-in teacher.
- `GET /api/v1/subjects/<id>/internals` — locked components and marks, scope `catalog:read`.

Report type `co-attainment` (Reports, permission `reports_view_attendance`) is listed only while the capability is on. Filters: `subject_id`, `course_id`, `department_id`. A subject filter limits the course-outcome rows; program outcomes still use every subject of that course.

Pages: Academics → Internals. Teachers and students: Internals, while the capability is on.

## Exam timetable

Capability `exams` (off by default). With it off there is no Exams entry, the teacher duty list stays hidden, and nothing is stored. Room bookings and the weekly generator are unchanged.

`exams` is one timetable: a name, a kind (`internal`, `university` or `practical`) and an optional exam term. `exam_sessions` is one paper at one date and time. `exam_session_cohorts` records the classes, `exam_session_rooms` the rooms, `exam_seats` each student's seat, and `invigilation_duties` who is in the room (`chief` or `invigilator`).

Solving places every selected paper on one slot. Two papers that share a student — a core paper and an elective, or two cores of one cohort — never share a slot. A shared elective is one paper, so every cohort that selected it sits it together. Usable seats in a room are its capacity divided by one more than the seating gap (a gap of 1 leaves every other seat empty), then capped by students per room when that is set. Each used room gets one invigilator who is not absent, not marked unavailable, and not already on duty in that slot. Duties are spread so the busiest person has as few sessions as possible.

While `bookings` is on, those rooms are busy on that date and time, so a new booking is refused and the generator avoids them for that week. A weekly timetable slot is not blocked by a one-day exam. Regular classes during an exam term are cancelled by the academic calendar when that capability is on, with reason `calendar`.

## Exam API

Reading needs `exams_view` or `timetable_generate`. Creating, solving and deleting need `exams_change` or `timetable_generate`. A teacher reads only their own duties. 404 `capability_off` when off. 409 `exam_unavailable` before `0022`.

- `GET /api/exams?exam_id=` — exams, exam terms, subjects, rooms, the selected exam's sessions and `permissions`.
- `POST /api/exams` — `{name, kind, term_id?}`.
- `POST /api/exams/<id>/solve` — `{subject_ids}` or `{papers: [{subject_id, cohorts: [{class_id, division_id?}]}]}`, plus optional `dates`, `slots` (`[{start, end}]`), `room_ids`, `seating_gap` (0–3) and `students_per_room`. With no dates, the exam term's first twelve weekdays are used. With no slots, 09:30–12:30 and 14:00–17:00. With no rooms, the first rooms in scope are used. 409 `exam_unsolved` when no arrangement fits.
- `DELETE /api/exams/<id>`.
- `GET /api/exams/<id>/seating` and `GET /api/exams/<id>/hall-tickets` — PDF via the report renderer.
- `GET /api/portal/teacher/exams` — the signed-in teacher's duties.

Pages: Academics → Exams. Teachers: Exam duties, while the capability is on.
