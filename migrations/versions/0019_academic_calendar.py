"""Academic terms (docs/ACADEMICS.md).

Revision ID: 0019_academic_calendar
Revises: 0018_bookings

The baseline already has `academic_terms` (year, name, dates, is_current) and nothing reads it.
This adds the institution, an optional semester and a kind (teaching, exam, break, internship),
and widens `name` to 80 characters. `lecture_sessions.cancel_reason` gains `calendar` for
sessions closed because they fall outside a teaching term. The calendar is read only while
capability `academic_terms` is on.

A database without the table gets the full shape, including `is_current`, so downgrade can
return it to the baseline columns.
"""

import sqlalchemy as sa
from alembic import op

revision = '0019_academic_calendar'
down_revision = '0018_bookings'
branch_labels = None
depends_on = None

TERMS = """
CREATE TABLE academic_terms (
  id int(11) NOT NULL AUTO_INCREMENT,
  academic_year_id int(11) NOT NULL,
  institution_id int(11) NOT NULL DEFAULT 1,
  semester_id int(11) DEFAULT NULL,
  name varchar(80) NOT NULL,
  start_date date NOT NULL,
  end_date date NOT NULL,
  is_current tinyint(1) DEFAULT 0,
  kind enum('teaching','exam','break','internship') NOT NULL DEFAULT 'teaching',
  PRIMARY KEY (id),
  KEY idx_academic_terms_institution (institution_id, start_date, end_date),
  KEY academic_year_id (academic_year_id),
  KEY fk_academic_terms_semester (semester_id),
  CONSTRAINT academic_terms_ibfk_1 FOREIGN KEY (academic_year_id) REFERENCES academic_years (id) ON DELETE CASCADE,
  CONSTRAINT fk_academic_terms_institution FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE,
  CONSTRAINT fk_academic_terms_semester FOREIGN KEY (semester_id) REFERENCES semesters (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
"""

REASON_WITH = "enum('faculty_absent','institution','exam','other','calendar')"
REASON_WITHOUT = "enum('faculty_absent','institution','exam','other')"

_ADDED = (
    ('fk_academic_terms_semester', 'semester_id'),
    ('fk_academic_terms_institution', 'institution_id'),
)


def _names(sql):
    return {row[0] for row in op.get_bind().execute(sa.text(sql)).fetchall()}


def _has_table():
    return 'academic_terms' in _names(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'academic_terms'"
    )


def _columns():
    return _names(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'academic_terms'"
    )


def _indexes():
    return _names(
        "SELECT INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'academic_terms'"
    )


def _constraints():
    return _names(
        "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'academic_terms'"
    )


def _reason_type():
    row = op.get_bind().execute(sa.text(
        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'lecture_sessions' AND COLUMN_NAME = 'cancel_reason'"
    )).fetchone()
    return (row[0] if row else '') or ''


def upgrade():
    if not _has_table():
        op.execute(TERMS)
    columns = _columns()
    if 'institution_id' not in columns:
        op.execute('ALTER TABLE academic_terms ADD COLUMN institution_id int(11) NOT NULL DEFAULT 1')
    if 'semester_id' not in columns:
        op.execute('ALTER TABLE academic_terms ADD COLUMN semester_id int(11) DEFAULT NULL')
    if 'kind' not in columns:
        op.execute(
            "ALTER TABLE academic_terms ADD COLUMN kind enum('teaching','exam','break','internship') NOT NULL DEFAULT 'teaching'"
        )
    op.execute('ALTER TABLE academic_terms MODIFY name varchar(80) NOT NULL')
    constraints = _constraints()
    if 'fk_academic_terms_institution' not in constraints:
        op.execute(
            'ALTER TABLE academic_terms ADD CONSTRAINT fk_academic_terms_institution '
            'FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE'
        )
    if 'fk_academic_terms_semester' not in constraints:
        op.execute(
            'ALTER TABLE academic_terms ADD CONSTRAINT fk_academic_terms_semester '
            'FOREIGN KEY (semester_id) REFERENCES semesters (id) ON DELETE SET NULL'
        )
    indexes = _indexes()
    if 'idx_academic_terms_institution' not in indexes:
        op.execute('ALTER TABLE academic_terms ADD KEY idx_academic_terms_institution (institution_id, start_date, end_date)')
    if 'calendar' not in _reason_type():
        op.execute(f'ALTER TABLE lecture_sessions MODIFY cancel_reason {REASON_WITH} DEFAULT NULL')


def downgrade():
    if 'calendar' in _reason_type():
        op.execute("UPDATE lecture_sessions SET cancel_reason = 'other' WHERE cancel_reason = 'calendar'")
        op.execute(f'ALTER TABLE lecture_sessions MODIFY cancel_reason {REASON_WITHOUT} DEFAULT NULL')
    if not _has_table():
        return
    constraints = _constraints()
    for name, _column in _ADDED:
        if name in constraints:
            op.execute(f'ALTER TABLE academic_terms DROP FOREIGN KEY {name}')
    indexes = _indexes()
    if 'idx_academic_terms_institution' in indexes:
        op.execute('ALTER TABLE academic_terms DROP INDEX idx_academic_terms_institution')
    columns = _columns()
    for column in ('kind', 'semester_id', 'institution_id'):
        if column in columns:
            op.execute(f'ALTER TABLE academic_terms DROP COLUMN {column}')
    if 'name' in _columns():
        op.execute('ALTER TABLE academic_terms MODIFY name varchar(50) NOT NULL')
