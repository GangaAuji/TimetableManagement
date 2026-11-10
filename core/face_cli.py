"""`flask face ...`: template encryption, key rotation, consent and retention.

    flask face generate-key                 print a new FACE_TEMPLATE_KEY (nothing is stored)
    flask face status                       how many templates are encrypted / plaintext / unreadable
    flask face encrypt-templates            rewrite plaintext templates with FACE_TEMPLATE_KEY
    flask face rotate-key                   rewrite every template with FACE_TEMPLATE_KEY, reading the
                                            old ones with FACE_TEMPLATE_KEY_PREVIOUS
    flask face consent USER_ID give|withdraw  record consent (or withdraw it and delete the templates)
    flask face purge [--days N] [--dry-run] retention: delete templates of withdrawn / inactive people

Counts only are printed; never a template or a key. See docs/FACE_ATTENDANCE.md.
"""

import click
from cryptography.fernet import Fernet
from flask import current_app
from flask.cli import with_appcontext

from core.tenancy.cli import tenant_option


@click.group('face')
def face():
    """Face template encryption, consent and retention."""


def _connection():
    from core.schema.status import database_reason
    from extensions import get_db_connection

    reason = database_reason(get_db_connection)
    if reason:
        raise click.ClickException(reason)
    return get_db_connection()


def _require_key():
    from services.face.templates import key_problem

    problem = key_problem(current_app.config)
    if problem:
        raise click.ClickException(problem)


@face.command('generate-key')
def generate_key():
    """Print a new Fernet key for FACE_TEMPLATE_KEY. Store it in the environment, never in the repository."""
    click.echo(Fernet.generate_key().decode('ascii'))


@face.command('status')
@with_appcontext
@tenant_option
def status():
    """Count encrypted, plaintext and unreadable templates, and people with and without consent."""
    from services.face.templates import decode_template, is_encrypted, key_problem

    problem = key_problem(current_app.config)
    click.echo(f'Key: {"configured" if not problem else problem}')
    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        counts = {'encrypted': 0, 'plaintext': 0, 'unreadable': 0}
        cursor.execute('SELECT embedding_json FROM mobile_face_templates')
        for row in cursor.fetchall():
            stored = row['embedding_json']
            readable = decode_template(stored) is not None
            if not readable:
                counts['unreadable'] += 1
            elif is_encrypted(stored):
                counts['encrypted'] += 1
            else:
                counts['plaintext'] += 1
        cursor.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM face_consents WHERE withdrawn_at IS NULL AND notice_version = %s",
            (current_app.config.get('FACE_CONSENT_NOTICE_VERSION'),),
        )
        consented = cursor.fetchone()['n']
        cursor.execute(
            'SELECT COUNT(DISTINCT t.user_id) AS n FROM mobile_face_templates t '
            'WHERE NOT EXISTS (SELECT 1 FROM face_consents c WHERE c.user_id = t.user_id AND c.withdrawn_at IS NULL)'
        )
        without = cursor.fetchone()['n']
    finally:
        cursor.close()
        connection.close()
    click.echo(f"Templates: encrypted {counts['encrypted']}, plaintext {counts['plaintext']}, unreadable {counts['unreadable']}")
    click.echo(f'Consent (notice {current_app.config.get("FACE_CONSENT_NOTICE_VERSION")}): {consented} people; '
               f'templates without active consent: {without}')


def _rewrite(label):
    from services.face.templates import reencrypt_all

    _require_key()
    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        counts = reencrypt_all(cursor)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
    click.echo(f"{label}: rewritten {counts['rewritten']}, already current {counts['already']}, unreadable {counts['unreadable']}")
    if counts['unreadable']:
        raise click.ClickException(
            f"{counts['unreadable']} template(s) could not be read with the configured key(s); they were left as they are."
        )


@face.command('encrypt-templates')
@with_appcontext
@tenant_option
def encrypt_templates():
    """Encrypt every plaintext template with FACE_TEMPLATE_KEY. Safe to re-run."""
    _rewrite('Encrypted')


@face.command('rotate-key')
@with_appcontext
@tenant_option
def rotate_key():
    """Re-encrypt every template with FACE_TEMPLATE_KEY; the old key must be in FACE_TEMPLATE_KEY_PREVIOUS."""
    if not current_app.config.get('FACE_TEMPLATE_KEY_PREVIOUS'):
        raise click.ClickException('Set FACE_TEMPLATE_KEY_PREVIOUS to the key being retired and FACE_TEMPLATE_KEY to the new one.')
    _rewrite('Rotated')
    click.echo('Remove FACE_TEMPLATE_KEY_PREVIOUS from the environment once every tenant has been rotated.')


@face.command('consent')
@click.argument('user_id', type=int)
@click.argument('action', type=click.Choice(['give', 'withdraw']))
@with_appcontext
@tenant_option
def consent(user_id, action):
    """Record consent for a person (source cli), or withdraw it and delete their templates."""
    from services.face.safeguards import record_consent, withdraw_consent

    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id FROM users WHERE id = %s', (user_id,))
        if not cursor.fetchone():
            raise click.ClickException(f'No user with id {user_id}.')
        if action == 'give':
            record_consent(cursor, user_id, source='cli')
            connection.commit()
            click.echo(f'Consent recorded for user {user_id} (notice {current_app.config.get("FACE_CONSENT_NOTICE_VERSION")}).')
        else:
            withdrawn, deleted = withdraw_consent(cursor, user_id)
            connection.commit()
            click.echo(f'Consent withdrawn for user {user_id}: {withdrawn} consent row(s) closed, {deleted} template(s) deleted.')
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@face.command('purge')
@click.option('--days', type=int, default=None, help='Retention in days (default FACE_RETENTION_DAYS).')
@click.option('--dry-run', is_flag=True, help='Report what would be deleted and change nothing.')
@with_appcontext
@tenant_option
def purge(days, dry_run):
    """Delete templates whose owner withdrew consent or was deactivated longer ago than the retention period."""
    from services.face.safeguards import purge_templates

    connection = _connection()
    cursor = connection.cursor(dictionary=True)
    try:
        counts = purge_templates(cursor, days=days)
        if dry_run:
            connection.rollback()
        else:
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
    verb = 'to delete' if dry_run else 'deleted'
    click.echo(f"Templates {verb}: withdrawn {counts['withdrawn']}, inactive users {counts['inactive_user']}, "
               f"never consented {counts['never_consented']}")
    if dry_run:
        click.echo('Dry run: nothing was deleted.')
