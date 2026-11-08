"""Temporary sign-in lock, per account.

SIGN_IN_MAX_FAILED_ATTEMPTS wrong passwords within SIGN_IN_FAILURE_WINDOW_MINUTES
lock the account until users.locked_until, SIGN_IN_LOCK_MINUTES later. The lock
ends by itself; a successful sign-in or an admin unlock clears the counter.
Super Admin accounts get the same temporary lock. Every lock and unlock is
written to the audit log. Times come from the database clock.
"""

from flask import current_app

from extensions import get_db_connection
from security import log_activity


def _setting(name, default):
    try:
        value = int(current_app.config.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def max_attempts():
    return _setting('SIGN_IN_MAX_FAILED_ATTEMPTS', 5)


def window_minutes():
    return _setting('SIGN_IN_FAILURE_WINDOW_MINUTES', 15)


def lock_minutes():
    return _setting('SIGN_IN_LOCK_MINUTES', 15)


def record_failed_sign_in(user_id):
    """Count one wrong password on its own connection. Return True when the account is locked now.

    This commits even when the request later fails, so the count cannot be
    rolled back by the attacker's own request.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT failed_attempts, locked_until, NOW() AS now,
                   locked_until IS NOT NULL AND locked_until > NOW() AS locked_now,
                   failed_window_start IS NULL
                       OR failed_window_start <= NOW() - INTERVAL %s MINUTE AS window_over
            FROM users WHERE id = %s FOR UPDATE
            """,
            (window_minutes(), user_id),
        )
        row = cursor.fetchone()
        if row is None:
            connection.rollback()
            return False
        if row['locked_now']:
            connection.rollback()
            return True
        expired = row['locked_until'] is not None
        if expired or row['window_over']:
            attempts = 1
            window_sql = 'NOW()'
        else:
            attempts = int(row['failed_attempts'] or 0) + 1
            window_sql = 'failed_window_start'
        locking = attempts >= max_attempts()
        lock_sql = 'NOW() + INTERVAL %s MINUTE' if locking else 'NULL'
        params = [attempts] + ([lock_minutes()] if locking else []) + [user_id]
        cursor.execute(
            f'UPDATE users SET failed_attempts = %s, failed_window_start = {window_sql}, '
            f'locked_until = {lock_sql} WHERE id = %s',
            tuple(params),
        )
        if expired:
            log_activity(user_id, 'account_unlocked', 'Sign-in lock expired', entity_type='user',
                         entity_id=user_id, cursor=cursor)
        if locking:
            log_activity(
                user_id, 'account_locked',
                f'Locked for {lock_minutes()} minutes after {attempts} failed sign-ins',
                entity_type='user', entity_id=user_id,
                new_values={'failed_attempts': attempts, 'lock_minutes': lock_minutes()},
                cursor=cursor,
            )
        connection.commit()
        return locking
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def clear_after_sign_in(cursor, user):
    """Reset the counter in the sign-in's transaction. An expired lock is logged as unlocked."""
    cursor.execute(
        'UPDATE users SET failed_attempts = 0, failed_window_start = NULL, locked_until = NULL WHERE id = %s',
        (user['id'],),
    )
    if user.get('locked_until') is not None:
        log_activity(user['id'], 'account_unlocked', 'Sign-in lock expired', entity_type='user',
                     entity_id=user['id'], cursor=cursor)


def unlock_account(cursor, user_id, actor_id):
    """Admin unlock in the caller's transaction: clears the counter, the lock, and a 'locked' status."""
    cursor.execute(
        'SELECT status, failed_attempts, locked_until FROM users WHERE id = %s', (user_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return False
    status = row['status'] if isinstance(row, dict) else row[0]
    cursor.execute(
        "UPDATE users SET failed_attempts = 0, failed_window_start = NULL, locked_until = NULL, "
        "status = IF(status = 'locked', 'active', status) WHERE id = %s",
        (user_id,),
    )
    log_activity(
        actor_id, 'account_unlocked', f'Unlocked user ID {user_id}', entity_type='user', entity_id=user_id,
        old_values={'status': status}, cursor=cursor,
    )
    return True
