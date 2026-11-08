"""Teacher attendance load and save. Exceptions are left for the route."""

from datetime import date, datetime

from flask import flash

from academic_rules.weekdays import weekday_name

from data_access.teacher_attendance import (
    count_attendance_for_date,
    fetch_attendance_history,
    fetch_existing_attendance,
    fetch_faculty_table_id,
    fetch_history_lecture,
    fetch_lecture_roster,
    fetch_owned_lecture_detail,
    fetch_teacher_lectures,
    upsert_attendance,
)
from attendance_calc import Figures
from data_access.attendance_calc import fetch_students
from data_access.lecture_sessions import fetch_session_for
from extensions import get_db_connection
from services.attendance_calc import figures_dict, load_inputs, policy, student_report_from
from services.lecture_sessions import (
    CANCEL_REASONS,
    SessionCancelled,
    SessionHasMarks,
    SessionNotFound,
    cancel_lecture,
    record_held_session,
    restore_lecture,
)
from utils.dates import format_hhmm


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def load_attendance_index(user_id):
    """Return today's lecture list. The caller handles a database error."""
    connection, cursor = _cursor()
    lectures = fetch_teacher_lectures(cursor, user_id)
    today = date.today().strftime('%Y-%m-%d')
    today_formatted = date.today().strftime('%d %b %Y')
    for lecture in lectures:
        lecture['start_time'] = format_hhmm(lecture['start_time'])
        lecture['end_time'] = format_hhmm(lecture['end_time'])
        result = count_attendance_for_date(cursor, lecture['timetable_id'], today)
        lecture['attendance_marked_today'] = result['count'] > 0 if result else False
    marked_today_count = sum(1 for lecture in lectures if lecture['attendance_marked_today'])
    cursor.close()
    connection.close()
    return {
        'lectures': lectures,
        'today': today_formatted,
        'marked_today_count': marked_today_count,
    }


def load_mark_page(user_id, timetable_id):
    """Return the mark page, missing, or denied. The caller handles a database error."""
    connection, cursor = _cursor()
    faculty_row = fetch_faculty_table_id(cursor, user_id)
    if not faculty_row:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return 'missing'
    attendance_date = date.today().strftime('%Y-%m-%d')
    lecture = fetch_owned_lecture_detail(cursor, timetable_id, user_id, on_date=attendance_date)
    if not lecture:
        flash("Lecture not found or you don't have permission to mark attendance for it.", "danger")
        cursor.close()
        connection.close()
        return 'denied'
    lecture['start_time'] = format_hhmm(lecture['start_time'])
    lecture['end_time'] = format_hhmm(lecture['end_time'])
    students = fetch_lecture_roster(cursor, lecture)
    existing_attendance = {
        row['student_id']: {'status': row['status'], 'remarks': row['remarks']}
        for row in fetch_existing_attendance(cursor, timetable_id, attendance_date)
    }
    attendance_already_marked = len(existing_attendance) > 0
    session_row = fetch_session_for(cursor, timetable_id, attendance_date)
    session_status = session_row['status'] if session_row else None
    for student in students:
        if student['id'] in existing_attendance:
            student['attendance_status'] = existing_attendance[student['id']]['status']
            student['remarks'] = existing_attendance[student['id']]['remarks']
        else:
            student['attendance_status'] = None
            student['remarks'] = None
    cursor.close()
    connection.close()
    return {
        'lecture': lecture,
        'students': students,
        'attendance_date': attendance_date,
        'attendance_already_marked': attendance_already_marked,
        'session_status': session_status,
        'cancelled': session_status == 'cancelled',
        'is_owner': bool(lecture.get('is_owner', True)),
    }


_MARK_STATUSES = frozenset(('Present', 'Late', 'Absent'))


def _close(cursor, connection):
    cursor.close()
    connection.close()


def _marks(form):
    """Return student marks, or None when a status or student id is not acceptable."""
    marks = {}
    for key, value in form.items():
        if not str(key).startswith('status_'):
            continue
        if value not in _MARK_STATUSES:
            return None
        try:
            student_id = int(str(key).split('_', 1)[1])
        except (TypeError, ValueError):
            return None
        if student_id < 1 or student_id in marks:
            return None
        marks[student_id] = (value, form.get(f'remarks_{student_id}', '') or '')
    return marks


