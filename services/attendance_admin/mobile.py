"""Admin attendance screens. mobile."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response
from ui.pages import render_template
from core.pagination import page_bounds
from extensions import get_db_connection
from datetime import datetime, timedelta

from services.attendance_admin._common import _table_exists, _decimal_to_number, _promote_log_to_attendance, _promote_log_to_faculty_attendance

def mobile_sync_logs():
    """Show mobile synced attendance events from attendance_logs."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'attendance_logs'):
            flash("attendance_logs table not found. Run mobile attendance migration first.", "warning")
            return render_template(
                'admin/attendance/mobile_logs.html',
                logs=[],
                stats={'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
                filters={'date': '', 'processing_status': '', 'device_id': '', 'student_query': '', 'limit': 100},
            )

        filter_date = (request.args.get('date') or '').strip()
        processing_status = (request.args.get('processing_status') or '').strip().lower()
        device_id = (request.args.get('device_id') or '').strip()
        student_query = (request.args.get('student_query') or '').strip()
        limit = request.args.get('limit', 100, type=int) or 100
        limit = max(1, min(limit, 500))

        where_clauses = ['1=1']
        params = []

        if filter_date:
            where_clauses.append('al.attendance_date = %s')
            params.append(filter_date)

        if processing_status in ('processed', 'pending', 'failed'):
            where_clauses.append('al.processing_status = %s')
            params.append(processing_status)

        if device_id:
            where_clauses.append('al.device_id LIKE %s')
            params.append(f'%{device_id}%')

        if student_query:
            where_clauses.append(
                '(st.name LIKE %s OR st.roll_number LIKE %s OR CAST(al.student_id AS CHAR) LIKE %s)'
            )
            like_student = f'%{student_query}%'
            params.extend([like_student, like_student, like_student])

        where_sql = ' AND '.join(where_clauses)

        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN al.processing_status = 'processed' THEN 1 ELSE 0 END) AS processed,
                SUM(CASE WHEN al.processing_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN al.processing_status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM attendance_logs al
            LEFT JOIN students st ON st.id = al.student_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        stats = cursor.fetchone() or {}
        stats = {
            'total': int(stats.get('total') or 0),
            'processed': int(stats.get('processed') or 0),
            'pending': int(stats.get('pending') or 0),
            'failed': int(stats.get('failed') or 0),
        }

        cursor.execute(
            f"""
            SELECT
                al.id,
                al.event_uuid,
                al.device_id,
                al.student_id,
                al.timetable_id,
                al.attendance_date,
                al.status,
                al.processing_status,
                al.confidence,
                al.face_model,
                al.detector_model,
                al.remarks,
                al.error_message,
                al.created_at,
                al.captured_at,
                al.processed_at,
                st.name AS student_name,
                st.roll_number,
                u.username AS marked_by_username,
                f.name AS marked_by_faculty,
                sub.name AS subject_name,
                c.name AS course_name,
                cl.name AS class_name,
                d.name AS division_name
            FROM attendance_logs al
            LEFT JOIN students st ON st.id = al.student_id
            LEFT JOIN users u ON u.id = al.marked_by_user_id
            LEFT JOIN faculty f ON f.id = al.marked_by_faculty_id
            LEFT JOIN timetable t ON t.id = al.timetable_id
            LEFT JOIN subjects sub ON sub.id = t.subject_id
            LEFT JOIN courses c ON c.id = t.course_id
            LEFT JOIN classes cl ON cl.id = t.class_id
            LEFT JOIN divisions d ON d.id = t.division_id
            WHERE {where_sql}
            ORDER BY al.created_at DESC
            LIMIT %s
            """,
            tuple(params + [limit]),
        )
        logs = cursor.fetchall() or []

        for row in logs:
            row['confidence'] = _decimal_to_number(row.get('confidence'))
            for key in ('attendance_date', 'created_at', 'captured_at', 'processed_at'):
                value = row.get(key)
                if isinstance(value, datetime):
                    if key == 'attendance_date':
                        row[key] = value.strftime('%Y-%m-%d')
                    else:
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')

        return render_template(
            'admin/attendance/mobile_logs.html',
            logs=logs,
            stats=stats,
            filters={
                'date': filter_date,
                'processing_status': processing_status,
                'device_id': device_id,
                'student_query': student_query,
                'limit': limit,
            },
        )
    except Exception as e:
        print(f"Error fetching mobile sync logs: {e}")
        import traceback
        traceback.print_exc()
        flash("Unable to load mobile sync attendance logs.", "danger")
        return render_template(
            'admin/attendance/mobile_logs.html',
            logs=[],
            stats={'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
            filters={'date': '', 'processing_status': '', 'device_id': '', 'student_query': '', 'limit': 100},
        )
    finally:
        cursor.close()
        connection.close()


def faculty_mobile_sync_logs():
    """Show mobile synced faculty attendance events from faculty_attendance_logs."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'faculty_attendance_logs'):
            flash(
                "faculty_attendance_logs table not found. Run `flask db upgrade`.",
                "warning",
            )
            return render_template(
                'admin/attendance/faculty_mobile_logs.html',
                logs=[],
                stats={'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
                filters={
                    'date': '',
                    'processing_status': '',
                    'device_id': '',
                    'faculty_query': '',
                    'shift_query': '',
                    'per_page': 100,
                },
                pagination={
                    'page': 1,
                    'per_page': 100,
                    'total_count': 0,
                    'total_pages': 1,
                    'has_prev': False,
                    'has_next': False,
                    'start_index': 0,
                    'end_index': 0,
                },
            )

        filter_date = (request.args.get('date') or '').strip()
        processing_status = (request.args.get('processing_status') or '').strip().lower()
        device_id = (request.args.get('device_id') or '').strip()
        faculty_query = (request.args.get('faculty_query') or '').strip()
        shift_query = (request.args.get('shift_query') or '').strip()
        page = request.args.get('page', 1, type=int) or 1
        page = max(page, 1)

        per_page = request.args.get('per_page', type=int)
        if per_page is None:
            per_page = request.args.get('limit', 100, type=int)
        per_page = per_page or 100
        if per_page not in (20, 50, 100):
            per_page = 100

        where_clauses = ['1=1']
        params = []

        if filter_date:
            where_clauses.append('fal.attendance_date = %s')
            params.append(filter_date)

        if processing_status in ('processed', 'pending', 'failed'):
            where_clauses.append('fal.processing_status = %s')
            params.append(processing_status)

        if device_id:
            where_clauses.append('fal.device_id LIKE %s')
            params.append(f'%{device_id}%')

        if faculty_query:
            where_clauses.append(
                '('
                'f.name LIKE %s '
                'OR f.employee_id LIKE %s '
                'OR CAST(fal.faculty_id AS CHAR) LIKE %s '
                'OR CAST(fal.faculty_user_id AS CHAR) LIKE %s'
                ')'
            )
            like_faculty = f'%{faculty_query}%'
            params.extend([like_faculty, like_faculty, like_faculty, like_faculty])

        if shift_query:
            where_clauses.append('(fal.shift_name LIKE %s OR fal.shift_code LIKE %s)')
            like_shift = f'%{shift_query}%'
            params.extend([like_shift, like_shift])

        where_sql = ' AND '.join(where_clauses)

        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN fal.processing_status = 'processed' THEN 1 ELSE 0 END) AS processed,
                SUM(CASE WHEN fal.processing_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN fal.processing_status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM faculty_attendance_logs fal
            LEFT JOIN faculty f ON f.id = fal.faculty_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        stats = cursor.fetchone() or {}
        stats = {
            'total': int(stats.get('total') or 0),
            'processed': int(stats.get('processed') or 0),
            'pending': int(stats.get('pending') or 0),
            'failed': int(stats.get('failed') or 0),
        }

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM faculty_attendance_logs fal
            LEFT JOIN faculty f ON f.id = fal.faculty_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        total_count_row = cursor.fetchone() or {}
        total_count = int(total_count_row.get('total_count') or 0)
        total_pages = page_bounds(page, per_page, total_count, minimum_pages=1)[1]
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * per_page

        cursor.execute(
            f"""
            SELECT
                fal.id,
                fal.event_uuid,
                fal.device_id,
                fal.faculty_id,
                fal.faculty_user_id,
                fal.attendance_date,
                fal.day_of_week,
                fal.shift_key,
                fal.shift_pattern_id,
                fal.shift_name,
                fal.shift_code,
                fal.shift_start_time,
                fal.shift_end_time,
                fal.status,
                fal.processing_status,
                fal.confidence,
                fal.face_model,
                fal.detector_model,
                fal.remarks,
                fal.error_message,
                fal.created_at,
                fal.captured_at,
                fal.processed_at,
                f.name AS faculty_name,
                f.employee_id,
                d.name AS department_name,
                fu.username AS faculty_username,
                mu.username AS marked_by_username,
                sp.shift_name AS shift_pattern_name,
                sp.shift_code AS shift_pattern_code
            FROM faculty_attendance_logs fal
            LEFT JOIN faculty f ON f.id = fal.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN users fu ON fu.id = fal.faculty_user_id
            LEFT JOIN users mu ON mu.id = fal.marked_by_user_id
            LEFT JOIN shift_patterns sp ON sp.id = fal.shift_pattern_id
            WHERE {where_sql}
            ORDER BY fal.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*params, per_page, offset]),
        )
        logs = cursor.fetchall() or []

        for row in logs:
            row['confidence'] = _decimal_to_number(row.get('confidence'))
            for key in ('attendance_date', 'created_at', 'captured_at', 'processed_at'):
                value = row.get(key)
                if isinstance(value, datetime):
                    if key == 'attendance_date':
                        row[key] = value.strftime('%Y-%m-%d')
                    else:
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')

        pagination = {
            'page': page,
            'per_page': per_page,
            'total_count': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'start_index': (offset + 1) if total_count > 0 else 0,
            'end_index': min(offset + len(logs), total_count),
        }

        return render_template(
            'admin/attendance/faculty_mobile_logs.html',
            logs=logs,
            stats=stats,
            filters={
                'date': filter_date,
                'processing_status': processing_status,
                'device_id': device_id,
                'faculty_query': faculty_query,
                'shift_query': shift_query,
                'per_page': per_page,
            },
            pagination=pagination,
        )
    except Exception as e:
        print(f"Error fetching faculty mobile sync logs: {e}")
        import traceback
        traceback.print_exc()
        flash("Unable to load faculty mobile sync logs.", "danger")
        return render_template(
            'admin/attendance/faculty_mobile_logs.html',
            logs=[],
            stats={'total': 0, 'processed': 0, 'pending': 0, 'failed': 0},
            filters={
                'date': '',
                'processing_status': '',
                'device_id': '',
                'faculty_query': '',
                'shift_query': '',
                'per_page': 100,
            },
            pagination={
                'page': 1,
                'per_page': 100,
                'total_count': 0,
                'total_pages': 1,
                'has_prev': False,
                'has_next': False,
                'start_index': 0,
                'end_index': 0,
            },
        )
    finally:
        cursor.close()
        connection.close()


