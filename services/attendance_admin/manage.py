"""Admin attendance screens. manage."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response
from ui.pages import render_template
from extensions import get_db_connection

def manage_attendance():
    """
    Attendance records - view, edit, bulk operations.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT id, name FROM courses ORDER BY name")
        courses = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM classes ORDER BY name")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM divisions ORDER BY name")
        divisions = cursor.fetchall()
        
        # Get attendance data if filters applied
        attendance_data = None
        filters = {}
        
        if request.args.get('fetch'):
            attendance_date = request.args.get('attendance_date')
            course_id = request.args.get('course_id')
            class_id = request.args.get('class_id')
            division_id = request.args.get('division_id')
            
            filters = {
                'attendance_date': attendance_date,
                'course_id': course_id,
                'class_id': class_id,
                'division_id': division_id
            }
            
            query = """
                SELECT 
                    a.id,
                    a.student_id,
                    s.roll_number as roll_number,
                    s.name as full_name,
                    c.name as course_name,
                    cl.name as class_name,
                    d.name as division_name,
                    DATE_FORMAT(a.attendance_date, '%Y-%m-%d') as attendance_date,
                    a.status,
                    a.remarks
                FROM attendance a
                JOIN students s ON a.student_id = s.id
                JOIN courses c ON s.course_id = c.id
                JOIN classes cl ON s.class_id = cl.id
                JOIN divisions d ON s.division_id = d.id
                WHERE 1=1
            """
            
            params = []
            
            if attendance_date:
                query += " AND a.attendance_date = %s"
                params.append(attendance_date)
            
            if course_id:
                query += " AND s.course_id = %s"
                params.append(course_id)
            
            if class_id:
                query += " AND s.class_id = %s"
                params.append(class_id)
            
            if division_id:
                query += " AND s.division_id = %s"
                params.append(division_id)
            
            query += " ORDER BY s.roll_number"
            
            cursor.execute(query, params)
            attendance_data = cursor.fetchall()
        
        import datetime
        today = datetime.date.today().strftime('%Y-%m-%d')
        
        return render_template('admin/attendance/manage.html',
                             courses=courses,
                             classes=classes,
                             divisions=divisions,
                             records=attendance_data or [],
                             today=today,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()


def update_attendance():
    """
    Update attendance record status.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        payload = request.get_json(silent=True) if request.is_json else {}

        attendance_id = (
            request.form.get('attendance_id')
            or request.form.get('record_id')
            or (payload or {}).get('attendance_id')
            or (payload or {}).get('record_id')
        )
        status = request.form.get('status') or (payload or {}).get('status')
        remarks = request.form.get('remarks')
        if remarks is None:
            remarks = (payload or {}).get('remarks', '')

        if not attendance_id:
            return jsonify({'success': False, 'message': 'attendance_id is required'}), 400

        try:
            attendance_id = int(attendance_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'attendance_id must be a valid integer'}), 400

        allowed_statuses = {'Present', 'Absent', 'Late'}
        normalized_status = str(status or '').strip().title()
        if normalized_status not in allowed_statuses:
            return jsonify({'success': False, 'message': 'status must be Present, Absent, or Late'}), 400

        cursor.execute("SELECT id FROM attendance WHERE id = %s", [attendance_id])
        existing_record = cursor.fetchone()
        if not existing_record:
            return jsonify({'success': False, 'message': 'Attendance record not found'}), 404

        cursor.execute(
            """
            UPDATE attendance
            SET status = %s, remarks = %s
            WHERE id = %s
            """,
            [normalized_status, str(remarks or '').strip(), attendance_id],
        )

        connection.commit()

        return jsonify({'success': True, 'message': 'Attendance updated successfully'})
    
    except Exception as e:
        connection.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    
    finally:
        cursor.close()
        connection.close()
