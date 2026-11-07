"""Admin report screens. shifts."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
from extensions import get_db_connection

def shifts_report():
    """
    Generate shift management reports.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT DISTINCT status FROM shift_change_requests ORDER BY status")
        statuses = cursor.fetchall()

        cursor.execute("""
            SELECT DISTINCT f.user_id, f.name
            FROM shift_change_requests scr
            JOIN faculty f ON scr.faculty_id = f.id OR scr.faculty_id = f.user_id
            ORDER BY f.name
        """)
        faculty_options = cursor.fetchall()

        status = request.args.get('status')
        faculty_id = request.args.get('faculty_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        filters = {
            'status': status,
            'faculty_id': faculty_id,
            'start_date': start_date,
            'end_date': end_date
        }

        # Get shift change requests with details
        query = """
            SELECT 
                scr.id,
                u.username,
                f.name as full_name,
                scr.current_shift_name as current_shift,
                scr.requested_shift_name as requested_shift,
                scr.reason,
                scr.status,
                DATE_FORMAT(scr.created_at, '%Y-%m-%d') as effective_date,
                DATE_FORMAT(scr.created_at, '%Y-%m-%d %H:%i') as created_at,
                scr.admin_response as admin_remarks
            FROM shift_change_requests scr
            LEFT JOIN faculty f ON scr.faculty_id = f.id OR scr.faculty_id = f.user_id
            LEFT JOIN users u ON f.user_id = u.id
        """

        conditions = []
        params = []
        if status:
            conditions.append("scr.status = %s")
            params.append(status)
        if faculty_id:
            conditions.append("(scr.faculty_id = %s OR f.id = %s OR f.user_id = %s)")
            params.extend([faculty_id, faculty_id, faculty_id])
        if start_date:
            conditions.append("DATE(scr.created_at) >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(scr.created_at) <= %s")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY scr.created_at DESC"
        cursor.execute(query, params)
        shift_requests = cursor.fetchall()
        
        # Get shift patterns summary
        cursor.execute("""
            SELECT 
                sp.shift_name as name,
                DATE_FORMAT(sp.start_time, '%H:%i') as start_time,
                DATE_FORMAT(sp.end_time, '%H:%i') as end_time,
                COUNT(DISTINCT fa.faculty_id) as faculty_count
            FROM shift_patterns sp
            LEFT JOIN faculty_availability fa ON sp.id = fa.shift_pattern_id
            GROUP BY sp.id, sp.shift_name, sp.start_time, sp.end_time
            ORDER BY sp.start_time
        """)
        shift_summary = cursor.fetchall()
        
        return render_template('admin/reports/shifts.html',
                             shift_requests=shift_requests,
                             shift_summary=shift_summary,
                             statuses=statuses,
                             faculty_options=faculty_options,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()
