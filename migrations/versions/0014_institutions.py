"""Institutions: several colleges inside one tenant.

Revision ID: 0014_institutions
Revises: 0013_integrations
Create Date: 2026-11-09

Adds the level between the tenant and its departments (see
docs/DESIGN_INSTITUTIONS.md): `organizations` (one row), `institutions`,
`institution_memberships` (which staff user belongs to which institution,
with a role) and `resource_shares` (which institutions may use a listed
room or faculty member). `departments` and `rooms` get `institution_id`
(NOT NULL, DEFAULT 1 so older code paths that insert without naming an
institution still work); `rooms` and `faculty` get `sharing`
(private | listed | organization).

The upgrade then backfills: one organization and one institution (id 1,
named after branding `site_title`), every department and room in it, and a
primary membership for every non-student user. Each object is created only
when missing and the backfill only runs on empty tables, so re-running is
safe. The downgrade drops the columns and tables; which college owned what
is lost, so it is destructive.
"""

import sqlalchemy as sa
from alembic import op

revision = '0014_institutions'
down_revision = '0013_integrations'
branch_labels = None
depends_on = None

ORGANIZATIONS = """
CREATE TABLE organizations (
  id int(11) NOT NULL AUTO_INCREMENT,
  name varchar(150) NOT NULL,
  short_name varchar(40) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='One row: the university or college group this tenant is'
"""

INSTITUTIONS = """
CREATE TABLE institutions (
  id int(11) NOT NULL AUTO_INCREMENT,
  organization_id int(11) NOT NULL DEFAULT 1,
  name varchar(150) NOT NULL,
  code varchar(20) NOT NULL,
  short_name varchar(40) DEFAULT NULL,
  is_active tinyint(1) NOT NULL DEFAULT 1,
  sort_order int(11) NOT NULL DEFAULT 0,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  updated_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_institution_code (code),
  KEY fk_institution_org (organization_id),
  CONSTRAINT fk_institution_org FOREIGN KEY (organization_id) REFERENCES organizations (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Colleges / schools / campuses of the organization'
"""

MEMBERSHIPS = """
CREATE TABLE institution_memberships (
  id int(11) NOT NULL AUTO_INCREMENT,
  user_id int(11) NOT NULL,
  institution_id int(11) NOT NULL,
  role varchar(50) NOT NULL,
  department_id int(11) DEFAULT NULL,
  is_primary tinyint(1) NOT NULL DEFAULT 0,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_membership (user_id, institution_id),
  KEY idx_membership_institution (institution_id),
  KEY fk_membership_department (department_id),
  CONSTRAINT fk_membership_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_membership_institution FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE,
  CONSTRAINT fk_membership_department FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Which staff user belongs to which institution, with what role'
"""

SHARES = """
CREATE TABLE resource_shares (
  id int(11) NOT NULL AUTO_INCREMENT,
  resource_type enum('room','faculty') NOT NULL,
  resource_id int(11) NOT NULL,
  institution_id int(11) NOT NULL,
  created_by int(11) DEFAULT NULL,
  created_at timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (id),
  UNIQUE KEY uq_resource_share (resource_type, resource_id, institution_id),
  KEY idx_resource_share_institution (institution_id, resource_type),
  KEY fk_resource_share_creator (created_by),
  CONSTRAINT fk_resource_share_institution FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE,
  CONSTRAINT fk_resource_share_creator FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Institutions that may use a listed room or faculty member'
"""

# (name, create, drop); applied in order, dropped in reverse.
OBJECTS = (
    ('organizations', ORGANIZATIONS, 'DROP TABLE organizations'),
    ('institutions', INSTITUTIONS, 'DROP TABLE institutions'),
    (
        'departments.institution_id',
        "ALTER TABLE departments ADD COLUMN institution_id int(11) NOT NULL DEFAULT 1 AFTER id",
        'ALTER TABLE departments DROP COLUMN institution_id',
    ),
    (
        'fk_department_institution',
        'ALTER TABLE departments ADD CONSTRAINT fk_department_institution FOREIGN KEY (institution_id) '
        'REFERENCES institutions (id)',
        'ALTER TABLE departments DROP FOREIGN KEY fk_department_institution',
    ),
    (
        'rooms.institution_id',
        "ALTER TABLE rooms ADD COLUMN institution_id int(11) NOT NULL DEFAULT 1 AFTER id",
        'ALTER TABLE rooms DROP COLUMN institution_id',
    ),
    (
        'fk_room_institution',
        'ALTER TABLE rooms ADD CONSTRAINT fk_room_institution FOREIGN KEY (institution_id) REFERENCES institutions (id)',
        'ALTER TABLE rooms DROP FOREIGN KEY fk_room_institution',
    ),
    (
        'rooms.sharing',
        "ALTER TABLE rooms ADD COLUMN sharing enum('private','listed','organization') NOT NULL DEFAULT 'private' "
        "COMMENT 'who else may timetable this room' AFTER institution_id",
        'ALTER TABLE rooms DROP COLUMN sharing',
    ),
    (
        'faculty.sharing',
        "ALTER TABLE faculty ADD COLUMN sharing enum('private','listed','organization') NOT NULL DEFAULT 'private' "
        "COMMENT 'who else may allocate this person' AFTER department_id",
        'ALTER TABLE faculty DROP COLUMN sharing',
    ),
    ('institution_memberships', MEMBERSHIPS, 'DROP TABLE institution_memberships'),
    ('resource_shares', SHARES, 'DROP TABLE resource_shares'),
)

