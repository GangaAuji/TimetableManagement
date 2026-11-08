"""Migrations against a real MariaDB server, in two scratch *_test databases.

Database A is built by `flask db upgrade`. Database B is built from the local
phpMyAdmin dump (structure only, rows skipped). Their information_schema must
match, and every foreign key must point at an existing table and column.

Credentials come from the environment or .env.test (see tests/conftest.py).
The test connects to the server without selecting a database and only ever
uses the two databases it creates and drops. It never touches MYSQL_DB itself.

Refresh the committed snapshot with UPDATE_SCHEMA_SNAPSHOT=1.
"""

import contextlib
import logging
import os
import re
from urllib.parse import quote_plus

import pytest

from core.schema.baseline import BASELINE_SNAPSHOT, MIGRATIONS_DIR, ROOT, SUPPORTED_SERVER
from core.schema.introspect import (
    compare,
    load_snapshot,
    missing_fk_targets,
    read_schema,
    server_version,
    write_snapshot,
)
from core.schema.sqlfile import read_statements

pytestmark = pytest.mark.live_db

LIVE_DUMP = ROOT / 'sql' / 'college_timetable_db.sql'
FORBIDDEN = {'college_timetable_db', 'college_timetable_db_test'}
_DEFINER = re.compile(r'\s+DEFINER=(?:`[^`]*`|\S+)@(?:`[^`]*`|\S+)', re.IGNORECASE)


def _scratch_name(base, suffix):
    name = f'{base}_{suffix}_test'
    if not name.endswith('_test') or name in FORBIDDEN:
        raise RuntimeError(f'Refusing to use database {name!r}.')
    return name


@contextlib.contextmanager
def _keep_logging():
    """Alembic's env.py runs fileConfig, which disables existing loggers."""
    manager = logging.Logger.manager
    disabled = {name: logger.disabled for name, logger in manager.loggerDict.items() if isinstance(logger, logging.Logger)}
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    try:
        yield
    finally:
        for name, logger in manager.loggerDict.items():
            if isinstance(logger, logging.Logger):
                logger.disabled = disabled.get(name, False)
        root.handlers[:] = handlers
        root.setLevel(level)


class Server:
    def __init__(self):
        import mysql.connector

        self.host = os.environ.get('MYSQL_HOST') or 'localhost'
        self.user = os.environ.get('MYSQL_USER')
        self.password = os.environ.get('MYSQL_PASSWORD') or ''
        configured = os.environ.get('MYSQL_DB') or ''
        if not self.user:
            pytest.skip('Set MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD and MYSQL_DB in .env.test.')
        if not configured.endswith('_test'):
            raise RuntimeError(f'MYSQL_DB {configured!r} is not a *_test database.')
        base = configured[: -len('_test')]
        self.a = _scratch_name(base, 'mig_a')
        self.b = _scratch_name(base, 'dump_b')
        self.connection = mysql.connector.connect(
            host=self.host, user=self.user, password=self.password, autocommit=True, charset='utf8mb4',
        )
        self.cursor = self.connection.cursor()
        self.cursor.execute('SELECT DATABASE()')
        assert self.cursor.fetchone()[0] is None
        self.version = server_version(self.cursor)

    def recreate(self, name):
        assert name in (self.a, self.b)
        self.cursor.execute(f'DROP DATABASE IF EXISTS `{name}`')
        self.cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')

    def drop(self, name):
        assert name in (self.a, self.b)
        self.cursor.execute(f'DROP DATABASE IF EXISTS `{name}`')

    def schema(self, name):
        assert name in (self.a, self.b)
        return read_schema(self.cursor, name)

    def query(self, name, sql):
        assert name in (self.a, self.b)
        self.cursor.execute(f'USE `{name}`')
        try:
            self.cursor.execute(sql)
            return self.cursor.fetchall() if self.cursor.with_rows else []
        finally:
            self.cursor.execute('USE information_schema')

    def has_table(self, name, table):
        self.cursor.execute(
            'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s', (name, table),
        )
        return self.cursor.fetchone() is not None

    def load_dump(self, name):
        assert name == self.b
        self.cursor.execute(f'USE `{name}`')
        try:
            for statement in read_statements(LIVE_DUMP):
                if statement.upper().startswith('INSERT INTO'):
                    continue
                self.cursor.execute(_DEFINER.sub('', statement, count=1))
        finally:
            self.cursor.execute('USE information_schema')

    def app(self, name):
        from flask import Flask
        from flask_migrate import Migrate
        from flask_sqlalchemy import SQLAlchemy

        from core.schema.cli import register_commands

        assert name in (self.a, self.b)
        app = Flask(f'migrations_{name}')
        app.config['SQLALCHEMY_DATABASE_URI'] = (
            f'mysql+mysqldb://{quote_plus(self.user)}:{quote_plus(self.password)}@{self.host}/{name}'
        )
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db = SQLAlchemy(app)
        Migrate(app, db, directory=str(MIGRATIONS_DIR))
        register_commands(app)
        return app, db


