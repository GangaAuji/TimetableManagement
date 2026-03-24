"""
Teacher Attendance Routes
Handles attendance marking and viewing for teachers
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import get_db_connection
from .teacher import teacher_required
from datetime import datetime, timedelta, date
import logging

attendance_bp = Blueprint('attendance', __name__, url_prefix='/teacher/attendance')

logger = logging.getLogger(__name__)


def format_time(time_obj):
    """Convert time/timedelta to HH:MM string format"""
    if time_obj is None:
        return ''
    if isinstance(time_obj, timedelta):
        total_seconds = int(time_obj.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}'
    elif hasattr(time_obj, 'strftime'):
        return time_obj.strftime('%H:%M')
    else:
        return str(time_obj)


@attendance_bp.route('/')
@teacher_required
def index():
    """Attendance dashboard - shows classes and subjects teacher can mark attendance for"""
    try:
        user_id = session.get('user_id')  # timetable.faculty_id stores user_id
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get all classes/subjects this teacher teaches
        cursor.execute("""
            SELECT DISTINCT 
                t.id as timetable_id,
                t.day_of_week,
                t.start_time,
                t.end_time,
                s.id as subject_id,
                s.name as subject_name,
                c.id as class_id,
                c.name as class_name,
                d.id as division_id,
                d.name as division_name,
                co.id as course_id,
                co.name as course_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            JOIN courses co ON t.course_id = co.id
            WHERE t.faculty_id = %s
            ORDER BY t.day_of_week, t.start_time
        """, (user_id,))
        
        lectures = cursor.fetchall()
        
        # Format times and check if attendance is marked for today
        today = date.today().strftime('%Y-%m-%d')
        today_formatted = date.today().strftime('%d %b %Y')
        for lecture in lectures:
            lecture['start_time'] = format_time(lecture['start_time'])
            lecture['end_time'] = format_time(lecture['end_time'])
            
            # Check if attendance is marked for today
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM attendance 
                WHERE timetable_id = %s AND attendance_date = %s
            """, (lecture['timetable_id'], today))
            
            result = cursor.fetchone()
            lecture['attendance_marked_today'] = result['count'] > 0 if result else False
        
        # Count how many lectures have attendance marked today
        marked_today_count = sum(1 for lecture in lectures if lecture['attendance_marked_today'])
        
        cursor.close()
        connection.close()
        
        return render_template('teacher/attendance/index.html', 
                             lectures=lectures, 
                             today=today_formatted,
                             marked_today_count=marked_today_count)
        
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
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get faculty.id from user_id for foreign key constraint
        cursor.execute("SELECT id FROM faculty WHERE user_id = %s", (user_id,))
        faculty_row = cursor.fetchone()
        if not faculty_row:
            flash("Faculty profile not found.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('teacher.dashboard'))
        faculty_id = faculty_row['id']
        
        # Always use today's date for marking attendance
        attendance_date = date.today().strftime('%Y-%m-%d')
        
        # Verify this lecture belongs to this teacher
        cursor.execute("""
            SELECT 
                t.id as timetable_id,
                t.day_of_week,
                t.start_time,
                t.end_time,
                s.id as subject_id,
                s.name as subject_name,
                c.id as class_id,
                c.name as class_name,
                d.id as division_id,
                d.name as division_name,
                co.id as course_id,
                co.name as course_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            JOIN courses co ON t.course_id = co.id
            WHERE t.id = %s AND t.faculty_id = %s
        """, (timetable_id, user_id))
        
        lecture = cursor.fetchone()
        
        if not lecture:
            flash("Lecture not found or you don't have permission to mark attendance for it.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('attendance.index'))
        
        # Format times
        lecture['start_time'] = format_time(lecture['start_time'])
        lecture['end_time'] = format_time(lecture['end_time'])
        
        # Get list of students in this class/division
        cursor.execute("""
            SELECT 
                s.id,
                s.name,
                s.roll_number,
                s.email
            FROM students s
            WHERE s.course_id = %s 
              AND s.class_id = %s 
              AND s.division_id = %s
            ORDER BY s.roll_number, s.name
        """, (lecture['course_id'], lecture['class_id'], lecture['division_id']))
        
        students = cursor.fetchall()
        
        # Get existing attendance for this date
        cursor.execute("""
            SELECT 
                student_id,
                status,
                remarks
            FROM attendance
            WHERE timetable_id = %s AND attendance_date = %s
        """, (timetable_id, attendance_date))
        
        existing_attendance = {row['student_id']: {'status': row['status'], 'remarks': row['remarks']} 
                              for row in cursor.fetchall()}
        
        # Check if attendance is already marked (at least one student has attendance)
        attendance_already_marked = len(existing_attendance) > 0
        
        # Merge existing attendance with student list
        for student in students:
            if student['id'] in existing_attendance:
                student['attendance_status'] = existing_attendance[student['id']]['status']
                student['remarks'] = existing_attendance[student['id']]['remarks']
            else:
                student['attendance_status'] = None
                student['remarks'] = None
        
        cursor.close()
        connection.close()
        
        return render_template('teacher/attendance/mark.html', 
                             lecture=lecture, 
                             students=students,
                             attendance_date=attendance_date,
                             attendance_already_marked=attendance_already_marked)
        
    except Exception as e:
        logger.error(f"Error loading mark attendance page: {str(e)}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('attendance.index'))


@attendance_bp.route('/mark/<int:timetable_id>', methods=['POST'])
@teacher_required
def save_attendance(timetable_id):
    """Save attendance marks for students"""
    connection = None
    try:
        user_id = session.get('user_id')  # timetable.faculty_id stores user_id
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get faculty.id from user_id for foreign key constraint
        cursor.execute("SELECT id FROM faculty WHERE user_id = %s", (user_id,))
        faculty_row = cursor.fetchone()
        if not faculty_row:
            flash("Faculty profile not found.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('attendance.index'))
        faculty_id = faculty_row['id']
        
        # Verify this lecture belongs to this teacher
        cursor.execute("SELECT id FROM timetable WHERE id = %s AND faculty_id = %s", 
                      (timetable_id, user_id))
        
        if not cursor.fetchone():
            flash("Unauthorized access.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('attendance.index'))
        
        attendance_date = request.form.get('attendance_date')
        
        if not attendance_date:
            flash("Attendance date is required.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('attendance.mark_attendance', timetable_id=timetable_id))
        
        # Get all student IDs from form
        saved_count = 0
        for key, value in request.form.items():
            if key.startswith('status_'):
                student_id = int(key.split('_')[1])
                status = value
                remarks = request.form.get(f'remarks_{student_id}', '')
                
                # Insert or update attendance
                cursor.execute("""
                    INSERT INTO attendance (student_id, timetable_id, attendance_date, status, marked_by, remarks)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        status = VALUES(status),
                        marked_by = VALUES(marked_by),
                        remarks = VALUES(remarks),
                        marked_at = NOW()
                """, (student_id, timetable_id, attendance_date, status, faculty_id, remarks))
                
                saved_count += 1
        
        connection.commit()
        cursor.close()
        connection.close()
        
        flash(f"Attendance saved successfully for {saved_count} students!", "success")
        return redirect(url_for('attendance.index'))
        
    except Exception as e:
        if connection:
            connection.rollback()
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
    """View attendance summary reports for classes taught by teacher"""
    try:
        user_id = session.get('user_id')  # timetable.faculty_id stores user_id
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get filter parameters
        subject_id = request.args.get('subject_id', type=int)
        class_id = request.args.get('class_id', type=int)
        division_id = request.args.get('division_id', type=int)
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Get all classes/subjects this teacher teaches for filters
        cursor.execute("""
            SELECT DISTINCT 
                s.id as subject_id,
                s.name as subject_name,
                c.id as class_id,
                c.name as class_name,
                d.id as division_id,
                d.name as division_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            WHERE t.faculty_id = %s
            ORDER BY c.name, d.name, s.name
        """, (user_id,))
        
        filter_options = cursor.fetchall()
        
        # Get attendance report if filters selected
        attendance_data = []
        if subject_id and class_id and division_id:
            # Build date filter
            date_filter = ""
            params = [class_id, division_id, subject_id, user_id]
            if date_from and date_to:
                date_filter = "AND a.attendance_date BETWEEN %s AND %s"
                params.extend([date_from, date_to])
            elif date_from:
                date_filter = "AND a.attendance_date >= %s"
                params.append(date_from)
            elif date_to:
                date_filter = "AND a.attendance_date <= %s"
                params.append(date_to)
            
            cursor.execute(f"""
                SELECT 
                    s.id as student_id,
                    s.name as student_name,
                    s.roll_number,
                    COUNT(DISTINCT a.id) as total_marked,
                    SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_count,
                    SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late_count,
                    SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent_count,
                    ROUND(
                        (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) * 100.0) / 
                        NULLIF(COUNT(DISTINCT a.id), 0), 
                        2
                    ) as attendance_percentage
                FROM students s
                LEFT JOIN attendance a ON a.student_id = s.id
                LEFT JOIN timetable t ON t.id = a.timetable_id
                WHERE s.class_id = %s 
                  AND s.division_id = %s
                  AND (t.subject_id = %s OR a.id IS NULL)
                  AND t.faculty_id = %s
                  {date_filter}
                GROUP BY s.id
                ORDER BY s.roll_number, s.name
            """, tuple(params))
            
            attendance_data = cursor.fetchall()
            
            # Convert Decimal values to int/float to prevent Decimal arithmetic issues in template
            for record in attendance_data:
                record['total_marked'] = int(record['total_marked']) if record['total_marked'] else 0
                record['present_count'] = int(record['present_count']) if record['present_count'] else 0
                record['late_count'] = int(record['late_count']) if record['late_count'] else 0
                record['absent_count'] = int(record['absent_count']) if record['absent_count'] else 0
                record['attendance_percentage'] = float(record['attendance_percentage']) if record['attendance_percentage'] else 0.0
        
        cursor.close()
        connection.close()
        
        return render_template('teacher/attendance/attendance_report.html',
                             filter_options=filter_options,
                             attendance_data=attendance_data,
                             selected_subject=subject_id,
                             selected_class=class_id,
                             selected_division=division_id,
                             date_from=date_from,
                             date_to=date_to)
        
    except Exception as e:
        logger.error(f"Error loading attendance report: {str(e)}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('attendance.index'))


@attendance_bp.route('/history/<int:timetable_id>')
@teacher_required
def attendance_history(timetable_id):
    """View attendance history for a specific lecture"""
    try:
        user_id = session.get('user_id')  # timetable.faculty_id stores user_id
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Verify access
        cursor.execute("""
            SELECT 
                t.id, s.name as subject_name, c.name as class_name, d.name as division_name
            FROM timetable t
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            WHERE t.id = %s AND t.faculty_id = %s
        """, (timetable_id, user_id))
        
        lecture = cursor.fetchone()
        if not lecture:
            flash("Unauthorized access.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('attendance.index'))
        
        # Get attendance history
        cursor.execute("""
            SELECT 
                a.attendance_date,
                COUNT(DISTINCT a.student_id) as total_students,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                MAX(a.marked_at) as marked_at
            FROM attendance a
            WHERE a.timetable_id = %s
            GROUP BY a.attendance_date
            ORDER BY a.attendance_date DESC
            LIMIT 50
        """, (timetable_id,))
        
        history = cursor.fetchall()
        
        # Convert Decimal values to int to prevent Decimal * float issues in template
        for record in history:
            record['total_students'] = int(record['total_students']) if record['total_students'] else 0
            record['present'] = int(record['present']) if record['present'] else 0
            record['late'] = int(record['late']) if record['late'] else 0
            record['absent'] = int(record['absent']) if record['absent'] else 0
        
        cursor.close()
        connection.close()
        
        return render_template('teacher/attendance/history.html',
                             lecture=lecture,
                             history=history)
        
    except Exception as e:
        logger.error(f"Error loading attendance history: {str(e)}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('attendance.index'))
