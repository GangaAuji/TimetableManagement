# Face attendance: data protection and anti-spoofing

How face data is stored, who may be enrolled, how a device's recognitions are
checked before they become attendance, and how a device is tied to the lecture
the teacher opened. Code: `services/face/templates.py`, `services/face/safeguards.py`,
`core/face_cli.py`, `api/mobile/v1/student_sync.py` (`_judge_event`, `/sessions/open`),
`api/web/account.py` (consent), `api/web/portal_actions.py` (open/close).
Schema: revision `0010_face_safeguards`.

## What the server holds

Recognition runs on the device. The server stores one **template** per person
(`mobile_face_templates.embedding_json`, a 192-float vector) and pushes it to
devices with `GET /mobile-sync/v1/users`. The server never receives camera
frames for recognition; it receives the device's verdict (`confidence`, and
optionally `liveness_score` and `frame_hash`).

### Encryption at rest

Templates are encrypted with Fernet (AES-128-CBC + HMAC) under
`FACE_TEMPLATE_KEY`. A stored value is either the legacy plaintext JSON list
or `enc:v1:<token>`; reads accept both, writes always encrypt when a key is
set. The key lives in the environment (`/etc/timetable/timetable.env`), never
in the database or the repository, so a database dump alone does not expose
biometric data.

```
flask face generate-key                    # print a key; put it in FACE_TEMPLATE_KEY
flask face status [--tenant SLUG]          # encrypted / plaintext / unreadable counts
flask face encrypt-templates [--tenant]    # convert plaintext rows; safe to re-run
```

Key rotation: set `FACE_TEMPLATE_KEY` to the new key and
`FACE_TEMPLATE_KEY_PREVIOUS` to the old one, run `flask face rotate-key` for
every tenant, then remove `FACE_TEMPLATE_KEY_PREVIOUS`. `/health` reports
`checks.face_key: configured|missing` (reported, not a 503: an installation
without face attendance has no key).

Without a key the app stores plaintext and `flask face status` says so. Do not
run production without one.

## Consent

`face_consents` holds one row per person per notice version: `given_at`,
`withdrawn_at`, `notice_version`, `recorded_by`, `source`. With
`FACE_CONSENT_REQUIRED=True` (the default):

- Registration (`/register/<token>`) refuses to create the account unless the
  `face_consent` box is ticked; the consent row is written in the same
  transaction as the template.
- `POST /mobile-sync/v1/users/<id>/face-template` answers 403 without an
  active consent for `FACE_CONSENT_NOTICE_VERSION`.
- `GET /mobile-sync/v1/users` omits the template (`has_face_template: false`)
  for anyone without active consent, so devices stop recognising them.
- A recognition for a person without consent is rejected (`no_consent`).
- `GET/POST/DELETE /api/account/face-consent` lets the signed-in person see,
  give and withdraw consent. Withdrawal deletes their templates at once and is
  audited (`face_consent_given`, `face_consent_withdrawn`).
- `flask face consent USER_ID give|withdraw` does the same from the shell.

Raising `FACE_CONSENT_NOTICE_VERSION` (a new privacy notice) makes everyone
re-consent: existing rows stay as history but no longer count.

## Retention

The nightly close-day job (`services/attendance_jobs.run_once`) and
`flask face purge [--days N] [--dry-run]` delete templates when:

- every consent of the person is withdrawn and the last withdrawal is older
  than `FACE_RETENTION_DAYS` (withdrawal already deletes immediately; this
  catches rows written before that behaviour or by other tools);
- the user is `inactive` (left the institution) for longer than the period;
- consent is required and the person never consented (an installation that
  turned the requirement on later).

Attendance rows and the recognition audit are kept; only the biometric
template goes.

## Passive liveness and the decision audit

A device cannot be fully trusted: a photo held up to the camera will match.
The server applies passive checks to every `Present`/`Late` event in
`POST /mobile-sync/v1/attendance/sync` and writes one row per event to
`face_recognition_audit` (`decision`, `reason`, `confidence`,
`liveness_score`, `frame_hash`, `template_age_days`, device, student,
lecture):

