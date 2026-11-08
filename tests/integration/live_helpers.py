"""Shared pieces for live_db tests: a server connection, *_test database names, and Alembic runs."""

import contextlib
import logging
import os
import re
from urllib.parse import quote_plus

import pytest

from config.testing import test_database_problem
from core.schema.baseline import MIGRATIONS_DIR

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


@contextlib.contextmanager
def keep_logging():
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


def migrate(name, action, revision):
    """Run flask_migrate.<action> on database `name` through a bare Flask app."""
    import flask_migrate
    from flask import Flask
    from flask_migrate import Migrate
    from flask_sqlalchemy import SQLAlchemy

    host, user, password = credentials()
    app = Flask(f'migrations_{checked_name(name)}')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+mysqldb://{quote_plus(user)}:{quote_plus(password)}@{host}/{name}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)
    Migrate(app, db, directory=str(MIGRATIONS_DIR))
    with keep_logging(), app.app_context():
        try:
            getattr(flask_migrate, action)(directory=str(MIGRATIONS_DIR), revision=revision)
        finally:
            db.get_engine().dispose()


def stamped(cursor, name):
    cursor.execute(
        'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s', (name, 'alembic_version'),
    )
    if cursor.fetchone() is None:
        return None
    cursor.execute(f'SELECT version_num FROM `{checked_name(name)}`.alembic_version')
    return [row[0] for row in cursor.fetchall()]
