"""Claiming queued job rows so that several worker processes can share one table.

A claim is `status = 'running'` plus `locked_by = <this worker>` and a fresh
`heartbeat_at`. The worker renews the heartbeat whenever it writes progress.
Rows whose heartbeat is older than JOB_STALE_SECONDS are requeued by any
worker on its next pass: a crashed or killed worker loses its claim after
that long and nothing else. Times are UTC from the database clock, so worker
hosts need no clock agreement.
"""

import os
import secrets
import socket

from flask import current_app, has_app_context

DEFAULT_STALE_SECONDS = 900
WORKER_ID = f'{socket.gethostname()[:30]}:{os.getpid()}:{secrets.token_hex(4)}'[:64]


def stale_seconds():
    if not has_app_context():
        return DEFAULT_STALE_SECONDS
    try:
        value = int(current_app.config.get('JOB_STALE_SECONDS', DEFAULT_STALE_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_STALE_SECONDS
    return value if value > 0 else DEFAULT_STALE_SECONDS


def claim_next(cursor, table, extra_set='', extra_where=''):
    """Move the oldest queued row (matching `extra_where`, if given) to running under this worker. Returns its id, or None."""
    where = f"status = 'queued'{(' AND ' + extra_where) if extra_where else ''}"
    cursor.execute(f"SELECT id FROM `{table}` WHERE {where} ORDER BY id ASC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        return None
    job_id = row['id'] if isinstance(row, dict) else row[0]
    cursor.execute(
        f"UPDATE `{table}` SET status = 'running', progress = 1, locked_by = %s, heartbeat_at = UTC_TIMESTAMP()"
        f"{(', ' + extra_set) if extra_set else ''} WHERE id = %s AND status = 'queued'",
        (WORKER_ID, job_id),
    )
    return job_id if cursor.rowcount == 1 else None


def heartbeat_clause():
    """SQL to append to a progress UPDATE so the claim stays fresh."""
    return 'heartbeat_at = UTC_TIMESTAMP()'


def requeue_stale(cursor, table, reset_set, seconds=None):
    """Requeue running rows whose heartbeat is older than `seconds` (or never written). Returns how many."""
    seconds = stale_seconds() if seconds is None else int(seconds)
    cursor.execute(
        f"UPDATE `{table}` SET status = 'queued', locked_by = NULL, heartbeat_at = NULL, {reset_set} "
        "WHERE status = 'running' "
        "AND (heartbeat_at IS NULL OR heartbeat_at <= UTC_TIMESTAMP() - INTERVAL %s SECOND)",
        (seconds,),
    )
    return cursor.rowcount
