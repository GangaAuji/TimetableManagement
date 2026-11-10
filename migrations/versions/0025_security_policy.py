"""Security policy row and the password-change clock (docs/DESIGN_CAPABILITIES.md).

Revision ID: 0025_security_policy
Revises: 0024_branding_scope

`security_settings` holds one tenant row. Its defaults match today's rules
(8 to 128 characters, no complexity, no expiry, no idle limit, no session
cap, no admin network list, no sign-in notice), so turning the capability on
changes nothing until an administrator saves a stricter row.
`users.password_changed_at` stays null for existing accounts, which are not
treated as expired. Downgrade drops the table and that column.
"""

import sqlalchemy as sa
from alembic import op

revision = '0025_security_policy'
down_revision = '0024_branding_scope'
branch_labels = None
depends_on = None

SETTINGS = """
CREATE TABLE security_settings (
  id tinyint(3) NOT NULL,
  min_length smallint(6) NOT NULL DEFAULT 8,
  max_length smallint(6) NOT NULL DEFAULT 128,
  require_upper tinyint(1) NOT NULL DEFAULT 0,
  require_lower tinyint(1) NOT NULL DEFAULT 0,
  require_digit tinyint(1) NOT NULL DEFAULT 0,
  require_symbol tinyint(1) NOT NULL DEFAULT 0,
  expiry_days smallint(6) NOT NULL DEFAULT 0,
  idle_minutes smallint(6) NOT NULL DEFAULT 0,
  max_sessions smallint(6) NOT NULL DEFAULT 0,
  admin_ip_allowlist varchar(2000) DEFAULT NULL,
  sign_in_notice tinyint(1) NOT NULL DEFAULT 0,
  updated_at timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One row of tenant sign-in and password rules'
"""


def _has_column():
    row = op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'users' AND COLUMN_NAME = 'password_changed_at' LIMIT 1"
    )).fetchone()
    return row is not None


def _has_table():
    row = op.get_bind().execute(sa.text(
        "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'security_settings' LIMIT 1"
    )).fetchone()
    return row is not None


def upgrade():
    if not _has_column():
        op.execute('ALTER TABLE users ADD COLUMN password_changed_at datetime DEFAULT NULL')
    if not _has_table():
        op.execute(SETTINGS)
    op.execute('INSERT IGNORE INTO security_settings (id) VALUES (1)')


def downgrade():
    if _has_table():
        op.execute('DROP TABLE security_settings')
    if _has_column():
        op.execute('ALTER TABLE users DROP COLUMN password_changed_at')
