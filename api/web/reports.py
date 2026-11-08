"""One report page. Exports are queued and written by the background worker."""

import os
import time

from flask import current_app, send_file, session

from api.web.access import InputError, allowed, body, close, iso_date, optional_id, optional_text, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from extensions import get_db_connection
from security import log_activity
from services.export_jobs import enqueue_job, ensure_worker
from services.reports_admin._common import (
    ALLOWED_REPORT_TYPES,
    REPORT_LABELS,
    _get_reports_storage_dir,
)

_TYPE_PERMISSION = {
    'attendance': 'reports_view_attendance',
    'timetable': 'reports_view_timetable',
    'audit-logs': 'reports_view_audit',
    'shifts': 'reports_view_shifts',
    'proxy-log': 'reports_view_proxy',
    'invitations': 'reports_view_invitations',
}
_FIELDS = frozenset((
    'report_type', 'start_date', 'end_date', 'course_id', 'class_id', 'division_id',
    'faculty_id', 'user_id', 'entity_id', 'view', 'status', 'role', 'action',
))
_SHIFT_STATUS = frozenset(('pending', 'approved', 'rejected'))
_INVITE_ROLES = frozenset(('Super Admin', 'Admin', 'HOD', 'Teacher', 'Student'))
_VIEWS = frozenset(('class', 'faculty', 'room'))
_MESSAGES = {
    'reports_unavailable': 'The page could not be loaded.',
    'report_type_invalid': 'Choose a report.',
    'report_filters_invalid': 'Check the report filters.',
    'report_generate_failed': 'The report could not be generated.',
    'report_not_found': 'That report was not found.',
    'export_kind_invalid': 'Choose an export.',
    'export_filters_invalid': 'Check the export filters.',
    'export_unavailable': 'The export could not be queued.',
}
_EXPORT_FIELDS = frozenset((
    'kind', 'search', 'username', 'role', 'status', 'last_login',
    'q', 'action', 'ip', 'area', 'when',
    'course', 'class', 'division',
))


def register_report_routes(blueprint):
    blueprint.add_url_rule('/reports', 'reports_list', _list, methods=['GET'])
    blueprint.add_url_rule('/reports', 'reports_generate', _generate, methods=['POST'])
    blueprint.add_url_rule('/reports/<int:report_id>/download', 'reports_download', _download, methods=['GET'])
    blueprint.add_url_rule('/exports', 'exports_queue', _queue_export, methods=['POST'])


