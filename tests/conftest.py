"""Test setup. Runs before any application module is imported.

Tests never read the project `.env`. Database settings come only from
`.env.test` next to it: MYSQL_* values inherited from the shell are removed
first. The database name must match config.testing.test_database_problem
(college_timetable_ci_*_test, never college_timetable_db or
college_timetable_db_test) or the run stops before collecting anything.

Tests marked `live_db` call `create_app()` and open real connections. They are
skipped unless pytest is run with `--live-db`. A test that uses the shared
`test_database` (directly or through `db`, `app`, `client`, or `factory`) is
marked `live_db` automatically.

Live fixtures: `test_database` rebuilds MYSQL_DB once per session with
`flask db upgrade` and the seeders, then captures every table. `db` restores
the tables a test changed. `client` is a test client on a TestingConfig app
with rate limits reset; `factory` creates users and an academic setup.
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import dotenv
import pytest

ROOT = Path(__file__).resolve().parent.parent
TEST_ENV_FILE = ROOT / '.env.test'
DATABASE_SETTINGS = ('MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DB')

_CONFIG_IMPORTED_EARLY = 'config' in sys.modules or 'config.base' in sys.modules

_original_load_dotenv = dotenv.load_dotenv


def _load_test_env_only(*_args, **_kwargs):
    """Stand-in for `load_dotenv`. `config/base.py` would otherwise load `.env`."""
    if TEST_ENV_FILE.is_file():
        return _original_load_dotenv(TEST_ENV_FILE, override=True)
    return False


for _name in DATABASE_SETTINGS:
    os.environ.pop(_name, None)
dotenv.load_dotenv = _load_test_env_only
_TEST_ENV_LOADED = _load_test_env_only()

os.environ['APP_ENV'] = 'testing'
os.environ['QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES'] = '0'
os.environ.setdefault('REQUIRE_MIGRATED_DB', 'false')
os.environ.setdefault('LOG_FILE', os.path.join(tempfile.gettempdir(), 'timetable-tests', 'app.log'))
os.environ.setdefault('FACE_DETECT_CONF_THRESHOLD', '0.5')
os.environ.setdefault('FACE_DETECT_IOU_THRESHOLD', '0.45')
os.environ.setdefault('FACE_TEMPLATE_MIN_QUALITY', '0.55')


def _database_problem():
    if _CONFIG_IMPORTED_EARLY:
        return 'config was imported before tests/conftest.py, so it may have read .env.'
    if not _TEST_ENV_LOADED:
        return f'{TEST_ENV_FILE.name} is missing or empty.'

    from config import Config
    from config.testing import TestingConfig, test_database_problem

    problem = test_database_problem(os.environ.get('MYSQL_DB'))
    if problem:
        return f'MYSQL_DB in {TEST_ENV_FILE.name}: {problem}'
    if Config is not TestingConfig:
        return f'config selected {Config.__name__}, not TestingConfig.'
    if Config.MYSQL_DB != os.environ['MYSQL_DB']:
        return 'TestingConfig.MYSQL_DB does not match .env.test.'
    return None


def pytest_addoption(parser):
    parser.addoption(
        '--live-db',
        action='store_true',
        default=False,
        help='Run tests marked live_db. They connect to the configured *_test database.',
    )


def pytest_configure(config):
    problem = _database_problem()
    if problem:
        pytest.exit(
            f'Refusing to run tests: {problem} '
            f'Set MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD and MYSQL_DB in {TEST_ENV_FILE.name}.',
            returncode=pytest.ExitCode.USAGE_ERROR,
        )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if 'test_database' in getattr(item, 'fixturenames', ()):
            item.add_marker(pytest.mark.live_db)
    if config.getoption('--live-db'):
        return
    skip_live = pytest.mark.skip(reason='needs a live *_test database; run with --live-db')
    for item in items:
        if 'live_db' in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(scope='session')
def test_database():
    """MYSQL_DB rebuilt once: upgrade to head, run the seeders, capture every table."""
    from seeders import run_seeders
    from tests.integration.isolation import Baseline
    from tests.integration.live_helpers import (
        configured_database,
        database_connection,
        migrate,
        recreate,
        server_connection,
    )

    name = configured_database()
    server = server_connection()
    cursor = server.cursor()
    try:
        recreate(cursor, name)
        migrate(name, 'upgrade', 'head')
    finally:
        cursor.close()
        server.close()
    connection = database_connection(name)
    cursor = connection.cursor()
    try:
        run_seeders(cursor)
        connection.commit()
    finally:
        cursor.close()
    baseline = Baseline.capture(connection)
    yield SimpleNamespace(name=name, connection=connection, baseline=baseline)
    connection.close()


@pytest.fixture
def db(test_database):
    """The shared test database. Tables the test changed are restored afterwards."""
    connection = test_database.connection
    yield connection
    connection.rollback()
    test_database.baseline.restore(connection)


@pytest.fixture(scope='session')
def app(test_database, tmp_path_factory):
    from app import create_app
    from config.testing import TestingConfig

    class HarnessConfig(TestingConfig):
        UPLOAD_FOLDER = str(tmp_path_factory.mktemp('uploads'))
        PROPAGATE_EXCEPTIONS = False

    return create_app(HarnessConfig)


@pytest.fixture(scope='session')
def make_app(test_database, tmp_path_factory):
    """Build an app on the test database with some TestingConfig settings changed."""
    from app import create_app
    from config.testing import TestingConfig

    def build(**settings):
        values = {'UPLOAD_FOLDER': str(tmp_path_factory.mktemp('uploads')), 'PROPAGATE_EXCEPTIONS': False}
        values.update(settings)
        return create_app(type('CustomConfig', (TestingConfig,), values))

    return build


@pytest.fixture(scope='session')
def default_lock_wait_app(make_app):
    """The server's default innodb_lock_wait_timeout instead of the 2 s test setting."""
    return make_app(MYSQL_INIT_COMMAND=None)


@pytest.fixture
def reset_rate_limits(db):
    """Empty the shared and in-process rate-limit counters. Call the returned function to reset again."""
    from security import rate_limit

    def reset():
        cursor = db.cursor()
        try:
            cursor.execute('DELETE FROM rate_limit_counters')
            db.commit()
        finally:
            cursor.close()
        with rate_limit._LOCK:
            rate_limit._HITS.clear()

    reset()
    return reset


@pytest.fixture
def client(app, db, reset_rate_limits):
    return app.test_client()


@pytest.fixture
def factory(db):
    from tests.factories import Factory

    return Factory(db)
