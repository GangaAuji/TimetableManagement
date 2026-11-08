# Database and migrations

## Supported server

**10.4.32-MariaDB** is the supported database engine. The baseline, its snapshot, and the tests are taken on that version. Other MariaDB or MySQL versions report types, defaults, and view text differently, so `flask db-adopt` will warn and is likely to list differences that come only from the server.

The MySQL 8.2 dumps in `backups/` are not the source of the schema. They use `utf8mb4_0900_ai_ci`, which MariaDB 10.4 does not have, and they do not match the live database.

## How the schema is managed

Alembic, through Flask-Migrate, owns the schema. The application still reads and writes rows with raw SQL in `models/db.py`. There are no ORM models.

| Revision | What it does |
| --- | --- |
| `0001_baseline` | Creates the `college_timetable_db` schema: 54 tables and 10 views. The SQL is in `migrations/sql/0001_baseline.sql`. |
| `0002_catch_up` | Adds `faculty_attendance` and `faculty_attendance_logs`, which the code uses but the live database lacks. Idempotent. |
| `0003_security_schema` | Adds `roles.hierarchy_level` (if missing), seeds the role levels, and creates `rate_limit_counters`. Downgrade drops `rate_limit_counters` only. |
| `0004_rate_limit_collation` | Converts `rate_limit_counters` to `utf8mb4_unicode_ci`. 0003 created it without a collation, so it got the server default, `utf8mb4_general_ci`. |
| `0005_seed_history` | Creates `seed_history` (`seeder`, `item`, `version`, `applied_at`), which records the one-time defaults `flask seed run` has handled. Downgrade drops it. |
| `0006_sign_in_lock` | Adds `users.failed_window_start` and `users.locked_until` (both `DATETIME NULL`, after `failed_attempts`) for the time-based sign-in lock. Adds only missing columns; downgrade drops only the ones that exist. |

`college_timetable_db` was adopted and upgraded on 8 Nov 2026.

`migrations/_archive/` keeps the first baseline attempt. It is not part of the revision chain, but it used the same revision id, `0001_baseline`. A database stamped by that old attempt would look adopted when it is not. Before adopting a database on another machine, run `SELECT version_num FROM alembic_version` there. If the table exists, stop and rename the new baseline id instead of adopting. On 8 Nov 2026 no database on the development server had an `alembic_version` table.

Autogenerate is turned off. `flask db migrate` and `flask db revision --autogenerate` stop with "Autogenerate is disabled: hand-written revisions only." There is no model metadata, so autogenerate would only ever propose dropping every table.

## New, empty database: install order

```text
flask db upgrade
flask seed run
flask admin create-superadmin <username> <email>
flask run            (or start the WSGI server)
```

There are no default accounts or passwords. `create-superadmin` is the only way the first account is made, and it needs the Super Admin role that `seed run` inserts.

## Deploying a new version

```text
flask db upgrade
flask seed run
```

Then start the app. The app never changes the schema itself.

## `flask seed run`

Seeders only add rows. They never update or delete one, so a role, permission, or branding value a college has changed stays as it is. Everything runs in one transaction, and the command refuses to run unless the database is at head. They run in this order:

| Seeder | Adds |
| --- | --- |
| Roles | Super Admin (level 1), Admin (2), HOD (3), Teacher (4), Student (5), each only if no role with that name exists. |
| Permissions | Every permission in `seeders/data/permissions.py` that is missing by name. Rows are matched by name, never by id. |
| Role permissions | Default grants from `seeders/data/roles.py`, each at most once (below). |
| Branding | The 22 default branding settings. |

**Role permission defaults are one-time grants.** Each (role, permission) default that has been granted, or that the database already had, gets a row in `seed_history`. A recorded default is never granted again, so a permission a college removed from a role stays removed, even with `--apply-role-defaults`.

- **Fresh install** (`role_permissions` is empty on the first run): every default is granted.
- **Existing database** (it already has role permissions on the first run): nothing is granted. Defaults it already has are recorded. The rest are printed, grouped by role, on every run until you grant them once with:

  ```text
  flask seed run --apply-role-defaults
  ```

