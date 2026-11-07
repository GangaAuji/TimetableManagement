"""Admin attendance screens."""

from services.attendance_admin._common import _table_exists, _decimal_to_number, _promote_log_to_attendance, _promote_log_to_faculty_attendance
from services.attendance_admin.students import attendance_overview, attendance_defaulters, student_attendance_details
from services.attendance_admin.faculty import faculty_attendance_overview, faculty_attendance_details
from services.attendance_admin.manage import manage_attendance, update_attendance
from services.attendance_admin.exports import export_overview, export_defaulters, charts_data
from services.attendance_admin.mobile import mobile_sync_logs, faculty_mobile_sync_logs, reprocess_faculty_mobile_sync_logs, reprocess_mobile_sync_logs

__all__ = [
    '_table_exists',
    '_decimal_to_number',
    '_promote_log_to_attendance',
    '_promote_log_to_faculty_attendance',
    'attendance_overview',
    'attendance_defaulters',
    'student_attendance_details',
    'faculty_attendance_overview',
    'faculty_attendance_details',
    'manage_attendance',
    'update_attendance',
    'export_overview',
    'export_defaulters',
    'charts_data',
    'mobile_sync_logs',
    'faculty_mobile_sync_logs',
    'reprocess_faculty_mobile_sync_logs',
    'reprocess_mobile_sync_logs',
]
