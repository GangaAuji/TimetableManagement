"""Background export queue. The request only stores the job; a worker writes the file."""

import csv
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime

from flask import current_app

from api.web.security import safe_clock, safe_stamp, safe_text
from extensions import get_db_connection
from services.audit_logs import _EXPORT_QUERY, _append_filters
from services.job_claims import claim_next, heartbeat_clause, requeue_stale, stale_seconds
from services.reports_admin import accreditation
from services.reports_admin._common import (
    ALLOWED_REPORT_TYPES,
    REPORT_LABELS,
    _get_reports_storage_dir,
)
from services.reports_admin.dataset import _build_report_export_dataset
from services.reports_admin.renderers import EXTENSIONS, normalise_format, render

_PAGE = 2000
_KIND = re.compile(r'[^a-z0-9_-]')
_guard = threading.Lock()
_started = False


def enqueue_job(report_type, filters, user_id):
    """Store a queued export and wake the worker. Returns the new job id."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO processed_reports (
                report_type, status, filters_json, row_count, file_name, file_path, created_by, progress
            ) VALUES (%s, 'queued', %s, 0, '', '', %s, 0)
            """,
            (report_type, json.dumps(filters), user_id),
        )
        job_id = cursor.lastrowid
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
    ensure_worker(current_app._get_current_object())
    return job_id


def ensure_worker(app, force=False):
    """Start the single background worker for this process. Never under a Flask CLI command unless `force` (flask workers run)."""
    global _started
    if not force and (app.config.get('CLI_COMMAND') or not app.config.get('BACKGROUND_WORKERS', True)):
        return
    with _guard:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(app,), name='export-queue', daemon=True).start()


def run_pass(app, drain=False):
    """One pass over every tenant: requeue stale claims, then run one job (or all queued with `drain`). Returns jobs run."""
    from core.tenancy import tenant_context, tenants_to_serve

    ran = 0
    for tenant in tenants_to_serve(app):
        key = tenant.slug if tenant is not None else None
        try:
            with tenant_context(app, tenant):
                requeued = _requeue_interrupted()
                if requeued:
                    app.logger.warning('Export queue requeued %s stale job(s) for tenant %s', requeued, key or 'default')
                while True:
                    job_id = _claim_next()
                    if not job_id:
                        break
                    _process(job_id)
                    ran += 1
                    if not drain:
                        break
        except Exception:
            app.logger.exception('Export queue worker failed for tenant %s', key or 'default')
    return ran


def _loop(app):
    while True:
        try:
            worked = run_pass(app)
        except Exception:
            app.logger.exception('Export queue worker failed')
            worked = 0
        if not worked:
            time.sleep(1.5)


def _requeue_interrupted(seconds=None):
    """Requeue running exports whose worker stopped reporting. Returns how many were requeued."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        count = requeue_stale(cursor, 'processed_reports', 'progress = 0', seconds)
        connection.commit()
    finally:
        cursor.close()
        connection.close()
    if count:
        _remove_orphan_partials(stale_seconds() if seconds is None else seconds)
    return count


def _remove_orphan_partials(older_than_seconds):
    """Drop .part files nobody has written to for that long. A live worker's partial is younger."""
    directory = _get_reports_storage_dir()
    cutoff = time.time() - max(0, int(older_than_seconds))
    for name in os.listdir(directory):
        if not name.endswith('.part'):
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            current_app.logger.exception('Could not remove a partial export')


