"""Academic terms: which dates are for teaching (docs/ACADEMICS.md).

A term belongs to one institution and one academic year, optionally one semester, and is
`teaching`, `exam`, `break` or `internship`. While capability `academic_terms` is off, or an
institution has saved no terms, every date is treated as today: the generator, close-day and
attendance are unchanged. Once terms exist, a date counts only when a teaching term covers it
and no exam, break or internship term does. Holidays stay in `institution_holidays`; callers
remove them as they already do.

`teaching_weeks` is the derived week list (no view): one row per teaching term and Monday.
"""

from datetime import date, datetime, timedelta

from core import capabilities

CAPABILITY = 'academic_terms'
KINDS = ('teaching', 'exam', 'break', 'internship')
CLOSED = ('exam', 'break', 'internship')
TABLE = 'academic_terms'


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def active(cursor):
    return capabilities.enabled(cursor, CAPABILITY) and _table(cursor)


def table_exists(cursor):
    return _table(cursor)


def _table(cursor):
    cursor.execute(
        "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
        (TABLE,),
    )
    return cursor.fetchone() is not None


# Pure calendar arithmetic ------------------------------------------------------------------------

def kept_dates(dates, terms, *, configured):
    """Dates that may be taught. With nothing configured, every date is kept.

    `terms` are {'start', 'end', 'kind'}. A closed term (exam, break, internship) wins over a
    teaching term on the same date. A date in no term is dropped once the institution has any term.
    """
    if not configured:
        return set(dates)
    closed, teaching = [], []
    for term in terms:
        span = (_as_date(term['start']), _as_date(term['end']))
        (closed if term.get('kind') in CLOSED else teaching).append(span)
    kept = set()
    for day in dates:
        day = _as_date(day)
        if any(start <= day <= end for start, end in closed):
            continue
        if any(start <= day <= end for start, end in teaching):
            kept.add(day)
    return kept


def teaching_day_list(start, end, terms, holidays=()):
    """Teaching dates from start to end, holidays removed. `terms` must be the institution's terms."""
    holidays = {_as_date(day) for day in holidays}
    days, day = [], _as_date(start)
    end = _as_date(end)
    while day <= end:
        days.append(day)
        day += timedelta(days=1)
    return sorted(day for day in kept_dates(days, terms, configured=bool(terms)) if day not in holidays)


def teaching_weeks(terms, holidays=()):
    """[{name, week_start, teaching_days}] for each Monday a teaching term still has a teaching day."""
    holidays = {_as_date(day) for day in holidays}
    rows = []
    for term in terms:
        if term.get('kind') != 'teaching':
            continue
        start, end = _as_date(term['start']), _as_date(term['end'])
        week = start - timedelta(days=start.weekday())
        while week <= end:
            count = 0
            for offset in range(7):
                day = week + timedelta(days=offset)
                if start <= day <= end and day not in holidays and kept_dates([day], terms, configured=True):
                    count += 1
            if count:
                rows.append({'name': term.get('name') or '', 'week_start': week, 'teaching_days': count})
            week += timedelta(days=7)
    return rows


# Stored terms ------------------------------------------------------------------------------------

def _terms_between(cursor, institution_id, start, end):
    cursor.execute(
        f"""
        SELECT id, name, kind, start_date, end_date, semester_id FROM {TABLE}
        WHERE institution_id = %s AND end_date >= %s AND start_date <= %s
        """,
        (int(institution_id or 1), start, end),
    )
    return [
        {'start': _as_date(row['start_date']), 'end': _as_date(row['end_date']), 'kind': row['kind'],
         'name': row['name'], 'id': row['id'], 'semester_id': row.get('semester_id')}
        for row in cursor.fetchall()
    ]


def configured(cursor, institution_id):
    """True when this institution has saved at least one term (and the capability is on)."""
    if not active(cursor):
        return False
    cursor.execute(f'SELECT 1 FROM {TABLE} WHERE institution_id = %s LIMIT 1', (int(institution_id or 1),))
    return cursor.fetchone() is not None


def teaching_dates(cursor, institution_id, dates):
    """The subset of `dates` the generator and the solver may use. All of them when the calendar is idle."""
    dates = [_as_date(day) for day in dates]
    if not dates or not configured(cursor, institution_id):
        return set(dates)
    terms = _terms_between(cursor, institution_id, min(dates), max(dates))
    return kept_dates(dates, terms, configured=True)


