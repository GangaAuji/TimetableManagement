"""Timetable versions: drafts, compare, publish, rollback (docs/TIMETABLE.md, "Versions").

Revision ID: 0017_timetable_versions
Revises: 0016_timetable_preferences

`timetable_versions`: one row per generation run (or rollback) while capability `timetable_versions`
is on. `timetable_version_cohorts`: the (course, class, division) set a version covers.
`timetable.version_id`: which version a slot belongs to; NULL for rows written before versions
existed or while the capability is off. Draft slots carry `is_active = 0`, so every reader that
filters active rows keeps seeing only the published timetable.
"""

import sqlalchemy as sa
from alembic import op

revision = '0017_timetable_versions'
down_revision = '0016_timetable_preferences'
branch_labels = None
depends_on = None

VERSIONS = """
CREATE TABLE timetable_versions (
  id int(11) NOT NULL AUTO_INCREMENT,
  institution_id int(11) NOT NULL DEFAULT 1,
  label varchar(120) NOT NULL DEFAULT '',
  status enum('draft','published','archived') NOT NULL DEFAULT 'draft',
  solver varchar(20) NOT NULL DEFAULT 'greedy',
  job_id int(11) DEFAULT NULL COMMENT 'timetable_jobs.id that produced it, when any',
  parent_version_id int(11) DEFAULT NULL COMMENT 'the version that was published when this one was created',
  settings_json text DEFAULT NULL COMMENT 'generation settings as given to the job',
  score_json text DEFAULT NULL COMMENT 'per-cohort quality score, rule cost and counts',
  created_by int(11) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  published_by int(11) DEFAULT NULL,
  published_at timestamp NULL DEFAULT NULL,
  PRIMARY KEY (id),
  KEY idx_timetable_versions_status (institution_id, status, created_at),
  KEY fk_timetable_versions_parent (parent_version_id),
  KEY fk_timetable_versions_creator (created_by),
  KEY fk_timetable_versions_publisher (published_by),
  CONSTRAINT fk_timetable_versions_institution FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE,
  CONSTRAINT fk_timetable_versions_parent FOREIGN KEY (parent_version_id) REFERENCES timetable_versions (id) ON DELETE SET NULL,
  CONSTRAINT fk_timetable_versions_creator FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT fk_timetable_versions_publisher FOREIGN KEY (published_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Draft, published and archived timetables'
"""

VERSION_COHORTS = """
CREATE TABLE timetable_version_cohorts (
  version_id int(11) NOT NULL,
  course_id int(11) NOT NULL,
  class_id int(11) NOT NULL,
  division_id int(11) NOT NULL,
  PRIMARY KEY (version_id, course_id, class_id, division_id),
  KEY idx_version_cohort (course_id, class_id, division_id),
  CONSTRAINT fk_version_cohort_version FOREIGN KEY (version_id) REFERENCES timetable_versions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Which classes a timetable version covers'
"""

# (name, create, drop); applied in order, dropped in reverse.
OBJECTS = (
    ('timetable_versions', VERSIONS, 'DROP TABLE timetable_versions'),
    ('timetable_version_cohorts', VERSION_COHORTS, 'DROP TABLE timetable_version_cohorts'),
    (
        'timetable.version_id',
        "ALTER TABLE timetable ADD COLUMN version_id int(11) DEFAULT NULL "
        "COMMENT 'timetable_versions.id; NULL = written without versions' AFTER is_active",
        'ALTER TABLE timetable DROP COLUMN version_id',
    ),
    (
        'fk_timetable_version',
        'ALTER TABLE timetable ADD CONSTRAINT fk_timetable_version FOREIGN KEY (version_id) '
        'REFERENCES timetable_versions (id) ON DELETE SET NULL',
        'ALTER TABLE timetable DROP FOREIGN KEY fk_timetable_version',
    ),
)

_TABLES = {name for name, _, _ in OBJECTS if '.' not in name and not name.startswith('fk_')}
_COLUMNS = {name for name, _, _ in OBJECTS if '.' in name}
_FOREIGN_KEYS = {'fk_timetable_version': 'timetable'}


def _existing():
    bind = op.get_bind()
    found = set()
    rows = bind.execute(sa.text(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN :names"
    ).bindparams(sa.bindparam('names', expanding=True)), {'names': sorted(_TABLES)}).fetchall()
    found.update(row[0] for row in rows)
    for name in _COLUMNS:
        table, column = name.split('.')
        if bind.execute(sa.text(
            "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table AND COLUMN_NAME = :column"
        ), {'table': table, 'column': column}).fetchone():
            found.add(name)
    for name, table in _FOREIGN_KEYS.items():
        if bind.execute(sa.text(
            "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table AND CONSTRAINT_NAME = :name AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
        ), {'table': table, 'name': name}).fetchone():
            found.add(name)
    return found


def upgrade_statements(existing):
    return [create for name, create, _ in OBJECTS if name not in existing]


def downgrade_statements(existing):
    return [drop for name, _, drop in reversed(OBJECTS) if name in existing]


def upgrade():
    for statement in upgrade_statements(_existing()):
        op.execute(statement)


def downgrade():
    for statement in downgrade_statements(_existing()):
        op.execute(statement)
