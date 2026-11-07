"""Read-only admin dashboard counts. Same queries as the existing admin home."""

from datetime import datetime

from flask import current_app, session

from extensions import get_db_connection
from routes.admin_utils import format_time
from api.web.responses import json_error, json_ok
from api.web.security import ADMIN_ROLES, safe_count, safe_text


def register_dashboard_routes(blueprint):
    @blueprint.route('/dashboard/summary', methods=['GET'])
    def dashboard_summary():
        if 'user_id' not in session:
            return json_error('Authentication required.', 401, 'unauthorized')
        if session.get('role') not in ADMIN_ROLES:
            return json_error('You do not have permission to view this dashboard.', 403, 'forbidden')

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            def count(query):
                cursor.execute(query)
                row = cursor.fetchone()
                return safe_count(row['count'] if row else 0)

            total_students = count("SELECT COUNT(id) as count FROM students WHERE is_active = 1")
            total_faculty = count("SELECT COUNT(id) as count FROM faculty WHERE is_active = 1")
            total_courses = count("SELECT COUNT(id) as count FROM courses WHERE is_active = 1")
            total_departments = count("SELECT COUNT(id) as count FROM departments WHERE is_active = 1")
            total_rooms = count("SELECT COUNT(id) as count FROM rooms")
            total_batches = count("SELECT COUNT(id) as count FROM course_batches WHERE is_active = 1")

            cursor.execute("SELECT room_type, COUNT(*) as count FROM rooms GROUP BY room_type")
            room_breakdown = {}
            for row in cursor.fetchall():
                room_type = safe_text(row.get('room_type'), 40) or 'Room'
                room_breakdown[room_type] = safe_count(row.get('count'))

            cursor.execute(
                """
                SELECT day_of_week, COUNT(*) as class_count
                FROM timetable
                GROUP BY day_of_week
                ORDER BY FIELD(day_of_week, 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')
                """
            )
            allowed_days = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')
            weekly_load = {day: 0 for day in allowed_days}
            for row in cursor.fetchall():
                day = row.get('day_of_week')
                if day in weekly_load:
                    weekly_load[day] = safe_count(row.get('class_count'))

            cursor.execute(
                """
                SELECT s.theory_practical, COUNT(t.id) as count
                FROM timetable t
                JOIN subjects s ON t.subject_id = s.id
                GROUP BY s.theory_practical
                """
            )
            session_types = {}
            for row in cursor.fetchall():
                label = safe_text(row.get('theory_practical'), 40) or 'Other'
                session_types[label] = safe_count(row.get('count'))

            today = datetime.now().strftime('%A')
            cursor.execute(
                """
                SELECT t.start_time, t.end_time, s.name as subject_name,
                       f.name as faculty_name, r.room_number,
                       c.name as class_name, d.name as division_name,
                       s.theory_practical
                FROM timetable t
                JOIN subjects s ON t.subject_id = s.id
                JOIN faculty f ON t.faculty_id = f.user_id
                LEFT JOIN rooms r ON t.room_id = r.id
                JOIN classes c ON t.class_id = c.id
                LEFT JOIN divisions d ON t.division_id = d.id
                WHERE t.day_of_week = %s
                ORDER BY t.start_time
                LIMIT 50
                """,
                (today,),
            )
            today_classes = []
            for row in cursor.fetchall():
                today_classes.append({
                    'start_time': safe_text(format_time(row['start_time']), 20),
                    'end_time': safe_text(format_time(row['end_time']), 20),
                    'subject_name': safe_text(row.get('subject_name'), 160),
                    'faculty_name': safe_text(row.get('faculty_name'), 160),
                    'room_number': safe_text(row.get('room_number'), 40),
                    'class_name': safe_text(row.get('class_name'), 120),
                    'division_name': safe_text(row.get('division_name'), 80),
                    'session_type': safe_text(row.get('theory_practical'), 40),
                })

            return json_ok({
                'today_day': datetime.now().strftime('%A, %B %d, %Y'),
                'total_students': total_students,
                'total_faculty': total_faculty,
                'total_courses': total_courses,
                'total_departments': total_departments,
                'total_rooms': total_rooms,
                'total_batches': total_batches,
                'classroom_count': safe_count(room_breakdown.get('Classroom', 0)),
                'laboratory_count': safe_count(room_breakdown.get('Laboratory', 0)),
                'weekly_load': weekly_load,
                'session_types': session_types,
                'today_classes': today_classes,
            })
        except Exception as exc:
            current_app.logger.exception('Dashboard summary failed: %s', exc)
            return json_error('The dashboard could not be loaded.', 500, 'dashboard_unavailable')
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