- **Later releases:** a default added later carries a higher `since` version in `seeders/data/roles.py` (raise `DEFAULTS_VERSION` with it). It is granted once on the next `seed run` without the flag.

Super Admin passes every permission check whatever its rows say; it is mapped to every permission only so the role editor shows it complete.

### Default mapping

| Role | Default permissions |
| --- | --- |
| Super Admin | All 104 |
| Admin (79) | Add/change/delete/view for academic years, allocations, batches, departments, holidays, semesters, shifts, and subjects; add/change/view (no delete) for courses and rooms; all 14 faculty permissions; all 8 report permissions; all 6 timetable permissions; `attendance_manage`, `attendance_manage_faculty`, `attendance_view`, `attendance_view_defaulters`, `attendance_view_details`, `attendance_view_faculty`, `attendance_view_reports`; `courses_view_subjects`; `students_add_student`, `students_bulk_invite`, `students_change_student`, `students_view_student`; `users_view_user` |
| HOD (42) | All allocations, holidays, and student permissions (including `students_export_data`); view academic years, batches, courses (`courses_view_course`, `courses_view_subjects`), departments, semesters, subjects, and rooms; `attendance_view`, `attendance_view_defaulters`, `attendance_view_details`, `attendance_view_faculty`; faculty `approve_absence`, `approve_proxy`, `export_data`, `view_absence`, `view_availability`, `view_faculty`, `view_proxy`, `view_timetable`; `reports_view`, `reports_view_attendance`, `reports_view_timetable`; `shifts_change`, `shifts_view`; `timetable_export`, `timetable_view`, `timetable_view_conflicts` |
| Teacher (6) | `faculty_add_absence`, `faculty_change_availability`, `faculty_view_availability`, `faculty_view_timetable`, `students_view_student`, `timetable_view` |
| Student (1) | `timetable_view` |

Roles, user management, invitations, settings (`admin_view_settings`, `admin_change_settings`), and deleting students, courses, or rooms are left to Super Admin.

## `flask admin create-superadmin`

```text
flask admin create-superadmin <username> <email> [--force] [--password-stdin]
```

- The password comes from the first line of standard input with `--password-stdin`, otherwise from `SUPERADMIN_PASSWORD`, otherwise from a hidden prompt that asks twice. With none of these (no terminal), the command stops. It must be 8 to 128 characters and is stored as a werkzeug hash.
- It refuses when a Super Admin already exists unless `--force` is given. `--force` only adds an account; it never changes an existing one.
- It always refuses a username or email that is already used.
- It writes a `superadmin_created` entry to `user_activity_log` and `audit_logs` (username, email, role, and whether `--force` was needed; never the password or hash).
- It prints only `Created Super Admin '<username>' (id N).` Unset `SUPERADMIN_PASSWORD` afterwards if you used it.

## Startup schema check

When `REQUIRE_MIGRATED_DB` is true (the default), the app compares `alembic_version` with the newest revision in `migrations/versions/` when it starts. If the database is behind, unstamped, at a revision this code does not know, or unreachable, the app logs one error that names the problem and the fix, and `/health` returns 503 with the reason:

```json
{"status": "unavailable", "reason": "The database is at 0005_seed_history; the code expects 0006_sign_in_lock. Run `flask db upgrade`.", "maintenance_mode": false}
```

`/health` checks again on every call, so it returns 200 as soon as the database is upgraded, without a restart. Other routes are not blocked. Set `REQUIRE_MIGRATED_DB=false` to turn the check off; the test suite does that by default.

## Sign-in lock, rate limits, and account authority

**Lock.** Wrong passwords are counted per account in `users.failed_attempts`, from `users.failed_window_start`. `SIGN_IN_MAX_FAILED_ATTEMPTS` (5) failures within `SIGN_IN_FAILURE_WINDOW_MINUTES` (15) set `users.locked_until` to `SIGN_IN_LOCK_MINUTES` (15) later, by the database clock. The lock ends by itself. A successful sign-in, or an admin unlock (`POST /api/users/<id>/unlock`, `POST /admin/users/unlock/<id>`, or reactivating the account), clears the counter and the lock. Super Admin accounts get the same temporary lock. Every lock (`account_locked`) and unlock (`account_unlocked`) is in `audit_logs`. Wrong passwords during a lock are not counted. The failure count commits on its own connection; the reset commits with the sign-in. `status = 'locked'` is still honoured as a manual lock, but sign-in no longer sets it. Rows locked that way before 0006 stay locked until an admin unlocks them.

