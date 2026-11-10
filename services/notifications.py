"""Notifications outbox (docs/NOTIFICATIONS.md).

Triggers call `enqueue` on the cursor of the change they belong to, so the
message is queued in the same transaction and never without the change.
The worker (`run_pass`, hosted by `flask workers run` or the in-process
thread) claims rows with the shared job-claim columns and sends them over
SMTP: the tenant's account from notification_settings when one is set,
otherwise the SMTP_* environment of the server. A failed send is retried
after NOTIFICATION_RETRY_SECONDS up to NOTIFICATION_MAX_ATTEMPTS times.

Triggers:
  on_lecture_cancelled   services.lecture_sessions.cancel_lecture
  on_proxy_assigned      proxy approval / admin assignment
  on_shift_request       faculty submits a shift-change request (to the HOD)
  on_shift_decision      admin decides it (to the faculty member)
  after_close_day        nightly: defaulter alerts (once per student per month)
                         and the not-marked digest to each HOD
"""

import json
import smtplib
import threading
import time
from datetime import date, datetime, timedelta
from email.message import EmailMessage

from flask import current_app, has_app_context

from extensions import get_db_connection
from services.job_claims import WORKER_ID, claim_next, requeue_stale
from services.secrets_at_rest import decrypt_text, encrypt_text

THREAD_NAME = 'notification-outbox'
TABLE = 'notifications'
KINDS = (
    'defaulter', 'lecture_cancelled', 'proxy_assigned', 'not_marked_digest', 'shift_request', 'shift_decision',
    'booking_request', 'booking_decision', 'sign_in', 'test',
)
SWITCHES = ('defaulter_alerts', 'cancellation_alerts', 'proxy_alerts', 'not_marked_digest', 'shift_alerts')
SETTING_FIELDS = ('enabled', 'smtp_host', 'smtp_port', 'smtp_user', 'smtp_from', 'smtp_starttls', 'reply_to', *SWITCHES)
DEFAULT_SETTINGS = {
    'enabled': True, 'smtp_host': None, 'smtp_port': None, 'smtp_user': None, 'smtp_from': None,
    'smtp_starttls': True, 'reply_to': None,
    'defaulter_alerts': True, 'cancellation_alerts': True, 'proxy_alerts': True, 'not_marked_digest': True, 'shift_alerts': True,
}
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_SECONDS = 300

_guard = threading.Lock()
_started = False


class NotificationsOff(Exception):
    """Raised by `send` when nothing can deliver mail; the row stays queued."""


# Settings -------------------------------------------------------------------

def _config(name, default=None):
    return current_app.config.get(name, default) if has_app_context() else default


def table_exists(cursor, name=TABLE):
    cursor.execute(
        'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s', (name,),
    )
    return cursor.fetchone() is not None


def load_settings(cursor):
    """The tenant's row (id = 1) merged over the defaults. The password is never returned; `has_password` says if one is stored."""
    settings = dict(DEFAULT_SETTINGS)
    settings['has_password'] = False
    if not table_exists(cursor, 'notification_settings'):
        return settings
    cursor.execute(
        'SELECT enabled, smtp_host, smtp_port, smtp_user, smtp_password_enc, smtp_from, smtp_starttls, reply_to, '
        'defaulter_alerts, cancellation_alerts, proxy_alerts, not_marked_digest, shift_alerts, updated_at '
        'FROM notification_settings WHERE id = 1'
    )
    row = cursor.fetchone()
    if not row:
        return settings
    for key in SETTING_FIELDS:
        value = row.get(key)
        settings[key] = bool(value) if key in ('enabled', 'smtp_starttls', *SWITCHES) else value
    settings['has_password'] = bool(row.get('smtp_password_enc'))
    settings['updated_at'] = row.get('updated_at')
    return settings


