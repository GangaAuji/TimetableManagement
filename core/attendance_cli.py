"""`flask attendance close-day` and `flask attendance backfill-sessions`.

Both print counts only, never names, and write one audit_logs row when they
apply. `--dry-run` reports and changes nothing. See docs/DATABASE.md.
"""

from datetime import date, timedelta

import click
from flask.cli import with_appcontext


@click.group('attendance')
def attendance():
    """Lecture sessions: close past days and backfill history."""


def _date(value, name):
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise click.ClickException(f'{name} must be a date like 2026-03-02.')


BACKFILL_FROM = '0007_lecture_sessions'


def _connection(accepted=()):
    from core.schema.status import database_reason
    from extensions import get_db_connection

    reason = database_reason(get_db_connection, accepted)
    if reason:
        raise click.ClickException(reason)
    return get_db_connection()


@attendance.command('close-day')
@click.option('--date', 'day', default=None, help='The day to close (default: yesterday).')
@click.option('--from', 'date_from', default=None, help='First day of a range to close.')
@click.option('--to', 'date_to', default=None, help='Last day of the range (default: yesterday).')
@click.option('--dry-run', is_flag=True, help='Report what would be written and change nothing.')
@with_appcontext
def close_day_command(day, date_from, date_to, dry_run):
    """Record not_marked for every lecture of a past day that nobody marked or cancelled."""
    from services.lecture_sessions import close_day

    yesterday = date.today() - timedelta(days=1)
    if day and (date_from or date_to):
        raise click.ClickException('Give --date or --from/--to, not both.')
    if date_from or date_to:
        first = _date(date_from, '--from') or _date(date_to, '--to')
        last = _date(date_to, '--to') or yesterday
    else:
        first = last = _date(day, '--date') or yesterday
    if first > last:
        raise click.ClickException('--from must not be after --to.')
    if last > yesterday:
        raise click.ClickException('Only past days can be closed.')
    if (last - first).days > 366:
        raise click.ClickException('Close at most one year at a time.')
    connection = _connection()
    try:
        current = first
        totals = {'created': 0, 'existing': 0, 'holiday': 0, 'outside_semester': 0, 'absent_filled': 0}
        verb = 'to write' if dry_run else 'written'
        while current <= last:
            counts = close_day(connection, current, dry_run=dry_run, today=date.today())
            for key in totals:
                totals[key] += counts[key]
            click.echo(
                f"{counts['date']} ({counts['weekday']}): slots {counts['slots']}, "
                f"not_marked {verb} {counts['created']}, already recorded {counts['existing']}, "
                f"holiday {counts['holiday']}, outside semester {counts['outside_semester']}, "
                f"device absences {verb} {counts['absent_filled']}"
            )
            current += timedelta(days=1)
    finally:
        connection.close()
    if first != last:
        click.echo(
            f"Total: not_marked {verb} {totals['created']}, already recorded {totals['existing']}, "
            f"holiday {totals['holiday']}, outside semester {totals['outside_semester']}, "
            f"device absences {verb} {totals['absent_filled']}"
        )
    if dry_run:
        click.echo('Dry run: nothing was written.')


@attendance.command('backfill-sessions')
@click.option('--dry-run', is_flag=True, help='Report sessions, links and anomalies; change nothing.')
@with_appcontext
def backfill_command(dry_run):
    """Create held sessions for every marked lecture and link the marks. Never invents unmarked lectures.

    Runs on a database at 0007_lecture_sessions or later: 0008 refuses to
    upgrade while marks have no session, so this must be able to run first.
    """
    from core.schema.status import revisions_from
    from services.lecture_sessions import backfill_sessions

    connection = _connection(revisions_from(BACKFILL_FROM))
    try:
        report = backfill_sessions(connection, dry_run=dry_run)
    finally:
        connection.close()
    for line in report.lines():
        click.echo(line)
    if dry_run:
        click.echo('Dry run: nothing was written.')