Every failed sign-in form POST answers the same `401 Sign in failed.`, whether the username is unknown, the password is wrong, or the account is locked or inactive. An unknown username runs one password hash, like a wrong password.

**Rate limits** (`security/rate_limit.py`, counters in `rate_limit_counters`). A sign-in POST is limited to `SIGN_IN_LIMIT_PER_ACCOUNT` (10) per 10 minutes per address and username, and `SIGN_IN_LIMIT_PER_ADDRESS` (300) per 10 minutes per address. Unknown usernames are counted per address only; after `SIGN_IN_UNKNOWN_LIMIT_PER_ADDRESS` (20) within the failure window, that address gets 429 for every sign-in.

The address is `request.remote_addr`. Behind a reverse proxy that is the proxy's address, so set `TRUSTED_PROXY_COUNT` to the number of proxies in front of the app; `app_factory` then wraps the app in werkzeug's `ProxyFix`, which takes the client from that many `X-Forwarded-For` hops. It is 0 by default, and then the headers are ignored. Never set it higher than the real number of proxies: a client could then choose its own address.

**Account authority** (`security/authority.py`). `roles.hierarchy_level` orders roles; smaller is more senior (Super Admin 1, Admin 2, HOD 3, Teacher 4, Student 5). An actor creates, edits, deactivates, resets, unlocks, or changes the role of only accounts whose role level is larger than their own, and can only give a role they could manage. Only a Super Admin manages a Super Admin, and the last active Super Admin cannot be deactivated or demoted. Nobody deactivates their own account. Roles: an actor edits only roles at or below their own level, cannot set a level above their own, and adds to a role only permissions they hold. Granting or revoking a user's permissions or groups needs `users_manage_permissions` (enforced, held by no role but Super Admin by default) and only permissions the actor holds. These checks read the actor's role from the database and apply to the JSON API and the legacy `/admin/users` routes.

## Flask CLI commands

When the app is loaded for a `flask` command other than `flask run`, such as `flask db upgrade`, `flask db-adopt`, `flask seed run`, `flask admin create-superadmin`, `flask routes`, or `flask shell`, it starts no background work: no quality-model retrainer, no export queue, no timetable queue, and no startup schema check. `flask run`, `python app.py`, and WSGI servers start them as usual.

`QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES=0` (or a negative value) turns the retrainer off.

## Existing database: adopt it, do not upgrade it

An existing database already has the baseline tables, so `flask db upgrade` from nothing would fail. Adopt it instead:

```text
flask db-adopt --check
flask db-adopt
```

`db-adopt` reads `information_schema` inside a read-only transaction and compares tables, columns (type, nullability, default, extra, charset, collation, comment), indexes, foreign keys (target and rules), check constraints, views (definition, security type, connection charset), triggers, routines, and events with `migrations/sql/0001_baseline.schema.json`. AUTO_INCREMENT counters, row data, view definers, and `alembic_version` are ignored.

- If anything differs, it prints every difference, exits with status 1, and changes nothing.
- If the database is already stamped, it refuses.
- `--check` compares and never stamps.
- Otherwise it stamps `0001_baseline`. That creates `alembic_version` and nothing else. Run `flask db upgrade` afterwards for `0002` and later.

When `db-adopt` reports differences, decide for each one whether the live database or the baseline is wrong. Fix it with a reviewed change on a copy first. Do not edit the baseline to make a database fit.

## Creating a revision

1. Pick the next number and a short name: `0006_add_room_floor`.
2. Generate an empty revision with that id:

   ```text
   flask db revision -m "add room floor" --rev-id 0006_add_room_floor
   ```

