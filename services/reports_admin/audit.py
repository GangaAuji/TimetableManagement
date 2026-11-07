"""Admin report screens. audit."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
from extensions import get_db_connection

def audit_logs_report():
    """
    Generate audit logs reports with filters.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT DISTINCT activity_type as action FROM user_activity_log ORDER BY activity_type")
        actions = cursor.fetchall()
        
        cursor.execute("SELECT id, username FROM users ORDER BY username")
        users = cursor.fetchall()
        
        # Get report data
        filters = {}
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        user_id = request.args.get('user_id')
        action = request.args.get('action')
        
        filters = {
            'start_date': start_date,
            'end_date': end_date,
            'user_id': user_id,
            'action': action
        }
        
        query = """
            SELECT 
                al.id,
                u.username,
                al.activity_type as action,
                al.description,
                al.ip_address,
                al.user_agent,
                DATE_FORMAT(al.created_at, '%Y-%m-%d %H:%i:%s') as timestamp
            FROM user_activity_log al
            JOIN users u ON al.user_id = u.id
        """
        
        conditions = []
        params = []
        
        if start_date:
            conditions.append("DATE(al.created_at) >= %s")
            params.append(start_date)
        
        if end_date:
            conditions.append("DATE(al.created_at) <= %s")
            params.append(end_date)
        
        if user_id:
            conditions.append("al.user_id = %s")
            params.append(user_id)
        
        if action:
            conditions.append("al.activity_type = %s")
            params.append(action)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY al.created_at DESC LIMIT 500"
        
        cursor.execute(query, params)
        report_data = cursor.fetchall()
        
        return render_template('admin/reports/audit_logs.html',
                             actions=actions,
                             users=users,
                             report_data=report_data,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()
