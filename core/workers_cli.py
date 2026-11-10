"""`flask workers run`: host the background workers outside the web process.

    flask workers run          serve until SIGTERM / Ctrl+C (the systemd service)
    flask workers run --once   one pass of every job kind, then exit (cron, tests)
    flask workers status       what the heartbeat file says
"""

import json
import signal
import threading

import click
from flask import current_app
from flask.cli import with_appcontext


@click.group('workers')
def workers():
    """Export queue, timetable queue, nightly close-day and the quality-model retrainer."""


@workers.command('run')
@click.option('--once', is_flag=True, help='Run one pass of every job kind and exit.')
@with_appcontext
def workers_run(once):
    """Run the background workers in this process."""
    from core.schema.status import database_reason
    from services.worker_process import run_once, serve

    app = current_app._get_current_object()
    if not app.config.get('TENANT_REGISTRY_DB'):
        from extensions import get_db_connection

        reason = database_reason(get_db_connection)
        if reason:
            raise click.ClickException(reason)
    if once:
        counts = run_once(app)
        click.echo(json.dumps(counts, sort_keys=True))
        return

    stop = threading.Event()

    def request_stop(_signum, _frame):
        stop.set()

    for name in ('SIGTERM', 'SIGINT'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), request_stop)
    click.echo('Workers running. Stop with SIGTERM or Ctrl+C.')
    serve(app, stop)
    click.echo('Workers stopped.')


@workers.command('status')
@with_appcontext
def workers_status():
    """Print the last heartbeat and whether it counts as healthy."""
    from services.worker_process import heartbeat_problem, read_heartbeat

    app = current_app._get_current_object()
    beat = read_heartbeat(app)
    click.echo(json.dumps(beat, sort_keys=True) if beat else 'No heartbeat file.')
    problem = heartbeat_problem(app)
    if problem:
        click.echo(problem)
        raise SystemExit(1)
    click.echo('Workers healthy.')
