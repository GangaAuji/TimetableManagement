"""`flask db-adopt`: put an existing database under Alembic without changing it.

The live schema is read inside a READ ONLY transaction and compared with the
baseline snapshot. Any difference is printed and nothing is written. Only an
identical, unstamped database is stamped at the baseline revision, which
creates alembic_version and nothing else.
"""

import click
from flask import current_app
from flask.cli import with_appcontext

from core.schema.baseline import BASELINE_REVISION, BASELINE_SNAPSHOT, SUPPORTED_SERVER
from core.schema.introspect import compare, load_snapshot, read_schema, server_version

_STAMPED = """
SELECT version_num FROM `alembic_version`
"""
_HAS_VERSION_TABLE = """
SELECT 1 FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'alembic_version'
"""


def _read_live(engine):
    """Return (database name, server version, stamped versions, schema) without writing."""
    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        cursor.execute('START TRANSACTION READ ONLY')
        try:
            cursor.execute('SELECT DATABASE()')
            name = cursor.fetchone()[0]
            if not name:
                raise click.ClickException('The configured connection has no database selected.')
            if isinstance(name, bytes):
                name = name.decode('utf-8')
            version = server_version(cursor)
            cursor.execute(_HAS_VERSION_TABLE, (name,))
            stamped = []
            if cursor.fetchone():
                cursor.execute(_STAMPED)
                stamped = [row[0] for row in cursor.fetchall()]
            schema = read_schema(cursor, name)
        finally:
            cursor.execute('ROLLBACK')
            cursor.close()
    finally:
        connection.close()
    return name, version, stamped, schema


@click.command('db-adopt')
@click.option('--check', is_flag=True, help='Compare only. Never stamp, even when identical.')
@with_appcontext
def db_adopt(check):
    """Stamp an existing database at the baseline if its schema is identical."""
    if not BASELINE_SNAPSHOT.exists():
        raise click.ClickException(
            f'Baseline snapshot {BASELINE_SNAPSHOT.name} is missing. See docs/DATABASE.md.'
        )
    expected = load_snapshot(BASELINE_SNAPSHOT)
    migrate = current_app.extensions['migrate']
    engine = migrate.db.get_engine()

    name, version, stamped, live = _read_live(engine)
    click.echo(f'Database `{name}` on {version}.')

    if stamped:
        raise click.ClickException(
            f'`{name}` is already stamped at {", ".join(stamped)}. db-adopt only adopts an unmanaged database.'
        )

    baseline_version = expected.get('server_version')
    if version != baseline_version:
        click.echo(
            f'Warning: the baseline snapshot was taken on {baseline_version}; '
            f'the supported server is {SUPPORTED_SERVER}. Differences may come from the server version.'
        )

    differences = compare(expected['schema'], live)
    if differences:
        click.echo(f'{len(differences)} difference(s) from {BASELINE_REVISION}:')
        for line in differences:
            click.echo(f'  - {line}')
        click.echo('Not stamped. The database was not changed.')
        raise SystemExit(1)

    click.echo(f'The schema is identical to {BASELINE_REVISION}.')
    if check:
        click.echo('--check given: not stamped.')
        return

    from flask_migrate import stamp

    stamp(directory=migrate.directory, revision=BASELINE_REVISION)
    click.echo(f'Stamped `{name}` at {BASELINE_REVISION}. Run `flask db upgrade` for later revisions.')


def register_commands(app):
    app.cli.add_command(db_adopt)
