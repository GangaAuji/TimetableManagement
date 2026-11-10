"""Proxy log page. This module does not read the request."""

from flask import current_app

from academic_rules.clashes import faculty_timetable_free
from core.pagination import page_bounds
from data_access.proxy_log import (
    PROXY_LOG_QUERY,
    approve_mapped_proxy,
    fetch_cover_faculty,
    fetch_named_faculty,
    fetch_proxy_clash,
    fetch_proxy_request,
    fetch_proxy_summary,
    reject_pending_proxy,
)
from extensions import get_db_connection


def load_proxy_log(page, status_filter, approval_filter, date_from, date_to, close_connection=False):
    """Return the page rows, unfiltered totals, and pagination. The connection stays open unless asked."""
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
    if close_connection:
        connection.close()
    return proxy_logs, summary_stats, pagination


def _notify(cursor, proxy_id):
    """Queue substitute notices in the approval transaction. A notice problem never blocks the decision."""
    from services import notifications

    try:
        notifications.on_proxy_assigned(cursor, proxy_id)
    except Exception:
        current_app.logger.exception('Proxy notices for proxy_log %s were not queued', proxy_id)


def _covers(cursor, row, chosen):
    people = fetch_cover_faculty(cursor, row['subject_id'], row['original_faculty_id'])
    if any(person.get('user_id') == chosen for person in people):
        return True
    if chosen != row.get('proxy_faculty_id'):
        return False
    return fetch_named_faculty(cursor, chosen) is not None


def _free(cursor, row, chosen, proxy_id):
    if not faculty_timetable_free(
        cursor, chosen, row['day_of_week'], row['start_time'], row['end_time'], active_only=False,
    ):
        return False
    return fetch_proxy_clash(
        cursor, chosen, row['absence_date'], row['start_time'], row['end_time'], proxy_id,
    ) is None


def load_proxy_choices(proxy_id):
    """Return faculty who can cover one request. The connection is closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        row = fetch_proxy_request(cursor, proxy_id)
        if not row:
            return 'missing'
        people = list(fetch_cover_faculty(cursor, row['subject_id'], row['original_faculty_id']))
        known = {person.get('user_id') for person in people}
        named = row.get('proxy_faculty_id')
        if named and named not in known:
            extra = fetch_named_faculty(cursor, named)
            if extra:
                people.append(extra)
                known.add(named)
        choices = []
        for person in people:
            user_id = person.get('user_id')
            if not user_id or user_id in {item['id'] for item in choices}:
                continue
            choices.append({
                'id': user_id,
                'name': person.get('name') or '',
                'employee_id': person.get('employee_id') or '',
                'free': _free(cursor, row, user_id, proxy_id),
            })
        return {
            'pending': (row.get('approval_status') or 'PENDING') == 'PENDING',
            'suggested_id': named if named in known else None,
            'choices': choices,
        }
    finally:
        cursor.close()
        connection.close()


def decide_proxy_request(proxy_id, decision, proxy_user_id, note, approved_by):
    """Approve a request onto one faculty member, or reject it. The connection is closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        row = fetch_proxy_request(cursor, proxy_id)
        if not row:
            return 'missing'
        if (row.get('approval_status') or '') != 'PENDING':
            return 'closed'
        if decision == 'reject':
            if not reject_pending_proxy(cursor, note, approved_by, proxy_id):
                return 'closed'
            connection.commit()
            return 'ok'
        chosen = proxy_user_id or row.get('proxy_faculty_id')
        if not chosen or chosen == row.get('original_faculty_id'):
            return 'choice'
        if not _covers(cursor, row, chosen):
            return 'choice'
        if not _free(cursor, row, chosen, proxy_id):
            return 'busy'
        if not approve_mapped_proxy(cursor, chosen, note, approved_by, proxy_id):
            return 'closed'
        _notify(cursor, proxy_id)
        connection.commit()
        return 'ok'
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
