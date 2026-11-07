# Duplication report

Date: 2026-10-26. Branch: `refactor/structure`.

This is a scan only. No functions were moved, and no request, response, or scheduling rule was changed.

A later extract must keep each call site’s current rule. Several copies look alike and then differ on status values, active-row filters, or which faculty id they mean. Those differences are called out below. Do not fold them into one function with one default.

## 1. Date and time parsing

**Locations**

| What | Where |
| --- | --- |
| `HH:MM` parse | `routes/timetable_algorithm.py` `_parse_time` |
| `YYYY-MM-DD` parse that returns the original string | `routes/api/access.py` `iso_date` |
| `YYYY-MM-DD` parse to a `date` | `routes/faculty/absences.py`, `routes/mobile/student_sync.py`, `routes/admin/attendance_admin.py` |
| ISO datetime with a trailing `Z` | `routes/mobile/sync_attendance.py` `_parse_iso_datetime` |
| Clock display `HH:MM`, including MySQL `timedelta` | `format_time` in `routes/admin_utils.py`, `routes/faculty/teacher.py`, `routes/faculty/attendance.py`, `routes/students/student.py`; `format_time_filter` in `app_factory.py`; `safe_clock` in `routes/api/security.py` |
| 12-hour display | `format_time_12hr_filter` in `app_factory.py`; some attendance pages use `%d %b %Y` and `%I:%M %p` |
| Weekday name | `strftime('%A')` in the timetable generator, teacher home, dashboards, and both proxy helpers |

The four `format_time` copies match, except `routes/students/student.py`, which returns a string unchanged. The others pass a string through `str()`. `safe_clock` also wraps a `timedelta` with `% 86400` before formatting. `format_time_12hr_filter` is a different format and stays separate.

**Proposed home:** `utils/dates.py`

```python
def parse_hhmm(value, field_name: str) -> datetime.time: ...
def parse_iso_date(value: str) -> datetime.date: ...
def format_hhmm(value, *, keep_string: bool = False) -> str: ...
def weekday_name(value) -> str: ...
```

Callers keep their own error text. `format_hhmm(..., keep_string=True)` is the student path. `safe_clock` stays on the `/api` allowlist and is not replaced by `format_hhmm`. Display formats other than `HH:MM` stay at the call site.

## 2. Holiday checks

**Locations**

- Week load used by generation: `routes/timetable_algorithm.py` around the `institution_holidays` query in `generate_timetable_for_class`. It loads recurring days and dates inside the week, for the course program or `Both`, then skips those days.
- Single-day block used by the manual add form: `routes/admin/timetable.py` in the add-session handler. It only rejects a recurring holiday for that weekday and program. It does not look up a calendar date.
- Create and edit uniqueness: `routes/admin/holiday.py` and `routes/api/catalog/holidays.py`. Both reject a second recurring row for the same weekday and program. The API also excludes the row being edited. The HTML form does not.
- Upcoming list: `routes/admin/dashboard.py`. Read-only, not a scheduling rule.

**Proposed home:** `academic_rules/holidays.py`

```python
def holidays_for_week(cursor, program: str, week_start, week_end) -> list: ...
def recurring_holiday_blocks_day(cursor, program: str, day_name: str) -> bool: ...
def recurring_holiday_taken(cursor, day_name: str, program: str, ignore_id: int | None) -> bool: ...
```

`holidays_for_week` is the generator query, moved as written. `recurring_holiday_blocks_day` is the manual-add query, moved as written. The HTML uniqueness check keeps `ignore_id=None`. Do not make the manual add use the week query.

## 3. Availability and absence

**Availability**

- Generator policy: `faculty_is_available` inside `generate_timetable_for_class` (`routes/timetable_algorithm.py`). An absence on that date blocks the slot. A busy span already assigned in this run blocks it. An explicit `is_available = 0` window that overlaps the slot blocks it. A recorded shift window does not block a slot outside that shift.
- Manual add policy: `routes/admin/timetable.py` add-session handler. If any availability row exists for that faculty and day, the slot must sit inside an `is_available = 1` window, and an overlapping `is_available = 0` window blocks it. This is stricter than the generator.
- Saves of availability rows are repeated in `routes/admin/faculty.py` (`manage_faculty_availability` and `faculty_availability_admin`) and `routes/faculty/availability.py`. Each path deletes existing rows and inserts the submitted slots. One path commits the delete before the insert.

**Absence**