def _claim_next():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        job_id = claim_next(cursor, 'processed_reports')
        connection.commit()
        return job_id
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def _process(job_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, report_type, filters_json FROM processed_reports WHERE id = %s",
            (job_id,),
        )
        job = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()
    if not job:
        return
    filters = {}
    partial = None
    try:
        filters = json.loads(job['filters_json'] or '{}')
        if not isinstance(filters, dict):
            filters = {}
        kind = job['report_type']
        fmt = normalise_format(filters.get('format')) or 'csv'
        if kind in ('users-export', 'audit-export', 'timetable-export'):
            fmt = 'csv'  # streamed row by row; the formatted renderers need the whole dataset
        _name, final, partial = _paths(kind, fmt)
        if kind == 'users-export':
            count = _export_users(job_id, filters, partial)
        elif kind == 'audit-export':
            count = _export_audit(job_id, filters, partial)
        elif kind == 'timetable-export':
            count = _export_timetable(job_id, filters, partial)
        elif kind in ALLOWED_REPORT_TYPES:
            count = _export_report(job_id, kind, filters, partial, fmt)
        else:
            raise ValueError('unknown export')
        os.replace(partial, final)
        _complete(job_id, count, _name, final)
    except Exception:
        current_app.logger.exception('Export job %s failed', job_id)
        _fail(job_id, partial)


def _paths(kind, fmt='csv'):
    safe_kind = _KIND.sub('', str(kind))[:40] or 'export'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f'{safe_kind}_{stamp}_{uuid.uuid4().hex[:8]}{EXTENSIONS.get(fmt, ".csv")}'
    directory = _get_reports_storage_dir()
    final = os.path.join(directory, name)
    return name, final, final + '.part'


def _progress(job_id, value):
    progress = max(1, min(99, int(value)))
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            f"UPDATE processed_reports SET progress = %s, {heartbeat_clause()} WHERE id = %s AND status = 'running'",
            (progress, job_id),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def _complete(job_id, row_count, file_name, file_path):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE processed_reports
            SET status = 'completed', progress = 100, row_count = %s, file_name = %s, file_path = %s
            WHERE id = %s AND status = 'running'
            """,
            (row_count, file_name, file_path, job_id),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def _fail(job_id, partial):
    if partial and os.path.isfile(partial):
        try:
            os.remove(partial)
        except OSError:
            current_app.logger.exception('Could not remove a partial export')
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE processed_reports
            SET status = 'failed', progress = 0, row_count = 0, file_name = '', file_path = ''
            WHERE id = %s AND status = 'running'
            """,
            (job_id,),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def _user_clause(filters):
    where = ['u.role NOT IN (%s, %s)']
    params = ['Teacher', 'Student']
    role = filters.get('role') or ''
    status = filters.get('status') or ''
    search = filters.get('search') or ''
    username = filters.get('username') or ''
    last_login = filters.get('last_login') or ''
    if role:
        where.append('u.role LIKE %s')
        params.append('%' + role + '%')
    if status:
        where.append('u.status LIKE %s')
        params.append('%' + status + '%')
    if search:
        where.append('(u.username LIKE %s OR u.role LIKE %s OR u.status LIKE %s OR CAST(u.last_login AS CHAR) LIKE %s)')
        like = '%' + search + '%'
        params.extend([like, like, like, like])
    if username:
        where.append('u.username LIKE %s')
        params.append('%' + username + '%')
    if last_login:
        where.append('CAST(u.last_login AS CHAR) LIKE %s')
        params.append('%' + last_login + '%')
    return ' WHERE ' + ' AND '.join(where), params


