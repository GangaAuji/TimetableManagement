# Capabilities: optional features

Everything the product differentiation roadmap adds (timetable rules and versions, bookings, academic calendar, exams, 2FA, channels, parent portal, ...) is a *capability*: an optional feature the core never depends on. Sign-in, attendance, timetable generation and reports work with every capability off, and an install that never visits Settings → Capabilities behaves exactly as before.

Revision: `0015_capabilities`. Code: `core/capabilities.py`, `api/web/capabilities.py`, `frontend/src/features/settings/pages/CapabilitiesPage.tsx`.

## The rule

A capability is **on** only when both hold:

| Switch | Where | Who | Default |
|---|---|---|---|
| Server flag `FEATURE_<NAME>` | environment → `config/base.py` | operator | on; `false`/`0`/`off` hides the feature for every tenant on the server |
| Tenant switch | `capabilities` table row, `enabled` | `capabilities_change` or `admin_change_settings`, Settings → Capabilities | the registry default for that capability when no row has been saved |

Missing pieces turn things **off**: no `capabilities` table (revision 0015 not applied) → everything off; unknown name → off; a lookup error → off. This is the same shape as `NOTIFICATIONS_ENABLED` + `notification_settings.enabled` for the outbox.

Registry defaults are on only for capabilities built so that "on with nothing configured" is today's behaviour (timetable preferences with built-in weights, drafts that publish the same rows, the interactive grid, calendar feeds). Anything that needs a provider, an approval workflow or new data is off by default.

## The registry

`core.capabilities.CAPABILITIES` is the single list: `name`, `title`, `description`, `phase` (J1, K2, ...), `default`, and a `settings` schema of `key -> (kind, default)` with kinds `int`, `bool`, `str`, `choice:a|b`. The settings page renders from this schema; `clean_settings()` validates against it and rejects unknown keys or wrong kinds.

| Name | Phase | Default | Settings |
|---|---|---|---|
| `timetable_preferences` | J1 | on | `default_weight` int |
| `timetable_versions` | J2 | on | `keep_drafts` int |
| `timetable_grid` | J3 | on | |
| `bookings` | J4 | off | `requires_approval` bool |
| `workload_norms` | J5 | off | `enforce` soft/hard |
| `academic_terms`, `syllabus`, `assessments`, `exams` | K | off | |
| `two_factor` | L1 | off | `required` optional / staff / everyone |
| `security_policy` | L1 | off | rules live in `security_settings`, not in this schema |
| `privacy_tools`, `channels`, `guardians`, `attendance_policies` | L2, I | off | kept in the registry, hidden from this list until each has a flow |
| `calendar_feeds` | I3 | on | kept in the registry, hidden from this list until the feed exists |

## Using it in code

```python
from core import capabilities

# Route guard: 404 {"error": {"code": "capability_off"}} when off; None when on.
denied = capabilities.require_capability('bookings')
if denied:
    return denied

# Inside a request with a cursor already open:
if capabilities.enabled(cursor, 'timetable_preferences'):
    weights = capabilities.settings(cursor, 'timetable_preferences')   # defaults overlaid by stored values
```

Answers are cached on `flask.g` for the request; `capabilities.forget()` clears the cache (saves call it). Background workers call `enabled(cursor, name)` inside an app context; outside one the answer is off.

The capability is checked **after** the permission check and the route still needs its ordinary permission: capabilities decide whether a feature exists in this tenant, permissions decide who may use it.

## What the UI sees

`GET /api/session` carries `capabilities: {name: bool}` (effective state, every registered name present) for signed-in users. `sanitizeSession` keeps it as `Record<string, boolean>`; pages read `useCapability('bookings')` from `shared/components/data-list.tsx` and hide entries, tabs and buttons when off. Navigation entries for a capability carry its name so the sidebar hides them too. Nothing in the UI switches a feature on from a client-side value: an API behind `require_capability` answers 404 regardless.

## Settings → Capabilities

`GET /api/capabilities` (`capabilities_view` or `admin_view_settings`) returns, per capability that has a flow: `flag`, `enabled` (tenant), `stored` (a row exists), `default`, `effective`, `settings` and `schema`, plus `table_exists` and `can_change`. `PUT /api/capabilities/<name>` (`capabilities_change` or `admin_change_settings`) accepts `{"enabled": bool}` and/or `{"settings": {...}}`; settings merge key by key; the switch is kept when not given. Every save is logged as `capability_changed` with the new values. With the table missing the PUT answers 409 `capabilities_table_missing` and the page shows a notice instead of switches.

The Admin role does not hold these permissions by default (Super Admin only), the same as the other settings pages. Grant `capabilities_view` to open the page without granting branding settings.

`privacy_tools`, `channels`, `guardians`, `calendar_feeds` and `attendance_policies` stay in the registry and are left out of this list until each one has a flow. The session payload still names them.

## Adding a capability

1. Add it to `CAPABILITIES` with its phase, default and settings schema, and the matching `FEATURE_<NAME>` line in `config/base.py` and `.env.example`.
2. Put the new tables in their own revision; nothing in the core schema may reference them with a NOT NULL foreign key.
3. Guard every new route with `require_capability(name)` after its permission check; skip background work when `enabled()` is false.
4. In the UI, read `useCapability(name)`. The menu still lists the page for anyone allowed to open it. The page shows that the feature is off, and its actions stay hidden, until the switch is on.
5. Tests: a unit test of the pure logic with the capability on, and a live test proving the existing flow is unchanged with it off (the default fixture state for off-by-default capabilities).

