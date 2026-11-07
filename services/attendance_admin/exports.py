"""Admin attendance screens. exports."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response
from ui.pages import render_template
from extensions import get_db_connection
from datetime import datetime, timedelta
import csv
import io

def export_overview():
    """
    Export overview statistics to CSV.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get class-wise attendance for today
        cursor.execute("""
            SELECT 
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                COUNT(DISTINCT a.student_id) as total_students,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                ROUND(
                    (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(*)) * 100, 
                    2
                ) as percentage
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN courses c ON s.course_id = c.id
            JOIN classes cl ON s.class_id = cl.id
            JOIN divisions d ON s.division_id = d.id
            WHERE DATE(a.attendance_date) = CURDATE()
            GROUP BY c.name, cl.name, d.name
            ORDER BY c.name, cl.name, d.name
        """)
        data = cursor.fetchall()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(['Course', 'Class', 'Division', 'Total Students', 'Present', 'Absent', 'Late', 'Percentage'])
        
        # Write data
        for row in data:
            writer.writerow([
                row['course_name'],
                row['class_name'],
                row['division_name'],
                row['total_students'],
                row['present'],
                row['absent'],
                row['late'],
                f"{float(row['percentage'] or 0):.2f}%"
            ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=attendance_overview_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
    
    finally:
        cursor.close()
        connection.close()


def export_defaulters():
    """
    Export defaulters list to CSV.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        threshold = request.args.get('threshold', 75, type=float)
        
        cursor.execute("""
            SELECT 
                st.id as student_id,
                st.roll_number,
                st.full_name,
                st.email,
                st.phone,
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                soa.total_classes,
                soa.present_count,
                soa.absent_count,
                soa.late_count,
                ROUND(soa.attendance_percentage, 2) as attendance_percentage
            FROM student_overall_attendance soa
            JOIN students st ON soa.student_id = st.id
            JOIN courses c ON st.course_id = c.id
            JOIN classes cl ON st.class_id = cl.id
            JOIN divisions d ON st.division_id = d.id
            WHERE soa.attendance_percentage < %s
            ORDER BY soa.attendance_percentage ASC, st.roll_number
        """, [threshold])
        data = cursor.fetchall()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow(['Roll Number', 'Name', 'Course', 'Class', 'Division', 
                        'Total Classes', 'Present', 'Absent', 'Late', 'Percentage', 
                        'Email', 'Phone'])
        
        # Write data
        for row in data:
            writer.writerow([
                row['roll_number'],
                row['full_name'],
                row['course_name'],
                row['class_name'],
                row['division_name'],
                int(row['total_classes'] or 0),
                int(row['present_count'] or 0),
                int(row['absent_count'] or 0),
                int(row['late_count'] or 0),
                f"{float(row['attendance_percentage'] or 0):.2f}%",
                row['email'],
                row['phone']
            ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=attendance_defaulters_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
    
    finally:
        cursor.close()
        connection.close()


def charts_data():
    """
    Provide JSON data for chart visualizations.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        chart_type = request.args.get('type', 'trend')
        
        if chart_type == 'trend':
            # Last 30 days attendance trend
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(attendance_date, '%Y-%m-%d') as date,
                    SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as present,
                    SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) as absent,
                    SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) as late
                FROM attendance
                WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                GROUP BY DATE_FORMAT(attendance_date, '%Y-%m-%d')
                ORDER BY DATE_FORMAT(attendance_date, '%Y-%m-%d')
            """)
            data = cursor.fetchall()
            
            # Convert to chart format
            labels = [row['date'] for row in data]
            present = [int(row['present']) for row in data]
            absent = [int(row['absent']) for row in data]
            late = [int(row['late']) for row in data]
            
            return jsonify({
                'labels': labels,
                'datasets': [
                    {'label': 'Present', 'data': present, 'color': '#10b981'},
                    {'label': 'Absent', 'data': absent, 'color': '#ef4444'},
                    {'label': 'Late', 'data': late, 'color': '#f59e0b'}
                ]
            })
        
        elif chart_type == 'distribution':
            # Class-wise attendance distribution
            cursor.execute("""
                SELECT 
                    CONCAT(c.name, ' ', cl.name) as class_name,
                    ROUND(AVG(
                        CASE WHEN a.status IN ('Present', 'Late') THEN 100 ELSE 0 END
                    ), 2) as attendance_percentage
                FROM attendance a
                JOIN students s ON a.student_id = s.id
                JOIN courses c ON s.course_id = c.id
                JOIN classes cl ON s.class_id = cl.id
                WHERE a.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                GROUP BY c.id, cl.id, c.name, cl.name
                ORDER BY attendance_percentage DESC
                LIMIT 10
            """)
            data = cursor.fetchall()
            
            labels = [row['class_name'] for row in data]
            values = [float(row['attendance_percentage']) for row in data]
            
            return jsonify({
                'labels': labels,
                'data': values
            })
        
        return jsonify({'error': 'Invalid chart type'}), 400
    
    finally:
        cursor.close()
        connection.close()
