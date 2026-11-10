"""Two colleges on one app: `flask tenant create` provisions each, requests are routed by hostname, nothing crosses.

Uses three scratch *_test databases (a registry and two tenants). They are
dropped at the end. The shared MYSQL_DB test database is not touched.
"""

import pytest

from config.testing import TestingConfig
from core.schema.status import head_revision
from tests.integration.live_helpers import (
    database_connection,
    drop,
    recreate,
    scratch_name,
    server_connection,
)

pytestmark = pytest.mark.live_db

ALPHA_PASSWORD = 'Alpha-Horse-42'
BETA_PASSWORD = 'Beta-Horse-43'
ALPHA_HOST = 'alpha.college.test'
BETA_HOST = 'beta.college.test'


@pytest.fixture(scope='module')
def names():
    return {
        'registry': scratch_name('tenant_registry'),
        'alpha': scratch_name('tenant_alpha'),
        'beta': scratch_name('tenant_beta'),
    }


@pytest.fixture(scope='module')
def databases(names):
    server = server_connection()
    cursor = server.cursor()
    try:
        recreate(cursor, names['registry'])
        drop(cursor, names['alpha'])
        drop(cursor, names['beta'])
        yield names
    finally:
        for name in names.values():
            drop(cursor, name)
        cursor.close()
        server.close()


@pytest.fixture(scope='module')
def app(databases, tmp_path_factory):
    from app import create_app

    class RegistryConfig(TestingConfig):
        TENANT_REGISTRY_DB = databases['registry']
        TENANT_CACHE_SECONDS = 0
        WTF_CSRF_ENABLED = False
        PROPAGATE_EXCEPTIONS = False
        UPLOAD_FOLDER = str(tmp_path_factory.mktemp('uploads'))

    return create_app(RegistryConfig)


@pytest.fixture(scope='module')
def cli(app):
    return app.test_cli_runner()


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


def _rows(name, statement, params=()):
    connection = database_connection(name)
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(statement, params)
            return cursor.fetchall()
        finally:
            cursor.close()
            connection.rollback()
    finally:
        connection.close()


def _create(cli, slug, hostname, db_name, username, password):
    result = cli.invoke(
        args=[
            'tenant', 'create', slug, '--hostname', hostname, '--database', db_name,
            '--admin-username', username, '--admin-email', f'{username}@college.test', '--password-stdin',
        ],
        input=password + '\n',
    )
    assert result.exit_code == 0, result.output
    assert password not in result.output
    assert f'Tenant {slug} is active at {hostname}' in result.output
    return result


def test_tenant_create_provisions_two_colleges(databases, cli):
    init = cli.invoke(args=['tenant', 'init'])
    assert init.exit_code == 0, init.output

    _create(cli, 'alpha', ALPHA_HOST, databases['alpha'], 'alpha_admin', ALPHA_PASSWORD)
    _create(cli, 'beta', BETA_HOST, databases['beta'], 'beta_admin', BETA_PASSWORD)

    head = head_revision()
    for name in ('alpha', 'beta'):
        assert _rows(databases[name], 'SELECT version_num FROM alembic_version') == [{'version_num': head}]
        assert _rows(databases[name], "SELECT COUNT(*) AS n FROM roles WHERE name = 'Super Admin'")[0]['n'] == 1
    assert [r['username'] for r in _rows(databases['alpha'], 'SELECT username FROM users')] == ['alpha_admin']
    assert [r['username'] for r in _rows(databases['beta'], 'SELECT username FROM users')] == ['beta_admin']

    listed = cli.invoke(args=['tenant', 'list'])
    assert listed.exit_code == 0, listed.output
    assert f'alpha\t{ALPHA_HOST}\t{databases["alpha"]}\tactive\t{head}' in listed.output
    assert f'beta\t{BETA_HOST}\t{databases["beta"]}\tactive\t{head}' in listed.output


def test_tenant_create_refuses_duplicates_and_existing_databases(databases, cli):
    again = cli.invoke(args=['tenant', 'create', 'alpha', '--hostname', 'other.college.test', '--database', scratch_name('tenant_unused')])
    assert again.exit_code != 0 and 'already exists: alpha' in again.output
    same_host = cli.invoke(args=['tenant', 'create', 'gamma', '--hostname', BETA_HOST, '--database', scratch_name('tenant_unused')])
    assert same_host.exit_code != 0 and 'already exists: beta' in same_host.output
    same_db = cli.invoke(args=['tenant', 'create', 'gamma', '--hostname', 'gamma.college.test', '--database', databases['registry']])
    assert same_db.exit_code != 0 and 'already exists' in same_db.output
    assert len(_rows(databases['registry'], 'SELECT slug FROM tenants')) == 2


def test_requests_are_routed_by_hostname(databases, client):
    alpha = client.get('/api/session', base_url=f'http://{ALPHA_HOST}')
    assert alpha.status_code == 200 and alpha.get_json()['data']['authenticated'] is False

    unknown_api = client.get('/api/session', base_url='http://nobody.college.test')
    assert unknown_api.status_code == 404
    assert unknown_api.get_json()['error']['code'] == 'unknown_tenant'
    unknown_page = client.get('/', base_url='http://nobody.college.test')
    assert unknown_page.status_code == 404

    health = client.get('/health', base_url='http://nobody.college.test')
    assert health.status_code == 200, health.get_data(as_text=True)
    assert health.get_json()['tenancy'] == 'registry'


