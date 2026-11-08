"""Lecture sessions: a held row on first marking, cancellation, the nightly close-day, and the backfill.

Functions that take a cursor run inside the caller's transaction and never
commit. close_day and backfill_sessions take a connection and commit (or roll
back on a dry run) themselves. See docs/DESIGN_ATTENDANCE_CALCULATION.md, 3.
"""

import json
from collections import OrderedDict
from datetime import date

from academic_rules.holidays import holidays_for_range, is_working_day
from academic_rules.weekdays import weekday_name
from data_access.lecture_sessions import (
    CANCELLED,
    HELD,
    NOT_MARKED,
    count_marks,
    delete_marks,
    fetch_active_slots_for_weekday,
    fetch_approved_proxy,
    fetch_marked_student_ids,
    fetch_mobile_sessions_for_date,
    fetch_proxies_for_date,
    fetch_session,
    fetch_session_dates,
    fetch_session_for,
    fetch_sessions,
    fetch_unlinked_mark_groups,
    fetch_unlinked_marks_outside_roster,
    insert_absent_mark,
    insert_not_marked,
    link_marks,
    resolve_taught_by,
    restore_session,
    upsert_cancelled_session,
    upsert_held_session,
)
from data_access.teacher_attendance import fetch_lecture_roster
from security import log_activity

CANCEL_REASONS = frozenset(('faculty_absent', 'institution', 'exam', 'other'))
SOURCES = frozenset(('teacher', 'mobile', 'admin', 'close_day', 'backfill'))

CLOSE_DAY_SOURCE = 'flask attendance close-day'
BACKFILL_SOURCE = 'flask attendance backfill-sessions'


class SessionCancelled(Exception):
    """Marking was refused because the lecture is cancelled."""


class SessionHasMarks(Exception):
    """Cancelling was refused because attendance has been marked."""


class SessionNotFound(Exception):
    pass


def record_held_session(cursor, timetable_id, session_date, marked_by_faculty_id, source):
    """Make sure a held session exists for the slot and date; return its id. Raises SessionCancelled."""
    existing = fetch_session_for(cursor, timetable_id, session_date)
    if existing and existing['status'] == CANCELLED:
        raise SessionCancelled(existing['id'])
    taught_by = resolve_taught_by(cursor, timetable_id, session_date)
    return upsert_held_session(cursor, timetable_id, session_date, taught_by, marked_by_faculty_id, source)


def cancel_lecture(cursor, *, timetable_id, session_date, actor_user_id, reason, notes='', source, clear_marks=False):
    """Cancel the slot's lecture on that date. Refused with SessionHasMarks unless clear_marks. Audited."""
    if reason not in CANCEL_REASONS:
        raise ValueError('reason')
    existing = fetch_session_for(cursor, timetable_id, session_date)
    marks = count_marks(cursor, existing['id']) if existing else 0
    if marks and not clear_marks:
        raise SessionHasMarks(marks)
    if marks:
        delete_marks(cursor, existing['id'])
    taught_by = resolve_taught_by(cursor, timetable_id, session_date)
    session_id = upsert_cancelled_session(
        cursor, timetable_id, session_date, taught_by, actor_user_id, reason, notes or None, source,
    )
    log_activity(
        actor_user_id, 'lecture_session_cancelled',
        f'Lecture {timetable_id} on {session_date} cancelled ({reason})', 'lecture_session', session_id,
        old_values={'status': existing['status'] if existing else None, 'marks': marks},
        new_values={'status': CANCELLED, 'reason': reason, 'marks_cleared': marks, 'timetable_id': timetable_id,
                    'session_date': str(session_date)},
        cursor=cursor,
    )
    return session_id


def restore_lecture(cursor, session_id, actor_user_id, today=None):
    """Undo a cancellation. Back to held when marks exist, not_marked for a past date, and no row for a future one."""
    today = today or date.today()
    session = fetch_session(cursor, session_id)
    if not session:
        raise SessionNotFound(session_id)
    if session['status'] != CANCELLED:
        return session['status']
    if count_marks(cursor, session_id):
        status = HELD
    elif session['session_date'] < today:
        status = NOT_MARKED
    else:
        status = None
    if status is None:
        cursor.execute('DELETE FROM lecture_sessions WHERE id = %s', (session_id,))
    else:
        restore_session(cursor, session_id, status)
    log_activity(
        actor_user_id, 'lecture_session_restored',
        f'Cancellation of lecture {session["timetable_id"]} on {session["session_date"]} undone',
        'lecture_session', session_id,
        old_values={'status': CANCELLED, 'reason': session['cancel_reason']},
        new_values={'status': status or 'removed', 'timetable_id': session['timetable_id'],
                    'session_date': str(session['session_date'])},
        cursor=cursor,
    )
    return status


