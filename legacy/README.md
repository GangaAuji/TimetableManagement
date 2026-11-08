# Legacy

These files are kept for reference only. Nothing in the application, the tests, or the Alembic setup imports or runs them. Do not run them against a database you need to keep.

They were moved here before database migrations were introduced, so that the only schema path left in the main tree is `migrations/`.

| File | Was at | Why it is here |
| --- | --- | --- |
| `college_timetable.sql` | `sql/college_timetable.sql` | Early scratch schema. It defines some tables twice, has a broken `users` insert, stores plaintext passwords, and runs `truncate rooms`. It does not match the current schema. |
| `run_full_migration.py`, `run_full_migration.bat` | `scripts/` | Drops and recreates every table in the `.env` database from `backups/college_timetable_db_2026_03_30.sql`, then reloads the data. It rewrites collations and some column definitions on the way in. Replaced by Alembic revisions. |
| `college_timetable_db_20260330_231208.sql` | `migrations/` | Full data dump that was sitting in the Alembic folder. It contains real user rows and password hashes, so it stays out of git (`*.sql` is ignored). Local copy only. |
| `hash_passwords.py` | `scripts/` | One-off script that hashed plaintext passwords in `users`. It imports `mysql` from `app`, which no longer exists, so it does not run as written. |

## Running them anyway

Paths were updated for the new location:

- `python legacy/run_full_migration.py` or `legacy\run_full_migration.bat`
- `python -m legacy.hash_passwords`

Both read the database from `.env`. Back up the database first.
