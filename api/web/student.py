"""Student home timetable."""

from datetime import datetime

from flask import current_app, session

from extensions import get_db_connection
from api.web.access import close
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_text

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
        if student.get('course_id') and student.get('class_id') and student.get('division_id'):
            cursor.execute(
                """
                SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, f.name AS faculty_name, r.room_number
                FROM timetable t
                JOIN subjects s ON s.id = t.subject_id
                LEFT JOIN faculty f ON f.user_id = t.faculty_id
                LEFT JOIN rooms r ON r.id = t.room_id
                WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s
                  AND COALESCE(t.is_active, 1) = 1
                ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
                """,
                (student['course_id'], student['class_id'], student['division_id']),
            )
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
                for row in cursor.fetchall()
            ]
        attendance = {'total_lectures': 0, 'total_present': 0, 'total_absent': 0, 'percentage': 0}
        try:
            cursor.execute(
                """
                SELECT total_lectures, total_present, total_absent, overall_percentage
                FROM student_overall_attendance
                WHERE student_id = %s
                """,
                (student['id'],),
            )
            stats = cursor.fetchone() or {}
            attendance = {
                'total_lectures': safe_count(stats.get('total_lectures')),
                'total_present': safe_count(stats.get('total_present')),
                'total_absent': safe_count(stats.get('total_absent')),
                'percentage': safe_count(stats.get('overall_percentage')),
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
