"""
Admin routes for viewing audit logs and monitoring system activity
"""

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from routes.admin_utils import admin_required
from database import get_db_connection
from datetime import datetime, timedelta
import json

audit_logs_bp = Blueprint('audit_logs', __name__, url_prefix='/admin/audit-logs')


@audit_logs_bp.route('/')
@admin_required
def audit_logs_view():
    """View audit logs with filters - uses user_activity_log table"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get filter parameters
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Build query from audit_logs table (enhanced security table)
    query = """
        SELECT 
            al.id, al.user_id, al.username,
            al.action,
            al.entity_type,
            al.entity_id,
            al.ip_address,
            al.user_agent,
            al.created_at,
            al.old_values,
            al.new_values,
            al.request_url,
            al.status
        FROM audit_logs al
        WHERE 1=1
    """
    params = []
    
    if user_id:
        query += " AND al.user_id = %s"
        params.append(user_id)
    
    if action:
        query += " AND al.action LIKE %s"
        params.append(f'%{action}%')
    
    if date_from:
        query += " AND al.created_at >= %s"
        params.append(date_from)
    
    if date_to:
        query += " AND al.created_at <= %s"
        params.append(date_to + ' 23:59:59')
    
    # Count total records
    count_query = f"SELECT COUNT(*) as total FROM ({query}) as filtered"
    cursor.execute(count_query, params)
    total_records = cursor.fetchone()['total']
    
    # Add pagination
    query += " ORDER BY al.created_at DESC LIMIT %s OFFSET %s"
    params.extend([per_page, (page - 1) * per_page])
    
    cursor.execute(query, params)
    logs = cursor.fetchall()
    
    # Get unique actions for filters
    cursor.execute("SELECT DISTINCT action FROM audit_logs WHERE action IS NOT NULL ORDER BY action")
    actions = [row['action'] for row in cursor.fetchall()]
    
    # Get unique entity types for filters
    cursor.execute("SELECT DISTINCT entity_type FROM audit_logs WHERE entity_type IS NOT NULL ORDER BY entity_type")
    entity_types = [row['entity_type'] for row in cursor.fetchall()]
    
    # Get all users for filter
    cursor.execute("SELECT id, username FROM users ORDER BY username")
    users = cursor.fetchall()
    
    # Calculate pagination
    total_pages = (total_records + per_page - 1) // per_page
    
    # Get dashboard data for combined view
    # Activity statistics (last 24 hours)
    cursor.execute(
        """
        SELECT 
            COUNT(*) as total_activities,
            COUNT(DISTINCT user_id) as active_users,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_activities
        FROM audit_logs
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """
    )
    stats_24h = cursor.fetchone()
    
    # Active sessions count
    cursor.execute(
        "SELECT COUNT(*) as count FROM user_sessions WHERE is_active = 1 AND (expires_at IS NULL OR expires_at > NOW())"
    )
    active_sessions_count = cursor.fetchone()['count']
    
    # Get recent active sessions
    cursor.execute(
        """
        SELECT s.session_id, s.user_id, u.username, s.ip_address, 
               s.last_activity, s.created_at
        FROM user_sessions s
        LEFT JOIN users u ON s.user_id = u.id
        WHERE s.is_active = 1 AND (s.expires_at IS NULL OR s.expires_at > NOW())
        ORDER BY s.last_activity DESC
        LIMIT 10
        """
    )
    recent_sessions = cursor.fetchall()
    
    # Most active users (last 7 days)
    cursor.execute(
        """
        SELECT user_id, username, COUNT(*) as activity_count
        FROM audit_logs
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY user_id, username
        ORDER BY activity_count DESC
        LIMIT 10
        """
    )
    most_active_users = cursor.fetchall()
    
    # Recent failed logins
    cursor.execute(
        """
        SELECT username, ip_address, failure_reason, attempted_at
        FROM login_attempts
        WHERE status = 'failed'
        ORDER BY attempted_at DESC
        LIMIT 20
        """
    )
    failed_logins = cursor.fetchall()
    
    # Recent critical actions
    cursor.execute(
        """
        SELECT id, user_id, username, action, entity_type, entity_id, created_at
        FROM audit_logs
        WHERE action IN ('delete_user', 'bulk_delete_users', 'delete_role', 
                         'revoke_permission', 'reset_password', 'bulk_reset_password',
                         'toggle_status', 'account_locked', 'edit_role', 'grant_permission')
           OR action LIKE '%delete%'
           OR action LIKE '%remove%'
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    critical_actions = cursor.fetchall()
    
    cursor.close()
    
    return render_template(
        'admin/audit_system.html',
        logs=logs,
        actions=actions,
        entity_types=entity_types,
        users=users,
        filters={
            'user_id': user_id,
            'action': action,
            'entity_type': '',
            'date_from': date_from,
            'date_to': date_to,
            'status': ''
        },
        page=page,
        total_pages=total_pages,
        total_records=total_records,
        stats_24h=stats_24h,
        active_sessions_count=active_sessions_count,
        recent_sessions=recent_sessions,
        most_active_users=most_active_users,
        failed_logins=failed_logins,
        critical_actions=critical_actions
    )


