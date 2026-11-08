from urllib.parse import quote_plus

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from models.db import close_db, get_db, get_db_connection

csrf = CSRFProtect()
db = SQLAlchemy()
migrate = Migrate()


def _install_migration_context_defaults():
    """Keep flask db commands working on Flask 2.0.

    The db command group stores its directory on the app context, and Flask
    2.0 closes that context before the subcommand runs.
    """
    from flask import has_request_context
    from flask.ctx import AppContext

    if getattr(AppContext.push, '_migration_defaults', False):
        return
    original = AppContext.push

    def push(self):
        original(self)
        if has_request_context():
            return
        if getattr(self.g, 'directory', None) is None:
            self.g.directory = 'migrations'
        if getattr(self.g, 'x_arg', None) is None:
            self.g.x_arg = ()

    push._migration_defaults = True
    AppContext.push = push


def configure_migrations(app):
    """Attach Flask-Migrate without using it for request queries. Reads the app's own config."""
    user = quote_plus(app.config.get('MYSQL_USER') or '')
    password = quote_plus(app.config.get('MYSQL_PASSWORD') or '')
    host = app.config.get('MYSQL_HOST') or 'localhost'
    name = app.config.get('MYSQL_DB') or ''
    app.config.setdefault('SQLALCHEMY_DATABASE_URI', f'mysql+mysqldb://{user}:{password}@{host}/{name}')
    app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)
    _install_migration_context_defaults()
    db.init_app(app)
    migrate.init_app(app, db)
