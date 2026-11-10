"""Authenticator secrets and one-time recovery codes (docs/DESIGN_CAPABILITIES.md).

Revision ID: 0023_second_factor
Revises: 0022_exam_schedule

Read and written only while capability `two_factor` is on. The secret column
holds a Fernet token, never the base32 secret. Recovery codes are stored as
password hashes. Sign-in is unchanged while the capability is off or this
table is missing.
"""

import sqlalchemy as sa
from alembic import op

revision = '0023_second_factor'
down_revision = '0022_exam_schedule'
branch_labels = None
depends_on = None

FACTORS = """
CREATE TABLE user_second_factors (
  user_id int(11) NOT NULL,
  secret_enc text NOT NULL,
  next_secret_enc text DEFAULT NULL,
  next_secret_at datetime DEFAULT NULL,
  confirmed_at datetime DEFAULT NULL,
  last_step bigint DEFAULT NULL,
  recovery_hashes text NOT NULL,
  created_at timestamp NULL DEFAULT current_timestamp(),
  updated_at timestamp NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (user_id),
  CONSTRAINT fk_second_factor_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Encrypted authenticator secret and hashed recovery codes for one user'
"""

OBJECTS = (
    ('user_second_factors', FACTORS, 'DROP TABLE user_second_factors'),
)

_TABLES = {name for name, _, _ in OBJECTS}
_DROP_ORDER = ('user_second_factors',)


def _existing():
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN :names"
    ).bindparams(sa.bindparam('names', expanding=True)), {'names': sorted(_TABLES)}).fetchall()
    return {row[0] for row in rows}


def upgrade_statements(existing):
    return [create for name, create, _ in OBJECTS if name not in existing]


def downgrade_statements(existing):
    by_name = {name: drop for name, _, drop in OBJECTS}
    return [by_name[name] for name in _DROP_ORDER if name in existing]


def upgrade():
    for statement in upgrade_statements(_existing()):
        op.execute(statement)


def downgrade():
    for statement in downgrade_statements(_existing()):
        op.execute(statement)
