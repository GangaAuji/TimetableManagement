"""lecture_sessions SQL. Callers pass a dictionary cursor and own the transaction."""

HELD = 'held'
CANCELLED = 'cancelled'
NOT_MARKED = 'not_marked'

_SESSION_COLUMNS = """
    ls.id, ls.timetable_id, ls.session_date, ls.status, ls.taught_by, ls.marked_by, ls.marked_at,
    ls.cancelled_by, ls.cancelled_at, ls.cancel_reason, ls.source, ls.notes, ls.created_at, ls.updated_at
"""


def fetch_session(cursor, session_id):
    cursor.execute(f'SELECT {_SESSION_COLUMNS} FROM lecture_sessions ls WHERE ls.id = %s', (session_id,))
    return cursor.fetchone()


def fetch_session_for(cursor, timetable_id, session_date):
    cursor.execute(
        f'SELECT {_SESSION_COLUMNS} FROM lecture_sessions ls WHERE ls.timetable_id = %s AND ls.session_date = %s',
        (timetable_id, session_date),
    )
    return cursor.fetchone()


def fetch_slot(cursor, timetable_id):
    """The slot with its course program and semester dates. None when the slot does not exist."""
    cursor.execute(
        """
        SELECT t.id, t.course_id, t.class_id, t.division_id, t.subject_id, t.faculty_id, t.day_of_week,
               t.start_time, t.end_time, t.semester_id, t.academic_year_id, COALESCE(t.is_active, 1) AS is_active,
               co.program, sem.start_date AS semester_start, sem.end_date AS semester_end,
               COALESCE(sub.is_elective, 0) AS is_elective
        FROM timetable t
        JOIN courses co ON co.id = t.course_id
        JOIN subjects sub ON sub.id = t.subject_id
        LEFT JOIN semesters sem ON sem.id = t.semester_id
        WHERE t.id = %s
        """,
        (timetable_id,),
    )
    return cursor.fetchone()


def fetch_mobile_sessions_for_date(cursor, session_date):
    """Held sessions the device recorded on the date, with the slot's roster columns and the marker to use for absences."""
    cursor.execute(
        """
        SELECT ls.id, ls.timetable_id, ls.session_date,
               COALESCE(ls.marked_by, f.id) AS marked_by,
               t.course_id, t.class_id, t.division_id, t.subject_id, t.semester_id, t.academic_year_id,
               COALESCE(sub.is_elective, 0) AS is_elective
        FROM lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        JOIN subjects sub ON sub.id = t.subject_id
        LEFT JOIN faculty f ON f.user_id = t.faculty_id
        WHERE ls.session_date = %s AND ls.status = 'held' AND ls.source = 'mobile'
        ORDER BY ls.id
        """,
        (session_date,),
    )
    return cursor.fetchall()


def fetch_marked_student_ids(cursor, session_id):
    cursor.execute('SELECT student_id FROM attendance WHERE session_id = %s', (session_id,))
    return {row['student_id'] for row in cursor.fetchall()}


def insert_absent_mark(cursor, student_id, session, remarks):
    """An Absent row for a roster student the device did not detect. Leaves an existing row alone."""
    cursor.execute(
        """
        INSERT IGNORE INTO attendance (student_id, timetable_id, session_id, attendance_date, status, marked_by, remarks)
        VALUES (%s, %s, %s, %s, 'Absent', %s, %s)
        """,
        (student_id, session['timetable_id'], session['id'], session['session_date'], session['marked_by'], remarks),
    )
    return cursor.rowcount == 1


def fetch_approved_proxy(cursor, timetable_id, session_date):
    """The faculty user id approved to take this slot on this date, or None."""
    cursor.execute(
        """
        SELECT proxy_faculty_id FROM proxy_log
        WHERE timetable_id = %s AND absence_date = %s AND status = 'ASSIGNED' AND approval_status = 'APPROVED'
          AND proxy_faculty_id IS NOT NULL
        ORDER BY approval_date DESC, id DESC
        LIMIT 1
        """,
        (timetable_id, session_date),
    )
    row = cursor.fetchone()
    return row['proxy_faculty_id'] if row else None


def resolve_taught_by(cursor, timetable_id, session_date):
    """The approved proxy for the date, else the slot's faculty user id."""
    proxy = fetch_approved_proxy(cursor, timetable_id, session_date)
    if proxy is not None:
        return proxy
    cursor.execute('SELECT faculty_id FROM timetable WHERE id = %s', (timetable_id,))
    row = cursor.fetchone()
    return row['faculty_id'] if row else None


