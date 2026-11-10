"""Consent, retention, passive liveness checks, the recognition audit, and lecture session codes.

Everything here takes a dictionary cursor and runs inside the caller's
transaction; nothing commits. Settings are read from current_app.config
(FACE_* in config/base.py). See docs/FACE_ATTENDANCE.md.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from flask import current_app, has_app_context

from services.face.templates import decode_template, is_encrypted

CONSENT_SOURCES = frozenset(('web', 'mobile', 'cli', 'admin'))
ACCEPTED = 'accepted'
REJECTED = 'rejected'

# Rejection reasons the audit stores (varchar(64)).
NO_CONSENT = 'no_consent'
LOW_CONFIDENCE = 'low_confidence'
LOW_LIVENESS = 'low_liveness'
DUPLICATE_FRAME = 'duplicate_frame'
TEMPLATE_TOO_OLD = 'template_too_old'
NO_TEMPLATE = 'no_template'
SESSION_CODE_REQUIRED = 'session_code_required'
SESSION_CODE_INVALID = 'session_code_invalid'
SESSION_CODE_EXPIRED = 'session_code_expired'
SESSION_CLOSED = 'session_closed'


def _setting(name, default):
    if not has_app_context():
        return default
    value = current_app.config.get(name, default)
    return default if value is None else value


def _flag(name, default):
    value = _setting(name, default)
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


class ConsentRequired(Exception):
    """Enrolment or recognition was refused because the person has no active consent."""


# Consent

def notice_version():
    return str(_setting('FACE_CONSENT_NOTICE_VERSION', '2026-01')).strip()


def consent_required():
    return _flag('FACE_CONSENT_REQUIRED', True)


def active_consent(cursor, user_id, version=None):
    """The user's active consent row for the notice version (any version when None), or None."""
    clauses, params = ['user_id = %s', 'withdrawn_at IS NULL'], [user_id]
    if version:
        clauses.append('notice_version = %s')
        params.append(version)
    cursor.execute(
        f"SELECT id, user_id, notice_version, given_at, recorded_by, source FROM face_consents "
        f"WHERE {' AND '.join(clauses)} ORDER BY given_at DESC, id DESC LIMIT 1",
        tuple(params),
    )
    return cursor.fetchone()


def has_consent(cursor, user_id):
    """True when consent is not required, or the user has an active consent for the current notice."""
    if not consent_required():
        return True
    return active_consent(cursor, user_id, notice_version()) is not None


def require_consent(cursor, user_id):
    if not has_consent(cursor, user_id):
        raise ConsentRequired(user_id)


def record_consent(cursor, user_id, *, source, recorded_by=None, version=None, given_at=None):
    """Record consent for the current notice. An active row for the same version is reused. Returns its id."""
    if source not in CONSENT_SOURCES:
        raise ValueError('source')
    version = version or notice_version()
    existing = active_consent(cursor, user_id, version)
    if existing:
        return existing['id']
    cursor.execute(
        'INSERT INTO face_consents (user_id, notice_version, given_at, recorded_by, source) VALUES (%s, %s, %s, %s, %s)',
        (user_id, version, given_at or datetime.utcnow().replace(microsecond=0), recorded_by, source),
    )
    return cursor.lastrowid


def withdraw_consent(cursor, user_id, *, delete_templates=True):
    """Close every active consent and (by default) delete the person's templates. Returns (consents, templates)."""
    cursor.execute(
        'UPDATE face_consents SET withdrawn_at = UTC_TIMESTAMP() WHERE user_id = %s AND withdrawn_at IS NULL', (user_id,),
    )
    withdrawn = cursor.rowcount
    deleted = delete_templates_for(cursor, user_id) if delete_templates else 0
    return withdrawn, deleted


def delete_templates_for(cursor, user_id):
    cursor.execute('DELETE FROM mobile_face_templates WHERE user_id = %s', (user_id,))
    return cursor.rowcount


def consent_status(cursor, user_ids):
    """{user_id: True/False} for the current notice version. Everyone is True when consent is off."""
    user_ids = [int(value) for value in user_ids if value is not None]
    if not user_ids:
        return {}
    if not consent_required():
        return {user_id: True for user_id in user_ids}
    placeholders = ','.join(['%s'] * len(user_ids))
    cursor.execute(
        f'SELECT DISTINCT user_id FROM face_consents WHERE withdrawn_at IS NULL AND notice_version = %s '
        f'AND user_id IN ({placeholders})',
        (notice_version(), *user_ids),
    )
    consented = {row['user_id'] for row in cursor.fetchall()}
    return {user_id: user_id in consented for user_id in user_ids}


