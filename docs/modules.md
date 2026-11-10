# Modules

The running application is split by job. Screens stay in `frontend`. HTTP and permission checks stay in `api/web`. Database work stays in `services` and `data_access`.

## Frontend

`frontend/src` is the React application.

| Folder | Responsibility |
| --- | --- |
| `app` | Router, session gate, and page permissions |
| `features/auth` | Student, teacher, and admin sign-in, plus invitation registration |
| `features/home` | Role home: staff dashboard, teacher dashboard, or student dashboard |
| `features/navigation` | Sidebar groups for staff and for the teacher or student portal |
| `features/academics` | Years, semesters, subjects, batches, allocations, holidays |
| `features/departments`, `courses`, `rooms` | Setup catalogs |
| `features/students`, `faculty`, `users`, `roles` | People, accounts, roles, and permissions |
| `features/invitations` | Invitation list for staff |
| `features/timetable` | Class timetable and the generation screen |
| `features/attendance`, `shifts`, `proxy` | Teaching operations |
| `features/reports`, `audit`, `devices`, `settings` | Reports, audit, mobile devices, branding, the Institutions page |
| `features/teacher`, `account` | Teacher tools and the shared profile page |
| `shared` | API client, shell (with the institution switcher in the header), tables, theme, page spacing, `institutions.ts` and `SharingFields` for the sharing controls |

Staff links point at `/admin/...`. Teacher and student links stay at `/my-...`. `page-access.ts` is the list of which permission opens which staff page.

## JSON API

`api/web` is the blueprint mounted at `/api`. Each module registers its own routes and calls `permission_denied` or a role check before it reads data.

| Module | Work |
| --- | --- |
| `session.py`, `security.py`, `access.py` | Session (including the current institution and `POST /session/institution`), security token, request checks, shared permission denial |
| `branding.py`, `settings.py`, `institutions.py` | Public branding, the saved settings screen, the organization and its institutions |
| `dashboard.py` | Staff home counts |
| `departments.py`, `courses.py`, `rooms.py`, `catalog/` | Academic setup |
| `people/` | Students and faculty records |
| `users.py`, `user_access.py`, `roles.py`, `permissions.py` | Accounts and access control |
| `invitations.py` | Invitation preview and staff invitation actions |
| `timetable.py` | Timetable view and generation jobs |
| `attendance.py`, `shifts.py`, `proxy.py` | Attendance, shifts, and proxy |
| `teacher.py`, `student.py`, `portal_actions.py`, `account.py` | Signed-in teacher, student, and profile actions |
| `reports.py`, `audit.py`, `devices.py` | Report jobs, audit, and registered devices |
| `responses.py` | The shared `{ success, data }` and `{ success, error }` shapes |

`api/mobile/v1` is the phone sync API at `/mobile-sync/v1`. It is not part of the browser `/api` blueprint.

## Services

`services` holds the work the API modules and workers call.

| Area | Files | Work |
| --- | --- | --- |
| Sign-in | `login.py`, `registration.py`, `invitations.py`, `sso.py` | Student, teacher, and admin sign-in, invitation registration, OpenID Connect |
| Timetable | `timetable/generator.py`, `timetable/joint_solver.py`, `timetable_slots.py`, `timetable_jobs.py`, `timetable_quality_service.py`, `lab_batches.py` | Generation, manual slots, the job queue, the quality model, lab batches |
| Attendance | `attendance_calc.py`, `lecture_sessions.py`, `teacher_attendance.py`, `student_portal.py`, `attendance_admin/_common.py` | Percentages and defaulters, sessions, the teacher and student views, mobile log promotion |
| Reports | `export_jobs.py`, `reports_admin/` | Queued CSV/Excel/PDF jobs, report datasets, NAAC/NBA templates |
| Notifications and webhooks | `notifications.py`, `webhooks.py`, `job_claims.py`, `worker_process.py` | The outboxes, the claim pattern, and the worker threads |
| Integrations | `api_keys.py`, `webhooks.py`, `sso.py`, `secrets_at_rest.py` | Public API keys, webhook endpoints, SSO settings, encryption of stored secrets |
| People and access | `users.py`, `user_actions.py`, `user_permissions.py`, `faculty_admin.py`, `profile.py`, `admin_queries.py` | Accounts, bulk actions, permissions, faculty, the account page |
| Audit | `audit_logs.py` | Activity, sessions, and failed sign-ins |
| Face | `face/` | Embeddings, encrypted templates, consent, liveness safeguards |

`academic_rules` holds clash, holiday, and availability checks used while a timetable is built. `data_access` holds the SQL helpers those services call; `data_access/institutions.py` adds the institution, membership and sharing queries, and `core/scope.py` turns the session into the per-request `Scope` whose predicates the catalog, people and timetable modules apply ([DESIGN_INSTITUTIONS.md](DESIGN_INSTITUTIONS.md)). `extensions.get_db_connection` is the one way to open a connection (`models/db.py` resolves the tenant's settings behind it). `security` holds the audit writers, permission lookups, session activity, and the shared rate limit; request-level permission checks are `api.web.access.permission_denied` / `allowed`.

## One request path

Every screen is a React page talking to `/api`. The only Flask views left are on `routes/auth.py`: the sign-in and sign-out forms, invitation registration, the SSO start/callback, `/health` and the favicon. The older server-rendered admin, teacher, student and academic blueprints were removed with the services that only they used; a bookmark to one of those URLs reaches the 404 handler in `ui/errors.py`, which sends the browser to the matching React path (`ui/pages.react_path`). New browser work goes through `api/web` and `frontend/src`.
