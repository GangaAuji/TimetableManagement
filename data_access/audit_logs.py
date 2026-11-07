"""Audit log SQL. Callers pass a cursor and their own parameter list."""


def run_query(cursor, query, params):
    """Run one assembled audit query and return every row."""
    cursor.execute(query, params)
    return cursor.fetchall()


def count_filtered(cursor, query, params):
    """Count rows in an assembled audit query."""
    cursor.execute(f"SELECT COUNT(*) as total FROM ({query}) as filtered", params)
    return cursor.fetchone()['total']


def fetch_actions(cursor):
    """Return distinct audit actions."""
    cursor.execute("SELECT DISTINCT action FROM audit_logs WHERE action IS NOT NULL ORDER BY action")
    return cursor.fetchall()


def fetch_entity_types(cursor):
    """Return distinct audit entity types."""
    cursor.execute("SELECT DISTINCT entity_type FROM audit_logs WHERE entity_type IS NOT NULL ORDER BY entity_type")
    return cursor.fetchall()


def fetch_usernames(cursor):
    """Return users for the audit filter."""
    cursor.execute("SELECT id, username FROM users ORDER BY username")
    return cursor.fetchall()


def fetch_stats_24h(cursor):
    """Return activity counts for the last 24 hours."""
    cursor.execute(
        """
        SELECT 
            COUNT(*) as total_activities,
            COUNT(DISTINCT user_id) as active_users,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_activities
        FROM audit_logs
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """
    )
    return cursor.fetchone()


def count_active_sessions(cursor):
    """Return the active session count."""
    cursor.execute(
        "SELECT COUNT(*) as count FROM user_sessions WHERE is_active = 1 AND (expires_at IS NULL OR expires_at > NOW())"
    )
    return cursor.fetchone()['count']


def _panel_clause(search, columns, search_sql, search_slots, column_sql):
    clauses = []
    params = []
    if search:
        clauses.append(search_sql)
        like = '%' + search + '%'
        params.extend([like] * search_slots)
    for key, column in column_sql.items():
        text = str((columns or {}).get(key) or '').replace('%', '').replace('_', '').strip()
        if text:
            clauses.append(column + ' LIKE %s')
            params.append('%' + text + '%')
    extra = (' AND ' + ' AND '.join(clauses)) if clauses else ''
    return extra, params


_SESSION_COLUMNS = {
    'username': 'u.username',
    'ip_address': 's.ip_address',
    'last_activity': 's.last_activity',
}
_FAILED_COLUMNS = {
    'username': 'username',
    'reason': 'failure_reason',
    'attempted_at': 'attempted_at',
}


