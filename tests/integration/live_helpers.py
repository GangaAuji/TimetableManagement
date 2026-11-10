"""Shared pieces for live_db tests: a server connection, *_test database names, and Alembic runs."""

import os
import re

import pytest

from config.testing import test_database_problem
from core.schema.runner import keep_logging, run_alembic  # noqa: F401  (keep_logging is used by tests)

_DEFINER = re.compile(r'\s+DEFINER=(?:`[^`]*`|\S+)@(?:`[^`]*`|\S+)', re.IGNORECASE)


def without_definer(statement):
    return _DEFINER.sub('', statement, count=1)


def checked_name(name):
    problem = test_database_problem(name)
    if problem:
        raise RuntimeError(f'Refusing to use database: {problem}')
    return name


def configured_database():
    return checked_name(os.environ.get('MYSQL_DB') or '')


def scratch_name(suffix):
    return checked_name(f'{configured_database()[: -len("_test")]}_{suffix}_test')


def credentials():
    user = os.environ.get('MYSQL_USER')
    if not user:
        pytest.skip('Set MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD and MYSQL_DB in .env.test.')
    return os.environ.get('MYSQL_HOST') or 'localhost', user, os.environ.get('MYSQL_PASSWORD') or ''


def server_connection():
    """A connection with no database selected."""
    import mysql.connector

    host, user, password = credentials()
    return mysql.connector.connect(host=host, user=user, password=password, autocommit=True, charset='utf8mb4')


def database_connection(name):
    """A transactional connection to one *_test database."""
    import mysql.connector

    host, user, password = credentials()
    return mysql.connector.connect(
        host=host, user=user, password=password, database=checked_name(name), autocommit=False, charset='utf8mb4',
    )


def recreate(cursor, name):
    checked_name(name)
    cursor.execute(f'DROP DATABASE IF EXISTS `{name}`')
    cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')


def drop(cursor, name):
    checked_name(name)
    cursor.execute(f'DROP DATABASE IF EXISTS `{name}`')


def migrate(name, action, revision):
    """Run flask_migrate.<action> on database `name` through core.schema.runner."""
    host, user, password = credentials()
    run_alembic({'host': host, 'user': user, 'password': password, 'database': checked_name(name)}, action, revision)


def stamped(cursor, name):
    cursor.execute(
        'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s', (name, 'alembic_version'),
    )
    if cursor.fetchone() is None:
        return None
    cursor.execute(f'SELECT version_num FROM `{checked_name(name)}`.alembic_version')
    return [row[0] for row in cursor.fetchall()]
