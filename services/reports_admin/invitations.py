"""Admin report screens. invitations."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
from extensions import get_db_connection

def invitations_report():
    """
    Generate invitations report.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        role = request.args.get('role')
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        course_id = request.args.get('course_id')
        class_id = request.args.get('class_id')
        division_id = request.args.get('division_id')

        filters = {
            'role': role,
            'status': status,
            'start_date': start_date,
            'end_date': end_date,
            'course_id': course_id,
            'class_id': class_id,
            'division_id': division_id
        }

        cursor.execute("SELECT DISTINCT role FROM registration_invitations ORDER BY role")
        roles = cursor.fetchall()

        cursor.execute("SELECT DISTINCT status FROM registration_invitations ORDER BY status")
        statuses = cursor.fetchall()

        cursor.execute("SELECT id, name FROM courses ORDER BY name")
        courses = cursor.fetchall()

        cursor.execute("SELECT id, name FROM classes ORDER BY name")
        classes = cursor.fetchall()

        cursor.execute("SELECT id, name FROM divisions ORDER BY name")
        divisions = cursor.fetchall()

        # Get invitation statistics (based on current filters)
        stats_query = """
            SELECT 
                status,
                role,
                COUNT(*) as count
            FROM registration_invitations
        """

        stats_conditions = []
        stats_params = []
        if role:
            stats_conditions.append("role = %s")
            stats_params.append(role)
        if status:
            stats_conditions.append("status = %s")
            stats_params.append(status)
        if start_date:
            stats_conditions.append("DATE(created_at) >= %s")
            stats_params.append(start_date)
        if end_date:
            stats_conditions.append("DATE(created_at) <= %s")
            stats_params.append(end_date)
        if course_id:
            stats_conditions.append("course_id = %s")
            stats_params.append(course_id)
        if class_id:
            stats_conditions.append("class_id = %s")
            stats_params.append(class_id)
        if division_id:
            stats_conditions.append("division_id = %s")
            stats_params.append(division_id)

        if stats_conditions:
            stats_query += " WHERE " + " AND ".join(stats_conditions)

        stats_query += " GROUP BY status, role"
        cursor.execute(stats_query, stats_params)
        stats = cursor.fetchall()
        
        # Get recent invitations
        invitations_query = """
            SELECT 
                ri.id,
                ri.email,
                ri.role,
                ri.status,
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                DATE_FORMAT(ri.created_at, '%Y-%m-%d %H:%i') as created_at,
                DATE_FORMAT(ri.expires_at, '%Y-%m-%d') as expires_at,
                CASE 
                    WHEN ri.status = 'used' THEN 'Registered'
                    WHEN ri.expires_at < NOW() THEN 'Expired'
                    ELSE 'Active'
                END as display_status
            FROM registration_invitations ri
            LEFT JOIN courses c ON ri.course_id = c.id
            LEFT JOIN classes cl ON ri.class_id = cl.id
            LEFT JOIN divisions d ON ri.division_id = d.id
        """

        conditions = []
        params = []
        if role:
            conditions.append("ri.role = %s")
            params.append(role)
        if status:
            conditions.append("ri.status = %s")
            params.append(status)
        if start_date:
            conditions.append("DATE(ri.created_at) >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(ri.created_at) <= %s")
            params.append(end_date)
        if course_id:
            conditions.append("ri.course_id = %s")
            params.append(course_id)
        if class_id:
            conditions.append("ri.class_id = %s")
            params.append(class_id)
        if division_id:
            conditions.append("ri.division_id = %s")
            params.append(division_id)

        if conditions:
            invitations_query += " WHERE " + " AND ".join(conditions)

        invitations_query += " ORDER BY ri.created_at DESC LIMIT 500"
        cursor.execute(invitations_query, params)
        invitations = cursor.fetchall()
        
        return render_template('admin/reports/invitations.html',
                             stats=stats,
                             invitations=invitations,
                             filters=filters,
                             roles=roles,
                             statuses=statuses,
                             courses=courses,
                             classes=classes,
                             divisions=divisions)
    
    finally:
        cursor.close()
        connection.close()
