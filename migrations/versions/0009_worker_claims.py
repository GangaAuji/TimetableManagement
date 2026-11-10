"""locked_by and heartbeat_at on the two job tables.

Revision ID: 0009_worker_claims
Revises: 0008_attendance_views
Create Date: 2026-11-09

A worker that claims a processed_reports or timetable_jobs row writes its
id into locked_by and keeps heartbeat_at fresh while it works. A restart
or a second worker process requeues only rows whose heartbeat is stale,
instead of every running row, so several worker processes are safe. Each
statement runs only when its column is missing; the downgrade drops only
what exists.
"""

import sqlalchemy as sa
from alembic import op

revision = '0009_worker_claims'
down_revision = '0008_attendance_views'
branch_labels = None
depends_on = None

TABLES = ('processed_reports', 'timetable_jobs')
COLUMNS = (
    ('locked_by', "varchar(64) DEFAULT NULL COMMENT 'worker id holding the running claim'"),
    ('heartbeat_at', "datetime DEFAULT NULL COMMENT 'last progress written by the claiming worker (UTC)'"),
)
_HAS_COLUMN = """
SELECT 1 FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column
"""


def _has_column(connection, table, column):
    return connection.execute(sa.text(_HAS_COLUMN), {'table': table, 'column': column}).first() is not None


def upgrade():
    connection = op.get_bind()
    for table in TABLES:
        for column, definition in COLUMNS:
            if not _has_column(connection, table, column):
                op.execute(f'ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}')


def downgrade():
    connection = op.get_bind()
    for table in TABLES:
        for column, _definition in reversed(COLUMNS):
            if _has_column(connection, table, column):
                op.execute(f'ALTER TABLE `{table}` DROP COLUMN `{column}`')
