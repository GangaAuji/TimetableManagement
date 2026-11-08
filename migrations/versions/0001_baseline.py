"""Baseline: the college_timetable_db schema on 10.4.32-MariaDB.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-08

The statements live in migrations/sql/0001_baseline.sql (54 tables, 10 views).
Never edit that file or this revision after a database has been upgraded or
stamped. An existing database is adopted with `flask db-adopt`, not upgraded.
"""
from alembic import op

from core.schema.baseline import baseline_objects, baseline_statements

revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    try:
        for statement in baseline_statements():
            op.execute(statement)
    finally:
        op.execute('SET FOREIGN_KEY_CHECKS = COALESCE(@OLD_FOREIGN_KEY_CHECKS, 1)')


def downgrade():
    tables, views = baseline_objects(baseline_statements())
    for view in reversed(views):
        op.execute(f'DROP VIEW IF EXISTS `{view}`')
    op.execute('SET @OLD_FOREIGN_KEY_CHECKS = @@FOREIGN_KEY_CHECKS')
    op.execute('SET FOREIGN_KEY_CHECKS = 0')
    try:
        for table in reversed(tables):
            op.execute(f'DROP TABLE IF EXISTS `{table}`')
    finally:
        op.execute('SET FOREIGN_KEY_CHECKS = @OLD_FOREIGN_KEY_CHECKS')
