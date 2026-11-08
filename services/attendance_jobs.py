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


def ensure_worker(app):
    """Start the worker once for this process. Never under a Flask CLI command or when workers are off."""
    global _started
    if app.config.get('CLI_COMMAND') or not app.config.get('BACKGROUND_WORKERS', True):
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


def run_once(app, today=None):
    """Close the last CATCH_UP_DAYS days. Returns the per-day counts."""
    from extensions import get_db_connection
    from services.lecture_sessions import close_day

    today = today or date.today()
    results = []
    with app.app_context():
        connection = get_db_connection()
        try:
            for back in range(CATCH_UP_DAYS, 0, -1):
                results.append(close_day(connection, today - timedelta(days=back), today=today))
        finally:
            connection.close()
    return results


def _loop(app, hour):
    while True:
        time.sleep(max(60, seconds_until(datetime.now(), hour)))
        try:
            results = run_once(app)
            app.logger.info(
                'Attendance close-day: %s not_marked rows written for %s days.',
                sum(r['created'] for r in results), len(results),
            )
        except Exception:
            app.logger.exception('Attendance close-day worker failed')
