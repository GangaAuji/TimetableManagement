# Tenancy: one database per college

One installation can serve several colleges. Each college is a **tenant** with its own MariaDB database, reached at its own hostname. Nothing in a tenant's database refers to another tenant; isolation is the database boundary, not a `tenant_id` column.

A tenant is the outer boundary: nothing is shared across it. A university or college group whose colleges *do* share labs, halls and visiting faculty is one tenant with several **institutions** inside it; see [DESIGN_INSTITUTIONS.md](DESIGN_INSTITUTIONS.md). Choose by the question "may these colleges ever see each other's rooms, people or timetables?" — no: separate tenants; yes: one tenant, several institutions.

## Two modes

| | Single college (default) | Tenant registry |
| --- | --- | --- |
| Setting | `MYSQL_DB=<name>`; `TENANT_REGISTRY_DB` unset | `TENANT_REGISTRY_DB=<registry database>`; `MYSQL_DB` unused |
| Request routing | Every request uses `MYSQL_DB` | The `Host` header selects the tenant; unknown host → 404, suspended → 503 |
| Migrations | `flask db upgrade` | `flask tenant upgrade SLUG` or `--all` (`flask db` is not registered) |
| Other commands | as before | need `--tenant SLUG` (`seed run`, `admin create-superadmin`, `attendance ...`, `db-adopt`) |
| Background workers | one database | loop over every active tenant |
| Files | `static/uploads/...`, `UPLOAD_FOLDER/reports` | `static/uploads/<slug>/...`, `UPLOAD_FOLDER/<slug>/reports`, learned model under `<model dir>/<slug>/` |

Existing single-college installations change nothing.

## The registry

`TENANT_REGISTRY_DB` names a database on the same server, reached with the same `MYSQL_HOST`, `MYSQL_USER` and `MYSQL_PASSWORD` as the tenant databases. It holds one table, created by `flask tenant init` (or the first `tenant create`):

```sql
tenants (id, slug, hostname, db_name, status, created_at, updated_at)
-- slug, hostname and db_name are each unique; status is provisioning | active | suspended
```

The registry is not under Alembic; `core/tenancy/registry.py::SCHEMA` is its definition. Hostname lookups are cached in the process for `TENANT_CACHE_SECONDS` (default 30), so changing a tenant's status takes effect within that time on every worker.

## Commands

```text
flask tenant init
flask tenant create <slug> --hostname <host> [--database <name>] [--admin-username U --admin-email E] [--password-stdin]
flask tenant list
flask tenant upgrade <slug> | --all
flask tenant set-status <slug> active|suspended
flask tenant forget <slug> --yes
```

`tenant create` registers the slug as `provisioning`, creates the database (`utf8mb4_unicode_ci`), runs every migration, runs the seeders, creates the Super Admin when `--admin-username`/`--admin-email` are given (password from `--password-stdin`, `SUPERADMIN_PASSWORD`, or a hidden prompt, as for `flask admin create-superadmin`), then marks the tenant `active`. It refuses a slug, hostname or database name already in use and refuses to touch a database that already exists. If a step fails the tenant stays `provisioning`: fix the cause, `flask tenant forget <slug>`, drop the database by hand if it was created, and run `create` again.

`tenant forget` removes the registry row only. **The app never drops a tenant database.**

Default database name: `college_timetable_<slug>` with hyphens turned into underscores.

## How a request finds its database

`core/tenancy/request.py` is the first `before_request` hook. It lower-cases the `Host` header, drops the port, and asks the registry. On a match it binds the tenant to the app context (`g.tenant`) and `models.db.connection_settings()` opens that tenant's database for everything that follows: rate limits, session lookup, the view, the branding context processor. `/health` and `/static/` do not need a tenant.

With a registry and no bound tenant, `connection_settings()` raises rather than falling back to `MYSQL_DB`.

### Sessions

A signed-in session carries the slug it was opened on (`session['tenant']`, written by an `after_request` hook on the sign-in response). A cookie presented on another college's hostname is cleared before anything reads it, so a session from `alpha.example` is anonymous on `beta.example` even if the two colleges share a parent domain. Set `SESSION_COOKIE_DOMAIN` only if you understand that this binding, not the cookie scope, is what keeps sessions apart.

### Mobile devices

Devices authenticate against `mobile_devices` in the tenant database they reach by hostname, so a device registered with one college cannot sync to another even with a valid signature.

## Workers and files

The close-day worker, the export queue, the timetable queue and the quality-model retrainer call `core.tenancy.tenants_to_serve(app)` and run their step once per active tenant inside `tenant_context(app, tenant)`. A tenant that fails is logged and the others continue. A tenant added while the app is running is picked up on the next pass.

Uploads saved through `utils/uploads.py` go under `static/uploads/<slug>/...`; the relative path stored in the database includes the slug, so existing URL building is unchanged. CSV exports go under `UPLOAD_FOLDER/<slug>/reports`. The learned timetable-quality model is written and read at `<dir>/<slug>/<file>` of `QUALITY_MODEL_PATH`.

Static uploads are served without authentication, as before. A file name is only reachable by someone who knows it; that is the existing exposure, now per tenant folder.

## `/health`

With a registry, `/health` checks that the registry answers and that every active tenant database is at the head revision (when `REQUIRE_MIGRATED_DB` is on). The first problem is reported as `Tenant <slug>: ...`. A healthy response includes `"tenancy": "registry"`.

## Tests

`tests/unit/test_tenancy.py` covers hostname parsing, validation, the lookup cache, session binding, path scoping, and the refusals (`bind` and `create_app` refuse a real database name in a testing app; `--tenant` without a registry is refused).

`tests/integration/test_tenancy_live.py` (needs `--live-db`) builds three scratch databases named `college_timetable_ci_tenant_{registry,alpha,beta}_test`, provisions two colleges with `flask tenant create`, and checks: migrations and seed rows in each, an account in one and not the other, routing by hostname (404 unknown, 503 suspended, `/health` without a tenant), a sign-in cookie replayed on the other hostname is anonymous and leaves no session row there, `--tenant` on commands, `tenant upgrade --all`, `run_all` of the close-day worker touching each tenant, `get_db_connection()` refusing an unbound context, and `tenant forget` keeping the database. All three databases are dropped at the end. The test-database guard (`config.testing.test_database_problem`) applies to the registry name and to every tenant `db_name` bound in a testing app.
