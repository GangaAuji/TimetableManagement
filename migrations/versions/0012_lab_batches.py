"""lab batches: lab_batch_groups, lab_batch_members and timetable.lab_batch_group_id.

Revision ID: 0012_lab_batches
Revises: 0011_notifications
Create Date: 2026-11-09

Implements docs/DESIGN_LAB_BATCHES.md. A division is split into lab batch
groups ("A1", "A2") for one academic year (and optionally one semester);
lab_batch_members says which students are in which group, with ended_at
set when a student moves so the old membership keeps its dates. A timetable
row with lab_batch_group_id set is a slot for that group only; NULL keeps
the current meaning (the whole division, or the whole class when
division_id is NULL). course_batches is untouched: it stays the intake
cohort. Every object is created only when missing; the downgrade drops only
what exists.
"""

import sqlalchemy as sa
from alembic import op

revision = '0012_lab_batches'
down_revision = '0011_notifications'
branch_labels = None
depends_on = None

LAB_BATCH_GROUPS = """
CREATE TABLE lab_batch_groups (
  id int(11) NOT NULL AUTO_INCREMENT,
  course_id int(11) NOT NULL,
  class_id int(11) NOT NULL,
  division_id int(11) DEFAULT NULL COMMENT 'NULL splits the whole class',
  academic_year_id int(11) NOT NULL,
  semester_id int(11) DEFAULT NULL COMMENT 'NULL: the same split all year',
  name varchar(20) NOT NULL,
  capacity int(11) DEFAULT NULL COMMENT 'Lab seats; the generator respects it',
  is_active tinyint(1) NOT NULL DEFAULT 1,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_lab_batch_group (course_id, class_id, division_id, academic_year_id, semester_id, name),
  KEY idx_lab_batch_group_cohort (course_id, class_id, division_id, academic_year_id),
  KEY fk_lab_batch_group_class (class_id),
  KEY fk_lab_batch_group_division (division_id),
  KEY fk_lab_batch_group_year (academic_year_id),
  KEY fk_lab_batch_group_semester (semester_id),
  CONSTRAINT fk_lab_batch_group_course FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_batch_group_class FOREIGN KEY (class_id) REFERENCES classes (id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_batch_group_division FOREIGN KEY (division_id) REFERENCES divisions (id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_batch_group_year FOREIGN KEY (academic_year_id) REFERENCES academic_years (id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_batch_group_semester FOREIGN KEY (semester_id) REFERENCES semesters (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Lab batches a division is split into (docs/DESIGN_LAB_BATCHES.md)'
"""

LAB_BATCH_MEMBERS = """
CREATE TABLE lab_batch_members (
  id int(11) NOT NULL AUTO_INCREMENT,
  lab_batch_group_id int(11) NOT NULL,
  student_id int(11) NOT NULL,
  added_at date NOT NULL,
  ended_at date DEFAULT NULL COMMENT 'Set when the student moved to another batch',
  PRIMARY KEY (id),
  UNIQUE KEY uq_lab_batch_member (lab_batch_group_id, student_id),
  KEY idx_lab_batch_member_student (student_id, ended_at),
  CONSTRAINT fk_lab_batch_member_group FOREIGN KEY (lab_batch_group_id) REFERENCES lab_batch_groups (id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_batch_member_student FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Which students are in which lab batch'
"""

# (object name, create statement, drop statement), in upgrade order.
OBJECTS = (
    ('lab_batch_groups', LAB_BATCH_GROUPS, 'DROP TABLE lab_batch_groups'),
    ('lab_batch_members', LAB_BATCH_MEMBERS, 'DROP TABLE lab_batch_members'),
    (
        'timetable.lab_batch_group_id',
        "ALTER TABLE timetable ADD COLUMN lab_batch_group_id int(11) DEFAULT NULL "
        "COMMENT 'NULL: the whole division' AFTER division_id",
        'ALTER TABLE timetable DROP COLUMN lab_batch_group_id',
    ),
    (
        'idx_timetable_lab_batch',
        'ALTER TABLE timetable ADD KEY idx_timetable_lab_batch (lab_batch_group_id)',
        'ALTER TABLE timetable DROP KEY idx_timetable_lab_batch',
    ),
    (
        'fk_timetable_lab_batch',
        'ALTER TABLE timetable ADD CONSTRAINT fk_timetable_lab_batch FOREIGN KEY (lab_batch_group_id) '
        'REFERENCES lab_batch_groups (id) ON DELETE SET NULL',
        'ALTER TABLE timetable DROP FOREIGN KEY fk_timetable_lab_batch',
    ),
)


def _existing():
    bind = op.get_bind()
    found = set()
    rows = bind.execute(sa.text(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME IN ('lab_batch_groups', 'lab_batch_members')"
    )).fetchall()
    found.update(row[0] for row in rows)
    if bind.execute(sa.text(
        "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'timetable' AND COLUMN_NAME = 'lab_batch_group_id'"
    )).fetchone():
        found.add('timetable.lab_batch_group_id')
    if bind.execute(sa.text(
        "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'timetable' AND INDEX_NAME = 'idx_timetable_lab_batch'"
    )).fetchone():
        found.add('idx_timetable_lab_batch')
    if bind.execute(sa.text(
        "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'timetable' AND CONSTRAINT_NAME = 'fk_timetable_lab_batch' AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
    )).fetchone():
        found.add('fk_timetable_lab_batch')
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
