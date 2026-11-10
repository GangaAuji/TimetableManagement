"""`flask notifications ...`: the outbox from the command line.

    flask notifications status              delivery route, queue counts, trigger switches
    flask notifications send [--one]        send what is queued now (one pass; --one sends a single message)
    flask notifications test ADDRESS        queue a test message to ADDRESS and send it
    flask notifications list [--limit N]    the most recent outbox rows
    flask notifications digest [--date D]   queue yesterday's (or D's) not-marked digest to the HODs
    flask notifications defaulters          queue this month's defaulter alerts

Never prints an SMTP password. See docs/NOTIFICATIONS.md.
"""

from datetime import date, timedelta

import click
from flask import current_app
from flask.cli import with_appcontext

from core.tenancy.cli import tenant_option


@click.group('notifications')
def notifications_group():
    """Notifications outbox: status, send, test."""


def _connection():
    from core.schema.status import database_reason
    from extensions import get_db_connection

    reason = database_reason(get_db_connection)
    if reason:
        raise click.ClickException(reason)
    return get_db_connection()


@notifications_group.command('status')
@with_appcontext
@tenant_option
def status():
    """Where mail goes, how many messages are queued, failed and sent, and which triggers are on."""
    from services import notifications

    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        state = notifications.status(cursor)
        settings = notifications.load_settings(cursor)
    finally:
        cursor.close()
        connection.close()
    click.echo(f"Enabled: {'yes' if state['enabled'] else 'no'}")
    click.echo(f"Delivery: {state['delivery']}{(' via ' + state['smtp_host']) if state.get('smtp_host') else ''}")
    click.echo(f"Queued: {state['queued']}  Failed: {state['failed']}  Sent: {state['sent']}")
    click.echo('Triggers: ' + ', '.join(f"{name}={'on' if settings.get(name) else 'off'}" for name in notifications.SWITCHES))


@notifications_group.command('send')
@click.option('--one', is_flag=True, help='Send a single message instead of draining the queue.')
@with_appcontext
@tenant_option
def send(one):
    """Send queued messages for this database now."""
    from services import notifications

    counts = notifications.run_tenant(current_app, drain=not one)
    click.echo(' '.join(f'{key}={value}' for key, value in counts.items()))
    if counts['deferred']:
        raise click.ClickException('No SMTP account is configured: set SMTP_HOST or the tenant notification settings.')


@notifications_group.command('test')
@click.argument('address')
@with_appcontext
@tenant_option
def test(address):
    """Queue a test message to ADDRESS and try to send it."""
    from services import notifications

    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        queued = notifications.queue_test_message(cursor, to=address)
        connection.commit()
    finally:
        cursor.close()
        connection.close()
    if not queued:
        raise click.ClickException('The test message was not queued.')
    counts = notifications.run_tenant(current_app, drain=True)
    click.echo(f"Queued #{queued}; " + ' '.join(f'{key}={value}' for key, value in counts.items()))


@notifications_group.command('list')
@click.option('--limit', default=20, show_default=True, type=int)
@with_appcontext
@tenant_option
def list_rows(limit):
    """The most recent outbox rows."""
    from services import notifications

    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        rows = notifications.recent(cursor, limit=max(1, min(limit, 500))) if notifications.table_exists(cursor) else []
    finally:
        cursor.close()
        connection.close()
    if not rows:
        click.echo('No notifications.')
        return
    for row in rows:
        error = f" ({row['last_error']})" if row.get('last_error') else ''
        click.echo(f"#{row['id']} {row['created_at']} {row['kind']:<18} {row['status']:<8} {row.get('recipient_email') or '-'} - {row['subject']}{error}")


@notifications_group.command('digest')
@click.option('--date', 'day', default=None, help='YYYY-MM-DD; yesterday when omitted.')
@with_appcontext
@tenant_option
def digest(day):
    """Queue the not-marked digest for one day to the HODs."""
    from services import notifications

    target = date.fromisoformat(day) if day else date.today() - timedelta(days=1)
    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        queued = notifications.not_marked_digest(cursor, target)
        connection.commit()
    finally:
        cursor.close()
        connection.close()
    click.echo(f'Queued {queued} digest message(s) for {target}.')


@notifications_group.command('defaulters')
@click.option('--threshold', default=None, type=float, help='Override the institution threshold for this run.')
@with_appcontext
@tenant_option
def defaulters(threshold):
    """Queue this month's defaulter alerts (one per student per month)."""
    from services import notifications

    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        queued = notifications.defaulter_alerts(cursor, threshold=threshold)
        connection.commit()
    finally:
        cursor.close()
        connection.close()
    click.echo(f'Queued {queued} defaulter alert(s).')
