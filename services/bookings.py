"""Room bookings on the timetable's clash ledger (docs/TIMETABLE.md, "Room bookings").

A booking reserves one room either on one date (`booking_date`) or every week on one weekday
(`day_of_week`, optionally until `repeat_until`). Only `approved` bookings block a room:

* `room_usage_for_week` gives the generator and the joint solver the approved bookings that fall
  in the week they schedule, in the same shape as existing timetable rows, plus exam sessions
  when capability `exams` is on;
* `booked_room` lets `check_slot` refuse a manual weekly slot that meets a weekly booking;
* `create` and `decide` refuse a booking that meets a live timetable slot (`booking_room_busy`)
  or another approved booking (`booking_room_booked`) and offer free rooms of the same type.

Everything here is a no-op when capability `bookings` is off or revision 0018 is not applied
(`active`). Nothing is read from or written to any table when inactive.
"""

from datetime import date, datetime, time, timedelta

from academic_rules.clashes import times_overlap
from core import capabilities
from data_access.institutions import candidate_rooms_clause

CAPABILITY = 'bookings'
TABLE = 'bookings'
KINDS = ('event', 'exam', 'maintenance', 'external')
STATUSES = ('requested', 'approved', 'rejected', 'cancelled')
DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
_SELECT = """
    SELECT b.id, b.institution_id, b.room_id, b.title, b.kind, b.booking_date, b.day_of_week, b.repeat_until,
           b.start_time, b.end_time, b.notes, b.status, b.booked_by, b.decided_by, b.decided_at, b.decision_note, b.created_at,
           r.room_number, r.room_type, r.capacity AS room_capacity, r.institution_id AS room_institution_id,
           ri.short_name AS room_institution_short_name, i.short_name AS institution_short_name,
           bu.username AS booked_by_name, du.username AS decided_by_name
    FROM bookings b
    JOIN rooms r ON r.id = b.room_id
    LEFT JOIN institutions ri ON ri.id = r.institution_id
    LEFT JOIN institutions i ON i.id = b.institution_id
    LEFT JOIN users bu ON bu.id = b.booked_by
    LEFT JOIN users du ON du.id = b.decided_by
"""


class BookingError(ValueError):
    """The booking breaks a rule; `code` names it, `alternatives` lists free rooms of the same type (may be empty)."""

    def __init__(self, code, message, alternatives=()):
        super().__init__(message)
        self.code = code
        self.alternatives = list(alternatives)


# Availability -------------------------------------------------------------------------------

def table_exists(cursor):
    cursor.execute(
        'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1', (TABLE,),
    )
    return cursor.fetchone() is not None


def active(cursor):
    """Capability on and revision 0018 applied."""
    return capabilities.enabled(cursor, CAPABILITY) and table_exists(cursor)


def requires_approval(cursor):
    return bool(capabilities.settings(cursor, CAPABILITY).get('requires_approval', True))


