"""Audit logs. List, detail, export, and session revoke use the existing audit service."""

import csv
import io
import json
import re
from datetime import datetime, timedelta

from flask import current_app, make_response, request, session

from api.web.access import InputError, optional_id, page_window, permission_denied
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_stamp, safe_text
from services.audit_logs import export_audit_rows, load_audit_page, load_failed_page, load_log_detail, load_session_page, load_user_activity, revoke_audit_session

_MESSAGES = {
    'audit_unavailable': 'The page could not be loaded.',
    'audit_not_found': 'That audit record was not found.',
    'audit_session_invalid': 'That session could not be revoked.',
}
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_SESSION = re.compile(r'^[A-Za-z0-9._:-]{8,128}$')
_SECRET = re.compile(r'password|token|secret|cookie', re.I)


def register_audit_routes(blueprint):
    blueprint.add_url_rule('/audit', 'audit_list', _list, methods=['GET'])
    blueprint.add_url_rule('/audit/export', 'audit_export', _export, methods=['GET'])
    blueprint.add_url_rule('/audit/sessions', 'audit_sessions', _sessions, methods=['GET'])
    blueprint.add_url_rule('/audit/sessions/revoke', 'audit_revoke_session', _revoke, methods=['POST'])
    blueprint.add_url_rule('/audit/failed-logins', 'audit_failed_logins', _failed, methods=['GET'])
    blueprint.add_url_rule('/audit/users/<int:user_id>', 'audit_user', _user, methods=['GET'])
    blueprint.add_url_rule('/audit/<int:log_id>', 'audit_detail', _detail, methods=['GET'])


def _denied():
    denied = permission_denied('reports_view_audit', 'audit_unavailable', _MESSAGES['audit_unavailable'])
    if denied and session.get('role') != 'Super Admin':
        alternate = permission_denied('users_view_activity_log', 'audit_unavailable', _MESSAGES['audit_unavailable'])
        if alternate:
            return alternate
    return None


def _search():
    text = safe_text(request.args.get('q') or '', 80)
    return text.replace('%', '').replace('_', '').strip()


def _named_columns(spec):
    columns = {}
    for arg, key, limit in spec:
        text = safe_text(request.args.get(arg) or '', limit).replace('%', '').replace('_', '').strip()
        if text:
            columns[key] = text
    return columns or None


def _date(value):
    text = safe_text(value or '', 10)
    return text if _DATE.match(text) else ''


def _filters():
    user_raw = request.args.get('user_id') or ''
    user_id = None
    if str(user_raw).isdigit():
        try:
            user_id = optional_id(int(user_raw), 'audit_unavailable')
        except InputError:
            user_id = None
    page, per_page = page_window()
    return {
        'user_id': user_id,
        'action': safe_text(request.args.get('action') or '', 80),
        'entity_type': safe_text(request.args.get('entity_type') or '', 40),
        'date_from': _date(request.args.get('date_from')),
        'date_to': _date(request.args.get('date_to')),
        'page': page,
        'per_page': per_page,
        'search': _search(),
        'columns': _named_columns((
            ('username', 'username', 50),
            ('ip', 'ip_address', 45),
            ('area', 'entity_type', 40),
            ('status', 'status', 20),
            ('when', 'created_at', 19),
        )),
    }


def _series(hourly, daily):
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    hours = {}
    for row in hourly or []:
        hours[safe_text(row.get('bucket'), 13)] = {
            'activities': safe_count(row.get('total')),
            'failed': safe_count(row.get('failed')),
            'people': safe_count(row.get('people')),
        }
    activity = []
    failed = []
    people = []
    for offset in range(23, -1, -1):
        stamp = now - timedelta(hours=offset)
        item = hours.get(stamp.strftime('%Y-%m-%d %H'), {})
        activity.append(safe_count(item.get('activities')))
        failed.append(safe_count(item.get('failed')))
        people.append(safe_count(item.get('people')))
    today = datetime.now().date()
    counts = {}
    for row in daily or []:
        day = row.get('day')
        key = day.isoformat() if hasattr(day, 'isoformat') else safe_text(day, 10)
        counts[key[:10]] = safe_count(row.get('total'))
    days = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        days.append({'label': day.strftime('%a')[:1], 'total': counts.get(day.isoformat(), 0)})
    return {'activities': activity, 'failed': failed, 'people': people, 'days': days}


def _log_row(row):
    return {
        'id': safe_count(row.get('id')),
        'user_id': safe_count(row.get('user_id')),
        'username': safe_text(row.get('username') or '', 50),
        'action': safe_text(row.get('action') or '', 80),
        'entity_type': safe_text(row.get('entity_type') or '', 40),
        'entity_id': safe_count(row.get('entity_id')),
        'ip_address': safe_text(row.get('ip_address') or '', 45),
        'status': safe_text(row.get('status') or '', 20),
        'created_at': safe_stamp(row.get('created_at')),
    }