def reprocess_faculty_mobile_sync_logs():
    """Reprocess pending/failed faculty mobile logs into faculty_attendance table."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'faculty_attendance_logs') or not _table_exists(cursor, 'faculty_attendance'):
            flash(
                'faculty_attendance_logs/faculty_attendance tables not found. Run migration first.',
                'warning',
            )
            return redirect(url_for('attendance_admin.faculty_mobile_sync_logs'))

        limit = request.form.get('limit', 100, type=int) or 100
        limit = max(1, min(limit, 500))

        cursor.execute(
            """
            SELECT *
            FROM faculty_attendance_logs
            WHERE processing_status IN ('pending', 'failed')
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        log_rows = cursor.fetchall() or []

        retried = 0
        processed = 0
        failed = 0

        for log_row in log_rows:
            retried += 1
            try:
                _promote_log_to_faculty_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE faculty_attendance_logs
                    SET processing_status = 'processed',
                        processed_at = NOW(),
                        error_message = NULL
                    WHERE id = %s
                    """,
                    (log_row['id'],),
                )
                processed += 1
            except Exception as process_error:
                failed += 1
                cursor.execute(
                    """
                    UPDATE faculty_attendance_logs
                    SET processing_status = 'failed',
                        error_message = %s
                    WHERE id = %s
                    """,
                    (str(process_error)[:500], log_row['id']),
                )

        connection.commit()
        flash(
            f"Faculty reprocess complete: retried={retried}, processed={processed}, failed={failed}",
            'success' if failed == 0 else 'warning',
        )
        return redirect(url_for('attendance_admin.faculty_mobile_sync_logs'))
    except Exception as e:
        connection.rollback()
        flash(f'Failed to reprocess faculty mobile sync logs: {str(e)}', 'danger')
        return redirect(url_for('attendance_admin.faculty_mobile_sync_logs'))
    finally:
        cursor.close()
        connection.close()


def reprocess_mobile_sync_logs():
    """Reprocess pending/failed mobile logs into attendance table."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'attendance_logs'):
            flash('attendance_logs table not found. Run migration first.', 'warning')
            return redirect(url_for('attendance_admin.mobile_sync_logs'))

        limit = request.form.get('limit', 100, type=int) or 100
        limit = max(1, min(limit, 500))

        cursor.execute(
            """
            SELECT *
            FROM attendance_logs
            WHERE processing_status IN ('pending', 'failed')
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (limit,),
        )
        log_rows = cursor.fetchall() or []

        retried = 0
        processed = 0
        failed = 0

        for log_row in log_rows:
            retried += 1
            try:
                _promote_log_to_attendance(cursor, log_row)
                cursor.execute(
                    """
                    UPDATE attendance_logs
                    SET processing_status = 'processed',
                        processed_at = NOW(),
                        error_message = NULL
                    WHERE id = %s
                    """,
                    (log_row['id'],),
                )
                processed += 1
            except Exception as process_error:
                failed += 1
                cursor.execute(
                    """
                    UPDATE attendance_logs
                    SET processing_status = 'failed',
                        error_message = %s
                    WHERE id = %s
                    """,
                    (str(process_error)[:500], log_row['id']),
                )

        connection.commit()
        flash(
            f"Reprocess complete: retried={retried}, processed={processed}, failed={failed}",
            'success' if failed == 0 else 'warning',
        )
        return redirect(url_for('attendance_admin.mobile_sync_logs'))
    except Exception as e:
        connection.rollback()
        flash(f'Failed to reprocess mobile sync logs: {str(e)}', 'danger')
        return redirect(url_for('attendance_admin.mobile_sync_logs'))
    finally:
        cursor.close()
        connection.close()
