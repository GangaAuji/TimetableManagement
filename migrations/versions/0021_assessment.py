"""Internal assessment: components, marks, and CO/PO mapping (docs/ACADEMICS.md).

Revision ID: 0021_assessment
Revises: 0020_syllabus

Read and written only while capability `assessments` is on. Students see a mark
only after its component is locked.
"""

import sqlalchemy as sa
from alembic import op

revision = '0021_assessment'
down_revision = '0020_syllabus'
branch_labels = None
depends_on = None

COMPONENTS = """
CREATE TABLE assessment_components (
  id int(11) NOT NULL AUTO_INCREMENT,
  subject_id int(11) NOT NULL,
  name varchar(80) NOT NULL,
  max_marks decimal(6,1) NOT NULL,
  weight decimal(5,1) NOT NULL DEFAULT 0.0,
  kind enum('IA','assignment','practical','viva','project') NOT NULL,
  sort_order smallint NOT NULL DEFAULT 0,
  locked_at datetime DEFAULT NULL,
  locked_by int(11) DEFAULT NULL,
  PRIMARY KEY (id),
  KEY fk_assessment_component_subject (subject_id),
  KEY fk_assessment_component_locker (locked_by),
  CONSTRAINT fk_assessment_component_subject FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
  CONSTRAINT fk_assessment_component_locker FOREIGN KEY (locked_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One internal assessment component of a subject'
"""

MARKS = """
CREATE TABLE assessment_marks (
  id int(11) NOT NULL AUTO_INCREMENT,
  component_id int(11) NOT NULL,
  student_id int(11) NOT NULL,
  marks decimal(6,1) DEFAULT NULL,
  entered_by int(11) DEFAULT NULL,
  locked_at datetime DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_assessment_mark (component_id, student_id),
  KEY fk_assessment_mark_student (student_id),
  KEY fk_assessment_mark_editor (entered_by),
  CONSTRAINT fk_assessment_mark_component FOREIGN KEY (component_id) REFERENCES assessment_components (id) ON DELETE CASCADE,
  CONSTRAINT fk_assessment_mark_student FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
  CONSTRAINT fk_assessment_mark_editor FOREIGN KEY (entered_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='A student mark on one assessment component'
"""

COURSE_OUTCOMES = """
CREATE TABLE course_outcomes (
  id int(11) NOT NULL AUTO_INCREMENT,
  subject_id int(11) NOT NULL,
  code varchar(12) NOT NULL,
  statement varchar(300) NOT NULL,
  sort_order smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_course_outcome (subject_id, code),
  CONSTRAINT fk_course_outcome_subject FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Course outcome of one subject'
"""

PROGRAM_OUTCOMES = """
CREATE TABLE program_outcomes (
  id int(11) NOT NULL AUTO_INCREMENT,
  course_id int(11) NOT NULL,
  code varchar(12) NOT NULL,
  statement varchar(300) NOT NULL,
  sort_order smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_program_outcome (course_id, code),
  CONSTRAINT fk_program_outcome_course FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Program outcome of one course'
"""

CO_PO = """
CREATE TABLE co_po_map (
  id int(11) NOT NULL AUTO_INCREMENT,
  co_id int(11) NOT NULL,
  po_id int(11) NOT NULL,
  level tinyint NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_co_po (co_id, po_id),
  KEY fk_co_po_program (po_id),
  CONSTRAINT fk_co_po_course FOREIGN KEY (co_id) REFERENCES course_outcomes (id) ON DELETE CASCADE,
  CONSTRAINT fk_co_po_program FOREIGN KEY (po_id) REFERENCES program_outcomes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='CO to PO correlation, level 1 to 3'
"""

COMPONENT_CO = """
CREATE TABLE component_co_map (
  id int(11) NOT NULL AUTO_INCREMENT,
  component_id int(11) NOT NULL,
  co_id int(11) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_component_co (component_id, co_id),
  KEY fk_component_co_outcome (co_id),
  CONSTRAINT fk_component_co_component FOREIGN KEY (component_id) REFERENCES assessment_components (id) ON DELETE CASCADE,
  CONSTRAINT fk_component_co_outcome FOREIGN KEY (co_id) REFERENCES course_outcomes (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Which course outcomes a component assesses'
"""

OBJECTS = (
    ('assessment_components', COMPONENTS, 'DROP TABLE assessment_components'),
    ('assessment_marks', MARKS, 'DROP TABLE assessment_marks'),
    ('course_outcomes', COURSE_OUTCOMES, 'DROP TABLE course_outcomes'),
    ('program_outcomes', PROGRAM_OUTCOMES, 'DROP TABLE program_outcomes'),
    ('co_po_map', CO_PO, 'DROP TABLE co_po_map'),
    ('component_co_map', COMPONENT_CO, 'DROP TABLE component_co_map'),
)

_TABLES = {name for name, _, _ in OBJECTS}
_DROP_ORDER = (
    'component_co_map', 'co_po_map', 'assessment_marks', 'assessment_components', 'course_outcomes', 'program_outcomes',
)


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
