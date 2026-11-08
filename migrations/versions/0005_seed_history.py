"""seed_history records which one-time defaults `flask seed run` has already handled.

Revision ID: 0005_seed_history
Revises: 0004_rate_limit_collation
Create Date: 2026-11-08

A default role permission is granted at most once. After that the row in
seed_history stops a later seed run from re-adding it, so a permission a
college removed from a role stays removed.
"""

from alembic import op

revision = '0005_seed_history'
down_revision = '0004_rate_limit_collation'
branch_labels = None
depends_on = None

SEED_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS seed_history (
  id int(11) NOT NULL AUTO_INCREMENT,
  seeder varchar(64) NOT NULL,
  item varchar(191) NOT NULL,
  version varchar(32) NOT NULL,
  applied_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_seed_history_item (seeder, item)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def upgrade():
    op.execute(SEED_HISTORY_TABLE)


def downgrade():
    op.execute('DROP TABLE IF EXISTS seed_history')
