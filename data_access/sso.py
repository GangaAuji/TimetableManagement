"""Rows of sso_settings (one row, id = 1) and sso_identities."""

SETTINGS_COLUMNS = 'id, enabled, provider, issuer, client_id, client_secret_enc, allowed_domains, link_by_email, button_label, updated_by, updated_at'


def table_exists(cursor, name='sso_settings'):
    cursor.execute(
        'SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s', (name,)
    )
    row = cursor.fetchone()
    return bool(row['n'] if isinstance(row, dict) else row[0])


def fetch_settings(cursor):
    cursor.execute(f'SELECT {SETTINGS_COLUMNS} FROM sso_settings WHERE id = 1')
    return cursor.fetchone()


def upsert_settings(cursor, values, updated_by):
    """Insert or update the single row. `values` holds only the columns to change."""
    columns = ['id', *values.keys(), 'updated_by']
    params = [1, *values.values(), updated_by]
    updates = ', '.join(f'{column} = VALUES({column})' for column in columns[1:])
    cursor.execute(
        f"INSERT INTO sso_settings ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(params))}) "
        f'ON DUPLICATE KEY UPDATE {updates}',
        params,
    )


def fetch_identity(cursor, issuer, subject):
    cursor.execute(
        'SELECT id, user_id, issuer, subject, email FROM sso_identities WHERE issuer = %s AND subject = %s', (issuer, subject)
    )
    return cursor.fetchone()


def insert_identity(cursor, *, user_id, issuer, subject, email):
    cursor.execute(
        'INSERT INTO sso_identities (user_id, issuer, subject, email, last_login_at) VALUES (%s, %s, %s, %s, NOW())',
        (user_id, issuer, subject, email),
    )
    return cursor.lastrowid


def touch_identity(cursor, identity_id, email):
    cursor.execute('UPDATE sso_identities SET last_login_at = NOW(), email = %s WHERE id = %s', (email, identity_id))


def fetch_identities(cursor):
    cursor.execute(
        'SELECT i.id, i.user_id, u.username, u.role, i.issuer, i.subject, i.email, i.created_at, i.last_login_at '
        'FROM sso_identities i JOIN users u ON u.id = i.user_id ORDER BY i.last_login_at DESC, i.id DESC LIMIT 500'
    )
    return cursor.fetchall()


def delete_identity(cursor, identity_id):
    cursor.execute('DELETE FROM sso_identities WHERE id = %s', (identity_id,))
    return cursor.rowcount


def fetch_staff_user_by_email(cursor, email):
    """An active, non-student user whose own email or faculty email matches. None unless exactly one."""
    cursor.execute(
        """
        SELECT DISTINCT u.id, u.username, u.role, u.status
        FROM users u
        LEFT JOIN faculty f ON f.user_id = u.id
        WHERE u.role <> 'Student' AND (LOWER(u.email) = %s OR LOWER(f.email) = %s)
        """,
        (email, email),
    )
    rows = cursor.fetchall()
    return rows[0] if len(rows) == 1 else None


def fetch_user(cursor, user_id):
    cursor.execute('SELECT id, username, password, role, status FROM users WHERE id = %s', (user_id,))
    return cursor.fetchone()