def may_mark(cursor, timetable_id, session_date, user_id, slot_faculty_user_id):
    """The slot's teacher, or the approved proxy for the date, may mark it."""
    if slot_faculty_user_id == user_id:
        return True
    return fetch_approved_proxy(cursor, timetable_id, session_date) == user_id


def list_sessions(cursor, **filters):
    return fetch_sessions(cursor, **filters)


def _audit_cli(cursor, action, source, values):
    cursor.execute(
        'INSERT INTO audit_logs (user_id, username, action, entity_type, entity_id, new_values, '
        'request_method, request_url, status) VALUES (NULL, NULL, %s, %s, NULL, %s, %s, %s, %s)',
        (action, 'lecture_session', json.dumps(values, default=str), 'CLI', source, 'success'),
    )


ABSENT_FILL_REMARK = 'Not detected by the attendance device'


def _fill_mobile_absences(cursor, day, dry_run):
    """Absent rows for roster students without a mark in every lecture the device marked on `day`.

    Only sessions with source 'mobile': a teacher's form says who it covers, a
    device only reports who it saw. The session's first marker is the marker.
    """
    filled = 0
    for session in fetch_mobile_sessions_for_date(cursor, day):
        if session['marked_by'] is None:
            continue
        marked = fetch_marked_student_ids(cursor, session['id'])
        for student in fetch_lecture_roster(cursor, session):
            if student['id'] in marked:
                continue
            if dry_run or insert_absent_mark(cursor, student['id'], session, ABSENT_FILL_REMARK):
                filled += 1
    return filled


def close_day(connection, day, *, dry_run=False, today=None):
    """Write not_marked for every active lecture of `day` that has no session row, and Absent for
    roster students a face-attendance device did not detect in a lecture it marked.

    Only for past days. Holidays (for the slot's program) and dates outside the
    slot's semester create nothing. Re-running changes nothing. Returns counts.
    """
    today = today or date.today()
    if day >= today:
        raise ValueError('close-day closes past days only')
    cursor = connection.cursor(dictionary=True)
    try:
        weekday = weekday_name(day)
        holidays = holidays_for_range(cursor, day, day)
        slots = fetch_active_slots_for_weekday(cursor, weekday)
        existing = fetch_session_dates(cursor, day)
        proxies = fetch_proxies_for_date(cursor, day)
        counts = {'date': str(day), 'weekday': weekday, 'slots': len(slots), 'created': 0, 'existing': 0,
                  'holiday': 0, 'outside_semester': 0, 'absent_filled': 0, 'dry_run': dry_run}
        counts['absent_filled'] = _fill_mobile_absences(cursor, day, dry_run)
        for slot in slots:
            if slot['id'] in existing:
                counts['existing'] += 1
                continue
            if not is_working_day(day, slot['program'], holidays):
                counts['holiday'] += 1
                continue
            start, end = slot.get('semester_start'), slot.get('semester_end')
            if start and end and not (start <= day <= end):
                counts['outside_semester'] += 1
                continue
            if not dry_run:
                insert_not_marked(cursor, slot['id'], day, proxies.get(slot['id'], slot['faculty_id']))
            counts['created'] += 1
        if dry_run:
            connection.rollback()
        else:
            _audit_cli(cursor, 'attendance_close_day', CLOSE_DAY_SOURCE, counts)
            connection.commit()
        return counts
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