def non_teaching_slot_ids(cursor, day):
    """Active timetable ids whose institution has a calendar and `day` is not a teaching day."""
    if not active(cursor):
        return set()
    cursor.execute(
        """
        SELECT t.id, COALESCE(d.institution_id, 1) AS institution_id
        FROM timetable t
        JOIN courses c ON c.id = t.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE COALESCE(t.is_active, 1) = 1
        """
    )
    by_institution = {}
    for row in cursor.fetchall():
        by_institution.setdefault(int(row['institution_id']), []).append(int(row['id']))
    closed = set()
    for institution_id, slot_ids in by_institution.items():
        if _as_date(day) not in teaching_dates(cursor, institution_id, [day]):
            if configured(cursor, institution_id):
                closed.update(slot_ids)
    return closed


def _institution_of_slot(cursor, timetable_id):
    cursor.execute(
        """
        SELECT COALESCE(d.institution_id, 1) AS institution_id
        FROM timetable t
        JOIN courses c ON c.id = t.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE t.id = %s
        """,
        (timetable_id,),
    )
    row = cursor.fetchone()
    return int(row['institution_id']) if row else 1


def refuse_session(cursor, timetable_id, session_date):
    """True when a new or unmarked session must not be held: the date is outside teaching.

    An unmarked row is cancelled with reason `calendar`. A session already held is left alone.
    """
    if not configured(cursor, _institution_of_slot(cursor, timetable_id)):
        return False
    if _as_date(session_date) in teaching_dates(cursor, _institution_of_slot(cursor, timetable_id), [session_date]):
        return False
    cursor.execute(
        'SELECT id, status FROM lecture_sessions WHERE timetable_id = %s AND session_date = %s',
        (timetable_id, session_date),
    )
    row = cursor.fetchone()
    if row and row['status'] == 'held':
        return False
    if row and row['status'] != 'cancelled':
        cursor.execute(
            """
            UPDATE lecture_sessions SET status = 'cancelled', cancel_reason = 'calendar', cancelled_at = CURRENT_TIMESTAMP
            WHERE id = %s AND NOT EXISTS (SELECT 1 FROM attendance a WHERE a.session_id = lecture_sessions.id)
            """,
            (row['id'],),
        )
    return True


def sweep(cursor):
    """Cancel unmarked sessions that fall in an exam, break or internship term. Returns how many."""
    if not active(cursor):
        return 0
    cursor.execute(
        f"""
        UPDATE lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        JOIN courses c ON c.id = t.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        JOIN {TABLE} term ON term.institution_id = COALESCE(d.institution_id, 1)
          AND term.kind IN ('exam', 'break', 'internship')
          AND ls.session_date BETWEEN term.start_date AND term.end_date
        SET ls.status = 'cancelled', ls.cancel_reason = 'calendar', ls.cancelled_at = CURRENT_TIMESTAMP
        WHERE ls.status <> 'cancelled'
          AND NOT EXISTS (SELECT 1 FROM attendance a WHERE a.session_id = ls.id)
        """
    )
    return int(cursor.rowcount or 0)


def period_totals(cursor, institution_id, start, end):
    """scheduled (teaching-day slot occurrences), conducted (held sessions), attended (Present or Late).

    None when the calendar is idle. Holidays are not scheduled.
    """
    if not configured(cursor, institution_id):
        return None
    from academic_rules.holidays import holidays_for_range, is_working_day

    start, end = _as_date(start), _as_date(end)
    terms = _terms_between(cursor, institution_id, start, end)
    holidays = holidays_for_range(cursor, start, end)
    teaching = set(teaching_day_list(start, end, terms))
    cursor.execute(
        """
        SELECT t.id, t.day_of_week, c.program
        FROM timetable t
        JOIN courses c ON c.id = t.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE COALESCE(t.is_active, 1) = 1 AND COALESCE(d.institution_id, 1) = %s
        """,
        (int(institution_id or 1),),
    )
    slots = cursor.fetchall()
    scheduled = 0
    day = start
    while day <= end:
        if day in teaching:
            name = day.strftime('%A')
            for slot in slots:
                if slot['day_of_week'] == name and is_working_day(day, slot.get('program') or 'UG', holidays):
                    scheduled += 1
        day += timedelta(days=1)
    slot_ids = [int(slot['id']) for slot in slots]
    conducted, attended = 0, 0
    if slot_ids:
        marks = ', '.join(['%s'] * len(slot_ids))
        cursor.execute(
            f"SELECT id, session_date, status FROM lecture_sessions WHERE timetable_id IN ({marks}) AND session_date BETWEEN %s AND %s",
            tuple(slot_ids) + (start, end),
        )
        sessions = [row for row in cursor.fetchall() if _as_date(row['session_date']) in teaching]
        conducted = sum(1 for row in sessions if row['status'] == 'held')
        session_ids = [int(row['id']) for row in sessions]
        if session_ids:
            placeholders = ', '.join(['%s'] * len(session_ids))
            cursor.execute(
                f"SELECT COUNT(*) AS n FROM attendance WHERE session_id IN ({placeholders}) AND status IN ('Present', 'Late')",
                tuple(session_ids),
            )
            attended = int((cursor.fetchone() or {}).get('n') or 0)
    return {'scheduled': scheduled, 'conducted': conducted, 'attended': attended, 'from': start.isoformat(), 'to': end.isoformat()}