def test_sign_in_on_one_college_is_not_valid_on_another(databases, client):
    response = client.post(
        '/admin/login',
        data={'username': 'alpha_admin', 'password': ALPHA_PASSWORD},
        base_url=f'http://{ALPHA_HOST}',
    )
    assert response.status_code in (200, 302), response.get_data(as_text=True)[:200]
    cookie = response.headers.get('Set-Cookie', '')
    assert cookie.startswith('session=')
    session_cookie = cookie.split(';', 1)[0]

    here = client.get('/api/session', base_url=f'http://{ALPHA_HOST}')
    assert here.get_json()['data']['authenticated'] is True
    assert here.get_json()['data']['username'] == 'alpha_admin'

    # The same cookie replayed against the other college is cleared, not honoured.
    there = client.get('/api/session', base_url=f'http://{BETA_HOST}', headers={'Cookie': session_cookie})
    assert there.status_code == 200
    assert there.get_json()['data']['authenticated'] is False

    # Alpha's credentials do not exist in beta's database.
    wrong = client.post(
        '/admin/login',
        data={'username': 'alpha_admin', 'password': ALPHA_PASSWORD},
        base_url=f'http://{BETA_HOST}',
    )
    assert wrong.status_code in (200, 302, 401)
    assert client.get('/api/session', base_url=f'http://{BETA_HOST}').get_json()['data']['authenticated'] is False

    # Only alpha's database recorded the sign-in.
    assert _rows(databases['alpha'], 'SELECT COUNT(*) AS n FROM user_sessions')[0]['n'] >= 1
    assert _rows(databases['beta'], 'SELECT COUNT(*) AS n FROM user_sessions')[0]['n'] == 0


def test_suspended_college_answers_503(databases, cli, client):
    suspend = cli.invoke(args=['tenant', 'set-status', 'beta', 'suspended'])
    assert suspend.exit_code == 0, suspend.output
    try:
        response = client.get('/api/session', base_url=f'http://{BETA_HOST}')
        assert response.status_code == 503
        assert response.get_json()['error']['code'] == 'tenant_unavailable'
        assert client.get('/api/session', base_url=f'http://{ALPHA_HOST}').status_code == 200
    finally:
        restore = cli.invoke(args=['tenant', 'set-status', 'beta', 'active'])
        assert restore.exit_code == 0, restore.output


def test_commands_need_and_honour_tenant(databases, cli):
    missing = cli.invoke(args=['seed', 'run'])
    assert missing.exit_code != 0 and 'Pass --tenant SLUG' in missing.output
    unknown = cli.invoke(args=['seed', 'run', '--tenant', 'nobody'])
    assert unknown.exit_code != 0 and "No tenant with slug 'nobody'" in unknown.output

    seeded = cli.invoke(args=['seed', 'run', '--tenant', 'beta'])
    assert seeded.exit_code == 0, seeded.output
    assert f'Tenant beta (database `{databases["beta"]}`)' in seeded.output

    closed = cli.invoke(args=['attendance', 'close-day', '--tenant', 'alpha', '--dry-run'])
    assert closed.exit_code == 0, closed.output
    assert 'Dry run: nothing was written.' in closed.output

    upgraded = cli.invoke(args=['tenant', 'upgrade', '--all'])
    assert upgraded.exit_code == 0, upgraded.output
    assert f'alpha: {head_revision()}' in upgraded.output and f'beta: {head_revision()}' in upgraded.output

    assert 'db' not in cli.app.cli.commands, 'flask db has no single database to act on with a registry'


def test_workers_run_once_per_active_tenant(app, databases, cli):
    from core.tenancy import tenant_context
    from services.attendance_jobs import run_all

    outcome = run_all(app)
    assert sorted(outcome) == ['alpha', 'beta']
    assert all(len(results) == 7 for results in outcome.values())

    from core.tenancy.registry import Registry

    alpha = Registry.from_config(app.config).by_slug('alpha')
    with tenant_context(app, alpha):
        from extensions import get_db_connection

        connection = get_db_connection()
        try:
            cursor = connection.cursor()
            cursor.execute('SELECT DATABASE()')
            assert cursor.fetchone()[0] == databases['alpha']
            cursor.close()
        finally:
            connection.close()

    with app.app_context():
        from extensions import get_db_connection

        with pytest.raises(RuntimeError, match='No tenant is bound'):
            get_db_connection()


def test_forget_keeps_the_database(databases, cli):
    gone = cli.invoke(args=['tenant', 'forget', 'beta', '--yes'])
    assert gone.exit_code == 0, gone.output
    assert 'was left in place' in gone.output
    assert [r['slug'] for r in _rows(databases['registry'], 'SELECT slug FROM tenants')] == ['alpha']
    assert _rows(databases['beta'], 'SELECT COUNT(*) AS n FROM users')[0]['n'] == 1
