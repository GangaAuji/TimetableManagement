"""attendance.session_id NOT NULL; drop the attendance_summary and student_overall_attendance views.

Revision ID: 0008_attendance_views
Revises: 0007_lecture_sessions
Create Date: 2026-11-09

Every attendance mark now belongs to a lecture_sessions row, and every
percentage comes from services.attendance_calc, so the two views that froze
the old calculation into SQL go. The upgrade refuses to run while any mark
has no session: run `flask attendance backfill-sessions` first (marks on a
cancelled lecture are left for review by that command and must be resolved
by hand). The downgrade makes the column nullable again and recreates the
views from the baseline text. Both directions change only what needs it.
"""

import sqlalchemy as sa
from alembic import op

from core.schema.baseline import baseline_statements

revision = '0008_attendance_views'
down_revision = '0007_lecture_sessions'
branch_labels = None
depends_on = None

VIEWS = ('attendance_summary', 'student_overall_attendance')
NOT_NULL = 'ALTER TABLE attendance MODIFY session_id int(11) NOT NULL'
NULLABLE = 'ALTER TABLE attendance MODIFY session_id int(11) DEFAULT NULL'

# The baseline creates its views after SET NAMES utf8mb4; the recreated views must record the same client settings.
_CHARSET_SAVE = (
    'SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT',
    'SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS',
    'SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION',
    'SET NAMES utf8mb4',
)
_CHARSET_RESTORE = (
    'SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT',
    'SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS',
    'SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION',
)


def refusal(count):
    return (
        f'{count} attendance row(s) have no session_id. Run `flask attendance backfill-sessions --dry-run`, '
        'then `flask attendance backfill-sessions`, resolve any marks it leaves on cancelled lectures '
        '(SELECT id FROM attendance WHERE session_id IS NULL), and upgrade again.'
    )


def view_statements(names=VIEWS):
    """The baseline CREATE VIEW statements for the named views, in baseline order."""
    wanted = {f'VIEW `{name}`' for name in names}
    return [
        statement for statement in baseline_statements()
        if statement.upper().startswith('CREATE') and any(marker in statement for marker in wanted)
    ]


def upgrade_statements(unlinked, nullable, existing_views):
    """Statements for the upgrade, or a RuntimeError when marks without a session exist."""
    if unlinked:
        raise RuntimeError(refusal(unlinked))
    statements = [NOT_NULL] if nullable else []
    statements += [f'DROP VIEW IF EXISTS `{name}`' for name in VIEWS if name in existing_views]
    return statements


def downgrade_statements(nullable, existing_views, statements_for_views=view_statements):
    statements = [] if nullable else [NULLABLE]
    missing = [name for name in VIEWS if name not in existing_views]
    if missing:
        statements += list(_CHARSET_SAVE) + statements_for_views(missing) + list(_CHARSET_RESTORE)
    return statements


def _state():
    bind = op.get_bind()
    unlinked = bind.execute(sa.text('SELECT COUNT(*) FROM attendance WHERE session_id IS NULL')).scalar()
    nullable = bind.execute(sa.text(
        "SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'session_id'"
    )).scalar()
    views = {row[0] for row in bind.execute(sa.text(
        "SELECT TABLE_NAME FROM information_schema.VIEWS WHERE TABLE_SCHEMA = DATABASE()"
    )).fetchall()}
    return int(unlinked or 0), nullable == 'YES', views


def upgrade():
    unlinked, nullable, views = _state()
    for statement in upgrade_statements(unlinked, nullable, views):
        op.execute(statement)


def downgrade():
    _, nullable, views = _state()
    for statement in downgrade_statements(nullable, views):
        op.execute(statement)