def _values(raw):
    if not raw:
        return {}
    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {'text': safe_text(raw, 500)}
    if not isinstance(parsed, dict):
        return {'text': safe_text(parsed, 500)}
    cleaned = {}
    for key, value in list(parsed.items())[:40]:
        name = safe_text(key, 40)
        if not name:
            continue
        cleaned[name] = '' if _SECRET.search(name) else safe_text(value, 200)
    return cleaned


def _list():
    denied = _denied()
    if denied:
        return denied
    try:
        filters = _filters()
        page_data = load_audit_page(
            filters['user_id'], filters['action'], filters['date_from'], filters['date_to'],
            filters['page'], filters['per_page'], filters['entity_type'] or None, filters['search'] or None,
            filters['columns'],
        )
        stats = page_data.get('stats_24h') or {}
        return json_ok({
            'logs': [_log_row(row) for row in page_data['logs'] if safe_count(row.get('id')) > 0],
            'actions': [safe_text(item, 80) for item in page_data['actions'] if safe_text(item, 80)],
            'entity_types': [safe_text(item, 40) for item in page_data['entity_types'] if safe_text(item, 40)],
            'users': [
                {'id': safe_count(row.get('id')), 'username': safe_text(row.get('username'), 50)}
                for row in page_data['users']
                if safe_count(row.get('id')) > 0 and safe_text(row.get('username'), 50)
            ],
            'page': filters['page'],
            'per_page': filters['per_page'],
            'total_pages': max(safe_count(page_data['total_pages']), 1),
            'total': safe_count(page_data['total_records']),
            'stats': {
                'activities': safe_count(stats.get('total_activities')),
                'active_users': safe_count(stats.get('active_users')),
                'failed': safe_count(stats.get('failed_activities')),
                'sessions': safe_count(page_data.get('active_sessions_count')),
            },
            'sessions': [
                {
                    'session_id': safe_text(row.get('session_id'), 128),
                    'username': safe_text(row.get('username') or '', 50),
                    'ip_address': safe_text(row.get('ip_address') or '', 45),
                    'last_activity': safe_stamp(row.get('last_activity')),
                }
                for row in page_data['recent_sessions']
                if _SESSION.match(safe_text(row.get('session_id'), 128))
            ],
            'active_users': [
                {'username': safe_text(row.get('username') or '', 50), 'count': safe_count(row.get('activity_count'))}
                for row in page_data['most_active_users']
                if safe_text(row.get('username') or '', 50)
            ],
            'failed_logins': [
                {
                    'username': safe_text(row.get('username') or '', 50),
                    'reason': safe_text(row.get('failure_reason') or '', 80),
                    'attempted_at': safe_stamp(row.get('attempted_at')),
                }
                for row in page_data['failed_logins']
            ],
            'critical': [_log_row(row) for row in page_data['critical_actions'] if safe_count(row.get('id')) > 0],
            'series': _series(page_data.get('hourly_activity'), page_data.get('daily_activity')),
        })
    except Exception:
        current_app.logger.exception('Audit list failed')
        return json_error(_MESSAGES['audit_unavailable'], 500, 'audit_unavailable')


def _detail(log_id):
    denied = _denied()
    if denied:
        return denied
    try:
        log = load_log_detail(log_id)
        if not log:
            return json_error(_MESSAGES['audit_not_found'], 404, 'audit_not_found')
        row = _log_row(log)
        row['request_url'] = safe_text(log.get('request_url') or '', 180)
        row['old_values'] = _values(log.get('old_values'))
        row['new_values'] = _values(log.get('new_values'))
        return json_ok({'log': row})
    except Exception:
        current_app.logger.exception('Audit detail failed')
        return json_error(_MESSAGES['audit_unavailable'], 500, 'audit_unavailable')


def _user(user_id):
    denied = _denied()
    if denied:
        return denied
    try:
        page_data = load_user_activity(user_id)
        if page_data == 'missing':
            return json_error(_MESSAGES['audit_not_found'], 404, 'audit_not_found')
        user = page_data['user'] or {}
        return json_ok({
            'user': {
                'id': safe_count(user.get('id')),
                'username': safe_text(user.get('username'), 50),
                'role': safe_text(user.get('role'), 50),
            },
            'summary': [
                {
                    'action': safe_text(row.get('action'), 80),
                    'count': safe_count(row.get('count')),
                    'last_activity': safe_stamp(row.get('last_activity')),
                }
                for row in page_data['activity_summary']
                if safe_text(row.get('action'), 80)
            ],
            'recent': [_log_row(row) for row in page_data['recent_activities'] if safe_count(row.get('id')) > 0],
            'sessions': [
                {
                    'session_id': safe_text(row.get('session_id'), 128),
                    'ip_address': safe_text(row.get('ip_address') or '', 45),
                    'last_activity': safe_stamp(row.get('last_activity')),
                }
                for row in page_data['active_sessions']
                if _SESSION.match(safe_text(row.get('session_id'), 128))
            ],
        })
    except Exception:
        current_app.logger.exception('Audit user activity failed')
        return json_error(_MESSAGES['audit_unavailable'], 500, 'audit_unavailable')