3. Rename the file to `0006_add_room_floor.py` if Alembic added a suffix, and check that `down_revision` is the previous head.
4. Write `upgrade()` with `op.execute(...)` or `op.add_column(...)`, and write `downgrade()` that undoes it exactly. Keep the SQL in the revision; do not import application modules, or a later code change would change what an applied revision does.
5. Give every new table an explicit `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`.
6. Prefer statements that are safe to repeat (`CREATE TABLE IF NOT EXISTS`, checking `information_schema` before `ALTER TABLE`) when a database might already have the change.
7. Run it on a copy (see below), including the downgrade, before merging.

## Rules

- **Never edit a revision once any database has been upgraded or stamped with it.** Write a new revision instead. This includes `0001_baseline.py`, `migrations/sql/0001_baseline.sql`, and the snapshot.
- **Always write `downgrade()`.** If a change cannot be undone without losing data, say so in the docstring and make `downgrade()` drop or restore what it can.
- **Test on a copy first.** Never run a new revision against `college_timetable_db` until it has passed on a `*_test` database built from a recent dump.
- **Hand-written revisions only.** Autogenerate stays off.
- **No schema changes from application code.** New tables, columns, and indexes go in a revision. The app runs no DDL at startup, on a request, or in a worker.

## Testing on a copy

The test suite reads database settings only from `.env.test` (not committed). It never reads `.env`, and it removes any `MYSQL_*` values inherited from the shell before loading `.env.test`. It refuses to run unless the database name starts with `college_timetable_ci_` and ends in `_test`, and it refuses `college_timetable_db` and `college_timetable_db_test` by name. The rule is `config.testing.test_database_problem`, used by `tests/conftest.py`, `tests/integration/live_helpers.py` (every scratch database), and `create_app` when `TESTING` is on:

```text
MYSQL_HOST=localhost
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DB=college_timetable_ci_test
```

The account needs to create and drop `*_test` databases. Then:

```text
pytest --live-db tests/integration/test_migration_baseline.py
pytest --live-db tests/integration/test_live_schema_revisions.py
pytest --live-db tests/integration/test_fresh_database.py
pytest --live-db tests/integration/test_seeders.py
pytest --live-db tests/integration/test_seeders_live_shaped.py
pytest --live-db tests/integration/test_admin_cli.py
pytest --live-db       # every live test, including the harness-based ones below
```

`test_seeders.py` seeds a scratch database at head and checks: a fresh install gets the full default mapping; seeding twice leaves identical rows; a customised role (a default removed, an extra permission added, a description and a level changed) survives re-seeding, including `--apply-role-defaults`; and a default from a later release is granted once and not again after it is removed.

`test_seeders_live_shaped.py` builds a copy from the live structure dump plus `sql/college_timetable_db.access-data.sql`, a data-only dump of `roles`, `permissions`, `role_permissions`, `permission_groups`, and `branding_settings`. It first checks that the dump has rows for those five tables only, no email address other than the `support@institution.edu` placeholder, and no password hashes. Then: the first run adds the two missing permissions and no role permissions, and lists the 21 defaults it would add (Admin 14, HOD 5, Super Admin 2); `--apply-role-defaults` grants those once; later runs change nothing; and removed permissions stay removed. To refresh the dump (read-only; it takes no table locks):

```text
C:\xampp\mysql\bin\mysqldump --single-transaction --no-create-info --skip-triggers --complete-insert ^
  --skip-comments --skip-add-locks --skip-disable-keys --skip-tz-utc --default-character-set=utf8mb4 ^
  --result-file=sql\college_timetable_db.access-data.sql college_timetable_db ^
  roles permissions role_permissions permission_groups branding_settings
```

Never add `users`, `students`, `faculty`, or any other table with personal data to that list. Check the branding values before using the file: the 8 Nov 2026 dump had a person's name in `footer_text`, which was replaced with `redacted`.

`test_admin_cli.py` follows the install order on its own scratch database: `create-superadmin` before seeding points to `seed run`; `seed run` grants every default; `create-superadmin` creates an account that logs in at `/admin/login` and writes the audit entries; a second Super Admin needs `--force`; and taken usernames or emails, short passwords, and a missing password are refused. No output contains the password or a hash.

