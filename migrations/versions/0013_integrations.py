"""Integrations: API keys, webhook endpoints and deliveries, SSO settings and identities.

Revision ID: 0013_integrations
Revises: 0012_lab_batches
Create Date: 2026-11-09

api_keys authenticate the public /api/v1: the key itself is shown once and
only its SHA-256 is stored; key_prefix finds the row. scopes is a
space-separated list (timetable:read attendance:read people:read
catalog:read). webhook_endpoints are the URLs a tenant subscribes to
events with (secret encrypted by the app, used for the HMAC signature);
webhook_deliveries is the outbox: triggers insert one row per subscribed
endpoint in the same transaction as the change and the webhook worker
claims and posts them with the shared job-claim columns. sso_settings is
one row per tenant (the OIDC provider staff sign in with); sso_identities
links a provider subject to a user. Each table is created only when
missing; the downgrade drops only what exists.
"""

import sqlalchemy as sa
from alembic import op

revision = '0013_integrations'
down_revision = '0012_lab_batches'
branch_labels = None
depends_on = None

API_KEYS = """
CREATE TABLE api_keys (
  id int(11) NOT NULL AUTO_INCREMENT,
  name varchar(100) NOT NULL,
  key_prefix char(12) NOT NULL,
  key_hash char(64) NOT NULL COMMENT 'SHA-256 of the full key; the key itself is never stored',
  scopes varchar(255) NOT NULL DEFAULT '' COMMENT 'space-separated scopes',
  created_by int(11) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  expires_at datetime DEFAULT NULL,
  last_used_at datetime DEFAULT NULL,
  revoked_at datetime DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_api_key_prefix (key_prefix),
  KEY fk_api_key_creator (created_by),
  CONSTRAINT fk_api_key_creator FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Keys for the public /api/v1'
"""

WEBHOOK_ENDPOINTS = """
CREATE TABLE webhook_endpoints (
  id int(11) NOT NULL AUTO_INCREMENT,
  name varchar(100) NOT NULL,
  url varchar(500) NOT NULL,
  secret_enc text NOT NULL COMMENT 'Fernet token; see services/secrets_at_rest.py',
  events varchar(255) NOT NULL DEFAULT '' COMMENT 'space-separated event names, or * for all',
  is_active tinyint(1) NOT NULL DEFAULT 1,
  created_by int(11) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  last_delivery_at datetime DEFAULT NULL,
  last_status varchar(20) DEFAULT NULL,
  PRIMARY KEY (id),
  KEY fk_webhook_endpoint_creator (created_by),
  CONSTRAINT fk_webhook_endpoint_creator FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='URLs that receive webhook events'
"""

WEBHOOK_DELIVERIES = """
CREATE TABLE webhook_deliveries (
  id bigint(20) NOT NULL AUTO_INCREMENT,
  endpoint_id int(11) NOT NULL,
  event varchar(60) NOT NULL,
  delivery_key char(36) NOT NULL COMMENT 'uuid sent as X-Timetable-Delivery',
  payload_json mediumtext NOT NULL,
  status enum('queued','running','sent','failed') NOT NULL DEFAULT 'queued',
  attempts int(11) NOT NULL DEFAULT 0,
  response_status int(11) DEFAULT NULL,
  last_error varchar(500) DEFAULT NULL,
  progress tinyint(4) NOT NULL DEFAULT 0,
  locked_by varchar(64) DEFAULT NULL,
  heartbeat_at datetime DEFAULT NULL,
  available_at datetime DEFAULT NULL COMMENT 'UTC; the worker posts at or after this time (NULL = now)',
  sent_at datetime DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_webhook_delivery_key (delivery_key),
  KEY idx_webhook_delivery_queue (status, available_at, id),
  KEY idx_webhook_delivery_endpoint (endpoint_id, created_at),
  CONSTRAINT fk_webhook_delivery_endpoint FOREIGN KEY (endpoint_id) REFERENCES webhook_endpoints (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Outgoing webhook posts (outbox)'
"""

SSO_SETTINGS = """
CREATE TABLE sso_settings (
  id int(11) NOT NULL,
  enabled tinyint(1) NOT NULL DEFAULT 0,
  provider varchar(20) NOT NULL DEFAULT 'oidc' COMMENT 'google, microsoft or oidc',
  issuer varchar(255) DEFAULT NULL,
  client_id varchar(255) DEFAULT NULL,
  client_secret_enc text DEFAULT NULL COMMENT 'Fernet token; see services/secrets_at_rest.py',
  allowed_domains varchar(500) DEFAULT NULL COMMENT 'space-separated email domains; empty = any verified email',
  link_by_email tinyint(1) NOT NULL DEFAULT 1 COMMENT 'match a first sign-in to a staff account by verified email',
  button_label varchar(60) DEFAULT NULL,
  updated_by int(11) DEFAULT NULL,
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  KEY fk_sso_settings_user (updated_by),
  CONSTRAINT fk_sso_settings_user FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One row (id=1): the OIDC provider staff sign in with'
"""

SSO_IDENTITIES = """
CREATE TABLE sso_identities (
  id int(11) NOT NULL AUTO_INCREMENT,
  user_id int(11) NOT NULL,
  issuer varchar(255) NOT NULL,
  subject varchar(255) NOT NULL,
  email varchar(190) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  last_login_at datetime DEFAULT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sso_identity (issuer, subject),
  KEY idx_sso_identity_user (user_id),
  CONSTRAINT fk_sso_identity_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Which provider subject signs in as which user'
"""

TABLES = (
    ('api_keys', API_KEYS),
    ('webhook_endpoints', WEBHOOK_ENDPOINTS),
    ('webhook_deliveries', WEBHOOK_DELIVERIES),
    ('sso_settings', SSO_SETTINGS),
    ('sso_identities', SSO_IDENTITIES),
)
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
