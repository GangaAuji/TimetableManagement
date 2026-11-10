"""Timetable rules and faculty preferences (docs/TIMETABLE.md, "Rules and preferences").

Revision ID: 0016_timetable_preferences
Revises: 0015_capabilities

`faculty_preferences`: windows a teacher prefers or wants to avoid, weighted 1-5. Soft: the
solvers pay a cost, `faculty_availability` stays the hard constraint.
`timetable_rules`: one JSON document of rule weights per institution (services/timetable/rules.py).
Both are read only while capability `timetable_preferences` is on.
"""

import sqlalchemy as sa
from alembic import op

revision = '0016_timetable_preferences'
down_revision = '0015_capabilities'
branch_labels = None
depends_on = None

FACULTY_PREFERENCES = """
CREATE TABLE faculty_preferences (
  id int(11) NOT NULL AUTO_INCREMENT,
  faculty_id int(11) NOT NULL COMMENT 'faculty.user_id, like timetable.faculty_id',
  day_of_week tinyint(4) NOT NULL COMMENT '1 = Monday .. 7 = Sunday, as faculty_availability',
  start_time time NOT NULL,
  end_time time NOT NULL,
  kind enum('preferred','avoid') NOT NULL DEFAULT 'avoid',
  weight tinyint(4) NOT NULL DEFAULT 3 COMMENT '1 (mild) to 5 (strong)',
  note varchar(120) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  KEY idx_faculty_preference (faculty_id, day_of_week),
  CONSTRAINT fk_faculty_preference_faculty FOREIGN KEY (faculty_id) REFERENCES faculty (user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Soft day/time preferences per teacher'
"""

TIMETABLE_RULES = """
CREATE TABLE timetable_rules (
  id int(11) NOT NULL AUTO_INCREMENT,
  institution_id int(11) NOT NULL DEFAULT 1,
  rules_json text NOT NULL COMMENT 'rule name -> {weight, params}; see services/timetable/rules.py',
  updated_by int(11) DEFAULT NULL,
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_timetable_rules_institution (institution_id),
  KEY fk_timetable_rules_updater (updated_by),
  CONSTRAINT fk_timetable_rules_institution FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE,
  CONSTRAINT fk_timetable_rules_updater FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Weighted soft rules per institution'
"""

TABLES = (('faculty_preferences', FACULTY_PREFERENCES), ('timetable_rules', TIMETABLE_RULES))
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
