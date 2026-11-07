"""Student dashboard, timetable, and attendance. This module does not read the request."""

import traceback
from datetime import datetime

from data_access.student_portal import (
    count_weekly_classes,
    fetch_attendance_totals,
    fetch_monthly_attendance,
    fetch_overall_attendance,
    fetch_recent_attendance,
    fetch_student_id,
    fetch_student_profile,
    fetch_student_section,
    fetch_student_timetable,
    fetch_subject_attendance,
    fetch_subject_records,
    fetch_subject_stats,
    fetch_today_classes,
)
from extensions import get_db_connection
from utils.dates import format_hhmm


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _clock(value):
    return format_hhmm(value, keep_string=True)


def load_student_dashboard(user_id):
    """Return the dashboard context, or an error string."""
    connection, cursor = _cursor()
    try:
        student_info = fetch_student_profile(cursor, user_id)
        if not student_info:
            return {'error': 'Student profile not found.'}
        student_id = student_info['id']
        course_id = student_info['course_id']
        class_id = student_info['class_id']
        division_id = student_info['division_id']
        today = datetime.now().strftime('%A')
        today_classes = []
        if course_id and class_id and division_id:
            today_classes = fetch_today_classes(cursor, course_id, class_id, division_id, today)
            for entry in today_classes:
                entry['start_time'] = _clock(entry['start_time'])
                entry['end_time'] = _clock(entry['end_time'])
        weekly_row = count_weekly_classes(cursor, course_id, class_id, division_id)
        weekly_count = weekly_row['count'] if course_id else 0
        attendance_stats = fetch_overall_attendance(cursor, student_id)
        if attendance_stats:
            attendance_stats['total_lectures'] = int(attendance_stats['total_lectures'] or 0)
            attendance_stats['total_present'] = int(attendance_stats['total_present'] or 0)
            attendance_stats['total_late'] = int(attendance_stats['total_late'] or 0)
            attendance_stats['total_absent'] = int(attendance_stats['total_absent'] or 0)
            attendance_stats['attendance_percentage'] = float(attendance_stats['attendance_percentage'] or 0)
        return {
            'student_info': student_info,
            'today_classes': today_classes,
            'weekly_count': weekly_count,
            'attendance_stats': attendance_stats,
            'now': datetime.now(),
        }
    except Exception as exc:
        print(f"Error fetching student dashboard: {exc}")
        traceback.print_exc()
        return {'error': 'An error occurred while loading the dashboard.'}
    finally:
        cursor.close()
        connection.close()


def load_student_timetable(user_id):
    """Return the timetable context, or an error string."""
    connection, cursor = _cursor()
    try:
        student_info = fetch_student_section(cursor, user_id)
        if not student_info or not all(student_info.values()):
            return {'error': 'Your profile is not fully set up. Please contact an administrator.'}
        timetable = fetch_student_timetable(
            cursor,
            student_info['course_id'],
            student_info['class_id'],
            student_info['division_id'],
        )
        for entry in timetable:
            entry['start_time'] = _clock(entry['start_time'])
            entry['end_time'] = _clock(entry['end_time'])
        return {'timetable': timetable}
    except Exception as exc:
        print(f"Error fetching student timetable: {exc}")
        return {'error': 'An error occurred while fetching your timetable.'}
    finally:
        cursor.close()
        connection.close()


