# Runbook: one Linux VPS per environment

Layout on the server: nginx → gunicorn (`timetable-web.service`, port 8000, `BACKGROUND_WORKERS=False`) → MariaDB 10.4. A second service, `timetable-workers.service`, runs `flask workers run`: the export queue, the timetable queue, the nightly close-day and the quality-model retrainer. A systemd timer runs `deploy/backup.sh` nightly. Everything lives under `/opt/timetable` (`app` = this repository, `venv`), owned by the `timetable` user.

Files: `deploy/install.sh`, `deploy/gunicorn.conf.py`, `deploy/systemd/*.service|*.timer`, `deploy/nginx/*.conf`, `deploy/backup.sh`, `deploy/restore.sh`, `deploy/requirements-prod.txt`.

## 1. First install

```bash
sudo mkdir -p /opt/timetable && sudo git clone <repo> /opt/timetable/app
sudo /opt/timetable/app/deploy/install.sh          # packages, venv, frontend build, systemd units, nginx site
sudo -u timetable cp /opt/timetable/app/.env.example /opt/timetable/app/.env
sudo -u timetable nano /opt/timetable/app/.env     # see "Settings that matter" below
```

Database and first account (run as the service user, in `/opt/timetable/app`, with `FLASK_APP=wsgi:app`):

```bash
# one college
flask db upgrade && flask seed run && flask admin create-superadmin <username> <email>
# several colleges (TENANT_REGISTRY_DB set; see docs/TENANCY.md)
flask tenant init
flask tenant create <slug> --hostname <host> --admin-username <u> --admin-email <e>
```

Certificates: `certbot certonly --webroot -w /var/www/letsencrypt -d <host>` for every hostname, then put the paths in `/etc/nginx/sites-available/timetable.conf`.

Start: `sudo systemctl restart timetable-web timetable-workers && sudo systemctl reload nginx && sudo systemctl start timetable-backup.timer`.

Check: `curl -s https://<host>/health` returns `"status": "healthy"` with `checks.database = ok`, a `checks.workers.heartbeat_age_seconds` under 60, and `checks.disk_free_mb`.

### Settings that matter

| Setting | Production value |
| --- | --- |
| `SECRET_KEY` | 64 random hex chars; changing it signs everyone out |
| `DEBUG` / `FLASK_ENV` | `False` / `production` |
| `BACKGROUND_WORKERS` | set to `False` by the web unit; leave unset in `.env` so `flask workers run` and the CLI are unaffected |
| `TRUSTED_PROXY_COUNT` | `1` (nginx) so client addresses and `https` are read from the forwarded headers |
| `SESSION_COOKIE_SECURE` | handled by HTTPS; set `WTF_CSRF_SSL_STRICT`/cookie flags per `config/base.py` if you change the scheme |
| `REQUIRE_MIGRATED_DB` | `true` (default): `/health` is 503 until every database is at head |
| `REQUIRE_WORKERS` | `true` once the workers service is running: `/health` is 503 when the heartbeat is missing or older than `WORKERS_STALE_SECONDS` (180) |
| `HEALTH_MIN_FREE_MB` | 500 (default); `/health` is 503 below it |
| `LOG_FILE` / `LOG_FORMAT` | `logs/app.log`; `json` when a log shipper reads it, `text` otherwise |
| `ALERT_WEBHOOK_URL` or `ALERT_MAIL_TO` + `SMTP_*` | where ERROR-level log records go (one per distinct message per `ALERT_QUIET_SECONDS`) |
| `JOB_STALE_SECONDS` | 900: a running export or generation whose worker stopped writing progress for this long is requeued |
| `BACKUP_DIR`, `BACKUP_KEEP_DAYS`, `BACKUP_REMOTE`, `BACKUP_REMOTE_TOOL` | read by `deploy/backup.sh` |
| `LICENSE_REQUIRED`, `LICENSE_FILE` | `false` leaves the server unchanged. `true` reads the signed file at `LICENSE_FILE` and reports it on `/health`. See §6 |
| `FACE_TEMPLATE_KEY` | from `flask face generate-key`; face templates are encrypted with it. Keep it out of the backups of the database (it lives in `.env` only). Then `flask face encrypt-templates [--tenant]` once. See [FACE_ATTENDANCE.md](FACE_ATTENDANCE.md) for consent, retention and session-code settings |
| `NOTIFICATIONS_ENABLED`, `SMTP_*`, `SETTINGS_ENCRYPTION_KEY` | the email outbox (`notification-outbox` thread in the workers service). Without `SMTP_HOST` each institution must enter its own account under Admin > Notifications; queued mail waits until one exists. `flask notifications status` shows the route and the queue. See [NOTIFICATIONS.md](NOTIFICATIONS.md) |