def _parse_date(raw):
    try:
        return datetime.strptime(str(raw), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _date_allowed(raw, lecture_day):
    """Attendance is taken today, and only when today is the lecture weekday."""
    chosen = _parse_date(raw)
    if chosen is None or chosen != date.today():
        return False
    return weekday_name(chosen) == weekday_name(lecture_day)


def save_teacher_attendance(user_id, timetable_id, form):
    """Save marks and record the lecture as held, in one transaction.

    The slot's teacher or the proxy approved for the date may mark. A cancelled
    lecture returns 'cancelled'. A database error rolls back and is raised
    again. The connection stays open on that path.
    """
    connection = None
    try:
        connection, cursor = _cursor()
        faculty_row = fetch_faculty_table_id(cursor, user_id)
        if not faculty_row:
            flash("Faculty profile not found.", "danger")
            _close(cursor, connection)
            return 'missing'
        faculty_id = faculty_row['id']
        attendance_date = form.get('attendance_date')
        chosen = _parse_date(attendance_date) if attendance_date else None
        lecture = fetch_owned_lecture_detail(cursor, timetable_id, user_id, on_date=chosen)
        if not lecture:
            flash("Unauthorized access.", "danger")
            _close(cursor, connection)
            return 'denied'
        if chosen is None or not _date_allowed(attendance_date, lecture.get('day_of_week')):
            flash("Attendance can only be marked today, on the lecture's scheduled day.", "danger")
            _close(cursor, connection)
            return 'date'
        marks = _marks(form)
        enrolled = {row['id'] for row in fetch_lecture_roster(cursor, lecture)}
        if marks is None or not set(marks) <= enrolled:
            flash("A student in this request is not in this class.", "danger")
            _close(cursor, connection)
            return 'student'
        try:
            session_id = record_held_session(cursor, timetable_id, chosen, faculty_id, 'teacher')
        except SessionCancelled:
            flash("This lecture is cancelled. Undo the cancellation before marking attendance.", "danger")
            connection.rollback()
            _close(cursor, connection)
            return 'cancelled'
        saved_count = 0
        for student_id, (status, remarks) in marks.items():
            upsert_attendance(
                cursor, student_id, timetable_id, attendance_date, status, faculty_id, remarks, session_id,
            )
            saved_count += 1
        connection.commit()
        _close(cursor, connection)
        return saved_count
    except Exception:
        if connection:
            connection.rollback()
        raise


def cancel_teacher_lecture(user_id, timetable_id, session_date, reason, notes=''):
    """Cancel one lecture of a slot the teacher owns or is the approved proxy for on that date.

    Returns 'denied', 'date', 'invalid', 'marked' (marks exist; only an admin may clear them), or the session id.
    """
    chosen = _parse_date(session_date)
    if chosen is None:
        return 'date'
    if reason not in CANCEL_REASONS:
        return 'invalid'
    connection = None
    try:
        connection, cursor = _cursor()
        lecture = fetch_owned_lecture_detail(cursor, timetable_id, user_id, on_date=chosen)
        if not lecture:
            _close(cursor, connection)
            return 'denied'
        if weekday_name(chosen) != weekday_name(lecture.get('day_of_week')):
            _close(cursor, connection)
            return 'date'
        try:
            session_id = cancel_lecture(
                cursor, timetable_id=timetable_id, session_date=chosen, actor_user_id=user_id,
                reason=reason, notes=notes, source='teacher',
            )
        except SessionHasMarks:
            connection.rollback()
            _close(cursor, connection)
            return 'marked'
        connection.commit()
        _close(cursor, connection)
        return session_id
    except Exception:
        if connection:
            connection.rollback()
        raise


def restore_teacher_lecture(user_id, timetable_id, session_date):
    """Undo a cancellation on a slot the teacher owns or is the approved proxy for. Returns 'denied', 'date', 'missing', or the new status."""
    chosen = _parse_date(session_date)
    if chosen is None:
        return 'date'
    connection = None
    try:
        connection, cursor = _cursor()
        lecture = fetch_owned_lecture_detail(cursor, timetable_id, user_id, on_date=chosen)
        if not lecture:
            _close(cursor, connection)
            return 'denied'
        session_row = fetch_session_for(cursor, timetable_id, chosen)
        if not session_row:
            _close(cursor, connection)
            return 'missing'
        try:
            status = restore_lecture(cursor, session_row['id'], user_id, today=date.today())
        except SessionNotFound:
            _close(cursor, connection)
            return 'missing'
        connection.commit()
        _close(cursor, connection)
        return status or 'removed'
    except Exception:
        if connection:
            connection.rollback()
        raise


def _roster_figures(cursor, lecture, date_from=None, date_to=None):
    """Every roster student's figures for the lecture's subject: the teacher's report for one slot.

    A student who was never marked is listed with no percentage, not left out.
    The figures pool every slot of the subject the student is in the roster
    for (two weekly Physics lectures give one Physics figure).
    """
    roster = fetch_lecture_roster(cursor, lecture)
    if not roster:
        return []
    rows = {row['id']: row for row in fetch_students(cursor, course_id=lecture['course_id'], class_id=lecture['class_id'], active_only=False)}
    student_rows = [rows[student['id']] for student in roster if student['id'] in rows]
    inputs = load_inputs(cursor, student_rows, date_from, date_to)
    chosen = policy()
    result = []
    for student in roster:
        if student['id'] not in rows:
            continue
        report = student_report_from(inputs, student['id'], chosen)
        entry = report.summary.subjects.get(lecture['subject_id'])
        figures = figures_dict(entry.figures if entry else Figures())
        figures.update({
            'student_id': student['id'],
            'student_name': student['name'],
            'roll_number': student['roll_number'],
        })
        result.append(figures)
    return result


def load_attendance_history(user_id, timetable_id, date_from=None, date_to=None):
    """Return the slot's recorded lectures and the roster's figures, or denied. The caller handles a database error."""
    connection, cursor = _cursor()
    try:
        lecture = fetch_history_lecture(cursor, timetable_id, user_id)
        if not lecture:
            flash("Unauthorized access.", "danger")
            return 'denied'
        history = fetch_attendance_history(cursor, timetable_id)
        for record in history:
            record['total_students'] = int(record['total_students']) if record['total_students'] else 0
            record['present'] = int(record['present']) if record['present'] else 0
            record['late'] = int(record['late']) if record['late'] else 0
            record['absent'] = int(record['absent']) if record['absent'] else 0
        return {
            'lecture': lecture,
            'history': history,
            'students': _roster_figures(cursor, lecture, date_from, date_to),
            'threshold': policy().threshold,
        }
    finally:
        cursor.close()
        connection.close()
