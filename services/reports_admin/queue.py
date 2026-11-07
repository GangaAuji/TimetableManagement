"""Admin report screens. queue."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response, current_app, send_file
from ui.pages import render_template
from extensions import get_db_connection
from security import has_permission, log_activity
from datetime import datetime, timedelta
import json
import os
import uuid

from services.reports_admin._common import ALLOWED_REPORT_TYPES, REPORT_LABELS, _ensure_processed_reports_table, _get_reports_storage_dir, _write_csv_file, _get_redirect_target, _clean_filters
from services.reports_admin.dataset import _build_report_export_dataset

def export_report(report_type):
    """
    Legacy direct export endpoint (disabled in queue-based workflow).
    """
    flash('Direct export is disabled. Process report first, then download from Reports Center table.', 'warning')
    return redirect(url_for('admin_reports.reports_index'))


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