- Teacher JSON: `routes/faculty/absences.py`. Inserts status `UNPROCESSED`. The id is `session['faculty_id']`, which is `faculty.id`.
- Admin JSON: `routes/admin/faculty.py` `faculty_absences_admin`. Inserts status `PROCESSED`. The id is the faculty id in the URL.
- Teacher page list: `routes/faculty/teacher.py`. API list: `routes/api/teacher.py` (limited to 20 rows).
- Generator: loads `faculty_absences` for the week and compares that `faculty_id` with `faculty_allocations.faculty_id`. Allocation faculty ids are user ids. Absence rows are stored with `faculty.id` on the teacher and admin forms. Leave that comparison where it is. Do not “correct” it while extracting.

**Proxy assignment**

- `find_and_assign_proxy` in `routes/faculty/teacher.py` inserts `proxy_log` with `status` only.
- `_admin_find_and_assign_proxy` in `routes/admin_utils.py` inserts the same match, and also sets `approval_status = 'APPROVED'`, `approval_date = NOW()`, and `approved_by`.

The free check under both is the same timetable overlap, and it does not filter `is_active`.

**Proposed home:** `academic_rules/availability.py` and `academic_rules/absences.py`

```python
def faculty_blocked_for_generation(faculty_id, day_name, slot_group, day_date, busy_state, availability_map, absence_keys) -> tuple[bool, str | None]: ...
def manual_add_availability_block(cursor, faculty_id, day_name, start_time, end_time) -> str | None: ...
def faculty_timetable_free(cursor, faculty_id, day_name, start_time, end_time) -> bool: ...
```

`faculty_blocked_for_generation` is today’s `faculty_is_available`, moved with its comments. `manual_add_availability_block` returns the same `ValueError` texts the form raises now. `faculty_timetable_free` replaces only `_is_faculty_free` and `is_faculty_available`.

Absence inserts stay in their routes until a signature carries the status:

```python
def insert_absence(cursor, faculty_row_id: int, absence_date, reason: str, status: str) -> None: ...
```

`status` is `'UNPROCESSED'` for the teacher route and `'PROCESSED'` for the admin route. Proxy inserts stay separate for the same reason: the column lists differ.

## 4. Clash checks

**Locations**

- Python overlap: `routes/timetable_algorithm.py` `_times_overlap`. A nested `overlaps` in `find_available_room` only calls that function.
- SQL overlap `NOT (end_time <= %s OR start_time >= %s)`:
  - class, faculty, and unavailable-window checks in `routes/admin/timetable.py`, with `COALESCE(is_active, 1) = 1` on timetable rows
  - room conflict select in the same file, also active-only, excluding the row being edited
  - `_is_faculty_free` and `is_faculty_available`, with no `is_active` filter

The predicate matches. The `is_active` filter does not. A shared helper must take that filter as an argument supplied by the caller.

**Proposed home:** `academic_rules/clashes.py`

```python
def times_overlap(a_start, a_end, b_start, b_end) -> bool: ...
def timetable_slot_taken(cursor, *, day, start, end, active_only: bool, faculty_id=None, course_id=None, class_id=None, division_id=None, room_id=None, exclude_id=None) -> bool: ...
```

`times_overlap` is `_times_overlap` moved as written. `active_only=True` is the manual timetable add and the room assign. `active_only=False` is the proxy free check. Room assignment still builds its own conflict message after the boolean check. That message stays in the route.

## 5. Pagination

**Locations**

- Shared helper: `routes/admin_utils.py` `paginate`. It builds `SELECT COUNT(*)` by cutting the query at the first ` FROM `, then adds `LIMIT` and `OFFSET`. Default page size is 10. An `ORDER BY` or a subquery in that tail becomes part of the count.
- Separate copies, each with its own count query and page size:
  - `routes/admin/students.py` (10)
  - `routes/admin/audit_logs.py` (50)
  - `routes/admin/attendance_admin.py` (20, 50, or 100)
  - `routes/api/people/students.py` (10, and the total is passed through `safe_count`)

**Proposed home:** `core/pagination.py`

```python
def page_bounds(page: int, per_page: int, total: int) -> tuple[int, int]: ...
```

Returns `(offset, total_pages)` using the integer math already at each site. Each site keeps its own `per_page` and its own `COUNT` query. Do not route the API student list through `paginate`, because that helper’s count rewrite can change totals, and the API total is capped by `safe_count`.

## 6. JSON responses

**Locations**