## 2. Upgrade to a new version

```bash
cd /opt/timetable/app && sudo -u timetable git pull
sudo deploy/install.sh                                   # dependencies and frontend build; idempotent
sudo systemctl stop timetable-workers                    # nothing claims jobs while the schema changes
sudo -u timetable deploy/backup.sh                       # a dump before any schema change
# one college:
flask db upgrade && flask seed run
# several colleges:
flask tenant upgrade --all && for s in $(flask tenant list | cut -f1); do flask seed run --tenant $s; done
sudo systemctl restart timetable-web timetable-workers
curl -s https://<host>/health
```

If `db upgrade` stops at `0008_attendance_views` with "N attendance row(s) have no session_id": run `flask attendance backfill-sessions [--tenant SLUG]` (first with `--dry-run`), resolve any marks it lists as being on a cancelled lecture, then run the upgrade again. Details in [DATABASE.md](DATABASE.md).

Rollback: `flask db downgrade <previous revision>` (or `deploy/restore.sh` with the pre-upgrade dump, see §4), `git checkout <previous tag>`, `deploy/install.sh`, restart. Revisions are written so a downgrade removes only what the upgrade added.

## 3. Day to day

- **Logs**: application errors in `logs/app.log` (rotated at 10 MB × 3). Debug traces and ordinary request lines are not written there. gunicorn access/error and the workers' stdout are in the journal: `journalctl -u timetable-web -u timetable-workers -f`. Every line carries `[request_id tenant]`; nginx sends its `$request_id` as `X-Request-ID`, the app echoes it in the response and the access log prints it, so one id follows a request through all three.
- **Workers**: `flask workers status` prints the heartbeat and exits 1 when it is stale or a thread is missing. `systemctl restart timetable-workers` is safe at any time: running jobs are requeued after `JOB_STALE_SECONDS` by the next pass. Two worker services on two hosts are also safe; claims carry `locked_by`.
- **One-off runs**: `flask workers run --once` drains both queues, closes the last 7 days and retrains once, then exits; `flask attendance close-day --date ...` for a specific day.
- **Suspend a college**: `flask tenant set-status <slug> suspended` (requests get 503 within `TENANT_CACHE_SECONDS`); `active` to reopen.
- **Maintenance page**: `MAINTENANCE_MODE=True` in `.env` and restart the web service. Students, teachers, and visitors see the maintenance page. Its heading and message are the Maintenance fields under Settings. The admin panel stays open for Admin, Super Admin, and HOD, including `/admin/login`.
- **Disk**: `/health` shows `disk_free_mb`; exports live under `uploads/<slug>/reports` and may be deleted when old, the rows in `processed_reports` then point at missing files (the UI reports "file missing").

## 4. Backups and the restore drill

`deploy/backup.sh` (nightly at 02:30 through `timetable-backup.timer`, or by hand) writes `BACKUP_DIR/<UTC stamp>/`: one `<database>.sql.gz` per database (the registry and every tenant, or `MYSQL_DB`), `files.tar.gz` with `static/uploads` and `UPLOAD_FOLDER`, and `SHA256SUMS`. `LATEST` names the newest stamp. Folders older than `BACKUP_KEEP_DAYS` are removed. With `BACKUP_REMOTE` set the folder is copied off the box with rclone (default) or rsync; keep at least the last 7 nightly copies off-box.

Restore one database into a **new** name and point a tenant at it (or swap names), rather than overwriting:

```bash
set -a; source /opt/timetable/app/.env; set +a
deploy/restore.sh /var/backups/timetable/<stamp>/<database>.sql.gz <database>_restored
# check it: flask db-adopt is not needed; the dump carries alembic_version. Compare counts, then:
flask tenant set-status <slug> suspended   # several colleges
# swap: RENAME is not available across databases in MariaDB; either change the tenant's db_name in the
# registry (UPDATE tenants SET db_name = '<database>_restored' WHERE slug = '<slug>') or restore with --replace
# after stopping both services.
```

