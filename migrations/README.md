# Migrations

Hand-written Alembic revisions live in `versions/`. The baseline SQL and its schema snapshot live in `sql/`. `_archive/` holds the first baseline attempt and is not part of the chain.

Read [docs/DATABASE.md](../docs/DATABASE.md) before adding a revision or touching an existing database. In short:

- New, empty database: `flask db upgrade`.
- Existing database: `flask db-adopt --check`, then `flask db-adopt`. Do not run `flask db stamp` or `flask db upgrade` on it by hand.
- `flask db migrate` (autogenerate) is disabled.
- Never edit a revision after a database has been upgraded or stamped with it, and always write `downgrade()`.
