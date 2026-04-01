from flask import Blueprint, render_template, redirect, url_for, session, jsonify
from functools import wraps
from database import get_db_connection
from datetime import datetime, timedelta

student_bp = Blueprint('student', __name__, url_prefix='/student')


def format_time(time_obj):
    """Convert time/timedelta to HH:MM string format"""
    if time_obj is None:
        return ''
    # If already a string, return as-is
    if isinstance(time_obj, str):
        return time_obj
    if isinstance(time_obj, timedelta):
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}'
    elif hasattr(time_obj, 'strftime'):
        return time_obj.strftime('%H:%M')
    else:
        return str(time_obj)


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
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get student info
        cursor.execute("""
            SELECT s.id, s.course_id, s.class_id, s.division_id, 
                   c.name as course_name, cl.name as class_name, d.name as division_name
            FROM students s
            LEFT JOIN courses c ON s.course_id = c.id
            LEFT JOIN classes cl ON s.class_id = cl.id
            LEFT JOIN divisions d ON s.division_id = d.id
            WHERE s.user_id = %s
        """, [session['user_id']])
        student_info = cursor.fetchone()
        
        if not student_info:
            return render_template('student/dashboard.html', error="Student profile not found.")
        
        student_id = student_info['id']
        course_id = student_info['course_id']
        class_id = student_info['class_id']
        division_id = student_info['division_id']
        
        # Get today's day name
        today = datetime.now().strftime('%A')
        
        # Get today's classes
        today_classes = []
        if course_id and class_id and division_id:
            cursor.execute("""
                SELECT 
                    t.id,
                    t.start_time, 
                    t.end_time, 
                    s.name as subject_name, 
                    f.name as faculty_name,
                    r.room_number
                FROM timetable t 
                JOIN subjects s ON t.subject_id = s.id 
                JOIN faculty f ON t.faculty_id = f.user_id
                LEFT JOIN rooms r ON t.room_id = r.id
                WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s 
                AND t.day_of_week = %s
                ORDER BY t.start_time
            """, (course_id, class_id, division_id, today))
            today_classes = cursor.fetchall()
            
            for entry in today_classes:
                entry['start_time'] = format_time(entry['start_time'])
                entry['end_time'] = format_time(entry['end_time'])
        
        # Get weekly total classes count
        cursor.execute("""
            SELECT COUNT(*) as count FROM timetable 
            WHERE course_id = %s AND class_id = %s AND division_id = %s
        """, (course_id, class_id, division_id))
        weekly_count = cursor.fetchone()['count'] if course_id else 0
        
        # Get overall attendance stats
        cursor.execute("""
            SELECT 
                COALESCE(total_lectures, 0) as total_lectures,
                COALESCE(total_present, 0) as total_present,
                COALESCE(total_late, 0) as total_late,
                COALESCE(total_absent, 0) as total_absent,
                COALESCE(overall_percentage, 0) as attendance_percentage
            FROM student_overall_attendance
            WHERE student_id = %s
        """, [student_id])
        attendance_stats = cursor.fetchone()
        
        if attendance_stats:
            attendance_stats['total_lectures'] = int(attendance_stats['total_lectures'] or 0)
            attendance_stats['total_present'] = int(attendance_stats['total_present'] or 0)
            attendance_stats['total_late'] = int(attendance_stats['total_late'] or 0)
            attendance_stats['total_absent'] = int(attendance_stats['total_absent'] or 0)
            attendance_stats['attendance_percentage'] = float(attendance_stats['attendance_percentage'] or 0)
        
        return render_template('student/dashboard.html',
                             student_info=student_info,
                             today_classes=today_classes,
                             weekly_count=weekly_count,
                             attendance_stats=attendance_stats,
                             now=datetime.now())
    except Exception as e:
        print(f"Error fetching student dashboard: {e}")
        import traceback
        traceback.print_exc()
        return render_template('student/dashboard.html', error="An error occurred while loading the dashboard.")
    finally:
        cursor.close()
        connection.close()


