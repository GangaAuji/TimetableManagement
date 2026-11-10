"""Exam sessions, seating and invigilation (docs/ACADEMICS.md).

Revision ID: 0022_exam_schedule
Revises: 0021_assessment

Read and written only while capability `exams` is on. A saved session occupies
its rooms on the booking ledger while capability `bookings` is on.
"""

import sqlalchemy as sa
from alembic import op

revision = '0022_exam_schedule'
down_revision = '0021_assessment'
branch_labels = None
depends_on = None

EXAMS = """
CREATE TABLE exams (
  id int(11) NOT NULL AUTO_INCREMENT,
  term_id int(11) DEFAULT NULL,
  name varchar(80) NOT NULL,
  kind enum('internal','university','practical') NOT NULL,
  seating_gap tinyint NOT NULL DEFAULT 0,
  students_per_room smallint DEFAULT NULL,
  created_by int(11) DEFAULT NULL,
  created_at timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  KEY fk_exam_term (term_id),
  KEY fk_exam_creator (created_by),
  CONSTRAINT fk_exam_term FOREIGN KEY (term_id) REFERENCES academic_terms (id) ON DELETE SET NULL,
  CONSTRAINT fk_exam_creator FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One exam timetable (internal, university or practical)'
"""

SESSIONS = """
CREATE TABLE exam_sessions (
  id int(11) NOT NULL AUTO_INCREMENT,
  exam_id int(11) NOT NULL,
  subject_id int(11) NOT NULL,
  exam_date date NOT NULL,
  start_time time NOT NULL,
  end_time time NOT NULL,
  PRIMARY KEY (id),
  KEY fk_exam_session_exam (exam_id),
  KEY fk_exam_session_subject (subject_id),
  KEY idx_exam_session_date (exam_date, start_time),
  CONSTRAINT fk_exam_session_exam FOREIGN KEY (exam_id) REFERENCES exams (id) ON DELETE CASCADE,
  CONSTRAINT fk_exam_session_subject FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One paper at one date and time'
"""

COHORTS = """
CREATE TABLE exam_session_cohorts (
  id int(11) NOT NULL AUTO_INCREMENT,
  exam_session_id int(11) NOT NULL,
  class_id int(11) NOT NULL,
  division_id int(11) DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_exam_cohort (exam_session_id, class_id, division_id),
  KEY fk_exam_cohort_class (class_id),
  KEY fk_exam_cohort_division (division_id),
  CONSTRAINT fk_exam_cohort_session FOREIGN KEY (exam_session_id) REFERENCES exam_sessions (id) ON DELETE CASCADE,
  CONSTRAINT fk_exam_cohort_class FOREIGN KEY (class_id) REFERENCES classes (id) ON DELETE CASCADE,
  CONSTRAINT fk_exam_cohort_division FOREIGN KEY (division_id) REFERENCES divisions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Cohorts sitting one exam session'
"""

ROOMS = """
CREATE TABLE exam_session_rooms (
  id int(11) NOT NULL AUTO_INCREMENT,
  exam_session_id int(11) NOT NULL,
  room_id int(11) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_exam_session_room (exam_session_id, room_id),
  KEY fk_exam_room_room (room_id),
  CONSTRAINT fk_exam_room_session FOREIGN KEY (exam_session_id) REFERENCES exam_sessions (id) ON DELETE CASCADE,
  CONSTRAINT fk_exam_room_room FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Rooms used by one exam session'
"""

SEATS = """
CREATE TABLE exam_seats (
  id int(11) NOT NULL AUTO_INCREMENT,
  exam_session_id int(11) NOT NULL,
  room_id int(11) NOT NULL,
  student_id int(11) NOT NULL,
  seat_no smallint NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_exam_seat_student (exam_session_id, student_id),
  UNIQUE KEY uq_exam_seat_place (exam_session_id, room_id, seat_no),
  KEY fk_exam_seat_room (room_id),
  KEY fk_exam_seat_student (student_id),
  CONSTRAINT fk_exam_seat_session FOREIGN KEY (exam_session_id) REFERENCES exam_sessions (id) ON DELETE CASCADE,
  CONSTRAINT fk_exam_seat_room FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE RESTRICT,
  CONSTRAINT fk_exam_seat_student FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Seat of one student in an exam room'
"""

DUTIES = """
CREATE TABLE invigilation_duties (
  id int(11) NOT NULL AUTO_INCREMENT,
  exam_session_id int(11) NOT NULL,
  faculty_id int(11) NOT NULL,
  room_id int(11) NOT NULL,
  role enum('chief','invigilator') NOT NULL DEFAULT 'invigilator',
  PRIMARY KEY (id),
  UNIQUE KEY uq_exam_duty (exam_session_id, faculty_id, room_id),
  KEY fk_exam_duty_faculty (faculty_id),
  KEY fk_exam_duty_room (room_id),
  CONSTRAINT fk_exam_duty_session FOREIGN KEY (exam_session_id) REFERENCES exam_sessions (id) ON DELETE CASCADE,
  CONSTRAINT fk_exam_duty_faculty FOREIGN KEY (faculty_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_exam_duty_room FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Invigilation duty for one room of an exam session'
"""

OBJECTS = (
    ('exams', EXAMS, 'DROP TABLE exams'),
    ('exam_sessions', SESSIONS, 'DROP TABLE exam_sessions'),
    ('exam_session_cohorts', COHORTS, 'DROP TABLE exam_session_cohorts'),
    ('exam_session_rooms', ROOMS, 'DROP TABLE exam_session_rooms'),
    ('exam_seats', SEATS, 'DROP TABLE exam_seats'),
    ('invigilation_duties', DUTIES, 'DROP TABLE invigilation_duties'),
)

_TABLES = {name for name, _, _ in OBJECTS}
_DROP_ORDER = (
    'exam_seats', 'invigilation_duties', 'exam_session_rooms', 'exam_session_cohorts', 'exam_sessions', 'exams',
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
