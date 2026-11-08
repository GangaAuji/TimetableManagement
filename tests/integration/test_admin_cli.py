"""The install order on a scratch *_test database: db upgrade, seed run, create-superadmin, then log in.

The app is built with create_app(config) pointed at that database. The tests
run in order and share it; it is dropped at the end.
"""

import json

import pytest

from config.testing import TestingConfig
from security.passwords import is_password_hash
from tests.integration.live_helpers import (
    database_connection,
    drop,
    migrate,
    recreate,
    scratch_name,
    server_connection,
)
from tests.integration.seed_helpers import default_pairs, mapping

pytestmark = pytest.mark.live_db

PASSWORD = 'Correct-Horse-42'
SECOND_PASSWORD = 'Another-Horse-43'
_HASH_PREFIXES = ('pbkdf2:', 'scrypt:', 'argon2:')


@pytest.fixture(scope='module')
def database_name():
    return scratch_name('admin_cli')


@pytest.fixture(scope='module')
def database(database_name):
    server = server_connection()
    cursor = server.cursor()
    try:
        recreate(cursor, database_name)
        migrate(database_name, 'upgrade', 'head')
        connection = database_connection(database_name)
        yield connection
        connection.close()
    finally:
        drop(cursor, database_name)
        server.close()


@pytest.fixture(scope='module')
def app(database, database_name, tmp_path_factory):
    from app import create_app

    class CliConfig(TestingConfig):
        MYSQL_DB = database_name
        WTF_CSRF_ENABLED = False
        PROPAGATE_EXCEPTIONS = False
        UPLOAD_FOLDER = str(tmp_path_factory.mktemp('uploads'))

    return create_app(CliConfig)


@pytest.fixture
def cli(app, monkeypatch):
    monkeypatch.delenv('SUPERADMIN_PASSWORD', raising=False)
    return app.test_cli_runner()


def _rows(connection, statement, params=()):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(statement, params)
        rows = cursor.fetchall()
        connection.commit()
        return rows
    finally:
        cursor.close()


def _no_secret(output, *passwords):
    for password in passwords:
        assert password not in output
    assert not any(prefix in output for prefix in _HASH_PREFIXES)


def test_create_superadmin_before_seeding_points_to_seed_run(cli):
    result = cli.invoke(args=['admin', 'create-superadmin', 'root', 'root@example.org'], env={'SUPERADMIN_PASSWORD': PASSWORD})
    assert result.exit_code != 0
    assert '`flask seed run`' in result.output
    _no_secret(result.output, PASSWORD)


def test_seed_run_on_a_fresh_database_grants_every_default(cli, database):
    result = cli.invoke(args=['seed', 'run'])
    assert result.exit_code == 0, result.output
    assert 'roles: 5 added, 0 already present.' in result.output
    assert f'role_permissions: {len(default_pairs())} granted, 0 already mapped' in result.output
    assert 'branding_settings: 22 added, 0 already present.' in result.output
    assert '--apply-role-defaults' not in result.output
    assert mapping(database) == default_pairs()

    again = cli.invoke(args=['seed', 'run', '--apply-role-defaults'])
    assert again.exit_code == 0, again.output
    assert 'role_permissions: 0 granted' in again.output


def test_create_superadmin_from_the_environment(cli, database):
    result = cli.invoke(args=['admin', 'create-superadmin', 'root', 'root@example.org'], env={'SUPERADMIN_PASSWORD': PASSWORD})
    assert result.exit_code == 0, result.output
    assert "Created Super Admin 'root'" in result.output
    _no_secret(result.output, PASSWORD)

    [user] = _rows(database, "SELECT id, password, role, email, status FROM users WHERE username = 'root'")
    assert user['role'] == 'Super Admin' and user['status'] == 'active' and user['email'] == 'root@example.org'
    assert is_password_hash(user['password']) and PASSWORD not in user['password']

    [activity] = _rows(database, 'SELECT activity_type, user_id FROM user_activity_log WHERE user_id = %s', (user['id'],))
    assert activity['activity_type'] == 'superadmin_created'
    [audit] = _rows(database, "SELECT action, entity_id, new_values FROM audit_logs WHERE action = 'superadmin_created'")
    assert audit['entity_id'] == user['id']
    assert json.loads(audit['new_values']) == {
        'username': 'root', 'email': 'root@example.org', 'role': 'Super Admin', 'forced': False,
    }
    assert PASSWORD not in audit['new_values'] and user['password'] not in audit['new_values']


def test_the_new_account_can_log_in_at_admin_login(app):
    client = app.test_client()
    wrong = client.post('/admin/login', data={'username': 'root', 'password': 'not-the-password'})
    assert wrong.status_code != 302
    with client.session_transaction() as session:
        assert 'user_id' not in session

    response = client.post('/admin/login', data={'username': 'root', 'password': PASSWORD})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session['username'] == 'root' and session['role'] == 'Super Admin'


def test_a_second_superadmin_needs_force(cli, database):
    refused = cli.invoke(args=['admin', 'create-superadmin', 'deputy', 'deputy@example.org'], env={'SUPERADMIN_PASSWORD': SECOND_PASSWORD})
    assert refused.exit_code != 0 and '--force' in refused.output
    _no_secret(refused.output, SECOND_PASSWORD)

    forced = cli.invoke(
        args=['admin', 'create-superadmin', 'deputy', 'deputy@example.org', '--force', '--password-stdin'],
        input=SECOND_PASSWORD + '\n',
    )
    assert forced.exit_code == 0, forced.output
    _no_secret(forced.output, SECOND_PASSWORD)
    assert len(_rows(database, "SELECT id FROM users WHERE role = 'Super Admin'")) == 2
    [audit] = _rows(database, "SELECT new_values FROM audit_logs WHERE username = 'deputy'")
    assert json.loads(audit['new_values'])['forced'] is True


def test_taken_names_short_passwords_and_missing_passwords_are_refused(cli, database):
    cases = [
        (['root', 'other@example.org'], {'input': PASSWORD + '\n'}, 'already taken'),
        (['third', 'ROOT@example.org'], {'input': PASSWORD + '\n'}, 'already used'),
        (['third', 'third@example.org'], {'input': 'short\n'}, '8 to 128'),
        (['bad name', 'third@example.org'], {'input': PASSWORD + '\n'}, 'username'),
        (['third', 'not-an-email'], {'input': PASSWORD + '\n'}, 'email'),
    ]
    for arguments, extra, message in cases:
        result = cli.invoke(args=['admin', 'create-superadmin', *arguments, '--force', '--password-stdin'], **extra)
        assert result.exit_code != 0 and message in result.output, (arguments, result.output)
        _no_secret(result.output, PASSWORD)

    missing = cli.invoke(args=['admin', 'create-superadmin', 'third', 'third@example.org', '--force'])
    assert missing.exit_code != 0 and 'No password given' in missing.output
    assert _rows(database, "SELECT id FROM users WHERE username = 'third'") == []
