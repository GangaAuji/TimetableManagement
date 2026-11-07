"""Single-commit helper. It does not close the connection."""

from contextlib import contextmanager


@contextmanager
def transaction(connection):
    """Commit when the block finishes, and roll back when it raises."""
    try:
        yield
        if connection is not None:
            connection.commit()
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
