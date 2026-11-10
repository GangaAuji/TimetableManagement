# Institutions: several colleges in one tenant

Status: implemented in revision `0014_institutions`. Companion to [TENANCY.md](TENANCY.md).

## The problem

A tenant (one database, one customer) was one college. A university runs
several colleges on one campus — Engineering, Architecture, Arts & Commerce —
that share a few labs and an auditorium, occasionally a visiting professor,
and want one management view, while each college keeps its own departments,
students, timetable, attendance and accreditation reports. Putting each
college in its own tenant (TENANCY.md) keeps data apart but cannot share a
room or a person. This design adds the missing level **inside** a tenant.

```
Tenant (customer, own database)            isolation boundary; who you sell to
└── Organization (exactly one row)         "Pillai University" or "XYZ College"
    └── Institution (one or more)          college / school / campus; accreditation unit
        └── Department (existing)          HOD scope
```

A standalone college is a tenant with one organization and one institution
and behaves exactly as before. Nothing in this design requires the tenant
registry; it works in single-database mode too.

## Tables (0014)

```sql
organizations (id, name, short_name, created_at, updated_at)            -- one row, id = 1
institutions  (id, organization_id, name, code UNIQUE, short_name,
               is_active, sort_order, created_at, updated_at)
institution_memberships (id, user_id, institution_id, role, department_id,
               is_primary, created_at)                                  -- UNIQUE (user_id, institution_id)
resource_shares (id, resource_type ENUM('room','faculty'), resource_id,
               institution_id, created_by, created_at)                  -- UNIQUE (resource_type, resource_id, institution_id)

departments.institution_id  int NOT NULL DEFAULT 1  FK institutions
rooms.institution_id        int NOT NULL DEFAULT 1  FK institutions
rooms.sharing               ENUM('private','listed','organization') NOT NULL DEFAULT 'private'
faculty.sharing             ENUM('private','listed','organization') NOT NULL DEFAULT 'private'
```

Upgrade backfill, in the same revision: one organization (name from
`branding_settings.site_title`, else "Institution"), one institution with
`id = 1` and the same name, every department and room pointed at it, and a
primary membership in it for every user whose role is not Student. A
database with these rows already present is left alone. Downgrade drops the
columns and tables; the data they carried (which college owns what) is lost,
which is why it is a destructive downgrade and says so.

The `DEFAULT 1` on the two columns is deliberate: existing code and tests that
insert a department or room without naming an institution keep working, and
the row lands in the first institution.

## Ownership: one anchor, derived everywhere else

An institution owns things through **departments**. The chain is:

| Object | Institution is | Column added? |
| --- | --- | --- |
| department | `departments.institution_id` | yes |
| course | its department's | no |
| subject, elective group, lab batch group | its course's | no |
| student | its course's | no |
| faculty (home) | its department's | no (`sharing` added) |
| allocation, timetable slot, lecture session, attendance | the course's | no |
| room | `rooms.institution_id` (department is optional) | yes (`sharing` added) |
| user (staff) | `institution_memberships` | table |

High-volume tables (`timetable`, `attendance`, `lecture_sessions`, logs) never
get an `institution_id`; they inherit through the course. Reports filter by
institution through `courses → departments`.

**Organization-wide by design** (one set for the whole tenant): `classes`
(FY/SY/TY), `divisions` (A/B/C), `academic_years`, `semesters`,
`shift_patterns`, `institution_holidays` (already carry `applies_to_program`),
roles and permissions, branding, notification/SSO/API settings, `rooms` with
`sharing = 'organization'`. These are vocabularies or policy, not resources;
per-institution overrides (a different semester calendar, a different
attendance threshold) are the obvious next step and are listed under *Not in
this revision*.

## Scope: what a signed-in user sees

`core/scope.py` resolves a `Scope` per request from the session:

```
Scope(institution_id, visible, organization_wide, multiple)
```

* **Super Admin**: `organization_wide = True`; `visible = ()` (everything).
  `institution_id` is the one chosen with the switcher, or `None` = all.
* **Everyone else**: `visible` = the institutions of their memberships;
  `institution_id` = the chosen one, or the primary membership.