def save_settings(cursor, values, user_id, *, password=None, clear_password=False):
    """Upsert the single settings row. `password=None` keeps the stored one; `clear_password` removes it."""
    current = load_settings(cursor)
    merged = {key: values.get(key, current.get(key)) for key in SETTING_FIELDS}
    cursor.execute('SELECT smtp_password_enc FROM notification_settings WHERE id = 1')
    row = cursor.fetchone()
    stored = row.get('smtp_password_enc') if row else None
    if clear_password:
        stored = None
    elif password:
        stored = encrypt_text(password)
    cursor.execute(
        """
        INSERT INTO notification_settings (
            id, enabled, smtp_host, smtp_port, smtp_user, smtp_password_enc, smtp_from, smtp_starttls, reply_to,
            defaulter_alerts, cancellation_alerts, proxy_alerts, not_marked_digest, shift_alerts, updated_by
        ) VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            enabled = VALUES(enabled), smtp_host = VALUES(smtp_host), smtp_port = VALUES(smtp_port),
            smtp_user = VALUES(smtp_user), smtp_password_enc = VALUES(smtp_password_enc), smtp_from = VALUES(smtp_from),
            smtp_starttls = VALUES(smtp_starttls), reply_to = VALUES(reply_to),
            defaulter_alerts = VALUES(defaulter_alerts), cancellation_alerts = VALUES(cancellation_alerts),
            proxy_alerts = VALUES(proxy_alerts), not_marked_digest = VALUES(not_marked_digest),
            shift_alerts = VALUES(shift_alerts), updated_by = VALUES(updated_by)
        """,
        (
            int(bool(merged['enabled'])), merged['smtp_host'] or None, merged['smtp_port'] or None, merged['smtp_user'] or None,
            stored, merged['smtp_from'] or None, int(bool(merged['smtp_starttls'])), merged['reply_to'] or None,
            *(int(bool(merged[key])) for key in SWITCHES), user_id,
        ),
    )
    return load_settings(cursor)


def smtp_account(cursor=None, settings=None):
    """Where mail goes out: the tenant's SMTP account when a host is set, else the server's SMTP_*; None when neither."""
    if settings is None and cursor is not None:
        settings = load_settings(cursor)
    settings = settings or {}
    if settings.get('smtp_host'):
        password = None
        if cursor is not None and settings.get('has_password'):
            cursor.execute('SELECT smtp_password_enc FROM notification_settings WHERE id = 1')
            row = cursor.fetchone()
            password = decrypt_text(row.get('smtp_password_enc')) if row else None
        return {
            'host': settings['smtp_host'], 'port': int(settings.get('smtp_port') or 587), 'user': settings.get('smtp_user'),
            'password': password, 'from': settings.get('smtp_from') or settings.get('smtp_user'),
            'starttls': bool(settings.get('smtp_starttls', True)), 'reply_to': settings.get('reply_to'), 'source': 'tenant',
        }
    host = _config('SMTP_HOST')
    if not host:
        return None
    return {
        'host': host, 'port': int(_config('SMTP_PORT', 587) or 587), 'user': _config('SMTP_USER'),
        'password': _config('SMTP_PASSWORD'), 'from': _config('SMTP_FROM') or _config('SMTP_USER'),
        'starttls': bool(_config('SMTP_STARTTLS', True)), 'reply_to': settings.get('reply_to'), 'source': 'server',
    }


def status(cursor):
    """What /health and the settings page show: enabled, where mail goes, queue depth."""
    settings = load_settings(cursor)
    account = smtp_account(cursor, settings)
    counts = {}
    if table_exists(cursor):
        cursor.execute(f'SELECT status, COUNT(*) AS n FROM `{TABLE}` GROUP BY status')
        counts = {row['status']: int(row['n']) for row in cursor.fetchall()}
    return {
        'enabled': bool(_config('NOTIFICATIONS_ENABLED', True)) and settings['enabled'],
        'delivery': account['source'] if account else 'none',
        'smtp_host': account['host'] if account else None,
        'queued': counts.get('queued', 0), 'failed': counts.get('failed', 0), 'sent': counts.get('sent', 0),
    }


# Enqueue --------------------------------------------------------------------

def _switch_on(cursor, switch):
    if not _config('NOTIFICATIONS_ENABLED', True):
        return False
    if not table_exists(cursor):
        return False
    settings = load_settings(cursor)
    return bool(settings['enabled'] and (switch is None or settings.get(switch, True)))


