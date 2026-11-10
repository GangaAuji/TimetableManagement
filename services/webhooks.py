"""Webhooks: an outbox of HTTP posts to the URLs a tenant subscribed.

Triggers call `emit(cursor, event, payload)` inside the transaction that
makes the change. It writes one `webhook_deliveries` row per active
endpoint subscribed to the event; nothing leaves the process until the
transaction commits, so a rolled-back change produces no webhook. The
worker (`run_pass`, hosted by `flask workers run`) claims rows with the
shared job-claim columns and posts them:

    POST <url>
    Content-Type: application/json
    X-Timetable-Event: attendance.marked
    X-Timetable-Delivery: <uuid>
    X-Timetable-Timestamp: <unix seconds>
    X-Timetable-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>.<body>")>

A 2xx marks the delivery sent; anything else retries with growing delay up
to WEBHOOK_MAX_ATTEMPTS, then the row is `failed` and can be retried from
the Integrations screen. The secret is per endpoint, encrypted at rest.

Events: attendance.marked (a teacher or device saved marks for a session),
timetable.published (a class timetable was generated or a slot added or
removed), attendance.defaulters (the defaulter list was produced for a
cohort).
"""

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import threading
import time
import uuid
from datetime import date, datetime, time as clock
from decimal import Decimal
from urllib.parse import urlparse

from flask import current_app, has_app_context

from data_access import webhooks as rows
from extensions import get_db_connection
from services.job_claims import claim_next, requeue_stale
from services.secrets_at_rest import decrypt_text, encrypt_text

EVENTS = {
    'attendance.marked': 'Marks were saved for a lecture session',
    'timetable.published': 'A class timetable was generated, or a slot was added or removed',
    'attendance.defaulters': 'A defaulter list was produced',
}
TABLE = 'webhook_deliveries'
THREAD_NAME = 'webhook-outbox'
DEFAULT_MAX_ATTEMPTS = 8
DEFAULT_TIMEOUT = 10
_guard = threading.Lock()
_started = False


class WebhookError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


# Settings and endpoints ------------------------------------------------------

def _config(name, default=None):
    if has_app_context():
        return current_app.config.get(name, default)
    return default


def parse_events(value):
    names = value if isinstance(value, (list, tuple, set, frozenset)) else str(value or '').split()
    if '*' in names:
        return ('*',)
    return tuple(sorted({name for name in names if name in EVENTS}))


def subscribed(endpoint, event):
    events = parse_events(endpoint.get('events'))
    return '*' in events or event in events


def _check_url(url):
    """https only (http allowed in debug), a host name, and no private or loopback target unless WEBHOOK_ALLOW_PRIVATE."""
    parsed = urlparse(url or '')
    schemes = ('https', 'http') if (_config('DEBUG') or _config('TESTING') or _config('WEBHOOK_ALLOW_HTTP')) else ('https',)
    if parsed.scheme not in schemes or not parsed.hostname or parsed.username or parsed.password or len(url) > 500:
        raise WebhookError('webhook_url_invalid')
    if _config('WEBHOOK_ALLOW_PRIVATE') or _config('TESTING'):
        return
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)}
    except OSError as exc:
        raise WebhookError('webhook_url_invalid') from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise WebhookError('webhook_url_private')


def list_endpoints(cursor):
    return rows.fetch_endpoints(cursor) if rows.table_exists(cursor) else []


def create_endpoint(cursor, *, name, url, events, created_by):
    """Insert an endpoint. Returns (id, plaintext secret); the secret is shown once."""
    clean_name = (name or '').strip()
    if not clean_name or len(clean_name) > 100:
        raise WebhookError('webhook_name_invalid')
    _check_url(url)
    clean_events = parse_events(events)
    if not clean_events:
        raise WebhookError('webhook_events_invalid')
    secret = 'whsec_' + secrets.token_urlsafe(32)
    endpoint_id = rows.insert_endpoint(
        cursor, name=clean_name, url=url.strip(), secret_enc=encrypt_text(secret), events=' '.join(clean_events), created_by=created_by,
    )
    return endpoint_id, secret


