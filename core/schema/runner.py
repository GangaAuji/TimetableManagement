"""Run an Alembic action (upgrade, downgrade, stamp, current) against any database.

Flask-Migrate reads the engine from the current app, whose URI is fixed when
the app is created. `flask tenant create` and the live tests need to migrate a
database that is not the one the app was created for, so this builds a
throw-away Flask app on the given connection settings and runs the action
through it. The migrations folder and its env.py are the project's own.
"""

import contextlib
import logging
from urllib.parse import quote_plus

from core.schema.baseline import MIGRATIONS_DIR


def database_uri(settings):
    """SQLAlchemy URI for the mysql-connector style settings dict (host, user, password, database)."""
    user = quote_plus(settings.get('user') or '')
    password = quote_plus(settings.get('password') or '')
    host = settings.get('host') or 'localhost'
    name = settings.get('database') or ''
    return f'mysql+mysqldb://{user}:{password}@{host}/{name}'


@contextlib.contextmanager
def keep_logging():
    """Alembic's env.py runs fileConfig, which disables existing loggers and replaces the root handlers."""
    manager = logging.Logger.manager
    disabled = {
        name: logger.disabled
        for name, logger in manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    }
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


def run_alembic(settings, action, revision=None, **options):
    """Run flask_migrate.<action> on the database in `settings`.

    A failing revision prints its error and raises SystemExit(1): that is
    Flask-Migrate's catch_errors wrapper, which callers must expect.
    """
    import flask_migrate
    from flask import Flask
    from flask_migrate import Migrate
    from flask_sqlalchemy import SQLAlchemy

    name = settings.get('database') or ''
    app = Flask(f'migrations_{name}')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri(settings)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)
    Migrate(app, db, directory=str(MIGRATIONS_DIR))
    command = getattr(flask_migrate, action)
    arguments = {'directory': str(MIGRATIONS_DIR), **options}
    if revision is not None:
        arguments['revision'] = revision
    with keep_logging(), app.app_context():
        try:
            command(**arguments)
        finally:
            db.get_engine().dispose()