def _export():
    denied = _denied()
    if denied:
        return denied
    try:
        filters = _filters()
        logs = export_audit_rows(
            filters['user_id'], filters['action'], filters['entity_type'], filters['date_from'], filters['date_to'],
            filters['search'] or None, filters['columns'],
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'User ID', 'Username', 'Action', 'Entity Type', 'Entity ID', 'IP Address', 'Method', 'Status', 'Timestamp'])
        for log in logs:
            writer.writerow([
                safe_count(log.get('id')),
                safe_count(log.get('user_id')),
                safe_text(log.get('username') or '', 50),
                safe_text(log.get('action') or '', 80),
                safe_text(log.get('entity_type') or '', 40),
                safe_count(log.get('entity_id')),
                safe_text(log.get('ip_address') or '', 45),
                safe_text(log.get('request_method') or '', 10),
                safe_text(log.get('status') or '', 20),
                safe_stamp(log.get('created_at')),
            ])
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=audit_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
    except Exception:
        current_app.logger.exception('Audit export failed')
        return json_error(_MESSAGES['audit_unavailable'], 500, 'audit_unavailable')


def _panel_page():
    page, per_page = page_window(100000)
    search = safe_text(request.args.get('q') or '', 50).replace('%', '').replace('_', '').strip()
    return page, per_page, search or None


def _sessions():
    denied = _denied()
    if denied:
        return denied
    try:
        page, per_page, search = _panel_page()
        columns = _named_columns((
            ('username', 'username', 50),
            ('ip', 'ip_address', 45),
            ('when', 'last_activity', 19),
        ))
        page_data = load_session_page(search, page, per_page, columns)
        return json_ok({
            'sessions': [
                {
                    'session_id': safe_text(row.get('session_id'), 128),
                    'username': safe_text(row.get('username') or '', 50),
                    'ip_address': safe_text(row.get('ip_address') or '', 45),
                    'last_activity': safe_stamp(row.get('last_activity')),
                }
                for row in page_data['sessions']
                if _SESSION.match(safe_text(row.get('session_id'), 128))
            ],
            'page': safe_count(page_data['page']),
            'per_page': per_page,
            'total': safe_count(page_data['total']),
            'total_pages': max(safe_count(page_data['total_pages']), 1),
        })
    except Exception:
        current_app.logger.exception('Audit session list failed')
        return json_error(_MESSAGES['audit_unavailable'], 500, 'audit_unavailable')


def _failed():
    denied = _denied()
    if denied:
        return denied
    try:
        page, per_page, search = _panel_page()
        columns = _named_columns((
            ('username', 'username', 50),
            ('reason', 'reason', 80),
            ('when', 'attempted_at', 19),
        ))
        page_data = load_failed_page(search, page, per_page, columns)
        return json_ok({
            'failed_logins': [
                {
                    'username': safe_text(row.get('username') or '', 50),
                    'reason': safe_text(row.get('failure_reason') or '', 80),
                    'attempted_at': safe_stamp(row.get('attempted_at')),
                }
                for row in page_data['failed_logins']
            ],
            'page': safe_count(page_data['page']),
            'per_page': per_page,
            'total': safe_count(page_data['total']),
            'total_pages': max(safe_count(page_data['total_pages']), 1),
        })
    except Exception:
        current_app.logger.exception('Audit failed login list failed')
        return json_error(_MESSAGES['audit_unavailable'], 500, 'audit_unavailable')


def _revoke():
    denied = _denied()
    if denied:
        return denied
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) - {'session_id'}:
            return json_error(_MESSAGES['audit_session_invalid'], 400, 'audit_session_invalid')
        session_id = safe_text(payload.get('session_id'), 128)
        if not _SESSION.match(session_id):
            return json_error(_MESSAGES['audit_session_invalid'], 400, 'audit_session_invalid')
        revoke_audit_session(session_id)
        return json_ok({'revoked': True})
    except Exception:
        current_app.logger.exception('Audit session revoke failed')
        return json_error(_MESSAGES['audit_unavailable'], 500, 'audit_unavailable')
