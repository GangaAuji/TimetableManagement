"""
Admin Attendance Management Module
Handles attendance overview, reports, and management for administrators.
"""

from flask import Blueprint
from security import has_permission
from services.attendance_admin import (
    attendance_overview as run_attendance_overview,
    attendance_defaulters as run_attendance_defaulters,
    student_attendance_details as run_student_attendance_details,
    faculty_attendance_overview as run_faculty_attendance_overview,
    faculty_attendance_details as run_faculty_attendance_details,
    manage_attendance as run_manage_attendance,
    update_attendance as run_update_attendance,
    export_overview as run_export_overview,
    export_defaulters as run_export_defaulters,
    charts_data as run_charts_data,
    mobile_sync_logs as run_mobile_sync_logs,
    faculty_mobile_sync_logs as run_faculty_mobile_sync_logs,
    reprocess_faculty_mobile_sync_logs as run_reprocess_faculty_mobile_sync_logs,
    reprocess_mobile_sync_logs as run_reprocess_mobile_sync_logs,
)


attendance_admin_bp = Blueprint('attendance_admin', __name__, url_prefix='/admin/attendance')

@attendance_admin_bp.route('/')
@has_permission('attendance_view')
def attendance_overview():
    return run_attendance_overview()

@attendance_admin_bp.route('/defaulters')
@has_permission('attendance_view_defaulters')
def attendance_defaulters():
    return run_attendance_defaulters()

@attendance_admin_bp.route('/student/<int:student_id>')
@has_permission('attendance_view_details')
def student_attendance_details(student_id):
    return run_student_attendance_details(student_id)

@attendance_admin_bp.route('/faculty')
@has_permission('attendance_view_faculty')
def faculty_attendance_overview():
    return run_faculty_attendance_overview()

@attendance_admin_bp.route('/faculty/<int:faculty_id>')
@has_permission('attendance_view_faculty')
def faculty_attendance_details(faculty_id):
    return run_faculty_attendance_details(faculty_id)

@attendance_admin_bp.route('/manage')
@has_permission('attendance_manage')
def manage_attendance():
    return run_manage_attendance()

@attendance_admin_bp.route('/manage/update', methods=['POST'])
@has_permission('attendance_manage')
def update_attendance():
    return run_update_attendance()

@attendance_admin_bp.route('/export/overview')
@has_permission('attendance_view')
def export_overview():
    return run_export_overview()

@attendance_admin_bp.route('/export/defaulters')
@has_permission('attendance_view_defaulters')
def export_defaulters():
    return run_export_defaulters()

@attendance_admin_bp.route('/charts/data')
@has_permission('attendance_view')
def charts_data():
    return run_charts_data()

@attendance_admin_bp.route('/mobile-logs')
@has_permission('attendance_view')
def mobile_sync_logs():
    return run_mobile_sync_logs()

@attendance_admin_bp.route('/faculty-mobile-logs')
@has_permission('attendance_view_faculty')
def faculty_mobile_sync_logs():
    return run_faculty_mobile_sync_logs()

@attendance_admin_bp.route('/faculty-mobile-logs/reprocess', methods=['POST'])
@has_permission('attendance_manage_faculty')
def reprocess_faculty_mobile_sync_logs():
    return run_reprocess_faculty_mobile_sync_logs()

@attendance_admin_bp.route('/mobile-logs/reprocess', methods=['POST'])
@has_permission('attendance_manage')
def reprocess_mobile_sync_logs():
    return run_reprocess_mobile_sync_logs()

