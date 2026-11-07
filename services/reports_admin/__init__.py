"""Admin report screens."""

from services.reports_admin._common import ALLOWED_REPORT_TYPES, REPORT_LABELS, _ensure_processed_reports_table, _get_reports_storage_dir, _write_csv_file, _get_redirect_target, _create_csv_response, _clean_filters
from services.reports_admin.dataset import _build_report_export_dataset
from services.reports_admin.center import preview_report, reports_index, reports_processor
from services.reports_admin.attendance import attendance_report
from services.reports_admin.timetable import timetable_report
from services.reports_admin.audit import audit_logs_report
from services.reports_admin.shifts import shifts_report
from services.reports_admin.proxy import proxy_log_report
from services.reports_admin.invitations import invitations_report
from services.reports_admin.queue import export_report, process_report, download_processed_report, delete_processed_report, restore_processed_report

__all__ = [
    'ALLOWED_REPORT_TYPES',
    'REPORT_LABELS',
    '_ensure_processed_reports_table',
    '_get_reports_storage_dir',
    '_write_csv_file',
    '_get_redirect_target',
    '_create_csv_response',
    '_clean_filters',
    '_build_report_export_dataset',
    'preview_report',
    'reports_index',
    'reports_processor',
    'attendance_report',
    'timetable_report',
    'audit_logs_report',
    'shifts_report',
    'proxy_log_report',
    'invitations_report',
    'export_report',
    'process_report',
    'download_processed_report',
    'delete_processed_report',
    'restore_processed_report',
]
