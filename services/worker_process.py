"""The worker process behind `flask workers run`.

In production the web tier runs gunicorn with BACKGROUND_WORKERS=False and
one systemd service runs `flask workers run`, which hosts the export queue,
the timetable queue, the nightly close-day and the quality-model retrainer
in a single process. It writes WORKERS_HEARTBEAT_FILE every
WORKERS_HEARTBEAT_SECONDS so /health can report a dead worker service.

`run_once` does one pass of everything and returns, for cron-style use and
for tests.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

DEFAULT_HEARTBEAT_SECONDS = 30
DEFAULT_STALE_SECONDS = 180
THREAD_NAMES = ('export-queue', 'timetable-queue', 'notification-outbox', 'webhook-outbox', 'attendance-close-day', 'quality-model-retrainer')


def heartbeat_path(app):
    configured = app.config.get('WORKERS_HEARTBEAT_FILE')
    if configured:
        return configured
    log_file = app.config.get('LOG_FILE') or ''
    directory = os.path.dirname(log_file) if log_file else os.path.join(app.root_path, 'logs')
    return os.path.join(directory or '.', 'workers.heartbeat')


def expected_threads(app):
    """The worker threads this configuration should have running."""
    names = ['export-queue', 'timetable-queue']
    if app.config.get('NOTIFICATIONS_ENABLED', True):
        names.append('notification-outbox')
    if app.config.get('WEBHOOKS_ENABLED', True):
        names.append('webhook-outbox')
    if int(app.config.get('ATTENDANCE_CLOSE_DAY_HOUR', 1)) >= 0:
        names.append('attendance-close-day')
    if int(app.config.get('QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES', 0) or 0) > 0:
        names.append('quality-model-retrainer')
    return names


def write_heartbeat(app, extra=None):
    """Write the heartbeat file atomically. Returns the payload written."""
    from services.job_claims import WORKER_ID

    alive = {thread.name for thread in threading.enumerate()}
    payload = {
        'worker_id': WORKER_ID,
        'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'threads': {name: name in alive for name in expected_threads(app)},
    }
    if extra:
        payload.update(extra)
    if extra and extra.get('mode') == 'once':
        payload['threads'] = {}  # a single pass has no long-running threads to report
    path = heartbeat_path(app)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    temporary = f'{path}.{os.getpid()}.tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle)
    os.replace(temporary, path)
    return payload


def read_heartbeat(app):
    """The last heartbeat payload plus its age in seconds, or None when there is no file."""
    path = heartbeat_path(app)
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
        age = max(0.0, time.time() - os.path.getmtime(path))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    payload['age_seconds'] = int(age)
    return payload


def heartbeat_problem(app):
    """Why the worker service looks dead, or None. Only consulted when REQUIRE_WORKERS is on."""
    stale = int(app.config.get('WORKERS_STALE_SECONDS', DEFAULT_STALE_SECONDS) or DEFAULT_STALE_SECONDS)
    beat = read_heartbeat(app)
    if beat is None:
        return f'No worker heartbeat at {heartbeat_path(app)}. Is `flask workers run` running?'
    if beat['age_seconds'] > stale:
        return f"The worker heartbeat is {beat['age_seconds']} s old (limit {stale} s)."
    dead = [name for name, alive in (beat.get('threads') or {}).items() if not alive]
    if dead:
        return f"Worker thread(s) not running: {', '.join(sorted(dead))}."
    return None


def start_all(app):
    """Start every worker thread in this process regardless of CLI_COMMAND and BACKGROUND_WORKERS."""
    from app_factory import _start_quality_model_retrainer
    from services.attendance_jobs import ensure_worker as ensure_close_day
    from services.export_jobs import ensure_worker as ensure_exports
    from services.notifications import ensure_worker as ensure_notifications
    from services.timetable_jobs import ensure_worker as ensure_timetables
    from services.webhooks import ensure_worker as ensure_webhooks

    ensure_exports(app, force=True)
    ensure_timetables(app, force=True)
    ensure_notifications(app, force=True)
    ensure_webhooks(app, force=True)
    ensure_close_day(app, force=True)
    _start_quality_model_retrainer(app, force=True)


def run_once(app):
    """One pass of every job kind. Returns counts per kind."""
    from app_factory import retrain_quality_model_once
    from services.attendance_jobs import run_all as close_days
    from services.export_jobs import run_pass as exports
    from services.notifications import run_pass as notifications
    from services.timetable_jobs import run_pass as timetables
    from services.webhooks import run_pass as webhooks

    counts = {}
    counts['exports'] = exports(app, drain=True)
    counts['timetables'] = timetables(app, drain=True)
    closed = close_days(app)
    counts['close_day_tenants'] = len(closed)
    counts['not_marked_written'] = sum(sum(day['created'] for day in results) for results in closed.values())
    counts['notifications_sent'] = notifications(app, drain=True)
    counts['webhooks_delivered'] = webhooks(app, drain=True)
    if int(app.config.get('QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES', 0) or 0) > 0:
        retrain_quality_model_once(app)
        counts['retrained'] = True
    write_heartbeat(app, {'mode': 'once'})
    return counts


def serve(app, stop_event=None):
    """Start the threads and keep the heartbeat fresh until `stop_event` is set (or the process is signalled)."""
    stop_event = stop_event or threading.Event()
    seconds = int(app.config.get('WORKERS_HEARTBEAT_SECONDS', DEFAULT_HEARTBEAT_SECONDS) or DEFAULT_HEARTBEAT_SECONDS)
    start_all(app)
    write_heartbeat(app, {'mode': 'serve'})
    while not stop_event.wait(max(1, seconds)):
        try:
            write_heartbeat(app, {'mode': 'serve'})
        except OSError:
            app.logger.exception('Could not write the worker heartbeat')
    try:
        os.remove(heartbeat_path(app))
    except OSError:
        pass
