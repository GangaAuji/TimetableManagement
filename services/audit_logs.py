"""Audit log pages. List and export leave the connection open."""

from core.pagination import page_bounds
from data_access.audit_logs import (
    count_active_sessions,
    count_failed_matches,
    count_filtered,
    count_session_matches,
    deactivate_session,
    fetch_actions,
    fetch_activity_summary,
    fetch_audit_user,
    fetch_critical_actions,
    fetch_entity_types,
    fetch_daily_activity,
    fetch_failed_logins,
    fetch_failed_page,
    fetch_hourly_activity,
    fetch_log,
    fetch_most_active_users,
    fetch_recent_activities,
    fetch_recent_sessions,
    fetch_session_page,
    fetch_stats_24h,
    fetch_user_sessions,
    fetch_usernames,
    run_query,
)
from extensions import get_db_connection

_LOG_QUERY = """
        SELECT 
            al.id, al.user_id, al.username,
            al.action,
            al.entity_type,
            al.entity_id,
            al.ip_address,
            al.user_agent,
            al.created_at,
            al.old_values,
            al.new_values,
            al.request_url,
            al.status
        FROM audit_logs al
        WHERE 1=1
    """

_EXPORT_QUERY = """
        SELECT 
            id, user_id, username, action, entity_type, entity_id,
            ip_address, request_method, status, created_at
        FROM audit_logs
        WHERE 1=1
    """


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def _append_filters(query, params, user_id, action, date_from, date_to, entity_type=None, search=None, columns=None):
    if user_id:
        query += " AND al.user_id = %s" if "al.user_id" in query else " AND user_id = %s"
        params.append(user_id)
    if action:
        query += " AND al.action LIKE %s" if "al.action" in query else " AND action LIKE %s"
        params.append(f'%{action}%')
    if entity_type:
        query += " AND entity_type = %s"
        params.append(entity_type)
    if date_from:
        query += " AND al.created_at >= %s" if "al.created_at" in query else " AND created_at >= %s"
        params.append(date_from)
    if date_to:
        query += " AND al.created_at <= %s" if "al.created_at" in query else " AND created_at <= %s"
        params.append(date_to + ' 23:59:59')
    if search:
        qualified = 'al.user_id' in query
        username = 'al.username' if qualified else 'username'
        action_column = 'al.action' if qualified else 'action'
        address = 'al.ip_address' if qualified else 'ip_address'
        area = 'al.entity_type' if qualified else 'entity_type'
        status_column = 'al.status' if qualified else 'status'
        when_column = 'al.created_at' if qualified else 'created_at'
        query += f" AND ({username} LIKE %s OR {action_column} LIKE %s OR {address} LIKE %s OR {area} LIKE %s OR {status_column} LIKE %s OR {when_column} LIKE %s)"
        like = f'%{search}%'
        params.extend([like, like, like, like, like, like])
    return _column_clause(query, params, columns)


_LOG_COLUMNS = {
    'username': ('al.username', 'username'),
    'ip_address': ('al.ip_address', 'ip_address'),
    'entity_type': ('al.entity_type', 'entity_type'),
    'status': ('al.status', 'status'),
    'created_at': ('al.created_at', 'created_at'),
}


def _column_clause(query, params, columns):
    if not columns:
        return query
    qualified = 'al.user_id' in query
    for key, pair in _LOG_COLUMNS.items():
        text = str(columns.get(key) or '').replace('%', '').replace('_', '').strip()
        if not text:
            continue
        column = pair[0] if qualified else pair[1]
        query += f" AND {column} LIKE %s"
        params.append('%' + text + '%')
    return query


def load_audit_page(user_id, action, date_from, date_to, page, per_page=50, entity_type=None, search=None, columns=None):
    """Return the audit page. The connection stays open."""
    connection, cursor = _cursor()
    query = _LOG_QUERY
    params = []
    query = _append_filters(query, params, user_id, action, date_from, date_to, entity_type, search, columns)
    total_records = count_filtered(cursor, query, params)
    offset, total_pages = page_bounds(page, per_page, total_records)
    query += " ORDER BY al.created_at DESC LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    logs = run_query(cursor, query, params)
    actions = [row['action'] for row in fetch_actions(cursor)]
    entity_types = [row['entity_type'] for row in fetch_entity_types(cursor)]
    users = fetch_usernames(cursor)
    page_data = {
        'logs': logs,
        'actions': actions,
        'entity_types': entity_types,
        'users': users,
        'total_pages': total_pages,
        'total_records': total_records,
        'stats_24h': fetch_stats_24h(cursor),
        'active_sessions_count': count_active_sessions(cursor),
        'recent_sessions': fetch_recent_sessions(cursor),
        'most_active_users': fetch_most_active_users(cursor),
        'failed_logins': fetch_failed_logins(cursor),
        'critical_actions': fetch_critical_actions(cursor),
        'hourly_activity': fetch_hourly_activity(cursor),
        'daily_activity': fetch_daily_activity(cursor),
    }
    cursor.close()
    return page_data


def load_log_detail(log_id):
    """Return one log row. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    log = fetch_log(cursor, log_id)
    cursor.close()
    connection.close()
    return log


def load_user_activity(user_id):
    """Return a user's activity. A missing user leaves the cursor and connection open."""
    connection, cursor = _cursor()
    user = fetch_audit_user(cursor, user_id)
    if not user:
        return 'missing'
    page = {
        'user': user,
        'activity_summary': fetch_activity_summary(cursor, user_id),
        'recent_activities': fetch_recent_activities(cursor, user_id),
        'active_sessions': fetch_user_sessions(cursor, user_id),
    }
    cursor.close()
    return page


def export_audit_rows(user_id, action, entity_type, date_from, date_to, search=None, columns=None):
    """Return up to 10000 export rows. The connection stays open."""
    connection, cursor = _cursor()
    query = _EXPORT_QUERY
    params = []
    query = _append_filters(query, params, user_id, action, date_from, date_to, entity_type, search, columns)
    query += " ORDER BY created_at DESC LIMIT 10000"
    logs = run_query(cursor, query, params)
    cursor.close()
    return logs


def _page_window(page, per_page, total):
    count = int(total or 0)
    total_pages = (count + per_page - 1) // per_page if count else 0
    current = page
    if total_pages and current > total_pages:
        current = total_pages
    if current < 1:
        current = 1
    offset = (current - 1) * per_page if count else 0
    return current, offset, total_pages


def load_session_page(search, page, per_page, columns=None):
    """Return one page of active sessions. The connection stays open."""
    connection, cursor = _cursor()
    total = count_session_matches(cursor, search, columns)
    current, offset, total_pages = _page_window(page, per_page, total)
    rows = fetch_session_page(cursor, search, per_page, offset, columns)
    cursor.close()
    return {'sessions': rows, 'total': total, 'total_pages': total_pages, 'page': current}


def load_failed_page(search, page, per_page, columns=None):
    """Return one page of failed logins. The connection stays open."""
    connection, cursor = _cursor()
    total = count_failed_matches(cursor, search, columns)
    current, offset, total_pages = _page_window(page, per_page, total)
    rows = fetch_failed_page(cursor, search, per_page, offset, columns)
    cursor.close()
    return {'failed_logins': rows, 'total': total, 'total_pages': total_pages, 'page': current}


def revoke_audit_session(session_id):
    """Deactivate a session. The connection stays open."""
    connection, cursor = _cursor()
    deactivate_session(cursor, session_id)
    connection.commit()
    cursor.close()
