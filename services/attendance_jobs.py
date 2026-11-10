"""The nightly close-day worker: after midnight, record not_marked for yesterday's unmarked lectures.

One daemon thread per process. It runs close_day for each of the last
CATCH_UP_DAYS days (close_day is idempotent, so a night the server was down is
caught up the next one). ATTENDANCE_CLOSE_DAY_HOUR is the local hour it runs
at; a negative value turns the worker off. Never started under a Flask CLI
command; `flask attendance close-day` does the same work by hand.
"""

import threading
import time
from datetime import date, datetime, timedelta

CATCH_UP_DAYS = 7
THREAD_NAME = 'attendance-close-day'

_guard = threading.Lock()
_started = False


def ensure_worker(app, force=False):
    """Start the worker once for this process. Never under a Flask CLI command or when workers are off, unless `force`."""
    global _started
    if not force and (app.config.get('CLI_COMMAND') or not app.config.get('BACKGROUND_WORKERS', True)):
        return
    hour = int(app.config.get('ATTENDANCE_CLOSE_DAY_HOUR', 1))
    if hour < 0:
        app.logger.info('Attendance close-day worker disabled (ATTENDANCE_CLOSE_DAY_HOUR=%s).', hour)
        return
    with _guard:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(app, hour), name=THREAD_NAME, daemon=True).start()


def seconds_until(now, hour):
    """Seconds from `now` to the next time the clock reads `hour`:00."""
    target = now.replace(hour=hour % 24, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_once(app, today=None, tenant=None):
    """Close the last CATCH_UP_DAYS days on one database. Returns the per-day counts."""
    from core.tenancy import tenant_context
    from extensions import get_db_connection
    from services.lecture_sessions import close_day

    today = today or date.today()
    results = []
    with tenant_context(app, tenant):
        connection = get_db_connection()
        try:
            for back in range(CATCH_UP_DAYS, 0, -1):
                results.append(close_day(connection, today - timedelta(days=back), today=today))
            purge_face_templates(app, connection)
            queue_notifications(app, connection, today)
        finally:
            connection.close()
    return results


def purge_face_templates(app, connection):
    """Delete face templates past FACE_RETENTION_DAYS after consent withdrawal or deactivation (docs/FACE_ATTENDANCE.md)."""
    from services.face.safeguards import purge_templates

    cursor = connection.cursor(dictionary=True)
    try:
        counts = purge_templates(cursor)
        connection.commit()
    except Exception:
        connection.rollback()
        app.logger.exception('Face template retention purge failed')
        return None
    finally:
        cursor.close()
    if any(counts.values()):
        app.logger.info('Face template retention: %s', counts)
    return counts


def queue_notifications(app, connection, today):
    """Yesterday's not-marked digest to the HODs and this month's defaulter alerts (docs/NOTIFICATIONS.md)."""
    from services.notifications import after_close_day

    return after_close_day(app, connection, today)


def run_all(app, today=None):
    """run_once for every active tenant (or the single database). Returns {slug or None: results}."""
    from core.tenancy import tenants_to_serve

    outcome = {}
    for tenant in tenants_to_serve(app):
        key = tenant.slug if tenant is not None else None
        try:
            outcome[key] = run_once(app, today=today, tenant=tenant)
        except Exception:
            app.logger.exception('Attendance close-day failed for tenant %s', key or 'default')
    return outcome


def _loop(app, hour):
    while True:
        time.sleep(max(60, seconds_until(datetime.now(), hour)))
        try:
            for key, results in run_all(app).items():
                app.logger.info(
                    'Attendance close-day%s: %s not_marked rows written for %s days.',
                    f' [{key}]' if key else '', sum(r['created'] for r in results), len(results),
                )
        except Exception:
            app.logger.exception('Attendance close-day worker failed')
