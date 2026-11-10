"""Syllabus units and one lesson log per lecture (docs/ACADEMICS.md).

Revision ID: 0020_syllabus
Revises: 0019_academic_calendar

`syllabus_units` is the planned hours of one subject. `lesson_logs` is the topic a teacher
records when a lecture is marked, from the mark screen or the mobile sync payload.
Both are read and written only while capability `syllabus` is on.
"""

import sqlalchemy as sa
from alembic import op

revision = '0020_syllabus'
down_revision = '0019_academic_calendar'
branch_labels = None
depends_on = None

UNITS = """
CREATE TABLE syllabus_units (
  id int(11) NOT NULL AUTO_INCREMENT,
  subject_id int(11) NOT NULL,
  unit_no smallint NOT NULL,
  title varchar(120) NOT NULL,
  planned_hours decimal(4,1) NOT NULL,
  sort_order smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_syllabus_unit (subject_id, unit_no),
  CONSTRAINT fk_syllabus_unit_subject FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Planned syllabus hours for one subject'
"""

LOGS = """
CREATE TABLE lesson_logs (
  id int(11) NOT NULL AUTO_INCREMENT,
  lecture_session_id int(11) NOT NULL,
  unit_id int(11) NOT NULL,
  topic varchar(200) NOT NULL,
  hours decimal(3,1) NOT NULL,
  notes varchar(500) NOT NULL DEFAULT '',
  recorded_by int(11) DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_lesson_session (lecture_session_id),
  KEY fk_lesson_unit (unit_id),
  KEY fk_lesson_recorder (recorded_by),
  CONSTRAINT fk_lesson_session FOREIGN KEY (lecture_session_id) REFERENCES lecture_sessions (id) ON DELETE CASCADE,
  CONSTRAINT fk_lesson_unit FOREIGN KEY (unit_id) REFERENCES syllabus_units (id) ON DELETE RESTRICT,
  CONSTRAINT fk_lesson_recorder FOREIGN KEY (recorded_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Topic taught in one held lecture'
"""

# (name, create, drop); applied in order, dropped in reverse.
OBJECTS = (
    ('syllabus_units', UNITS, 'DROP TABLE syllabus_units'),
    ('lesson_logs', LOGS, 'DROP TABLE lesson_logs'),
)

_TABLES = {name for name, _, _ in OBJECTS}


def _existing():
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN :names"
    ).bindparams(sa.bindparam('names', expanding=True)), {'names': sorted(_TABLES)}).fetchall()
    return {row[0] for row in rows}


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
