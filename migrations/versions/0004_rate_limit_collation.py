"""rate_limit_counters uses utf8mb4_unicode_ci like the rest of the schema.

Revision ID: 0004_rate_limit_collation
Revises: 0003_security_schema
Create Date: 2026-11-08

0003 created the table without a collation, so it took the server default
(utf8mb4_general_ci on MariaDB 10.4). The table only holds short-lived
counters keyed by an ASCII bucket name, so converting it is safe and fast.
Running the conversion on a table that is already unicode_ci changes nothing.
"""

from alembic import op

revision = '0004_rate_limit_collation'
down_revision = '0003_security_schema'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE rate_limit_counters CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')


def downgrade():
    op.execute('ALTER TABLE rate_limit_counters CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci')
