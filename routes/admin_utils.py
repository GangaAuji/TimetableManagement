"""
Admin Utilities Module
Contains shared decorators and helper functions for admin routes.
No route definitions - all routes are in routes/admin/ modules.
"""

from flask import session, redirect, url_for, flash
from functools import wraps
from datetime import datetime

from utils.dates import format_hhmm

from services.admin_queries import assign_admin_proxy, faculty_is_free, query_page


# --- Decorators ---
def admin_required(f):
    """Decorator to ensure only Admin, Super Admin, and HOD can access admin pages"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow Admin, Super Admin, and HOD to access admin pages
        if 'role' not in session or session['role'] not in ('Admin', 'Super Admin', 'HOD'):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('auth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# --- Utility Functions ---
def format_time(time_obj):
    """Convert time/timedelta to HH:MM string format"""
    return format_hhmm(time_obj)


def get_time_ago(timestamp):
    """Convert timestamp to human-readable time ago format"""
    if timestamp is None:
        return 'Unknown'
    now = datetime.now()
    diff = now - timestamp
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return 'Just now'
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f'{minutes} minute{"s" if minutes != 1 else ""} ago'
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f'{hours} hour{"s" if hours != 1 else ""} ago'
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f'{days} day{"s" if days != 1 else ""} ago'
    else:
        return timestamp.strftime('%b %d, %Y')


def paginate(query, params, page, per_page=10):
    """Return one page of rows and the page count."""
    return query_page(query, params, page, per_page)


def _is_faculty_free(cursor, faculty_id, day, start_time, end_time):
    """Return whether a faculty member has no overlapping timetable row."""
    return faculty_is_free(cursor, faculty_id, day, start_time, end_time)


def _admin_find_and_assign_proxy(absent_faculty_id, absence_date):
    """Assign a proxy for each lecture on the absence weekday."""
    assign_admin_proxy(absent_faculty_id, absence_date, session)
