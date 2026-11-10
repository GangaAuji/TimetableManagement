"""Manual timetable slots: one place for the rules a hand-added slot must pass.

Used by the JSON API (api/web/timetable.py) and the legacy manage form
(services/admin_timetable.py). A slot may name a lab batch
(lab_batch_group_id); two different batches of one division may share a
time, a whole-division slot may not (academic_rules.clashes).
"""

from academic_rules.availability import manual_add_availability_block
from academic_rules.holidays import recurring_holiday_blocks_day
from data_access.admin_timetable import (
    fetch_allocated_faculty,
    fetch_class_overlap,
    fetch_course_program,
    fetch_faculty_overlap,
    insert_timetable_session,
)
from data_access.institutions import candidate_faculty_clause, candidate_rooms_clause, institution_of_course
from data_access.lecture_sessions import count_slot_sessions


class SlotError(ValueError):
    """The slot breaks a rule; `code` names it, the message is for people."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _check_sharing(cursor, course_id, faculty_id, room_id):
    """In a multi-institution tenant the room and teacher must be the course's own or shared to its institution."""
    try:
        cursor.execute('SELECT COUNT(*) AS n FROM institutions WHERE is_active = 1')
        if int((cursor.fetchone() or {}).get('n') or 0) <= 1:
            return
    except Exception:
        return   # before revision 0014: no institutions, no sharing rules
    institution_id = institution_of_course(cursor, course_id)
    if institution_id is None:
        return
    if room_id is not None:
        clause, params = candidate_rooms_clause(institution_id, 'r')
        cursor.execute(f'SELECT 1 FROM rooms r WHERE r.id = %s AND {clause}', (room_id, *params))
        if not cursor.fetchone():
            raise SlotError('slot_room_not_shared', 'That room belongs to another institution and is not shared with this one.')
    if faculty_id is not None:
        clause, params = candidate_faculty_clause(institution_id, 'f', 'fd')
        cursor.execute(
            f'SELECT 1 FROM faculty f LEFT JOIN departments fd ON fd.id = f.department_id WHERE f.user_id = %s AND {clause}',
            (faculty_id, *params),
        )
        if not cursor.fetchone():
            raise SlotError('slot_faculty_not_shared', 'That faculty member belongs to another institution and is not shared with this one.')


def check_slot(cursor, *, course_id, class_id, division_id, subject_id, day, start_time, end_time,
               faculty_id=None, lab_batch_group_id=None, room_id=None, exclude_id=None, first_only=False):
    """Run every rule a slot must pass without writing anything.

    Returns `(faculty_id, errors)`: the teacher that would be used (the allocated one when none is
    given) and a list of `SlotError`s, empty when the slot is fine. `exclude_id` ignores one existing
    slot, the one being moved. With `first_only` the list stops at the first failure, which is what
    `add_slot` needs; the Timetable grid's `POST /api/timetable/check` wants them all.
    """
    errors = []

    def fail(code, message):
        errors.append(SlotError(code, message))
        return first_only

    if start_time >= end_time:
        fail('slot_time_invalid', 'The end time must be after the start time.')
        return faculty_id, errors
    if not faculty_id:
        allocated = fetch_allocated_faculty(cursor, class_id, division_id, subject_id)
        if not allocated:
            fail('slot_no_faculty', 'No faculty is allocated for this subject. Assign faculty first or choose one.')
            return None, errors
        faculty_id = allocated['faculty_id']
    if lab_batch_group_id is not None:
        cursor.execute(
            'SELECT course_id, class_id, division_id, is_active FROM lab_batch_groups WHERE id = %s', (lab_batch_group_id,),
        )
        batch = cursor.fetchone()
        if not batch or int(batch['course_id']) != int(course_id) or int(batch['class_id']) != int(class_id) or (
            batch['division_id'] is not None and int(batch['division_id']) != int(division_id)
        ):
            if fail('slot_batch_invalid', 'That lab batch does not belong to this class and division.'):
                return faculty_id, errors
    program_row = fetch_course_program(cursor, course_id)
    program = program_row['program'] if program_row else 'UG'
    if recurring_holiday_blocks_day(cursor, program, day):
        if fail('slot_holiday', 'Cannot add a session on a weekly holiday for this program.'):
            return faculty_id, errors
    if fetch_class_overlap(cursor, course_id, class_id, division_id, day, start_time, end_time, lab_batch_group_id, exclude_id=exclude_id):
        if lab_batch_group_id is None:
            blocked = fail('slot_class_busy', 'Overlaps with an existing session for this class/division.')
        else:
            blocked = fail('slot_batch_busy', 'This batch, or the whole division, already has a session at that time.')
        if blocked:
            return faculty_id, errors
    if fetch_faculty_overlap(cursor, faculty_id, day, start_time, end_time, exclude_id=exclude_id):
        if fail('slot_faculty_busy', 'Selected faculty is busy at that time.'):
            return faculty_id, errors
    message = manual_add_availability_block(cursor, faculty_id, day, start_time, end_time)
    if message:
        if fail('slot_faculty_unavailable', message):
            return faculty_id, errors
    try:
        _check_sharing(cursor, course_id, faculty_id, room_id)
    except SlotError as exc:
        if fail(exc.code, str(exc)):
            return faculty_id, errors
    if room_id is not None:
        exclude = ' AND id <> %s' if exclude_id is not None else ''
        cursor.execute(
            f"""
            SELECT 1 FROM timetable
            WHERE room_id = %s AND day_of_week = %s AND COALESCE(is_active, 1) = 1
              AND NOT (end_time <= %s OR start_time >= %s){exclude}
            LIMIT 1
            """,
            (room_id, day, start_time, end_time) + ((exclude_id,) if exclude_id is not None else ()),
        )
        if cursor.fetchone():
            if fail('slot_room_busy', 'That room is in use at that time.'):
                return faculty_id, errors
        else:
            # Approved weekly bookings (services/bookings.py) sit on the same ledger; no-op when the capability is off.
            from services import bookings

            booked = bookings.booked_room(cursor, room_id, day, start_time, end_time)
            if booked:
                fail('slot_room_booked', f"That room is booked for '{booked['title']}' at that time.")
    return faculty_id, errors


