"""Attendance overview, records, faculty attendance, mobile logs, lecture sessions, and the student view."""

from datetime import date, timedelta

from flask import current_app, request, session

from extensions import get_db_connection
from core.pagination import page_bounds
from api.web.access import InputError, allowed, body, close, flag, iso_date, optional_text, permission_denied, reject_input, required_text, whole_number
from services.attendance_admin._common import _promote_log_to_attendance, _table_exists
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_stamp, safe_text
from data_access.attendance_calc import count_not_marked_sessions
from data_access.lecture_sessions import fetch_session
from services.attendance_calc import defaulters, parse_threshold, percent_value, period_statistics, student_report
from services.lecture_sessions import (
    CANCEL_REASONS,
    SessionHasMarks,
    SessionNotFound,
    cancel_lecture,
    list_sessions,
    restore_lecture,
)

_MESSAGES = {
    'attendance_unavailable': 'The page could not be loaded.',
    'invalid_body': 'The request could not be accepted.',
    'session_invalid': 'Check the form and try again.',
    'session_date': 'Enter a valid date.',
    'session_marked': 'Attendance has been marked for this lecture. Pass clear_marks to remove the marks and cancel it.',
    'session_missing': 'That lecture session was not found.',
    'attendance_date_invalid': 'Enter a valid date.',
    'attendance_status_invalid': 'Status must be Present, Absent, or Late.',
    'attendance_record_missing': 'That attendance record was not found.',
    'attendance_filters_invalid': 'Check the filters and try again.',
    'attendance_limit_invalid': 'Choose between 1 and 500 logs.',
}
_FACULTY_STATUSES = frozenset(('Present', 'Late', 'Absent'))
_LOG_STATUSES = frozenset(('processed', 'pending', 'failed'))
_ACTIVITY_SIZES = frozenset((20, 50, 100))
_MARK_STATUSES = frozenset(('Present', 'Absent', 'Late'))
_SESSION_STATUSES = frozenset(('held', 'cancelled', 'not_marked'))
_DEFAULTER_LIMIT = 200
_OVERVIEW_DAYS = 30


def register_attendance_routes(blueprint):
    blueprint.add_url_rule('/attendance/overview', 'attendance_overview', overview, methods=['GET'])
    blueprint.add_url_rule('/attendance/manage', 'attendance_records', records, methods=['GET'])
    blueprint.add_url_rule('/attendance/manage/<int:record_id>', 'attendance_record_update', update_record, methods=['POST'])
    blueprint.add_url_rule('/attendance/faculty', 'attendance_faculty', faculty, methods=['GET'])
    blueprint.add_url_rule('/attendance/mobile', 'attendance_mobile', mobile, methods=['GET'])
    blueprint.add_url_rule('/attendance/mobile/reprocess', 'attendance_mobile_reprocess', reprocess_logs, methods=['POST'])
    blueprint.add_url_rule('/attendance/sessions', 'attendance_sessions', sessions, methods=['GET'])
    blueprint.add_url_rule('/attendance/sessions/cancel', 'attendance_session_cancel_date', cancel_by_date, methods=['POST'])
    blueprint.add_url_rule('/attendance/sessions/<int:session_id>/cancel', 'attendance_session_cancel', cancel_session, methods=['POST'])
    blueprint.add_url_rule('/attendance/sessions/<int:session_id>/uncancel', 'attendance_session_uncancel', uncancel_session, methods=['POST'])
    blueprint.add_url_rule('/portal/attendance', 'attendance_student', student, methods=['GET'])