def _email_of_user(cursor, user_id):
    cursor.execute(
        """
        SELECT COALESCE(NULLIF(u.email, ''), NULLIF(f.email, ''), NULLIF(s.email, '')) AS email
        FROM users u
        LEFT JOIN faculty f ON f.user_id = u.id
        LEFT JOIN students s ON s.user_id = u.id
        WHERE u.id = %s
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    return (row or {}).get('email')


def enqueue(cursor, *, kind, subject, body, recipient_user_id=None, recipient_email=None, payload=None, dedupe_key=None):
    """Queue one message. Returns the new id, or None when the dedupe key already exists.

    Without an address for the recipient the row is stored as `skipped`
    (so the trigger is visible in the outbox) and None is returned.
    """
    if kind not in KINDS:
        raise ValueError('kind')
    email = (recipient_email or '').strip() or (_email_of_user(cursor, recipient_user_id) if recipient_user_id else None)
    state = 'queued' if email else 'skipped'
    cursor.execute(
        f"""
        INSERT IGNORE INTO `{TABLE}` (kind, channel, recipient_user_id, recipient_email, subject, body, payload_json, dedupe_key,
                                      status, last_error, available_at)
        VALUES (%s, 'email', %s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())
        """,
        (
            kind, recipient_user_id, email, subject[:200], body, json.dumps(payload) if payload is not None else None,
            dedupe_key[:190] if dedupe_key else None, state, None if email else 'recipient has no email address',
        ),
    )
    if cursor.rowcount != 1:
        return None
    return cursor.lastrowid if email else None


def recent(cursor, *, limit=100, user_id=None):
    clauses, params = [], []
    if user_id is not None:
        clauses.append('recipient_user_id = %s')
        params.append(user_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    cursor.execute(
        f'SELECT id, kind, recipient_user_id, recipient_email, subject, status, attempts, last_error, created_at, sent_at '
        f'FROM `{TABLE}` {where} ORDER BY id DESC LIMIT %s',
        (*params, int(limit)),
    )
    return cursor.fetchall()


# Sending --------------------------------------------------------------------

def send(account, *, to, subject, body, reply_to=None):
    """Deliver one message over SMTP. Raises on failure; raises NotificationsOff when there is no account."""
    if not account:
        raise NotificationsOff('No SMTP account: set SMTP_HOST or the tenant notification settings.')
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = account.get('from') or account.get('user') or 'timetable@localhost'
    message['To'] = to
    if reply_to or account.get('reply_to'):
        message['Reply-To'] = reply_to or account['reply_to']
    message.set_content(body)
    with smtplib.SMTP(account['host'], int(account.get('port') or 587), timeout=20) as client:
        if account.get('starttls', True):
            client.starttls()
        if account.get('user'):
            client.login(account['user'], account.get('password') or '')
        client.send_message(message)


def _max_attempts():
    try:
        return max(1, int(_config('NOTIFICATION_MAX_ATTEMPTS', DEFAULT_MAX_ATTEMPTS)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_ATTEMPTS


def _retry_seconds():
    try:
        return max(5, int(_config('NOTIFICATION_RETRY_SECONDS', DEFAULT_RETRY_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_SECONDS


def process_one(connection, notification_id, sender=send):
    """Send one claimed row and record the outcome. Returns 'sent', 'retry', 'failed' or 'deferred'."""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(f'SELECT * FROM `{TABLE}` WHERE id = %s', (notification_id,))
        row = cursor.fetchone()
        if not row:
            return 'failed'
        account = smtp_account(cursor)
        try:
            sender(account, to=row['recipient_email'], subject=row['subject'], body=row['body'])
        except NotificationsOff as exc:
            # Nothing can send right now: leave it queued without burning an attempt.
            cursor.execute(
                f"UPDATE `{TABLE}` SET status = 'queued', locked_by = NULL, heartbeat_at = NULL, progress = 0, last_error = %s, "
                f"available_at = UTC_TIMESTAMP() + INTERVAL %s SECOND WHERE id = %s",
                (str(exc)[:500], _retry_seconds(), notification_id),
            )
            connection.commit()
            return 'deferred'
        except Exception as exc:  # SMTP and network errors
            attempts = int(row['attempts']) + 1
            final = attempts >= _max_attempts()
            cursor.execute(
                f"UPDATE `{TABLE}` SET status = %s, attempts = %s, last_error = %s, locked_by = NULL, heartbeat_at = NULL, "
                f"progress = 0, available_at = UTC_TIMESTAMP() + INTERVAL %s SECOND WHERE id = %s",
                ('failed' if final else 'queued', attempts, f'{exc.__class__.__name__}: {exc}'[:500],
                 _retry_seconds() * attempts, notification_id),
            )
            connection.commit()
            if has_app_context():
                current_app.logger.warning('Notification %s not sent (attempt %s): %s', notification_id, attempts, exc)
            return 'failed' if final else 'retry'
        cursor.execute(
            f"UPDATE `{TABLE}` SET status = 'sent', attempts = attempts + 1, progress = 100, sent_at = UTC_TIMESTAMP(), "
            f"last_error = NULL WHERE id = %s",
            (notification_id,),
        )
        connection.commit()
        return 'sent'
    finally:
        cursor.close()


def _claim(connection):
    cursor = connection.cursor(dictionary=True)
    try:
        if not table_exists(cursor):
            return None
        requeue_stale(cursor, TABLE, 'progress = 0')
        # available_at is UTC like heartbeat_at (services/job_claims.py), never the session time zone.
        claimed = claim_next(cursor, TABLE, extra_where='(available_at IS NULL OR available_at <= UTC_TIMESTAMP())')
        connection.commit()
        return claimed
    finally:
        cursor.close()


def run_tenant(app, *, drain=True, sender=send, limit=200):
    """Send queued mail for the current tenant database. Returns counts by outcome."""
    counts = {'sent': 0, 'retry': 0, 'failed': 0, 'deferred': 0}
    if not app.config.get('NOTIFICATIONS_ENABLED', True):
        return counts
    connection = get_db_connection()
    try:
        for _ in range(limit):
            notification_id = _claim(connection)
            if not notification_id:
                break
            outcome = process_one(connection, notification_id, sender=sender)
            counts[outcome] += 1
            if outcome == 'deferred' or not drain:
                break
    finally:
        connection.close()
    return counts


def run_pass(app, drain=True, sender=send):
    """One pass over every tenant. Returns the number of messages sent."""
    from core.tenancy import tenant_context, tenants_to_serve

    sent = 0
    for tenant in tenants_to_serve(app):
        key = tenant.slug if tenant is not None else None
        try:
            with tenant_context(app, tenant):
                sent += run_tenant(app, drain=drain, sender=sender)['sent']
        except Exception:
            app.logger.exception('Notification outbox failed for tenant %s', key or 'default')
    return sent


def ensure_worker(app, force=False):
    """Start the outbox thread once per process. Never under a CLI command unless `force` (flask workers run)."""
    global _started
    if not force and (app.config.get('CLI_COMMAND') or not app.config.get('BACKGROUND_WORKERS', True)):
        return
    if not app.config.get('NOTIFICATIONS_ENABLED', True):
        return
    with _guard:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(app,), name=THREAD_NAME, daemon=True).start()


def _loop(app):
    interval = max(5, int(app.config.get('NOTIFICATION_POLL_SECONDS', 15) or 15))
    while True:
        try:
            run_pass(app)
        except Exception:
            app.logger.exception('Notification outbox worker failed')
        time.sleep(interval)


# Triggers -------------------------------------------------------------------

def _institution():
    return _config('INSTITUTION_SHORT_NAME') or _config('INSTITUTION_NAME') or 'Timetable'


def _slot(cursor, timetable_id):
    cursor.execute(
        """
        SELECT t.id, t.course_id, t.class_id, t.division_id, t.lab_batch_group_id, t.faculty_id, t.day_of_week,
               t.start_time, t.end_time,
               sub.id AS subject_id, sub.name AS subject_name, COALESCE(sub.is_elective, 0) AS is_elective,
               f.name AS faculty_name, f.department_id,
               c.name AS course_name, cl.name AS class_name, d.name AS division_name, lbg.name AS lab_batch_name
        FROM timetable t
        JOIN subjects sub ON sub.id = t.subject_id
        LEFT JOIN faculty f ON f.user_id = t.faculty_id
        LEFT JOIN courses c ON c.id = t.course_id
        LEFT JOIN classes cl ON cl.id = t.class_id
        LEFT JOIN divisions d ON d.id = t.division_id
        LEFT JOIN lab_batch_groups lbg ON lbg.id = t.lab_batch_group_id
        WHERE t.id = %s
        """,
        (timetable_id,),
    )
    return cursor.fetchone()


def _roster_users(cursor, slot):
    """(user_id, email, name) of the students a slot's lecture is for."""
    clauses, params = ['COALESCE(s.is_active, 1) = 1', 's.course_id = %s'], [slot['course_id']]
    if slot.get('class_id'):
        clauses.append('s.class_id = %s')
        params.append(slot['class_id'])
    if slot.get('division_id'):
        clauses.append('s.division_id = %s')
        params.append(slot['division_id'])
    if slot.get('is_elective'):
        clauses.append(
            "s.id IN (SELECT student_id FROM student_subject_selections WHERE subject_id = %s AND (status IS NULL OR status <> 'Withdrawn'))"
        )
        params.append(slot['subject_id'])
    if slot.get('lab_batch_group_id'):
        clauses.append(
            's.id IN (SELECT student_id FROM lab_batch_members WHERE lab_batch_group_id = %s AND ended_at IS NULL)'
        )
        params.append(slot['lab_batch_group_id'])
    cursor.execute(
        f"SELECT s.user_id, COALESCE(NULLIF(u.email, ''), s.email) AS email, s.name FROM students s "
        f"LEFT JOIN users u ON u.id = s.user_id WHERE {' AND '.join(clauses)}",
        tuple(params),
    )
    return cursor.fetchall()


def _cohort_label(slot):
    parts = [slot.get('course_name'), slot.get('class_name'), slot.get('division_name'), slot.get('lab_batch_name')]
    return ' / '.join(str(part) for part in parts if part)


def _time(value):
    if value is None:
        return ''
    if hasattr(value, 'total_seconds'):
        seconds = int(value.total_seconds())
        return f'{seconds // 3600:02d}:{seconds % 3600 // 60:02d}'
    return str(value)[:5]


def on_lecture_cancelled(cursor, *, timetable_id, session_date, reason, notes=''):
    """Tell the roster students and the slot's teacher. Returns how many messages were queued."""
    if not _switch_on(cursor, 'cancellation_alerts'):
        return 0
    slot = _slot(cursor, timetable_id)
    if not slot:
        return 0
    when = f"{session_date} {_time(slot['start_time'])}-{_time(slot['end_time'])}"
    subject = f"[{_institution()}] {slot['subject_name']} on {session_date} is cancelled"
    body = (
        f"The {slot['subject_name']} lecture for {_cohort_label(slot)} scheduled {when} "
        f"with {slot.get('faculty_name') or 'the faculty member'} is cancelled.\n"
        f"Reason: {reason}{(' - ' + notes) if notes else ''}\n"
    )
    payload = {'timetable_id': timetable_id, 'session_date': str(session_date), 'reason': reason}
    queued = 0
    for student in _roster_users(cursor, slot):
        if enqueue(cursor, kind='lecture_cancelled', subject=subject, body=body, recipient_user_id=student['user_id'],
                   recipient_email=student.get('email'), payload=payload,
                   dedupe_key=f"cancel:{timetable_id}:{session_date}:{student['user_id']}"):
            queued += 1
    if slot.get('faculty_id') and enqueue(
        cursor, kind='lecture_cancelled', subject=subject, body=body, recipient_user_id=slot['faculty_id'], payload=payload,
        dedupe_key=f"cancel:{timetable_id}:{session_date}:{slot['faculty_id']}",
    ):
        queued += 1
    return queued


def on_proxy_assigned(cursor, proxy_log_id):
    """Tell the substitute and the absent teacher. Returns how many messages were queued."""
    if not _switch_on(cursor, 'proxy_alerts'):
        return 0
    cursor.execute(
        """
        SELECT pl.id, pl.original_faculty_id, pl.proxy_faculty_id, pl.timetable_id, pl.absence_date, pl.status,
               o.name AS original_name, p.name AS proxy_name
        FROM proxy_log pl
        LEFT JOIN faculty o ON o.user_id = pl.original_faculty_id
        LEFT JOIN faculty p ON p.user_id = pl.proxy_faculty_id
        WHERE pl.id = %s
        """,
        (proxy_log_id,),
    )
    row = cursor.fetchone()
    if not row or not row.get('proxy_faculty_id') or row.get('status') != 'ASSIGNED':
        return 0
    slot = _slot(cursor, row['timetable_id']) or {}
    what = f"{slot.get('subject_name') or 'a lecture'} for {_cohort_label(slot)} on {row['absence_date']} {_time(slot.get('start_time'))}-{_time(slot.get('end_time'))}"
    payload = {'proxy_log_id': proxy_log_id, 'timetable_id': row['timetable_id'], 'absence_date': str(row['absence_date'])}
    queued = 0
    if enqueue(
        cursor, kind='proxy_assigned', recipient_user_id=row['proxy_faculty_id'], payload=payload,
        subject=f"[{_institution()}] You are the substitute for {slot.get('subject_name') or 'a lecture'} on {row['absence_date']}",
        body=f"You have been assigned to take {what} in place of {row.get('original_name') or 'a colleague'}.\n",
        dedupe_key=f"proxy:{proxy_log_id}:{row['proxy_faculty_id']}",
    ):
        queued += 1
    if row.get('original_faculty_id') and enqueue(
        cursor, kind='proxy_assigned', recipient_user_id=row['original_faculty_id'], payload=payload,
        subject=f"[{_institution()}] Substitute arranged for {slot.get('subject_name') or 'your lecture'} on {row['absence_date']}",
        body=f"{row.get('proxy_name') or 'A colleague'} will take {what} for you.\n",
        dedupe_key=f"proxy:{proxy_log_id}:{row['original_faculty_id']}",
    ):
        queued += 1
    return queued


def _hods(cursor, department_id):
    """HOD users of a department (users.is_hod); every HOD when the department is unknown."""
    if department_id:
        cursor.execute("SELECT id FROM users WHERE is_hod = 1 AND status = 'active' AND department_id = %s", (department_id,))
    else:
        cursor.execute("SELECT id FROM users WHERE is_hod = 1 AND status = 'active'")
    return [row['id'] for row in cursor.fetchall()]


def on_shift_request(cursor, request_id):
    """A faculty member asked for a shift change: tell the HOD(s) of their department. Returns messages queued."""
    if not _switch_on(cursor, 'shift_alerts'):
        return 0
    cursor.execute(
        """
        SELECT r.id, r.faculty_id, r.day_of_week, r.current_shift_name, r.requested_shift_name, r.reason,
               f.name AS faculty_name, f.department_id
        FROM shift_change_requests r
        LEFT JOIN faculty f ON f.user_id = r.faculty_id
        WHERE r.id = %s
        """,
        (request_id,),
    )
    row = cursor.fetchone()
    if not row:
        return 0
    subject = f"[{_institution()}] Shift change request from {row.get('faculty_name') or 'a faculty member'}"
    body = (
        f"{row.get('faculty_name') or 'A faculty member'} requests {row['day_of_week']}: "
        f"{row.get('current_shift_name') or '-'} -> {row.get('requested_shift_name') or '-'}.\n"
        f"Reason: {row.get('reason') or '-'}\n"
    )
    queued = 0
    for hod in _hods(cursor, row.get('department_id')):
        if enqueue(cursor, kind='shift_request', recipient_user_id=hod, subject=subject, body=body,
                   payload={'request_id': request_id}, dedupe_key=f'shift:{request_id}:{hod}'):
            queued += 1
    return queued


def on_shift_decision(cursor, request_id):
    """The request was approved or rejected: tell the faculty member."""
    if not _switch_on(cursor, 'shift_alerts'):
        return 0
    cursor.execute(
        'SELECT id, faculty_id, day_of_week, requested_shift_name, status, admin_response FROM shift_change_requests WHERE id = %s',
        (request_id,),
    )
    row = cursor.fetchone()
    if not row or row['status'] not in ('approved', 'rejected'):
        return 0
    return 1 if enqueue(
        cursor, kind='shift_decision', recipient_user_id=row['faculty_id'],
        subject=f"[{_institution()}] Your shift change request was {row['status']}",
        body=(
            f"Your request for {row['day_of_week']} ({row.get('requested_shift_name') or '-'}) was {row['status']}.\n"
            f"Response: {row.get('admin_response') or '-'}\n"
        ),
        payload={'request_id': request_id, 'status': row['status']},
        dedupe_key=f"shift-decision:{request_id}:{row['status']}",
    ) else 0


def _booking_when(row):
    if row.get('booking_date'):
        when = row['booking_date']
        when = when.isoformat() if hasattr(when, 'isoformat') else str(when)[:10]
    else:
        when = f"every {row.get('day_of_week') or 'week'}"
        if row.get('repeat_until'):
            until = row['repeat_until']
            when += f" until {until.isoformat() if hasattr(until, 'isoformat') else str(until)[:10]}"
    return f"{when} {_time(row.get('start_time'))}-{_time(row.get('end_time'))}"


def _room_approvers(cursor, institution_id):
    """Active users who may approve bookings for rooms of `institution_id`: holders of rooms_change_room who are
    members of that institution (every holder when the tenant has one institution or no memberships table)."""
    cursor.execute(
        """
        SELECT DISTINCT u.id FROM users u
        JOIN roles r ON r.name = u.role
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE u.status = 'active' AND p.name = 'rooms_change_room'
        """
    )
    holders = [row['id'] for row in cursor.fetchall()]
    if not holders or not institution_id:
        return holders
    if not table_exists(cursor, 'institution_memberships'):
        return holders
    marks = ', '.join(['%s'] * len(holders))
    cursor.execute(
        f"SELECT DISTINCT user_id FROM institution_memberships WHERE institution_id = %s AND user_id IN ({marks})",
        (institution_id, *holders),
    )
    members = [row['user_id'] for row in cursor.fetchall()]
    cursor.execute(f"SELECT id FROM users WHERE role = 'Super Admin' AND status = 'active' AND id IN ({marks})", tuple(holders))
    super_admins = [row['id'] for row in cursor.fetchall()]
    return sorted(set(members) | set(super_admins)) or holders


def on_booking_request(cursor, booking_id):
    """A room was requested: tell the people who can approve it (the room's owning institution). Returns messages queued."""
    if not _switch_on(cursor, None):
        return 0
    from services import bookings

    row = bookings.load(cursor, booking_id)
    if not row or row['status'] != 'requested':
        return 0
    subject = f"[{_institution()}] Room booking request: {row['room_number']} for {row['title']}"
    body = (
        f"{row.get('booked_by_name') or 'Someone'} asks for {row['room_number']} ({row.get('kind')}) on {_booking_when(row)}.\n"
        f"Title: {row['title']}\nNotes: {row.get('notes') or '-'}\n"
    )
    queued = 0
    for user_id in _room_approvers(cursor, row.get('room_institution_id')):
        if user_id == row.get('booked_by'):
            continue
        if enqueue(cursor, kind='booking_request', recipient_user_id=user_id, subject=subject, body=body,
                   payload={'booking_id': booking_id}, dedupe_key=f'booking:{booking_id}:{user_id}'):
            queued += 1
    return queued


def on_booking_decision(cursor, booking_id):
    """The booking was approved or rejected: tell whoever asked for it."""
    if not _switch_on(cursor, None):
        return 0
    from services import bookings

    row = bookings.load(cursor, booking_id)
    if not row or row['status'] not in ('approved', 'rejected') or not row.get('booked_by'):
        return 0
    return 1 if enqueue(
        cursor, kind='booking_decision', recipient_user_id=row['booked_by'],
        subject=f"[{_institution()}] Your booking of {row['room_number']} was {row['status']}",
        body=(
            f"Your booking '{row['title']}' of {row['room_number']} on {_booking_when(row)} was {row['status']}.\n"
            f"Response: {row.get('decision_note') or '-'}\n"
        ),
        payload={'booking_id': booking_id, 'status': row['status']},
        dedupe_key=f"booking-decision:{booking_id}:{row['status']}",
    ) else 0


def defaulter_alerts(cursor, *, month=None, threshold=None):
    """Queue one alert per student currently below the threshold, once per calendar month. Returns messages queued."""
    from services.attendance_calc import defaulters

    if not _switch_on(cursor, 'defaulter_alerts'):
        return 0
    month = month or date.today().strftime('%Y-%m')
    below, chosen = defaulters(cursor, threshold=threshold)
    if below:
        from services.webhooks import on_defaulters

        on_defaulters(
            cursor, threshold=float(chosen.threshold), month=month,
            students=[
                {
                    'student_id': report.student_id, 'name': report.student.get('name'), 'roll_number': report.student.get('roll_number'),
                    'course_id': report.student.get('course_id'), 'class_id': report.student.get('class_id'),
                    'division_id': report.student.get('division_id'), 'percentage': float(report.overall.percentage),
                    'attended': report.overall.attended, 'countable': report.overall.countable,
                }
                for report in below
            ],
        )
    queued = 0
    for report in below:
        student, overall = report.student, report.overall
        if not student.get('user_id'):
            continue
        if enqueue(
            cursor, kind='defaulter', recipient_user_id=student['user_id'], recipient_email=student.get('email'),
            subject=f"[{_institution()}] Attendance below {chosen.threshold}%",
            body=(
                f"Dear {student.get('name') or 'student'},\n\n"
                f"Your attendance is {overall.percentage}% ({overall.attended} of {overall.countable} countable lectures), "
                f"below the required {chosen.threshold}%. "
                + (f"Attend the next {report.summary.classes_needed} lectures to reach it.\n" if report.summary.classes_needed else '\n')
            ),
            payload={'student_id': report.student_id, 'percentage': float(overall.percentage), 'month': month},
            dedupe_key=f'defaulter:{report.student_id}:{month}',
        ):
            queued += 1
    return queued


def not_marked_digest(cursor, day):
    """One message per HOD listing yesterday's lectures in their department that were never marked. Returns messages queued."""
    if not _switch_on(cursor, 'not_marked_digest'):
        return 0
    cursor.execute(
        """
        SELECT ls.timetable_id, t.start_time, t.end_time, sub.name AS subject_name, f.name AS faculty_name, f.department_id,
               c.name AS course_name, cl.name AS class_name, d.name AS division_name
        FROM lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        JOIN subjects sub ON sub.id = t.subject_id
        LEFT JOIN faculty f ON f.user_id = COALESCE(ls.taught_by, t.faculty_id)
        LEFT JOIN courses c ON c.id = t.course_id
        LEFT JOIN classes cl ON cl.id = t.class_id
        LEFT JOIN divisions d ON d.id = t.division_id
        WHERE ls.session_date = %s AND ls.status = 'not_marked'
        ORDER BY f.department_id, t.start_time, sub.name
        """,
        (day,),
    )
    rows = cursor.fetchall()
    if not rows:
        return 0
    by_department = {}
    for row in rows:
        by_department.setdefault(row.get('department_id'), []).append(row)
    queued = 0
    for department_id, lectures in by_department.items():
        lines = [
            f"- {_time(row['start_time'])}-{_time(row['end_time'])} {row['subject_name']} ({_cohort_label(row)}) - {row.get('faculty_name') or 'unassigned'}"
            for row in lectures
        ]
        body = f"Lectures on {day} with no attendance marked:\n\n" + '\n'.join(lines) + '\n'
        for hod in _hods(cursor, department_id):
            if enqueue(cursor, kind='not_marked_digest', recipient_user_id=hod,
                       subject=f"[{_institution()}] {len(lectures)} lecture(s) not marked on {day}",
                       body=body, payload={'date': str(day), 'count': len(lectures)},
                       dedupe_key=f'not-marked:{day}:{hod}'):
                queued += 1
    return queued


def after_close_day(app, connection, today=None):
    """Nightly triggers on one tenant database: the not-marked digest for yesterday and this month's defaulter alerts."""
    today = today or date.today()
    cursor = connection.cursor(dictionary=True)
    counts = {'not_marked_digest': 0, 'defaulter': 0}
    try:
        if not table_exists(cursor):
            return counts
        from services.academic_calendar import sweep

        counts['calendar_cancelled'] = sweep(cursor)
        counts['not_marked_digest'] = not_marked_digest(cursor, today - timedelta(days=1))
        counts['defaulter'] = defaulter_alerts(cursor, month=today.strftime('%Y-%m'))
        connection.commit()
    except Exception:
        connection.rollback()
        app.logger.exception('Notification triggers after close-day failed')
    finally:
        cursor.close()
    if any(counts.values()):
        app.logger.info('Notifications queued after close-day: %s', counts)
    return counts


def queue_test_message(cursor, *, to, user_id=None):
    """A test message to one address, used by the settings page and the CLI."""
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return enqueue(
        cursor, kind='test', recipient_email=to, recipient_user_id=user_id,
        subject=f'[{_institution()}] Test notification',
        body=f'This is a test message from the timetable system sent at {stamp}.\n',
    )


__all__ = [
    'KINDS', 'SWITCHES', 'SETTING_FIELDS', 'WORKER_ID', 'NotificationsOff',
    'load_settings', 'save_settings', 'smtp_account', 'status', 'enqueue', 'recent', 'send', 'process_one',
    'run_tenant', 'run_pass', 'ensure_worker', 'on_lecture_cancelled', 'on_proxy_assigned', 'on_shift_request',
    'on_shift_decision', 'defaulter_alerts', 'not_marked_digest', 'after_close_day', 'queue_test_message',
]
