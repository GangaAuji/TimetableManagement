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
