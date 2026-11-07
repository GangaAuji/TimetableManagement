"""Proxy log page. This module does not read the request."""

from core.pagination import page_bounds
from data_access.proxy_log import PROXY_LOG_QUERY, fetch_proxy_summary
from extensions import get_db_connection


def load_proxy_log(page, status_filter, approval_filter, date_from, date_to):
    """Return the page rows, unfiltered totals, and pagination. The connection stays open."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    per_page = 20
    query = PROXY_LOG_QUERY
    params = []
    if status_filter:
        query += " AND pl.status = %s"
        params.append(status_filter)
    if approval_filter:
        query += " AND pl.approval_status = %s"
        params.append(approval_filter)
    if date_from:
        query += " AND pl.absence_date >= %s"
        params.append(date_from)
    if date_to:
        query += " AND pl.absence_date <= %s"
        params.append(date_to)
    count_query = f"SELECT COUNT(*) AS total {query[query.find('FROM'):query.rfind('ORDER BY') if 'ORDER BY' in query else len(query)]}"
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()['total']
    offset, total_pages = page_bounds(page, per_page, total_count)
    query += " ORDER BY pl.absence_date DESC, t.start_time ASC"
    query += " LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    cursor.execute(query, params)
    proxy_logs = []
    for row in cursor.fetchall():
        proxy_logs.append({
            'id': row['id'],
            'absence_date': row['absence_date'],
            'status': row['status'],
            'approval_status': row['approval_status'],
            'approval_date': row['approval_date'],
            'approval_notes': row['approval_notes'],
            'original_faculty_name': row['original_faculty_name'],
            'original_employee_id': row['original_employee_id'],
            'proxy_faculty_name': row['proxy_faculty_name'],
            'proxy_employee_id': row['proxy_employee_id'],
            'day_of_week': row['day_of_week'],
            'start_time': row['start_time'],
            'end_time': row['end_time'],
            'subject_name': row['subject_name'],
            'class_name': row['class_name'],
            'division_name': row['division_name'],
            'department_name': row['department_name'],
            'approved_by_username': row['approved_by_username'],
        })
    stats = fetch_proxy_summary(cursor)
    summary_stats = {
        'total_records': stats['total_records'],
        'assigned_count': stats['assigned_count'],
        'unassigned_count': stats['unassigned_count'],
        'pending_approval': stats['pending_approval'],
        'approved_count': stats['approved_count'],
        'rejected_count': stats['rejected_count'],
    }
    cursor.close()
    has_prev = page > 1
    has_next = page < total_pages
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_num': page - 1 if has_prev else None,
        'next_num': page + 1 if has_next else None,
    }
    return proxy_logs, summary_stats, pagination