| Reason | Rejected when |
|---|---|
| `low_confidence` | `confidence` missing or below `FACE_MIN_CONFIDENCE` (0.70) |
| `low_liveness` | the device sent `liveness_score` and it is below `FACE_MIN_LIVENESS` (0.50) |
| `duplicate_frame` | the same `frame_hash` was already used on this device within `FACE_DUPLICATE_FRAME_SECONDS` (600) |
| `template_too_old` | the matched template was written more than `FACE_TEMPLATE_MAX_AGE_DAYS` ago (730; 0 disables) |
| `no_consent` | see above |

A rejected event is answered in `results[]` with `status: failed` and the
reason, is not written to `attendance_logs`, and the person stays unmarked.
Events with `source: "manual"` (or status `Absent`) are a teacher's manual
mark, not a recognition: they skip these checks and are audited as
`accepted/manual`.

### Device requirement

Devices running the attendance app must:

- send `confidence` with every recognition (events without it are rejected);
- send `frame_hash` (SHA-256 of the captured frame, or any stable per-frame
  id; the server hashes it) so a replayed capture is detected;
- send `liveness_score` when the app has a liveness model (blink, depth,
  texture); the threshold then applies. Devices without one are accepted on
  confidence alone, so prefer models that produce it;
- send `session_code` when `FACE_REQUIRE_SESSION_CODE` is on (next section);
- be registered in `mobile_devices` with an `owner_user_id` (the teacher
  carrying it): only that teacher's lectures can be opened from the device.

## Session codes: a device marks only the lecture the teacher opened

`lecture_sessions.session_code` / `session_code_expires_at` (revision 0007)
are now used. Opening a lecture records it as held and issues an 8-character
code valid for `FACE_SESSION_CODE_MINUTES` (90):

- web: `POST /api/portal/attendance/open/<timetable_id>` `{date}` by the
  slot's teacher or the approved proxy (`close/<timetable_id>` expires it);
- device: `POST /mobile-sync/v1/sessions/open` `{timetable_id,
  attendance_date}` by the device's owner (another `user_id` is refused).

With `FACE_REQUIRE_SESSION_CODE=True` every sync event must carry the current
code for its lecture and date; otherwise `session_code_required`,
`session_code_invalid`, `session_code_expired` or `session_closed`
(cancelled lecture) are audited and the event is rejected. With the flag off
a code is checked only when one is sent, so a college can roll devices out
before switching the requirement on.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `FACE_TEMPLATE_KEY` | unset | Fernet key for templates at rest |
| `FACE_TEMPLATE_KEY_PREVIOUS` | unset | Old key during `flask face rotate-key` |
| `FACE_CONSENT_REQUIRED` | `True` | Enrolment, distribution and recognition need consent |
| `FACE_CONSENT_NOTICE_VERSION` | `2026-01` | Notice version consent is recorded against |
| `FACE_RETENTION_DAYS` | `30` | Days before the purge removes templates after withdrawal / deactivation |
| `FACE_MIN_CONFIDENCE` | `0.70` | Minimum recognition confidence |
| `FACE_MIN_LIVENESS` | `0.50` | Minimum liveness score, when the device sends one |
| `FACE_DUPLICATE_FRAME_SECONDS` | `600` | Window for duplicate frame detection, per device |
| `FACE_TEMPLATE_MAX_AGE_DAYS` | `730` | Templates older than this are refused (0 = no limit) |
| `FACE_REQUIRE_SESSION_CODE` | `False` | Devices must send the teacher's session code |
| `FACE_SESSION_CODE_MINUTES` | `90` | Validity of an issued code |

## Tests

`tests/integration/test_face_safeguards.py` covers encryption and the CLI,
consent gates on enrolment and distribution, every rejection reason and the
audit rows, session codes from web and device, withdrawal and retention.
`tests/unit/test_face_templates.py` covers the codec without a database.
