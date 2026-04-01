from flask import session, redirect, url_for, flash, render_template, request
from database import get_db_connection
from .teacher import teacher_bp, teacher_required, format_time

@teacher_bp.route('/my-shifts')
@teacher_required
def my_shifts():
    """View assigned shifts and availability"""
    faculty_id = session.get('faculty_id')  # This is faculty.id
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get user_id for this faculty (faculty_availability uses user_id)
        cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
        faculty_record = cursor.fetchone()
        if not faculty_record:
            flash("Faculty profile not found.", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('teacher.dashboard'))
        
        faculty_user_id = faculty_record['user_id']
        
        # Get faculty details
        cursor.execute("""
            SELECT f.name, f.email, d.name as department_name
            FROM faculty f
            LEFT JOIN departments d ON f.department_id = d.id
            WHERE f.id = %s
        """, (faculty_id,))
        faculty_info = cursor.fetchone()
        
        # Get faculty availability with shift patterns (faculty_availability.faculty_id stores user_id)
        cursor.execute("""
            SELECT fa.day_of_week, fa.is_available, fa.notes,
                   sp.shift_name, sp.shift_code, sp.start_time, sp.end_time
            FROM faculty_availability fa
            LEFT JOIN shift_patterns sp ON fa.shift_pattern_id = sp.id
            WHERE fa.faculty_id = %s
            ORDER BY fa.day_of_week
        """, (faculty_user_id,))
        availability_records = cursor.fetchall()
        
        # Build schedule by day
        day_names = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 
                    5: 'Friday', 6: 'Saturday', 7: 'Sunday'}
        
        schedule = {}
        for record in availability_records:
            day_num = record['day_of_week']
            day_name = day_names.get(day_num, f'Day {day_num}')
            schedule[day_name] = {
                'day_num': day_num,
                'is_available': bool(record['is_available']),
                'notes': record['notes'],
                'shift_name': record['shift_name'],
                'shift_code': record['shift_code'],
                'start_time': format_time(record['start_time']) if record['start_time'] else None,
                'end_time': format_time(record['end_time']) if record['end_time'] else None
            }
        
        # Get pending shift change requests (shift_change_requests.faculty_id stores faculty.user_id)
        cursor.execute("""
            SELECT id, day_of_week, current_shift_name, requested_shift_name, 
                   reason, status, created_at, admin_response
            FROM shift_change_requests
            WHERE faculty_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (faculty_user_id,))
        change_requests = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return render_template('teacher/my_shifts.html',
                             faculty_info=faculty_info,
                             schedule=schedule,
                             day_names=day_names,
                             change_requests=change_requests)
    
    except Exception as e:
        cursor.close()
        flash(f'Error loading shift information: {str(e)}', 'danger')
        return redirect(url_for('teacher.dashboard'))

@teacher_bp.route('/request-shift-change', methods=['POST'])
@teacher_required
def request_shift_change():
    """Submit a shift change request"""
    faculty_id = session.get('faculty_id')
    day_of_week = request.form.get('day_of_week')
    current_shift_name = request.form.get('current_shift_name', 'Not Assigned')
    requested_shift_name = request.form.get('requested_shift_name')
    reason = request.form.get('reason', '')
    
    if not day_of_week or not requested_shift_name:
        flash('Please provide all required information.', 'warning')
        return redirect(url_for('teacher.my_shifts'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # shift_change_requests.faculty_id references faculty.user_id
        cursor.execute("SELECT user_id FROM faculty WHERE id = %s", (faculty_id,))
        faculty_record = cursor.fetchone()
        if not faculty_record or not faculty_record.get('user_id'):
            flash('Faculty profile not found.', 'danger')
            return redirect(url_for('teacher.my_shifts'))

        faculty_user_id = faculty_record['user_id']

        cursor.execute("""
            INSERT INTO shift_change_requests 
            (faculty_id, day_of_week, current_shift_name, requested_shift_name, reason, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
        """, (faculty_user_id, day_of_week, current_shift_name, requested_shift_name, reason))
        
        connection.commit()
        flash('Shift change request submitted successfully! Admin will review it soon.', 'success')
    
    except Exception as e:
        connection.rollback()
        flash(f'Error submitting request: {str(e)}', 'danger')
    
    finally:

    
        cursor.close()

    
        connection.close()
    
    return redirect(url_for('teacher.my_shifts'))