`tests/unit/test_permission_canon.py` needs no database. It scans the code for every permission check (`has_permission`, `check_user_permission`, `permission_denied`, `allowed`, template helpers, the local wrappers that pass a name through, and `frontend/src/app/page-access.ts`). It fails if the code checks a name that is not in the canon, if a permission marked `enforced=True` is not checked anywhere, or if a permission marked `enforced=False` is not in its explicit allowlist of 24.

`test_live_schema_revisions.py` loads `sql/college_timetable_db.live-schema.sql`, a structure-only mysqldump of `college_timetable_db` taken at `0003_security_schema`, into a scratch database, then runs upgrade to head, downgrade to `0005` and back, downgrade to `0002`, upgrade again, and downgrade to `0003`, and checks that the schema comes back each time.

`test_fresh_database.py` builds its own scratch database, upgrades it to head, runs `flask seed run`, boots the real app with the export and timetable workers on, and uses the report, timetable, and branding endpoints. It also downgrades to `0003` to check that `/health` returns 503 and that startup logs the error, then upgrades again, and drops the database at the end.

### The shared test database and fixtures

Every other live test uses one database, `MYSQL_DB` from `.env.test`. The `test_database` fixture in `tests/conftest.py` drops and recreates it once per session, runs `flask db upgrade` to head and the seeders, and captures every table. After each test, the `db` fixture compares `CHECKSUM TABLE` results and refills only the tables that changed. The app commits on a new connection for each query, so one rolled-back transaction per test is not possible. A test that uses `test_database`, `db`, `app`, `client`, or `factory` is marked `live_db` automatically and skipped without `--live-db`.

- `app` is `create_app(TestingConfig)` with a temporary `UPLOAD_FOLDER`. `TestingConfig` applies the name rule above, starts no background threads, installs no log handlers, and sets `MYSQL_INIT_COMMAND` to a 2-second lock wait so a lock conflict fails fast. `default_lock_wait_app` uses the server default wait instead; sign-in, changing your own password, renaming a role you hold, and editing your own account on the legacy screen must each finish in under 2 seconds with it. `make_app(**settings)` builds an app with other settings changed (for example `TRUSTED_PROXY_COUNT`).
- `client` is a test client with the rate-limit counters cleared. `reset_rate_limits` clears them again when called.
- `factory` (`tests/factories.py`) creates a user of each role with the linked `faculty` or `students` row (same id as the user), and `academic()` creates a department, course, class, division, subject, room, teacher, and a Monday 09:00–10:00 lecture. `grant(user, name)` gives one user a permission directly.
- `tests/http_helpers.py` has `csrf_token(client)` (GET `/api/csrf-token` with the same cookie jar), `api(...)` for JSON calls with `X-CSRFToken` and `Origin`, `login(client, user)` through the real form, and `signed_in_as(client)`.

Run the whole suite:

```text
pytest                 # no database; live tests are skipped
pytest --live-db       # everything, about 5 minutes
```

`test_audit_regressions.py` holds one test per audit bug; each fails with its file reverted to HEAD `ef1008b`. Strict xfails mark bugs that are still open:

- `POST /admin/attendance/manage/update` redirects instead of answering 403 without `attendance_manage`.
- A practical cannot be limited to a lab batch: there are no lab sub-batch tables (`test_teacher_attendance.py`; see `docs/DESIGN_LAB_BATCHES.md`).

`log_activity(..., cursor=cursor)` writes the audit rows in the caller's transaction, so a change and its audit row commit or roll back together (`test_split_connection_locks.py`). Failed sign-ins are always written on their own connection. `test_sign_in_lock.py` covers the lock and rate limits, `test_account_authority.py` the hierarchy and permission grants, and `test_teacher_attendance.py` the rosters for division, whole-class, and elective lectures.

`test_migration_baseline.py` builds one scratch database with the migrations and one from `sql/college_timetable_db.sql` (structure only; rows are skipped), and checks that their `information_schema` matches, that every foreign key target exists, that `db-adopt` refuses a changed schema without writing anything, and that `0002` is idempotent and both downgrades clean up. It drops both scratch databases at the end. It never connects to `MYSQL_DB` itself or to `college_timetable_db`.

## Regenerating the baseline

Only before any database has been stamped or upgraded with it:

