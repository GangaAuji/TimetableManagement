"""Syllabus units and the topic recorded against a held lecture (docs/ACADEMICS.md).

Capability `syllabus`. Off: nothing is read or written, the mark screen omits the topic,
and the coverage report and `/api/v1/subjects/<id>/coverage` stay hidden.
Pace (behind / ahead) uses the academic calendar when that institution has one configured.
Otherwise the percentage is still delivered / planned and the pace is `no_pace`.
"""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from mysql.connector import IntegrityError

from core import capabilities
from services import academic_calendar as calendar

CAPABILITY = 'syllabus'
TOPIC_MAX = 200
NOTES_MAX = 500
TITLE_MAX = 120
UNIT_MAX = 40
_HOUR_STEPS = tuple(Decimal('0.5') * step for step in range(1, 7))  # 0.5 .. 3.0
_PACE_TOLERANCE = Decimal('0.5')
_ONE = Decimal('0.1')

MESSAGES = {
    'lesson_invalid': 'Choose a unit and a topic, and hours between 0.5 and 3.',
    'lesson_unit': 'That unit is not part of this subject.',
    'syllabus_unavailable': 'The syllabus tables are missing; apply the database migrations first.',
    'syllabus_invalid': 'Each unit needs a number from 1 to 99, a title and planned hours from 0.5 to 400.',
    'syllabus_in_use': 'A lesson has been logged against a unit you are removing.',
    'subject_not_found': 'That subject was not found.',
    'capability_off': 'This feature is switched off for your institution.',
}

REPORT_FIELDS = [
    'subject_code', 'subject_name', 'unit_no', 'unit_title',
    'planned_hours', 'delivered_hours', 'coverage_percent', 'expected_hours', 'pace',
]
REPORT_LABELS = {
    'subject_code': 'Code', 'subject_name': 'Subject', 'unit_no': 'Unit', 'unit_title': 'Title',
    'planned_hours': 'Planned hours', 'delivered_hours': 'Delivered hours', 'coverage_percent': 'Coverage %',
    'expected_hours': 'Expected by now', 'pace': 'Pace',
}


class LessonRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES.get(code, code))


def active(cursor):
    return capabilities.enabled(cursor, CAPABILITY)


def tables_ready(cursor):
    return capabilities.table_exists(cursor, 'syllabus_units') and capabilities.table_exists(cursor, 'lesson_logs')


def parse_hours(value):
    """A taught length on the half hour from 0.5 to 3, or None."""
    number = _decimal(value)
    if number is None or number not in _HOUR_STEPS:
        return None
    return number


def parse_planned(value):
    """Planned hours for a unit: one decimal place, 0.5 to 400."""
    number = _decimal(value)
    if number is None or number < Decimal('0.5') or number > Decimal('400'):
        return None
    return number


def pace_of(planned, delivered, elapsed, total):
    """(expected hours, pace). Pace is no_pace when the calendar has no teaching weeks."""
    planned = Decimal(planned)
    delivered = Decimal(delivered)
    if elapsed is None or total is None or int(total) <= 0:
        return None, 'no_pace'
    expected = (planned * Decimal(int(elapsed)) / Decimal(int(total))).quantize(_ONE, rounding=ROUND_HALF_UP)
    if delivered < expected - _PACE_TOLERANCE:
        pace = 'behind'
    elif delivered > expected + _PACE_TOLERANCE:
        pace = 'ahead'
    else:
        pace = 'on_track'
    return expected, pace


def coverage_lines(units, delivered, *, elapsed=None, total=None):
    """One row per unit. `delivered` maps unit id to hours already taught. Pure: no database."""
    rows = []
    for unit in units:
        planned = Decimal(str(unit['planned_hours']))
        got = Decimal(str(delivered.get(unit['id'], 0) or 0))
        expected, pace = pace_of(planned, got, elapsed, total)
        percent = None if planned <= 0 else (got * Decimal(100) / planned).quantize(_ONE, rounding=ROUND_HALF_UP)
        rows.append({
            'id': unit['id'],
            'unit_no': int(unit['unit_no']),
            'title': unit['title'],
            'planned_hours': planned,
            'delivered_hours': got,
            'percent': percent,
            'expected_hours': expected,
            'pace': pace,
        })
    return rows