def count_session_matches(cursor, search, columns=None):
    """Count active sessions, optionally matching a username or address."""
    extra, params = _panel_clause(
        search, columns,
        '(u.username LIKE %s OR s.ip_address LIKE %s OR s.last_activity LIKE %s)', 3, _SESSION_COLUMNS,
    )
    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM user_sessions s
        LEFT JOIN users u ON s.user_id = u.id
        WHERE s.is_active = 1 AND (s.expires_at IS NULL OR s.expires_at > NOW())
        """ + extra,
        params,
    )
    return cursor.fetchone()['count']


def fetch_session_page(cursor, search, limit, offset, columns=None):
    """Return one page of active sessions, newest activity first."""
    extra, params = _panel_clause(
        search, columns,
        '(u.username LIKE %s OR s.ip_address LIKE %s OR s.last_activity LIKE %s)', 3, _SESSION_COLUMNS,
    )
    params.extend([limit, offset])
    cursor.execute(
        """
        SELECT s.session_id, u.username, s.ip_address, s.last_activity
        FROM user_sessions s
        LEFT JOIN users u ON s.user_id = u.id
        WHERE s.is_active = 1 AND (s.expires_at IS NULL OR s.expires_at > NOW())
        """ + extra + " ORDER BY s.last_activity DESC LIMIT %s OFFSET %s",
        params,
    )
    return cursor.fetchall()


def count_failed_matches(cursor, search, columns=None):
    """Count failed login attempts, optionally matching a name, address, or reason."""
    extra, params = _panel_clause(
        search, columns,
        '(username LIKE %s OR ip_address LIKE %s OR failure_reason LIKE %s OR attempted_at LIKE %s)', 4, _FAILED_COLUMNS,
    )
    cursor.execute(
        "SELECT COUNT(*) as count FROM login_attempts WHERE status = 'failed'" + extra,
        params,
    )
    return cursor.fetchone()['count']


def fetch_failed_page(cursor, search, limit, offset, columns=None):
    """Return one page of failed login attempts."""
    extra, params = _panel_clause(
        search, columns,
        '(username LIKE %s OR ip_address LIKE %s OR failure_reason LIKE %s OR attempted_at LIKE %s)', 4, _FAILED_COLUMNS,
    )
    params.extend([limit, offset])
    cursor.execute(
        """
        SELECT username, failure_reason, attempted_at
        FROM login_attempts
        WHERE status = 'failed'
        """ + extra + " ORDER BY attempted_at DESC LIMIT %s OFFSET %s",
        params,
    )
    return cursor.fetchall()


def fetch_recent_sessions(cursor):
    """Return the ten most recent active sessions."""
    cursor.execute(
        """
        SELECT s.session_id, s.user_id, u.username, s.ip_address, 
               s.last_activity, s.created_at
        FROM user_sessions s
        LEFT JOIN users u ON s.user_id = u.id
        WHERE s.is_active = 1 AND (s.expires_at IS NULL OR s.expires_at > NOW())
        ORDER BY s.last_activity DESC
        LIMIT 10
        """
    )
    return cursor.fetchall()


def fetch_most_active_users(cursor):
    """Return the most active users from the last 7 days."""
    cursor.execute(
        """
        SELECT user_id, username, COUNT(*) as activity_count
        FROM audit_logs
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY user_id, username
        ORDER BY activity_count DESC
        LIMIT 10
        """
    )
    return cursor.fetchall()


def fetch_failed_logins(cursor):
    """Return recent failed login attempts."""
    cursor.execute(
        """
        SELECT username, ip_address, failure_reason, attempted_at
        FROM login_attempts
        WHERE status = 'failed'
        ORDER BY attempted_at DESC
        LIMIT 20
        """
    )
    return cursor.fetchall()


def fetch_hourly_activity(cursor):
    """Return hourly audit counts for the last 24 hours."""
    cursor.execute(
        """
        SELECT DATE_FORMAT(created_at, %s) AS bucket,
               COUNT(*) AS total,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
               COUNT(DISTINCT user_id) AS people
        FROM audit_logs
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        GROUP BY bucket
        ORDER BY bucket
        """,
        ('%Y-%m-%d %H',),
    )
    return cursor.fetchall()


def fetch_daily_activity(cursor):
    """Return daily audit counts for the last 7 days."""
    cursor.execute(
        """
        SELECT DATE(created_at) AS day, COUNT(*) AS total
        FROM audit_logs
        WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
        GROUP BY DATE(created_at)
        ORDER BY day
        """
    )
    return cursor.fetchall()


def fetch_critical_actions(cursor):
    """Return recent critical audit actions."""
    cursor.execute(
        """
        SELECT id, user_id, username, action, entity_type, entity_id, created_at
        FROM audit_logs
        WHERE action IN ('delete_user', 'bulk_delete_users', 'delete_role', 
                         'revoke_permission', 'reset_password', 'bulk_reset_password',
                         'toggle_status', 'account_locked', 'edit_role', 'grant_permission')
           OR action LIKE '%delete%'
           OR action LIKE '%remove%'
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    return cursor.fetchall()


def fetch_log(cursor, log_id):
    """Return one audit log row."""
    cursor.execute(
        """
        SELECT * FROM audit_logs WHERE id = %s
        """,
        (log_id,)
    )
    return cursor.fetchone()


def fetch_audit_user(cursor, user_id):
    """Return one user for the activity page."""
    cursor.execute("SELECT id, username, email, role FROM users WHERE id = %s", (user_id,))
    return cursor.fetchone()


def fetch_activity_summary(cursor, user_id):
    """Return 30-day activity counts for one user."""
    cursor.execute(
        """
        SELECT 
            action,
            COUNT(*) as count,
            MAX(created_at) as last_activity
        FROM audit_logs
        WHERE user_id = %s 
          AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        GROUP BY action
        ORDER BY count DESC
        """,
        (user_id,)
    )
    return cursor.fetchall()


def fetch_recent_activities(cursor, user_id):
    """Return the latest 50 activities for one user."""
    cursor.execute(
        """
        SELECT id, action, entity_type, entity_id, status, created_at
        FROM audit_logs
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 50
        """,
        (user_id,)
    )
    return cursor.fetchall()


def fetch_user_sessions(cursor, user_id):
    """Return active sessions for one user."""
    cursor.execute(
        """
        SELECT session_id, ip_address, user_agent, last_activity, created_at, expires_at
        FROM user_sessions
        WHERE user_id = %s AND is_active = 1
        ORDER BY last_activity DESC
        """,
        (user_id,)
    )
    return cursor.fetchall()


def deactivate_session(cursor, session_id):
    """Mark one user session inactive."""
    cursor.execute(
        "UPDATE user_sessions SET is_active = 0 WHERE session_id = %s",
        (session_id,)
    )
