"""Teacher home and the classes assigned to the signed-in teacher."""

from datetime import datetime

from flask import current_app, get_flashed_messages, session

from extensions import get_db_connection
from api.web.access import close
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_text

_MESSAGES = {'teacher_unavailable': 'The page could not be loaded.'}


def register_teacher_routes(blueprint):
    blueprint.add_url_rule('/portal/teacher', 'teacher_home', _home, methods=['GET'])
    blueprint.add_url_rule('/portal/classes', 'teacher_classes', _classes, methods=['GET'])
    blueprint.add_url_rule('/portal/assignments', 'teacher_assignments', _assignments, methods=['GET'])


def _syllabus(value):
    text = safe_text(value or '', 300)
    if text.startswith('https://') and ' ' not in text:
        return text
    return ''


def assignment_rows(rows):
    """Shape allocated subjects. Only an https syllabus link is returned."""
    shaped = []
    for row in rows or []:
        shaped.append({
            'subject': safe_text(row.get('subject'), 100),
            'department': safe_text(row.get('department') or '', 100),
            'course': safe_text(row.get('course') or '', 100),
            'class_name': safe_text(row.get('class') or '', 100),
            'division': safe_text(row.get('division') or '', 50),
            'syllabus_url': _syllabus(row.get('syllabus_url')),
        })
    return shaped


def _teacher_only():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Teacher':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    return None


def _home():
    denied = _teacher_only()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT id, user_id, name FROM faculty WHERE id = %s OR user_id = %s LIMIT 1',
            (session.get('faculty_id') or 0, session.get('user_id')),
        )
        faculty = cursor.fetchone()
        if not faculty:
            return json_error(_MESSAGES['teacher_unavailable'], 404, 'teacher_unavailable')
        today = datetime.now().strftime('%A')
        cursor.execute(
            """
            SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            WHERE t.faculty_id = %s
            ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
            """,
            (faculty['user_id'],),
        )
        sessions = [
            {
                'day': safe_text(row.get('day_of_week'), 12),
                'start_time': safe_clock(row.get('start_time')),
                'end_time': safe_clock(row.get('end_time')),
                'subject': safe_text(row.get('subject_name'), 100),
                'class_name': safe_text(row.get('class_name'), 100),
                'division_name': safe_text(row.get('division_name'), 50),
                'today': row.get('day_of_week') == today,
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            'SELECT absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC LIMIT 20',
            (faculty['id'],),
        )
        absences = [
            {
                'date': safe_text(row.get('absence_date').isoformat()[:10] if hasattr(row.get('absence_date'), 'isoformat') else row.get('absence_date'), 10),
                'reason': safe_text(row.get('reason') or '', 200),
                'status': safe_text(row.get('status') or '', 20),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({
            'name': safe_text(faculty.get('name'), 100),
            'today': today,
            'sessions': sessions,
            'absences': absences,
        })
    except Exception:
        current_app.logger.exception('Teacher home failed')
        return json_error(_MESSAGES['teacher_unavailable'], 500, 'teacher_unavailable')
    finally:
        close(cursor, connection)


def _assignments():
    denied = _teacher_only()
    if denied:
        return denied
    try:
        from services.teacher_portal import load_assignments
        rows = load_assignments(session.get('faculty_id'))
        get_flashed_messages()
        if rows == 'missing':
            return json_error(_MESSAGES['teacher_unavailable'], 404, 'teacher_unavailable')
        return json_ok({'assignments': assignment_rows(rows)})
    except Exception:
        get_flashed_messages()
        current_app.logger.exception('Teacher assignments failed')
        return json_error(_MESSAGES['teacher_unavailable'], 500, 'teacher_unavailable')


def _classes():
    denied = _teacher_only()
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT user_id FROM faculty WHERE id = %s OR user_id = %s LIMIT 1',
            (session.get('faculty_id') or 0, session.get('user_id')),
        )
        faculty = cursor.fetchone()
        if not faculty:
            return json_error(_MESSAGES['teacher_unavailable'], 404, 'teacher_unavailable')
        cursor.execute(
            """
            SELECT DISTINCT co.name AS course_name, cl.name AS class_name, d.name AS division_name, s.name AS subject_name
            FROM timetable t
            JOIN classes cl ON t.class_id = cl.id
            JOIN divisions d ON t.division_id = d.id
            JOIN courses co ON t.course_id = co.id
            JOIN subjects s ON t.subject_id = s.id
            WHERE t.faculty_id = %s
            ORDER BY cl.name, d.name, s.name
            """,
            (faculty['user_id'],),
        )
        rows = [
            {
                'course_name': safe_text(row.get('course_name'), 100),
                'class_name': safe_text(row.get('class_name'), 100),
                'division_name': safe_text(row.get('division_name'), 50),
                'subject': safe_text(row.get('subject_name'), 100),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'classes': rows})
    except Exception:
        current_app.logger.exception('Teacher classes failed')
        return json_error(_MESSAGES['teacher_unavailable'], 500, 'teacher_unavailable')
    finally:
        close(cursor, connection)