```text
mysqldump --no-data --single-transaction --skip-lock-tables --skip-triggers --skip-comments ^
  --result-file=sql\college_timetable_db.checks.sql college_timetable_db ^
  course_batches divisions rooms semesters subjects timetable
python -m core.schema.baseline sql/college_timetable_db.sql --checks sql/college_timetable_db.checks.sql
UPDATE_SCHEMA_SNAPSHOT=1 pytest --live-db tests/integration/test_migration_baseline.py
```

Use the MariaDB 10.4.32 `mysqldump` from XAMPP (`C:\xampp\mysql\bin`), not the MySQL client on `PATH`. phpMyAdmin's export drops CHECK constraints, together with engine, charset, collation, and comment, from any table that has one. The checks file supplies them for the six tables listed above. The builder refuses any table that still has no table options, so if a new table gets a CHECK constraint, add it to the mysqldump list.

The first command rewrites `migrations/sql/0001_baseline.sql` from a phpMyAdmin dump: it keeps every table, index, constraint, and view as dumped (engine, charset, and collation included), drops rows, AUTO_INCREMENT counters, view definers, and session noise, and makes every view `SQL SECURITY INVOKER`. The second rewrites the snapshot that `db-adopt` compares against.

The snapshot `migrations/sql/0001_baseline.schema.json` is a reviewed file. Nothing writes it unless `UPDATE_SCHEMA_SNAPSHOT=1` is set; without it the test only compares. After regenerating, read the diff before committing and check that it lists 54 tables and 10 views.

## Cleanup list

- **24 permissions no code checks** (`enforced=False` in `seeders/data/permissions.py`). They exist on installed databases and are still shown in the role editor, where granting or removing them does nothing. For each one, either add the check to the code it describes, or hide it from the role editor and the permission lists. Then change `enforced` and update the allowlist in `tests/unit/test_permission_canon.py`. Do not delete the rows.
  - Attendance: `attendance_view_reports`
  - Courses: `courses_manage_subjects`, `courses_view_subjects`
  - Faculty: `faculty_add_absence`, `faculty_approve_absence`, `faculty_approve_proxy`, `faculty_change_availability`, `faculty_delete_absence`, `faculty_export_data`, `faculty_view_absence`, `faculty_view_availability`, `faculty_view_timetable`
  - Invitations: `invitations_create`, `invitations_resend`, `invitations_revoke`, `invitations_view`
  - Roles: `roles_clone_role`
  - Rooms: `rooms_export_utilization`, `rooms_view_schedule`
  - Students: `students_export_data`
  - Timetable: `timetable_delete`, `timetable_export`, `timetable_view`, `timetable_view_conflicts`
- **Permission group names.** Live uses `Attendance` and `Reports` (capitalised), and an empty group for the two `admin_*` settings permissions; new installs get `admin` for those. Seeders never change existing rows, so align them in a reviewed data change if the role editor's grouping matters.

- **Mixed collations.** `academic_terms` and `timetable_jobs` use `utf8mb4_general_ci`; the other 52 tables use `utf8mb4_unicode_ci`. Left as is because changing a collation can break joins and comparisons. Fix it later in its own revision, tested on a copy.
- **"Does this table or column exist?" checks.** Every database at head has these objects, so the checks are now dead weight, but they are left in place for now:
  - `api/mobile/v1/sync_attendance.py`: `_table_exists` and `_column_exists` (`mobile_face_templates`, and `updated_at` on `mobile_face_templates`, `students`, `faculty`, `users`).
  - `api/mobile/v1/faculty_sync.py`: `faculty_attendance` and `faculty_attendance_logs`, twice.
  - `services/attendance_admin/_common.py` (`_table_exists`), used by `mobile.py` (`attendance_logs` twice, `faculty_attendance_logs`, `faculty_attendance`) and `faculty.py` (`faculty_attendance`, twice).
  - `data_access/registration.py`: one `information_schema.TABLES` lookup.
  - `api/web/branding.py`: `_table_exists('branding_settings')`.
  - `services/timetable/generator.py`: `SHOW COLUMNS FROM timetable` for `is_active` and `room_id`.