def update_endpoint(cursor, endpoint_id, *, name, url, events, is_active, rotate_secret=False):
    """Change an endpoint. Returns the new plaintext secret when rotated, else None."""
    if rows.fetch_endpoint(cursor, endpoint_id) is None:
        raise WebhookError('webhook_not_found')
    clean_name = (name or '').strip()
    if not clean_name or len(clean_name) > 100:
        raise WebhookError('webhook_name_invalid')
    _check_url(url)
    clean_events = parse_events(events)
    if not clean_events:
        raise WebhookError('webhook_events_invalid')
    secret = ('whsec_' + secrets.token_urlsafe(32)) if rotate_secret else None
    rows.update_endpoint(
        cursor, endpoint_id, name=clean_name, url=url.strip(), events=' '.join(clean_events), is_active=is_active,
        secret_enc=encrypt_text(secret) if secret else None,
    )
    return secret


def delete_endpoint(cursor, endpoint_id):
    if rows.delete_endpoint(cursor, endpoint_id) != 1:
        raise WebhookError('webhook_not_found')


def retry_delivery(cursor, delivery_id):
    return rows.retry_delivery(cursor, delivery_id) == 1


def status(cursor):
    if not rows.table_exists(cursor) or not rows.table_exists(cursor, TABLE):
        return {'ready': False, 'queue': {}}
    return {'ready': True, 'queue': rows.queue_counts(cursor)}


# Emitting ---------------------------------------------------------------------

def _json_default(value):
    if isinstance(value, (datetime, date, clock)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, 'total_seconds'):
        return int(value.total_seconds())
    raise TypeError(f'{type(value).__name__} is not JSON serialisable')


def emit(cursor, event, payload):
    """Queue `event` for every subscribed endpoint. Returns the delivery ids. Safe before the table exists (no-op)."""
    if event not in EVENTS:
        raise ValueError(f'unknown webhook event {event!r}')
    if not rows.table_exists(cursor):
        return []
    endpoints = [endpoint for endpoint in rows.fetch_endpoints(cursor, active_only=True) if subscribed(endpoint, event)]
    if not endpoints:
        return []
    body = json.dumps({'event': event, 'occurred_at': datetime.utcnow().replace(microsecond=0).isoformat() + 'Z', 'data': payload},
                      default=_json_default, sort_keys=True)
    return [
        rows.insert_delivery(cursor, endpoint_id=endpoint['id'], event=event, delivery_key=str(uuid.uuid4()), payload_json=body)
        for endpoint in endpoints
    ]


def safe_emit(cursor, event, payload):
    """`emit` that never raises: a webhook must not break the change that triggered it."""
    try:
        return emit(cursor, event, payload)
    except Exception:
        if has_app_context():
            current_app.logger.exception('Webhook %s could not be queued', event)
        return []


# Delivery --------------------------------------------------------------------

def sign(secret, timestamp, body):
    """`sha256=<hex>` over `<timestamp>.<body>`; receivers recompute it with the endpoint secret."""
    digest = hmac.new(secret.encode('utf-8'), f'{timestamp}.{body}'.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'sha256={digest}'


def verify(secret, timestamp, body, signature, *, tolerance_seconds=300, now=None):
    """What a receiver does. True when the signature matches and the timestamp is recent."""
    try:
        sent = int(timestamp)
    except (TypeError, ValueError):
        return False
    moment = int(now if now is not None else time.time())
    if abs(moment - sent) > tolerance_seconds:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature or '')


def post(url, body, headers, timeout):
    """The HTTP call, separated so tests and `run_tenant(sender=...)` can replace it. Returns the status code."""
    import requests

    response = requests.post(url, data=body.encode('utf-8'), headers=headers, timeout=timeout, allow_redirects=False)
    return response.status_code


