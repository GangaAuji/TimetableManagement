"""Schema status, /health, CLI detection, background threads, and the branding seeder. No live database."""

import threading

import click
import pytest
from click.testing import CliRunner
from flask import Flask
from flask.cli import FlaskGroup

import app_factory
from config import Config
from core.runtime import loaded_for_cli_command
from core.schema.status import database_reason, head_revision, reason_for
from data_access.branding import DEFAULT_SETTINGS
from services.branding import seed_branding_defaults

_WORKER_THREADS = {'quality-model-retrainer', 'export-queue', 'timetable-queue'}


def _worker_threads():
    return {thread.name for thread in threading.enumerate()} & _WORKER_THREADS


def test_reason_names_the_revision_and_the_fix():
    head = head_revision()
    assert reason_for([head]) is None
    behind = reason_for(['0002_catch_up'])
    assert '0002_catch_up' in behind and head in behind and '`flask db upgrade`' in behind
    assert 'no migration stamp' in reason_for([])
    assert 'does not know' in reason_for(['9999_from_elsewhere'])
    assert 'several' in reason_for(['0002_catch_up', head])


class _Cursor:
    def __init__(self, has_table, versions):
        self.has_table = has_table
        self.versions = versions
        self.result = []

    def execute(self, sql, params=None):
        if 'information_schema' in sql:
            self.result = [(1,)] if self.has_table else []
        else:
            self.result = [(version,) for version in self.versions]

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result

    def close(self):
        pass


class _Connection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_database_reason_reads_the_stamp_and_closes_the_connection():
    connection = _Connection(_Cursor(True, [head_revision()]))
    assert database_reason(lambda: connection) is None
    assert connection.closed
    assert 'no migration stamp' in database_reason(lambda: _Connection(_Cursor(False, [])))
    assert '0003_security_schema' in database_reason(lambda: _Connection(_Cursor(True, ['0003_security_schema'])))

    def refuse():
        raise ConnectionRefusedError('password=secret')

    reason = database_reason(refuse)
    assert reason == 'The database is unreachable: ConnectionRefusedError.'


def test_cli_detection_counts_run_as_serving():
    assert loaded_for_cli_command() is False
    group = click.Group('flask')
    with click.Context(group, info_name='flask') as parent:
        assert loaded_for_cli_command() is True
        with click.Context(click.Command('db-adopt'), info_name='db-adopt', parent=parent):
            assert loaded_for_cli_command() is True
        with click.Context(click.Command('run'), info_name='run', parent=parent):
            assert loaded_for_cli_command() is False


@pytest.mark.parametrize('args', [['routes'], ['db-adopt', '--help'], ['seed', '--help'], ['admin', '--help']])
def test_flask_cli_commands_start_no_background_threads(monkeypatch, args):
    monkeypatch.setattr(Config, 'DEBUG', False)
    monkeypatch.setattr(Config, 'QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES', 5)
    before = _worker_threads()
    created = []

    def factory():
        app = app_factory.create_app()
        created.append(app)
        return app

    cli = FlaskGroup(create_app=factory, load_dotenv=False)
    result = CliRunner().invoke(cli, args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert created and all(app.config['CLI_COMMAND'] for app in created)
    from services import export_jobs, timetable_jobs

    for app in created:
        export_jobs.ensure_worker(app)
        timetable_jobs.ensure_worker(app)
    assert _worker_threads() == before


def test_create_app_outside_the_cli_is_not_a_cli_command():
    app = app_factory.create_app()
    assert app.config['CLI_COMMAND'] is False


class _Thread:
    started = []

    def __init__(self, target=None, name=None, daemon=None, args=()):
        self.name = name

    def start(self):
        _Thread.started.append(self.name)


@pytest.mark.parametrize('minutes, expected', [(0, []), (-1, []), (5, ['quality-model-retrainer'])])
def test_retrain_interval_zero_disables_the_retrainer(monkeypatch, minutes, expected):
    monkeypatch.setattr(app_factory.threading, 'Thread', _Thread)
    _Thread.started = []
    app = Flask('retrainer_probe')
    app.config['QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES'] = minutes
    app_factory._start_quality_model_retrainer(app)
    assert _Thread.started == expected


def test_health_returns_503_with_the_reason_until_the_database_is_at_head(monkeypatch):
    app = app_factory.create_app()
    client = app.test_client()
    calls = []

    def behind(connect):
        calls.append(connect)
        return 'The database is at 0002_catch_up; the code expects 0004_rate_limit_collation. Run `flask db upgrade`.'

    monkeypatch.setattr(app_factory, 'database_reason', behind)
    app.config['REQUIRE_MIGRATED_DB'] = False
    assert client.get('/health').status_code == 200
    assert calls == []

    app.config['REQUIRE_MIGRATED_DB'] = True
    response = client.get('/health')
    assert response.status_code == 503
    assert response.get_json()['status'] == 'unavailable'
    assert 'flask db upgrade' in response.get_json()['reason']

    monkeypatch.setattr(app_factory, 'database_reason', lambda connect: None)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'healthy'


def test_startup_logs_a_clear_error_when_the_database_is_behind(monkeypatch):
    records = []

    class _Collect(app_factory.logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collect(level=app_factory.logging.ERROR)
    app_logger = app_factory.logging.getLogger('app')
    app_logger.addHandler(handler)
    monkeypatch.setattr(Config, 'REQUIRE_MIGRATED_DB', True)
    monkeypatch.setattr(app_factory, 'database_reason', lambda connect: 'The database is at 0002_catch_up.')
    try:
        app_factory.create_app()
    finally:
        app_logger.removeHandler(handler)
    messages = [record.getMessage() for record in records]
    assert any('Database schema check failed: The database is at 0002_catch_up.' in text for text in messages)


class _SeedCursor:
    def __init__(self):
        self.keys = set()
        self.rowcount = -1

    def execute(self, sql, params):
        assert sql.startswith('INSERT IGNORE INTO branding_settings')
        key = params[0]
        self.rowcount = 0 if key in self.keys else 1
        self.keys.add(key)


def test_branding_seed_adds_missing_defaults_and_never_overwrites():
    cursor = _SeedCursor()
    assert len(DEFAULT_SETTINGS) == 22
    assert seed_branding_defaults(cursor) == 22
    assert seed_branding_defaults(cursor) == 0
