"""Admin report screens. timetable."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
from extensions import get_db_connection

def timetable_report():
    """
    Generate timetable reports for various entities.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT id, name FROM courses ORDER BY name")
        courses = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM classes ORDER BY name")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT user_id, name as full_name FROM faculty ORDER BY name")
        faculty = cursor.fetchall()
        
        cursor.execute("SELECT id, room_number, room_type as room_name FROM rooms ORDER BY room_number")
        rooms = cursor.fetchall()
        
        # Get report data if filters are applied
        report_data = None
        filters = {}
        
        if request.args.get('generate'):
            report_type = request.args.get('report_type', 'class')
            entity_id = request.args.get('entity_id')
            
            filters = {
                'report_type': report_type,
                'entity_id': entity_id
            }
            
            if report_type == 'class' and entity_id:
                query = """
                    SELECT 
                        t.day_of_week,
                        DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                        DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                        sub.name as subject_name,
                        sub.course_code as subject_code,
                        f.name as faculty_name,
                        r.room_number,
                        r.room_type as room_name,
                        d.name as division_name
                    FROM timetable t
                    JOIN subjects sub ON t.subject_id = sub.id
                    JOIN faculty f ON t.faculty_id = f.user_id
                    JOIN rooms r ON t.room_id = r.id
                    JOIN divisions d ON t.division_id = d.id
                    WHERE t.class_id = %s AND t.is_active = 1
                    ORDER BY 
                        FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'),
                        t.start_time
                """
                cursor.execute(query, [entity_id])
                report_data = cursor.fetchall()
            
            elif report_type == 'faculty' and entity_id:
                query = """
                    SELECT 
                        t.day_of_week,
                        DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                        DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                        sub.name as subject_name,
                        sub.course_code as subject_code,
                        c.name as course_name,
                        cl.name as class_name,
                        d.name as division_name,
                        r.room_number,
                        r.room_type as room_name
                    FROM timetable t
                    JOIN subjects sub ON t.subject_id = sub.id
                    JOIN courses c ON t.course_id = c.id
                    JOIN classes cl ON t.class_id = cl.id
                    JOIN divisions d ON t.division_id = d.id
                    JOIN rooms r ON t.room_id = r.id
                    WHERE t.faculty_id = %s AND t.is_active = 1
                    ORDER BY 
                        FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'),
                        t.start_time
                """
                cursor.execute(query, [entity_id])
                report_data = cursor.fetchall()
            
            elif report_type == 'room' and entity_id:
                query = """
                    SELECT 
                        t.day_of_week,
                        DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                        DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                        sub.name as subject_name,
                        f.name as faculty_name,
                        c.name as course_name,
                        cl.name as class_name,
                        d.name as division_name
                    FROM timetable t
                    JOIN subjects sub ON t.subject_id = sub.id
                    JOIN faculty f ON t.faculty_id = f.user_id
                    JOIN courses c ON t.course_id = c.id
                    JOIN classes cl ON t.class_id = cl.id
                    JOIN divisions d ON t.division_id = d.id
                    WHERE t.room_id = %s AND t.is_active = 1
                    ORDER BY 
                        FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'),
                        t.start_time
                """
                cursor.execute(query, [entity_id])
                report_data = cursor.fetchall()
        
        return render_template('admin/reports/timetable.html',
                             courses=courses,
                             classes=classes,
                             faculty=faculty,
                             rooms=rooms,
                             report_data=report_data,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()
