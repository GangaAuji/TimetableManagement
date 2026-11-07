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
| `features/reports`, `audit`, `devices`, `settings` | Reports, audit, mobile devices, branding |
| `features/teacher`, `account` | Teacher tools and the shared profile page |
| `shared` | API client, shell, tables, theme, and page spacing |

Staff links point at `/admin/...`. Teacher and student links stay at `/my-...`. `page-access.ts` is the list of which permission opens which staff page.

## JSON API

`api/web` is the blueprint mounted at `/api`. Each module registers its own routes and calls `permission_denied` or a role check before it reads data.

| Module | Work |
| --- | --- |
| `session.py`, `security.py`, `access.py` | Session, security token, request checks, shared permission denial |
| `branding.py`, `settings.py` | Public branding and the saved settings screen |
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

`services` holds the work the routes call.

| Area | Files | Work |
| --- | --- | --- |
| Sign-in | `login.py`, `registration.py`, `invitations.py` | Student, teacher, and admin sign-in, and invitation registration |
| Academic setup | `departments.py`, `courses.py`, `academic_years.py`, `semesters.py`, `subjects.py`, `batches.py`, `allocations.py` | Catalog saves |
| Timetable | `timetable/generator.py`, `timetable_jobs.py`, `timetable_quality_service.py` | Generation, the job queue, and the quality model |
| Attendance | `attendance_admin/`, `teacher_attendance.py`, `student_portal.py` | Staff attendance and the teacher or student views |
| Reports | `export_jobs.py`, `reports_admin/` | Queued CSV jobs and report datasets |
| People and access | `users.py`, `roles.py`, `user_permissions.py`, `faculty_admin.py`, `admin_students.py` | Accounts, roles, faculty, and students |
| Audit | `audit_logs.py` | Activity, sessions, and failed sign-ins |
| Database | `db_indexes.py` | Composite indexes added once at startup |
| Face | `face/face_embedding.py` | Embedding used by invitation registration |

`academic_rules` holds clash, holiday, and availability checks used while a timetable is built. `data_access` holds the SQL helpers those services call. `models/db.py` is the shared database connection used by the older request path. `security` holds permission checks, session activity, and the in-process rate limit.

## What still renders through Flask

`routes/` still contains the older admin, teacher, student, and academic views. Those views call `ui/pages.py`, which sends the browser to the React path. New browser work goes through `api/web` and `frontend/src`, not through a new HTML template.
