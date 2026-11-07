# Migrations

Alembic revisions for this application live in `versions/`. The application still reads and writes data through `models/db.py`. These revisions do not run on startup.

## Naming

- `NNNN_short_description.py`
- `NNNN` is a four-digit sequence: `0001`, `0002`, `0003`.
- The description uses lowercase words separated by underscores.
- `0001_baseline_existing_schema.py` is the current schema. Do not edit it after a database has been stamped or upgraded.
- Every revision implements both `upgrade()` and `downgrade()`.

## Existing database

The database already has these tables. Stamp it so Alembic records the baseline without creating or changing anything:

```text
flask db stamp head
```

Run that once, from the project root, with `FLASK_APP=app:create_app`.

## New database

On an empty database, create the schema from the revisions:

```text
flask db upgrade
```

Do not run `flask db upgrade` against a database that already has the tables. `0001` creates them and will stop if they exist.

## Downgrade

`flask db downgrade` drops the tables and views created by these revisions. Do not run it on a database you need to keep.
