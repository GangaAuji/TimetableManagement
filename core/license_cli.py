"""Inspect and issue installation licenses.

``flask license inspect`` reads the file configured by ``LICENSE_FILE``.
``flask license issue`` signs a new file with the vendor private key. That key
is not on a college server. The command checks that the private key matches
the public key embedded in the application (or ``LICENSE_PUBLIC_KEY`` in tests).
"""

import base64
import json

import click
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import current_app
from flask.cli import with_appcontext

from core.license import PUBLIC_KEY_B64, sign_document


def _load_private(path, config):
    try:
        with open(path, 'rb') as handle:
            private = serialization.load_pem_private_key(handle.read(), password=None)
    except (OSError, ValueError) as exc:
        raise click.ClickException(f'The private key could not be read ({exc.__class__.__name__}).') from exc
    if not isinstance(private, Ed25519PrivateKey):
        raise click.ClickException('The private key must be an Ed25519 key.')
    public = base64.b64encode(
        private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode('ascii')
    expected = str(config.get('LICENSE_PUBLIC_KEY') or PUBLIC_KEY_B64).strip()
    if public != expected:
        raise click.ClickException('That private key does not match the public key in this application.')
    return private


@click.group('license')
def license_group():
    """The offline license for this installation."""


@license_group.command('inspect')
@with_appcontext
def license_inspect():
    """Print the license status. The signature is not printed."""
    from core.license import evaluate

    status = dict(evaluate(current_app.config))
    click.echo(json.dumps(status, indent=2, sort_keys=True))


@license_group.command('issue')
@click.option('--private-key', required=True, type=click.Path(exists=True, dir_okay=False))
@click.option('--customer', required=True)
@click.option('--edition', default='campus', show_default=True)
@click.option('--expires', default=None, help='YYYY-MM-DD, or omit for a license that does not expire.')
@click.option('--max-students', default=None, type=int)
@click.option('--max-institutions', default=None, type=int)
@click.option('--capability', 'capabilities', multiple=True, help='Repeat for each capability this edition includes.')
@click.option('--out', 'destination', required=True, type=click.Path(dir_okay=False))
@with_appcontext
def license_issue(private_key, customer, edition, expires, max_students, max_institutions, capabilities, destination):
    """Write a signed license file. The private key is read and not copied into the file."""
    private = _load_private(private_key, current_app.config)
    try:
        document = sign_document(
            {
                'customer': customer,
                'edition': edition,
                'expires': expires,
                'max_students': max_students,
                'max_institutions': max_institutions,
                'capabilities': list(capabilities),
            },
            private,
        )
    except ValueError as exc:
        raise click.ClickException(f'The license fields could not be accepted ({exc}).') from exc
    with open(destination, 'w', encoding='utf-8') as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write('\n')
    click.echo(f'Wrote a license for {document["customer"]} ({document["edition"]}) to {destination}.')
