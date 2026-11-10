"""Read-only admin dashboard counts. Same queries as the existing admin home."""

from datetime import date, datetime, timedelta

from flask import current_app, session

from data_access.admin_dashboard import fetch_department_students, fetch_faculty_workload, fetch_open_work, fetch_upcoming_holidays
from data_access.attendance_calc import count_not_marked_sessions
from data_access.invitations import fetch_invitation_stats
from core.scope import current_scope
from extensions import get_db_connection
from utils.dates import format_hhmm as format_time
from services.attendance_calc import cohort_reports, daily_trend, figures_dict, pooled_figures, policy
from api.web.responses import json_error, json_ok
from api.web.security import ADMIN_ROLES, safe_count, safe_stamp, safe_text

_REPORT_DAYS = 30
_TREND_DAYS = 14


def _total(value):
    if value is None or isinstance(value, bool):
        return 0
    try:
        return safe_count(int(value))
    except (TypeError, ValueError):
        return 0


def _percent(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 100:
        return None
    return round(number, 2)


def _hours(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if number < 0 or number > 1000:
        return 0.0
    return round(number, 1)


def clip_trend(rows):
    """Keep the latest two weeks of the attendance trend."""
    shaped = []
    for row in list(rows or [])[-_TREND_DAYS:]:
        shaped.append({
            'date': safe_text(row.get('date'), 10),
            'present': safe_count(row.get('present')),
            'late': safe_count(row.get('late')),
            'absent': safe_count(row.get('absent')),
            'percentage': _percent(row.get('percentage')),
        })
    return shaped


def _report(cursor):
    """30-day attendance figures, the overall defaulter count, and a short trend."""
    today = date.today()
    period = cohort_reports(cursor, date_from=today - timedelta(days=_REPORT_DAYS), date_to=today)
    figures = figures_dict(pooled_figures(period))
    lectures = set()
    for report in period:
        for session, _slot, _outcome, _mark in report.outcomes():
            lectures.add(session.get('id'))
    chosen = policy()
    overall = cohort_reports(cursor)
    below = 0
    for report in overall:
        value = report.overall.percentage
        if value is not None and float(value) < chosen.threshold:
            below += 1
    return {
        'present': safe_count(figures.get('present')),
        'late': safe_count(figures.get('late')),
        'absent': safe_count(figures.get('absent')),
        'excused': safe_count(figures.get('excused')),
        'not_marked': safe_count(figures.get('not_marked')),
        'countable': safe_count(figures.get('countable')),
        'lectures': safe_count(len(lectures)),
        'students': safe_count(sum(1 for report in period if report.overall.countable)),
        'percentage': _percent(figures.get('percentage')),
        'threshold': _percent(chosen.threshold) or 75.0,
        'defaulters': safe_count(below),
        'unmarked_lectures': safe_count(count_not_marked_sessions(cursor)),
        'trend': clip_trend(daily_trend(period)),
    }


def _empty_report():
    return {
        'present': 0,
        'late': 0,
        'absent': 0,
        'excused': 0,
        'not_marked': 0,
        'countable': 0,
        'lectures': 0,
        'students': 0,
        'percentage': None,
        'threshold': 75.0,
        'defaulters': 0,
        'unmarked_lectures': 0,
        'trend': [],
    }


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

            def count(query, params=()):
                cursor.execute(query, params)
                row = cursor.fetchone()
                return safe_count(row['count'] if row else 0)

            # Counts follow the chosen institution; a Super Admin with none chosen sees the organization.
            scope = current_scope(cursor)
            student_sql, student_params = scope.student_clause('s')
            course_sql, course_params = scope.course_clause('c')
            department_sql, department_params = scope.clause('institution_id')
            room_sql, room_params = scope.clause('institution_id')
            total_students = count(f"SELECT COUNT(s.id) as count FROM students s WHERE s.is_active = 1 AND {student_sql}", student_params)
            total_faculty = count(
                f"SELECT COUNT(f.id) as count FROM faculty f LEFT JOIN departments d ON d.id = f.department_id "
                f"WHERE f.is_active = 1 AND {scope.clause('d.institution_id')[0]}",
                scope.clause('d.institution_id')[1],
            )
            total_courses = count(f"SELECT COUNT(c.id) as count FROM courses c WHERE c.is_active = 1 AND {course_sql}", course_params)
            total_departments = count(f"SELECT COUNT(id) as count FROM departments WHERE is_active = 1 AND {department_sql}", department_params)
            total_rooms = count(f"SELECT COUNT(id) as count FROM rooms WHERE {room_sql}", room_params)
            total_batches = count(
                f"SELECT COUNT(cb.id) as count FROM course_batches cb JOIN courses c ON c.id = cb.course_id "
                f"WHERE cb.is_active = 1 AND {course_sql}",
                course_params,
            )

            cursor.execute(f"SELECT room_type, COUNT(*) as count FROM rooms WHERE {room_sql} GROUP BY room_type", room_params)
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

            shifts, proxy = fetch_open_work(cursor)
            invitations = fetch_invitation_stats(cursor) or {}
            departments = [
                {'name': safe_text(row.get('name'), 80), 'students': _total(row.get('student_count'))}
                for row in fetch_department_students(cursor)
            ]
            workload = [
                {
                    'name': safe_text(row.get('name'), 80),
                    'classes': _total(row.get('class_count')),
                    'hours': _hours(row.get('hours')),
                }
                for row in fetch_faculty_workload(cursor)
            ]
            holidays = [
                {'name': safe_text(row.get('name'), 80), 'date': safe_stamp(row.get('holiday_date'))[:10]}
                for row in fetch_upcoming_holidays(cursor)
            ]
            try:
                attendance = _report(cursor)
            except Exception:
                current_app.logger.exception('Dashboard attendance summary failed')
                attendance = _empty_report()

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
                'attendance': attendance,
                'pending_shifts': _total((shifts or {}).get('count')),
                'unassigned_proxy': _total((proxy or {}).get('unassigned')),
                'pending_proxy': _total((proxy or {}).get('pending')),
                'pending_invitations': _total(invitations.get('pending')),
                'departments': departments,
                'workload': workload,
                'holidays': holidays,
            })
        except Exception as exc:
            current_app.logger.exception('Dashboard summary failed: %s', exc)
            return json_error('The dashboard could not be loaded.', 500, 'dashboard_unavailable')
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()
