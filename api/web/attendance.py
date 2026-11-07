"""Attendance overview, records, faculty attendance, mobile logs, and the student view."""

from flask import current_app, session

from extensions import get_db_connection
from api.web.access import close, permission_denied
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text

_MESSAGES = {'attendance_unavailable': 'The page could not be loaded.'}


def register_attendance_routes(blueprint):
    blueprint.add_url_rule('/attendance/overview', 'attendance_overview', overview, methods=['GET'])
    blueprint.add_url_rule('/attendance/manage', 'attendance_records', records, methods=['GET'])
    blueprint.add_url_rule('/attendance/faculty', 'attendance_faculty', faculty, methods=['GET'])
    blueprint.add_url_rule('/attendance/mobile', 'attendance_mobile', mobile, methods=['GET'])
    blueprint.add_url_rule('/portal/attendance', 'attendance_student', student, methods=['GET'])


def overview():
    denied = permission_denied('attendance_view', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT student_id) AS total_students,
                COUNT(*) AS total_records,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS total_absent
            FROM attendance
            WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            """
        )
        stats = cursor.fetchone() or {}
        cursor.execute(
            """
            SELECT s.name, c.name AS course_name, soa.overall_percentage
            FROM student_overall_attendance soa
            JOIN students s ON s.id = soa.student_id
            LEFT JOIN courses c ON c.id = s.course_id
            WHERE soa.overall_percentage < 75
            ORDER BY soa.overall_percentage ASC
            LIMIT 50
            """
        )
        defaulters = [
            {
                'name': safe_text(row.get('name'), 100),
                'course_name': safe_text(row.get('course_name') or '', 100),
                'percentage': safe_count(row.get('overall_percentage')),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({
            'total_students': safe_count(stats.get('total_students')),
            'total_records': safe_count(stats.get('total_records')),
            'total_present': safe_count(stats.get('total_present')),
            'total_late': safe_count(stats.get('total_late')),
            'total_absent': safe_count(stats.get('total_absent')),
            'defaulters': defaulters,
        })
    except Exception:
        current_app.logger.exception('Attendance overview failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def records():
    denied = permission_denied('attendance_manage', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT s.name AS student_name, c.name AS course_name,
                   DATE_FORMAT(a.attendance_date, '%Y-%m-%d') AS attendance_date, a.status
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            LEFT JOIN courses c ON s.course_id = c.id
            ORDER BY a.attendance_date DESC, a.id DESC
            LIMIT 50
            """
        )
        rows = [
            {
                'student': safe_text(row.get('student_name'), 100),
                'course': safe_text(row.get('course_name') or '', 100),
                'date': safe_text(row.get('attendance_date') or '', 10),
                'status': safe_text(row.get('status') or '', 20),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'records': rows})
    except Exception:
        current_app.logger.exception('Attendance records failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def faculty():
    denied = permission_denied('attendance_view_faculty', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT f.name AS faculty_name, fa.attendance_date, fa.status
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            ORDER BY fa.attendance_date DESC
            LIMIT 50
            """
        )
        rows = [
            {
                'faculty': safe_text(row.get('faculty_name'), 100),
                'date': safe_stamp(row.get('attendance_date'))[:10],
                'status': safe_text(row.get('status') or '', 20),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'records': rows})
    except Exception:
        current_app.logger.exception('Faculty attendance failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)


def mobile():
    denied = permission_denied('attendance_view', 'attendance_unavailable', _MESSAGES['attendance_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT al.attendance_date, al.processing_status, al.status, s.name AS student_name
            FROM attendance_logs al
            LEFT JOIN students s ON s.id = al.student_id
            ORDER BY al.id DESC
            LIMIT 50
            """
        )
        rows = [
            {
                'date': safe_stamp(row.get('attendance_date'))[:10],
                'student': safe_text(row.get('student_name') or '', 100),
                'status': safe_text(row.get('status') or '', 20),
                'processing': safe_text(row.get('processing_status') or '', 20),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'logs': rows})
    except Exception:
        current_app.logger.exception('Mobile attendance logs failed')
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
        cursor.execute('SELECT id FROM students WHERE user_id = %s', (session.get('user_id'),))
        learner = cursor.fetchone()
        if not learner:
            return json_error(_MESSAGES['attendance_unavailable'], 404, 'attendance_unavailable')
        cursor.execute(
            """
            SELECT subject_name, total_lectures_scheduled, lectures_attended, lectures_missed, attendance_percentage
            FROM attendance_summary
            WHERE student_id = %s
            ORDER BY subject_name
            """,
            (learner['id'],),
        )
        rows = [
            {
                'subject': safe_text(row.get('subject_name'), 100),
                'scheduled': safe_count(row.get('total_lectures_scheduled')),
                'attended': safe_count(row.get('lectures_attended')),
                'missed': safe_count(row.get('lectures_missed')),
                'percentage': safe_count(row.get('attendance_percentage')),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'subjects': rows})
    except Exception:
        current_app.logger.exception('Student attendance failed')
        return json_error(_MESSAGES['attendance_unavailable'], 500, 'attendance_unavailable')
    finally:
        close(cursor, connection)
