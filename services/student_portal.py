"""Student dashboard, timetable, and attendance. This module does not read the request.

Attendance figures come from services.attendance_calc (held lectures, the
roster rule, the institution's policy). Nothing here reads the two legacy
views.
"""

import traceback
from datetime import datetime, timedelta

from data_access.student_portal import (
    count_weekly_classes,
    fetch_student_id,
    fetch_student_profile,
    fetch_student_section,
    fetch_student_timetable,
    fetch_today_classes,
)
from extensions import get_db_connection
from services.attendance_calc import figures_dict, monthly_breakdown, outcome_label, percent_value, student_report
from utils.dates import format_hhmm

RECENT_DAYS = 30


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _clock(value):
    return format_hhmm(value, keep_string=True)


def _overall(report):
    """The overall figures plus the projection, in the keys the screens use."""
    stats = figures_dict(report.overall)
    stats['classes_needed'] = report.summary.classes_needed
    stats['classes_that_can_be_missed'] = report.summary.classes_that_can_be_missed
    stats['threshold'] = percent_value(report.summary.policy.threshold)
    return stats


def load_student_dashboard(user_id):
    """Return the dashboard context, or an error string."""
    connection, cursor = _cursor()
    try:
        student_info = fetch_student_profile(cursor, user_id)
        if not student_info:
            return {'error': 'Student profile not found.'}
        today = datetime.now().strftime('%A')
        today_classes = []
        weekly_count = 0
        if student_info['course_id'] and student_info['class_id']:
            today_classes = fetch_today_classes(cursor, student_info, today)
            for entry in today_classes:
                entry['start_time'] = _clock(entry['start_time'])
                entry['end_time'] = _clock(entry['end_time'])
            weekly_count = count_weekly_classes(cursor, student_info)['count']
        report = student_report(cursor, student_info['id'])
        return {
            'student_info': student_info,
            'today_classes': today_classes,
            'weekly_count': weekly_count,
            'attendance_stats': _overall(report) if report else None,
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
        if not student_info or not student_info.get('course_id') or not student_info.get('class_id'):
            return {'error': 'Your profile is not fully set up. Please contact an administrator.'}
        timetable = fetch_student_timetable(cursor, student_info)
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


def _subject_rows(report):
    result = []
    for subject_id, entry in report.summary.subjects.items():
        row = figures_dict(entry.figures)
        row['subject_id'] = subject_id
        row['subject_name'] = report.subject_name(subject_id)
        row['components'] = list(entry.components)
        result.append(row)
    result.sort(key=lambda row: (row['subject_name'], row['subject_id']))
    return result


def _record(session, slot, outcome, mark):
    return {
        'session_id': session['id'],
        'attendance_date': session['session_date'],
        'status': outcome_label(outcome),
        'remarks': (mark or {}).get('remarks') or '',
        'subject_name': slot.get('subject_name') or '',
        'start_time': slot.get('start_time'),
        'end_time': slot.get('end_time'),
        'day_of_week': slot.get('day_of_week'),
        'marked_by_name': (mark or {}).get('marked_by_name') or '',
        'marked_at': (mark or {}).get('marked_at') or session.get('marked_at'),
    }


def load_student_attendance(user_id):
    """Return attendance context, or an error string."""
    connection, cursor = _cursor()
    try:
        student = fetch_student_id(cursor, user_id)
        if not student:
            return {'error': 'Student profile not found.'}
        report = student_report(cursor, student['id'])
        if report is None:
            return {'error': 'Student profile not found.'}
        since = datetime.now().date() - timedelta(days=RECENT_DAYS)
        recent = [
            _record(session, slot, outcome, mark)
            for session, slot, outcome, mark in reversed(report.outcomes())
            if session['session_date'] >= since
        ]
        return {
            'overall_stats': _overall(report),
            'components': {name: figures_dict(figures) for name, figures in report.summary.components.items()},
            'subject_wise': _subject_rows(report),
            'recent_records': recent[:50],
        }
    except Exception as exc:
        print(f"Error fetching student attendance: {exc}")
        traceback.print_exc()
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
        report = student_report(cursor, student['id'])
        if report is None or subject_id not in report.summary.subjects:
            return {'error': 'No attendance records found for this subject.'}
        entry = report.summary.subjects[subject_id]
        subject_stats = figures_dict(entry.figures)
        subject_stats['subject_id'] = subject_id
        subject_stats['subject_name'] = report.subject_name(subject_id)
        subject_stats['components'] = list(entry.components)
        subject_stats['threshold'] = percent_value(report.summary.policy.threshold)
        records = [_record(session, slot, outcome, mark) for session, slot, outcome, mark in reversed(report.outcomes(subject_id))]
        return {
            'subject_stats': subject_stats,
            'attendance_records': records,
            'monthly_breakdown': monthly_breakdown(report, subject_id),
        }
    except Exception as exc:
        print(f"Error fetching subject attendance: {exc}")
        traceback.print_exc()
        return {'error': 'An error occurred while fetching attendance data.'}
    finally:
        cursor.close()
        connection.close()