@audit_logs_bp.route('/details/<int:log_id>')
@admin_required
def log_details(log_id):
    """View detailed information about a specific audit log entry"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    cursor.execute(
        """
        SELECT * FROM audit_logs WHERE id = %s
        """,
        (log_id,)
    )
    
    log = cursor.fetchone()
    cursor.close()
    connection.close()
    
    if not log:
        flash('Audit log not found.', 'danger')
        return redirect(url_for('audit_logs.audit_logs_view'))
    
    # Parse JSON fields
    if log['old_values']:
        log['old_values'] = json.loads(log['old_values'])
    if log['new_values']:
        log['new_values'] = json.loads(log['new_values'])
    
    return render_template('admin/audit_log_details.html', log=log)


@audit_logs_bp.route('/user-activity/<int:user_id>')
@admin_required
def user_activity(user_id):
    """View activity summary for a specific user"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get user info
    cursor.execute("SELECT id, username, email, role FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('audit_logs.audit_logs_view'))
    
    # Get activity summary (last 30 days)
    cursor.execute(
        """
        SELECT 
            action,
            COUNT(*) as count,
            MAX(created_at) as last_activity
        FROM audit_logs
        WHERE user_id = %s 
          AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        GROUP BY action
        ORDER BY count DESC
        """,
        (user_id,)
    )
    activity_summary = cursor.fetchall()
    
    # Get recent activities
    cursor.execute(
        """
        SELECT id, action, entity_type, entity_id, status, created_at
        FROM audit_logs
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 50
        """,
        (user_id,)
    )
    recent_activities = cursor.fetchall()
    
    # Get active sessions
    cursor.execute(
        """
        SELECT session_id, ip_address, user_agent, last_activity, created_at, expires_at
        FROM user_sessions
        WHERE user_id = %s AND is_active = 1
        ORDER BY last_activity DESC
        """,
        (user_id,)
    )
    active_sessions = cursor.fetchall()
    
    cursor.close()
    
    return render_template(
        'admin/user_activity.html',
        user=user,
        activity_summary=activity_summary,
        recent_activities=recent_activities,
        active_sessions=active_sessions
    )


@audit_logs_bp.route('/dashboard')
@admin_required
def security_dashboard():
    """Redirect to main audit page (now shows dashboard by default)"""
    return redirect(url_for('audit_logs.audit_logs_view'))


@audit_logs_bp.route('/export')
@admin_required
def export_logs():
    """Export audit logs to CSV"""
    import csv
    import io
    from flask import make_response
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get filter parameters (same as view)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')
    entity_type = request.args.get('entity_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query (same as view but without pagination)
    query = """
        SELECT 
            id, user_id, username, action, entity_type, entity_id,
            ip_address, request_method, status, created_at
        FROM audit_logs
        WHERE 1=1
    """
    params = []
    
    if user_id:
        query += " AND user_id = %s"
        params.append(user_id)
    if action:
        query += " AND action LIKE %s"
        params.append(f'%{action}%')
    if entity_type:
        query += " AND entity_type = %s"
        params.append(entity_type)
    if date_from:
        query += " AND created_at >= %s"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= %s"
        params.append(date_to + ' 23:59:59')
    
    query += " ORDER BY created_at DESC LIMIT 10000"  # Limit for safety
    
    cursor.execute(query, params)
    logs = cursor.fetchall()
    cursor.close()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['ID', 'User ID', 'Username', 'Action', 'Entity Type', 
                     'Entity ID', 'IP Address', 'Method', 'Status', 'Timestamp'])
    
    # Data
    for log in logs:
        writer.writerow([
            log['id'], log['user_id'], log['username'], log['action'],
            log['entity_type'], log['entity_id'], log['ip_address'],
            log['request_method'], log['status'], log['created_at']
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=audit_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response


@audit_logs_bp.route('/session/revoke/<session_id>', methods=['POST'])
@admin_required
def revoke_session(session_id):
    """Revoke a user session"""
    # CSRF is handled by WTForms protection - form must include csrf_token field
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    cursor.execute(
        "UPDATE user_sessions SET is_active = 0 WHERE session_id = %s",
        (session_id,)
    )
    
    connection.commit()
    cursor.close()
    
    flash('Session revoked successfully.', 'success')
    return redirect(request.referrer or url_for('audit_logs.security_dashboard'))
