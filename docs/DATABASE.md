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
| `0003_security_schema` | Adds `roles.hierarchy_level` (if missing), seeds the role levels, and creates `rate_limit_counters`. |

`migrations/_archive/` keeps the first baseline attempt. It is not part of the revision chain.

Autogenerate is turned off. `flask db migrate` and `flask db revision --autogenerate` stop with "Autogenerate is disabled: hand-written revisions only." There is no model metadata, so autogenerate would only ever propose dropping every table.

## New, empty database

```text
flask db upgrade
```

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

1. Pick the next number and a short name: `0004_add_room_floor`.
2. Generate an empty revision with that id:

   ```text
   flask db revision -m "add room floor" --rev-id 0004_add_room_floor
   ```

3. Rename the file to `0004_add_room_floor.py` if Alembic added a suffix, and check that `down_revision` is the previous head.
4. Write `upgrade()` with `op.execute(...)` or `op.add_column(...)`, and write `downgrade()` that undoes it exactly.
5. Prefer statements that are safe to repeat (`CREATE TABLE IF NOT EXISTS`, checking `information_schema` before `ALTER TABLE`) when a database might already have the change.
6. Run it on a copy (see below), including the downgrade, before merging.

## Rules

- **Never edit a revision once any database has been upgraded or stamped with it.** Write a new revision instead. This includes `0001_baseline.py`, `migrations/sql/0001_baseline.sql`, and the snapshot.
- **Always write `downgrade()`.** If a change cannot be undone without losing data, say so in the docstring and make `downgrade()` drop or restore what it can.
- **Test on a copy first.** Never run a new revision against `college_timetable_db` until it has passed on a `*_test` database built from a recent dump.
- **Hand-written revisions only.** Autogenerate stays off.
- **No schema changes from request code.** New tables, columns, and indexes go in a revision. Some runtime DDL still exists (`services/db_indexes.py`, `services/schema_guard.py`, `services/timetable_jobs.py`, `services/reports_admin/_common.py`, `data_access/branding.py`); folding it into revisions is the next step.

## Testing on a copy

The test suite refuses to run unless the configured database name ends in `_test`, and it never reads `.env`. Put test credentials in `.env.test`, which is not committed:

```text
MYSQL_HOST=localhost
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DB=college_timetable_ci_test
```

The account needs to create and drop `*_test` databases. Then:

```text
pytest --live-db tests/integration/test_migration_baseline.py
```

The test builds one scratch database with the migrations and one from `sql/college_timetable_db.sql` (structure only; rows are skipped), and checks that their `information_schema` matches, that every foreign key target exists, that `db-adopt` refuses a changed schema without writing anything, and that `0002` is idempotent and both downgrades clean up. It drops both scratch databases at the end. It never connects to `MYSQL_DB` itself or to `college_timetable_db`.

## Regenerating the baseline

Only before any database has been stamped or upgraded with it:

```text
python -m core.schema.baseline sql/college_timetable_db.sql
UPDATE_SCHEMA_SNAPSHOT=1 pytest --live-db tests/integration/test_migration_baseline.py
```

The first command rewrites `migrations/sql/0001_baseline.sql` from a phpMyAdmin dump: it keeps every table, index, constraint, and view as dumped (engine, charset, and collation included), drops rows, AUTO_INCREMENT counters, view definers, and session noise, and makes every view `SQL SECURITY INVOKER`. The second rewrites the snapshot that `db-adopt` compares against.
