
import math
from flask import Blueprint, make_response, render_template, redirect, url_for, request, flash, current_app, jsonify
from database import get_db_connection
from security import has_permission


proxy_bp = Blueprint('proxy', __name__, url_prefix='/admin/proxy')


@proxy_bp.route('/')
@has_permission('faculty_view_proxy')
def proxy_log():
    """Display comprehensive proxy log with faculty absence and proxy assignment details"""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    # Get filter parameters
    status_filter = request.args.get('status', '', type=str)
    approval_filter = request.args.get('approval_status', '', type=str)
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)
    
    # Build the main query
    query = """
        SELECT 
            pl.id,
            pl.absence_date,
            pl.status,
            pl.approval_status,
            pl.approval_date,
            pl.approval_notes,
            
            -- Original faculty details
            orig_f.name AS original_faculty_name,
            orig_f.employee_id AS original_employee_id,
            
            -- Proxy faculty details (nullable)
            proxy_f.name AS proxy_faculty_name,
            proxy_f.employee_id AS proxy_employee_id,
            
            -- Timetable and subject details
            t.day_of_week,
            t.start_time,
            t.end_time,
            s.name AS subject_name,
            
            -- Class and division details
            c.name AS class_name,
            d.name AS division_name,
            
            -- Department details
            dept.name AS department_name,
            
            -- Approved by details
            approver.username AS approved_by_username
            
        FROM proxy_log pl
        JOIN timetable t ON pl.timetable_id = t.id
        JOIN faculty orig_f ON pl.original_faculty_id = orig_f.user_id
        LEFT JOIN faculty proxy_f ON pl.proxy_faculty_id = proxy_f.user_id
        JOIN subjects s ON t.subject_id = s.id
        JOIN classes c ON t.class_id = c.id
        JOIN divisions d ON t.division_id = d.id
        LEFT JOIN departments dept ON orig_f.department_id = dept.id
        LEFT JOIN users approver ON pl.approved_by = approver.id
        WHERE 1=1
    """
    
    params = []
    
    # Apply filters
    if status_filter:
        query += " AND pl.status = %s"
        params.append(status_filter)
    
    if approval_filter:
        query += " AND pl.approval_status = %s"
        params.append(approval_filter)
    
    if date_from:
        query += " AND pl.absence_date >= %s"
        params.append(date_from)
    
    if date_to:
        query += " AND pl.absence_date <= %s"
        params.append(date_to)
    
    # Get total count for pagination
    count_query = f"SELECT COUNT(*) AS total {query[query.find('FROM'):query.rfind('ORDER BY') if 'ORDER BY' in query else len(query)]}"
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()['total']
    
    # Add ordering and pagination
    query += " ORDER BY pl.absence_date DESC, t.start_time ASC"
    query += " LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    # Execute main query
    cursor.execute(query, params)
    proxy_logs = []
    
    for row in cursor.fetchall():
        log_entry = {
            'id': row['id'],
            'absence_date': row['absence_date'],
            'status': row['status'],
            'approval_status': row['approval_status'],
            'approval_date': row['approval_date'],
            'approval_notes': row['approval_notes'],
            'original_faculty_name': row['original_faculty_name'],
            'original_employee_id': row['original_employee_id'],
            'proxy_faculty_name': row['proxy_faculty_name'],
            'proxy_employee_id': row['proxy_employee_id'],
            'day_of_week': row['day_of_week'],
            'start_time': row['start_time'],
            'end_time': row['end_time'],
            'subject_name': row['subject_name'],
            'class_name': row['class_name'],
            'division_name': row['division_name'],
            'department_name': row['department_name'],
            'approved_by_username': row['approved_by_username']
        }
        proxy_logs.append(log_entry)
    
    # Get summary statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total_records,
            SUM(CASE WHEN pl.status = 'ASSIGNED' THEN 1 ELSE 0 END) as assigned_count,
            SUM(CASE WHEN pl.status = 'UNASSIGNED' THEN 1 ELSE 0 END) as unassigned_count,
            SUM(CASE WHEN pl.approval_status = 'PENDING' THEN 1 ELSE 0 END) as pending_approval,
            SUM(CASE WHEN pl.approval_status = 'APPROVED' THEN 1 ELSE 0 END) as approved_count,
            SUM(CASE WHEN pl.approval_status = 'REJECTED' THEN 1 ELSE 0 END) as rejected_count
        FROM proxy_log pl
    """)
    stats = cursor.fetchone()
    summary_stats = {
        'total_records': stats['total_records'],
        'assigned_count': stats['assigned_count'],
        'unassigned_count': stats['unassigned_count'],
        'pending_approval': stats['pending_approval'],
        'approved_count': stats['approved_count'],
        'rejected_count': stats['rejected_count']
    }
    
    cursor.close()
    
    # Pagination info
    total_pages = math.ceil(total_count / per_page)
    has_prev = page > 1
    has_next = page < total_pages
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None
    
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_num': prev_num,
        'next_num': next_num
    }
    
    return render_template('admin/proxy_log.html', 
                         proxy_logs=proxy_logs,
                         summary_stats=summary_stats,
                         pagination=pagination,
                         status_filter=status_filter,
                         approval_filter=approval_filter,
                         date_from=date_from,
                         date_to=date_to)