def _decimal(value):
    if isinstance(value, bool) or value is None or isinstance(value, str) and not value.strip():
        return None
    try:
        return Decimal(str(value)).quantize(_ONE, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _positive(value, upper):
    if isinstance(value, bool) or isinstance(value, float) or value in (None, ''):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 1 or number > upper:
        return None
    if not isinstance(value, int) and str(value).strip() != str(number):
        return None
    return number


def _text(value, limit, *, required):
    if value is None and not required:
        return ''
    if not isinstance(value, str):
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return None
    text = value.strip()
    if len(text) > limit or (required and not text):
        return None
    return text


def _event_value(event, *keys):
    for key in keys:
        if key in event and event[key] not in (None, ''):
            return event[key]
    return None


def _lesson_present(raw, *, aliases):
    keys = ('unit_id', 'topic', 'hours', 'notes')
    if aliases:
        keys = keys + ('unitId',)
    return any(raw.get(key) not in (None, '') for key in keys)


def clean_lesson(raw, *, aliases=False):
    """A complete lesson, or LessonRejected. Hours default to 1 when omitted."""
    if not isinstance(raw, dict):
        raise LessonRejected('lesson_invalid')
    unit_id = _positive(_event_value(raw, 'unit_id', 'unitId') if aliases else raw.get('unit_id'), 10**9)
    topic = _text(_event_value(raw, 'topic') if aliases else raw.get('topic'), TOPIC_MAX, required=True)
    hours_raw = _event_value(raw, 'hours') if aliases else raw.get('hours')
    hours = parse_hours(1 if hours_raw is None else hours_raw)
    notes_raw = raw.get('notes') if 'notes' in raw else None
    notes = _text(notes_raw, NOTES_MAX, required=False)
    if unit_id is None or topic is None or hours is None or notes is None:
        raise LessonRejected('lesson_invalid')
    return {'unit_id': unit_id, 'topic': topic, 'hours': hours, 'notes': notes}


def accept_lesson(cursor, subject_id, raw):
    """None when there is nothing to store (or the capability is off). Raises LessonRejected when the fields are present but not usable."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise LessonRejected('lesson_invalid')
    if not active(cursor) or not _lesson_present(raw, aliases=False):
        return None
    if not tables_ready(cursor):
        raise LessonRejected('syllabus_unavailable')
    cleaned = clean_lesson(raw)
    _unit_belongs(cursor, subject_id, cleaned['unit_id'])
    return cleaned


def lesson_from_event(cursor, timetable_id, event):
    """The lesson on a mobile event, or None when the capability is off or the event has no topic.

    Raises LessonRejected when the capability is on and the topic fields are present but invalid,
    so the caller can reject that event before writing the mark.
    """
    if not isinstance(event, dict) or not active(cursor) or not _lesson_present(event, aliases=True):
        return None
    if not tables_ready(cursor):
        raise LessonRejected('syllabus_unavailable')
    cursor.execute('SELECT subject_id FROM timetable WHERE id = %s', (int(timetable_id),))
    slot = cursor.fetchone()
    if not slot or not slot.get('subject_id'):
        raise LessonRejected('lesson_invalid')
    cleaned = clean_lesson(event, aliases=True)
    _unit_belongs(cursor, slot['subject_id'], cleaned['unit_id'])
    return cleaned


def _unit_belongs(cursor, subject_id, unit_id):
    cursor.execute('SELECT subject_id FROM syllabus_units WHERE id = %s', (int(unit_id),))
    row = cursor.fetchone()
    if not row or int(row['subject_id']) != int(subject_id):
        raise LessonRejected('lesson_unit')


def write_lesson(cursor, session_id, lesson, recorded_by=None):
    """Insert or replace the one topic for this lecture. The unit must belong to the session's subject."""
    cursor.execute(
        """
        SELECT t.subject_id FROM lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        WHERE ls.id = %s
        """,
        (int(session_id),),
    )
    row = cursor.fetchone()
    if not row or not row.get('subject_id'):
        raise LessonRejected('lesson_invalid')
    _unit_belongs(cursor, row['subject_id'], lesson['unit_id'])
    cursor.execute(
        """
        INSERT INTO lesson_logs (lecture_session_id, unit_id, topic, hours, notes, recorded_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            unit_id = VALUES(unit_id), topic = VALUES(topic), hours = VALUES(hours),
            notes = VALUES(notes), recorded_by = VALUES(recorded_by)
        """,
        (int(session_id), int(lesson['unit_id']), lesson['topic'], lesson['hours'], lesson['notes'] or '', recorded_by),
    )


def list_units(cursor, subject_id):
    cursor.execute(
        """
        SELECT id, unit_no, title, planned_hours, sort_order
        FROM syllabus_units WHERE subject_id = %s ORDER BY sort_order, unit_no
        """,
        (int(subject_id),),
    )
    return list(cursor.fetchall())


def lesson_for(cursor, session_id):
    if not session_id:
        return None
    cursor.execute(
        'SELECT unit_id, topic, hours, notes FROM lesson_logs WHERE lecture_session_id = %s',
        (int(session_id),),
    )
    return cursor.fetchone()


def mark_context(cursor, subject_id, session_id):
    return {'units': list_units(cursor, subject_id), 'lesson': lesson_for(cursor, session_id)}


def clean_units(raw_units):
    if not isinstance(raw_units, list) or len(raw_units) > UNIT_MAX:
        raise LessonRejected('syllabus_invalid')
    cleaned, seen = [], set()
    for item in raw_units:
        if not isinstance(item, dict):
            raise LessonRejected('syllabus_invalid')
        unit_no = _positive(item.get('unit_no'), 99)
        title = _text(item.get('title'), TITLE_MAX, required=True)
        planned = parse_planned(item.get('planned_hours'))
        if unit_no is None or title is None or planned is None or unit_no in seen:
            raise LessonRejected('syllabus_invalid')
        seen.add(unit_no)
        row = {'unit_no': unit_no, 'title': title, 'planned_hours': planned, 'sort_order': len(cleaned)}
        if item.get('id') not in (None, ''):
            unit_id = _positive(item.get('id'), 10**9)
            if unit_id is None:
                raise LessonRejected('syllabus_invalid')
            row['id'] = unit_id
        cleaned.append(row)
    return cleaned


def replace_units(cursor, subject_id, raw_units):
    """Replace the subject's units. A unit that already has a lesson log cannot be removed."""
    if not active(cursor):
        raise LessonRejected('capability_off')
    if not tables_ready(cursor):
        raise LessonRejected('syllabus_unavailable')
    if _subject(cursor, subject_id) is None:
        raise LessonRejected('subject_not_found')
    incoming = clean_units(raw_units)
    cursor.execute('SELECT id FROM syllabus_units WHERE subject_id = %s', (int(subject_id),))
    existing = {int(row['id']) for row in cursor.fetchall()}
    kept = set()
    for item in incoming:
        if 'id' in item:
            if item['id'] not in existing:
                raise LessonRejected('syllabus_invalid')
            kept.add(item['id'])
    removed = [unit_id for unit_id in existing if unit_id not in kept]
    if removed:
        marks = ', '.join(['%s'] * len(removed))
        cursor.execute(f'SELECT unit_id FROM lesson_logs WHERE unit_id IN ({marks}) LIMIT 1', tuple(removed))
        if cursor.fetchone():
            raise LessonRejected('syllabus_in_use')
    try:
        for index, item in enumerate(incoming):
            if 'id' in item:
                cursor.execute('UPDATE syllabus_units SET unit_no = %s WHERE id = %s', (-(index + 1), int(item['id'])))
        if removed:
            marks = ', '.join(['%s'] * len(removed))
            cursor.execute(
                f'DELETE FROM syllabus_units WHERE subject_id = %s AND id IN ({marks})',
                (int(subject_id),) + tuple(removed),
            )
        for item in incoming:
            if 'id' in item:
                cursor.execute(
                    """
                    UPDATE syllabus_units
                    SET unit_no = %s, title = %s, planned_hours = %s, sort_order = %s
                    WHERE id = %s AND subject_id = %s
                    """,
                    (item['unit_no'], item['title'], str(item['planned_hours']), item['sort_order'], item['id'], int(subject_id)),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO syllabus_units (subject_id, unit_no, title, planned_hours, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (int(subject_id), item['unit_no'], item['title'], str(item['planned_hours']), item['sort_order']),
                )
    except IntegrityError as exc:
        raise LessonRejected('syllabus_invalid') from exc
    return list_units(cursor, subject_id)


def _subject(cursor, subject_id):
    cursor.execute(
        """
        SELECT s.id, s.name, COALESCE(s.course_code, '') AS course_code, COALESCE(d.institution_id, 1) AS institution_id
        FROM subjects s
        LEFT JOIN courses c ON c.id = s.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE s.id = %s
        """,
        (int(subject_id),),
    )
    return cursor.fetchone()


def week_progress(cursor, institution_id, today):
    """(elapsed teaching weeks, total teaching weeks) or (None, None) when the calendar is idle."""
    if not calendar.configured(cursor, institution_id):
        return None, None
    terms = [
        {'name': row['name'], 'kind': row['kind'], 'start': row['start_date'], 'end': row['end_date']}
        for row in calendar.list_terms(cursor, institution_id)
    ]
    weeks = calendar.teaching_weeks(terms)
    if not weeks:
        return None, None
    today = today if isinstance(today, date) else date.today()
    elapsed = sum(1 for week in weeks if week['week_start'] <= today)
    return elapsed, len(weeks)


def _delivered(cursor, *, subject_id=None, department_id=None, scoped=True):
    where, params = ['1=1'], []
    if scoped:
        from core.scope import current_scope

        scope_sql, scope_params = current_scope(cursor).clause('d.institution_id')
        where.append(scope_sql)
        params.extend(scope_params)
    if subject_id:
        where.append('s.id = %s')
        params.append(int(subject_id))
    if department_id:
        where.append('d.id = %s')
        params.append(int(department_id))
    cursor.execute(
        f"""
        SELECT s.id AS subject_id, s.name AS subject_name, s.course_code AS course_code,
               d.institution_id AS institution_id,
               u.id AS unit_id, u.unit_no, u.title, u.planned_hours, u.sort_order,
               COALESCE(SUM(CASE WHEN ls.status = 'held' THEN l.hours ELSE 0 END), 0) AS delivered
        FROM syllabus_units u
        JOIN subjects s ON s.id = u.subject_id
        LEFT JOIN courses c ON c.id = s.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        LEFT JOIN lesson_logs l ON l.unit_id = u.id
        LEFT JOIN lecture_sessions ls ON ls.id = l.lecture_session_id
        WHERE {' AND '.join(where)}
        GROUP BY s.id, s.name, s.course_code, d.institution_id, u.id, u.unit_no, u.title, u.planned_hours, u.sort_order
        ORDER BY s.name, u.sort_order, u.unit_no
        """,
        tuple(params),
    )
    return list(cursor.fetchall())


def coverage_for(cursor, subject_id, *, today=None, scoped=False):
    """Coverage of one subject, or None when it does not exist (or is outside the caller's scope)."""
    subject = _subject(cursor, subject_id)
    if not subject:
        return None
    if scoped:
        from core.scope import current_scope

        if not current_scope(cursor).allows(subject['institution_id']):
            return None
    rows = _delivered(cursor, subject_id=subject_id, scoped=scoped)
    elapsed, total = week_progress(cursor, subject['institution_id'], today or date.today())
    lines = coverage_lines(
        [{'id': row['unit_id'], 'unit_no': row['unit_no'], 'title': row['title'], 'planned_hours': row['planned_hours']} for row in rows],
        {row['unit_id']: row['delivered'] for row in rows},
        elapsed=elapsed, total=total,
    )
    return {
        'subject_id': int(subject['id']),
        'subject_name': subject['name'],
        'course_code': subject['course_code'] or '',
        'institution_id': int(subject['institution_id'] or 1),
        'elapsed_weeks': elapsed,
        'total_weeks': total,
        'units': lines,
    }


def subject_choices(cursor):
    from core.scope import current_scope

    clause, params = current_scope(cursor).clause('d.institution_id')
    cursor.execute(
        f"""
        SELECT s.id, CONCAT(COALESCE(s.course_code, ''), ' ', s.name) AS name
        FROM subjects s
        LEFT JOIN courses c ON c.id = s.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE {clause}
        ORDER BY s.name
        LIMIT 300
        """,
        params,
    )
    return list(cursor.fetchall())


def report(cursor, filters):
    """(rows, fieldnames, labels, meta) for the syllabus-coverage export. Empty when the capability is off."""
    if not active(cursor):
        return [], list(REPORT_FIELDS), dict(REPORT_LABELS), {'coverage': 'off'}
    if not tables_ready(cursor):
        return [], list(REPORT_FIELDS), dict(REPORT_LABELS), {'coverage': 'tables missing'}
    filters = filters or {}
    rows = _delivered(
        cursor, subject_id=filters.get('subject_id'), department_id=filters.get('department_id'), scoped=True,
    )
    progress, out = {}, []
    today = date.today()
    for row in rows:
        institution_id = int(row['institution_id'] or 1)
        if institution_id not in progress:
            progress[institution_id] = week_progress(cursor, institution_id, today)
        elapsed, total = progress[institution_id]
        line = coverage_lines(
            [{'id': row['unit_id'], 'unit_no': row['unit_no'], 'title': row['title'], 'planned_hours': row['planned_hours']}],
            {row['unit_id']: row['delivered']},
            elapsed=elapsed, total=total,
        )[0]
        out.append({
            'subject_code': row['course_code'] or '',
            'subject_name': row['subject_name'],
            'unit_no': line['unit_no'],
            'unit_title': line['title'],
            'planned_hours': float(line['planned_hours']),
            'delivered_hours': float(line['delivered_hours']),
            'coverage_percent': None if line['percent'] is None else float(line['percent']),
            'expected_hours': None if line['expected_hours'] is None else float(line['expected_hours']),
            'pace': line['pace'],
        })
    return out, list(REPORT_FIELDS), dict(REPORT_LABELS), {'units': len(out), 'subjects': len({row['subject_name'] for row in out})}