class BackfillReport:
    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.sessions = 0          # sessions to create (or created)
        self.reused = 0            # existing held / not_marked sessions the marks were linked to
        self.rows = 0              # attendance rows to link (or linked)
        self.skipped_rows = 0      # rows left unlinked (their session is cancelled)
        self.anomalies = OrderedDict((kind, []) for kind in (
            'weekday_mismatch', 'retired_slot', 'marker_not_teacher', 'holiday', 'outside_roster', 'cancelled_session',
        ))

    def note(self, kind, timetable_id, day, detail=None):
        entry = {'timetable_id': timetable_id, 'date': str(day)}
        if detail is not None:
            entry['detail'] = detail
        self.anomalies[kind].append(entry)

    def counts(self):
        return {
            'dry_run': self.dry_run, 'sessions': self.sessions, 'reused': self.reused, 'rows': self.rows,
            'skipped_rows': self.skipped_rows,
            'anomalies': {kind: len(items) for kind, items in self.anomalies.items() if items},
        }

    def lines(self):
        verb = 'to create' if self.dry_run else 'created'
        link = 'to link' if self.dry_run else 'linked'
        out = [
            f'Sessions {verb}: {self.sessions} (existing sessions reused: {self.reused})',
            f'Attendance rows {link}: {self.rows} (left unlinked: {self.skipped_rows})',
        ]
        total = sum(len(items) for items in self.anomalies.values())
        out.append(f'Anomalies: {total}')
        for kind, items in self.anomalies.items():
            for item in items:
                detail = f" ({item['detail']})" if 'detail' in item else ''
                out.append(f"  - {kind}: slot {item['timetable_id']} on {item['date']}{detail}")
        return out


def _groups(rows):
    """Collapse marker-level rows into one entry per (slot, date). Rows arrive with the busiest marker first."""
    groups = OrderedDict()
    for row in rows:
        key = (row['timetable_id'], row['attendance_date'])
        group = groups.get(key)
        if group is None:
            group = dict(row)
            group['markers'] = []
            groups[key] = group
        group['markers'].append(row)
    for group in groups.values():
        group['marks'] = sum(marker['marks'] for marker in group['markers'])
        group['first_marked_at'] = min(
            (marker['first_marked_at'] for marker in group['markers'] if marker['first_marked_at']), default=None,
        )
    return groups


def backfill_sessions(connection, *, dry_run=False):
    """Create held sessions for marked (slot, date) pairs and link the marks. Never invents unmarked lectures."""
    report = BackfillReport(dry_run)
    cursor = connection.cursor(dictionary=True)
    try:
        groups = _groups(fetch_unlinked_mark_groups(cursor))
        if groups:
            days = [key[1] for key in groups]
            holidays = holidays_for_range(cursor, min(days), max(days))
        for (timetable_id, day), group in groups.items():
            proxy = fetch_approved_proxy(cursor, timetable_id, day)
            taught_by = proxy if proxy is not None else group['faculty_id']
            if weekday_name(day) != weekday_name(group['day_of_week']):
                report.note('weekday_mismatch', timetable_id, day, f"slot is on {group['day_of_week']}")
            if not group['is_active']:
                report.note('retired_slot', timetable_id, day)
            if not is_working_day(day, group['program'], holidays):
                report.note('holiday', timetable_id, day)
            strangers = [m for m in group['markers'] if m['marker_user_id'] not in (group['faculty_id'], proxy)]
            if strangers:
                report.note('marker_not_teacher', timetable_id, day, f"marked_by {[m['marked_by'] for m in strangers]}")
            roster = {row['id'] for row in fetch_lecture_roster(cursor, group)}
            outside = fetch_unlinked_marks_outside_roster(cursor, timetable_id, day, roster)
            if outside:
                report.note('outside_roster', timetable_id, day, f'students {outside}')
            existing = fetch_session_for(cursor, timetable_id, day)
            if existing and existing['status'] == CANCELLED:
                report.note('cancelled_session', timetable_id, day, f"{group['marks']} marks left unlinked")
                report.skipped_rows += group['marks']
                continue
            if existing:
                report.reused += 1
            else:
                report.sessions += 1
            report.rows += group['marks']
            if dry_run:
                continue
            marked_by = group['markers'][0]['marked_by']
            session_id = upsert_held_session(cursor, timetable_id, day, taught_by, marked_by, 'backfill')
            if group['first_marked_at'] and not existing:
                cursor.execute('UPDATE lecture_sessions SET marked_at = %s WHERE id = %s', (group['first_marked_at'], session_id))
            link_marks(cursor, session_id, timetable_id, day)
        if dry_run:
            connection.rollback()
        else:
            values = report.counts()
            values['anomaly_list'] = {kind: items for kind, items in report.anomalies.items() if items}
            _audit_cli(cursor, 'attendance_backfill_sessions', BACKFILL_SOURCE, values)
            connection.commit()
        return report
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
