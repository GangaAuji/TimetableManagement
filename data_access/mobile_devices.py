"""Mobile device SQL. Callers pass a cursor."""


def fetch_mobile_devices(cursor):
    """Return registered mobile devices."""
    cursor.execute(
        """
            SELECT md.id, md.device_id, md.device_name, md.platform, md.owner_user_id,
                   md.is_active, md.rate_limit_per_minute, md.last_used_at, md.created_at,
                   u.username AS owner_username
            FROM mobile_devices md
            LEFT JOIN users u ON u.id = md.owner_user_id
            ORDER BY md.created_at DESC
            """
    )
    return cursor.fetchall()


def fetch_active_users(cursor):
    """Return active users for the device owner list."""
    cursor.execute("SELECT id, username, role FROM users WHERE status = 'active' ORDER BY username")
    return cursor.fetchall()


def insert_mobile_device(cursor, values):
    """Insert one mobile device."""
    cursor.execute(
        """
            INSERT INTO mobile_devices (
                device_id, device_name, platform, owner_user_id,
                api_key_secret, is_active, rate_limit_per_minute, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
            """,
        values,
    )


def fetch_device_id(cursor, device_pk):
    """Return the device id row."""
    cursor.execute("SELECT device_id FROM mobile_devices WHERE id = %s", (device_pk,))
    return cursor.fetchone()


def update_device_secret(cursor, secret, device_pk):
    """Replace a device secret."""
    cursor.execute(
        "UPDATE mobile_devices SET api_key_secret = %s, updated_at = NOW() WHERE id = %s",
        (secret, device_pk),
    )


def fetch_device_active(cursor, device_pk):
    """Return the active flag row."""
    cursor.execute("SELECT is_active FROM mobile_devices WHERE id = %s", (device_pk,))
    return cursor.fetchone()


def update_device_active(cursor, next_state, device_pk):
    """Store a device active flag."""
    cursor.execute(
        "UPDATE mobile_devices SET is_active = %s, updated_at = NOW() WHERE id = %s",
        (next_state, device_pk),
    )
