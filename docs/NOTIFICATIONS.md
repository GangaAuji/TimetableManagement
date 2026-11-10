# Notifications

Email alerts for the events people otherwise find out about too late:
a student slipping below the attendance threshold, a cancelled lecture, a
substitute arrangement, lectures nobody marked, and shift-change requests.
Everything goes through one outbox table, so a trigger never sends mail
from inside a web request and a failed SMTP server never loses a message.

Schema: revision `0011_notifications`. Code: `services/notifications.py`,
`api/web/notifications.py`, `core/notifications_cli.py`.

## How a message travels

1. A trigger runs on the cursor of the change it belongs to (the
   cancellation, the proxy approval, the close-day pass) and inserts a
   `notifications` row with `status = 'queued'`. Trigger and change commit
   together; if the change rolls back, so does the message.
2. `dedupe_key` is unique. A trigger that fires twice (close-day catch-up,
   a double submit, an admin re-approving) queues one message, not two.
3. The outbox worker (`notification-outbox` thread inside `flask workers
   run`, or in the web process when `BACKGROUND_WORKERS` is on) claims the
   oldest queued row whose `available_at` has passed, with the same
   `locked_by`/`heartbeat_at` claim as the other queues, and sends it over
   SMTP. `sent_at` is set on success.
4. On an SMTP or network error the row goes back to `queued` with
   `attempts + 1`, `last_error`, and `available_at` pushed out by
   `NOTIFICATION_RETRY_SECONDS x attempts`. After
   `NOTIFICATION_MAX_ATTEMPTS` it becomes `failed` and stays visible on
   the settings page and in `flask notifications list`.
5. When no SMTP account is configured at all the row stays `queued` with
   `last_error` saying so and no attempt is used; configure an account
   and the worker sends the backlog.

A recipient without an email address (no `users.email`, `faculty.email` or
`students.email`) produces a `skipped` row so the trigger is still visible.

## Triggers

| Kind | When | To | Dedupe |
| --- | --- | --- | --- |
| `lecture_cancelled` | `cancel_lecture` (teacher portal, admin sessions screen) | every student in the slot's roster (cohort; elective slots only the students who chose the subject) and the slot's teacher | slot + date + recipient |
| `proxy_assigned` | a proxy is approved with a substitute, or the admin absence screen assigns one | the substitute and the absent teacher | `proxy_log.id` + recipient |
| `shift_request` | a faculty member submits a shift-change request | the HOD(s) of the faculty member's department (`users.is_hod`) | request + HOD |
| `shift_decision` | the request is approved or rejected | the faculty member | request + status |
| `booking_request` | a room booking is requested (capability `bookings`) | `rooms_change_room` holders of the room's owning institution, except the requester | booking + recipient |
| `booking_decision` | the booking is approved or rejected | whoever requested it | booking + status |
| `not_marked_digest` | after the nightly close-day, for yesterday | each HOD, one message listing their department's `not_marked` lectures | date + HOD |
| `defaulter` | after the nightly close-day | every student below `ATTENDANCE_THRESHOLD_PERCENT`, once per calendar month | student + month |
| `test` | settings page or `flask notifications test` | the address given | none |

Each trigger has a switch in `notification_settings` (the booking triggers
follow `enabled` alone); `enabled` turns the whole institution off. `NOTIFICATIONS_ENABLED=false` turns the feature off
on the server for every tenant (no thread, no rows).

## SMTP account

Mail goes through, in order of preference:

1. the institution's account from the settings page (`notification_settings`:
   host, port, user, password, from, STARTTLS, reply-to). The password is
   stored Fernet-encrypted (`services/secrets_at_rest.py`) with
   `SETTINGS_ENCRYPTION_KEY`, else `FACE_TEMPLATE_KEY`, else a key derived
   from `SECRET_KEY`. Rotating the key in use makes stored passwords
   unreadable; enter them again. The API never returns the password, only
   `has_password`.
2. the server's `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
   `SMTP_FROM`, `SMTP_STARTTLS` from the environment (the same ones the
   alert handler uses).

The settings page (Admin > Notifications, permission `notifications_view`
or `admin_view_settings` to read and `notifications_change` or
`admin_change_settings` to change) shows which one is in use
and the queue counts, and queues a test message.

## Operating it

```
flask notifications status [--tenant SLUG]     delivery route, queue counts, switches
flask notifications send [--one]               send what is queued now
flask notifications test you@example.edu       queue a test message and send it
flask notifications list [--limit N]           recent outbox rows (never the password)
flask notifications digest [--date YYYY-MM-DD] queue the not-marked digest by hand
flask notifications defaulters [--threshold N] queue this month's defaulter alerts by hand
```

`flask workers run --once` includes one outbox pass (`notifications_sent`
in its counts). `/health` reports `notifications: disabled | server-smtp |
tenant-smtp-or-none`, and the worker heartbeat lists the
`notification-outbox` thread when the feature is on.

Settings: `NOTIFICATIONS_ENABLED` (true), `NOTIFICATION_MAX_ATTEMPTS` (5),
`NOTIFICATION_RETRY_SECONDS` (300), `NOTIFICATION_POLL_SECONDS` (15),
`SETTINGS_ENCRYPTION_KEY` (unset). Times in `notifications` are UTC like the
other job tables.

## Tests

`tests/unit/test_notifications.py` covers the secrets codec, the SMTP
sender against a fake `smtplib.SMTP`, the retry bookkeeping and revision
0011. `tests/integration/test_notifications_live.py` runs every trigger on
the golden cohort, the dedupe rules, the switches, sending through a fake
sender with retries, the encrypted tenant password round trip and the
settings API. No test ever opens an SMTP connection.