- `/api` envelope is already shared: `routes/api/responses.py` `json_ok` and `json_error`. Shape: `success` plus `data`, or `success` plus `error.code` and `error.message`.
- Mobile uses a different shape. `_json_error` in `routes/mobile/security.py` and `routes/mobile/sync_attendance.py` returns `{"success": false, "error": "<string>"}`.
- Older JSON still returns `jsonify` directly: admin reports, faculty absence lists (`{"data": items}`), and faculty availability. Those are not the `/api` envelope.

**Proposed home:** move the existing `/api` helpers later to `core/responses.py` with the same two signatures. Leave mobile `_json_error` in the mobile package. Do not point admin or faculty `jsonify` calls at `json_ok`. That would change the body.

## 7. Permission checks

Three adapters already exist, and they answer in different ways.

| Adapter | Where | On failure |
| --- | --- | --- |
| `has_permission` | `security/__init__.py` | Flash and redirect to login |
| Local `has_permission` | `routes/admin/branding.py` | Flash and redirect to `auth.dashboard`. Uses `check_user_permission` rather than the SQL inside the security decorator |
| `permission_denied` and `allowed` | `routes/api/access.py` | 401 `unauthorized`, 403 `forbidden`, or 500 with the caller’s code and message |

`routes/api/departments.py`, `routes/api/courses.py`, and `routes/api/rooms.py` each repeat `_permission_error` and `_can`. The catalog, people, users, and settings modules already call `permission_denied`.

**Proposed home:** keep `security.has_permission` and `security.check_user_permission`. Keep `routes/api/access.py` `permission_denied` and `allowed` as the JSON adapters. A later edit can delete the three local copies only when the 500 message and the log line stay the ones each file uses today. The branding decorator redirects somewhere else, so it stays a separate wrapper even if it calls `check_user_permission`.

Role gates that only check `session['role']` (`admin_required`, `teacher_required`, `student_required`) are not the same check. Leave them.

## 8. Validation

**Locations**

- Shared JSON parsers: `routes/api/access.py` `required_text`, `optional_text`, `flag`, `iso_date`, `whole_number`, `optional_id`, `decimal_number`, `body`. Failures raise `InputError`.
- Copies that raise a different exception: `_required_text` and `_optional_text` in `routes/api/departments.py` (`_DepartmentInputError`) and `routes/api/courses.py` (`_CourseInputError`). Each file’s save handler catches its own exception.
- HTML forms: `utils/forms.py` (WTForms). Login, registration, users, and invitations. These are not the JSON parsers.

**Proposed home:** keep the parsers in `routes/api/access.py` for now. A later move to `core/validation.py` re-exports the same names. Departments and courses can call `required_text` only if their handlers still catch the exception they catch today. One way is to keep the local exception and wrap `required_text`. Do not run WTForms and the JSON parsers through one function.

## 9. Commit and rollback

The same shape is repeated: open a connection, `commit` on the success path, `rollback` in `except`, close in `finally`. `routes/api/access.py` `close` is the only shared closer, and most routes still close inline.

Families, not every line:

- Catalog and record APIs: `routes/api/catalog/` (`years`, `semesters`, `batches`, `subjects`, `allocations`, `holidays`), `routes/api/courses.py`, `routes/api/departments.py`, `routes/api/rooms.py`, `routes/api/people/`, `routes/api/users.py`, `routes/api/account.py`.
- Admin writes: `routes/admin/faculty.py`, `routes/admin/students.py`, `routes/admin/timetable.py`, `routes/admin/holiday.py`, `routes/admin/rooms.py`, `routes/admin/branding.py`, `routes/admin/shift_management.py`, `routes/admin/attendance_admin.py`, `routes/admin/reports.py`, `routes/user_management_routes.py`, `routes/academic_routes.py`.
- Teacher, mobile, and auth: `routes/faculty/`, `routes/mobile/`, `routes/auth_routes.py`, `routes/profile_routes.py`.

`routes/admin/faculty.py` and `routes/faculty/availability.py` commit the availability `DELETE` before the `INSERT`, with a comment that the delete must commit first. A wrapper that commits once at the end would change that.

**Proposed home:** `core/db.py`

```python
@contextmanager
def transaction(connection): ...
```

Commits if the block finishes, rolls back if it raises, and does not close the connection. Use it only where the route already has one commit at the end. Skip the availability delete-then-insert paths. Skip `routes/timetable_algorithm.py`, whose commits stay with generation until that file is split.

