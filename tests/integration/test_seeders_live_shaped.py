"""Seeders on a copy shaped like college_timetable_db: its schema plus its access rows.

The copy is built from two gitignored files in sql/ (see docs/DATABASE.md):
the structure-only dump taken at 0003_security_schema, and a data-only dump of
roles, permissions, role_permissions, permission_groups and branding_settings.
The tests run in order on one scratch *_test database, which is dropped at the end.
"""

import re
from pathlib import Path

import pytest

from core.schema.sqlfile import read_statements
from seeders.data.permissions import PERMISSIONS
from tests.integration.live_helpers import (
    database_connection,
    drop,
    migrate,
    recreate,
    scratch_name,
    server_connection,
    without_definer,
)
from seeders.role_permissions import BASELINE
from tests.integration.seed_helpers import default_pairs, execute, ledger, mapping, seed, snapshot, unique_keys

pytestmark = pytest.mark.live_db

SQL = Path(__file__).resolve().parents[2] / 'sql'
LIVE_SCHEMA = SQL / 'college_timetable_db.live-schema.sql'
ACCESS_DATA = SQL / 'college_timetable_db.access-data.sql'
DUMPED_TABLES = {'roles', 'permissions', 'role_permissions', 'permission_groups', 'branding_settings'}
NEW_PERMISSIONS = {'attendance_view_faculty', 'attendance_manage_faculty'}
PLACEHOLDER_EMAIL = 'support@institution.edu'


@pytest.fixture(scope='module')
def copy():
    for path in (LIVE_SCHEMA, ACCESS_DATA):
        if not path.exists():
            pytest.skip(f'{path.name} is not in sql/.')
    server = server_connection()
    cursor = server.cursor()
    name = scratch_name('seed_live_copy')
    connection = None
    try:
        recreate(cursor, name)
        cursor.execute(f'USE `{name}`')
        for statement in read_statements(LIVE_SCHEMA):
            cursor.execute(without_definer(statement))
        cursor.execute("INSERT INTO alembic_version (version_num) VALUES ('0003_security_schema')")
        migrate(name, 'upgrade', 'head')
        cursor.execute(f'USE `{name}`')
        for statement in read_statements(ACCESS_DATA):
            cursor.execute(statement)
        connection = database_connection(name)
        yield connection
    finally:
        if connection is not None:
            connection.close()
        cursor.execute('USE information_schema')
        drop(cursor, name)
        server.close()


def test_the_access_dump_holds_no_personal_data():
    if not ACCESS_DATA.exists():
        pytest.skip(f'{ACCESS_DATA.name} is not in sql/.')
    statements = read_statements(ACCESS_DATA)
    tables = set()
    for statement in statements:
        if statement.startswith('/*!'):
            continue
        found = re.match(r'INSERT INTO `(\w+)`', statement)
        assert found, statement[:80]
        tables.add(found.group(1))
    assert tables <= DUMPED_TABLES
    text = ACCESS_DATA.read_text(encoding='utf-8')
    assert set(re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text)) <= {PLACEHOLDER_EMAIL}
    assert not re.search(r'pbkdf2:|scrypt:|argon2:', text)


def test_first_run_adds_no_role_permissions_and_lists_what_it_would_add(copy):
    before = snapshot(copy)
    live_pairs = mapping(copy)
    results = seed(copy)
    after = snapshot(copy)

    assert results['roles'].added == 0
    assert results['branding_settings'].added == 0
    assert results['permissions'].added == 2
    added = {row[1] for row in after['permissions']} - {row[1] for row in before['permissions']}
    assert added == NEW_PERMISSIONS
    assert after['roles'] == before['roles']
    assert after['branding_settings'] == before['branding_settings']
    assert after['role_permissions'] == before['role_permissions']

    role_permissions = results['role_permissions']
    assert role_permissions.fresh is False and role_permissions.added == 0
    would_add = default_pairs() - live_pairs
    assert set(role_permissions.pending) == would_add
    assert role_permissions.present == len(default_pairs() & live_pairs)
    by_role = {}
    for role, permission in would_add:
        by_role.setdefault(role, set()).add(permission)
    assert {role: len(names) for role, names in by_role.items()} == {'Admin': 14, 'HOD': 5, 'Super Admin': 2}
    assert NEW_PERMISSIONS <= by_role['Admin'] and by_role['HOD'] >= {'attendance_view_faculty'}
    assert any('--apply-role-defaults' in line for line in role_permissions.lines)

    second = seed(copy)
    assert second['permissions'].added == 0 and second['role_permissions'].added == 0
    assert set(second['role_permissions'].pending) == would_add
    assert snapshot(copy) == after


def _assert_ledger_matches_mappings(connection, handled):
    items = ledger(connection)
    assert len(items) == len(set(items)), 'duplicate ledger rows'
    assert items.count(BASELINE) == 1
    pairs = {tuple(item.split(':', 1)) for item in items if item != BASELINE}
    assert len(pairs) == handled
    assert pairs <= mapping(connection), 'ledger rows with no mapping'
    assert pairs == mapping(connection) & default_pairs()


def test_the_ledger_has_one_row_per_handled_mapping(copy):
    assert unique_keys(copy, 'seed_history')['uq_seed_history_item'] == ['seeder', 'item']
    results = seed(copy)['role_permissions']
    assert results.added == 0
    _assert_ledger_matches_mappings(copy, results.present + results.earlier)
    assert len(ledger(copy)) == len(mapping(copy)) + 1


def test_apply_role_defaults_grants_them_once(copy):
    live_pairs = mapping(copy)
    results = seed(copy, apply_role_defaults=True)
    granted = mapping(copy) - live_pairs
    assert results['role_permissions'].added == len(granted) == 21
    assert granted == default_pairs() - live_pairs
    assert results['role_permissions'].pending == []

    _assert_ledger_matches_mappings(copy, len(mapping(copy)))
    applied = snapshot(copy)
    assert seed(copy, apply_role_defaults=True)['role_permissions'].added == 0
    assert seed(copy)['role_permissions'].added == 0
    assert snapshot(copy) == applied


def test_a_removed_permission_stays_removed(copy):
    execute(copy, "DELETE rp FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                  "JOIN permissions p ON p.id = rp.permission_id WHERE r.name = 'HOD' AND p.name = 'faculty_view_proxy'")
    execute(copy, "DELETE rp FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                  "JOIN permissions p ON p.id = rp.permission_id WHERE r.name = 'Admin' AND p.name = 'rooms_view_room'")
    customised = snapshot(copy)
    seed(copy)
    seed(copy, apply_role_defaults=True)
    assert snapshot(copy) == customised
    pairs = mapping(copy)
    assert ('HOD', 'faculty_view_proxy') not in pairs and ('Admin', 'rooms_view_room') not in pairs
    assert {permission.name for permission in PERMISSIONS} <= {row[1] for row in customised['permissions']}
