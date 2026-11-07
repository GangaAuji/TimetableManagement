from flask import Blueprint, redirect, url_for, session, flash
from ui.pages import render_template
from functools import wraps
from datetime import datetime

from utils.dates import format_hhmm
from services.teacher_portal import find_and_assign_proxy, is_faculty_available, load_assignments, load_teacher_dashboard

teacher_bp = Blueprint('teacher', __name__, url_prefix='/teacher')

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Ensure only logged-in teachers with a bound faculty profile can access
        if 'role' not in session or session['role'] != 'Teacher':
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('auth.login'))
        if 'faculty_id' not in session or not session.get('faculty_id'):
            flash("Faculty profile not found. Please contact administrator.", "danger")
            # Log the user out to reset inconsistent session state
            return redirect(url_for('auth.logout'))
        return f(*args, **kwargs)
    return decorated_function

# --- Utility function for time formatting ---
def format_time(time_obj):
    """Convert time/timedelta to HH:MM string format"""
    return format_hhmm(time_obj)


# --- Assignments page (classes, departments, subjects, syllabus) ---
@teacher_bp.route('/assignments')
@teacher_required
def assignments():
    rows = load_assignments(session.get('faculty_id'))
    if rows == 'missing':
        return redirect(url_for('auth.logout'))
    return render_template('teacher/assignments.html', assignments=rows)


# --- Dashboard ---
@teacher_bp.route('/dashboard')
@teacher_required
def dashboard():
    page = load_teacher_dashboard(session)
    if page == 'missing':
        return redirect(url_for('auth.logout'))
    return render_template('teacher/dashboard.html',
                         timetable=page['timetable'],
                         weekly_timetable=page['weekly_timetable'],
                         absences=page['absences'],
                         teaching_classes=page['teaching_classes'],
                         now=datetime.now())


# --- Placeholder to avoid broken nav if referenced ---
@teacher_bp.route('/attendance')
@teacher_required
def attendance():
    return render_template('teacher/placeholder.html', title='Attendance', message='Attendance module is coming soon.')
