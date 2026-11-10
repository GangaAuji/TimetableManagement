"""Capabilities: one row per optional feature (docs/DESIGN_CAPABILITIES.md).

Revision ID: 0015_capabilities
Revises: 0014_institutions

A capability is on only when the server flag FEATURE_<NAME> is on AND its row here says
`enabled = 1`. Rows are created lazily by the settings page; a missing row means "off".
Nothing else in the schema depends on this table, so the application runs without it.
"""

import sqlalchemy as sa
from alembic import op

revision = '0015_capabilities'
down_revision = '0014_institutions'
branch_labels = None
depends_on = None

CAPABILITIES = """
CREATE TABLE capabilities (
  id int(11) NOT NULL AUTO_INCREMENT,
  capability varchar(60) NOT NULL COMMENT 'name from core.capabilities.CAPABILITIES',
  enabled tinyint(1) NOT NULL DEFAULT 0,
  settings_json text DEFAULT NULL COMMENT 'JSON object validated against the registry schema',
  updated_by int(11) DEFAULT NULL,
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_capability_name (capability),
  KEY fk_capability_updater (updated_by),
  CONSTRAINT fk_capability_updater FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Optional features switched on per tenant'
"""

TABLES = (('capabilities', CAPABILITIES),)
_HAS_TABLE = "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table"


def _has_table(connection, table):
    return connection.execute(sa.text(_HAS_TABLE), {'table': table}).first() is not None


def upgrade():
    connection = op.get_bind()
    for table, statement in TABLES:
        if not _has_table(connection, table):
            op.execute(statement)


def downgrade():
    connection = op.get_bind()
    for table, _statement in reversed(TABLES):
        if _has_table(connection, table):
            op.execute(f'DROP TABLE `{table}`')