# Retention

def purge_templates(cursor, *, days=None, now=None):
    """Delete templates whose owner withdrew consent or became inactive more than `days` ago.

    Also deletes templates of users who never consented when consent is
    required (an installation that turned FACE_CONSENT_REQUIRED on later).
    Returns counts per reason.
    """
    days = int(_setting('FACE_RETENTION_DAYS', 30) if days is None else days)
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=max(0, days))
    counts = {'withdrawn': 0, 'inactive_user': 0, 'never_consented': 0}

    cursor.execute(
        """
        DELETE t FROM mobile_face_templates t
        WHERE EXISTS (SELECT 1 FROM face_consents c WHERE c.user_id = t.user_id AND c.withdrawn_at IS NOT NULL)
          AND NOT EXISTS (SELECT 1 FROM face_consents c WHERE c.user_id = t.user_id AND c.withdrawn_at IS NULL)
          AND (SELECT MAX(c.withdrawn_at) FROM face_consents c WHERE c.user_id = t.user_id) <= %s
        """,
        (cutoff,),
    )
    counts['withdrawn'] = cursor.rowcount

    cursor.execute(
        """
        DELETE t FROM mobile_face_templates t
        JOIN users u ON u.id = t.user_id
        WHERE u.status = 'inactive' AND COALESCE(u.updated_at, u.created_at) <= %s
        """,
        (cutoff,),
    )
    counts['inactive_user'] = cursor.rowcount

    if consent_required():
        cursor.execute(
            """
            DELETE t FROM mobile_face_templates t
            WHERE NOT EXISTS (SELECT 1 FROM face_consents c WHERE c.user_id = t.user_id)
              AND t.created_at <= %s
            """,
            (cutoff,),
        )
        counts['never_consented'] = cursor.rowcount
    return counts


# Audit

def frame_hash_of(value):
    """A device may send the frame hash itself or a frame identifier; both end up as a 64-char hex digest."""
    if value in (None, ''):
        return None
    text = str(value).strip()
    if len(text) == 64 and all(c in '0123456789abcdef' for c in text.lower()):
        return text.lower()
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def record_decision(cursor, *, device_id, decision, reason='ok', event_uuid=None, user_id=None, student_id=None,
                    timetable_id=None, attendance_date=None, confidence=None, liveness_score=None, frame_hash=None,
                    template_age_days=None):
    """One audit row per recognition event the server judged. Returns its id."""
    cursor.execute(
        """
        INSERT INTO face_recognition_audit
            (device_id, event_uuid, user_id, student_id, timetable_id, attendance_date, confidence, liveness_score,
             frame_hash, template_age_days, decision, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(device_id)[:128], event_uuid, user_id, student_id, timetable_id, attendance_date,
            _decimal(confidence), _decimal(liveness_score), frame_hash, template_age_days, decision, str(reason)[:64],
        ),
    )
    audit_id = cursor.lastrowid
    if has_app_context():
        current_app.logger.info(
            'face recognition %s: device=%s event=%s user=%s student=%s timetable=%s confidence=%s liveness=%s reason=%s',
            decision, device_id, event_uuid, user_id, student_id, timetable_id, _decimal(confidence),
            _decimal(liveness_score), reason,
        )
    return audit_id


def _decimal(value):
    if value in (None, ''):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(min(max(number, 0.0), 9.9999), 4)


def recent_frame_seen(cursor, device_id, frame_hash, seconds=None, exclude_event_uuid=None):
    """True when this device already sent a frame with this hash inside the window."""
    if not frame_hash:
        return False
    seconds = int(_setting('FACE_DUPLICATE_FRAME_SECONDS', 600) if seconds is None else seconds)
    cursor.execute(
        """
        SELECT 1 FROM face_recognition_audit
        WHERE device_id = %s AND frame_hash = %s AND created_at >= UTC_TIMESTAMP() - INTERVAL %s SECOND
          AND (%s IS NULL OR event_uuid IS NULL OR event_uuid <> %s)
        LIMIT 1
        """,
        (str(device_id)[:128], frame_hash, seconds, exclude_event_uuid, exclude_event_uuid),
    )
    return cursor.fetchone() is not None


def template_age_days(cursor, user_id, now=None):
    """Days since the user's active template was last written, or None without one."""
    cursor.execute(
        'SELECT updated_at, created_at FROM mobile_face_templates WHERE user_id = %s AND is_active = 1 '
        'ORDER BY updated_at DESC LIMIT 1',
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    written = row['updated_at'] or row['created_at']
    if written is None:
        return 0
    now = now or datetime.utcnow()
    return max(0, (now - written).days)


def check_recognition(cursor, *, device_id, user_id, confidence, liveness_score=None, frame_hash=None,
                      event_uuid=None):
    """Passive checks on one recognition. Returns (ok, reason, details).

    Rejects when the person has no consent, the confidence is below
    FACE_MIN_CONFIDENCE, a liveness score was sent and is below
    FACE_MIN_LIVENESS, the same frame was already used on this device
    within FACE_DUPLICATE_FRAME_SECONDS, or the matched template is older
    than FACE_TEMPLATE_MAX_AGE_DAYS. A missing confidence is a rejection:
    the device has to say how sure it was.
    """
    details = {'template_age_days': template_age_days(cursor, user_id) if user_id else None}
    if user_id is not None and not has_consent(cursor, user_id):
        return False, NO_CONSENT, details
    score = _decimal(confidence)
    if score is None or score < float(_setting('FACE_MIN_CONFIDENCE', 0.70)):
        return False, LOW_CONFIDENCE, details
    liveness = _decimal(liveness_score)
    if liveness_score not in (None, '') and (liveness is None or liveness < float(_setting('FACE_MIN_LIVENESS', 0.5))):
        return False, LOW_LIVENESS, details
    if frame_hash and recent_frame_seen(cursor, device_id, frame_hash, exclude_event_uuid=event_uuid):
        return False, DUPLICATE_FRAME, details
    max_age = int(_setting('FACE_TEMPLATE_MAX_AGE_DAYS', 730) or 0)
    age = details['template_age_days']
    if max_age > 0 and age is not None and age > max_age:
        return False, TEMPLATE_TOO_OLD, details
    return True, 'ok', details


# Lecture session codes

def _code():
    return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))