@student_bp.route('/timetable')
@student_required
def timetable():
    """
    Fetches and displays the weekly timetable for the logged-in student.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get the student's class, course, and division details
        cursor.execute("SELECT course_id, class_id, division_id FROM students WHERE user_id = %s", [session['user_id']])
        student_info = cursor.fetchone()

        if not student_info or not all(student_info.values()):
            return render_template('student/timetable.html', error="Your profile is not fully set up. Please contact an administrator.")

        course_id = student_info['course_id']
        class_id = student_info['class_id']
        division_id = student_info['division_id']

        # Fetch the weekly timetable
        cursor.execute("""
            SELECT 
                t.day_of_week, 
                t.start_time, 
                t.end_time, 
                s.name as subject_name, 
                f.name as faculty_name,
                r.room_number
            FROM timetable t 
            JOIN subjects s ON t.subject_id = s.id 
            JOIN faculty f ON t.faculty_id = f.user_id
            LEFT JOIN rooms r ON t.room_id = r.id
            WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s 
            ORDER BY 
                FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), 
                t.start_time
        """, (course_id, class_id, division_id))
        
        timetable = cursor.fetchall()
        
        # Format time fields
        for entry in timetable:
            entry['start_time'] = format_time(entry['start_time'])
            entry['end_time'] = format_time(entry['end_time'])
        
        return render_template('student/timetable.html', timetable=timetable)
    except Exception as e:
        print(f"Error fetching student timetable: {e}")
        return render_template('student/timetable.html', error="An error occurred while fetching your timetable.")
    finally:
        cursor.close()
        connection.close()


@student_bp.route('/attendance')
@student_required
def attendance():
    """
    Display overall attendance statistics and subject-wise breakdown for the logged-in student.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get student ID
        cursor.execute("SELECT id FROM students WHERE user_id = %s", [session['user_id']])
        student = cursor.fetchone()
        
        if not student:
            return render_template('student/attendance/index.html', error="Student profile not found.")
        
        student_id = student['id']
        
        # Get overall attendance statistics
        cursor.execute("""
            SELECT 
                total_lectures,
                total_present,
                total_late,
                total_absent,
                overall_percentage
            FROM student_overall_attendance
            WHERE student_id = %s
        """, [student_id])
        
        overall_stats = cursor.fetchone()
        
        # Convert Decimal values to int/float in overall stats with expected template keys
        if overall_stats:
            overall_stats['total_lectures_scheduled'] = int(overall_stats.get('total_lectures', 0) or 0)
            overall_stats['total_lectures_attended'] = int(overall_stats.get('total_present', 0) or 0)
            overall_stats['present_count'] = int(overall_stats.get('total_present', 0) or 0)
            overall_stats['late_count'] = int(overall_stats.get('total_late', 0) or 0)
            overall_stats['absent_count'] = int(overall_stats.get('total_absent', 0) or 0)
            overall_stats['attendance_percentage'] = float(overall_stats.get('overall_percentage', 0) or 0.0)
        
        # Get subject-wise attendance breakdown
        cursor.execute("""
            SELECT 
                subject_id,
                subject_name,
                total_lectures_scheduled as total_lectures,
                lectures_attended as attended_lectures,
                attendance_percentage,
                lectures_attended as present_count,
                lectures_missed as absent_count,
                lectures_late as late_count
            FROM attendance_summary
            WHERE student_id = %s
            ORDER BY subject_name
        """, [student_id])
        
        subject_wise = cursor.fetchall()
        
        # Convert Decimal values to int/float in subject-wise data
        for record in subject_wise:
            record['total_lectures'] = int(record.get('total_lectures', 0) or 0)
            record['attended_lectures'] = int(record.get('attended_lectures', 0) or 0)
            record['present_count'] = int(record.get('present_count', 0) or 0)
            record['absent_count'] = int(record.get('absent_count', 0) or 0)
            record['late_count'] = int(record.get('late_count', 0) or 0)
            record['attendance_percentage'] = float(record.get('attendance_percentage', 0) or 0.0)
        
        # Get recent attendance records (last 30 days)
        cursor.execute("""
            SELECT 
                a.attendance_date,
                a.status,
                a.remarks,
                s.name as subject_name,
                CONCAT(c.name, ' - ', cl.name, ' ', d.name) as class_info,
                COALESCE(f.name, 'Unknown') as marked_by_name
            FROM attendance a
            JOIN students st ON a.student_id = st.id
            JOIN timetable t ON a.timetable_id = t.id
            JOIN subjects s ON t.subject_id = s.id
            JOIN courses c ON t.course_id = c.id
            JOIN classes cl ON t.class_id = cl.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN faculty f ON a.marked_by = f.id OR a.marked_by = f.user_id
            WHERE a.student_id = %s
            AND t.course_id = st.course_id
            AND t.class_id = st.class_id
            AND t.division_id = st.division_id
            AND a.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            ORDER BY a.attendance_date DESC, s.name
            LIMIT 50
        """, [student_id])
        
        recent_records = cursor.fetchall()

        for record in recent_records:
            if hasattr(record.get('attendance_date'), 'strftime'):
                record['attendance_date'] = record['attendance_date'].strftime('%d %b %Y')
        
        return render_template('student/attendance/index.html',
                             overall_stats=overall_stats,
                             subject_wise=subject_wise,
                             recent_records=recent_records)
    
    except Exception as e:
        print(f"Error fetching student attendance: {e}")
        return render_template('student/attendance/index.html', 
                             error="An error occurred while fetching attendance data.")
    finally:
        cursor.close()
        connection.close()


