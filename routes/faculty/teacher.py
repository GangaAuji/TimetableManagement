from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify, make_response
from functools import wraps
from database import get_db_connection
from datetime import datetime, date, timedelta
import csv
import io

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
    if time_obj is None:
        return ''
    if isinstance(time_obj, timedelta):
        # Convert timedelta to hours:minutes
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}'
    elif hasattr(time_obj, 'strftime'):
        # datetime.time object
        return time_obj.strftime('%H:%M')
    else:
        return str(time_obj)

# --- Proxy Logic ---
def is_faculty_available(cursor, faculty_id, day, start_time, end_time):
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


def find_and_assign_proxy(absent_faculty_id, absence_date):
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    day_of_week = absence_date.strftime('%A')
    cursor.execute(
        "SELECT id, subject_id, start_time, end_time FROM timetable WHERE faculty_id = %s AND day_of_week = %s",
        (absent_faculty_id, day_of_week),
    )
    affected_lectures = cursor.fetchall()

    for lecture in affected_lectures:
        timetable_id, subject_id, start_time, end_time = lecture['id'], lecture['subject_id'], lecture['start_time'], lecture['end_time']
        cursor.execute(
            "SELECT faculty_id FROM faculty_allocations WHERE subject_id = %s AND faculty_id != %s",
            (subject_id, absent_faculty_id),
        )
        potential_proxies = cursor.fetchall()
        assigned_proxy_id = next(
            (p['faculty_id'] for p in potential_proxies if is_faculty_available(cursor, p['faculty_id'], day_of_week, start_time, end_time)),
            None,
        )

        status = 'ASSIGNED' if assigned_proxy_id else 'UNASSIGNED'
        cursor.execute(
            """
            INSERT INTO proxy_log (original_faculty_id, proxy_faculty_id, timetable_id, absence_date, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (absent_faculty_id, assigned_proxy_id, timetable_id, absence_date, status),
        )

    connection.commit()
    cursor.close()


# --- Assignments page (classes, departments, subjects, syllabus) ---
@teacher_bp.route('/assignments')
@teacher_required
def assignments():
    faculty_id = session.get('faculty_id')  # This is faculty.id
    if not faculty_id:
        flash("Faculty profile not found.", "danger")
        return redirect(url_for('auth.logout'))
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    # Get user_id for this faculty (faculty_allocations.faculty_id stores user_id)
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    faculty_record = cursor.fetchone()
    if not faculty_record:
        flash("Faculty profile not found.", "danger")
        cursor.close()
        connection.close()
        return redirect(url_for('auth.logout'))
    
    faculty_user_id = faculty_record['user_id']
    
    cursor.execute(
        """
        SELECT dep.name AS department, crs.name AS course, c.name AS class_name, d.name AS division_name,
               s.id AS subject_id, s.name AS subject_name, COALESCE(s.syllabus_url, '') AS syllabus_url
        FROM faculty_allocations fa
        JOIN subjects s ON s.id = fa.subject_id
        JOIN classes c ON c.id = fa.class_id
        JOIN divisions d ON d.id = fa.division_id
        JOIN courses crs ON crs.id = s.course_id
        JOIN departments dep ON dep.id = crs.department_id
        WHERE fa.faculty_id = %s
        ORDER BY dep.name, crs.name, c.name, d.name, s.name
        """,
        [faculty_user_id],
    )
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    # Transform rows into friendly dicts
    assignments = [
        {
            'department': r['department'],
            'course': r['course'],
            'class': r['class_name'],
            'division': r['division_name'],
            'subject_id': r['subject_id'],
            'subject': r['subject_name'],
            'syllabus_url': r['syllabus_url'] or ''
        }
        for r in rows
    ]
    return render_template('teacher/assignments.html', assignments=assignments)


# --- Dashboard ---
@teacher_bp.route('/dashboard')
@teacher_required
def dashboard():
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    faculty_id = session.get('faculty_id')
    
    if not faculty_id:
        # Try to get faculty_id from user_id
        user_id = session.get('user_id')
        if user_id:
            cursor.execute("SELECT id, user_id, name FROM faculty WHERE user_id = %s", (user_id,))
            faculty_record = cursor.fetchone()
            if faculty_record:
                faculty_id = faculty_record['id']
                session['faculty_id'] = faculty_id
            else:
                flash("Faculty profile not found. Please contact administrator.", "danger")
                return redirect(url_for('auth.logout'))
        else:
            flash("Faculty profile not found. Please contact administrator.", "danger")
            return redirect(url_for('auth.logout'))

    # Get the user_id for this faculty (timetable uses user_id, not faculty.id)
    cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
    faculty_record = cursor.fetchone()
    if not faculty_record:
        flash("Faculty profile not found. Please contact administrator.", "danger")
        return redirect(url_for('auth.logout'))
    
    faculty_user_id = faculty_record['user_id']
    
    from datetime import datetime
    today_day = datetime.now().strftime('%A')  # Get today's day name
    
    # Fetch TODAY'S schedule only (timetable uses user_id as faculty_id)
    cursor.execute(
        """
        SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s AND t.day_of_week = %s
        ORDER BY t.start_time
        """,
        [faculty_user_id, today_day],
    )
    today_timetable = cursor.fetchall()

    # Fetch FULL WEEK's schedule (timetable uses user_id as faculty_id)
    cursor.execute(
        """
        SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name, c.name AS class_name, d.name AS division_name
        FROM timetable t
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        WHERE t.faculty_id = %s
        ORDER BY 
            CASE t.day_of_week
                WHEN 'Monday' THEN 1
                WHEN 'Tuesday' THEN 2
                WHEN 'Wednesday' THEN 3
                WHEN 'Thursday' THEN 4
                WHEN 'Friday' THEN 5
                WHEN 'Saturday' THEN 6
                WHEN 'Sunday' THEN 7
            END,
            t.start_time
        """,
        [faculty_user_id],
    )
    weekly_timetable = cursor.fetchall()

    cursor.execute(
        "SELECT absence_date, reason, status FROM faculty_absences WHERE faculty_id = %s ORDER BY absence_date DESC",
        [faculty_id],
    )
    absences = cursor.fetchall()
    
    # Fetch classes where teacher teaches with student information (timetable uses user_id)
    cursor.execute(
        """
        SELECT DISTINCT 
            cl.name as class_name, 
            d.name as division_name, 
            co.name as course_name,
            s.name as subject_name,
            COUNT(DISTINCT st.id) as student_count
        FROM timetable t
        JOIN classes cl ON t.class_id = cl.id
        JOIN divisions d ON t.division_id = d.id
        JOIN courses co ON t.course_id = co.id
        JOIN subjects s ON t.subject_id = s.id
        LEFT JOIN students st ON st.class_id = t.class_id 
            AND st.division_id = t.division_id 
            AND st.course_id = t.course_id
        WHERE t.faculty_id = %s
        GROUP BY cl.id, d.id, co.id, s.id
        ORDER BY cl.name, d.name, s.name
        """,
        [faculty_user_id],
    )
    teaching_classes = cursor.fetchall()
    
    cursor.close()
    
    return render_template('teacher/dashboard.html', 
                         timetable=today_timetable, 
                         weekly_timetable=weekly_timetable, 
                         absences=absences, 
                         teaching_classes=teaching_classes,
                         now=datetime.now())


# --- Placeholder to avoid broken nav if referenced ---
@teacher_bp.route('/attendance')
@teacher_required
def attendance():
    return render_template('teacher/placeholder.html', title='Attendance', message='Attendance module is coming soon.')