# Editing -----------------------------------------------------------------------------------------

def clean_term(payload):
    """Validate an API term. Raises ValueError('term_invalid')."""
    if not isinstance(payload, dict):
        raise ValueError('term_invalid')
    name = payload.get('name')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80 or any(ord(ch) < 32 for ch in name):
        raise ValueError('term_invalid')
    kind = payload.get('kind') or 'teaching'
    if kind not in KINDS:
        raise ValueError('term_invalid')
    try:
        start, end = _as_date(payload.get('start_date')), _as_date(payload.get('end_date'))
        year_id = int(payload.get('academic_year_id'))
    except (TypeError, ValueError):
        raise ValueError('term_invalid')
    if start > end or year_id <= 0:
        raise ValueError('term_invalid')
    semester = payload.get('semester_id')
    if semester in (None, '', 0):
        semester = None
    else:
        try:
            semester = int(semester)
        except (TypeError, ValueError):
            raise ValueError('term_invalid')
        if semester <= 0:
            raise ValueError('term_invalid')
    return {'name': name.strip(), 'kind': kind, 'start_date': start, 'end_date': end,
            'academic_year_id': year_id, 'semester_id': semester}


def _overlaps(cursor, institution_id, term, exclude_id=None):
    """Another term of this institution covers the same dates (a whole-year term overlaps every semester)."""
    cursor.execute(
        f"""
        SELECT id, semester_id FROM {TABLE}
        WHERE institution_id = %s AND id <> %s AND start_date <= %s AND end_date >= %s
        """,
        (int(institution_id or 1), int(exclude_id or 0), term['end_date'], term['start_date']),
    )
    for row in cursor.fetchall():
        other = row.get('semester_id')
        if term['semester_id'] is None or other is None or int(other) == term['semester_id']:
            return True
    return False


def save_term(cursor, institution_id, term, term_id=None):
    """Insert or update. Raises ValueError('term_overlap') or RuntimeError('terms_table_missing')."""
    if not _table(cursor):
        raise RuntimeError('terms_table_missing')
    cursor.execute('SELECT id, start_date, end_date FROM academic_years WHERE id = %s', (term['academic_year_id'],))
    year = cursor.fetchone()
    if not year or not (_as_date(year['start_date']) <= term['start_date'] and term['end_date'] <= _as_date(year['end_date'])):
        raise ValueError('term_invalid')
    if term['semester_id'] is not None:
        cursor.execute('SELECT academic_year_id FROM semesters WHERE id = %s', (term['semester_id'],))
        semester = cursor.fetchone()
        if not semester or int(semester['academic_year_id']) != term['academic_year_id']:
            raise ValueError('term_invalid')
    if _overlaps(cursor, institution_id, term, term_id):
        raise ValueError('term_overlap')
    values = (term['name'], term['kind'], term['start_date'], term['end_date'], term['academic_year_id'], term['semester_id'])
    if term_id:
        cursor.execute(
            f"""
            UPDATE {TABLE}
            SET name = %s, kind = %s, start_date = %s, end_date = %s, academic_year_id = %s, semester_id = %s
            WHERE id = %s AND institution_id = %s
            """,
            values + (int(term_id), int(institution_id or 1)),
        )
        if cursor.rowcount == 0:
            raise ValueError('term_not_found')
        return int(term_id)
    cursor.execute(
        f"""
        INSERT INTO {TABLE} (institution_id, name, kind, start_date, end_date, academic_year_id, semester_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (int(institution_id or 1),) + values,
    )
    return int(cursor.lastrowid)


def delete_term(cursor, institution_id, term_id):
    cursor.execute(f'DELETE FROM {TABLE} WHERE id = %s AND institution_id = %s', (int(term_id), int(institution_id or 1)))
    return cursor.rowcount > 0


def list_terms(cursor, institution_id=None):
    clause, params = '', ()
    if institution_id:
        clause, params = 'WHERE t.institution_id = %s', (int(institution_id),)
    cursor.execute(
        f"""
        SELECT t.id, t.institution_id, t.name, t.kind, t.start_date, t.end_date, t.academic_year_id, t.semester_id,
               y.name AS year_name, s.semester_name
        FROM {TABLE} t
        JOIN academic_years y ON y.id = t.academic_year_id
        LEFT JOIN semesters s ON s.id = t.semester_id
        {clause}
        ORDER BY t.start_date, t.name
        """,
        params,
    )
    return cursor.fetchall()