* **`multiple`** is false while the tenant has at most one active
  institution. Then every predicate is `1=1` and `allows()` is always true:
  a one-college install runs exactly the pre-0014 queries.
* **Fallbacks that keep one-college installs unchanged**: a staff user with
  no membership row (created by an older code path) is placed in the
  institution of their `users.department_id`, else the first institution.
  Teachers and students are placed by their faculty department / student
  course.

The session stores only the chosen `institution_id` (written at sign-in by
`services.login` and `services.sso`, rewritten by `POST
/api/session/institution`). The visible list is read from
`institution_memberships` on each request that needs it and cached on
`flask.g` (`core.scope.current_scope`), so a membership change applies on
the user's next request without a new sign-in.

`Scope.clause(column)` returns a SQL fragment and parameters:

| Scope | `clause('d.institution_id')` |
| --- | --- |
| Super Admin, nothing chosen | `1=1` |
| Super Admin, chose 2 | `d.institution_id = %s` → (2,) |
| HOD in {1, 3}, chose 1 | `d.institution_id = %s` → (1,) |
| HOD in {1, 3}, "all mine" | `d.institution_id IN (%s, %s)` → (1, 3) |

Lists use it; `Scope.allows(institution_id)` applies the same rule to one
row and guards reads and writes of a single object. Reads answer "not found"
when the row is outside the scope, so the id is not confirmed; writes on a
row the caller can see but does not own (a room shared in from another
college) answer 403 `room_not_owned` / `department_not_owned` /
`faculty_not_owned`. The scope is **in addition to** permissions: a HOD with
`departments_change` can still only change departments of the institution
they are working in.

### Where the scope is applied

| Screen / API | Filter |
| --- | --- |
| Departments | `departments.institution_id` |
| Courses, subjects, batches, lab batches, allocations | via `courses.department_id → departments` |
| Students | via `students.course_id → courses → departments` |
| Faculty | home department's institution **or shared with the scope** (badge "shared from …") |
| Rooms | `rooms.institution_id` **or shared with the scope** |
| Timetable (class picker, manual slot form) | courses as above; room and faculty choices use the sharing rule below; `add_slot` refuses a room or teacher the course's institution may not use (`slot_room_not_shared`, `slot_faculty_not_shared`) |
| Dashboard counts | same joins |
| Reports datasets, accreditation, invitations, user list, public `/api/v1` | not yet scoped (see *Not in this revision*) |

Attendance marking, the teacher and student portals, mobile sync and the
notification/webhook triggers are unchanged: they act on a slot or a session
the caller already owns, and the slot's institution is the course's.

## Sharing: rooms and faculty

A shared resource is **one row** with a policy, never a copy.

| `sharing` | Visible to / usable by |
| --- | --- |
| `private` (default) | its own institution |
| `listed` | its own institution plus every institution in `resource_shares` for it |
| `organization` | every institution of the tenant |

`data_access/institutions.py::candidate_rooms_clause(scope_institution)` and
`candidate_faculty_clause(...)` produce the predicate:

```sql
r.institution_id = %s
OR r.sharing = 'organization'
OR (r.sharing = 'listed' AND EXISTS (SELECT 1 FROM resource_shares s
      WHERE s.resource_type = 'room' AND s.resource_id = r.id AND s.institution_id = %s))
```

Both timetable solvers load rooms through it for the institution of the
course being generated: `services/timetable/generator.py` per course, and
`services/timetable/joint_solver.py` per cohort (`Demand.room_ids`), so one
joint run over cohorts from two colleges gives each its own room pool and a
shared elective the intersection. Manual slot rooms, the timetable page's
room and faculty pickers (flagged `shared`) and the allocation screen's
faculty dropdown use the same predicates. A visiting professor is one
faculty row, `sharing = 'listed'` to the second college, with allocations in
both; leave, substitution and workload stay one person.

**Clash rules do not change.** `timetable` already holds every slot of the
tenant, so a shared lab booked by Architecture is busy for Engineering with no
extra ledger (`slot_room_busy`, as before).

