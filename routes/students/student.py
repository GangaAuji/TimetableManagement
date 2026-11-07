from flask import Blueprint, redirect, url_for, session
from ui.pages import render_template
from functools import wraps

from utils.dates import format_hhmm
from services.student_portal import (
    load_student_attendance,
    load_student_dashboard,
    load_student_timetable,
    load_subject_attendance,
)

student_bp = Blueprint('student', __name__, url_prefix='/student')


def format_time(time_obj):
    """Convert time/timedelta to HH:MM string format"""
    return format_hhmm(time_obj, keep_string=True)


def student_required(f):
    """Decorator to ensure the user is logged in as a student."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'Student':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@student_bp.route('/dashboard')
@student_required
def dashboard():
    """
    Student dashboard with overview statistics.
    """
    page = load_student_dashboard(session['user_id'])
    if 'error' in page:
        return render_template('student/dashboard.html', error=page['error'])
    return render_template('student/dashboard.html', **page)


@student_bp.route('/timetable')
@student_required
def timetable():
    """
    Fetches and displays the weekly timetable for the logged-in student.
    """
    page = load_student_timetable(session['user_id'])
    if 'error' in page:
        return render_template('student/timetable.html', error=page['error'])
    return render_template('student/timetable.html', timetable=page['timetable'])


@student_bp.route('/attendance')
@student_required
def attendance():
    """
    Display overall attendance statistics and subject-wise breakdown for the logged-in student.
    """
    page = load_student_attendance(session['user_id'])
    if 'error' in page:
        return render_template('student/attendance/index.html', error=page['error'])
    return render_template(
        'student/attendance/index.html',
        overall_stats=page['overall_stats'],
        subject_wise=page['subject_wise'],
        recent_records=page['recent_records'],
    )


@student_bp.route('/attendance/subject/<int:subject_id>')
@student_required
def attendance_subject(subject_id):
    """
    Display detailed attendance records for a specific subject.
    """
    page = load_subject_attendance(session['user_id'], subject_id)
    if 'error' in page:
        return render_template('student/attendance/subject.html', error=page['error'])
    return render_template(
        'student/attendance/subject.html',
        subject_stats=page['subject_stats'],
        attendance_records=page['attendance_records'],
        monthly_breakdown=page['monthly_breakdown'],
    )