## Capabilities wired so far

- `timetable_preferences` (J1): `services/timetable/rules.py` reads it in `effective_rules()`; off → the solvers use the legacy objective and no preferences, and `/api/timetable/rules`, `/api/faculty/<id>/preferences`, `/api/portal/preferences` answer 404. UI: Timetable → Rules, the Preferences expander on Availability, and the teacher's My availability page.
- `timetable_versions` (J2): `services/timetable/versions.py` reads it in `active()`; the job worker opens a draft only when it is on, otherwise generation replaces live rows directly. `/api/timetable/versions/*` answer 404 when off. UI: Timetable → Versions and the draft banner on Generate. Setting `keep_drafts` bounds how many drafts an institution keeps.
- `bookings` (J4, **off** by default): `services/bookings.py` reads it in `active()`; off → `room_usage_for_week()` and `booked_room()` return nothing without touching the table, so the generator, the joint solver and `check_slot` behave exactly as before, and `/api/bookings/*` answer 404. UI: Timetable → Bookings. Setting `requires_approval` (default true) makes requests wait for the room owner's `rooms_change_room` holders; false approves every clash-free booking at once.
- `academic_terms` (K1, **off** by default): `services/academic_calendar.py`. Off, or on with no terms saved, `teaching_dates()` returns every date it was given and `sweep()` / `non_teaching_slot_ids()` do nothing, so generation, close-day and attendance percentages are unchanged. On, with terms, only teaching dates are scheduled, exam/break/internship dates cancel unmarked sessions (`cancel_reason = calendar`) and close-day skips them. UI: Academics → Calendar. See [ACADEMICS.md](ACADEMICS.md).
- `syllabus` (K2, **off** by default): `services/syllabus.py`. Off, the mark screen hides the topic, mobile `topic` is ignored, `lesson_logs` stays empty, `GET /api/syllabus` and `GET /api/v1/subjects/<id>/coverage` answer 404, and the `syllabus-coverage` report is omitted. On, a teacher records one topic per lecture and coverage is delivered hours / planned hours, with behind/ahead pace when the academic calendar is configured. UI: Academics → Syllabus. See [ACADEMICS.md](ACADEMICS.md).
- `assessments` (K3, **off** by default): `services/assessment.py`. Off, Academics → Internals and the student and teacher Internals tabs are hidden, and `GET /api/assessments`, the portal routes and `GET /api/v1/subjects/<id>/internals` answer 404. On, a department records components, course and program outcomes and marks; students see a mark only after its component is locked; the `co-attainment` report is the NBA table. See [ACADEMICS.md](ACADEMICS.md).
- `exams` (K4, **off** by default): `services/exams.py` and `services/timetable/exam_solver.py`. Off, Academics → Exams and the teacher Exam duties tab are hidden, `GET /api/exams` answers 404, and the booking ledger is unchanged. On, a department solves papers, rooms and invigilators; seating plans and hall tickets download as PDF; saved sessions occupy rooms on the booking ledger while `bookings` is on. See [ACADEMICS.md](ACADEMICS.md).
- `two_factor` (L1, **off** by default): `services/second_factor.py`. Off, or on before revision `0023_second_factor` is applied, sign-in is unchanged. On, a person enrolls from Profile (current password, then the setup key, then the first 6-digit code). The page shows eight recovery codes once. The next sign-in asks for a code after the password and opens the session only when the code matches; a recovery code works once instead. `required` is `optional` (only people who enrolled), `staff` (Super Admin, Admin and HOD must enroll before the session opens) or `everyone`. An identity provider that asserts MFA (`amr` of `otp`/`mfa`, or `acr` containing `mfa`) skips the code. Turning the authenticator off needs the current password and a code, and is refused while the role is required to have one.
- `security_policy` (L1, **off** by default): `services/security_policy.py`. Off, or on before revision `0025_security_policy`, sign-in and password checks stay as they are. On, Settings → Security supplies the minimum and maximum length, complexity, expiry, idle timeout, concurrent-session limit, admin network list and sign-in notice. The saved defaults match today's rules, so turning the switch on changes nothing until a stricter row is saved. Rules apply from the next sign-in. Viewing needs `security_policy_view` or `admin_view_settings`; changing needs `security_policy_change` or `admin_change_settings`.
- `workload_norms` (J5, **off** by default): `services/workload.py` reads it in `active()`; off → `limits_for()`/`max_hours()` return `{}` and `assess()` `[]`, so neither solver sees a norm, the `workload_max` rule costs nothing, the workload report keeps its old columns, the teacher dashboard sends `workload: null` and `/api/timetable/workload-norms` answers 404. The norms live in `timetable_rules` under `_workload` (no table of their own). Setting `enforce` (default `soft`) decides whether the maximum is a cost or a constraint. UI: Timetable → Workload norms.

The first two are on by default once their revision is applied, as the roadmap set out; an operator who wants the old behaviour switches them off in Settings → Capabilities or sets `FEATURE_TIMETABLE_PREFERENCES=false` / `FEATURE_TIMETABLE_VERSIONS=false`. Bookings, workload norms, the academic calendar, syllabus coverage, internal assessment, the exam timetable, the authenticator and the security policy are opt-in.

## Tests

- `tests/unit/test_capabilities.py`: the rule with a fake cursor (missing table, missing row, defaults, flag override, cache), settings validation, the route guard, revision 0015.
- `tests/integration/test_capabilities_live.py`: session payload, listing, switching and settings through the API, audit rows, permission boundaries, a server flag set off winning over the tenant switch.
