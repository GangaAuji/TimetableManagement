"""`flask admin create-superadmin USERNAME EMAIL`.

The password comes from --password-stdin, the SUPERADMIN_PASSWORD environment
variable, or a hidden prompt, in that order. It is hashed with werkzeug and
never printed, logged, or written to the audit log.
"""

import json
import os
import re
import sys

import click
from flask.cli import with_appcontext

PASSWORD_ENV = 'SUPERADMIN_PASSWORD'
SUPER_ADMIN = 'Super Admin'
_ACTIVITY = 'superadmin_created'
_SOURCE = 'flask admin create-superadmin'
_USERNAME = re.compile(r'^[A-Za-z0-9._@-]{3,50}$')
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@click.group('admin')
def admin():
    """Administrator accounts."""


def _password(from_stdin):
    if from_stdin:
        password = click.get_text_stream('stdin').readline().rstrip('\r\n')
    elif os.environ.get(PASSWORD_ENV):
        password = os.environ[PASSWORD_ENV]
    elif sys.stdin is not None and sys.stdin.isatty():
        password = click.prompt('Password', hide_input=True, confirmation_prompt=True)
    else:
        raise click.ClickException(
            f'No password given. Use --password-stdin, set {PASSWORD_ENV}, or run the command in a terminal.'
        )
    if not 8 <= len(password) <= 128:
        raise click.ClickException('The password must be 8 to 128 characters.')
    return password


def _audit(cursor, user_id, username, email, forced):
    cursor.execute(
        'INSERT INTO user_activity_log (user_id, activity_type, description, ip_address, user_agent) '
        'VALUES (%s, %s, %s, %s, %s)',
        (user_id, _ACTIVITY, f'Super Admin {username} created with {_SOURCE}', None, _SOURCE),
    )
    cursor.execute(
        'INSERT INTO audit_logs (user_id, username, action, entity_type, entity_id, new_values, '
        'request_method, request_url, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
        (
            user_id, username, _ACTIVITY, 'user', user_id,
            json.dumps({'username': username, 'email': email, 'role': SUPER_ADMIN, 'forced': forced}),
            'CLI', _SOURCE, 'success',
        ),
    )


@admin.command('create-superadmin')
@click.argument('username')
@click.argument('email')
@click.option('--password-stdin', is_flag=True, help='Read the password from the first line of standard input.')
@click.option('--force', is_flag=True, help='Create the account even when a Super Admin already exists.')
@with_appcontext
def create_superadmin(username, email, password_stdin, force):
    """Create a Super Admin account."""
    from core.schema.status import database_reason
    from extensions import get_db_connection
    from security.passwords import hash_password

    if not _USERNAME.match(username):
        raise click.ClickException('The username must be 3 to 50 letters, digits, or . _ @ -')
    if len(email) > 100 or not _EMAIL.match(email):
        raise click.ClickException('Enter a valid email address of up to 100 characters.')
    reason = database_reason(get_db_connection)
    if reason:
        raise click.ClickException(reason)

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT 1 FROM roles WHERE name = %s', (SUPER_ADMIN,))
        if cursor.fetchone() is None:
            raise click.ClickException('The Super Admin role is missing. Run `flask seed run` first.')
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = %s', (SUPER_ADMIN,))
        existing = cursor.fetchone()[0]
        if existing and not force:
            raise click.ClickException(
                f'{existing} Super Admin account(s) already exist. Use --force to add another.'
            )
        cursor.execute('SELECT 1 FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            raise click.ClickException(f'The username {username!r} is already taken.')
        cursor.execute('SELECT 1 FROM users WHERE LOWER(email) = LOWER(%s)', (email,))
        if cursor.fetchone():
            raise click.ClickException(f'The email {email!r} is already used by another account.')
        connection.rollback()

        password_hash = hash_password(_password(password_stdin))
        cursor.execute(
            'INSERT INTO users (username, password, role, email, status, password_changed_at) '
            "VALUES (%s, %s, %s, %s, 'active', NOW())",
            (username, password_hash, SUPER_ADMIN, email),
        )
        user_id = cursor.lastrowid
        _audit(cursor, user_id, username, email, bool(existing))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
    click.echo(f"Created Super Admin '{username}' (id {user_id}).")
