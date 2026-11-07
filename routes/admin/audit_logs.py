"""
Admin routes for viewing audit logs and monitoring system activity
"""

from flask import Blueprint, request, redirect, url_for, jsonify, flash, make_response
from ui.pages import render_template
from routes.admin_utils import admin_required
from datetime import datetime
import csv
import io
import json

from services.audit_logs import (
    export_audit_rows,
    load_audit_page,
    load_log_detail,
    load_user_activity,
    revoke_audit_session,
)

audit_logs_bp = Blueprint('audit_logs', __name__, url_prefix='/admin/audit-logs')


@audit_logs_bp.route('/')
@admin_required
def audit_logs_view():
    """View audit logs with filters - uses user_activity_log table"""
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    page_data = load_audit_page(user_id, action, date_from, date_to, page, per_page)
    return render_template(
        'admin/audit_system.html',
        logs=page_data['logs'],
        actions=page_data['actions'],
        entity_types=page_data['entity_types'],
        users=page_data['users'],
        filters={
            'user_id': user_id,
            'action': action,
            'entity_type': '',
            'date_from': date_from,
            'date_to': date_to,
            'status': ''
        },
        page=page,
        total_pages=page_data['total_pages'],
        total_records=page_data['total_records'],
        stats_24h=page_data['stats_24h'],
        active_sessions_count=page_data['active_sessions_count'],
        recent_sessions=page_data['recent_sessions'],
        most_active_users=page_data['most_active_users'],
        failed_logins=page_data['failed_logins'],
        critical_actions=page_data['critical_actions']
    )


@audit_logs_bp.route('/details/<int:log_id>')
@admin_required
def log_details(log_id):
    """View detailed information about a specific audit log entry"""
    log = load_log_detail(log_id)
    if not log:
        flash('Audit log not found.', 'danger')
        return redirect(url_for('audit_logs.audit_logs_view'))
    if log['old_values']:
        log['old_values'] = json.loads(log['old_values'])
    if log['new_values']:
        log['new_values'] = json.loads(log['new_values'])
    return render_template('admin/audit_log_details.html', log=log)


@audit_logs_bp.route('/user-activity/<int:user_id>')
@admin_required
def user_activity(user_id):
    """View activity summary for a specific user"""
    page_data = load_user_activity(user_id)
    if page_data == 'missing':
        flash('User not found.', 'danger')
        return redirect(url_for('audit_logs.audit_logs_view'))
    return render_template(
        'admin/user_activity.html',
        user=page_data['user'],
        activity_summary=page_data['activity_summary'],
        recent_activities=page_data['recent_activities'],
        active_sessions=page_data['active_sessions']
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
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')
    entity_type = request.args.get('entity_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    logs = export_audit_rows(user_id, action, entity_type, date_from, date_to)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'User ID', 'Username', 'Action', 'Entity Type',
                     'Entity ID', 'IP Address', 'Method', 'Status', 'Timestamp'])
    for log in logs:
        writer.writerow([
            log['id'], log['user_id'], log['username'], log['action'],
            log['entity_type'], log['entity_id'], log['ip_address'],
            log['request_method'], log['status'], log['created_at']
        ])
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=audit_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


@audit_logs_bp.route('/session/revoke/<session_id>', methods=['POST'])
@admin_required
def revoke_session(session_id):
    """Revoke a user session"""
    # CSRF is handled by WTForms protection - form must include csrf_token field
    revoke_audit_session(session_id)
    flash('Session revoked successfully.', 'success')
    return redirect(request.referrer or url_for('audit_logs.security_dashboard'))
