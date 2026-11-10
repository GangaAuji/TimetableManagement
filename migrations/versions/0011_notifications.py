"""notifications outbox and per-tenant notification_settings.

Revision ID: 0011_notifications
Revises: 0010_face_safeguards
Create Date: 2026-11-09

notifications is an outbox: triggers (defaulter below threshold, lecture
cancelled, proxy assigned, not-marked digest, shift requests) insert a row
in the same transaction as the change; the notification worker claims rows
with the shared job-claim columns (status/progress/locked_by/heartbeat_at)
and sends them over SMTP. dedupe_key is unique so a trigger that fires
twice (close-day re-runs, double submits) queues one message.
notification_settings holds one row per tenant database: the SMTP account
to send from (password encrypted by the app) and which triggers are on.
Each table is created only when missing; the downgrade drops only what exists.
"""

import sqlalchemy as sa
from alembic import op

revision = '0011_notifications'
down_revision = '0010_face_safeguards'
branch_labels = None
depends_on = None

NOTIFICATIONS = """
CREATE TABLE notifications (
  id bigint(20) NOT NULL AUTO_INCREMENT,
  kind varchar(40) NOT NULL COMMENT 'defaulter, lecture_cancelled, proxy_assigned, not_marked_digest, shift_request, shift_decision, test',
  channel enum('email') NOT NULL DEFAULT 'email',
  recipient_user_id int(11) DEFAULT NULL,
  recipient_email varchar(190) DEFAULT NULL,
  subject varchar(200) NOT NULL,
  body text NOT NULL,
  payload_json text DEFAULT NULL,
  dedupe_key varchar(190) DEFAULT NULL,
  status enum('queued','running','sent','failed','skipped') NOT NULL DEFAULT 'queued',
  attempts int(11) NOT NULL DEFAULT 0,
  last_error varchar(500) DEFAULT NULL,
  progress tinyint(4) NOT NULL DEFAULT 0,
  locked_by varchar(64) DEFAULT NULL,
  heartbeat_at datetime DEFAULT NULL,
  available_at datetime DEFAULT NULL COMMENT 'UTC; the worker sends at or after this time (NULL = now)',
  sent_at datetime DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_notification_dedupe (dedupe_key),
  KEY idx_notification_queue (status, available_at, id),
  KEY idx_notification_recipient (recipient_user_id, created_at),
  KEY idx_notification_kind (kind, created_at),
  CONSTRAINT fk_notification_recipient FOREIGN KEY (recipient_user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Outgoing notifications (outbox)'
"""

NOTIFICATION_SETTINGS = """
CREATE TABLE notification_settings (
  id int(11) NOT NULL,
  enabled tinyint(1) NOT NULL DEFAULT 1,
  smtp_host varchar(190) DEFAULT NULL,
  smtp_port int(11) DEFAULT NULL,
  smtp_user varchar(190) DEFAULT NULL,
  smtp_password_enc text DEFAULT NULL COMMENT 'Fernet token; see services/secrets_at_rest.py',
  smtp_from varchar(190) DEFAULT NULL,
  smtp_starttls tinyint(1) NOT NULL DEFAULT 1,
  reply_to varchar(190) DEFAULT NULL,
  defaulter_alerts tinyint(1) NOT NULL DEFAULT 1,
  cancellation_alerts tinyint(1) NOT NULL DEFAULT 1,
  proxy_alerts tinyint(1) NOT NULL DEFAULT 1,
  not_marked_digest tinyint(1) NOT NULL DEFAULT 1,
  shift_alerts tinyint(1) NOT NULL DEFAULT 1,
  updated_by int(11) DEFAULT NULL,
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  KEY fk_notification_settings_user (updated_by),
  CONSTRAINT fk_notification_settings_user FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One row (id=1): SMTP account and trigger switches for this database'
"""

TABLES = (('notifications', NOTIFICATIONS), ('notification_settings', NOTIFICATION_SETTINGS))
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
