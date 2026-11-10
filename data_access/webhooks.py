"""Rows of webhook_endpoints and webhook_deliveries."""

ENDPOINT_COLUMNS = 'id, name, url, events, is_active, created_by, created_at, last_delivery_at, last_status'


def table_exists(cursor, name='webhook_endpoints'):
    cursor.execute(
        'SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s', (name,)
    )
    row = cursor.fetchone()
    return bool(row['n'] if isinstance(row, dict) else row[0])


def fetch_endpoints(cursor, active_only=False):
    where = 'WHERE is_active = 1' if active_only else ''
    cursor.execute(f'SELECT {ENDPOINT_COLUMNS} FROM webhook_endpoints {where} ORDER BY id')
    return cursor.fetchall()


def fetch_endpoint(cursor, endpoint_id, with_secret=False):
    extra = ', secret_enc' if with_secret else ''
    cursor.execute(f'SELECT {ENDPOINT_COLUMNS}{extra} FROM webhook_endpoints WHERE id = %s', (endpoint_id,))
    return cursor.fetchone()


def insert_endpoint(cursor, *, name, url, secret_enc, events, created_by):
    cursor.execute(
        'INSERT INTO webhook_endpoints (name, url, secret_enc, events, created_by) VALUES (%s, %s, %s, %s, %s)',
        (name, url, secret_enc, events, created_by),
    )
    return cursor.lastrowid


def update_endpoint(cursor, endpoint_id, *, name, url, events, is_active, secret_enc=None):
    sets = ['name = %s', 'url = %s', 'events = %s', 'is_active = %s']
    params = [name, url, events, 1 if is_active else 0]
    if secret_enc is not None:
        sets.append('secret_enc = %s')
        params.append(secret_enc)
    params.append(endpoint_id)
    cursor.execute(f"UPDATE webhook_endpoints SET {', '.join(sets)} WHERE id = %s", params)
    return cursor.rowcount


def delete_endpoint(cursor, endpoint_id):
    cursor.execute('DELETE FROM webhook_endpoints WHERE id = %s', (endpoint_id,))
    return cursor.rowcount


def insert_delivery(cursor, *, endpoint_id, event, delivery_key, payload_json):
    cursor.execute(
        'INSERT INTO webhook_deliveries (endpoint_id, event, delivery_key, payload_json, available_at) '
        'VALUES (%s, %s, %s, %s, UTC_TIMESTAMP())',
        (endpoint_id, event, delivery_key, payload_json),
    )
    return cursor.lastrowid


def fetch_delivery(cursor, delivery_id):
    cursor.execute(
        'SELECT d.*, e.url, e.secret_enc, e.is_active FROM webhook_deliveries d JOIN webhook_endpoints e ON e.id = d.endpoint_id WHERE d.id = %s',
        (delivery_id,),
    )
    return cursor.fetchone()


def recent_deliveries(cursor, *, endpoint_id=None, limit=100):
    clauses, params = [], []
    if endpoint_id is not None:
        clauses.append('d.endpoint_id = %s')
        params.append(endpoint_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    cursor.execute(
        f'SELECT d.id, d.endpoint_id, e.name AS endpoint_name, d.event, d.delivery_key, d.status, d.attempts, d.response_status, '
        f'd.last_error, d.created_at, d.sent_at FROM webhook_deliveries d JOIN webhook_endpoints e ON e.id = d.endpoint_id '
        f'{where} ORDER BY d.id DESC LIMIT %s',
        (*params, int(limit)),
    )
    return cursor.fetchall()


def queue_counts(cursor):
    cursor.execute('SELECT status, COUNT(*) AS n FROM webhook_deliveries GROUP BY status')
    return {row['status']: int(row['n']) for row in cursor.fetchall()}


def mark_sent(cursor, delivery_id, response_status):
    cursor.execute(
        "UPDATE webhook_deliveries SET status = 'sent', attempts = attempts + 1, progress = 100, response_status = %s, "
        "last_error = NULL, sent_at = UTC_TIMESTAMP(), locked_by = NULL, heartbeat_at = NULL WHERE id = %s",
        (response_status, delivery_id),
    )


def mark_retry(cursor, delivery_id, *, attempts, final, response_status, error, delay_seconds):
    cursor.execute(
        "UPDATE webhook_deliveries SET status = %s, attempts = %s, response_status = %s, last_error = %s, progress = 0, "
        "locked_by = NULL, heartbeat_at = NULL, available_at = UTC_TIMESTAMP() + INTERVAL %s SECOND WHERE id = %s",
        ('failed' if final else 'queued', attempts, response_status, error[:500] if error else None, int(delay_seconds), delivery_id),
    )


def stamp_endpoint(cursor, endpoint_id, status):
    cursor.execute(
        'UPDATE webhook_endpoints SET last_delivery_at = UTC_TIMESTAMP(), last_status = %s WHERE id = %s', (status[:20], endpoint_id)
    )


def retry_delivery(cursor, delivery_id):
    """Put a failed delivery back in the queue with a fresh attempt budget."""
    cursor.execute(
        "UPDATE webhook_deliveries SET status = 'queued', attempts = 0, last_error = NULL, available_at = UTC_TIMESTAMP() "
        "WHERE id = %s AND status = 'failed'",
        (delivery_id,),
    )
    return cursor.rowcount
