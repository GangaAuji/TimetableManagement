"""face_consents and face_recognition_audit.

Revision ID: 0010_face_safeguards
Revises: 0009_worker_claims
Create Date: 2026-11-09

face_consents records that a person agreed to face recognition (notice
version, when, by whom) and when they withdrew. Enrolment and recognition
are refused without an active row when FACE_CONSENT_REQUIRED is on, and a
withdrawal deletes the person's templates. face_recognition_audit keeps one
row per recognition event the devices send, accepted or rejected, with the
confidence, liveness score, frame hash and reason, so every decision can be
reviewed. Templates themselves are encrypted in place by the app
(services/face/templates.py); no column changes are needed for that. Each
table is created only when missing; the downgrade drops only what exists.
"""

import sqlalchemy as sa
from alembic import op

revision = '0010_face_safeguards'
down_revision = '0009_worker_claims'
branch_labels = None
depends_on = None

FACE_CONSENTS = """
CREATE TABLE face_consents (
  id int(11) NOT NULL AUTO_INCREMENT,
  user_id int(11) NOT NULL,
  notice_version varchar(40) NOT NULL,
  given_at datetime NOT NULL,
  withdrawn_at datetime DEFAULT NULL,
  recorded_by int(11) DEFAULT NULL COMMENT 'users.id of who recorded it; NULL for the person themselves',
  source enum('web','mobile','cli','admin') NOT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  KEY idx_face_consent_user (user_id, withdrawn_at),
  KEY fk_face_consent_recorded_by (recorded_by),
  CONSTRAINT fk_face_consent_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_face_consent_recorded_by FOREIGN KEY (recorded_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Consent to face recognition, per person and notice version'
"""

FACE_RECOGNITION_AUDIT = """
CREATE TABLE face_recognition_audit (
  id bigint(20) NOT NULL AUTO_INCREMENT,
  device_id varchar(128) NOT NULL,
  event_uuid varchar(64) DEFAULT NULL,
  user_id int(11) DEFAULT NULL COMMENT 'users.id of the recognised person, when known',
  student_id int(11) DEFAULT NULL,
  timetable_id int(11) DEFAULT NULL,
  attendance_date date DEFAULT NULL,
  confidence decimal(5,4) DEFAULT NULL,
  liveness_score decimal(5,4) DEFAULT NULL,
  frame_hash varchar(64) DEFAULT NULL,
  template_age_days int(11) DEFAULT NULL,
  decision enum('accepted','rejected') NOT NULL,
  reason varchar(64) NOT NULL DEFAULT 'ok',
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  KEY idx_face_audit_device_time (device_id, created_at),
  KEY idx_face_audit_frame (frame_hash),
  KEY idx_face_audit_event (event_uuid),
  KEY idx_face_audit_user_time (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Every face recognition decision the server made'
"""

TABLES = (('face_consents', FACE_CONSENTS), ('face_recognition_audit', FACE_RECOGNITION_AUDIT))
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
