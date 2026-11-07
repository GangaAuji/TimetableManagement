"""Admin report screens. Shared helpers."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
import csv
import io
import os

ALLOWED_REPORT_TYPES = {
    'attendance',
    'timetable',
    'audit-logs',
    'shifts',
    'proxy-log',
    'invitations'
}

REPORT_LABELS = {
    'attendance': 'Attendance',
    'timetable': 'Timetable',
    'audit-logs': 'Audit Logs',
    'shifts': 'Shift Management',
    'proxy-log': 'Proxy Log',
    'invitations': 'Invitations',
    'users-export': 'Users export',
    'audit-export': 'Audit log export',
    'timetable-export': 'Timetable export',
}

_reports_table_ready = False


def _ensure_processed_reports_table(cursor):
    """Ensure processed reports metadata table exists for download queue."""
    global _reports_table_ready
    if _reports_table_ready:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_reports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            report_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'completed',
            filters_json TEXT NULL,
            row_count INT NOT NULL DEFAULT 0,
            file_name VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            created_by INT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            downloaded_at TIMESTAMP NULL DEFAULT NULL,
            progress TINYINT UNSIGNED NOT NULL DEFAULT 100,
            INDEX idx_processed_reports_created_at (created_at),
            INDEX idx_processed_reports_created_by (created_by),
            INDEX idx_processed_reports_queue (status, id),
            INDEX idx_processed_reports_recent (status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    _ensure_job_progress(cursor)
    _reports_table_ready = True


def _ensure_job_progress(cursor):
    """Add the progress column on tables created before queued exports."""
    cursor.execute("SHOW COLUMNS FROM processed_reports LIKE 'progress'")
    if cursor.fetchone():
        return
    try:
        cursor.execute(
            "ALTER TABLE processed_reports ADD COLUMN progress TINYINT UNSIGNED NOT NULL DEFAULT 100"
        )
    except Exception as exc:
        if 'Duplicate column' not in str(exc):
            raise

def _get_reports_storage_dir():
    """Get and create storage folder for processed CSV files."""
    reports_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    return reports_dir

def _write_csv_file(file_path, fieldnames, rows):
    """Persist report rows to CSV file."""
    with open(file_path, 'w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, '') for key in fieldnames})

def _get_redirect_target():
    """Return safe redirect target after processing report."""
    target = request.form.get('return_to')
    if target and target.startswith('/'):
        return target
    return url_for('admin_reports.reports_index')

def _create_csv_response(filename, fieldnames, rows):
    """Build a downloadable CSV response from dictionary rows."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, '') for key in fieldnames})

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    return response

def _clean_filters(payload):
    """Collect non-empty filter values for preview/export logging."""
    cleaned = {}
    for key in payload.keys():
        if key == 'csrf_token':
            continue
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == '':
            continue
        cleaned[key] = value
    return cleaned
