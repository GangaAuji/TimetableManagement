"""Admin dashboard figures. This module does not read the request."""

from datetime import datetime

from flask import current_app

from data_access.admin_dashboard import (
    count_active,
    count_rows,
    fetch_faculty_workload,
    fetch_recent_proxies,
    fetch_room_breakdown,
    fetch_session_types,
    fetch_todays_classes,
    fetch_upcoming_holidays,
    fetch_weekly_load,
)
from extensions import get_db_connection


def _empty_dashboard():
    return {
        'stats': {
            'today_day': datetime.now().strftime('%A, %B %d, %Y'),
            'total_students': 0,
            'total_faculty': 0,
            'total_courses': 0,
            'total_departments': 0,
            'total_rooms': 0,
            'total_batches': 0,
            'total_subjects': 0,
            'total_allocations': 0,
            'room_breakdown': {},
            'weekly_load': {},
            'session_types': {},
            'session_percentages': {},
            'today_classes': [],
            'recent_updates': [],
            'top_faculty': [],
        },
        'recent_proxies': [],
        'upcoming_holidays': [],
    }


def load_admin_dashboard():
    """Return the dashboard template data. A failure leaves the connection open."""
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        total_students = int(count_active(cursor, 'students')['count'])
        total_faculty = int(count_active(cursor, 'faculty')['count'])
        total_courses = int(count_active(cursor, 'courses')['count'])
        total_departments = int(count_active(cursor, 'departments')['count'])
        total_rooms = int(count_rows(cursor, 'rooms')['count'])
        total_batches = int(count_active(cursor, 'course_batches')['count'])
        total_subjects = int(count_rows(cursor, 'subjects')['count'])
        total_allocations = int(count_rows(cursor, 'faculty_allocations')['count'])
        room_breakdown = {row['room_type']: int(row['count']) for row in fetch_room_breakdown(cursor)}
        weekly_load = {row['day_of_week']: int(row['class_count']) for row in fetch_weekly_load(cursor)}
        session_types = {row['theory_practical']: int(row['count']) for row in fetch_session_types(cursor)}
        total_sessions = sum(session_types.values()) or 1
        session_percentages = {k: float(round((int(v) / total_sessions) * 100, 1)) for k, v in session_types.items()}
        today = datetime.now().strftime('%A')
        todays_classes = fetch_todays_classes(cursor, today)
        recent_proxies = fetch_recent_proxies(cursor)
        upcoming_holidays = fetch_upcoming_holidays(cursor)
        faculty_workload = fetch_faculty_workload(cursor)
        cursor.close()
        return {
            'stats': {
                'today_day': datetime.now().strftime('%A, %B %d, %Y'),
                'total_students': total_students,
                'total_faculty': total_faculty,
                'total_courses': total_courses,
                'total_departments': total_departments,
                'total_rooms': total_rooms,
                'total_batches': total_batches,
                'total_subjects': total_subjects,
                'total_allocations': total_allocations,
                'room_breakdown': room_breakdown,
                'weekly_load': weekly_load,
                'session_types': session_types,
                'session_percentages': session_percentages,
                'today_classes': todays_classes,
                'recent_updates': [],
                'top_faculty': faculty_workload,
            },
            'recent_proxies': recent_proxies,
            'upcoming_holidays': upcoming_holidays,
        }
    except Exception:
        current_app.logger.exception('Admin dashboard failed to load')
        return _empty_dashboard()
