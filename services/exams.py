"""Exam timetable, seating and invigilation (docs/ACADEMICS.md).

Capability `exams`. Off: nothing is read or written, and the booking ledger
is unchanged. On, a solved timetable stores one session per paper, seats
students, and assigns invigilators. While `bookings` is also on, those rooms
are busy on the shared ledger for that date and time.

Regular teaching on an exam term is suspended by the academic calendar
(`services/academic_calendar.py`), not by this module.
"""

from datetime import date, datetime, time, timedelta

from academic_rules.clashes import times_overlap
from core import capabilities
from services.timetable.exam_solver import ExamProblem, Paper, Room, Slot, SolverUnavailable, solve, usable_seats

CAPABILITY = 'exams'
KINDS = ('internal', 'university', 'practical')
ROLES = ('chief', 'invigilator')
_MAX_PAPERS = 40
_MAX_ROOMS = 25
_MAX_DATES = 12
_MAX_SLOTS = 24
_DEFAULT_SLOTS = (('09:30', '12:30'), ('14:00', '17:00'))

MESSAGES = {
    'exam_unavailable': 'The exam tables are missing; apply the database migrations first.',
    'exam_invalid': 'Check the exam name, dates, subjects and rooms, then try again.',
    'exam_not_found': 'That exam was not found.',
    'exam_no_students': 'A paper has no students. Check the cohort and, for an elective, the subject selections.',
    'exam_no_room': 'Choose at least one room with seats.',
    'exam_no_invigilator': 'There is no active faculty member who can invigilate.',
    'exam_unsolved': 'No exam timetable fits those rooms, the seating gap and invigilator availability.',
    'subject_not_found': 'That subject was not found.',
    'capability_off': 'This feature is switched off for your institution.',
}

_REASONS = {
    'CAPACITY': 'Not enough seats for a paper once the seating gap is applied.',
    'NO_INVIGILATOR': MESSAGES['exam_no_invigilator'],
    'EMPTY': 'Add at least one subject and one date.',
    'INFEASIBLE': MESSAGES['exam_unsolved'],
    'UNKNOWN': 'The solver did not finish in time. Use fewer papers or more rooms.',
}


class ExamError(Exception):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or MESSAGES.get(code, code))


def active(cursor):
    return capabilities.enabled(cursor, CAPABILITY) and tables_ready(cursor)


def tables_ready(cursor):
    return capabilities.table_exists(cursor, 'exams') and capabilities.table_exists(cursor, 'exam_sessions')