def _list():
    denied = permission_denied('reports_view', 'reports_unavailable', _MESSAGES['reports_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        ensure_worker(current_app._get_current_object())
        cursor.execute(
            """
            SELECT pr.id, pr.report_type, pr.status, pr.progress, pr.row_count, pr.file_name,
                   pr.created_at, pr.created_by AS owner_id, u.username AS created_by
            FROM processed_reports pr
            LEFT JOIN users u ON u.id = pr.created_by
            WHERE pr.status <> 'deleted'
            ORDER BY pr.created_at DESC
            LIMIT 100
            """
        )
        reports = [_job(row) for row in cursor.fetchall()]
        types = _available_types()
        try:
            options = _cached_options(cursor) if types else {}
        except Exception:
            current_app.logger.exception('Report options failed')
            options = {}
        return json_ok({
            'reports': reports,
            'types': types,
            'can_generate': bool(types),
            'options': options,
        })
    except Exception:
        current_app.logger.exception('Report list failed')
        return json_ok({'reports': [], 'types': [], 'can_generate': False, 'options': {}})
    finally:
        close(cursor, connection)


def _generate():
    denied = permission_denied('reports_export', 'reports_unavailable', _MESSAGES['reports_unavailable'])
    if denied:
        return denied
    try:
        payload = body(_FIELDS)
        report_type = payload.get('report_type')
        if report_type not in ALLOWED_REPORT_TYPES or not allowed(_TYPE_PERMISSION[report_type]):
            raise InputError('report_type_invalid')
        filters = _filters(report_type, payload)
        processed_id = enqueue_job(report_type, filters, session.get('user_id'))
        try:
            log_activity(
                session.get('user_id'),
                'reports_process',
                f'Queued {report_type} report #{processed_id}',
                entity_type='processed_report',
                entity_id=processed_id,
                new_values={'report_type': report_type, 'status': 'queued'},
            )
        except Exception:
            current_app.logger.exception('Report job was queued but the activity log failed')
        return json_ok({
            'id': safe_count(processed_id),
            'report_type': report_type,
            'label': REPORT_LABELS.get(report_type, report_type),
            'status': 'queued',
            'row_count': 0,
            'file_name': '',
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except ValueError:
        current_app.logger.exception('Report filters were rejected')
        return json_error(_MESSAGES['report_filters_invalid'], 400, 'report_filters_invalid')
    except Exception:
        current_app.logger.exception('Report generation failed')
        return json_error(_MESSAGES['report_generate_failed'], 500, 'report_generate_failed')


def _download(report_id):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, report_type, status, row_count, file_name, file_path, created_by
            FROM processed_reports
            WHERE id = %s
            """,
            (report_id,),
        )
        record = cursor.fetchone()
        storage = os.path.abspath(_get_reports_storage_dir())
        candidate = os.path.abspath(record.get('file_path') or '') if record else ''
        inside = False
        if candidate:
            try:
                inside = os.path.commonpath([storage, candidate]) == storage
            except ValueError:
                inside = False
        if not record or record.get('status') != 'completed' or not inside or not os.path.isfile(candidate):
            return json_error(_MESSAGES['report_not_found'], 404, 'report_not_found')
        denied = _download_denied(record)
        if denied:
            try:
                log_activity(
                    session.get('user_id'),
                    'reports_download_denied',
                    f"Denied download of processed report #{report_id}",
                    entity_type='processed_report',
                    entity_id=report_id,
                )
            except Exception:
                current_app.logger.exception('Denied report download could not be audited')
            return denied
        cursor.execute('UPDATE processed_reports SET downloaded_at = NOW() WHERE id = %s', (report_id,))
        log_activity(
            session.get('user_id'),
            'reports_download',
            f"Downloaded processed report #{report_id} ({record['report_type']})",
            entity_type='processed_report',
            entity_id=report_id,
            new_values={'report_type': record['report_type'], 'row_count': record['row_count'], 'file_name': record['file_name']},
            cursor=cursor,
        )
        connection.commit()
        return send_file(candidate, as_attachment=True, download_name=record['file_name'], mimetype='text/csv')
    except Exception:
        current_app.logger.exception('Report download failed')
        return json_error(_MESSAGES['report_not_found'], 404, 'report_not_found')
    finally:
        close(cursor, connection)


def _available_types():
    if not allowed('reports_export'):
        return []
    return [
        {'id': report_type, 'label': REPORT_LABELS[report_type]}
        for report_type in (
            'attendance', 'timetable', 'audit-logs', 'shifts', 'proxy-log', 'invitations',
        )
        if report_type in ALLOWED_REPORT_TYPES and allowed(_TYPE_PERMISSION[report_type])
    ]


_option_cache = {'at': 0.0, 'value': None}


def _cached_options(cursor):
    """Dropdown lists change rarely. Reuse them so job polling does not reload every table."""
    now = time.time()
    cached = _option_cache['value']
    if cached is not None and now - _option_cache['at'] < 60:
        return cached
    value = _options(cursor)
    _option_cache['at'] = now
    _option_cache['value'] = value
    return value


def _options(cursor):
    def choices(query):
        cursor.execute(query)
        return [
            {'id': safe_count(row.get('id')), 'name': safe_text(row.get('name'), 100)}
            for row in cursor.fetchall()
            if safe_count(row.get('id')) > 0
        ]

    return {
        'courses': choices('SELECT id, name FROM courses ORDER BY name'),
        'classes': choices('SELECT id, name FROM classes ORDER BY name'),
        'divisions': choices('SELECT id, name FROM divisions ORDER BY name'),
        'faculty': choices('SELECT user_id AS id, name FROM faculty ORDER BY name'),
        'rooms': choices("SELECT id, room_number AS name FROM rooms ORDER BY room_number"),
        'users': choices('SELECT id, username AS name FROM users ORDER BY username'),
    }


def _filters(report_type, payload):
    start = iso_date(payload.get('start_date'), 'report_filters_invalid', required=False)
    end = iso_date(payload.get('end_date'), 'report_filters_invalid', required=False)
    course_id = optional_id(payload.get('course_id'), 'report_filters_invalid')
    class_id = optional_id(payload.get('class_id'), 'report_filters_invalid')
    division_id = optional_id(payload.get('division_id'), 'report_filters_invalid')
    filters = {}
    if report_type == 'timetable':
        view = payload.get('view') or 'class'
        entity_id = optional_id(payload.get('entity_id'), 'report_filters_invalid')
        if view not in _VIEWS or not entity_id:
            raise InputError('report_filters_invalid')
        return {'report_type': view, 'entity_id': entity_id}
    if report_type == 'attendance':
        _copy_dates(filters, start, end)
        _copy_id(filters, 'course_id', course_id)
        _copy_id(filters, 'class_id', class_id)
        _copy_id(filters, 'division_id', division_id)
    elif report_type == 'audit-logs':
        _copy_dates(filters, start, end)
        _copy_id(filters, 'user_id', optional_id(payload.get('user_id'), 'report_filters_invalid'))
        action = optional_text(payload.get('action'), 40, 'report_filters_invalid')
        if action:
            filters['action'] = action
    elif report_type == 'shifts':
        _copy_dates(filters, start, end)
        _copy_id(filters, 'faculty_id', optional_id(payload.get('faculty_id'), 'report_filters_invalid'))
        status = optional_text(payload.get('status'), 20, 'report_filters_invalid')
        if status and status not in _SHIFT_STATUS:
            raise InputError('report_filters_invalid')
        if status:
            filters['status'] = status
    elif report_type == 'proxy-log':
        _copy_dates(filters, start, end)
    elif report_type == 'invitations':
        _copy_dates(filters, start, end)
        _copy_id(filters, 'course_id', course_id)
        _copy_id(filters, 'class_id', class_id)
        _copy_id(filters, 'division_id', division_id)
        role = optional_text(payload.get('role'), 20, 'report_filters_invalid')
        status = optional_text(payload.get('status'), 20, 'report_filters_invalid')
        if role and role not in _INVITE_ROLES:
            raise InputError('report_filters_invalid')
        if status and not status.isalpha():
            raise InputError('report_filters_invalid')
        if role:
            filters['role'] = role
        if status:
            filters['status'] = status
    return filters


def _copy_dates(filters, start, end):
    if start:
        filters['start_date'] = start
    if end:
        filters['end_date'] = end


def _copy_id(filters, key, value):
    if value:
        filters[key] = value


def _queue_export():
    try:
        payload = body(_EXPORT_FIELDS)
        kind = payload.get('kind')
        if kind == 'users':
            denied = permission_denied('users_export_data', 'export_unavailable', _MESSAGES['export_unavailable'])
            report_type = 'users-export'
            filters = _user_export_filters(payload)
        elif kind == 'audit':
            denied = _audit_export_denied()
            report_type = 'audit-export'
            filters = _audit_export_filters(payload)
        elif kind == 'timetable':
            denied = permission_denied('timetable_change', 'export_unavailable', _MESSAGES['export_unavailable'])
            report_type = 'timetable-export'
            filters = _timetable_export_filters(payload)
        else:
            raise InputError('export_kind_invalid')
        if denied:
            return denied
        job_id = enqueue_job(report_type, filters, session.get('user_id'))
        try:
            log_activity(
                session.get('user_id'),
                'reports_process',
                f'Queued {report_type} #{job_id}',
                entity_type='processed_report',
                entity_id=job_id,
                new_values={'report_type': report_type, 'status': 'queued'},
            )
        except Exception:
            current_app.logger.exception('Export job was queued but the activity log failed')
        return json_ok({
            'id': safe_count(job_id),
            'status': 'queued',
            'label': REPORT_LABELS.get(report_type, report_type),
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Export queue failed')
        return json_error(_MESSAGES['export_unavailable'], 500, 'export_unavailable')


def _audit_export_denied():
    denied = permission_denied('reports_view_audit', 'export_unavailable', _MESSAGES['export_unavailable'])
    if denied and session.get('role') != 'Super Admin':
        alternate = permission_denied('users_view_activity_log', 'export_unavailable', _MESSAGES['export_unavailable'])
        if alternate:
            return alternate
    return None


def _plain(value, limit):
    text = optional_text(value, limit, 'export_filters_invalid')
    return text.replace('%', '').replace('_', '').strip()


def _user_export_filters(payload):
    return {
        'search': _plain(payload.get('search'), 100),
        'username': _plain(payload.get('username'), 50),
        'role': _plain(payload.get('role'), 50),
        'status': _plain(payload.get('status'), 20),
        'last_login': _plain(payload.get('last_login'), 19),
    }


def _audit_export_filters(payload):
    columns = {}
    for source, key, limit in (
        ('username', 'username', 50),
        ('ip', 'ip_address', 45),
        ('area', 'entity_type', 40),
        ('status', 'status', 20),
        ('when', 'created_at', 19),
    ):
        text = _plain(payload.get(source), limit)
        if text:
            columns[key] = text
    return {
        'search': _plain(payload.get('q'), 80),
        'action': _plain(payload.get('action'), 80),
        'columns': columns or None,
    }


def _timetable_export_filters(payload):
    course_id = optional_id(payload.get('course'), 'export_filters_invalid')
    class_id = optional_id(payload.get('class'), 'export_filters_invalid')
    division_id = optional_id(payload.get('division'), 'export_filters_invalid')
    if not course_id or not class_id or not division_id:
        raise InputError('export_filters_invalid')
    return {'course_id': course_id, 'class_id': class_id, 'division_id': division_id}


def _download_denied(record):
    """Return the shared permission denial, or None when this download is allowed."""
    if _may_download(record):
        return None
    kind = record.get('report_type')
    owner = safe_count(record.get('created_by') or record.get('owner_id')) == safe_count(session.get('user_id'))
    if owner and kind == 'users-export':
        permission = 'users_export_data'
    elif owner and kind == 'audit-export':
        permission = 'reports_view_audit'
    elif owner and kind == 'timetable-export':
        permission = 'timetable_change'
    else:
        permission = 'reports_export'
    return permission_denied(permission, 'reports_unavailable', _MESSAGES['reports_unavailable'])


def _may_download(record):
    if record.get('status') != 'completed':
        return False
    if allowed('reports_export'):
        return True
    if safe_count(record.get('created_by') or record.get('owner_id')) != safe_count(session.get('user_id')):
        return False
    kind = record.get('report_type')
    if kind == 'users-export':
        return allowed('users_export_data')
    if kind == 'audit-export':
        return allowed('reports_view_audit') or allowed('users_view_activity_log')
    if kind == 'timetable-export':
        return allowed('timetable_change')
    return False


def _job(row):
    report_type = safe_text(row.get('report_type'), 40)
    progress = safe_count(row.get('progress'))
    if progress > 100:
        progress = 100
    return {
        'id': safe_count(row.get('id')),
        'report_type': report_type,
        'label': REPORT_LABELS.get(report_type, report_type),
        'status': safe_text(row.get('status'), 20),
        'progress': progress,
        'row_count': safe_count(row.get('row_count')),
        'file_name': safe_text(row.get('file_name') or '', 180),
        'created_by': safe_text(row.get('created_by') or '', 50),
        'created_at': safe_stamp(row.get('created_at')),
        'can_download': _may_download({
            'status': row.get('status'),
            'report_type': report_type,
            'owner_id': row.get('owner_id'),
        }),
    }
