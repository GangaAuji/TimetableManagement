# Integrations: public API, webhooks and SSO

Everything on this page is configured on **Settings → Integrations**
(`/admin/settings/integrations`, permissions `integrations_view` or
`admin_view_settings` to read and `integrations_change` or
`admin_change_settings` to change). The tables arrived with Alembic
revision `0013_integrations` (see [DATABASE.md](DATABASE.md)).

## Public API (`/api/v1`)

A read-only, versioned JSON API for other systems (ERP, LMS, data
warehouses, parent apps). It is separate from the signed-in `/api` the
React pages use and from the mobile sync API.

### Authentication

```
GET /api/v1/timetable?course_id=3&class_id=7
Authorization: Bearer ttk_<12 char prefix>_<32 char secret>
```

* Keys are created on the Integrations screen. The plaintext is shown
  **once**; only the prefix and a SHA-256 hash are stored (`api_keys`).
* A key carries the **scopes** it was created with and cannot gain one later.
  Create another key instead.

  | Scope | Covers |
  | --- | --- |
  | `catalog:read` | departments, courses, classes, divisions, academic years, rooms, subjects, subject coverage (while `syllabus` is on), locked internal marks (while `assessments` is on), lab batches |
  | `timetable:read` | active timetable slots per class |
  | `people:read` | students and faculty directory (no credentials) |
  | `attendance:read` | lecture sessions, marks, a student's attendance, defaulters |

* An optional expiry date; revoking a key is immediate.
* Per-key rate limit: `PUBLIC_API_LIMIT_PER_MINUTE` (default 600). Over the
  limit the response is `429 rate_limited`.
* `GET /api/v1/me` works with any valid key and returns its name, scopes and
  expiry.

Responses are `{"success": true, "data": ...}`; paginated endpoints accept
`limit` and `offset` and add `page: {limit, offset, count, has_more}`. Errors are
`{"success": false, "error": {"code", "message"}}` with `401 unauthorized`,
`403 forbidden` (missing scope), `405 method_not_allowed` (the API is
read-only) or `429 rate_limited`.

### OpenAPI

`GET /api/v1/openapi.json` (no key needed) is generated from the route
declarations (`api/v1/registry.py`), so it never drifts from the code.
`GET /api/v1` lists the routes and scopes in plain JSON. The Integrations
screen links to both.

### Tenancy

Keys live in the tenant's database, so a key only ever reads the college it
was created in ([TENANCY.md](TENANCY.md)).

## Webhooks

An endpoint is a URL plus a per-endpoint secret and the events it wants.
Secrets are generated (`whsec_…`), shown once, and stored encrypted with
`SETTINGS_ENCRYPTION_KEY` (`webhook_endpoints.secret_enc`); **Rotate secret**
produces a new one.

| Event | Fired when | Payload |
| --- | --- | --- |
| `attendance.marked` | a teacher or a device saved marks for a lecture session | session id and date, slot, subject, cohort, counts per status, `source` |
| `timetable.published` | a class timetable was generated, or a slot was added, retired or deleted | cohort, `reason` (`generated`, `slot_added`, `slot_retired`, `slot_deleted`), slot count, solver |
| `attendance.defaulters` | the defaulter list was produced for a cohort (the notification trigger) | threshold, month, the students below it with percentages |

`*` subscribes to every event.

### Delivery

Triggers write to the outbox (`webhook_deliveries`) **inside the
transaction** that made the change; a rolled-back change produces no
webhook. The `webhook-outbox` thread of `flask workers run` (per tenant)
claims rows with the shared job-claim columns and posts them:

```
POST <url>
Content-Type: application/json
X-Timetable-Event: attendance.marked
X-Timetable-Delivery: <uuid>
X-Timetable-Timestamp: <unix seconds>
X-Timetable-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>
```

Verify by recomputing the HMAC over `"<timestamp>.<body>"` with the
endpoint secret, comparing in constant time, and rejecting timestamps older
than five minutes (`services.webhooks.verify` is the reference). Use
`X-Timetable-Delivery` to de-duplicate: a retry re-sends the same id.