Room bookings (revision 0018, capability `bookings`) honour the same policy:
an institution may request any room `candidate_rooms_clause` gives it, the
room's owning institution approves (`rooms_change_room` holders in the
owner's scope; `booking_not_owned` otherwise), and an approved booking is
busy for every institution's solver and manual slots, exactly like a
timetable row. See [TIMETABLE.md](TIMETABLE.md#room-bookings).

Only the owning institution (or a Super Admin) edits a resource's `sharing`
and share list. Deleting a department, room or faculty row that other
institutions use is refused with the existing "in use" responses.

## Memberships and the switcher

A user may belong to several institutions with different roles (HOD in
Engineering, visiting teacher in Architecture). `users.role` and
`users.department_id` stay the primary identity; `institution_memberships`
adds the others. `GET /api/session` returns `institution` (current) and
`institutions` (the visible list with names); the React shell shows a
switcher only when the list has more than one entry. `POST
/api/session/institution {institution_id | null}` validates against the
memberships (Super Admin may pick any or `null` = all) and rewrites the
session.

`/api/institutions` (view: `institutions_view` or `admin_view_settings`; change:
`institutions_change` or `admin_change_settings`) lists and edits the organization name and the
institutions (Settings → Institutions in the React shell); deactivating an
institution hides it from pickers but keeps its data, and the last active
one cannot be deactivated (`institution_last_active`). Department and room
forms gain an *Institution* field; room and faculty forms gain the sharing
controls; the Rooms and Faculty lists show an Institution column with
"shared in" badges, and only owned rows offer Edit. All of these appear
only when the tenant has more than one active institution.

Memberships are written by the 0014 backfill (every non-student user into
institution 1) and by faculty creation (the new teacher joins the
institution of their department). Other memberships are added with SQL for
now; the user editor does not yet have an *Institutions* field.

## Permissions

Institution and organization settings use `institutions_view` /
`institutions_change`. `admin_view_settings` / `admin_change_settings` still
open the same page. Sharing controls stay under
`rooms_change_room` / `faculty_change_faculty` of the owning institution.
The existing `department_id` scoping on `user_permissions` is unchanged; a
department always belongs to one institution, so a department-scoped grant
is implicitly institution-scoped.

## Branding

`branding_settings.institution_id` (revision `0024_branding_scope`) is null
on the organization row and set on an override. Resolution is the institution,
then the organization row, then the built-in default. The sign-in page selects
an institution with `?i=CODE` (the institution code). After sign-in, the
session's institution is used, which is the primary membership chosen at
sign-in. Settings → Branding edits one scope at a time. The same
`admin_view_settings` / `admin_change_settings` permissions apply, and an
override can be saved only for an institution in the current scope.

## Not in this revision

* Per-institution overrides of calendar, attendance policy and notification
  settings. Those tables can take an optional `institution_id` later; the
  screens do not.
* Cross-institution student enrolment (a student taking an elective owned by
  another college). `student_subject_selections` can carry it; the roster
  rule would need to look past the student's course.
* An organization dashboard beyond the Super Admin's "all institutions"
  scope on the existing pages.
* Sharing of lab batch groups or subjects.
* Scoping of reports datasets, accreditation exports, invitations, the user
  list and the public `/api/v1` by institution; a memberships editor on the
  user screen; timetable-grid labels for slots of another institution.

## Tests

`tests/unit/test_institutions.py`: `Scope` predicates for each role with and
without a chosen institution, the single-institution short-circuit, sign-in
and switcher behaviour against a fake cursor (primary membership, fallback,
Super Admin, stale or tampered session values, missing tables), per-request
caching on `g`, the sharing predicates, `replace_shares` writing only the
difference, the 0014 planner (ordering, missing-only creation, reverse
drops, backfill phases) and the joint solver's room pools.

`tests/integration/test_institutions_live.py` (`--live-db`): a
one-institution tenant with no switcher and no sharing rules; two
institutions in one `*_test` database with each admin seeing only their
own departments, courses, rooms, faculty and subjects and the other
college's rows answering not-found / not-owned; a `listed` lab and a
visiting teacher usable by the other college's manual slots while private
ones are refused; the shared lab still booked once per slot across colleges;
the owner listing and un-listing a room through the API; a teacher signing
into their department's institution; the Super Admin switching into one
college and back; the institutions API (organization, create, code rules,
deactivate, last-active guard, members). The rest of the live suite runs on
a one-institution database and is the proof that it behaves as before.
