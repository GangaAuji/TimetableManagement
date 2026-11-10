"""`flask tenant ...` and the `--tenant SLUG` option for commands that work on one database.

tenant init                    create the registry table
tenant create SLUG --hostname  create the database, upgrade, seed, optional Super Admin, register
tenant list                    show every tenant and its migration stamp
tenant upgrade SLUG | --all    `db upgrade` on one or every active tenant
tenant set-status SLUG STATUS  active | suspended
tenant forget SLUG             remove the registry row (the database is kept)

The app never drops a tenant database. Passwords follow `flask admin
create-superadmin`: --password-stdin, SUPERADMIN_PASSWORD, or a hidden prompt.
"""

import functools

import click
from flask import current_app
from flask.cli import with_appcontext

from core.tenancy import STATUSES, Tenant, bind, registry_enabled
from core.tenancy.registry import (
    Registry,
    default_database_name,
    normalise_host,
    valid_database_name,
    valid_hostname,
    valid_slug,
)


def _registry():
    if not registry_enabled(current_app.config):
        raise click.ClickException('TENANT_REGISTRY_DB is not set; this installation serves one college.')
    return Registry.from_config(current_app.config)


def _tenant_or_fail(registry, slug):
    tenant = registry.by_slug(slug)
    if tenant is None:
        raise click.ClickException(f'No tenant with slug {slug!r}.')
    return tenant


def tenant_option(command):
    """Add `--tenant SLUG` and bind that tenant before the command body runs. Apply inside @with_appcontext."""

    @click.option('--tenant', 'tenant_slug', default=None, metavar='SLUG', help='The college to work on (tenant registry installs).')
    @functools.wraps(command)
    def wrapper(*args, tenant_slug=None, **kwargs):
        if registry_enabled(current_app.config):
            if not tenant_slug:
                raise click.ClickException('This installation has a tenant registry. Pass --tenant SLUG.')
            registry = Registry.from_config(current_app.config)
            tenant = _tenant_or_fail(registry, tenant_slug)
            bind(tenant)
            click.echo(f'Tenant {tenant.slug} (database `{tenant.db_name}`).')
        elif tenant_slug:
            raise click.ClickException('--tenant needs TENANT_REGISTRY_DB; this installation serves one college.')
        return command(*args, **kwargs)

    return wrapper


def _settings_for(db_name):
    config = current_app.config
    settings = {
        'host': config.get('MYSQL_HOST'),
        'user': config.get('MYSQL_USER'),
        'password': config.get('MYSQL_PASSWORD'),
        'database': db_name,
    }
    if config.get('MYSQL_INIT_COMMAND'):
        settings['init_command'] = config.get('MYSQL_INIT_COMMAND')
    return settings


def _refuse_in_tests(db_name):
    if current_app.config.get('TESTING'):
        from config.testing import test_database_problem

        problem = test_database_problem(db_name)
        if problem:
            raise click.ClickException(f'Refusing in a testing app: {problem}')


def _database_exists(registry, db_name):
    connection = registry.connect()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute('SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s', (db_name,))
            return cursor.fetchone() is not None
        finally:
            cursor.close()
            connection.rollback()
    finally:
        connection.close()


def _create_database(registry, db_name):
    connection = registry.connect()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(f'CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            connection.commit()
        finally:
            cursor.close()
    finally:
        connection.close()


def _stamp(db_name):
    import mysql.connector

    settings = _settings_for(db_name)
    try:
        connection = mysql.connector.connect(**settings, autocommit=False)
    except mysql.connector.Error as exc:
        return f'unreachable ({exc.__class__.__name__})'
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
                (db_name, 'alembic_version'),
            )
            if cursor.fetchone() is None:
                return 'unstamped'
            cursor.execute(f'SELECT version_num FROM `{db_name}`.alembic_version')
            rows = [row[0] for row in cursor.fetchall()]
            return ', '.join(rows) if rows else 'unstamped'
        finally:
            cursor.close()
            connection.rollback()
    finally:
        connection.close()


@click.group('tenant')
def tenant():
    """Colleges served by this installation (one database each)."""


@tenant.command('init')
@with_appcontext
def tenant_init():
    """Create the registry table if it is missing."""
    registry = _registry()
    _refuse_in_tests(registry.settings['database'])
    registry.ensure_schema()
    click.echo(f"Tenant registry ready in `{registry.settings['database']}`.")