Any 2xx marks the delivery `sent`. Anything else (or a timeout,
`WEBHOOK_TIMEOUT_SECONDS`, default 10) retries with growing delay up to
`WEBHOOK_MAX_ATTEMPTS` (default 8), then the row is `failed`; the
Integrations screen shows recent deliveries with status, response code and
last error, and **Retry** requeues one.

### URL rules

`https` only in production (`WEBHOOK_ALLOW_HTTP` relaxes this for a test
rig). Hosts that resolve to private, loopback or link-local addresses are
refused unless `WEBHOOK_ALLOW_PRIVATE` is set, so an endpoint cannot be
pointed at the server's own network. Paused endpoints (`is_active = 0`) get
no new deliveries. `WEBHOOKS_ENABLED=false` stops the worker thread
entirely; triggers still queue nothing when there are no endpoints.

## Staff sign-in with SSO (OpenID Connect)

Admins, HODs and teachers can sign in with Google Workspace, Microsoft Entra
ID or any OpenID Connect provider. Students keep the password form (their
accounts have no verified staff email).

### Setup

1. Register the application with the provider. Redirect URI:
   `https://<your host>/auth/sso/callback` (`SSO_REDIRECT_BASE_URL` overrides
   the host when the app sits behind a proxy that rewrites it).
2. On Integrations → Single sign-on choose the provider, paste the client id
   and secret (stored encrypted in `sso_settings.client_secret_enc`), and
   for Microsoft or a generic provider enter the issuer URL. Google's issuer
   is fixed.
3. Optionally limit **allowed domains** (`college.edu staff.college.edu`).
   With one Google domain the sign-in page is pre-filtered to it.
4. Tick **Enable**. The sign-in pages show a "Sign in with …" button
   (`button_label`).

### Flow

`GET /auth/sso/start` begins an authorization-code flow with PKCE (S256), a
random `state` and `nonce` kept in the Flask session for at most ten
minutes. `GET /auth/sso/callback` checks the state, exchanges the code,
fetches the provider's JWKS (refreshing once on an unknown `kid`) and
verifies the `id_token`: RS256 only, issuer, audience/`azp`, `exp`, `iat`,
`nbf`, the nonce and a `sub`.

The identity (`issuer`, `sub`) is then matched:

* A row in `sso_identities` → that user.
* Otherwise, when **link by email** is on, the token's *verified* email
  (inside the allowed domains) must match exactly one non-student account
  (`users.email` or `faculty.email`); a link row is created.
* Anything else is refused with a reason on the sign-in page
  (`sso_no_account`, `sso_domain_not_allowed`, `sso_email_unverified`,
  `sso_state_mismatch`, `sso_token_invalid`, …).

Locked or inactive accounts are refused as they are for passwords. A
successful sign-in writes `login_attempts` and an `sso_login` activity, and
lands on `/admin` for admin roles or `/` for teachers. Linked accounts are
listed on the Integrations screen and can be unlinked.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `PUBLIC_API_LIMIT_PER_MINUTE` | 600 | requests per key per minute |
| `WEBHOOKS_ENABLED` | true | run the outbox thread |
| `WEBHOOK_MAX_ATTEMPTS` | 8 | retries before a delivery is `failed` |
| `WEBHOOK_POLL_SECONDS` | 10 | worker poll interval |
| `WEBHOOK_TIMEOUT_SECONDS` | 10 | HTTP timeout per post |
| `WEBHOOK_ALLOW_HTTP` | false | allow `http://` endpoints |
| `WEBHOOK_ALLOW_PRIVATE` | false | allow endpoints on private networks |
| `SSO_REDIRECT_BASE_URL` | request host | external base URL for the OIDC redirect |
| `SETTINGS_ENCRYPTION_KEY` | — | Fernet key for webhook secrets and the SSO client secret (shared with SMTP settings) |

## Tests

`tests/unit/test_integrations.py` covers key parsing, OpenAPI generation,
webhook signing and URL checks, `id_token` verification (valid plus eight
tamperings) and the migration chain. `tests/integration/test_integrations_live.py`
(`--live-db`, `*_test` databases only) exercises the public API with real
keys and scopes, a teacher mark producing a signed webhook post, retry and
backoff, slot changes publishing, and a complete SSO callback against a fake
provider.