def upsert_held_session(cursor, timetable_id, session_date, taught_by, marked_by, source):
    """Insert a held session, or turn an existing not_marked one into held. Returns the session id.

    The first marker and time are kept when the row already has them.
    """
    cursor.execute(
        """
        INSERT INTO lecture_sessions (timetable_id, session_date, status, taught_by, marked_by, marked_at, source)
        VALUES (%s, %s, 'held', %s, %s, NOW(), %s)
        ON DUPLICATE KEY UPDATE
            id = LAST_INSERT_ID(id),
            status = 'held',
            taught_by = COALESCE(taught_by, VALUES(taught_by)),
            marked_by = COALESCE(marked_by, VALUES(marked_by)),
            marked_at = COALESCE(marked_at, VALUES(marked_at))
        """,
        (timetable_id, session_date, taught_by, marked_by, source),
    )
    return cursor.lastrowid


def insert_not_marked(cursor, timetable_id, session_date, taught_by, source='close_day'):
    """Record that nobody marked this lecture. Returns True when a row was added, False when one existed."""
    cursor.execute(
        """
        INSERT INTO lecture_sessions (timetable_id, session_date, status, taught_by, source)
        VALUES (%s, %s, 'not_marked', %s, %s)
        ON DUPLICATE KEY UPDATE id = id
        """,
        (timetable_id, session_date, taught_by, source),
    )
    return cursor.rowcount == 1


def upsert_cancelled_session(cursor, timetable_id, session_date, taught_by, cancelled_by, reason, notes, source):
    """Mark the slot's lecture on that date as cancelled, creating the row when needed. Returns the id."""
    cursor.execute(
        """
        INSERT INTO lecture_sessions
            (timetable_id, session_date, status, taught_by, cancelled_by, cancelled_at, cancel_reason, notes, source)
        VALUES (%s, %s, 'cancelled', %s, %s, NOW(), %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            id = LAST_INSERT_ID(id),
            status = 'cancelled',
            taught_by = COALESCE(taught_by, VALUES(taught_by)),
            cancelled_by = VALUES(cancelled_by),
            cancelled_at = NOW(),
            cancel_reason = VALUES(cancel_reason),
            notes = VALUES(notes)
        """,
        (timetable_id, session_date, taught_by, cancelled_by, reason, notes, source),
    )
    return cursor.lastrowid


def restore_session(cursor, session_id, status):
    """Take a cancelled session back to held or not_marked."""
    cursor.execute(
        """
        UPDATE lecture_sessions
        SET status = %s, cancelled_by = NULL, cancelled_at = NULL, cancel_reason = NULL
        WHERE id = %s AND status = 'cancelled'
        """,
        (status, session_id),
    )
    return cursor.rowcount


def count_marks(cursor, session_id):
    cursor.execute('SELECT COUNT(*) AS n FROM attendance WHERE session_id = %s', (session_id,))
    return cursor.fetchone()['n']


def count_slot_sessions(cursor, timetable_id):
    cursor.execute('SELECT COUNT(*) AS n FROM lecture_sessions WHERE timetable_id = %s', (timetable_id,))
    return cursor.fetchone()['n']


def delete_marks(cursor, session_id):
    cursor.execute('DELETE FROM attendance WHERE session_id = %s', (session_id,))
    return cursor.rowcount


def link_marks(cursor, session_id, timetable_id, session_date):
    """Point unlinked attendance rows of the slot and date at the session. Returns how many."""
    cursor.execute(
        'UPDATE attendance SET session_id = %s WHERE timetable_id = %s AND attendance_date = %s AND session_id IS NULL',
        (session_id, timetable_id, session_date),
    )
    return cursor.rowcount


def fetch_active_slots_for_weekday(cursor, weekday_name):
    """Active slots on this weekday with their program and semester dates."""
    cursor.execute(
        """
        SELECT t.id, t.course_id, t.class_id, t.division_id, t.subject_id, t.faculty_id, t.day_of_week,
               t.semester_id, co.program, sem.start_date AS semester_start, sem.end_date AS semester_end
        FROM timetable t
        JOIN courses co ON co.id = t.course_id
        LEFT JOIN semesters sem ON sem.id = t.semester_id
        WHERE t.day_of_week = %s AND COALESCE(t.is_active, 1) = 1
        ORDER BY t.id
        """,
        (weekday_name,),
    )
    return cursor.fetchall()