@student_bp.route('/attendance/subject/<int:subject_id>')
@student_required
def attendance_subject(subject_id):
    """
    Display detailed attendance records for a specific subject.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get student ID
        cursor.execute("SELECT id FROM students WHERE user_id = %s", [session['user_id']])
        student = cursor.fetchone()
        
        if not student:
            return render_template('student/attendance/subject.html', error="Student profile not found.")
        
        student_id = student['id']
        
        # Get subject information and statistics
        cursor.execute("""
            SELECT 
                subject_id,
                subject_name,
                total_lectures_scheduled as total_lectures,
                lectures_attended as attended_lectures,
                attendance_percentage,
                lectures_attended as present_count,
                lectures_missed as absent_count,
                lectures_late as late_count
            FROM attendance_summary
            WHERE student_id = %s AND subject_id = %s
        """, [student_id, subject_id])
        
        subject_stats = cursor.fetchone()
        
        # Convert Decimal values to int/float
        if subject_stats:
            subject_stats['total_lectures'] = int(subject_stats.get('total_lectures', 0) or 0)
            subject_stats['attended_lectures'] = int(subject_stats.get('attended_lectures', 0) or 0)
            subject_stats['present_count'] = int(subject_stats.get('present_count', 0) or 0)
            subject_stats['absent_count'] = int(subject_stats.get('absent_count', 0) or 0)
            subject_stats['late_count'] = int(subject_stats.get('late_count', 0) or 0)
            subject_stats['attendance_percentage'] = float(subject_stats.get('attendance_percentage', 0) or 0.0)
        
        if not subject_stats:
            return render_template('student/attendance/subject.html', 
                                 error="No attendance records found for this subject.")
        
        # Get detailed attendance records for this subject
        cursor.execute("""
            SELECT 
                a.attendance_date,
                a.status,
                a.remarks,
                t.start_time,
                t.end_time,
                t.day_of_week,
                CONCAT(c.name, ' - ', cl.name, ' ', d.name) as class_info,
                COALESCE(f.name, 'Unknown') as marked_by_name,
                a.marked_at
            FROM attendance a
            JOIN students st ON a.student_id = st.id
            JOIN timetable t ON a.timetable_id = t.id
            JOIN courses c ON t.course_id = c.id
            JOIN classes cl ON t.class_id = cl.id
            JOIN divisions d ON t.division_id = d.id
            LEFT JOIN faculty f ON a.marked_by = f.id OR a.marked_by = f.user_id
            WHERE a.student_id = %s 
            AND t.course_id = st.course_id
            AND t.class_id = st.class_id
            AND t.division_id = st.division_id
            AND t.subject_id = %s
            ORDER BY a.attendance_date DESC, t.start_time DESC
        """, [student_id, subject_id])
        
        attendance_records = cursor.fetchall()

        for record in attendance_records:
            if hasattr(record.get('attendance_date'), 'strftime'):
                record['attendance_date'] = record['attendance_date'].strftime('%d %b %Y')
            if hasattr(record.get('start_time'), 'strftime'):
                record['start_time'] = record['start_time'].strftime('%I:%M %p')
            if hasattr(record.get('end_time'), 'strftime'):
                record['end_time'] = record['end_time'].strftime('%I:%M %p')
            if hasattr(record.get('marked_at'), 'strftime'):
                record['marked_at'] = record['marked_at'].strftime('%d %b %Y %I:%M %p')
        
        # Calculate monthly breakdown for the last 6 months
        cursor.execute("""
            SELECT 
                DATE_FORMAT(a.attendance_date, '%Y-%m') as month,
                COUNT(*) as total_lectures,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                ROUND((SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(*)) * 100, 2) as percentage
            FROM attendance a
            JOIN timetable t ON a.timetable_id = t.id
            WHERE a.student_id = %s 
            AND t.subject_id = %s
            AND a.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
            GROUP BY DATE_FORMAT(a.attendance_date, '%Y-%m')
            ORDER BY month DESC
        """, [student_id, subject_id])
        
        monthly_breakdown = cursor.fetchall()
        
        # Convert Decimal values to int/float
        for record in monthly_breakdown:
            record['total_lectures'] = int(record.get('total_lectures', 0) or 0)
            record['present'] = int(record.get('present', 0) or 0)
            record['late'] = int(record.get('late', 0) or 0)
            record['absent'] = int(record.get('absent', 0) or 0)
            record['percentage'] = float(record.get('percentage', 0) or 0.0)
        
        return render_template('student/attendance/subject.html',
                             subject_stats=subject_stats,
                             attendance_records=attendance_records,
                             monthly_breakdown=monthly_breakdown)
    
    except Exception as e:
        print(f"Error fetching subject attendance: {e}")
        return render_template('student/attendance/subject.html', 
                             error="An error occurred while fetching attendance data.")
    finally:
        cursor.close()
        connection.close()

