"""Is the database at the revision this code expects?"""

from functools import lru_cache

from core.schema.baseline import MIGRATIONS_DIR

_HAS_VERSION_TABLE = """
SELECT 1 FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'alembic_version'
"""


@lru_cache(maxsize=1)
def _revisions():
    """Return (head, every known revision id) from the migrations folder."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f'The migrations have {len(heads)} heads; expected one.')
    known = frozenset(script.revision for script in scripts.walk_revisions('base', 'heads'))
    return heads[0], known


def head_revision():
    return _revisions()[0]


def reason_for(stamped):
    """Return None when `stamped` (the alembic_version rows) is the head, otherwise why not."""
    head, known = _revisions()
    if not stamped:
        return (
            'The database has no migration stamp. '
            'Run `flask db-adopt` on an existing database or `flask db upgrade` on a new one.'
        )
    if len(stamped) > 1:
        return f'The database has several migration stamps ({", ".join(stamped)}); expected {head}.'
    current = stamped[0]
    if current == head:
        return None
    if current in known:
        return f'The database is at {current}; the code expects {head}. Run `flask db upgrade`.'
    return f'The database is at {current}, which this code does not know; the code expects {head}.'


def database_reason(connect):
    """Open a connection with `connect`, read alembic_version, and return None or the reason it is not at head."""
    try:
        connection = connect()
    except Exception as exc:
        return f'The database is unreachable: {exc.__class__.__name__}.'
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(_HAS_VERSION_TABLE)
            stamped = []
            if cursor.fetchone():
                cursor.execute('SELECT version_num FROM alembic_version')
                stamped = sorted(row[0] for row in cursor.fetchall())
            connection.rollback()
        finally:
            cursor.close()
    except Exception as exc:
        return f'The migration stamp could not be read: {exc.__class__.__name__}.'
    finally:
        connection.close()
    return reason_for(stamped)
