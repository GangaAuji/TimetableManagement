"""Room bookings on the timetable's clash ledger (docs/TIMETABLE.md, "Room bookings").

Revision ID: 0018_bookings
Revises: 0017_timetable_versions

`bookings`: a room reserved for an event, exam, maintenance or an outside party, either on one
date (`booking_date`) or every week on one weekday (`day_of_week`, until `repeat_until`). Only
`approved` rows block the room; the generator, the joint solver and manual slots read them
beside `timetable`. `institution_id` is the requesting institution: a room shared to it
(Institutions, resource_shares) is bookable by it, and the room's owner approves.
"""

import sqlalchemy as sa
from alembic import op

revision = '0018_bookings'
down_revision = '0017_timetable_versions'
branch_labels = None
depends_on = None

BOOKINGS = """
CREATE TABLE bookings (
  id int(11) NOT NULL AUTO_INCREMENT,
  institution_id int(11) NOT NULL DEFAULT 1 COMMENT 'the institution that asked for the room',
  room_id int(11) NOT NULL,
  title varchar(120) NOT NULL,
  kind enum('event','exam','maintenance','external') NOT NULL DEFAULT 'event',
  booking_date date DEFAULT NULL COMMENT 'one-off booking; NULL when weekly',
  day_of_week enum('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday') DEFAULT NULL COMMENT 'weekly booking; NULL when one-off',
  repeat_until date DEFAULT NULL COMMENT 'last date a weekly booking applies; NULL = open-ended',
  start_time time NOT NULL,
  end_time time NOT NULL,
  notes varchar(500) NOT NULL DEFAULT '',
  status enum('requested','approved','rejected','cancelled') NOT NULL DEFAULT 'requested',
  booked_by int(11) DEFAULT NULL,
  decided_by int(11) DEFAULT NULL,
  decided_at timestamp NULL DEFAULT NULL,
  decision_note varchar(300) NOT NULL DEFAULT '',
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  KEY idx_bookings_room_date (room_id, status, booking_date),
  KEY idx_bookings_room_day (room_id, status, day_of_week),
  KEY idx_bookings_institution (institution_id, status, created_at),
  KEY fk_bookings_booked_by (booked_by),
  KEY fk_bookings_decided_by (decided_by),
  CONSTRAINT fk_bookings_room FOREIGN KEY (room_id) REFERENCES rooms (id) ON DELETE CASCADE,
  CONSTRAINT fk_bookings_institution FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE,
  CONSTRAINT fk_bookings_booked_by FOREIGN KEY (booked_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT fk_bookings_decided_by FOREIGN KEY (decided_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Room bookings beside the timetable'
"""

# (name, create, drop); applied in order, dropped in reverse.
OBJECTS = (
    ('bookings', BOOKINGS, 'DROP TABLE bookings'),
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
