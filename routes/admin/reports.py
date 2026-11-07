"""
Admin Reports Module
Centralized reporting system for administrators with various report types.
"""

from flask import Blueprint
from security import has_permission
from services.reports_admin import (
    preview_report as run_preview_report,
    reports_index as run_reports_index,
    reports_processor as run_reports_processor,
    attendance_report as run_attendance_report,
    timetable_report as run_timetable_report,
    audit_logs_report as run_audit_logs_report,
    shifts_report as run_shifts_report,
    proxy_log_report as run_proxy_log_report,
    invitations_report as run_invitations_report,
    export_report as run_export_report,
    process_report as run_process_report,
    download_processed_report as run_download_processed_report,
    delete_processed_report as run_delete_processed_report,
    restore_processed_report as run_restore_processed_report,
)


reports_bp = Blueprint('admin_reports', __name__, url_prefix='/admin/reports')

@reports_bp.route('/preview/<report_type>', methods=['POST'])
@has_permission('reports_export')
def preview_report(report_type):
    return run_preview_report(report_type)

@reports_bp.route('/')
@has_permission('reports_view')
def reports_index():
    return run_reports_index()

@reports_bp.route('/processor')
@has_permission('reports_export')
def reports_processor():
    return run_reports_processor()

@reports_bp.route('/attendance')
@has_permission('reports_view_attendance')
def attendance_report():
    return run_attendance_report()

@reports_bp.route('/timetable')
@has_permission('reports_view_timetable')
def timetable_report():
    return run_timetable_report()

@reports_bp.route('/audit-logs')
@has_permission('reports_view_audit')
def audit_logs_report():
    return run_audit_logs_report()

@reports_bp.route('/shifts')
@has_permission('reports_view_shifts')
def shifts_report():
    return run_shifts_report()

@reports_bp.route('/proxy-log')
@has_permission('reports_view_proxy')
def proxy_log_report():
    return run_proxy_log_report()

@reports_bp.route('/invitations')
@has_permission('reports_view_invitations')
def invitations_report():
    return run_invitations_report()

@reports_bp.route('/export/<report_type>', methods=['POST'])
@has_permission('reports_export')
def export_report(report_type):
    return run_export_report(report_type)

@reports_bp.route('/process/<report_type>', methods=['POST'])
@has_permission('reports_export')
def process_report(report_type):
    return run_process_report(report_type)

@reports_bp.route('/download/<int:processed_report_id>')
@has_permission('reports_export')
def download_processed_report(processed_report_id):
    return run_download_processed_report(processed_report_id)

@reports_bp.route('/delete/<int:processed_report_id>', methods=['POST'])
@has_permission('reports_export')
def delete_processed_report(processed_report_id):
    return run_delete_processed_report(processed_report_id)

@reports_bp.route('/restore/<int:processed_report_id>', methods=['POST'])
@has_permission('reports_export')
def restore_processed_report(processed_report_id):
    return run_restore_processed_report(processed_report_id)

