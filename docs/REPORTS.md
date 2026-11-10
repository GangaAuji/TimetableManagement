# Reports and exports

Every report is queued from the Reports page (`POST /api/reports`), written
by the export worker (`services/export_jobs.py`) into the reports folder,
and downloaded from `GET /api/reports/<id>/download`. This note covers the
file formats and the accreditation templates added for NAAC/NBA binders.

## Formats

`format` on the request is `csv` (default), `xlsx` or `pdf`. The renderer
(`services/reports_admin/renderers.py`) takes the same dataset (ordered
field names plus dict rows) for all three:

- **CSV**: the raw field names as headings, one row per record; what
  scripts and spreadsheets import.
- **Excel** (`openpyxl`): a title block (institution, report, the filters
  used, generated-at), a bold header row with readable labels
  (`roll_number` becomes "Roll number"), frozen panes and column widths.
- **PDF** (`reportlab`): the same title block and a ruled table that
  repeats its header on every page; landscape when there are more than
  seven columns; page numbers in the footer.

The download sets the mimetype from the file's extension. The users,
audit-log and timetable bulk exports stream row by row and stay CSV.

## Accreditation templates

Report types built in `services/reports_admin/accreditation.py`. The attendance
templates use the same `attendance_calc` figures the screens show, so a binder
printout agrees with the dashboard. `syllabus-coverage` is separate and appears
only while that capability is on. `co-attainment` is the NBA course-outcome and program-outcome table and appears only while capability `assessments` is on.

| Type | Rows | Filters | Permission |
| --- | --- | --- | --- |
| `defaulters` | students below the threshold, lowest first, with shortfall and lectures needed | course, class, division, dates, `threshold` (institution default when empty) | `reports_view_attendance` |
| `subject-wise` | one row per subject and cohort: pooled held/countable/attended, present/late/absent/excused/not-marked, percentage, students below the threshold | course, class, division, dates, `subject_id` | `reports_view_attendance` |
| `monthly-register` | student x lecture-date matrix for one month with P/L/A/E/NM cells and totals | `month` (YYYY-MM, required), course and class (required), division, `subject_id` (all subjects when empty) | `reports_view_attendance` |
| `faculty-workload` | per faculty member: weekly slots and hours, lectures scheduled, held, cancelled, not marked, taken as proxy, held %; with the `workload_norms` capability on, also designation, norm min/max and a `workload_flag` (under/ok/over/no_norm), plus `outside_norm` in the meta | dates, `department_id`, `faculty_id` | `reports_view_timetable` |
| `syllabus-coverage` | one row per syllabus unit: planned hours, delivered hours, coverage %, expected hours and pace (`behind`, `ahead`, `on_track`, `no_pace`). Listed only while capability `syllabus` is on; an empty file when it is off | `subject_id`, `department_id` | `reports_view_attendance` |
| `co-attainment` | one row per course outcome and per program outcome: students counted, how many reached 60%, attainment % and level (3 / 2 / 1 / 0). Listed only while capability `assessments` is on; an empty file when it is off. A subject filter limits the course-outcome rows; program outcomes use every subject of that course | `subject_id`, `course_id`, `department_id` | `reports_view_attendance` |

Meta lines in the Excel and PDF title block record the filters (cohort,
period, threshold, month, legend) so the file explains itself.

Exam seating plans and hall tickets use the same PDF renderer, downloaded from the exam
(`GET /api/exams/<id>/seating` and `GET /api/exams/<id>/hall-tickets`) while capability `exams` is on.
They are not queued report types. See [ACADEMICS.md](ACADEMICS.md).

## Tests

`tests/integration/test_accreditation_reports.py` builds each template on
the golden cohort from `docs/DESIGN_ATTENDANCE_CALCULATION.md`, renders all
three formats, and runs a queued report through the export worker and the
download endpoint.
