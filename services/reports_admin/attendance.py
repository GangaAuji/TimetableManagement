"""Admin report screens. attendance."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
from extensions import get_db_connection

def attendance_report():
    """
    Generate attendance reports with various filters.
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
        
        # Get report data if filters are applied
        report_data = None
        filters = {}
        
        if request.args.get('generate'):
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            course_id = request.args.get('course_id')
            class_id = request.args.get('class_id')
            division_id = request.args.get('division_id')
            
            filters = {
                'start_date': start_date,
                'end_date': end_date,
                'course_id': course_id,
                'class_id': class_id,
                'division_id': division_id
            }
            
            # Build query based on filters
            query = """
                SELECT 
                    s.id,
                    s.id as roll_number,
                    s.name as full_name,
                    c.name as course_name,
                    cl.name as class_name,
                    d.name as division_name,
                    COUNT(a.id) as total_classes,
                    SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                    SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                    SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                    ROUND(
                        (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(a.id)) * 100, 
                        2
                    ) as attendance_percentage
                FROM students s
                JOIN courses c ON s.course_id = c.id
                JOIN classes cl ON s.class_id = cl.id
                JOIN divisions d ON s.division_id = d.id
                LEFT JOIN attendance a ON s.id = a.student_id
            """
            
            conditions = []
            params = []
            
            if start_date:
                conditions.append("a.attendance_date >= %s")
                params.append(start_date)
            
            if end_date:
                conditions.append("a.attendance_date <= %s")
                params.append(end_date)
            
            if course_id:
                conditions.append("s.course_id = %s")
                params.append(course_id)
            
            if class_id:
                conditions.append("s.class_id = %s")
                params.append(class_id)
            
            if division_id:
                conditions.append("s.division_id = %s")
                params.append(division_id)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " GROUP BY s.id, s.name, c.name, cl.name, d.name ORDER BY s.id"
            
            cursor.execute(query, params)
            report_data = cursor.fetchall()
            
            # Convert Decimal to float
            if report_data:
                for row in report_data:
                    row['attendance_percentage'] = float(row['attendance_percentage'] or 0)
        
        return render_template('admin/reports/attendance.html',
                             courses=courses,
                             classes=classes,
                             divisions=divisions,
                             report_data=report_data,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()