def add_slot(cursor, *, course_id, class_id, division_id, subject_id, day, start_time, end_time,
             faculty_id=None, lab_batch_group_id=None, room_id=None):
    """Insert one slot after every check (`check_slot`). Returns the new timetable id.

    Without `faculty_id` the subject's allocated teacher for the class and
    division is used. A lab batch must belong to the same course and class
    (and division, unless it splits the whole class).
    """
    faculty_id, errors = check_slot(
        cursor, course_id=course_id, class_id=class_id, division_id=division_id, subject_id=subject_id, day=day,
        start_time=start_time, end_time=end_time, faculty_id=faculty_id, lab_batch_group_id=lab_batch_group_id,
        room_id=room_id, first_only=True,
    )
    if errors:
        raise errors[0]
    # With versions on, a manual slot joins the cohort's published version so a rollback restores it.
    version_id = None
    try:
        from services.timetable import versions

        if versions.active(cursor):
            version_id = versions.published_version_for(cursor, course_id, class_id, division_id)
    except Exception:
        version_id = None
    timetable_id = insert_timetable_session(
        cursor, (course_id, class_id, division_id, subject_id, faculty_id, day, start_time, end_time),
        lab_batch_group_id, room_id, version_id=version_id,
    )
    from services.webhooks import on_timetable_published

    on_timetable_published(
        cursor, course_id=course_id, class_id=class_id, division_id=division_id, reason='slot_added', timetable_id=timetable_id,
    )
    return timetable_id


def _hhmm(value):
    from datetime import timedelta

    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        return f'{total // 3600:02d}:{(total % 3600) // 60:02d}'
    if hasattr(value, 'strftime'):
        return value.strftime('%H:%M')
    return str(value or '')[:5]


