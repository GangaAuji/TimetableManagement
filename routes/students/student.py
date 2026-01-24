from flask import Blueprint, render_template, redirect, url_for, session
from functools import wraps
from database import get_db_connection

student_bp = Blueprint('student', __name__, url_prefix='/student')

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
    Fetches and displays the timetable for the logged-in student.
    It retrieves the student's class details and then queries the timetable.
    """
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        # Get the student's class, course, and division details from their user ID
        cursor.execute("SELECT course_id, class_id, division_id FROM students WHERE user_id = %s", [session['user_id']])
        student_info = cursor.fetchone()

        # Handle cases where student profile might not be fully configured
        if not student_info or not all(student_info.values()):
            return render_template('student/dashboard.html', error="Your profile is not fully set up. Please contact an administrator.")

        course_id = student_info['course_id']
        class_id = student_info['class_id']
        division_id = student_info['division_id']

        # Fetch the timetable based on the student's details
        # Note: timetable.faculty_id stores user_id, not faculty.id
        cursor.execute("""
            SELECT 
                t.day_of_week, 
                t.start_time, 
                t.end_time, 
                s.name as subject_name, 
                f.name as faculty_name
            FROM timetable t 
            JOIN subjects s ON t.subject_id = s.id 
            JOIN faculty f ON t.faculty_id = f.user_id
            WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s 
            ORDER BY 
                FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), 
                t.start_time
        """, (course_id, class_id, division_id))
        
        timetable = cursor.fetchall()
        
        return render_template('student/dashboard.html', timetable=timetable)
    except Exception as e:
        # Log the error for debugging
        print(f"Error fetching student dashboard: {e}")
        return render_template('student/dashboard.html', error="An error occurred while fetching your timetable.")
    finally:

        cursor.close()

        connection.close()