@tenant.command('create')
@click.argument('slug')
@click.option('--hostname', required=True, help='The Host header that reaches this college, e.g. abc.timetable.example')
@click.option('--database', 'db_name', default=None, help='Database name. Default: college_timetable_<slug>.')
@click.option('--admin-username', default=None, help='Create a Super Admin with this username.')
@click.option('--admin-email', default=None, help='Email for the Super Admin.')
@click.option('--password-stdin', is_flag=True, help='Read the Super Admin password from the first line of standard input.')
@with_appcontext
def tenant_create(slug, hostname, db_name, admin_username, admin_email, password_stdin):
    """Create a college: its database, migrations, seed rows, optional Super Admin, and the registry row."""
    from core.admin_cli import create_superadmin_account
    from core.schema.runner import run_alembic
    from extensions import get_db_connection
    from seeders import run_seeders

    if not valid_slug(slug):
        raise click.ClickException('The slug must be 1 to 40 lowercase letters, digits or hyphens, not starting or ending with a hyphen.')
    hostname = normalise_host(hostname)
    if not valid_hostname(hostname):
        raise click.ClickException('The hostname must be a lowercase DNS name without a scheme or path.')
    db_name = db_name or default_database_name(slug)
    if not valid_database_name(db_name):
        raise click.ClickException('The database name may contain only lowercase letters, digits and underscores (64 at most).')
    if (admin_username is None) != (admin_email is None):
        raise click.ClickException('Give both --admin-username and --admin-email, or neither.')

    registry = _registry()
    _refuse_in_tests(registry.settings['database'])
    _refuse_in_tests(db_name)
    registry.ensure_schema()
    for existing, field in ((registry.by_slug(slug), 'slug'), (registry.by_hostname(hostname), 'hostname'), (registry.by_database(db_name), 'database')):
        if existing is not None:
            raise click.ClickException(f'A tenant with that {field} already exists: {existing.slug}.')
    if _database_exists(registry, db_name):
        raise click.ClickException(f'Database `{db_name}` already exists. Choose another name; the app never adopts or drops a database here.')
    if current_app.config.get('LICENSE_REQUIRED'):
        from core.license import growth_block
        blocked = growth_block(current_app.config, 'institutions', len(registry.all()))
        if blocked:
            raise click.ClickException(blocked[1])

    record = registry.insert(Tenant(slug=slug, hostname=hostname, db_name=db_name, status='provisioning'))
    click.echo(f'Registered {slug} ({hostname}) as provisioning.')
    try:
        _create_database(registry, db_name)
        click.echo(f'Created database `{db_name}`.')
        run_alembic(_settings_for(db_name), 'upgrade', 'head')
        click.echo('Migrations applied.')
        bind(record)
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            results = run_seeders(cursor)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()
        for result in results:
            click.echo(result.summary())
        if admin_username is not None:
            user_id = create_superadmin_account(admin_username, admin_email, password_stdin, force=False)
            click.echo(f"Created Super Admin '{admin_username}' (id {user_id}).")
    except BaseException:
        click.echo(
            f'Provisioning failed. {slug} stays registered as provisioning; fix the cause, '
            f'`flask tenant forget {slug}`, drop `{db_name}` by hand if it was created, and run create again.',
            err=True,
        )
        raise
    registry.set_status(slug, 'active')
    click.echo(f'Tenant {slug} is active at {hostname}.')


@tenant.command('list')
@with_appcontext
def tenant_list():
    """Show every tenant with its hostname, database, status and migration stamp."""
    registry = _registry()
    tenants = registry.all()
    if not tenants:
        click.echo('No tenants registered.')
        return
    for item in tenants:
        click.echo(f'{item.slug}\t{item.hostname}\t{item.db_name}\t{item.status}\t{_stamp(item.db_name)}')


@tenant.command('upgrade')
@click.argument('slug', required=False)
@click.option('--all', 'every', is_flag=True, help='Upgrade every active tenant.')
@with_appcontext
def tenant_upgrade(slug, every):
    """Run `db upgrade` to head on one tenant, or on every active one."""
    from core.schema.runner import run_alembic

    registry = _registry()
    if every == bool(slug):
        raise click.ClickException('Give a SLUG or --all, not both.')
    targets = [_tenant_or_fail(registry, slug)] if slug else [t for t in registry.all() if t.active]
    for item in targets:
        _refuse_in_tests(item.db_name)
        click.echo(f'Upgrading {item.slug} (`{item.db_name}`)...')
        run_alembic(_settings_for(item.db_name), 'upgrade', 'head')
        click.echo(f'{item.slug}: {_stamp(item.db_name)}')


@tenant.command('set-status')
@click.argument('slug')
@click.argument('status', type=click.Choice([s for s in STATUSES if s != 'provisioning']))
@with_appcontext
def tenant_set_status(slug, status):
    """Suspend a college (requests get 503) or make it active again."""
    registry = _registry()
    _tenant_or_fail(registry, slug)
    registry.set_status(slug, status)
    click.echo(f'{slug} is now {status}.')


@tenant.command('forget')
@click.argument('slug')
@click.confirmation_option(prompt='Remove the registry row? The database itself is kept.')
@with_appcontext
def tenant_forget(slug):
    """Remove a tenant from the registry. Its database is never dropped by the app."""
    registry = _registry()
    item = _tenant_or_fail(registry, slug)
    registry.delete(slug)
    click.echo(f'Forgot {slug}. Database `{item.db_name}` was left in place.')