def open_session_code(cursor, session_id, *, minutes=None, now=None):
    """Give the session a fresh code valid for FACE_SESSION_CODE_MINUTES. Returns (code, expires_at)."""
    minutes = int(_setting('FACE_SESSION_CODE_MINUTES', 90) if minutes is None else minutes)
    now = (now or datetime.utcnow()).replace(microsecond=0)
    expires_at = now + timedelta(minutes=max(1, minutes))
    code = _code()
    cursor.execute(
        'UPDATE lecture_sessions SET session_code = %s, session_code_expires_at = %s WHERE id = %s',
        (code, expires_at, session_id),
    )
    return code, expires_at


def close_session_code(cursor, session_id):
    cursor.execute(
        'UPDATE lecture_sessions SET session_code_expires_at = UTC_TIMESTAMP() WHERE id = %s AND session_code IS NOT NULL',
        (session_id,),
    )
    return cursor.rowcount


def session_code_required():
    return _flag('FACE_REQUIRE_SESSION_CODE', False)


def check_session_code(cursor, timetable_id, session_date, code, now=None):
    """(ok, reason) for a device's code against lecture_sessions. ok when codes are not required and none was sent."""
    code = (code or '').strip().upper()
    if not code:
        return (False, SESSION_CODE_REQUIRED) if session_code_required() else (True, 'ok')
    cursor.execute(
        'SELECT status, session_code, session_code_expires_at FROM lecture_sessions '
        'WHERE timetable_id = %s AND session_date = %s',
        (timetable_id, session_date),
    )
    row = cursor.fetchone()
    if not row or not row['session_code'] or row['session_code'].upper() != code:
        return False, SESSION_CODE_INVALID
    if row['status'] == 'cancelled':
        return False, SESSION_CLOSED
    expires = row['session_code_expires_at']
    if expires is not None and expires <= (now or datetime.utcnow()):
        return False, SESSION_CODE_EXPIRED
    return True, 'ok'


# Template helpers shared by the sync endpoints

def readable_template(stored):
    """Decode a stored template; None when it is encrypted with a key this process does not have."""
    values = decode_template(stored)
    if values is None and is_encrypted(stored) and has_app_context():
        current_app.logger.error('A face template could not be decrypted; check FACE_TEMPLATE_KEY[_PREVIOUS].')
    return values
