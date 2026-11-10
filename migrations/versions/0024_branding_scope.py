"""Optional per-institution branding (docs/DESIGN_INSTITUTIONS.md).

Revision ID: 0024_branding_scope
Revises: 0023_second_factor

`branding_settings.institution_id` is null for the organization row. A row for
an institution overrides that key. `institution_scope` is 0 for the
organization so the unique key still allows one organization row per setting
(MariaDB treats NULL as distinct in a unique index). Missing the column,
sign-in and Settings keep reading the organization rows.
"""

import sqlalchemy as sa
from alembic import op

revision = '0024_branding_scope'
down_revision = '0023_second_factor'
branch_labels = None
depends_on = None


def _names(sql):
    rows = op.get_bind().execute(sa.text(sql)).fetchall()
    return {row[0] for row in rows}


def _columns():
    return _names(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'branding_settings'"
    )


def _indexes():
    return _names(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'branding_settings'"
    )


def _constraints():
    return _names(
        "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'branding_settings'"
    )


def upgrade():
    columns = _columns()
    if 'institution_id' not in columns:
        op.execute('ALTER TABLE branding_settings ADD COLUMN institution_id int(11) DEFAULT NULL')
    if 'institution_scope' not in columns:
        op.execute(
            'ALTER TABLE branding_settings ADD COLUMN institution_scope int(11) '
            'GENERATED ALWAYS AS (IFNULL(`institution_id`, 0)) STORED'
        )
    if 'fk_branding_institution' not in _constraints():
        op.execute(
            'ALTER TABLE branding_settings ADD CONSTRAINT fk_branding_institution '
            'FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE'
        )
    indexes = _indexes()
    if 'setting_key' in indexes:
        op.execute('ALTER TABLE branding_settings DROP INDEX setting_key')
    if 'uq_branding_scope' not in indexes:
        op.execute(
            'ALTER TABLE branding_settings ADD UNIQUE KEY uq_branding_scope (setting_key, institution_scope)'
        )


def downgrade():
    constraints = _constraints()
    if 'fk_branding_institution' in constraints:
        op.execute('ALTER TABLE branding_settings DROP FOREIGN KEY fk_branding_institution')
    indexes = _indexes()
    if 'uq_branding_scope' in indexes:
        op.execute('ALTER TABLE branding_settings DROP INDEX uq_branding_scope')
    columns = _columns()
    if 'institution_id' in columns:
        op.execute('DELETE FROM branding_settings WHERE institution_id IS NOT NULL')
    if 'institution_scope' in columns:
        op.execute('ALTER TABLE branding_settings DROP COLUMN institution_scope')
    if 'institution_id' in columns:
        op.execute('ALTER TABLE branding_settings DROP COLUMN institution_id')
    if 'setting_key' not in _indexes():
        op.execute('ALTER TABLE branding_settings ADD UNIQUE KEY setting_key (setting_key)')