def as_time(value):
    if isinstance(value, time):
        return value
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        return time(hour=(seconds // 3600) % 24, minute=(seconds % 3600) // 60)
    if isinstance(value, str):
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
    if hasattr(value, 'hour'):
        return time(value.hour, value.minute)
    raise ValueError('time')


def hhmm(value):
    return as_time(value).strftime('%H:%M')


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def applies_on(booking, on_date):
    """Whether an approved booking row occupies its room on `on_date` (one-off date or weekly rule)."""
    if booking.get('booking_date'):
        return _as_date(booking['booking_date']) == on_date
    if booking.get('day_of_week') != on_date.strftime('%A'):
        return False
    until = booking.get('repeat_until')
    return until is None or _as_date(until) >= on_date


def _approved_rows(cursor, *, room_ids=None, days=(), dates=()):
    """Approved bookings that are weekly on one of `days` or dated on one of `dates`."""
    clauses, params = [], []
    if days:
        clauses.append(f"b.day_of_week IN ({', '.join(['%s'] * len(days))})")
        params.extend(days)
    if dates:
        clauses.append(f"b.booking_date IN ({', '.join(['%s'] * len(dates))})")
        params.extend(dates)
    if not clauses:
        return []
    where = f"b.status = 'approved' AND ({' OR '.join(clauses)})"
    if room_ids is not None:
        ids = sorted({int(room_id) for room_id in room_ids})
        if not ids:
            return []
        where += f" AND b.room_id IN ({', '.join(['%s'] * len(ids))})"
        params.extend(ids)
    cursor.execute(
        f'SELECT b.id, b.room_id, b.title, b.kind, b.booking_date, b.day_of_week, b.repeat_until, b.start_time, b.end_time '
        f'FROM bookings b WHERE {where}',
        tuple(params),
    )
    return cursor.fetchall()


def room_usage_for_week(cursor, week_dates, room_ids=None):
    """{day name: {room id: [(start, end)]}} of approved bookings that fall on the given dates.

    `week_dates` is {day name: date} (or an iterable of (day, date) pairs) for the week being
    scheduled. Weekly bookings apply when their weekday is in the week and `repeat_until` has not
    passed; dated bookings when the date is in the week. Empty when bookings are inactive.
    """
    pairs = list(week_dates.items()) if isinstance(week_dates, dict) else list(week_dates)
    if not pairs or not active(cursor):
        return {}
    by_day = {day: _as_date(day_date) for day, day_date in pairs}
    usage = {}
    _merge_exam_usage(cursor, by_day, room_ids, usage)
    for row in _approved_rows(cursor, room_ids=room_ids, days=tuple(by_day), dates=tuple(by_day.values())):
        for day, day_date in by_day.items():
            if applies_on(row, day_date):
                usage.setdefault(day, {}).setdefault(int(row['room_id']), []).append((as_time(row['start_time']), as_time(row['end_time'])))
    return usage


def booked_room(cursor, room_id, day, start_time, end_time, on_date=None):
    """The approved booking that occupies `room_id` at that weekly time, or None.

    Without `on_date` only weekly bookings count (a weekly timetable slot meets every week); with
    one, dated bookings on that date count too.
    """
    if not active(cursor):
        return None
    start, end = as_time(start_time), as_time(end_time)
    on_date = _as_date(on_date) if on_date else None
    today = date.today()
    for row in _approved_rows(cursor, room_ids=(room_id,), days=(day,), dates=(on_date,) if on_date else ()):
        if not times_overlap(as_time(row['start_time']), as_time(row['end_time']), start, end):
            continue
        if on_date:
            if not applies_on(row, on_date):
                continue
        elif row.get('booking_date') or (row.get('repeat_until') and _as_date(row['repeat_until']) < today):
            continue   # a weekly slot meets only weekly bookings still in force
        return row
    return None


def timetable_conflicts(cursor, room_id, day, start_time, end_time):
    """Live timetable slots that use the room at that weekly time (the ledger the booking must respect)."""
    cursor.execute(
        """
        SELECT t.id, t.start_time, t.end_time, s.name AS subject_name,
               COALESCE(c.name, '') AS course_name, COALESCE(cl.name, '') AS class_name, COALESCE(d.name, '') AS division_name
        FROM timetable t
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN courses c ON c.id = t.course_id
        LEFT JOIN classes cl ON cl.id = t.class_id
        LEFT JOIN divisions d ON d.id = t.division_id
        WHERE t.room_id = %s AND t.day_of_week = %s AND COALESCE(t.is_active, 1) = 1
          AND NOT (t.end_time <= %s OR t.start_time >= %s)
        ORDER BY t.start_time
        LIMIT 20
        """,
        (room_id, day, start_time, end_time),
    )
    return cursor.fetchall()


def booking_conflicts(cursor, room_id, *, day, start_time, end_time, booking_date=None, repeat_until=None, exclude_id=None):
    """Approved bookings the proposed booking would overlap.

    A dated booking meets weekly bookings on its weekday (within their window) and dated bookings
    on its date. A weekly booking meets other weekly bookings on that weekday whose windows
    overlap, and dated bookings on that weekday within its own window.
    """
    start, end = as_time(start_time), as_time(end_time)
    cursor.execute(
        """
        SELECT b.id, b.title, b.kind, b.booking_date, b.day_of_week, b.repeat_until, b.start_time, b.end_time
        FROM bookings b
        WHERE b.room_id = %s AND b.status = 'approved' AND (b.day_of_week = %s OR DAYNAME(b.booking_date) = %s)
        """,
        (room_id, day, day),
    )
    found = []
    for row in cursor.fetchall():
        if exclude_id is not None and int(row['id']) == int(exclude_id):
            continue
        if not times_overlap(as_time(row['start_time']), as_time(row['end_time']), start, end):
            continue
        if booking_date is not None:
            if not applies_on(row, _as_date(booking_date)):
                continue
        else:
            other_until = _as_date(row['repeat_until']) if row.get('repeat_until') else None
            mine_until = _as_date(repeat_until) if repeat_until else None
            if row.get('booking_date'):
                when = _as_date(row['booking_date'])
                if when < date.today() or (mine_until and when > mine_until):
                    continue
            elif other_until and other_until < date.today():
                continue
        found.append(row)
    return found


def free_rooms(cursor, *, institution_id, room_type, day, start_time, end_time, booking_date=None, exclude_room=None, limit=8):
    """Rooms of the same type the institution may use that are free at that time (timetable and approved bookings)."""
    clause, params = candidate_rooms_clause(institution_id, 'r')
    type_clause = ' AND r.room_type = %s' if room_type else ''
    cursor.execute(
        f'SELECT r.id, r.room_number, r.room_type, r.capacity FROM rooms r WHERE {clause}{type_clause} ORDER BY r.room_number',
        tuple(params) + ((room_type,) if room_type else ()),
    )
    rooms = cursor.fetchall()
    free = []
    for room in rooms:
        if exclude_room is not None and int(room['id']) == int(exclude_room):
            continue
        if timetable_conflicts(cursor, room['id'], day, start_time, end_time):
            continue
        if booking_conflicts(cursor, room['id'], day=day, start_time=start_time, end_time=end_time, booking_date=booking_date):
            continue
        if _exam_hold(cursor, room['id'], day, start_time, end_time, booking_date, None):
            continue
        free.append({'id': int(room['id']), 'room_number': room['room_number'], 'room_type': room.get('room_type') or '', 'capacity': room.get('capacity')})
        if len(free) >= limit:
            break
    return free


def _refuse_if_taken(cursor, *, institution_id, room, day, start_time, end_time, booking_date, repeat_until, exclude_id=None):
    conflicts = timetable_conflicts(cursor, room['id'], day, start_time, end_time)
    alternatives = None
    if conflicts:
        first = conflicts[0]
        cohort = ' / '.join(part for part in (first['course_name'], first['class_name'], first['division_name']) if part)
        alternatives = free_rooms(
            cursor, institution_id=institution_id, room_type=room.get('room_type'), day=day, start_time=start_time,
            end_time=end_time, booking_date=booking_date, exclude_room=room['id'],
        )
        raise BookingError(
            'booking_room_busy',
            f"{room['room_number']} is timetabled for {first['subject_name']} ({cohort}) at that time on {day}s.",
            alternatives,
        )
    taken = booking_conflicts(
        cursor, room['id'], day=day, start_time=start_time, end_time=end_time, booking_date=booking_date,
        repeat_until=repeat_until, exclude_id=exclude_id,
    )
    if taken:
        alternatives = free_rooms(
            cursor, institution_id=institution_id, room_type=room.get('room_type'), day=day, start_time=start_time,
            end_time=end_time, booking_date=booking_date, exclude_room=room['id'],
        )
        raise BookingError('booking_room_booked', f"{room['room_number']} is already booked for '{taken[0]['title']}' at that time.", alternatives)
    held = _exam_hold(cursor, room['id'], day, start_time, end_time, booking_date, repeat_until)
    if held:
        alternatives = free_rooms(
            cursor, institution_id=institution_id, room_type=room.get('room_type'), day=day, start_time=start_time,
            end_time=end_time, booking_date=booking_date, exclude_room=room['id'],
        )
        raise BookingError('booking_room_booked', f"{room['room_number']} is held for the exam '{held['title']}' at that time.", alternatives)


def _merge_exam_usage(cursor, by_day, room_ids, usage):
    """Dated exam sessions on this week's dates, when capability `exams` is on. No query otherwise."""
    from services.exams import occupying

    for row in occupying(cursor, tuple(by_day.values()), room_ids):
        for day, day_date in by_day.items():
            if _as_date(row['exam_date']) == day_date:
                usage.setdefault(day, {}).setdefault(int(row['room_id']), []).append((as_time(row['start_time']), as_time(row['end_time'])))


def _exam_hold(cursor, room_id, day, start, end, booking_date, repeat_until):
    from services.exams import hold

    return hold(cursor, room_id, day, start, end, booking_date=booking_date, repeat_until=repeat_until)


# Writes -------------------------------------------------------------------------------------

def _room(cursor, room_id, institution_id):
    """The room when the institution may book it (own or shared to it); None otherwise."""
    clause, params = candidate_rooms_clause(institution_id, 'r')
    cursor.execute(
        f'SELECT r.id, r.room_number, r.room_type, r.capacity, r.institution_id FROM rooms r WHERE r.id = %s AND {clause}',
        (room_id, *params),
    )
    return cursor.fetchone()


def create(cursor, *, institution_id, room_id, title, kind, start_time, end_time, booking_date=None, day_of_week=None,
           repeat_until=None, notes='', booked_by=None, approve=False):
    """Insert one booking after the clash checks. Returns the new id.

    Exactly one of `booking_date` and `day_of_week` must be given. With `approve` the row is
    approved at once (the tenant does not require approval, or an approver books a room their
    institution owns); otherwise it waits as `requested`, which blocks nothing yet.
    """
    if kind not in KINDS:
        raise BookingError('booking_kind_invalid', 'Choose event, exam, maintenance or external.')
    if bool(booking_date) == bool(day_of_week):
        raise BookingError('booking_when_invalid', 'Give either a date or a weekday for the booking.')
    if day_of_week and day_of_week not in DAYS:
        raise BookingError('booking_when_invalid', 'Choose a weekday.')
    start, end = as_time(start_time), as_time(end_time)
    if start >= end:
        raise BookingError('booking_time_invalid', 'The end time must be after the start time.')
    if booking_date:
        booking_date = _as_date(booking_date)
        day = booking_date.strftime('%A')
        repeat_until = None
    else:
        day = day_of_week
        repeat_until = _as_date(repeat_until) if repeat_until else None
    room = _room(cursor, room_id, institution_id)
    if room is None:
        raise BookingError('booking_room_invalid', 'That room is not available to this institution.')
    _refuse_if_taken(
        cursor, institution_id=institution_id, room=room, day=day, start_time=start, end_time=end,
        booking_date=booking_date, repeat_until=repeat_until,
    )
    status = 'approved' if approve else 'requested'
    cursor.execute(
        """
        INSERT INTO bookings (institution_id, room_id, title, kind, booking_date, day_of_week, repeat_until, start_time, end_time,
                              notes, status, booked_by, decided_by, decided_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            institution_id, room['id'], title, kind, booking_date, day_of_week, repeat_until, start, end, notes or '', status,
            booked_by, booked_by if approve else None, datetime.utcnow() if approve else None,
        ),
    )
    return cursor.lastrowid


def load(cursor, booking_id):
    cursor.execute(f'{_SELECT} WHERE b.id = %s', (booking_id,))
    return cursor.fetchone()


def decide(cursor, booking_id, *, approve, decided_by, note=''):
    """Approve or reject a requested booking. Approval re-runs the clash checks against the ledger as it is now."""
    row = load(cursor, booking_id)
    if row is None:
        raise BookingError('booking_not_found', 'That booking was not found.')
    if row['status'] != 'requested':
        raise BookingError('booking_decided', 'That booking has already been decided.')
    if approve:
        day = _as_date(row['booking_date']).strftime('%A') if row.get('booking_date') else row['day_of_week']
        room = {'id': row['room_id'], 'room_number': row['room_number'], 'room_type': row.get('room_type')}
        _refuse_if_taken(
            cursor, institution_id=row['institution_id'], room=room, day=day, start_time=row['start_time'], end_time=row['end_time'],
            booking_date=row.get('booking_date'), repeat_until=row.get('repeat_until'), exclude_id=booking_id,
        )
    cursor.execute(
        "UPDATE bookings SET status = %s, decided_by = %s, decided_at = %s, decision_note = %s WHERE id = %s",
        ('approved' if approve else 'rejected', decided_by, datetime.utcnow(), (note or '')[:300], booking_id),
    )
    return 'approved' if approve else 'rejected'


def cancel(cursor, booking_id, *, cancelled_by):
    """Withdraw a requested or approved booking. Returns the previous status."""
    row = load(cursor, booking_id)
    if row is None:
        raise BookingError('booking_not_found', 'That booking was not found.')
    if row['status'] not in ('requested', 'approved'):
        raise BookingError('booking_decided', 'That booking is already closed.')
    cursor.execute(
        "UPDATE bookings SET status = 'cancelled', decided_by = %s, decided_at = %s WHERE id = %s",
        (cancelled_by, datetime.utcnow(), booking_id),
    )
    return row['status']


# Reads --------------------------------------------------------------------------------------

def list_bookings(cursor, *, rooms_clause='1=1', rooms_params=(), institution_clause='1=1', institution_params=(),
                  status=None, room_id=None, from_date=None, to_date=None, limit=300):
    """Bookings of rooms the caller may see or that the caller's institutions asked for, newest first.

    `rooms_clause`/`institution_clause` are predicates on aliases `r` (rooms) and `b` (bookings).
    `from_date`/`to_date` keep dated bookings in the window and every weekly booking still in force.
    """
    where = [f'(({rooms_clause}) OR ({institution_clause}))']
    params = list(rooms_params) + list(institution_params)
    if status:
        where.append('b.status = %s')
        params.append(status)
    if room_id:
        where.append('b.room_id = %s')
        params.append(room_id)
    if from_date:
        where.append('(b.booking_date IS NULL OR b.booking_date >= %s) AND (b.repeat_until IS NULL OR b.repeat_until >= %s)')
        params.extend((from_date, from_date))
    if to_date:
        where.append('(b.booking_date IS NULL OR b.booking_date <= %s)')
        params.append(to_date)
    cursor.execute(
        f"{_SELECT} WHERE {' AND '.join(where)} "
        f"ORDER BY FIELD(b.status, 'requested', 'approved', 'rejected', 'cancelled'), b.booking_date IS NULL, b.booking_date, "
        f"FIELD(b.day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), b.start_time, b.id DESC "
        f"LIMIT %s",
        tuple(params) + (int(limit),),
    )
    return cursor.fetchall()