def _as_time(value):
    if isinstance(value, time):
        return value.replace(microsecond=0)
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        return time(hour=(seconds // 3600) % 24, minute=(seconds % 3600) // 60)
    if isinstance(value, str):
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
    raise ExamError('exam_invalid')


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ExamError('exam_invalid')


def hhmm(value):
    return _as_time(value).strftime('%H:%M')


def _scope():
    from core.scope import current_scope
    return current_scope


def _id(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExamError('exam_invalid')
    if value < 1:
        raise ExamError('exam_invalid')
    return value


# Ledger -------------------------------------------------------------------------------------

def occupying(cursor, dates, room_ids=None):
    """Exam rows that occupy a room on one of `dates`. Empty when exams are off."""
    if not dates or not active(cursor):
        return []
    days = tuple(dates)
    params = list(days)
    room_sql = ''
    if room_ids is not None:
        ids = sorted({int(room_id) for room_id in room_ids})
        if not ids:
            return []
        room_sql = f" AND esr.room_id IN ({', '.join(['%s'] * len(ids))})"
        params.extend(ids)
    cursor.execute(
        f"""
        SELECT esr.room_id, e.name AS title, es.exam_date, es.start_time, es.end_time
        FROM exam_session_rooms esr
        JOIN exam_sessions es ON es.id = esr.exam_session_id
        JOIN exams e ON e.id = es.exam_id
        WHERE es.exam_date IN ({', '.join(['%s'] * len(days))}){room_sql}
        """,
        tuple(params),
    )
    return cursor.fetchall()


def hold(cursor, room_id, day, start, end, booking_date=None, repeat_until=None):
    """The exam session that occupies this room at that time, or None.

    A dated booking meets the exam on that date. A weekly booking meets a future exam on that
    weekday inside its repeat window (open-ended when `repeat_until` is missing).
    """
    if not active(cursor):
        return None
    start, end = _as_time(start), _as_time(end)
    if booking_date:
        rows = occupying(cursor, (_as_date(booking_date),), (room_id,))
    else:
        today = date.today()
        until = _as_date(repeat_until) if repeat_until else None
        cursor.execute(
            """
            SELECT esr.room_id, e.name AS title, es.exam_date, es.start_time, es.end_time
            FROM exam_session_rooms esr
            JOIN exam_sessions es ON es.id = esr.exam_session_id
            JOIN exams e ON e.id = es.exam_id
            WHERE esr.room_id = %s AND DAYNAME(es.exam_date) = %s AND es.exam_date >= %s
            ORDER BY es.exam_date
            LIMIT 30
            """,
            (room_id, day, today),
        )
        rows = [
            row for row in cursor.fetchall()
            if until is None or _as_date(row['exam_date']) <= until
        ]
    for row in rows:
        if times_overlap(_as_time(row['start_time']), _as_time(row['end_time']), start, end):
            return row
    return None


# Reads --------------------------------------------------------------------------------------

def _allows(cursor, institution_id):
    if institution_id is None:
        return True
    return _scope()(cursor).allows(institution_id)


def list_exams(cursor):
    if not tables_ready(cursor):
        return []
    cursor.execute(
        """
        SELECT e.id, e.term_id, e.name, e.kind, e.seating_gap, e.students_per_room, t.name AS term_name,
               t.institution_id, t.start_date, t.end_date
        FROM exams e
        LEFT JOIN academic_terms t ON t.id = e.term_id
        ORDER BY e.id DESC
        """
    )
    return [row for row in cursor.fetchall() if _allows(cursor, row.get('institution_id'))]


def load_exam(cursor, exam_id):
    cursor.execute(
        """
        SELECT e.id, e.term_id, e.name, e.kind, e.seating_gap, e.students_per_room, t.name AS term_name,
               t.institution_id, t.start_date, t.end_date, t.kind AS term_kind
        FROM exams e
        LEFT JOIN academic_terms t ON t.id = e.term_id
        WHERE e.id = %s
        """,
        (exam_id,),
    )
    row = cursor.fetchone()
    if row is None or not _allows(cursor, row.get('institution_id')):
        return None
    return row


def subject_choices(cursor):
    clause, params = _scope()(cursor).clause('d.institution_id')
    cursor.execute(
        f"""
        SELECT s.id, s.name, s.course_code, s.class_id, s.is_elective, s.course_type, cl.name AS class_name
        FROM subjects s
        JOIN courses c ON c.id = s.course_id
        JOIN departments d ON d.id = c.department_id
        LEFT JOIN classes cl ON cl.id = s.class_id
        WHERE {clause}
        ORDER BY s.name, s.course_code
        """,
        tuple(params),
    )
    return cursor.fetchall()


def room_choices(cursor):
    clause, params = _scope()(cursor).clause('r.institution_id')
    cursor.execute(
        f"""
        SELECT r.id, r.room_number, r.room_type, r.capacity
        FROM rooms r
        WHERE {clause} AND COALESCE(r.is_available, 1) = 1 AND COALESCE(r.capacity, 0) > 0
        ORDER BY r.room_number
        """,
        tuple(params),
    )
    return cursor.fetchall()


def term_choices(cursor):
    if not capabilities.table_exists(cursor, 'academic_terms'):
        return []
    clause, params = _scope()(cursor).clause('t.institution_id')
    cursor.execute(
        f"""
        SELECT t.id, t.name, t.start_date, t.end_date, t.kind
        FROM academic_terms t
        WHERE {clause} AND t.kind = 'exam'
        ORDER BY t.start_date, t.name
        """,
        tuple(params),
    )
    return cursor.fetchall()


def sessions_for(cursor, exam_id):
    cursor.execute(
        """
        SELECT es.id, es.subject_id, s.name AS subject_name, s.course_code, es.exam_date, es.start_time, es.end_time
        FROM exam_sessions es
        JOIN subjects s ON s.id = es.subject_id
        WHERE es.exam_id = %s
        ORDER BY es.exam_date, es.start_time, s.name
        """,
        (exam_id,),
    )
    sessions = cursor.fetchall()
    if not sessions:
        return []
    ids = [int(row['id']) for row in sessions]
    marks = ', '.join(['%s'] * len(ids))
    cursor.execute(
        f"""
        SELECT c.exam_session_id, c.class_id, c.division_id, cl.name AS class_name, dv.name AS division_name
        FROM exam_session_cohorts c
        JOIN classes cl ON cl.id = c.class_id
        LEFT JOIN divisions dv ON dv.id = c.division_id
        WHERE c.exam_session_id IN ({marks})
        ORDER BY cl.name, dv.name
        """,
        tuple(ids),
    )
    cohorts = {}
    for row in cursor.fetchall():
        cohorts.setdefault(int(row['exam_session_id']), []).append(row)
    cursor.execute(
        f"""
        SELECT d.exam_session_id, d.room_id, d.faculty_id, d.role, r.room_number, COALESCE(f.name, '') AS faculty_name
        FROM invigilation_duties d
        JOIN rooms r ON r.id = d.room_id
        LEFT JOIN faculty f ON f.user_id = d.faculty_id
        WHERE d.exam_session_id IN ({marks})
        ORDER BY r.room_number
        """,
        tuple(ids),
    )
    duties = {}
    for row in cursor.fetchall():
        duties.setdefault(int(row['exam_session_id']), []).append(row)
    cursor.execute(
        f"""
        SELECT exam_session_id, room_id, COUNT(*) AS seats
        FROM exam_seats
        WHERE exam_session_id IN ({marks})
        GROUP BY exam_session_id, room_id
        """,
        tuple(ids),
    )
    counts = {(int(row['exam_session_id']), int(row['room_id'])): int(row['seats']) for row in cursor.fetchall()}
    packed = []
    for row in sessions:
        session_id = int(row['id'])
        row['cohorts'] = cohorts.get(session_id, [])
        row['rooms'] = []
        for duty in duties.get(session_id, []):
            row['rooms'].append({**duty, 'seats': counts.get((session_id, int(duty['room_id'])), 0)})
        packed.append(row)
    return packed


def teacher_duties(cursor, user_id):
    clause, params = _scope()(cursor).clause('dpt.institution_id')
    cursor.execute(
        f"""
        SELECT e.name AS exam_name, es.exam_date, es.start_time, es.end_time, s.name AS subject_name,
               s.course_code, r.room_number, d.role
        FROM invigilation_duties d
        JOIN exam_sessions es ON es.id = d.exam_session_id
        JOIN exams e ON e.id = es.exam_id
        JOIN subjects s ON s.id = es.subject_id
        JOIN courses c ON c.id = s.course_id
        JOIN departments dpt ON dpt.id = c.department_id
        JOIN rooms r ON r.id = d.room_id
        WHERE d.faculty_id = %s AND {clause}
        ORDER BY es.exam_date, es.start_time, r.room_number
        """,
        (user_id, *params),
    )
    return cursor.fetchall()


def seating_rows(cursor, exam_id):
    cursor.execute(
        """
        SELECT r.room_number, st.seat_no, COALESCE(stu.roll_number, '') AS roll_number, stu.name AS student_name,
               s.course_code, s.name AS subject_name, es.exam_date, es.start_time, es.end_time
        FROM exam_seats st
        JOIN exam_sessions es ON es.id = st.exam_session_id
        JOIN exams e ON e.id = es.exam_id
        JOIN subjects s ON s.id = es.subject_id
        JOIN rooms r ON r.id = st.room_id
        JOIN students stu ON stu.id = st.student_id
        WHERE e.id = %s
        ORDER BY es.exam_date, es.start_time, r.room_number, st.seat_no
        """,
        (exam_id,),
    )
    return cursor.fetchall()


def hall_ticket_rows(cursor, exam_id):
    cursor.execute(
        """
        SELECT COALESCE(stu.roll_number, '') AS roll_number, stu.name AS student_name, s.course_code, s.name AS subject_name,
               es.exam_date, es.start_time, es.end_time, r.room_number, st.seat_no
        FROM exam_seats st
        JOIN exam_sessions es ON es.id = st.exam_session_id
        JOIN exams e ON e.id = es.exam_id
        JOIN subjects s ON s.id = es.subject_id
        JOIN rooms r ON r.id = st.room_id
        JOIN students stu ON stu.id = st.student_id
        WHERE e.id = %s
        ORDER BY stu.roll_number, stu.name, es.exam_date, es.start_time
        """,
        (exam_id,),
    )
    return cursor.fetchall()


# Writes -------------------------------------------------------------------------------------

def create_exam(cursor, *, name, kind, term_id, created_by):
    if kind not in KINDS:
        raise ExamError('exam_invalid')
    name = str(name or '').strip()
    if not name or len(name) > 80:
        raise ExamError('exam_invalid')
    if term_id is not None:
        term = _term(cursor, term_id)
        if term is None or term['kind'] != 'exam':
            raise ExamError('exam_invalid')
    cursor.execute(
        """
        INSERT INTO exams (term_id, name, kind, created_by)
        VALUES (%s, %s, %s, %s)
        """,
        (term_id, name, kind, created_by),
    )
    return cursor.lastrowid


def delete_exam(cursor, exam_id):
    if load_exam(cursor, exam_id) is None:
        raise ExamError('exam_not_found')
    cursor.execute('DELETE FROM exams WHERE id = %s', (exam_id,))


def solve_into(cursor, exam_id, payload):
    """Replace this exam's sessions with a solved timetable. Returns a summary dict."""
    exam = load_exam(cursor, exam_id)
    if exam is None:
        raise ExamError('exam_not_found')
    gap = _gap(payload.get('seating_gap', exam.get('seating_gap') or 0))
    per_room = _per_room(payload.get('students_per_room', exam.get('students_per_room')))
    built = _papers(cursor, payload)
    dates = _dates(payload.get('dates'), exam)
    windows = _windows(payload.get('slots'))
    slots = [
        Slot(index=index, on=day, start=start, end=end)
        for index, (day, start, end) in enumerate((day, start, end) for day in dates for start, end in windows)
    ]
    if len(slots) > _MAX_SLOTS:
        raise ExamError('exam_invalid')
    rooms = _rooms(cursor, payload.get('room_ids'))
    people = _invigilators(cursor)
    if not people:
        raise ExamError('exam_no_invigilator')
    problem = ExamProblem(
        papers=[Paper(key=paper['key'], name=paper['name'], students=frozenset(student['id'] for student in paper['students'])) for paper in built],
        slots=slots,
        rooms=[Room(id=int(room['id']), capacity=int(room['capacity'])) for room in rooms],
        invigilators=[int(person['id']) for person in people],
        seating_gap=gap,
        students_per_room=per_room,
        unavailable=_unavailable(cursor, [int(person['id']) for person in people], slots),
    )
    try:
        sittings, status = solve(problem)
    except SolverUnavailable as exc:
        raise ExamError('exam_unsolved', str(exc)) from exc
    if not sittings:
        raise ExamError('exam_unsolved', _REASONS.get(status, MESSAGES['exam_unsolved']))
    _replace(cursor, exam_id, built, slots, sittings, rooms, gap, per_room)
    return {'status': status, 'sessions': len(sittings), 'dates': [day.isoformat() for day in dates]}


def _gap(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 3:
        raise ExamError('exam_invalid')
    return value


def _per_room(value):
    if value in (None, '', 0):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 500:
        raise ExamError('exam_invalid')
    return value


def _term(cursor, term_id):
    if not capabilities.table_exists(cursor, 'academic_terms'):
        return None
    cursor.execute(
        'SELECT id, name, kind, institution_id, start_date, end_date FROM academic_terms WHERE id = %s',
        (term_id,),
    )
    row = cursor.fetchone()
    if row is None or not _allows(cursor, row.get('institution_id')):
        return None
    return row


def _subject(cursor, subject_id):
    cursor.execute(
        """
        SELECT s.id, s.name, s.course_code, s.course_id, s.class_id, s.is_elective, s.course_type, d.institution_id
        FROM subjects s
        JOIN courses c ON c.id = s.course_id
        JOIN departments d ON d.id = c.department_id
        WHERE s.id = %s
        """,
        (subject_id,),
    )
    row = cursor.fetchone()
    if row is None or not _allows(cursor, row.get('institution_id')):
        return None
    return row


def _elective(row):
    if row.get('is_elective'):
        return True
    return str(row.get('course_type') or '').startswith('Elective')


def _papers(cursor, payload):
    specs = _specs(payload)
    if not specs or len(specs) > _MAX_PAPERS:
        raise ExamError('exam_invalid')
    built = []
    for index, spec in enumerate(specs):
        subject = _subject(cursor, _id(spec['subject_id']))
        if subject is None:
            raise ExamError('subject_not_found')
        cohorts = spec.get('cohorts') or [{'class_id': subject.get('class_id'), 'division_id': None}]
        students = []
        seen = set()
        stored = []
        for cohort in cohorts:
            if not isinstance(cohort, dict):
                raise ExamError('exam_invalid')
            class_id = cohort.get('class_id')
            division_id = cohort.get('division_id')
            class_id = None if class_id in (None, '', 0) else _id(class_id)
            division_id = None if division_id in (None, '', 0) else _id(division_id)
            if class_id is not None:
                stored.append({'class_id': class_id, 'division_id': division_id})
            for student in _roster(cursor, subject, class_id, division_id):
                if student['id'] not in seen:
                    seen.add(student['id'])
                    students.append(student)
        if not students:
            raise ExamError('exam_no_students')
        students.sort(key=lambda row: (str(row.get('roll_number') or ''), row['name'], row['id']))
        built.append({
            'key': index + 1,
            'subject_id': int(subject['id']),
            'name': subject['name'],
            'code': subject.get('course_code') or '',
            'elective': _elective(subject),
            'cohorts': stored,
            'students': students,
        })
    return _merge_shared_electives(built)


def _specs(payload):
    papers = payload.get('papers')
    if papers is not None:
        if not isinstance(papers, list):
            raise ExamError('exam_invalid')
        return papers
    raw = payload.get('subject_ids')
    if not isinstance(raw, list):
        raise ExamError('exam_invalid')
    return [{'subject_id': subject_id} for subject_id in raw]


def _merge_shared_electives(built):
    """One elective subject sits once, even when several cohort rows selected it."""
    merged = []
    by_subject = {}
    key = 1
    for paper in built:
        if not paper['elective']:
            paper['key'] = key
            key += 1
            merged.append(paper)
            continue
        current = by_subject.get(paper['subject_id'])
        if current is None:
            paper['key'] = key
            key += 1
            by_subject[paper['subject_id']] = paper
            merged.append(paper)
            continue
        seen = {student['id'] for student in current['students']}
        for student in paper['students']:
            if student['id'] not in seen:
                current['students'].append(student)
                seen.add(student['id'])
        known = {(row['class_id'], row['division_id']) for row in current['cohorts']}
        for cohort in paper['cohorts']:
            token = (cohort['class_id'], cohort['division_id'])
            if token not in known:
                current['cohorts'].append(cohort)
    return merged


def _roster(cursor, subject, class_id, division_id):
    elective = _elective(subject)
    cursor.execute(
        """
        SELECT s.id, s.name, COALESCE(s.roll_number, '') AS roll_number
        FROM students s
        WHERE s.course_id = %s AND COALESCE(s.is_active, 1) = 1
          AND (%s IS NULL OR s.class_id = %s)
          AND (%s IS NULL OR s.division_id = %s)
          AND (%s = 0 OR s.id IN (
                SELECT student_id FROM student_subject_selections
                WHERE subject_id = %s AND (status IS NULL OR status <> 'Withdrawn')
          ))
        """,
        (subject['course_id'], class_id, class_id, division_id, division_id, 1 if elective else 0, subject['id']),
    )
    return cursor.fetchall()


def _dates(raw, exam):
    if raw in (None, ''):
        if not exam.get('start_date') or not exam.get('end_date'):
            raise ExamError('exam_invalid')
        start, end = _as_date(exam['start_date']), _as_date(exam['end_date'])
        days = []
        cursor_day = start
        while cursor_day <= end and len(days) < _MAX_DATES:
            if cursor_day.weekday() < 6:
                days.append(cursor_day)
            cursor_day += timedelta(days=1)
        if not days:
            raise ExamError('exam_invalid')
        return days
    if not isinstance(raw, list) or not raw or len(raw) > _MAX_DATES:
        raise ExamError('exam_invalid')
    return [_as_date(value) for value in raw]


def _windows(raw):
    if raw in (None, ''):
        raw = [{'start': start, 'end': end} for start, end in _DEFAULT_SLOTS]
    if not isinstance(raw, list) or not raw or len(raw) > 4:
        raise ExamError('exam_invalid')
    windows = []
    for item in raw:
        if not isinstance(item, dict):
            raise ExamError('exam_invalid')
        start, end = _as_time(item.get('start')), _as_time(item.get('end'))
        if start >= end:
            raise ExamError('exam_invalid')
        windows.append((start, end))
    return windows


def _rooms(cursor, raw):
    choices = {int(row['id']): row for row in room_choices(cursor)}
    if raw in (None, ''):
        picked = list(choices.values())[:_MAX_ROOMS]
    else:
        if not isinstance(raw, list) or not raw:
            raise ExamError('exam_invalid')
        picked = []
        for room_id in raw:
            row = choices.get(_id(room_id))
            if row is None:
                raise ExamError('exam_invalid')
            picked.append(row)
    if not picked or len(picked) > _MAX_ROOMS:
        raise ExamError('exam_no_room')
    return picked


def _invigilators(cursor):
    clause, params = _scope()(cursor).clause('d.institution_id')
    cursor.execute(
        f"""
        SELECT f.user_id AS id
        FROM faculty f
        JOIN users u ON u.id = f.user_id
        JOIN departments d ON d.id = u.department_id
        WHERE COALESCE(f.is_active, 1) = 1 AND u.status = 'active' AND {clause}
        ORDER BY f.user_id
        """,
        tuple(params),
    )
    return cursor.fetchall()


def _unavailable(cursor, faculty_ids, slots):
    if not faculty_ids or not slots:
        return {}
    marks = ', '.join(['%s'] * len(faculty_ids))
    first, last = min(slot.on for slot in slots), max(slot.on for slot in slots)
    cursor.execute(
        f"""
        SELECT faculty_id, absence_date FROM faculty_absences
        WHERE faculty_id IN ({marks}) AND absence_date BETWEEN %s AND %s
        """,
        tuple(faculty_ids) + (first, last),
    )
    absent = {(int(row['faculty_id']), _as_date(row['absence_date'])) for row in cursor.fetchall()}
    cursor.execute(
        f"""
        SELECT faculty_id, day_of_week, is_available, start_time, end_time
        FROM faculty_availability
        WHERE faculty_id IN ({marks})
        """,
        tuple(faculty_ids),
    )
    windows = {}
    for row in cursor.fetchall():
        windows.setdefault(int(row['faculty_id']), {}).setdefault(int(row['day_of_week']), []).append(row)
    blocked = {faculty_id: set() for faculty_id in faculty_ids}
    for slot in slots:
        weekday = slot.on.weekday() + 1
        for faculty_id in faculty_ids:
            if (faculty_id, slot.on) in absent or not _covers(windows.get(faculty_id, {}).get(weekday, []), slot):
                blocked[faculty_id].add(slot.index)
    return blocked


def _covers(windows, slot):
    """True when this faculty may invigilate the slot.

    No rows means available. An unavailable row that covers the slot blocks it. Available rows
    with times must contain the slot; an available row with no times does not constrain.
    """
    if not windows:
        return True
    constrained = False
    for row in windows:
        start = _as_time(row['start_time']) if row.get('start_time') else None
        end = _as_time(row['end_time']) if row.get('end_time') else None
        if not row.get('is_available'):
            if start is None or end is None or times_overlap(start, end, slot.start, slot.end):
                return False
            continue
        if start and end:
            constrained = True
            if start <= slot.start and end >= slot.end:
                return True
    return not constrained


def _replace(cursor, exam_id, papers, slots, sittings, rooms, gap, per_room):
    by_key = {paper['key']: paper for paper in papers}
    by_slot = {slot.index: slot for slot in slots}
    capacity = {int(room['id']): int(room['capacity']) for room in rooms}
    cursor.execute(
        'UPDATE exams SET seating_gap = %s, students_per_room = %s WHERE id = %s',
        (gap, per_room, exam_id),
    )
    cursor.execute('DELETE FROM exam_sessions WHERE exam_id = %s', (exam_id,))
    for sitting in sittings:
        paper = by_key[sitting.paper_key]
        slot = by_slot[sitting.slot]
        cursor.execute(
            """
            INSERT INTO exam_sessions (exam_id, subject_id, exam_date, start_time, end_time)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (exam_id, paper['subject_id'], slot.on, slot.start, slot.end),
        )
        session_id = cursor.lastrowid
        for cohort in paper['cohorts']:
            cursor.execute(
                'INSERT INTO exam_session_cohorts (exam_session_id, class_id, division_id) VALUES (%s, %s, %s)',
                (session_id, cohort['class_id'], cohort['division_id']),
            )
        offset = 0
        students = paper['students']
        for index, (room_id, faculty_id) in enumerate(sitting.rooms):
            cap = usable_seats(capacity[room_id], gap, per_room)
            chunk = students[offset:offset + cap]
            offset += len(chunk)
            cursor.execute(
                'INSERT INTO exam_session_rooms (exam_session_id, room_id) VALUES (%s, %s)',
                (session_id, room_id),
            )
            cursor.execute(
                """
                INSERT INTO invigilation_duties (exam_session_id, faculty_id, room_id, role)
                VALUES (%s, %s, %s, %s)
                """,
                (session_id, faculty_id, room_id, 'chief' if index == 0 else 'invigilator'),
            )
            for seat_no, student in enumerate(chunk, start=1):
                cursor.execute(
                    """
                    INSERT INTO exam_seats (exam_session_id, room_id, student_id, seat_no)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (session_id, room_id, student['id'], seat_no),
                )
        if offset < len(students):
            raise ExamError('exam_unsolved', MESSAGES['exam_unsolved'])
