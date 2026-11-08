import logging
from logging.config import fileConfig

from flask import current_app

from alembic import context
from alembic.util import CommandError

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

AUTOGENERATE_DISABLED = (
    'Autogenerate is disabled: hand-written revisions only. '
    'Create one with: flask db revision -m "short description" --rev-id NNNN_short_description '
    '(see docs/DATABASE.md).'
)


def refuse_autogenerate():
    if getattr(config.cmd_opts, 'autogenerate', False):
        raise CommandError(AUTOGENERATE_DISABLED)


def get_engine():
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions['migrate'].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions['migrate'].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace(
            '%', '%%')
    except AttributeError:
        return str(get_engine().url).replace('%', '%%')


config.set_main_option('sqlalchemy.url', get_engine_url())


def process_revision_directives(context, revision, directives):
    # Alembic only calls this while generating a revision from the database,
    # which is autogenerate. Plain `flask db revision` never runs env.py.
    raise CommandError(AUTOGENERATE_DISABLED)


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    refuse_autogenerate()
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    refuse_autogenerate()
    conf_args = dict(current_app.extensions['migrate'].configure_args)
    conf_args['process_revision_directives'] = process_revision_directives

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
