"""Role hierarchy and the shared rate-limit table.

Revision ID: 0003_security_schema
Revises: 0002_catch_up
Create Date: 2026-11-08

The statements are idempotent. A clean database gains the column. An existing
database that already has hierarchy_level only receives the level seed and the
rate-limit table.

Downgrade drops rate_limit_counters only. hierarchy_level is part of the
baseline, and the seeded levels are left in place.
"""

import sqlalchemy as sa
from alembic import op

revision = '0003_security_schema'
down_revision = '0002_catch_up'
branch_labels = None
depends_on = None

ROLE_LEVELS = (
    ('Super Admin', 1),
    ('Admin', 2),
    ('HOD', 3),
    ('Teacher', 4),
    ('Student', 5),
)

RATE_LIMIT_TABLE = """CREATE TABLE IF NOT EXISTS rate_limit_counters (
    bucket VARCHAR(191) NOT NULL,
    hits INT UNSIGNED NOT NULL DEFAULT 0,
    window_start DATETIME(6) NOT NULL,
    PRIMARY KEY (bucket)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""


def role_level_statements(column_exists):
    """Return the role-column statements for a clean or existing database."""
    statements = []
    if not column_exists:
        statements.append('ALTER TABLE roles ADD COLUMN hierarchy_level INT NOT NULL DEFAULT 50')
    for name, level in ROLE_LEVELS:
        statements.append(
            "UPDATE roles SET hierarchy_level = %d WHERE name = '%s' AND hierarchy_level = 50" % (level, name)
        )
    statements.append(RATE_LIMIT_TABLE)
    return statements


def _column_exists():
    row = op.get_bind().execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'roles'
              AND COLUMN_NAME = 'hierarchy_level'
            LIMIT 1
            """
        )
    ).fetchone()
    return row is not None


def upgrade():
    for statement in role_level_statements(_column_exists()):
        op.execute(statement)


def downgrade():
    op.execute('DROP TABLE IF EXISTS rate_limit_counters')