@pytest.fixture(scope='module')
def server():
    if not LIVE_DUMP.exists():
        pytest.skip('The phpMyAdmin dump sql/college_timetable_db.sql is not available.')
    srv = Server()
    try:
        srv.recreate(srv.a)
        srv.recreate(srv.b)
        srv.load_dump(srv.b)
        _migrate(srv, srv.a, 'upgrade', '0001_baseline')
        srv.baseline_schema = srv.schema(srv.a)
        yield srv
    finally:
        srv.drop(srv.a)
        srv.drop(srv.b)
        srv.connection.close()


def _migrate(srv, name, action, revision):
    import flask_migrate

    app, db = srv.app(name)
    with _keep_logging(), app.app_context():
        try:
            getattr(flask_migrate, action)(directory=str(MIGRATIONS_DIR), revision=revision)
        finally:
            db.get_engine().dispose()


def _adopt(srv, name, *args):
    app, db = srv.app(name)
    with _keep_logging():
        try:
            result = app.test_cli_runner().invoke(args=['db-adopt', *args])
        finally:
            with app.app_context():
                db.get_engine().dispose()
    return result


def _stamped(srv, name):
    if not srv.has_table(name, 'alembic_version'):
        return None
    return [row[0] for row in srv.query(name, 'SELECT version_num FROM alembic_version')]


def test_migrations_and_the_dump_build_the_same_schema(server):
    assert compare(server.schema(server.b), server.schema(server.a)) == []


def test_snapshot_matches_the_migrated_schema(server):
    if server.version != SUPPORTED_SERVER:
        pytest.skip(f'Snapshot is for {SUPPORTED_SERVER}; this server is {server.version}.')
    migrated = server.schema(server.a)
    if os.environ.get('UPDATE_SCHEMA_SNAPSHOT') == '1':
        write_snapshot(BASELINE_SNAPSHOT, migrated, server.version)
    snapshot = load_snapshot(BASELINE_SNAPSHOT)
    assert snapshot['server_version'] == server.version
    assert compare(snapshot['schema'], migrated) == []


def test_every_foreign_key_target_exists(server):
    schema = server.schema(server.a)
    assert schema['foreign_keys']
    assert missing_fk_targets(schema) == []


def test_db_adopt_reports_differences_and_writes_nothing(server):
    server.query(server.b, 'ALTER TABLE `roles` ADD COLUMN `adopt_probe` int(11) DEFAULT NULL')
    try:
        result = _adopt(server, server.b)
    finally:
        server.query(server.b, 'ALTER TABLE `roles` DROP COLUMN `adopt_probe`')
    assert result.exit_code == 1, result.output
    assert 'unexpected column `roles.adopt_probe`' in result.output
    assert 'Not stamped. The database was not changed.' in result.output
    assert _stamped(server, server.b) is None


def test_db_adopt_check_does_not_stamp_and_then_adopt_stamps_once(server):
    checked = _adopt(server, server.b, '--check')
    assert checked.exit_code == 0, checked.output
    assert 'identical to 0001_baseline' in checked.output
    assert _stamped(server, server.b) is None

    adopted = _adopt(server, server.b)
    assert adopted.exit_code == 0, adopted.output
    assert _stamped(server, server.b) == ['0001_baseline']

    again = _adopt(server, server.b)
    assert again.exit_code != 0
    assert 'already stamped at 0001_baseline' in again.output
    assert _stamped(server, server.b) == ['0001_baseline']


def test_catch_up_runs_on_an_adopted_database(server):
    assert _stamped(server, server.b) == ['0001_baseline']
    _migrate(server, server.b, 'upgrade', '0002_catch_up')
    assert server.has_table(server.b, 'faculty_attendance')
    assert server.has_table(server.b, 'faculty_attendance_logs')
    assert missing_fk_targets(server.schema(server.b)) == []
    assert _stamped(server, server.b) == ['0002_catch_up']


def test_catch_up_is_idempotent_and_both_downgrades_clean_up(server):
    server.query(server.a, (
        'CREATE TABLE `faculty_attendance` (`id` int(11) NOT NULL AUTO_INCREMENT, PRIMARY KEY (`id`)) '
        'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'
    ))
    _migrate(server, server.a, 'upgrade', '0002_catch_up')
    columns = server.query(server.a, 'SHOW COLUMNS FROM `faculty_attendance`')
    assert [row[0] for row in columns] == ['id']
    assert server.has_table(server.a, 'faculty_attendance_logs')

    _migrate(server, server.a, 'downgrade', '0001_baseline')
    assert compare(server.baseline_schema, server.schema(server.a)) == []

    _migrate(server, server.a, 'downgrade', 'base')
    leftover = server.schema(server.a)
    assert leftover['tables'] == {}
    assert leftover['views'] == {}
    assert _stamped(server, server.a) == []
