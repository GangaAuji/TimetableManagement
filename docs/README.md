# Timetable Management documentation

These notes describe the application as it runs now: a React screen on port 5173 and a Flask API on port 5000, with MySQL behind the API.

| Document | What it covers |
| --- | --- |
| [application.md](application.md) | Who uses the system, how a request travels, and which addresses are public |
| [modules.md](modules.md) | The frontend, JSON API, services, security, and data folders |
| [system-flows.md](system-flows.md) | Sign-in, invitations, timetable generation, exports, and attendance |
| [DATABASE.md](DATABASE.md) | Supported server, Alembic revisions, adopting an existing database, and the rules for new revisions |
| [TENANCY.md](TENANCY.md) | Serving several colleges from one installation: the tenant registry, `flask tenant`, routing by hostname, per-tenant workers and files |
| [RUNBOOK.md](RUNBOOK.md) | Installing and upgrading on a VPS (gunicorn, nginx, systemd, `flask workers run`), logs and alerts, backups and the restore drill, incidents |
| [FACE_ATTENDANCE.md](FACE_ATTENDANCE.md) | Face data protection: templates encrypted at rest and key rotation, consent and retention, passive liveness checks and the recognition audit, lecture session codes for devices |
| [REPORTS.md](REPORTS.md) | Report exports in CSV, Excel and PDF; the NAAC/NBA templates (defaulter list, subject-wise attendance, monthly register, faculty workload) and their filters |
| [NOTIFICATIONS.md](NOTIFICATIONS.md) | The email outbox: triggers (defaulters, cancellations, substitutes, not-marked digest, shift requests), per-institution SMTP settings, the worker, `flask notifications` |
| [TIMETABLE.md](TIMETABLE.md) | Generating timetables: the class-by-class generator, the joint CP-SAT solver for shared faculty, electives and lab batches, manual slots, and the clash rules |
| [DESIGN_LAB_BATCHES.md](DESIGN_LAB_BATCHES.md) | Lab batches: the tables, dated memberships, the roster and clash rules, and where batches show up in attendance and generation |
| [INTEGRATIONS.md](INTEGRATIONS.md) | The public `/api/v1` with API keys, scopes and OpenAPI; signed webhooks and their outbox; staff sign-in with OpenID Connect (Google, Microsoft) |
| [DESIGN_INSTITUTIONS.md](DESIGN_INSTITUTIONS.md) | Several colleges inside one tenant: organization and institutions, memberships and the switcher, the per-request scope, sharing rooms and faculty between colleges, and what the solvers do with it |
| [DESIGN_CAPABILITIES.md](DESIGN_CAPABILITIES.md) | Optional features: the registry, the server flag + tenant switch rule, the route guard, the session payload the UI reads, and how to add a capability |

`route_inventory.md` is an older generated list of Flask URLs. Some of those paths still exist as legacy views. The browser uses the React routes and `/api` described in the files above.