def _session_row(row):
    return {
        'id': safe_count(row.get('id')),
        'timetable_id': safe_count(row.get('timetable_id')),
        'date': safe_stamp(row.get('session_date'))[:10],
        'status': safe_text(row.get('status') or '', 12),
        'source': safe_text(row.get('source') or '', 12),
        'reason': safe_text(row.get('cancel_reason') or '', 20),
        'note': safe_text(row.get('notes') or '', 255),
        'day': safe_text(row.get('day_of_week') or '', 12),
        'start_time': safe_clock(row.get('start_time')),
        'end_time': safe_clock(row.get('end_time')),
        'subject': safe_text(row.get('subject_name') or '', 100),
        'class_name': safe_text(row.get('class_name') or '', 100),
        'division_name': safe_text(row.get('division_name') or '', 50),
        'teacher': safe_text(row.get('teacher_name') or '', 100),
        'marks': safe_count(row.get('marks')),
        'marked_at': safe_stamp(row.get('marked_at')),
        'cancelled_at': safe_stamp(row.get('cancelled_at')),
    }


def sessions():
    """Lecture sessions, newest first. ?status=not_marked lists lectures nobody marked."""
    denied = permission_denied('attendance_view', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    status = request.args.get('status') or None
    if status is not None and status not in _SESSION_STATUSES:
        return reject_input(_MESSAGES, 'session_invalid')
    try:
        date_from = iso_date(request.args.get('from'), 'session_date', required=False)
        date_to = iso_date(request.args.get('to'), 'session_date', required=False)
        timetable_id = request.args.get('timetable_id')
        timetable_id = whole_number(timetable_id, 1000000, 'session_invalid', lower=1) if timetable_id else None
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        rows = list_sessions(cursor, status=status, date_from=date_from, date_to=date_to, timetable_id=timetable_id)
        return json_ok({'sessions': [_session_row(row) for row in rows]})
    except Exception:
        current_app.logger.exception('Lecture sessions list failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def _cancel_payload(fields):
    payload = body(fields)
    reason = payload.get('reason')
    if reason not in CANCEL_REASONS:
        raise InputError('session_invalid')
    note = optional_text(payload.get('note'), 255, 'session_invalid')
    clear_marks = flag(payload['clear_marks']) if 'clear_marks' in payload else False
    return payload, reason, note, clear_marks


def _cancel(timetable_id, when, reason, note, clear_marks):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            session_id = cancel_lecture(
                cursor, timetable_id=timetable_id, session_date=when, actor_user_id=session.get('user_id'),
                reason=reason, notes=note, source='admin', clear_marks=clear_marks,
            )
        except SessionHasMarks:
            connection.rollback()
            return json_error(_MESSAGES['session_marked'], 409, 'session_marked')
        connection.commit()
        return json_ok({'session_id': safe_count(session_id), 'status': 'cancelled'})
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Lecture session cancel failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def cancel_by_date():
    """Cancel a slot's lecture on a date, creating the session row when it does not exist yet."""
    denied = permission_denied('attendance_manage', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    try:
        payload, reason, note, clear_marks = _cancel_payload(frozenset(('timetable_id', 'date', 'reason', 'note', 'clear_marks')))
        timetable_id = whole_number(payload.get('timetable_id'), 1000000, 'session_invalid', lower=1)
        when = date.fromisoformat(iso_date(payload.get('date'), 'session_date'))
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    return _cancel(timetable_id, when, reason, note, clear_marks)


def cancel_session(session_id):
    denied = permission_denied('attendance_manage', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    try:
        _, reason, note, clear_marks = _cancel_payload(frozenset(('reason', 'note', 'clear_marks')))
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        row = fetch_session(cursor, session_id)
    except Exception:
        current_app.logger.exception('Lecture session lookup failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)
    if not row:
        return json_error(_MESSAGES['session_missing'], 404, 'session_missing')
    return _cancel(row['timetable_id'], row['session_date'], reason, note, clear_marks)


def uncancel_session(session_id):
    denied = permission_denied('attendance_manage', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            status = restore_lecture(cursor, session_id, session.get('user_id'), today=date.today())
        except SessionNotFound:
            connection.rollback()
            return json_error(_MESSAGES['session_missing'], 404, 'session_missing')
        connection.commit()
        return json_ok({'session_id': safe_count(session_id), 'status': safe_text(status or 'removed', 12)})
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Lecture session restore failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def _defaulter_row(report):
    student = report.student
    overall = report.overall
    return {
        'student_id': safe_count(student.get('id')),
        'name': safe_text(student.get('name'), 100),
        'roll_number': safe_text(student.get('roll_number') or '', 50),
        'course_name': safe_text(student.get('course_name') or '', 100),
        'class_name': safe_text(student.get('class_name') or '', 100),
        'division_name': safe_text(student.get('division_name') or '', 50),
        'held': safe_count(overall.held),
        'countable': safe_count(overall.countable),
        'attended': safe_count(overall.attended),
        'absent': safe_count(overall.absent),
        'excused': safe_count(overall.excused),
        'not_marked': safe_count(overall.not_marked),
        'percentage': percent_value(overall.percentage),
        'classes_needed': None if report.summary.classes_needed is None else safe_count(report.summary.classes_needed),
    }


def overview():
    denied = permission_denied('attendance_view', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    threshold = request.args.get('threshold')
    if threshold is not None and parse_threshold(threshold) is None:
        return reject_input(_MESSAGES, 'session_invalid')
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        today = date.today()
        stats = period_statistics(cursor, today - timedelta(days=_OVERVIEW_DAYS), today)
        below, chosen = defaulters(cursor, threshold=threshold)
        return json_ok({
            'period_days': _OVERVIEW_DAYS,
            'total_students': safe_count(stats.get('students')),
            'total_lectures': safe_count(stats.get('lectures')),
            'total_records': safe_count(stats.get('countable')),
            'total_present': safe_count(stats.get('present')),
            'total_late': safe_count(stats.get('late')),
            'total_absent': safe_count(stats.get('absent')),
            'total_excused': safe_count(stats.get('excused')),
            'total_not_marked': safe_count(stats.get('not_marked')),
            'percentage': percent_value(stats.get('percentage')),
            'threshold': percent_value(chosen.threshold),
            'defaulter_count': safe_count(len(below)),
            'not_marked_count': safe_count(count_not_marked_sessions(cursor)),
            'defaulters': [_defaulter_row(report) for report in below[:_DEFAULTER_LIMIT]],
        })
    except Exception:
        current_app.logger.exception('Attendance overview failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def _choice_id(value):
    if value in (None, ''):
        return None
    return whole_number(value, 1000000, 'invalid_body', lower=1)


def _named_rows(cursor, table):
    if table not in ('courses', 'classes', 'divisions'):
        raise InputError('invalid_body')
    cursor.execute(f'SELECT id, name FROM {table} ORDER BY name LIMIT 300')
    return [{'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 100)} for row in cursor.fetchall()]


def record_filters(args):
    """Date is required. Course, class, and division narrow the same list the old screen used."""
    chosen = iso_date(args.get('date') or date.today().isoformat(), 'attendance_date_invalid')
    return chosen, _choice_id(args.get('course_id')), _choice_id(args.get('class_id')), _choice_id(args.get('division_id'))


def records():
    denied = permission_denied('attendance_manage', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        chosen, course_id, class_id, division_id = record_filters(request.args)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT a.id, s.roll_number, s.name AS student_name, c.name AS course_name,
                   cl.name AS class_name, d.name AS division_name,
                   a.attendance_date, a.status, a.remarks
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN courses c ON s.course_id = c.id
            JOIN classes cl ON s.class_id = cl.id
            JOIN divisions d ON s.division_id = d.id
            WHERE a.attendance_date = %s
        """
        params = [chosen]
        if course_id:
            query += ' AND s.course_id = %s'
            params.append(course_id)
        if class_id:
            query += ' AND s.class_id = %s'
            params.append(class_id)
        if division_id:
            query += ' AND s.division_id = %s'
            params.append(division_id)
        query += ' ORDER BY s.roll_number LIMIT 300'
        cursor.execute(query, params)
        rows = [
            {
                'id': safe_count(row.get('id')),
                'roll': safe_text(row.get('roll_number') or '', 30),
                'student': safe_text(row.get('student_name'), 100),
                'course': safe_text(row.get('course_name') or '', 100),
                'class_name': safe_text(row.get('class_name') or '', 100),
                'division': safe_text(row.get('division_name') or '', 50),
                'date': safe_stamp(row.get('attendance_date'))[:10],
                'status': safe_text(row.get('status') or '', 20),
                'remarks': safe_text(row.get('remarks') or '', 200),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({
            'records': rows,
            'date': chosen,
            'courses': _named_rows(cursor, 'courses'),
            'classes': _named_rows(cursor, 'classes'),
            'divisions': _named_rows(cursor, 'divisions'),
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Attendance records failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def update_record(record_id):
    denied = permission_denied('attendance_manage', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(frozenset(('status', 'remarks')))
        status = required_text(payload.get('status'), 20, 'attendance_status_invalid').title()
        if status not in _MARK_STATUSES:
            raise InputError('attendance_status_invalid')
        remarks = optional_text(payload.get('remarks'), 200, 'invalid_body')
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT id FROM attendance WHERE id = %s', [record_id])
        if not cursor.fetchone():
            return json_error(_MESSAGES['attendance_record_missing'], 404, 'attendance_record_missing')
        cursor.execute(
            'UPDATE attendance SET status = %s, remarks = %s WHERE id = %s',
            [status, remarks, record_id],
        )
        connection.commit()
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Attendance update failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def _total(value):
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return safe_count(number)


def _percent(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number < 0:
        return 0.0
    if number > 100:
        return 100.0
    return round(number, 2)


def _activity_page(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    if number < 1 or number > 10000:
        return 1
    return number


def _activity_size(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 20
    return number if number in _ACTIVITY_SIZES else 20


def _log_limit(value):
    if value in (None, ''):
        return 100
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 100
    if number < 1:
        return 1
    if number > 500:
        return 500
    return number


def faculty_filters(args):
    """Keep the overview filters. An unknown status is ignored."""
    status = args.get('status') or ''
    if status not in _FACULTY_STATUSES:
        status = ''
    query = optional_text(args.get('q'), 80, 'attendance_filters_invalid')
    date_from = iso_date(args.get('date_from'), 'attendance_date_invalid', required=False) or ''
    date_to = iso_date(args.get('date_to'), 'attendance_date_invalid', required=False) or ''
    if date_from and date_to and date_from > date_to:
        raise InputError('attendance_date_invalid')
    return {
        'q': query,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'page': _activity_page(args.get('page')),
        'per_page': _activity_size(args.get('per_page')),
    }


def mobile_filters(args):
    """Keep the student sync filters and the 1–500 row cap."""
    status = (args.get('processing_status') or '').strip().lower()
    if status not in _LOG_STATUSES:
        status = ''
    chosen = iso_date(args.get('date'), 'attendance_date_invalid', required=False) or ''
    device = optional_text(args.get('device_id'), 64, 'attendance_filters_invalid')
    student = optional_text(args.get('student_query'), 80, 'attendance_filters_invalid')
    return chosen, status, device, student, _log_limit(args.get('limit'))


def reprocess_limit(payload):
    if payload.get('limit') in (None, ''):
        return 100
    return whole_number(payload.get('limit'), 500, 'attendance_limit_invalid', lower=1)


def _empty_faculty():
    return {
        'available': False,
        'stats': {'faculty': 0, 'records': 0, 'present': 0, 'late': 0, 'absent': 0, 'percentage': 0.0},
        'today': [],
        'records': [],
        'summary': [],
        'page': 1,
        'per_page': 20,
        'total': 0,
        'total_pages': 1,
        'has_prev': False,
        'has_next': False,
    }


def _activity_row(row):
    return {
        'faculty_id': safe_count(row.get('faculty_id')),
        'faculty': safe_text(row.get('faculty_name'), 100),
        'employee_id': safe_text(row.get('employee_id') or '', 20),
        'department': safe_text(row.get('department_name') or '', 100),
        'date': safe_stamp(row.get('attendance_date'))[:10],
        'status': safe_text(row.get('status') or '', 20),
        'shift': safe_text(row.get('shift_name') or '', 80),
        'start_time': safe_clock(row.get('shift_start_time')),
        'end_time': safe_clock(row.get('shift_end_time')),
        'marked_by': safe_text(row.get('marked_by_username') or '', 50),
        'marked_at': safe_stamp(row.get('marked_at')),
        'source': safe_text(row.get('source') or '', 20),
    }


def _summary_row(row):
    return {
        'faculty_id': safe_count(row.get('faculty_id')),
        'faculty': safe_text(row.get('faculty_name'), 100),
        'employee_id': safe_text(row.get('employee_id') or '', 20),
        'department': safe_text(row.get('department_name') or '', 100),
        'shifts': _total(row.get('total_shifts')),
        'present': _total(row.get('total_present')),
        'late': _total(row.get('total_late')),
        'absent': _total(row.get('total_absent')),
        'percentage': _percent(row.get('attendance_percentage')),
    }


def faculty():
    denied = permission_denied('attendance_view_faculty', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        chosen = faculty_filters(request.args)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not _table_exists(cursor, 'faculty_attendance'):
            return json_ok(_empty_faculty())
        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT faculty_id) AS total_faculty,
                COUNT(*) AS total_records,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS total_absent,
                ROUND(
                    (SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)) * 100,
                    2
                ) AS overall_percentage
            FROM faculty_attendance
            WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            """
        )
        overall = cursor.fetchone() or {}
        cursor.execute(
            """
            SELECT
                COALESCE(NULLIF(shift_name, ''), 'General Availability') AS shift_name,
                COUNT(*) AS total_marked,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS late_count,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS absent_count
            FROM faculty_attendance
            WHERE attendance_date = CURDATE()
            GROUP BY shift_key, shift_name
            ORDER BY shift_name
            """
        )
        today = [
            {
                'shift': safe_text(row.get('shift_name'), 80),
                'marked': _total(row.get('total_marked')),
                'present': _total(row.get('present_count')),
                'late': _total(row.get('late_count')),
                'absent': _total(row.get('absent_count')),
            }
            for row in cursor.fetchall() or []
        ]
        clauses = ['1=1']
        params = []
        if chosen['status']:
            clauses.append('fa.status = %s')
            params.append(chosen['status'])
        if chosen['date_from']:
            clauses.append('fa.attendance_date >= %s')
            params.append(chosen['date_from'])
        if chosen['date_to']:
            clauses.append('fa.attendance_date <= %s')
            params.append(chosen['date_to'])
        if chosen['q']:
            like = f"%{chosen['q']}%"
            clauses.append(
                """(
                    f.name LIKE %s OR f.employee_id LIKE %s OR d.name LIKE %s
                    OR COALESCE(u.username, '') LIKE %s
                    OR COALESCE(fa.shift_name, '') LIKE %s
                    OR COALESCE(fa.shift_code, '') LIKE %s
                )"""
            )
            params.extend([like, like, like, like, like, like])
        where_sql = ' AND '.join(clauses)
        cursor.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN users u ON u.id = fa.marked_by_user_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        total = _total((cursor.fetchone() or {}).get('total_count'))
        page = chosen['page']
        per_page = chosen['per_page']
        _offset, total_pages = page_bounds(page, per_page, total, minimum_pages=1)
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * per_page
        cursor.execute(
            f"""
            SELECT
                fa.attendance_date, fa.status, fa.shift_name, fa.shift_start_time, fa.shift_end_time,
                fa.marked_at, fa.source, f.id AS faculty_id, f.name AS faculty_name, f.employee_id,
                d.name AS department_name, u.username AS marked_by_username
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN users u ON u.id = fa.marked_by_user_id
            WHERE {where_sql}
            ORDER BY fa.marked_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*params, per_page, offset]),
        )
        records = [_activity_row(row) for row in cursor.fetchall() or []]
        cursor.execute(
            """
            SELECT
                f.id AS faculty_id, f.name AS faculty_name, f.employee_id, d.name AS department_name,
                COUNT(*) AS total_shifts,
                SUM(CASE WHEN fa.status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN fa.status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN fa.status = 'Absent' THEN 1 ELSE 0 END) AS total_absent,
                ROUND(
                    (SUM(CASE WHEN fa.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)) * 100,
                    2
                ) AS attendance_percentage
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            WHERE fa.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY f.id, f.name, f.employee_id, d.name
            ORDER BY attendance_percentage ASC, f.name ASC
            LIMIT 100
            """
        )
        summary = [_summary_row(row) for row in cursor.fetchall() or []]
        return json_ok({
            'available': True,
            'stats': {
                'faculty': _total(overall.get('total_faculty')),
                'records': _total(overall.get('total_records')),
                'present': _total(overall.get('total_present')),
                'late': _total(overall.get('total_late')),
                'absent': _total(overall.get('total_absent')),
                'percentage': _percent(overall.get('overall_percentage')),
            },
            'today': today,
            'records': records,
            'summary': summary,
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Faculty attendance failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def _log_row(row):
    confidence = row.get('confidence')
    try:
        score = None if confidence is None or isinstance(confidence, bool) else round(float(confidence), 2)
    except (TypeError, ValueError):
        score = None
    if score is not None and (score < 0 or score > 100):
        score = None
    return {
        'id': safe_count(row.get('id')),
        'date': safe_stamp(row.get('attendance_date'))[:10],
        'student': safe_text(row.get('student_name') or '', 100),
        'roll': safe_text(row.get('roll_number') or '', 30),
        'course': safe_text(row.get('course_name') or '', 100),
        'class_name': safe_text(row.get('class_name') or '', 100),
        'division': safe_text(row.get('division_name') or '', 50),
        'subject': safe_text(row.get('subject_name') or '', 100),
        'status': safe_text(row.get('status') or '', 20),
        'processing': safe_text(row.get('processing_status') or '', 20),
        'device': safe_text(row.get('device_id') or '', 64),
        'marked_by': safe_text(row.get('marked_by_username') or row.get('marked_by_faculty') or '', 50),
        'confidence': score,
        'captured_at': safe_stamp(row.get('captured_at')),
        'processed_at': safe_stamp(row.get('processed_at')),
        'error': safe_text(row.get('error_message') or '', 160),
    }


def mobile():
    denied = permission_denied('attendance_view', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        chosen_date, status, device, student, limit = mobile_filters(request.args)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not _table_exists(cursor, 'attendance_logs'):
            return json_ok({
                'available': False,
                'stats': {'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
                'logs': [],
                'can_reprocess': allowed('attendance_manage'),
            })
        clauses = ['1=1']
        params = []
        if chosen_date:
            clauses.append('al.attendance_date = %s')
            params.append(chosen_date)
        if status:
            clauses.append('al.processing_status = %s')
            params.append(status)
        if device:
            clauses.append('al.device_id LIKE %s')
            params.append(f'%{device}%')
        if student:
            clauses.append('(st.name LIKE %s OR st.roll_number LIKE %s OR CAST(al.student_id AS CHAR) LIKE %s)')
            like = f'%{student}%'
            params.extend([like, like, like])
        where_sql = ' AND '.join(clauses)
        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN al.processing_status = 'processed' THEN 1 ELSE 0 END) AS processed,
                SUM(CASE WHEN al.processing_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN al.processing_status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM attendance_logs al
            LEFT JOIN students st ON st.id = al.student_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        stats = cursor.fetchone() or {}
        cursor.execute(
            f"""
            SELECT
                al.id, al.device_id, al.attendance_date, al.status, al.processing_status,
                al.confidence, al.error_message, al.captured_at, al.processed_at,
                st.name AS student_name, st.roll_number, u.username AS marked_by_username,
                f.name AS marked_by_faculty, sub.name AS subject_name, c.name AS course_name,
                cl.name AS class_name, d.name AS division_name
            FROM attendance_logs al
            LEFT JOIN students st ON st.id = al.student_id
            LEFT JOIN users u ON u.id = al.marked_by_user_id
            LEFT JOIN faculty f ON f.id = al.marked_by_faculty_id
            LEFT JOIN timetable t ON t.id = al.timetable_id
            LEFT JOIN subjects sub ON sub.id = t.subject_id
            LEFT JOIN courses c ON c.id = t.course_id
            LEFT JOIN classes cl ON cl.id = t.class_id
            LEFT JOIN divisions d ON d.id = t.division_id
            WHERE {where_sql}
            ORDER BY al.created_at DESC
            LIMIT %s
            """,
            tuple(params + [limit]),
        )
        return json_ok({
            'available': True,
            'stats': {
                'total': _total(stats.get('total')),
                'processed': _total(stats.get('processed')),
                'pending': _total(stats.get('pending')),
                'failed': _total(stats.get('failed')),
            },
            'logs': [_log_row(row) for row in cursor.fetchall() or []],
            'can_reprocess': allowed('attendance_manage'),
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Mobile attendance logs failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def reprocess_logs():
    """Retry pending and failed student logs. Counts only; the row keeps any failure note."""
    denied = permission_denied('attendance_manage', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        limit = reprocess_limit(body(frozenset(('limit',))))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not _table_exists(cursor, 'attendance_logs'):
            return json_ok({'available': False, 'retried': 0, 'processed': 0, 'failed': 0})
        cursor.execute(
            """
            SELECT *
            FROM attendance_logs
            WHERE processing_status IN ('pending', 'failed')
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        retried = 0
        processed = 0
        failed = 0
        for log_row in cursor.fetchall() or []:
            retried += 1
            try:
                _promote_log_to_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE attendance_logs
                    SET processing_status = 'processed', processed_at = NOW(), error_message = NULL
                    WHERE id = %s
                    """,
                    (log_row['id'],),
                )
                processed += 1
            except Exception:
                failed += 1
                cursor.execute(
                    """
                    UPDATE attendance_logs
                    SET processing_status = 'failed', error_message = %s
                    WHERE id = %s
                    """,
                    ('The log could not be applied.', log_row['id']),
                )
        connection.commit()
        return json_ok({'available': True, 'retried': retried, 'processed': processed, 'failed': failed})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Mobile log reprocess failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def student():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Student':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        report = student_report(cursor, user_id=session.get('user_id'))
        if report is None:
            return json_error(_MESSAGES['attendance_unavailable'], 404, 'attendance_unavailable')
        rows = []
        for subject_id, entry in report.summary.subjects.items():
            figures = entry.figures
            rows.append({
                'id': safe_count(subject_id),
                'subject': safe_text(report.subject_name(subject_id), 100),
                'held': safe_count(figures.held),
                'scheduled': safe_count(figures.countable),
                'attended': safe_count(figures.attended),
                'missed': safe_count(figures.absent),
                'excused': safe_count(figures.excused),
                'not_marked': safe_count(figures.not_marked),
                'percentage': percent_value(figures.percentage),
            })
        rows.sort(key=lambda row: (row['subject'], row['id']))
        overall = report.overall
        return json_ok({
            'subjects': rows,
            'overall': {
                'held': safe_count(overall.held),
                'scheduled': safe_count(overall.countable),
                'attended': safe_count(overall.attended),
                'missed': safe_count(overall.absent),
                'excused': safe_count(overall.excused),
                'not_marked': safe_count(overall.not_marked),
                'percentage': percent_value(overall.percentage),
            },
            'classes_needed': None if report.summary.classes_needed is None else safe_count(report.summary.classes_needed),
            'threshold': percent_value(report.summary.policy.threshold),
        })
    except Exception:
        current_app.logger.exception('Student attendance failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)