def load_student_attendance(user_id):
    """Return attendance context, or an error string."""
    connection, cursor = _cursor()
    try:
        student = fetch_student_id(cursor, user_id)
        if not student:
            return {'error': 'Student profile not found.'}
        student_id = student['id']
        overall_stats = fetch_attendance_totals(cursor, student_id)
        if overall_stats:
            overall_stats['total_lectures_scheduled'] = int(overall_stats.get('total_lectures', 0) or 0)
            overall_stats['total_lectures_attended'] = int(overall_stats.get('total_present', 0) or 0)
            overall_stats['present_count'] = int(overall_stats.get('total_present', 0) or 0)
            overall_stats['late_count'] = int(overall_stats.get('total_late', 0) or 0)
            overall_stats['absent_count'] = int(overall_stats.get('total_absent', 0) or 0)
            overall_stats['attendance_percentage'] = float(overall_stats.get('overall_percentage', 0) or 0.0)
        subject_wise = fetch_subject_attendance(cursor, student_id)
        for record in subject_wise:
            record['total_lectures'] = int(record.get('total_lectures', 0) or 0)
            record['attended_lectures'] = int(record.get('attended_lectures', 0) or 0)
            record['present_count'] = int(record.get('present_count', 0) or 0)
            record['absent_count'] = int(record.get('absent_count', 0) or 0)
            record['late_count'] = int(record.get('late_count', 0) or 0)
            record['attendance_percentage'] = float(record.get('attendance_percentage', 0) or 0.0)
        recent_records = fetch_recent_attendance(cursor, student_id)
        for record in recent_records:
            if hasattr(record.get('attendance_date'), 'strftime'):
                record['attendance_date'] = record['attendance_date'].strftime('%d %b %Y')
        return {
            'overall_stats': overall_stats,
            'subject_wise': subject_wise,
            'recent_records': recent_records,
        }
    except Exception as exc:
        print(f"Error fetching student attendance: {exc}")
        return {'error': 'An error occurred while fetching attendance data.'}
    finally:
        cursor.close()
        connection.close()


def load_subject_attendance(user_id, subject_id):
    """Return one subject's attendance, or an error string."""
    connection, cursor = _cursor()
    try:
        student = fetch_student_id(cursor, user_id)
        if not student:
            return {'error': 'Student profile not found.'}
        student_id = student['id']
        subject_stats = fetch_subject_stats(cursor, student_id, subject_id)
        if subject_stats:
            subject_stats['total_lectures'] = int(subject_stats.get('total_lectures', 0) or 0)
            subject_stats['attended_lectures'] = int(subject_stats.get('attended_lectures', 0) or 0)
            subject_stats['present_count'] = int(subject_stats.get('present_count', 0) or 0)
            subject_stats['absent_count'] = int(subject_stats.get('absent_count', 0) or 0)
            subject_stats['late_count'] = int(subject_stats.get('late_count', 0) or 0)
            subject_stats['attendance_percentage'] = float(subject_stats.get('attendance_percentage', 0) or 0.0)
        if not subject_stats:
            return {'error': 'No attendance records found for this subject.'}
        attendance_records = fetch_subject_records(cursor, student_id, subject_id)
        for record in attendance_records:
            if hasattr(record.get('attendance_date'), 'strftime'):
                record['attendance_date'] = record['attendance_date'].strftime('%d %b %Y')
            if hasattr(record.get('start_time'), 'strftime'):
                record['start_time'] = record['start_time'].strftime('%I:%M %p')
            if hasattr(record.get('end_time'), 'strftime'):
                record['end_time'] = record['end_time'].strftime('%I:%M %p')
            if hasattr(record.get('marked_at'), 'strftime'):
                record['marked_at'] = record['marked_at'].strftime('%d %b %Y %I:%M %p')
        monthly_breakdown = fetch_monthly_attendance(cursor, student_id, subject_id)
        for record in monthly_breakdown:
            record['total_lectures'] = int(record.get('total_lectures', 0) or 0)
            record['present'] = int(record.get('present', 0) or 0)
            record['late'] = int(record.get('late', 0) or 0)
            record['absent'] = int(record.get('absent', 0) or 0)
            record['percentage'] = float(record.get('percentage', 0) or 0.0)
        return {
            'subject_stats': subject_stats,
            'attendance_records': attendance_records,
            'monthly_breakdown': monthly_breakdown,
        }
    except Exception as exc:
        print(f"Error fetching subject attendance: {exc}")
        return {'error': 'An error occurred while fetching attendance data.'}
    finally:
        cursor.close()
        connection.close()
