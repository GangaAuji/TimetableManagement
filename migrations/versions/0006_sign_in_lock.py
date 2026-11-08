"""Time-based sign-in lock: users.locked_until and users.failed_window_start.

Revision ID: 0006_sign_in_lock
Revises: 0005_seed_history
Create Date: 2026-11-08

failed_window_start is when the current run of failed sign-ins began, so
failures older than the window stop counting. locked_until is when a lock
ends; the account signs in again after that without an admin. Both columns
are added only when missing, and the downgrade drops only what exists.
"""

import sqlalchemy as sa
from alembic import op

revision = '0006_sign_in_lock'
down_revision = '0005_seed_history'
branch_labels = None
depends_on = None

COLUMNS = (
    ('failed_window_start', 'ALTER TABLE users ADD COLUMN failed_window_start DATETIME NULL DEFAULT NULL AFTER failed_attempts'),
    ('locked_until', 'ALTER TABLE users ADD COLUMN locked_until DATETIME NULL DEFAULT NULL AFTER failed_window_start'),
)


def _existing():
    rows = op.get_bind().execute(
        sa.text(
            """
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
              AND COLUMN_NAME IN ('failed_window_start', 'locked_until')
            """
        )
    ).fetchall()
    return {row[0] for row in rows}


def upgrade_statements(existing):
    return [statement for name, statement in COLUMNS if name not in existing]


def downgrade_statements(existing):
    return [f'ALTER TABLE users DROP COLUMN {name}' for name, _ in reversed(COLUMNS) if name in existing]


def upgrade():
    for statement in upgrade_statements(_existing()):
        op.execute(statement)


def downgrade():
    for statement in downgrade_statements(_existing()):
        op.execute(statement)