def fetch_session_dates(cursor, session_date):
    """Slot ids that already have a session row on the date."""
    cursor.execute('SELECT timetable_id FROM lecture_sessions WHERE session_date = %s', (session_date,))
    return {row['timetable_id'] for row in cursor.fetchall()}


def fetch_proxies_for_date(cursor, session_date):
    """timetable_id -> approved proxy user id for the date."""
    cursor.execute(
        """
        SELECT timetable_id, proxy_faculty_id FROM proxy_log
        WHERE absence_date = %s AND status = 'ASSIGNED' AND approval_status = 'APPROVED' AND proxy_faculty_id IS NOT NULL
        ORDER BY approval_date, id
        """,
        (session_date,),
    )
    return {row['timetable_id']: row['proxy_faculty_id'] for row in cursor.fetchall()}


def fetch_unlinked_mark_groups(cursor):
    """Attendance rows with no session, grouped by slot, date and marker, with the slot's details."""
    cursor.execute(
        """
        SELECT a.timetable_id, a.attendance_date, a.marked_by, COUNT(*) AS marks, MIN(a.marked_at) AS first_marked_at,
               t.day_of_week, COALESCE(t.is_active, 1) AS is_active, t.faculty_id, t.course_id, t.class_id,
               t.division_id, t.subject_id, t.semester_id, t.academic_year_id, co.program,
               (s.is_elective = 1 OR s.course_type IN ('Elective', 'Elective Practical')) AS is_elective,
               f.user_id AS marker_user_id
        FROM attendance a
        JOIN timetable t ON t.id = a.timetable_id
        JOIN courses co ON co.id = t.course_id
        JOIN subjects s ON s.id = t.subject_id
        LEFT JOIN faculty f ON f.id = a.marked_by
        WHERE a.session_id IS NULL
        GROUP BY a.timetable_id, a.attendance_date, a.marked_by
        ORDER BY a.attendance_date, a.timetable_id, marks DESC, a.marked_by
        """
    )
    return cursor.fetchall()


def fetch_unlinked_marks_outside_roster(cursor, timetable_id, attendance_date, roster_ids):
    """Student ids marked for the slot and date that are not in `roster_ids`."""
    cursor.execute(
        'SELECT DISTINCT student_id FROM attendance WHERE timetable_id = %s AND attendance_date = %s AND session_id IS NULL',
        (timetable_id, attendance_date),
    )
    return sorted(row['student_id'] for row in cursor.fetchall() if row['student_id'] not in roster_ids)


def count_unlinked_marks(cursor):
    cursor.execute('SELECT COUNT(*) AS n FROM attendance WHERE session_id IS NULL')
    return cursor.fetchone()['n']


def fetch_sessions(cursor, *, status=None, date_from=None, date_to=None, timetable_id=None, limit=200):
    """Sessions for the admin list, newest first, with slot and teacher details."""
    clauses, params = ['1 = 1'], []
    if status:
        clauses.append('ls.status = %s')
        params.append(status)
    if date_from:
        clauses.append('ls.session_date >= %s')
        params.append(date_from)
    if date_to:
        clauses.append('ls.session_date <= %s')
        params.append(date_to)
    if timetable_id:
        clauses.append('ls.timetable_id = %s')
        params.append(timetable_id)
    params.append(int(limit))
    cursor.execute(
        f"""
        SELECT ls.id, ls.timetable_id, ls.session_date, ls.status, ls.source, ls.cancel_reason, ls.notes,
               ls.marked_at, ls.cancelled_at,
               t.day_of_week, t.start_time, t.end_time,
               s.name AS subject_name, c.name AS class_name, d.name AS division_name,
               COALESCE(taught.name, owner.name) AS teacher_name,
               (SELECT COUNT(*) FROM attendance a WHERE a.session_id = ls.id) AS marks
        FROM lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        JOIN subjects s ON s.id = t.subject_id
        JOIN classes c ON c.id = t.class_id
        LEFT JOIN divisions d ON d.id = t.division_id
        LEFT JOIN faculty owner ON owner.user_id = t.faculty_id
        LEFT JOIN faculty taught ON taught.user_id = ls.taught_by
        WHERE {' AND '.join(clauses)}
        ORDER BY ls.session_date DESC, t.start_time, ls.id DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return cursor.fetchall()