def _max_attempts():
    try:
        return max(1, int(_config('WEBHOOK_MAX_ATTEMPTS', DEFAULT_MAX_ATTEMPTS)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_ATTEMPTS


def _delay(attempts):
    return min(3600, 30 * (2 ** (attempts - 1)))


def process_one(connection, delivery_id, sender=post):
    """Post one claimed delivery and record the outcome. Returns 'sent', 'retry' or 'failed'."""
    cursor = connection.cursor(dictionary=True)
    try:
        row = rows.fetch_delivery(cursor, delivery_id)
        if not row:
            return 'failed'
        if not row.get('is_active'):
            rows.mark_retry(cursor, delivery_id, attempts=int(row['attempts']), final=True, response_status=None,
                            error='endpoint is inactive', delay_seconds=0)
            connection.commit()
            return 'failed'
        timestamp = str(int(time.time()))
        body = row['payload_json']
        try:
            secret = decrypt_text(row['secret_enc'])
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'TimetableManagement-Webhooks/1.0',
                'X-Timetable-Event': row['event'],
                'X-Timetable-Delivery': row['delivery_key'],
                'X-Timetable-Timestamp': timestamp,
                'X-Timetable-Signature': sign(secret, timestamp, body),
            }
            status_code = sender(row['url'], body, headers, float(_config('WEBHOOK_TIMEOUT_SECONDS', DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT))
            error = None if 200 <= int(status_code) < 300 else f'HTTP {status_code}'
        except Exception as exc:  # network errors, bad secret key
            status_code = None
            error = f'{exc.__class__.__name__}: {exc}'
        if error is None:
            rows.mark_sent(cursor, delivery_id, int(status_code))
            rows.stamp_endpoint(cursor, row['endpoint_id'], 'sent')
            connection.commit()
            return 'sent'
        attempts = int(row['attempts']) + 1
        final = attempts >= _max_attempts()
        rows.mark_retry(cursor, delivery_id, attempts=attempts, final=final, response_status=status_code, error=error,
                        delay_seconds=_delay(attempts))
        rows.stamp_endpoint(cursor, row['endpoint_id'], 'failed' if final else 'retrying')
        connection.commit()
        if has_app_context():
            current_app.logger.warning('Webhook delivery %s not sent (attempt %s): %s', delivery_id, attempts, error)
        return 'failed' if final else 'retry'
    finally:
        cursor.close()


def _claim(connection):
    cursor = connection.cursor(dictionary=True)
    try:
        if not rows.table_exists(cursor, TABLE):
            return None
        requeue_stale(cursor, TABLE, 'progress = 0')
        claimed = claim_next(cursor, TABLE, extra_where='(available_at IS NULL OR available_at <= UTC_TIMESTAMP())')
        connection.commit()
        return claimed
    finally:
        cursor.close()


def run_tenant(app, *, drain=True, sender=post, limit=200):
    """Post queued deliveries for the current tenant database. Returns counts by outcome."""
    counts = {'sent': 0, 'retry': 0, 'failed': 0}
    if not app.config.get('WEBHOOKS_ENABLED', True):
        return counts
    connection = get_db_connection()
    try:
        for _ in range(limit):
            delivery_id = _claim(connection)
            if not delivery_id:
                break
            counts[process_one(connection, delivery_id, sender=sender)] += 1
            if not drain:
                break
    finally:
        connection.close()
    return counts


def run_pass(app, drain=True, sender=post):
    """One pass over every tenant. Returns the number of deliveries sent."""
    from core.tenancy import tenant_context, tenants_to_serve

    sent = 0
    for tenant in tenants_to_serve(app):
        key = tenant.slug if tenant is not None else None
        try:
            with tenant_context(app, tenant):
                sent += run_tenant(app, drain=drain, sender=sender)['sent']
        except Exception:
            app.logger.exception('Webhook outbox failed for tenant %s', key or 'default')
    return sent


def ensure_worker(app, force=False):
    """Start the outbox thread once per process. Never under a CLI command unless `force` (flask workers run)."""
    global _started
    if not force and (app.config.get('CLI_COMMAND') or not app.config.get('BACKGROUND_WORKERS', True)):
        return
    if not app.config.get('WEBHOOKS_ENABLED', True):
        return
    with _guard:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(app,), name=THREAD_NAME, daemon=True).start()


def _loop(app):
    interval = max(5, int(app.config.get('WEBHOOK_POLL_SECONDS', 15) or 15))
    while True:
        try:
            run_pass(app)
        except Exception:
            app.logger.exception('Webhook outbox worker failed')
        time.sleep(interval)


# Triggers ---------------------------------------------------------------------

def _clock(value):
    if value is None:
        return None
    if hasattr(value, 'total_seconds'):
        total = int(value.total_seconds())
        return f'{total // 3600:02d}:{(total % 3600) // 60:02d}'
    return value.strftime('%H:%M') if hasattr(value, 'strftime') else str(value)[:5]


def on_attendance_marked(cursor, *, session_id, timetable_id, session_date, marked_by_user_id=None, source='teacher'):
    """After marks are saved for a session: the session, its slot and the counts by status."""
    cursor.execute(
        """
        SELECT t.course_id, t.class_id, t.division_id, t.subject_id, s.name AS subject_name, t.day_of_week, t.start_time, t.end_time,
               t.lab_batch_group_id, lbg.name AS lab_batch_name,
               (SELECT COUNT(*) FROM attendance a WHERE a.session_id = %s) AS marks,
               (SELECT COUNT(*) FROM attendance a WHERE a.session_id = %s AND a.status = 'Present') AS present,
               (SELECT COUNT(*) FROM attendance a WHERE a.session_id = %s AND a.status = 'Late') AS late,
               (SELECT COUNT(*) FROM attendance a WHERE a.session_id = %s AND a.status = 'Absent') AS absent
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN lab_batch_groups lbg ON lbg.id = t.lab_batch_group_id
        WHERE t.id = %s
        """,
        (session_id, session_id, session_id, session_id, timetable_id),
    )
    slot = cursor.fetchone()
    if not slot:
        return []
    return safe_emit(cursor, 'attendance.marked', {
        'session_id': session_id, 'timetable_id': timetable_id, 'date': session_date,
        'course_id': slot['course_id'], 'class_id': slot['class_id'], 'division_id': slot.get('division_id'),
        'subject': {'id': slot['subject_id'], 'name': slot['subject_name']},
        'lab_batch': {'id': slot['lab_batch_group_id'], 'name': slot['lab_batch_name']} if slot.get('lab_batch_group_id') else None,
        'day': slot['day_of_week'], 'start_time': _clock(slot['start_time']), 'end_time': _clock(slot['end_time']),
        'marks': int(slot['marks']), 'present': int(slot['present']), 'late': int(slot['late']), 'absent': int(slot['absent']),
        'marked_by_user_id': marked_by_user_id, 'source': source,
    })


def on_timetable_published(cursor, *, course_id, class_id, division_id, reason, slot_count=None, solver=None, timetable_id=None):
    """After a class timetable changes: generated (whole class) or a single slot added/removed."""
    if slot_count is None:
        cursor.execute(
            'SELECT COUNT(*) AS n FROM timetable WHERE course_id = %s AND class_id = %s AND (division_id = %s OR (%s IS NULL AND division_id IS NULL)) '
            'AND COALESCE(is_active, 1) = 1',
            (course_id, class_id, division_id, division_id),
        )
        slot_count = int((cursor.fetchone() or {}).get('n') or 0)
    return safe_emit(cursor, 'timetable.published', {
        'course_id': course_id, 'class_id': class_id, 'division_id': division_id, 'reason': reason,
        'slot_count': slot_count, 'solver': solver, 'timetable_id': timetable_id,
    })


def on_defaulters(cursor, *, threshold, students, course_id=None, class_id=None, division_id=None, month=None):
    """After a defaulter list is produced: who is below the line, with their percentages."""
    return safe_emit(cursor, 'attendance.defaulters', {
        'threshold': threshold, 'course_id': course_id, 'class_id': class_id, 'division_id': division_id, 'month': month,
        'count': len(students), 'students': students[:500],
    })