def _export_users(job_id, filters, partial):
    clause, params = _user_clause(filters)
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(f'SELECT COUNT(u.id) AS n FROM users u{clause}', tuple(params))
        total = int(cursor.fetchone()['n'] or 0)
        written = 0
        last_id = 0
        with open(partial, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(['ID', 'Username', 'Role', 'Status', 'Last login'])
            while True:
                cursor.execute(
                    f"""
                    SELECT u.id, u.username, u.role, u.status, u.last_login
                    FROM users u
                    {clause} AND u.id > %s
                    ORDER BY u.id ASC
                    LIMIT %s
                    """,
                    tuple(params) + (last_id, _PAGE),
                )
                rows = cursor.fetchall()
                if not rows:
                    break
                for row in rows:
                    writer.writerow([
                        row.get('id') or '',
                        safe_text(row.get('username'), 50),
                        safe_text(row.get('role'), 50),
                        safe_text(row.get('status') or 'active', 20),
                        safe_stamp(row.get('last_login')),
                    ])
                last_id = rows[-1]['id']
                written += len(rows)
                _progress(job_id, 100 if total == 0 else written * 100 / total)
                if len(rows) < _PAGE:
                    break
        return written
    finally:
        cursor.close()
        connection.close()


def _audit_query(base, filters):
    params = []
    columns = filters.get('columns') if isinstance(filters.get('columns'), dict) else None
    query = _append_filters(
        base,
        params,
        filters.get('user_id'),
        filters.get('action') or '',
        filters.get('date_from') or '',
        filters.get('date_to') or '',
        filters.get('entity_type') or None,
        filters.get('search') or None,
        columns,
    )
    return query, params


def _export_audit(job_id, filters, partial):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        count_sql, count_params = _audit_query('SELECT COUNT(*) AS n FROM audit_logs WHERE 1=1', filters)
        cursor.execute(count_sql, count_params)
        total = int(cursor.fetchone()['n'] or 0)
        written = 0
        last_id = None
        with open(partial, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(['ID', 'User ID', 'Username', 'Action', 'Entity Type', 'Entity ID', 'IP Address', 'Method', 'Status', 'Timestamp'])
            while True:
                page_sql, page_params = _audit_query(_EXPORT_QUERY, filters)
                if last_id is not None:
                    page_sql += ' AND id < %s'
                    page_params.append(last_id)
                page_sql += ' ORDER BY id DESC LIMIT %s'
                page_params.append(_PAGE)
                cursor.execute(page_sql, page_params)
                rows = cursor.fetchall()
                if not rows:
                    break
                for row in rows:
                    writer.writerow([
                        row.get('id') or '',
                        row.get('user_id') or '',
                        safe_text(row.get('username') or '', 50),
                        safe_text(row.get('action') or '', 80),
                        safe_text(row.get('entity_type') or '', 40),
                        row.get('entity_id') or '',
                        safe_text(row.get('ip_address') or '', 45),
                        safe_text(row.get('request_method') or '', 10),
                        safe_text(row.get('status') or '', 20),
                        safe_stamp(row.get('created_at')),
                    ])
                last_id = rows[-1]['id']
                written += len(rows)
                _progress(job_id, 100 if total == 0 else written * 100 / total)
                if len(rows) < _PAGE:
                    break
        return written
    finally:
        cursor.close()
        connection.close()


def _export_timetable(job_id, filters, partial):
    _progress(job_id, 20)
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name,
                   COALESCE(f.name, '') AS faculty_name, r.room_number
            FROM timetable t
            JOIN subjects s ON s.id = t.subject_id
            LEFT JOIN faculty f ON f.user_id = t.faculty_id
            LEFT JOIN rooms r ON r.id = t.room_id
            WHERE t.course_id = %s AND t.class_id = %s AND t.division_id = %s
              AND COALESCE(t.is_active, 1) = 1
            ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
            """,
            (filters.get('course_id'), filters.get('class_id'), filters.get('division_id')),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()
    _progress(job_id, 70)
    with open(partial, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Day', 'Start', 'End', 'Subject', 'Faculty', 'Room'])
        for row in rows:
            writer.writerow([
                safe_text(row.get('day_of_week'), 12),
                safe_clock(row.get('start_time')),
                safe_clock(row.get('end_time')),
                safe_text(row.get('subject_name'), 100),
                safe_text(row.get('faculty_name') or '', 100),
                safe_text(row.get('room_number') or '', 20),
            ])
    return len(rows)


def _export_report(job_id, report_type, filters, partial, fmt='csv'):
    _progress(job_id, 10)
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    labels, meta = {}, {}
    try:
        if report_type in accreditation.ACCREDITATION_TYPES:
            rows, fieldnames, labels, meta = accreditation.build(cursor, report_type, filters)
        else:
            rows, fieldnames = _build_report_export_dataset(cursor, report_type, filters)
            meta = {key: value for key, value in filters.items() if key != 'format' and value not in (None, '')}
    finally:
        cursor.close()
        connection.close()
    _progress(job_id, 80)
    title = REPORT_LABELS.get(report_type, report_type)
    return render(partial, fmt, fieldnames, rows, title=title, meta=meta, labels=labels)
