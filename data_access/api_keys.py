"""Rows of api_keys: credentials for the public /api/v1. Only hashes are stored."""

COLUMNS = 'id, name, key_prefix, scopes, created_by, created_at, expires_at, last_used_at, revoked_at'


def table_exists(cursor):
    cursor.execute(
        "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'api_keys'"
    )
    row = cursor.fetchone()
    return bool(row['n'] if isinstance(row, dict) else row[0])


def fetch_keys(cursor):
    cursor.execute(f'SELECT {COLUMNS} FROM api_keys ORDER BY revoked_at IS NOT NULL, id DESC')
    return cursor.fetchall()


def fetch_key(cursor, key_id):
    cursor.execute(f'SELECT {COLUMNS} FROM api_keys WHERE id = %s', (key_id,))
    return cursor.fetchone()


def fetch_by_prefix(cursor, prefix):
    """The row to check a presented key against, including its hash."""
    cursor.execute(f'SELECT {COLUMNS}, key_hash FROM api_keys WHERE key_prefix = %s', (prefix,))
    return cursor.fetchone()


def insert_key(cursor, *, name, prefix, key_hash, scopes, created_by, expires_at):
    cursor.execute(
        'INSERT INTO api_keys (name, key_prefix, key_hash, scopes, created_by, expires_at) VALUES (%s, %s, %s, %s, %s, %s)',
        (name, prefix, key_hash, scopes, created_by, expires_at),
    )
    return cursor.lastrowid


def revoke_key(cursor, key_id):
    cursor.execute('UPDATE api_keys SET revoked_at = UTC_TIMESTAMP() WHERE id = %s AND revoked_at IS NULL', (key_id,))
    return cursor.rowcount


def touch_key(cursor, key_id):
    cursor.execute('UPDATE api_keys SET last_used_at = UTC_TIMESTAMP() WHERE id = %s', (key_id,))