## 10. Audit logging

`log_activity` already lives in `security/__init__.py`. Callers are login and logout, profile and password changes, user and role administration, report exports, and a few `/api` user and account writes.

Catalog saves, holiday saves, timetable generation, attendance marking, and most faculty edits do not call it. That is current behavior. An extract must not add `log_activity` calls, because that would insert new audit rows.

No new module. Later code keeps calling `log_activity(user_id, activity_type, description=None, entity_type=None, entity_id=None, old_values=None, new_values=None)`.

## 11. File uploads

| Caller | Allowed types | Name | Folder |
| --- | --- | --- | --- |
| `routes/admin/branding.py` | png, jpg, jpeg, gif, svg | `{setting}_{timestamp}_{filename}` | `static/uploads/branding` |
| `routes/profile_routes.py` | png, jpg, jpeg, gif | `{user_id}_{timestamp}_{filename}` | `static/uploads/profiles` |
| `routes/mobile/sync_attendance.py` `upload_face_image` | png, jpg, jpeg, webp | `{user_id}_{utc_timestamp}_{filename}` | `static/uploads/profiles` |
| `routes/admin/students.py` `bulk_invite_students` | csv or spreadsheet, read with pandas | not stored as an image | not a static upload |

Branding and profile both use `secure_filename` plus a local timestamp. The mobile upload uses UTC and a different allowlist, including `webp` and excluding `gif` and `svg`. Profile upload is still the HTML form. It was not ported to `/api`, and this scan does not port it.

**Proposed home:** `utils/uploads.py`

```python
def save_uploaded_file(file_storage, relative_dir: str, *, allowed_extensions: set[str], name_prefix: str, timestamp: str) -> str: ...
```

The caller passes the allowlist, prefix, and timestamp it already builds. The helper only does `secure_filename`, joins the path under `static/`, creates the directory, and saves. The student CSV reader stays in the students route.

## Leave in place until a later phase

- `routes/timetable_algorithm.py` slot building, scoring, and candidate selection. Clash and holiday helpers can be called from there later. The generator body moves only in the timetable split, function by function, with the old import left behind.
- Face image decoding and embedding. The mobile upload saves a file. Embedding generation stays in `services/face/`.
- `/mobile-sync/v1` response helpers. There is no `/api/v1` blueprint.

## If this is approved

Suggested order, still one step at a time:

1. Done. `utils/dates.py` `format_hhmm`. The old `format_time` names still call it. The student route passes `keep_string=True`. `safe_clock` and the 12-hour filter were not changed.
2. Done. Departments, courses, and rooms call `permission_denied` and `allowed`. Departments and courses translate `required_text` and `optional_text` into their own input errors. Rooms had no copy of those text helpers. Log lines and 500 messages are unchanged.
3. Done. `core/pagination.py` `page_bounds` supplies the offset and page count. Each list still runs its own count query and keeps its page size. Attendance still uses at least one page and still clamps the requested page before the offset.
4. Done. `academic_rules/clashes.py` has `times_overlap` and `faculty_timetable_free`. The generator still calls `_times_overlap`. Proxy free checks pass `active_only=False`, so inactive timetable rows still block a proxy. The manual add and room-conflict queries were not moved.
5. Done. Holiday week load, the manual weekday block, and recurring-holiday uniqueness call `academic_rules/holidays.py`. Generation availability and the manual availability block call `academic_rules/availability.py`. A shift window still does not block generation. The manual form still requires a covering available window.
6. Done. `utils/uploads.py` `save_uploaded_file` stores branding, profile, and mobile face images. Each caller still checks its own allowlist, builds its own timestamp, and keeps its own error text. The student CSV import was not moved. `core/db.py` `transaction` commits one open transaction and rolls back if that block raises. It is used by the department, course, year, semester, batch, subject, allocation, and holiday saves and deletes, by room delete, and by branding init, update, and reset. The read after a year, batch, or holiday save stays outside the block. Student, faculty, account, shift, user, and room-save handlers still call `commit()` because some of their input-error paths do not roll back. Availability saves that commit a delete before the insert, and the timetable generator commits, were not wrapped.
7. Done. `core/exceptions.py` defines `AppError`, `NotFoundError`, `ForbiddenError`, and `UnavailableError`. `errors.py` maps them with the same JSON envelope as `json_error`. Pages still use the React response. The CSRF handler is unchanged. Route input errors still return their own codes from the route.