Files: `tar -xzf files.tar.gz -C /opt/timetable/app/static` for `uploads/`, and the `UPLOAD_FOLDER` part into its parent.

**Drill** (do it after the first install and after every MariaDB upgrade): `tests/integration/test_backup_restore_drill.py` performs the same dump → restore → compare on the test database and is part of the live suite in CI. On the server, run `deploy/restore.sh` with last night's dump into `<database>_drill`, check `SELECT COUNT(*)` on `users`, `attendance`, `lecture_sessions` against production, then `DROP DATABASE <database>_drill`. Record the date in your change log.

## 5. Incidents

| Symptom | Where to look | Action |
| --- | --- | --- |
| `/health` 503 `database: The database is at ...` | a migration did not run | `flask db upgrade` / `flask tenant upgrade --all` |
| `/health` 503 `license:` | `LICENSE_REQUIRED=true` and the file is missing, altered, or expired | install a current license at `LICENSE_FILE`, or set the flag false on a lab server |
| `/health` 503 `workers: No worker heartbeat` | `systemctl status timetable-workers`, journal | restart the service; check `.env` is readable by `timetable` |
| `/health` 503 `disk:` | `df -h`, `du -sh uploads static/uploads /var/backups/timetable` | remove old exports or backups; lower `BACKUP_KEEP_DAYS` |
| Export or generation stuck at "running" | `processed_reports` / `timetable_jobs` rows with old `heartbeat_at` | wait `JOB_STALE_SECONDS` or restart the workers; the row is requeued |
| 404 "No college is served at this address" | `flask tenant list`; nginx `server_name` | add the hostname to the registry and certificate |
| Sign-in loops or "Session expired" | `SECRET_KEY` changed, or `TRUSTED_PROXY_COUNT` wrong so cookies are marked insecure | fix `.env`, restart web |
| Alerts flooding | `ALERT_QUIET_SECONDS` | raise it; the handler already sends one alert per distinct message per period |

Secrets rotation: change `SECRET_KEY` (signs everyone out), `MYSQL_PASSWORD` (also in MariaDB: `ALTER USER`), `MOBILE_SYNC_API_KEY` (devices must re-register), then restart both services. For `FACE_TEMPLATE_KEY`: set the new key, put the old one in `FACE_TEMPLATE_KEY_PREVIOUS`, restart, run `flask face rotate-key` for every tenant, then remove `FACE_TEMPLATE_KEY_PREVIOUS` and restart again.

## 6. Packaging

`deploy/upgrade.sh` is the upgrade in §2 as one command. It backs up first, stops the workers, runs `install.sh`, migrates, restarts, and requires `/health` to be healthy. The backup stamp it prints is the one to give `deploy/restore.sh` if the schema change has to be undone.

`deploy/setup.sh` is the first boot on Debian or Ubuntu. It installs MariaDB when the server does not already have it, writes `.env` from prompts, optionally installs a license file, then runs `install.sh`, the migration, the seed, and the first Super Admin. With a license file, `LICENSE_REQUIRED` is true. Without one, the flag stays false and the server behaves as it does today.

`deploy/support-bundle.sh` writes a zip for a support request: the redacted report from `flask support bundle`, disk and service state, the backup stamp and checksum file names, and the last journal lines. It does not include database dumps, uploads, or secret values.

The license is a signed JSON file (`flask license inspect`, `flask license issue --private-key ... --out license.json`). The private key stays off the server; `deploy/keys/` is not part of the application. `/health` reports `checks.license` as `not required` until `LICENSE_REQUIRED=true`. Then a missing or expired file makes `/health` return 503, the admin shell shows the reason, and adding a student or an institution is refused. Existing accounts can still sign in. One grace day follows the expiry date. `max_students` is counted in the college database. `max_institutions` limits institution rows there, and limits `flask tenant create` to that many colleges.

Docker uses the same split as the units: `deploy/docker-compose.yml` runs MariaDB 10.4, gunicorn (`BACKGROUND_WORKERS=False`), `flask workers run`, and nginx serving the built React app. Copy `deploy/docker.env.example` to `deploy/docker.env`. Put the license at `deploy/license/license.json`. The web container migrates only when `TIMETABLE_AUTO_UPGRADE=1` on that first boot. Later releases use `TIMETABLE_RUNTIME=docker deploy/upgrade.sh`.

