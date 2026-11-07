"""Admin report screens. proxy."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
from extensions import get_db_connection

def proxy_log_report():
    """
    Generate proxy assignment reports.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get proxy log entries
        filters = {}
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        filters = {
            'start_date': start_date,
            'end_date': end_date
        }
        
        query = """
            SELECT 
                pl.id,
                f1.name as original_faculty,
                f2.name as proxy_faculty,
                sub.name as subject_name,
                course.name as course_name,
                c.name as class_name,
                d.name as division_name,
                DATE_FORMAT(pl.absence_date, '%Y-%m-%d') as proxy_date,
                DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                COALESCE(pl.approval_notes, '') as reason,
                DATE_FORMAT(COALESCE(pl.approval_date, pl.absence_date), '%Y-%m-%d %H:%i') as created_at
            FROM proxy_log pl
            JOIN faculty f1 ON pl.original_faculty_id = f1.user_id
            JOIN faculty f2 ON pl.proxy_faculty_id = f2.user_id
            JOIN timetable t ON pl.timetable_id = t.id
            JOIN subjects sub ON t.subject_id = sub.id
            JOIN courses course ON t.course_id = course.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
        """
        
        conditions = []
        params = []
        
        if start_date:
            conditions.append("pl.absence_date >= %s")
            params.append(start_date)
        
        if end_date:
            conditions.append("pl.absence_date <= %s")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY pl.absence_date DESC, t.start_time DESC LIMIT 500"
        
        cursor.execute(query, params)
        proxy_logs = cursor.fetchall()
        
        return render_template('admin/reports/proxy_log.html',
                             proxy_logs=proxy_logs,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()
