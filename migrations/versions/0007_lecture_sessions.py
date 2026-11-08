"""lecture_sessions, attendance_excuses, and attendance.session_id.

Revision ID: 0007_lecture_sessions
Revises: 0006_sign_in_lock
Create Date: 2026-11-08

lecture_sessions records that a timetable slot on a date was held, cancelled,
or never marked; it is the denominator of every attendance percentage.
attendance_excuses holds approved absences. attendance.session_id links each
mark to its session and stays nullable until the backfill has run everywhere
(`flask attendance backfill-sessions`); a later revision makes it NOT NULL.
Every statement runs only when its object is missing, and the downgrade drops
only what exists. The two attendance views are not touched.
"""

import sqlalchemy as sa
from alembic import op

revision = '0007_lecture_sessions'
down_revision = '0006_sign_in_lock'
branch_labels = None
depends_on = None

LECTURE_SESSIONS = """
CREATE TABLE lecture_sessions (
  id int(11) NOT NULL AUTO_INCREMENT,
  timetable_id int(11) NOT NULL,
  session_date date NOT NULL,
  status enum('held','cancelled','not_marked') NOT NULL,
  taught_by int(11) DEFAULT NULL COMMENT 'faculty.user_id: the approved proxy, else the slot faculty',
  marked_by int(11) DEFAULT NULL COMMENT 'faculty.id of the first marker',
  marked_at datetime DEFAULT NULL,
  cancelled_by int(11) DEFAULT NULL,
  cancelled_at datetime DEFAULT NULL,
  cancel_reason enum('faculty_absent','institution','exam','other') DEFAULT NULL,
  source enum('teacher','mobile','admin','close_day','backfill') NOT NULL,
  session_code varchar(16) DEFAULT NULL,
  session_code_expires_at datetime DEFAULT NULL,
  notes varchar(255) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uk_lecture_session (timetable_id, session_date),
  KEY idx_lecture_session_date (session_date),
  KEY idx_lecture_session_status (status),
  KEY fk_lecture_session_taught_by (taught_by),
  KEY fk_lecture_session_marked_by (marked_by),
  KEY fk_lecture_session_cancelled_by (cancelled_by),
  CONSTRAINT fk_lecture_session_slot FOREIGN KEY (timetable_id) REFERENCES timetable (id) ON DELETE RESTRICT,
  CONSTRAINT fk_lecture_session_taught_by FOREIGN KEY (taught_by) REFERENCES faculty (user_id) ON DELETE SET NULL,
  CONSTRAINT fk_lecture_session_marked_by FOREIGN KEY (marked_by) REFERENCES faculty (id) ON DELETE SET NULL,
  CONSTRAINT fk_lecture_session_cancelled_by FOREIGN KEY (cancelled_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One row per lecture occurrence: held, cancelled, or not marked'
"""

ATTENDANCE_EXCUSES = """
CREATE TABLE attendance_excuses (
  id int(11) NOT NULL AUTO_INCREMENT,
  student_id int(11) NOT NULL,
  subject_id int(11) DEFAULT NULL COMMENT 'NULL: every subject',
  date_from date NOT NULL,
  date_to date NOT NULL,
  reason varchar(255) DEFAULT NULL,
  approved_by int(11) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  KEY idx_attendance_excuse_student (student_id, date_from, date_to),
  KEY fk_attendance_excuse_subject (subject_id),
  KEY fk_attendance_excuse_approved_by (approved_by),
  CONSTRAINT fk_attendance_excuse_student FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
  CONSTRAINT fk_attendance_excuse_subject FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
  CONSTRAINT fk_attendance_excuse_approved_by FOREIGN KEY (approved_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Approved absences that do not count against the student'
"""

# (object name, create statement, drop statement), in upgrade order.
OBJECTS = (
    ('lecture_sessions', LECTURE_SESSIONS, 'DROP TABLE lecture_sessions'),
    ('attendance_excuses', ATTENDANCE_EXCUSES, 'DROP TABLE attendance_excuses'),
    (
        'attendance.session_id',
        'ALTER TABLE attendance ADD COLUMN session_id int(11) DEFAULT NULL AFTER timetable_id',
        'ALTER TABLE attendance DROP COLUMN session_id',
    ),
    (
        'idx_attendance_session',
        'ALTER TABLE attendance ADD KEY idx_attendance_session (session_id)',
        'ALTER TABLE attendance DROP KEY idx_attendance_session',
    ),
    (
        'fk_attendance_session',
        'ALTER TABLE attendance ADD CONSTRAINT fk_attendance_session FOREIGN KEY (session_id) '
        'REFERENCES lecture_sessions (id) ON DELETE RESTRICT',
        'ALTER TABLE attendance DROP FOREIGN KEY fk_attendance_session',
    ),
)


def _existing():
    bind = op.get_bind()
    found = set()
    rows = bind.execute(sa.text(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME IN ('lecture_sessions', 'attendance_excuses')"
    )).fetchall()
    found.update(row[0] for row in rows)
    if bind.execute(sa.text(
        "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'session_id'"
    )).fetchone():
        found.add('attendance.session_id')
    if bind.execute(sa.text(
        "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'attendance' AND INDEX_NAME = 'idx_attendance_session'"
    )).fetchone():
        found.add('idx_attendance_session')
    if bind.execute(sa.text(
        "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'attendance' AND CONSTRAINT_NAME = 'fk_attendance_session' AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
    )).fetchone():
        found.add('fk_attendance_session')
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