_TABLES = {name for name, _, _ in OBJECTS if '.' not in name and not name.startswith('fk_')}
_COLUMNS = {name for name, _, _ in OBJECTS if '.' in name}
_FOREIGN_KEYS = {
    'fk_department_institution': 'departments',
    'fk_room_institution': 'rooms',
}


def _existing():
    bind = op.get_bind()
    found = set()
    rows = bind.execute(sa.text(
        "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN :names"
    ).bindparams(sa.bindparam('names', expanding=True)), {'names': sorted(_TABLES)}).fetchall()
    found.update(row[0] for row in rows)
    for name in _COLUMNS:
        table, column = name.split('.')
        if bind.execute(sa.text(
            "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table AND COLUMN_NAME = :column"
        ), {'table': table, 'column': column}).fetchone():
            found.add(name)
    for name, table in _FOREIGN_KEYS.items():
        if bind.execute(sa.text(
            "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :table AND CONSTRAINT_NAME = :name AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
        ), {'table': table, 'name': name}).fetchone():
            found.add(name)
    return found


def upgrade_statements(existing):
    return [create for name, create, _ in OBJECTS if name not in existing]


def downgrade_statements(existing):
    return [drop for name, _, drop in reversed(OBJECTS) if name in existing]


def backfill_statements(*, organizations, institutions, memberships, title):
    """The data rows the upgrade adds; each only when its table is empty.

    Returns (before_foreign_keys, after_tables): the organization and the
    first institution must exist before the department/room foreign keys
    are added (existing rows already carry DEFAULT 1); memberships need
    their table.
    """
    before = []
    after = []
    if organizations == 0:
        before.append(('INSERT INTO organizations (id, name) VALUES (1, :title)', {'title': title}))
    if institutions == 0:
        before.append((
            "INSERT INTO institutions (id, organization_id, name, code, short_name, is_active, sort_order) "
            "VALUES (1, 1, :title, 'MAIN', NULL, 1, 0)",
            {'title': title},
        ))
    if memberships == 0:
        after.append((
            "INSERT INTO institution_memberships (user_id, institution_id, role, department_id, is_primary) "
            "SELECT u.id, 1, u.role, u.department_id, 1 FROM users u WHERE u.role <> 'Student'",
            {},
        ))
    return before, after


def _count(bind, table):
    return bind.execute(sa.text(f'SELECT COUNT(*) FROM `{table}`')).scalar() or 0


def _title(bind):
    row = bind.execute(sa.text(
        "SELECT setting_value FROM branding_settings WHERE setting_key = 'site_title'"
    )).fetchone() if bind.execute(sa.text(
        "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'branding_settings'"
    )).fetchone() else None
    title = (row[0] if row and row[0] else '').strip()
    return title[:150] or 'Institution'


def upgrade():
    bind = op.get_bind()
    existing = _existing()
    title = _title(bind)
    pending = {name for name, _, _ in OBJECTS if name not in existing}
    # Tables first, so the organization and institution rows can be written
    # before the foreign keys that point at them.
    for name, create, _ in OBJECTS:
        if name in pending and name in ('organizations', 'institutions'):
            op.execute(create)
    before, _ = backfill_statements(
        organizations=_count(bind, 'organizations'), institutions=_count(bind, 'institutions'),
        memberships=1, title=title,
    )
    for statement, params in before:
        bind.execute(sa.text(statement), params)
    for name, create, _ in OBJECTS:
        if name in pending and name not in ('organizations', 'institutions'):
            op.execute(create)
    _, after = backfill_statements(
        organizations=1, institutions=1, memberships=_count(bind, 'institution_memberships'), title=title,
    )
    for statement, params in after:
        bind.execute(sa.text(statement), params)


def downgrade():
    for statement in downgrade_statements(_existing()):
        op.execute(statement)
