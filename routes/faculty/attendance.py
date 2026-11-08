"""
Teacher Attendance Routes
Handles attendance marking and viewing for teachers
"""
from flask import Blueprint, request, redirect, url_for, flash, session
from ui.pages import render_template
from .teacher import teacher_required
from datetime import datetime, date

from utils.dates import format_hhmm
import logging

from services.teacher_attendance import (
    load_attendance_history,
    load_attendance_index,
    load_mark_page,
    save_teacher_attendance,
)

attendance_bp = Blueprint('attendance', __name__, url_prefix='/teacher/attendance')

logger = logging.getLogger(__name__)


def format_time(time_obj):
    """Convert time/timedelta to HH:MM string format"""
    return format_hhmm(time_obj)


@attendance_bp.route('/')
@teacher_required
def index():
    """Attendance dashboard - shows classes and subjects teacher can mark attendance for"""
    try:
        user_id = session.get('user_id')  # timetable.faculty_id stores user_id
        page = load_attendance_index(user_id)
        return render_template('teacher/attendance/index.html',
                             lectures=page['lectures'],
                             today=page['today'],
                             marked_today_count=page['marked_today_count'])
    except Exception as e:
        logger.error(f"Error loading attendance dashboard: {str(e)}")
        flash(f"Error loading attendance dashboard: {str(e)}", "danger")
        return redirect(url_for('teacher.dashboard'))


@attendance_bp.route('/mark/<int:timetable_id>')
@teacher_required
def mark_attendance(timetable_id):
    """Show attendance marking page for a specific lecture"""
    try:
        user_id = session.get('user_id')  # timetable.faculty_id stores user_id
        page = load_mark_page(user_id, timetable_id)
        if page == 'missing':
            return redirect(url_for('teacher.dashboard'))
        if page == 'denied':
            return redirect(url_for('attendance.index'))
        return render_template('teacher/attendance/mark.html',
                             lecture=page['lecture'],
                             students=page['students'],
                             attendance_date=page['attendance_date'],
                             attendance_already_marked=page['attendance_already_marked'])
    except Exception as e:
        logger.error(f"Error loading mark attendance page: {str(e)}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('attendance.index'))


@attendance_bp.route('/mark/<int:timetable_id>', methods=['POST'])
@teacher_required
def save_attendance(timetable_id):
    """Save attendance marks for students"""
    try:
        user_id = session.get('user_id')  # timetable.faculty_id stores user_id
        result = save_teacher_attendance(user_id, timetable_id, request.form)
        if result == 'missing':
            return redirect(url_for('attendance.index'))
        if result == 'denied':
            return redirect(url_for('attendance.index'))
        if result == 'date' or result == 'student':
            return redirect(url_for('attendance.mark_attendance', timetable_id=timetable_id))
        flash(f"Attendance saved successfully for {result} students!", "success")
        return redirect(url_for('attendance.index'))
    except Exception as e:
        logger.error(f"Error saving attendance: {str(e)}")
        flash(f"Error saving attendance: {str(e)}", "danger")
        return redirect(url_for('attendance.mark_attendance', timetable_id=timetable_id))


@attendance_bp.route('/report')
@teacher_required
def attendance_report():
    """Generic reports page with multiple report types"""
    return render_template('teacher/attendance/reports.html')


@attendance_bp.route('/report/attendance-report')
@teacher_required
def attendance_summary_report():
    """The React shell; the per-lecture report lives at /portal/attendance/history/<id>."""
    return render_template('teacher/attendance/attendance_report.html')


@attendance_bp.route('/history/<int:timetable_id>')
@teacher_required
def attendance_history(timetable_id):
    """View attendance history for a specific lecture"""
    try:
        user_id = session.get('user_id')  # timetable.faculty_id stores user_id
        page = load_attendance_history(user_id, timetable_id)
        if page == 'denied':
            return redirect(url_for('attendance.index'))
        return render_template('teacher/attendance/history.html',
                             lecture=page['lecture'],
                             history=page['history'])
    except Exception as e:
        logger.error(f"Error loading attendance history: {str(e)}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('attendance.index'))
