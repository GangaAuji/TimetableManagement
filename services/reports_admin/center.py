"""Admin report screens. center."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
from extensions import get_db_connection
from security import has_permission, log_activity

from services.reports_admin._common import ALLOWED_REPORT_TYPES, REPORT_LABELS, _ensure_processed_reports_table, _clean_filters
from services.reports_admin.dataset import _build_report_export_dataset

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


def reports_processor():
    """
    Legacy processor page has been replaced by per-report processing workflow.
    """
    flash('Use each report page to process data. Final download is available from Reports Center queue.', 'info')
    return redirect(url_for('admin_reports.reports_index'))
