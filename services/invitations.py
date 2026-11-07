"""Registration invitation list and changes. Connections stay open."""

import secrets
from datetime import datetime, timedelta

from flask import current_app

from core.pagination import page_bounds
from data_access.invitations import (
    count_invitations,
    expire_invitation,
    fetch_invitation_stats,
    fetch_invitation_status,
    fetch_invitation_token,
    fetch_invitations,
    fetch_named_rows,
    fetch_pending_invitation,
    fetch_registered_email,
    insert_invitation,
    refresh_invitation,
)
from extensions import get_db_connection

QUERY_BASE = """
        FROM registration_invitations ri
        LEFT JOIN courses c ON ri.course_id = c.id
        LEFT JOIN departments d ON ri.department_id = d.id
        LEFT JOIN users u ON ri.created_by = u.id
    """


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def list_invitations(page, search, status_filter, per_page=15, columns=None):
    """Return the invitation page. The connection stays open."""
    connection, cursor = _cursor()
    conditions = []
    params = []
    if search:
        conditions.append("(ri.email LIKE %s OR ri.name LIKE %s OR ri.role LIKE %s OR ri.status LIKE %s OR c.name LIKE %s OR d.name LIKE %s OR ri.expires_at LIKE %s)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term, search_term, search_term, search_term, search_term])
    if status_filter == 'pending':
        conditions.append("ri.status = 'pending' AND ri.expires_at > NOW()")
    elif status_filter == 'used':
        conditions.append("ri.status = 'used'")
    elif status_filter == 'expired':
        conditions.append("(ri.status = 'expired' OR (ri.status = 'pending' AND ri.expires_at <= NOW()))")
    for key, column in (
        ('name', 'ri.name'),
        ('email', 'ri.email'),
        ('role', 'ri.role'),
        ('status', 'ri.status'),
        ('expires_at', 'ri.expires_at'),
    ):
        text = str((columns or {}).get(key) or '').replace('%', '').replace('_', '').strip()
        if not text or (key == 'status' and text.lower() in ('pending', 'used', 'expired')):
            continue
        conditions.append(column + ' LIKE %s')
        params.append('%' + text + '%')
    place = str((columns or {}).get('place') or '').replace('%', '').replace('_', '').strip()
    if place:
        conditions.append('(c.name LIKE %s OR d.name LIKE %s)')
        params.extend(['%' + place + '%', '%' + place + '%'])
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = count_invitations(cursor, QUERY_BASE, where_clause, params)
    offset, total_pages = page_bounds(page, per_page, total)
    invitations = fetch_invitations(cursor, QUERY_BASE, where_clause, params, per_page, offset)
    courses = fetch_named_rows(cursor, 'courses')
    classes = fetch_named_rows(cursor, 'classes')
    divisions = fetch_named_rows(cursor, 'divisions')
    departments = fetch_named_rows(cursor, 'departments')
    stats_row = fetch_invitation_stats(cursor)
    stats = {
        'pending': stats_row['pending'] or 0,
        'used': stats_row['used'] or 0,
        'expired': stats_row['expired'] or 0,
        'total': stats_row['total'] or 0,
    }
    cursor.close()
    return {
        'invitations': invitations,
        'courses': courses,
        'classes': classes,
        'divisions': divisions,
        'departments': departments,
        'stats': stats,
        'total': total,
        'total_pages': total_pages,
    }


def create_registration_invitation(email, name, role, days_valid, course_id, class_id, division_id, department_id, session):
    """Create an invitation. Return duplicate, registered, a token, or error. The connection stays open."""
    connection, cursor = _cursor()
    if fetch_pending_invitation(cursor, email):
        cursor.close()
        return 'duplicate'
    if fetch_registered_email(cursor, role, email):
        cursor.close()
        return 'registered'
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=days_valid)
    try:
        insert_invitation(cursor, (
            token, email, name, role, course_id, class_id, division_id, department_id,
            session['user_id'], expires_at,
        ))
        connection.commit()
        cursor.close()
        return token
    except Exception as exc:
        connection.rollback()
        current_app.logger.error(f"Error creating invitation: {str(exc)}")
        cursor.close()
        return 'error'


def revoke_registration_invitation(invitation_id):
    """Expire a pending invitation. The connection stays open."""
    connection, cursor = _cursor()
    expire_invitation(cursor, invitation_id)
    connection.commit()
    cursor.close()


def resend_registration_invitation(invitation_id):
    """Return missing, used, or a new token. The connection stays open."""
    connection, cursor = _cursor()
    invitation = fetch_invitation_status(cursor, invitation_id)
    if not invitation:
        cursor.close()
        return 'missing'
    if invitation['status'] == 'used':
        cursor.close()
        return 'used'
    new_token = secrets.token_urlsafe(32)
    new_expires_at = datetime.now() + timedelta(days=7)
    refresh_invitation(cursor, new_token, new_expires_at, invitation_id)
    connection.commit()
    cursor.close()
    return new_token


def invitation_token(invitation_id):
    """Return a token, or None. The connection stays open."""
    connection, cursor = _cursor()
    result = fetch_invitation_token(cursor, invitation_id)
    cursor.close()
    if result:
        return result['token']
    return None