def slot_cost(cursor, *, course_id, class_id, division_id, subject_id, day, start_time, end_time, faculty_id,
              lab_batch_group_id=None, room_id=None, exclude_id=None):
    """How the soft rules (services/timetable/rules.py) judge adding this slot. None when rules are off.

    Scores the cohort's active slots without and with the candidate and returns the extra cost and the
    violations the candidate introduces, so the grid can shade a drop target amber before it is confirmed.
    """
    from services.timetable import rules as rule_set

    rules, preferences_on = rule_set.effective_rules(cursor, rule_set.institution_for_course(cursor, course_id))
    if not preferences_on:
        return None
    exclude = ' AND t.id <> %s' if exclude_id is not None else ''
    tail = (exclude_id,) if exclude_id is not None else ()
    cursor.execute(
        f"""
        SELECT t.id, t.day_of_week, t.start_time, t.end_time, t.subject_id, t.faculty_id, t.room_id, t.lab_batch_group_id,
               COALESCE(s.name, '') AS subject_name, COALESCE(s.theory_practical, '') AS session_type, COALESCE(f.name, '') AS faculty_name
        FROM timetable t
        LEFT JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN faculty f ON f.user_id = t.faculty_id
        WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s AND COALESCE(t.is_active, 1) = 1{exclude}
        """,
        (course_id, class_id, division_id) + tail,
    )
    entries = [
        {
            'day': row['day_of_week'], 'start_time': _hhmm(row['start_time']), 'end_time': _hhmm(row['end_time']),
            'subject_id': row['subject_id'], 'subject_name': row['subject_name'], 'faculty_id': row['faculty_id'],
            'faculty_name': row['faculty_name'], 'room_id': row['room_id'], 'lab_batch_group_id': row['lab_batch_group_id'],
            'session_type': row['session_type'],
        }
        for row in cursor.fetchall()
    ]
    cursor.execute(
        f"""
        SELECT t.day_of_week, t.start_time, t.end_time, t.faculty_id, t.subject_id, t.room_id FROM timetable t
        WHERE t.faculty_id = %s AND COALESCE(t.is_active, 1) = 1
          AND NOT (t.course_id = %s AND t.class_id = %s AND t.division_id = %s){exclude}
        """,
        (faculty_id, course_id, class_id, division_id) + tail,
    )
    external = [
        {'day': row['day_of_week'], 'start_time': _hhmm(row['start_time']), 'end_time': _hhmm(row['end_time']),
         'faculty_id': row['faculty_id'], 'subject_id': row['subject_id'], 'room_id': row['room_id'], 'lab_batch_group_id': None, 'session_type': ''}
        for row in cursor.fetchall()
    ]
    cursor.execute("SELECT name, COALESCE(theory_practical, '') AS subject_type FROM subjects WHERE id = %s", (subject_id,))
    subject = cursor.fetchone() or {}
    cursor.execute('SELECT name FROM faculty WHERE user_id = %s', (faculty_id,))
    teacher = cursor.fetchone() or {}
    candidate = {
        'day': day, 'start_time': _hhmm(start_time), 'end_time': _hhmm(end_time), 'subject_id': subject_id,
        'subject_name': subject.get('name') or '', 'faculty_id': faculty_id, 'faculty_name': teacher.get('name') or '',
        'room_id': room_id, 'lab_batch_group_id': lab_batch_group_id, 'session_type': subject.get('subject_type') or '',
    }
    preferences = rule_set.load_preferences(cursor, {faculty_id} | {row['faculty_id'] for row in entries if row['faculty_id']})
    starts = sorted({row['start_time'] for row in entries + external + [candidate]})
    before = rule_set.evaluate(entries, rules, preferences, slot_starts=starts, external=external)
    after = rule_set.evaluate(entries + [candidate], rules, preferences, slot_starts=starts, external=external)
    seen = {(v['rule'], v['day'], v['start_time'], v['faculty_id'], v['detail']) for v in before['violations']}
    introduced = [v for v in after['violations'] if (v['rule'], v['day'], v['start_time'], v['faculty_id'], v['detail']) not in seen]
    return {
        'cost_before': int(before['cost']),
        'cost_after': int(after['cost']),
        'delta': int(after['cost']) - int(before['cost']),
        'violations': introduced,
    }


def remove_slot(cursor, timetable_id):
    """Retire a slot that has recorded lectures (keeps attendance history); delete one that has none.

    Returns 'retired', 'deleted' or None when there is no such active slot.
    """
    cursor.execute('SELECT id, course_id, class_id, division_id FROM timetable WHERE id = %s AND COALESCE(is_active, 1) = 1', (timetable_id,))
    slot = cursor.fetchone()
    if slot is None:
        return None
    cursor.execute('SELECT 1 FROM attendance WHERE timetable_id = %s LIMIT 1', (timetable_id,))
    has_marks = cursor.fetchone() is not None
    if has_marks or count_slot_sessions(cursor, timetable_id):
        cursor.execute('UPDATE timetable SET is_active = 0 WHERE id = %s', (timetable_id,))
        outcome = 'retired'
    else:
        cursor.execute('DELETE FROM timetable WHERE id = %s', (timetable_id,))
        outcome = 'deleted'
    from services.webhooks import on_timetable_published

    on_timetable_published(
        cursor, course_id=slot['course_id'], class_id=slot['class_id'], division_id=slot.get('division_id'),
        reason=f'slot_{outcome}', timetable_id=timetable_id,
    )
    return outcome
