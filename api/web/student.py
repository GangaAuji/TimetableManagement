"""Student home timetable."""

from datetime import datetime

from flask import current_app, session

from extensions import get_db_connection
from api.web.access import close
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_text
from data_access.student_portal import fetch_student_timetable
from services.attendance_calc import percent_value, student_report

_MESSAGES = {'student_unavailable': 'The page could not be loaded.'}


def register_student_home_routes(blueprint):
    blueprint.add_url_rule('/portal/student', 'student_home', _home, methods=['GET'])


def _home():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Student':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT s.id, s.course_id, s.class_id, s.division_id, c.name AS course_name, cl.name AS class_name, d.name AS division_name
            FROM students s
            LEFT JOIN courses c ON c.id = s.course_id
            LEFT JOIN classes cl ON cl.id = s.class_id
            LEFT JOIN divisions d ON d.id = s.division_id
            WHERE s.user_id = %s
            """,
            (session.get('user_id'),),
        )
        student = cursor.fetchone()
        if not student:
            return json_error(_MESSAGES['student_unavailable'], 404, 'student_unavailable')
        today = datetime.now().strftime('%A')
        sessions = []
        if student.get('course_id') and student.get('class_id'):
            sessions = [
                {
                    'day': safe_text(row.get('day_of_week'), 12),
                    'start_time': safe_clock(row.get('start_time')),
                    'end_time': safe_clock(row.get('end_time')),
                    'subject': safe_text(row.get('subject_name'), 100),
                    'faculty': safe_text(row.get('faculty_name') or '', 100),
                    'room': safe_text(row.get('room_number') or '', 20),
                    'today': row.get('day_of_week') == today,
                }
                for row in fetch_student_timetable(cursor, student)
            ]
        attendance = {'total_lectures': 0, 'total_present': 0, 'total_absent': 0, 'percentage': None, 'classes_needed': None}
        try:
            report = student_report(cursor, student['id'])
            if report is not None:
                overall = report.overall
                attendance = {
                    'total_lectures': safe_count(overall.countable),
                    'total_present': safe_count(overall.attended),
                    'total_absent': safe_count(overall.absent),
                    'excused': safe_count(overall.excused),
                    'not_marked': safe_count(overall.not_marked),
                    'percentage': percent_value(overall.percentage),
                    'classes_needed': None if report.summary.classes_needed is None else safe_count(report.summary.classes_needed),
                    'threshold': percent_value(report.summary.policy.threshold),
                }
        except Exception:
            current_app.logger.exception('Student attendance summary unavailable')
        return json_ok({
            'course_name': safe_text(student.get('course_name') or '', 100),
            'class_name': safe_text(student.get('class_name') or '', 100),
            'division_name': safe_text(student.get('division_name') or '', 50),
            'today': today,
            'sessions': sessions,
            'attendance': attendance,
        })
    except Exception:
        current_app.logger.exception('Student home failed')
        return json_error(_MESSAGES['student_unavailable'], 500, 'student_unavailable')
    finally:
        close(cursor, connection)
