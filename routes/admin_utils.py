"""
Admin Utilities Module
Contains shared decorators and helper functions for admin routes.
No route definitions - all routes are in routes/admin/ modules.
"""

from flask import session, redirect, url_for, flash
from functools import wraps
from datetime import timedelta, datetime
import math

from database import get_db_connection


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
    if time_obj is None:
        return ''
    if isinstance(time_obj, timedelta):
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}"
    elif hasattr(time_obj, 'strftime'):
        return time_obj.strftime('%H:%M')
    else:
        return str(time_obj)


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
    """
    Helper for pagination of database queries
    
    Args:
        query: SQL query string (without LIMIT/OFFSET)
        params: Tuple of query parameters
        page: Current page number (1-indexed)
        per_page: Number of results per page
        
    Returns:
        Tuple of (results, total_pages)
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Correctly build the count query by finding the FROM clause in the full query
    from_clause_index = query.upper().find(' FROM ')
    if from_clause_index == -1:
        raise ValueError("Query for pagination must include a FROM clause.")
        
    count_query = f"SELECT COUNT(*) AS total {query[from_clause_index:]}"

    cursor.execute(count_query, params)
    total = cursor.fetchone()['total']
    total_pages = math.ceil(total / per_page)
    
    offset = (page - 1) * per_page
    data_query = f"{query} LIMIT %s OFFSET %s"
    cursor.execute(data_query, params + (per_page, offset))
    results = cursor.fetchall()
    cursor.close()
    return results, total_pages


# --- Helper Functions for Proxy Assignment ---
def _is_faculty_free(cursor, faculty_id, day, start_time, end_time):
    """
    Check if a faculty member is free during a specific time slot
    
    Args:
        cursor: Database cursor
        faculty_id: Faculty user ID
        day: Day of the week (e.g., 'Monday')
        start_time: Start time of the slot
        end_time: End time of the slot
        
    Returns:
        Boolean - True if faculty is free, False otherwise
    """
    cursor.execute(
        """
        SELECT 1
        FROM timetable
        WHERE faculty_id = %s
          AND day_of_week = %s
          AND NOT (end_time <= %s OR start_time >= %s)
        LIMIT 1
        """,
        (faculty_id, day, start_time, end_time),
    )
    return cursor.fetchone() is None


def _admin_find_and_assign_proxy(absent_faculty_id, absence_date):
    """
    Find and assign proxy faculty for an absent faculty member's lectures
    
    Args:
        absent_faculty_id: User ID of the absent faculty
        absence_date: Date of absence (datetime.date object)
        
    Creates proxy_log entries for all affected lectures
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    day_of_week = absence_date.strftime('%A')
    
    # Get all lectures for the absent faculty on that day
    cursor.execute(
        "SELECT id, subject_id, start_time, end_time FROM timetable WHERE faculty_id = %s AND day_of_week = %s",
        (absent_faculty_id, day_of_week),
    )
    affected_lectures = cursor.fetchall()

    for lecture in affected_lectures:
        timetable_id, subject_id, start_time, end_time = lecture['id'], lecture['subject_id'], lecture['start_time'], lecture['end_time']
        
        # Find potential proxies (faculty teaching the same subject)
        cursor.execute(
            "SELECT faculty_id FROM faculty_allocations WHERE subject_id = %s AND faculty_id != %s",
            (subject_id, absent_faculty_id),
        )
        potential_proxies = cursor.fetchall()
        
        # Find first available proxy
        assigned_proxy_id = next(
            (p['faculty_id'] for p in potential_proxies if _is_faculty_free(cursor, p['faculty_id'], day_of_week, start_time, end_time)),
            None,
        )

        status = 'ASSIGNED' if assigned_proxy_id else 'UNASSIGNED'
        
        # Create proxy log entry
        cursor.execute(
            """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status, approval_status, approval_date, approved_by)
            VALUES (%s, %s, %s, %s, %s, 'APPROVED', NOW(), %s)
            """,
            (absent_faculty_id, assigned_proxy_id, timetable_id, absence_date, status, session.get('user_id')),
        )

    connection.commit()
    cursor.close()
