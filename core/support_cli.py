"""``flask support bundle`` writes the diagnosis file. The shell wrapper adds host checks."""

import json

import click
from flask import current_app
from flask.cli import with_appcontext


@click.group('support')
def support_group():
    """Diagnosis for a support request."""


@support_group.command('bundle')
@click.option('--output', required=True, type=click.Path(dir_okay=False), help='Path of the JSON report to write.')
@with_appcontext
def support_bundle(output):
    """Write a JSON report with secrets removed. This does not include a database dump."""
    from core.support_bundle import build_report

    database = 'not checked'
    try:
        from app_factory import _database_problem

        database = _database_problem(current_app) or 'ok'
    except Exception as exc:
        database = f'unreadable ({exc.__class__.__name__})'
    report = build_report(current_app, database)
    with open(output, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write('\n')
    click.echo(f'Wrote {output}.')
