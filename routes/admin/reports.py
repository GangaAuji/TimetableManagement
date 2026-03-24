"""
Admin Reports Module
Centralized reporting system for administrators with various report types.
"""

from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from database import get_db_connection
from security import has_permission, log_activity
from datetime import datetime, timedelta
from decimal import Decimal
import csv
import io
import json
import os
import uuid

reports_bp = Blueprint('admin_reports', __name__, url_prefix='/admin/reports')

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
    'invitations': 'Invitations'
}


def _ensure_processed_reports_table(cursor):
    """Ensure processed reports metadata table exists for download queue."""
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
            INDEX idx_processed_reports_created_at (created_at),
            INDEX idx_processed_reports_created_by (created_by)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


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


def _build_report_export_dataset(cursor, report_type, payload):
    """Build export dataset and ordered CSV fields for a report type."""
    rows = []
    fieldnames = []

    if report_type == 'attendance':
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')
        course_id = payload.get('course_id')
        class_id = payload.get('class_id')
        division_id = payload.get('division_id')

        query = """
            SELECT
                s.id as student_id,
                s.id as roll_number,
                s.name as full_name,
                c.name as course_name,
                cl.name as class_name,
                d.name as division_name,
                COUNT(a.id) as total_classes,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                ROUND(
                    (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / NULLIF(COUNT(a.id), 0)) * 100,
                    2
                ) as attendance_percentage
            FROM students s
            JOIN courses c ON s.course_id = c.id
            JOIN classes cl ON s.class_id = cl.id
            JOIN divisions d ON s.division_id = d.id
            LEFT JOIN attendance a ON s.id = a.student_id
        """

        conditions = []
        params = []
        if start_date:
            conditions.append("a.attendance_date >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("a.attendance_date <= %s")
            params.append(end_date)
        if course_id:
            conditions.append("s.course_id = %s")
            params.append(course_id)
        if class_id:
            conditions.append("s.class_id = %s")
            params.append(class_id)
        if division_id:
            conditions.append("s.division_id = %s")
            params.append(division_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " GROUP BY s.id, s.name, c.name, cl.name, d.name ORDER BY s.id"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        for row in rows:
            row['attendance_percentage'] = float(row.get('attendance_percentage') or 0)

        fieldnames = [
            'student_id', 'roll_number', 'full_name', 'course_name', 'class_name',
            'division_name', 'total_classes', 'present', 'absent', 'late', 'attendance_percentage'
        ]

    elif report_type == 'timetable':
        report_view = payload.get('report_type', 'class')
        entity_id = payload.get('entity_id')

        if report_view not in {'class', 'faculty', 'room'} or not entity_id:
            raise ValueError('Timetable export requires a report type and entity.')

        if report_view == 'class':
            query = """
                SELECT
                    t.day_of_week,
                    DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                    DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                    sub.name as subject_name,
                    sub.course_code as subject_code,
                    f.name as faculty_name,
                    r.room_number,
                    r.room_type as room_name,
                    d.name as division_name
                FROM timetable t
                JOIN subjects sub ON t.subject_id = sub.id
                JOIN faculty f ON t.faculty_id = f.user_id
                JOIN rooms r ON t.room_id = r.id
                JOIN divisions d ON t.division_id = d.id
                WHERE t.class_id = %s AND t.is_active = 1
                ORDER BY FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), t.start_time
            """
            cursor.execute(query, [entity_id])
            rows = cursor.fetchall()
            fieldnames = [
                'day_of_week', 'start_time', 'end_time', 'subject_name', 'subject_code',
                'faculty_name', 'room_number', 'room_name', 'division_name'
            ]
        elif report_view == 'faculty':
            query = """
                SELECT
                    t.day_of_week,
                    DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                    DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                    sub.name as subject_name,
                    sub.course_code as subject_code,
                    c.name as course_name,
                    cl.name as class_name,
                    d.name as division_name,
                    r.room_number,
                    r.room_type as room_name
                FROM timetable t
                JOIN subjects sub ON t.subject_id = sub.id
                JOIN courses c ON t.course_id = c.id
                JOIN classes cl ON t.class_id = cl.id
                JOIN divisions d ON t.division_id = d.id
                JOIN rooms r ON t.room_id = r.id
                WHERE t.faculty_id = %s AND t.is_active = 1
                ORDER BY FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), t.start_time
            """
            cursor.execute(query, [entity_id])
            rows = cursor.fetchall()
            fieldnames = [
                'day_of_week', 'start_time', 'end_time', 'subject_name', 'subject_code',
                'course_name', 'class_name', 'division_name', 'room_number', 'room_name'
            ]
        else:
            query = """
                SELECT
                    t.day_of_week,
                    DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                    DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                    sub.name as subject_name,
                    sub.course_code as subject_code,
                    f.name as faculty_name,
                    c.name as course_name,
                    cl.name as class_name,
                    d.name as division_name
                FROM timetable t
                JOIN subjects sub ON t.subject_id = sub.id
                JOIN faculty f ON t.faculty_id = f.user_id
                JOIN courses c ON t.course_id = c.id
                JOIN classes cl ON t.class_id = cl.id
                JOIN divisions d ON t.division_id = d.id
                WHERE t.room_id = %s AND t.is_active = 1
                ORDER BY FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'), t.start_time
            """
            cursor.execute(query, [entity_id])
            rows = cursor.fetchall()
            fieldnames = [
                'day_of_week', 'start_time', 'end_time', 'subject_name', 'subject_code',
                'faculty_name', 'course_name', 'class_name', 'division_name'
            ]

    elif report_type == 'audit-logs':
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')
        user_id = payload.get('user_id')
        action = payload.get('action')

        query = """
            SELECT
                al.id,
                u.username,
                al.activity_type as action,
                al.description,
                al.ip_address,
                al.user_agent,
                DATE_FORMAT(al.created_at, '%%Y-%%m-%%d %%H:%%i:%%s') as timestamp
            FROM user_activity_log al
            JOIN users u ON al.user_id = u.id
        """

        conditions = []
        params = []
        if start_date:
            conditions.append("DATE(al.created_at) >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(al.created_at) <= %s")
            params.append(end_date)
        if user_id:
            conditions.append("al.user_id = %s")
            params.append(user_id)
        if action:
            conditions.append("al.activity_type = %s")
            params.append(action)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY al.created_at DESC LIMIT 500"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        fieldnames = ['id', 'timestamp', 'username', 'action', 'description', 'ip_address', 'user_agent']

    elif report_type == 'shifts':
        status = payload.get('status')
        faculty_id = payload.get('faculty_id')
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')

        query = """
            SELECT
                scr.id,
                f.name as full_name,
                scr.current_shift_name as current_shift,
                scr.requested_shift_name as requested_shift,
                scr.reason,
                scr.status,
                DATE_FORMAT(scr.created_at, '%Y-%m-%d') as effective_date,
                DATE_FORMAT(scr.created_at, '%Y-%m-%d %H:%i') as created_at,
                COALESCE(scr.admin_response, '') as admin_remarks
            FROM shift_change_requests scr
            LEFT JOIN faculty f ON scr.faculty_id = f.id OR scr.faculty_id = f.user_id
        """

        conditions = []
        params = []
        if status:
            conditions.append("scr.status = %s")
            params.append(status)
        if faculty_id:
            conditions.append("(scr.faculty_id = %s OR f.id = %s OR f.user_id = %s)")
            params.extend([faculty_id, faculty_id, faculty_id])
        if start_date:
            conditions.append("DATE(scr.created_at) >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(scr.created_at) <= %s")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY scr.created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        fieldnames = [
            'id', 'full_name', 'current_shift', 'requested_shift', 'status',
            'effective_date', 'created_at', 'reason', 'admin_remarks'
        ]

    elif report_type == 'proxy-log':
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')

        query = """
            SELECT
                pl.id,
                f1.name as original_faculty,
                f2.name as proxy_faculty,
                sub.name as subject_name,
                course.name as course_name,
                c.name as class_name,
                d.name as division_name,
                DATE_FORMAT(pl.absence_date, '%Y-%m-%d') as proxy_date,
                DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                COALESCE(pl.approval_notes, '') as reason,
                DATE_FORMAT(COALESCE(pl.approval_date, pl.absence_date), '%Y-%m-%d %H:%i') as created_at
            FROM proxy_log pl
            JOIN faculty f1 ON pl.original_faculty_id = f1.user_id
            LEFT JOIN faculty f2 ON pl.proxy_faculty_id = f2.user_id
            JOIN timetable t ON pl.timetable_id = t.id
            JOIN subjects sub ON t.subject_id = sub.id
            JOIN courses course ON t.course_id = course.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
        """

        conditions = []
        params = []
        if start_date:
            conditions.append("pl.absence_date >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("pl.absence_date <= %s")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY pl.absence_date DESC, t.start_time DESC LIMIT 500"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        fieldnames = [
            'id', 'proxy_date', 'start_time', 'end_time', 'original_faculty',
            'proxy_faculty', 'subject_name', 'course_name', 'class_name',
            'division_name', 'reason', 'created_at'
        ]

    elif report_type == 'invitations':
        role = payload.get('role')
        status = payload.get('status')
        start_date = payload.get('start_date')
        end_date = payload.get('end_date')
        course_id = payload.get('course_id')
        class_id = payload.get('class_id')
        division_id = payload.get('division_id')

        query = """
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
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY ri.created_at DESC LIMIT 500"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        fieldnames = [
            'id', 'email', 'role', 'status', 'display_status',
            'course_name', 'class_name', 'division_name', 'created_at', 'expires_at'
        ]

    return rows, fieldnames


@reports_bp.route('/preview/<report_type>', methods=['POST'])
@has_permission('reports_export')
def preview_report(report_type):
    """
    Preview report row count before CSV export.
    """
    if report_type not in ALLOWED_REPORT_TYPES:
        return jsonify({'success': False, 'error': 'Invalid report type selected.'}), 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    filters = _clean_filters(request.form)
    try:
        rows, _ = _build_report_export_dataset(cursor, report_type, request.form)
        row_count = len(rows)

        log_activity(
            session.get('user_id'),
            'reports_preview',
            f'Previewed {report_type} export ({row_count} rows)',
            entity_type='report',
            entity_id=report_type,
            new_values={
                'report_type': report_type,
                'row_count': row_count,
                'filters': filters,
                'status': 'success'
            }
        )

        return jsonify({
            'success': True,
            'report_type': report_type,
            'row_count': row_count,
            'filters': filters
        })
    except ValueError as validation_error:
        log_activity(
            session.get('user_id'),
            'reports_preview',
            f'Preview failed for {report_type}: {validation_error}',
            entity_type='report',
            entity_id=report_type,
            new_values={
                'report_type': report_type,
                'filters': filters,
                'status': 'validation_error',
                'error': str(validation_error)
            }
        )
        return jsonify({'success': False, 'error': str(validation_error)}), 400
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/')
@has_permission('reports_view')
def reports_index():
    """
    Main reports dashboard showing all available report types.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        _ensure_processed_reports_table(cursor)
        connection.commit()

        cursor.execute("""
            SELECT
                pr.id,
                pr.report_type,
                pr.status,
                pr.row_count,
                pr.file_name,
                pr.created_at,
                pr.downloaded_at,
                u.username as created_by_name
            FROM processed_reports pr
            LEFT JOIN users u ON pr.created_by = u.id
            WHERE pr.status <> 'deleted'
            ORDER BY pr.created_at DESC
            LIMIT 100
        """)
        processed_reports = cursor.fetchall()

        cursor.execute("""
            SELECT
                pr.id,
                pr.report_type,
                pr.status,
                pr.row_count,
                pr.file_name,
                pr.created_at,
                pr.downloaded_at,
                u.username as created_by_name
            FROM processed_reports pr
            LEFT JOIN users u ON pr.created_by = u.id
            WHERE pr.status = 'deleted'
            ORDER BY pr.created_at DESC
            LIMIT 50
        """)
        deleted_reports = cursor.fetchall()

        return render_template(
            'admin/reports/index.html',
            processed_reports=processed_reports,
            deleted_reports=deleted_reports,
            report_labels=REPORT_LABELS
        )
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/processor')
@has_permission('reports_export')
def reports_processor():
    """
    Legacy processor page has been replaced by per-report processing workflow.
    """
    flash('Use each report page to process data. Final download is available from Reports Center queue.', 'info')
    return redirect(url_for('admin_reports.reports_index'))


@reports_bp.route('/attendance')
@has_permission('reports_view_attendance')
def attendance_report():
    """
    Generate attendance reports with various filters.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT id, name FROM courses ORDER BY name")
        courses = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM classes ORDER BY name")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM divisions ORDER BY name")
        divisions = cursor.fetchall()
        
        # Get report data if filters are applied
        report_data = None
        filters = {}
        
        if request.args.get('generate'):
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            course_id = request.args.get('course_id')
            class_id = request.args.get('class_id')
            division_id = request.args.get('division_id')
            
            filters = {
                'start_date': start_date,
                'end_date': end_date,
                'course_id': course_id,
                'class_id': class_id,
                'division_id': division_id
            }
            
            # Build query based on filters
            query = """
                SELECT 
                    s.id,
                    s.id as roll_number,
                    s.name as full_name,
                    c.name as course_name,
                    cl.name as class_name,
                    d.name as division_name,
                    COUNT(a.id) as total_classes,
                    SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present,
                    SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent,
                    SUM(CASE WHEN a.status = 'Late' THEN 1 ELSE 0 END) as late,
                    ROUND(
                        (SUM(CASE WHEN a.status IN ('Present', 'Late') THEN 1 ELSE 0 END) / COUNT(a.id)) * 100, 
                        2
                    ) as attendance_percentage
                FROM students s
                JOIN courses c ON s.course_id = c.id
                JOIN classes cl ON s.class_id = cl.id
                JOIN divisions d ON s.division_id = d.id
                LEFT JOIN attendance a ON s.id = a.student_id
            """
            
            conditions = []
            params = []
            
            if start_date:
                conditions.append("a.attendance_date >= %s")
                params.append(start_date)
            
            if end_date:
                conditions.append("a.attendance_date <= %s")
                params.append(end_date)
            
            if course_id:
                conditions.append("s.course_id = %s")
                params.append(course_id)
            
            if class_id:
                conditions.append("s.class_id = %s")
                params.append(class_id)
            
            if division_id:
                conditions.append("s.division_id = %s")
                params.append(division_id)
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " GROUP BY s.id, s.name, c.name, cl.name, d.name ORDER BY s.id"
            
            cursor.execute(query, params)
            report_data = cursor.fetchall()
            
            # Convert Decimal to float
            if report_data:
                for row in report_data:
                    row['attendance_percentage'] = float(row['attendance_percentage'] or 0)
        
        return render_template('admin/reports/attendance.html',
                             courses=courses,
                             classes=classes,
                             divisions=divisions,
                             report_data=report_data,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/timetable')
@has_permission('reports_view_timetable')
def timetable_report():
    """
    Generate timetable reports for various entities.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT id, name FROM courses ORDER BY name")
        courses = cursor.fetchall()
        
        cursor.execute("SELECT id, name FROM classes ORDER BY name")
        classes = cursor.fetchall()
        
        cursor.execute("SELECT user_id, name as full_name FROM faculty ORDER BY name")
        faculty = cursor.fetchall()
        
        cursor.execute("SELECT id, room_number, room_type as room_name FROM rooms ORDER BY room_number")
        rooms = cursor.fetchall()
        
        # Get report data if filters are applied
        report_data = None
        filters = {}
        
        if request.args.get('generate'):
            report_type = request.args.get('report_type', 'class')
            entity_id = request.args.get('entity_id')
            
            filters = {
                'report_type': report_type,
                'entity_id': entity_id
            }
            
            if report_type == 'class' and entity_id:
                query = """
                    SELECT 
                        t.day_of_week,
                        DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                        DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                        sub.name as subject_name,
                        sub.course_code as subject_code,
                        f.name as faculty_name,
                        r.room_number,
                        r.room_type as room_name,
                        d.name as division_name
                    FROM timetable t
                    JOIN subjects sub ON t.subject_id = sub.id
                    JOIN faculty f ON t.faculty_id = f.user_id
                    JOIN rooms r ON t.room_id = r.id
                    JOIN divisions d ON t.division_id = d.id
                    WHERE t.class_id = %s AND t.is_active = 1
                    ORDER BY 
                        FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'),
                        t.start_time
                """
                cursor.execute(query, [entity_id])
                report_data = cursor.fetchall()
            
            elif report_type == 'faculty' and entity_id:
                query = """
                    SELECT 
                        t.day_of_week,
                        DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                        DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                        sub.name as subject_name,
                        sub.course_code as subject_code,
                        c.name as course_name,
                        cl.name as class_name,
                        d.name as division_name,
                        r.room_number,
                        r.room_type as room_name
                    FROM timetable t
                    JOIN subjects sub ON t.subject_id = sub.id
                    JOIN courses c ON t.course_id = c.id
                    JOIN classes cl ON t.class_id = cl.id
                    JOIN divisions d ON t.division_id = d.id
                    JOIN rooms r ON t.room_id = r.id
                    WHERE t.faculty_id = %s AND t.is_active = 1
                    ORDER BY 
                        FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'),
                        t.start_time
                """
                cursor.execute(query, [entity_id])
                report_data = cursor.fetchall()
            
            elif report_type == 'room' and entity_id:
                query = """
                    SELECT 
                        t.day_of_week,
                        DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                        DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                        sub.name as subject_name,
                        f.name as faculty_name,
                        c.name as course_name,
                        cl.name as class_name,
                        d.name as division_name
                    FROM timetable t
                    JOIN subjects sub ON t.subject_id = sub.id
                    JOIN faculty f ON t.faculty_id = f.user_id
                    JOIN courses c ON t.course_id = c.id
                    JOIN classes cl ON t.class_id = cl.id
                    JOIN divisions d ON t.division_id = d.id
                    WHERE t.room_id = %s AND t.is_active = 1
                    ORDER BY 
                        FIELD(t.day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'),
                        t.start_time
                """
                cursor.execute(query, [entity_id])
                report_data = cursor.fetchall()
        
        return render_template('admin/reports/timetable.html',
                             courses=courses,
                             classes=classes,
                             faculty=faculty,
                             rooms=rooms,
                             report_data=report_data,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/audit-logs')
@has_permission('reports_view_audit')
def audit_logs_report():
    """
    Generate audit logs reports with filters.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT DISTINCT activity_type as action FROM user_activity_log ORDER BY activity_type")
        actions = cursor.fetchall()
        
        cursor.execute("SELECT id, username FROM users ORDER BY username")
        users = cursor.fetchall()
        
        # Get report data
        filters = {}
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        user_id = request.args.get('user_id')
        action = request.args.get('action')
        
        filters = {
            'start_date': start_date,
            'end_date': end_date,
            'user_id': user_id,
            'action': action
        }
        
        query = """
            SELECT 
                al.id,
                u.username,
                al.activity_type as action,
                al.description,
                al.ip_address,
                al.user_agent,
                DATE_FORMAT(al.created_at, '%%Y-%%m-%%d %%H:%%i:%%s') as timestamp
            FROM user_activity_log al
            JOIN users u ON al.user_id = u.id
        """
        
        conditions = []
        params = []
        
        if start_date:
            conditions.append("DATE(al.created_at) >= %s")
            params.append(start_date)
        
        if end_date:
            conditions.append("DATE(al.created_at) <= %s")
            params.append(end_date)
        
        if user_id:
            conditions.append("al.user_id = %s")
            params.append(user_id)
        
        if action:
            conditions.append("al.activity_type = %s")
            params.append(action)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY al.created_at DESC LIMIT 500"
        
        cursor.execute(query, params)
        report_data = cursor.fetchall()
        
        return render_template('admin/reports/audit_logs.html',
                             actions=actions,
                             users=users,
                             report_data=report_data,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/shifts')
@has_permission('reports_view_shifts')
def shifts_report():
    """
    Generate shift management reports.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get filter options
        cursor.execute("SELECT DISTINCT status FROM shift_change_requests ORDER BY status")
        statuses = cursor.fetchall()

        cursor.execute("""
            SELECT DISTINCT f.user_id, f.name
            FROM shift_change_requests scr
            JOIN faculty f ON scr.faculty_id = f.id OR scr.faculty_id = f.user_id
            ORDER BY f.name
        """)
        faculty_options = cursor.fetchall()

        status = request.args.get('status')
        faculty_id = request.args.get('faculty_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        filters = {
            'status': status,
            'faculty_id': faculty_id,
            'start_date': start_date,
            'end_date': end_date
        }

        # Get shift change requests with details
        query = """
            SELECT 
                scr.id,
                u.username,
                f.name as full_name,
                scr.current_shift_name as current_shift,
                scr.requested_shift_name as requested_shift,
                scr.reason,
                scr.status,
                DATE_FORMAT(scr.created_at, '%Y-%m-%d') as effective_date,
                DATE_FORMAT(scr.created_at, '%Y-%m-%d %H:%i') as created_at,
                scr.admin_response as admin_remarks
            FROM shift_change_requests scr
            LEFT JOIN faculty f ON scr.faculty_id = f.id OR scr.faculty_id = f.user_id
            LEFT JOIN users u ON f.user_id = u.id
        """

        conditions = []
        params = []
        if status:
            conditions.append("scr.status = %s")
            params.append(status)
        if faculty_id:
            conditions.append("(scr.faculty_id = %s OR f.id = %s OR f.user_id = %s)")
            params.extend([faculty_id, faculty_id, faculty_id])
        if start_date:
            conditions.append("DATE(scr.created_at) >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("DATE(scr.created_at) <= %s")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY scr.created_at DESC"
        cursor.execute(query, params)
        shift_requests = cursor.fetchall()
        
        # Get shift patterns summary
        cursor.execute("""
            SELECT 
                sp.shift_name as name,
                DATE_FORMAT(sp.start_time, '%H:%i') as start_time,
                DATE_FORMAT(sp.end_time, '%H:%i') as end_time,
                COUNT(DISTINCT fa.faculty_id) as faculty_count
            FROM shift_patterns sp
            LEFT JOIN faculty_availability fa ON sp.id = fa.shift_pattern_id
            GROUP BY sp.id, sp.shift_name, sp.start_time, sp.end_time
            ORDER BY sp.start_time
        """)
        shift_summary = cursor.fetchall()
        
        return render_template('admin/reports/shifts.html',
                             shift_requests=shift_requests,
                             shift_summary=shift_summary,
                             statuses=statuses,
                             faculty_options=faculty_options,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/proxy-log')
@has_permission('reports_view_proxy')
def proxy_log_report():
    """
    Generate proxy assignment reports.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get proxy log entries
        filters = {}
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        filters = {
            'start_date': start_date,
            'end_date': end_date
        }
        
        query = """
            SELECT 
                pl.id,
                f1.name as original_faculty,
                f2.name as proxy_faculty,
                sub.name as subject_name,
                course.name as course_name,
                c.name as class_name,
                d.name as division_name,
                DATE_FORMAT(pl.absence_date, '%Y-%m-%d') as proxy_date,
                DATE_FORMAT(t.start_time, '%H:%i') as start_time,
                DATE_FORMAT(t.end_time, '%H:%i') as end_time,
                COALESCE(pl.approval_notes, '') as reason,
                DATE_FORMAT(COALESCE(pl.approval_date, pl.absence_date), '%Y-%m-%d %H:%i') as created_at
            FROM proxy_log pl
            JOIN faculty f1 ON pl.original_faculty_id = f1.user_id
            JOIN faculty f2 ON pl.proxy_faculty_id = f2.user_id
            JOIN timetable t ON pl.timetable_id = t.id
            JOIN subjects sub ON t.subject_id = sub.id
            JOIN courses course ON t.course_id = course.id
            JOIN classes c ON t.class_id = c.id
            LEFT JOIN divisions d ON t.division_id = d.id
        """
        
        conditions = []
        params = []
        
        if start_date:
            conditions.append("pl.absence_date >= %s")
            params.append(start_date)
        
        if end_date:
            conditions.append("pl.absence_date <= %s")
            params.append(end_date)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY pl.absence_date DESC, t.start_time DESC LIMIT 500"
        
        cursor.execute(query, params)
        proxy_logs = cursor.fetchall()
        
        return render_template('admin/reports/proxy_log.html',
                             proxy_logs=proxy_logs,
                             filters=filters)
    
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/invitations')
@has_permission('reports_view_invitations')
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


@reports_bp.route('/export/<report_type>', methods=['POST'])
@has_permission('reports_export')
def export_report(report_type):
    """
    Legacy direct export endpoint (disabled in queue-based workflow).
    """
    flash('Direct export is disabled. Process report first, then download from Reports Center table.', 'warning')
    return redirect(url_for('admin_reports.reports_index'))


@reports_bp.route('/process/<report_type>', methods=['POST'])
@has_permission('reports_export')
def process_report(report_type):
    """
    Process report with current filters and store downloadable CSV metadata.
    """
    if report_type not in ALLOWED_REPORT_TYPES:
        flash('Invalid report type selected.', 'error')
        return redirect(_get_redirect_target())

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    filters = _clean_filters(request.form)
    redirect_target = _get_redirect_target()

    try:
        _ensure_processed_reports_table(cursor)
        rows, fieldnames = _build_report_export_dataset(cursor, report_type, request.form)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_suffix = uuid.uuid4().hex[:8]
        file_name = f"{report_type}_report_{timestamp}_{unique_suffix}.csv"
        file_path = os.path.join(_get_reports_storage_dir(), file_name)

        _write_csv_file(file_path, fieldnames, rows)

        cursor.execute("""
            INSERT INTO processed_reports (
                report_type, status, filters_json, row_count, file_name, file_path, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            report_type,
            'completed',
            json.dumps(filters),
            len(rows),
            file_name,
            file_path,
            session.get('user_id')
        ))
        processed_id = cursor.lastrowid
        connection.commit()

        log_activity(
            session.get('user_id'),
            'reports_process',
            f'Processed {report_type} report #{processed_id} ({len(rows)} rows)',
            entity_type='processed_report',
            entity_id=processed_id,
            new_values={
                'report_type': report_type,
                'row_count': len(rows),
                'filters': filters,
                'status': 'completed',
                'file_name': file_name
            }
        )

        flash(f"{REPORT_LABELS.get(report_type, report_type.title())} report processed successfully. Download from Reports Center table.", 'success')
        return redirect(redirect_target)

    except ValueError as validation_error:
        log_activity(
            session.get('user_id'),
            'reports_process',
            f'Processing failed for {report_type}: {validation_error}',
            entity_type='processed_report',
            entity_id=None,
            new_values={
                'report_type': report_type,
                'filters': filters,
                'status': 'validation_error',
                'error': str(validation_error)
            }
        )
        flash(str(validation_error), 'error')
        connection.rollback()
        return redirect(redirect_target)
    except Exception as process_error:
        connection.rollback()
        log_activity(
            session.get('user_id'),
            'reports_process',
            f'Processing failed for {report_type}: {process_error}',
            entity_type='processed_report',
            entity_id=None,
            new_values={
                'report_type': report_type,
                'filters': filters,
                'status': 'error',
                'error': str(process_error)
            }
        )
        flash('Failed to process report. Please try again.', 'error')
        return redirect(redirect_target)
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/download/<int:processed_report_id>')
@has_permission('reports_export')
def download_processed_report(processed_report_id):
    """
    Download a previously processed report from reports center table.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        _ensure_processed_reports_table(cursor)

        cursor.execute("""
            SELECT id, report_type, status, row_count, file_name, file_path
            FROM processed_reports
            WHERE id = %s
        """, (processed_report_id,))
        report_record = cursor.fetchone()

        if not report_record:
            flash('Processed report not found.', 'error')
            return redirect(url_for('admin_reports.reports_index'))

        if report_record.get('status') == 'deleted':
            flash('This report is in trash. Restore it before download.', 'warning')
            return redirect(url_for('admin_reports.reports_index'))

        if report_record.get('status') != 'completed' or not os.path.exists(report_record.get('file_path', '')):
            flash('Processed report file is not available for download.', 'error')
            return redirect(url_for('admin_reports.reports_index'))

        cursor.execute(
            "UPDATE processed_reports SET downloaded_at = NOW() WHERE id = %s",
            (processed_report_id,)
        )
        connection.commit()

        log_activity(
            session.get('user_id'),
            'reports_download',
            f"Downloaded processed report #{processed_report_id} ({report_record['report_type']})",
            entity_type='processed_report',
            entity_id=processed_report_id,
            new_values={
                'report_type': report_record['report_type'],
                'row_count': report_record['row_count'],
                'status': report_record['status'],
                'file_name': report_record['file_name']
            }
        )

        return send_file(
            report_record['file_path'],
            as_attachment=True,
            download_name=report_record['file_name'],
            mimetype='text/csv'
        )
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/delete/<int:processed_report_id>', methods=['POST'])
@has_permission('reports_export')
def delete_processed_report(processed_report_id):
    """
    Soft delete a processed report record (move to trash).
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        _ensure_processed_reports_table(cursor)

        cursor.execute("""
            SELECT id, report_type, file_name, file_path, row_count
            FROM processed_reports
            WHERE id = %s
        """, (processed_report_id,))
        report_record = cursor.fetchone()

        if not report_record:
            flash('Processed report not found.', 'error')
            return redirect(url_for('admin_reports.reports_index'))

        cursor.execute(
            "UPDATE processed_reports SET status = 'deleted' WHERE id = %s",
            (processed_report_id,)
        )
        connection.commit()

        log_activity(
            session.get('user_id'),
            'reports_soft_delete',
            f"Moved processed report #{processed_report_id} to trash ({report_record['report_type']})",
            entity_type='processed_report',
            entity_id=processed_report_id,
            new_values={
                'report_type': report_record['report_type'],
                'row_count': report_record['row_count'],
                'file_name': report_record['file_name'],
                'status': 'deleted',
                'mode': 'soft_delete'
            }
        )

        flash('Processed report moved to trash.', 'success')
        return redirect(url_for('admin_reports.reports_index'))
    except Exception:
        connection.rollback()
        flash('Failed to delete processed report.', 'error')
        return redirect(url_for('admin_reports.reports_index'))
    finally:
        cursor.close()
        connection.close()


@reports_bp.route('/restore/<int:processed_report_id>', methods=['POST'])
@has_permission('reports_export')
def restore_processed_report(processed_report_id):
    """
    Restore a soft-deleted processed report.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        _ensure_processed_reports_table(cursor)

        cursor.execute("""
            SELECT id, report_type, status, file_name, file_path, row_count
            FROM processed_reports
            WHERE id = %s
        """, (processed_report_id,))
        report_record = cursor.fetchone()

        if not report_record:
            flash('Processed report not found.', 'error')
            return redirect(url_for('admin_reports.reports_index'))

        if report_record.get('status') != 'deleted':
            flash('Processed report is not in trash.', 'warning')
            return redirect(url_for('admin_reports.reports_index'))

        if not report_record.get('file_path') or not os.path.exists(report_record.get('file_path')):
            flash('Cannot restore report because file is missing.', 'error')
            return redirect(url_for('admin_reports.reports_index'))

        cursor.execute(
            "UPDATE processed_reports SET status = 'completed' WHERE id = %s",
            (processed_report_id,)
        )
        connection.commit()

        log_activity(
            session.get('user_id'),
            'reports_restore',
            f"Restored processed report #{processed_report_id} ({report_record['report_type']})",
            entity_type='processed_report',
            entity_id=processed_report_id,
            new_values={
                'report_type': report_record['report_type'],
                'row_count': report_record['row_count'],
                'file_name': report_record['file_name'],
                'status': 'completed',
                'mode': 'restore'
            }
        )

        flash('Processed report restored successfully.', 'success')
        return redirect(url_for('admin_reports.reports_index'))
    except Exception:
        connection.rollback()
        flash('Failed to restore processed report.', 'error')
        return redirect(url_for('admin_reports.reports_index'))
    finally:
        cursor.close()
        connection.close()
