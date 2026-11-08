"""Seeders on a fresh *_test database at head: full defaults, idempotency, and customisations surviving."""

import pytest

from seeders.data.permissions import PERMISSIONS
from seeders.data.roles import ROLES
from seeders.role_permissions import RolePermissionsSeeder
from tests.integration.live_helpers import database_connection, drop, migrate, recreate, scratch_name, server_connection
from tests.integration.seed_helpers import default_pairs, execute, mapping, seed, snapshot

pytestmark = pytest.mark.live_db


@pytest.fixture
def fresh():
    server = server_connection()
    cursor = server.cursor()
    name = scratch_name('seed_fresh')
    connection = None
    try:
        recreate(cursor, name)
        migrate(name, 'upgrade', 'head')
        connection = database_connection(name)
        yield connection
    finally:
        if connection is not None:
            connection.close()
        drop(cursor, name)
        server.close()


def test_fresh_install_gets_the_full_default_mapping(fresh):
    results = seed(fresh)
    assert results['roles'].added == len(ROLES)
    assert results['permissions'].added == len(PERMISSIONS)
    role_permissions = results['role_permissions']
    assert role_permissions.fresh is True
    assert role_permissions.added == len(default_pairs())
    assert role_permissions.pending == [] and role_permissions.lines == []
    assert mapping(fresh) == default_pairs()

    rows = snapshot(fresh)
    levels = {row[1]: row[5] for row in rows['roles']}
    assert levels == {role.name: role.level for role in ROLES}
    assert len(rows['seed_history']) == len(default_pairs()) + 1


def test_seeding_twice_gives_identical_rows(fresh):
    seed(fresh)
    first = snapshot(fresh)
    again = seed(fresh)
    assert all(result.added == 0 for result in again.values())
    assert again['role_permissions'].earlier == len(default_pairs())
    assert snapshot(fresh) == first
    seed(fresh, apply_role_defaults=True)
    assert snapshot(fresh) == first


def test_a_customised_role_survives_reseeding(fresh):
    seed(fresh)
    execute(fresh, "DELETE rp FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                   "JOIN permissions p ON p.id = rp.permission_id WHERE r.name = 'Teacher' AND p.name = 'timetable_view'")
    execute(fresh, "INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r, permissions p "
                   "WHERE r.name = 'Teacher' AND p.name = 'reports_view'")
    execute(fresh, "UPDATE permissions SET description = 'Our own wording', module = 'Custom' WHERE name = 'reports_view'")
    execute(fresh, "UPDATE roles SET hierarchy_level = 7, description = 'Department head' WHERE name = 'HOD'")
    customised = snapshot(fresh)
    teacher = {permission for role, permission in mapping(fresh) if role == 'Teacher'}

    seed(fresh)
    seed(fresh, apply_role_defaults=True)

    assert snapshot(fresh) == customised
    assert {permission for role, permission in mapping(fresh) if role == 'Teacher'} == teacher
    assert 'timetable_view' not in teacher and 'reports_view' in teacher


def test_a_default_from_a_later_release_is_granted_once(fresh):
    seed(fresh)
    later = {'Teacher': {'attendance_view': 2}}
    cursor = fresh.cursor()
    result = RolePermissionsSeeder(defaults=later).run(cursor)
    fresh.commit()
    assert result.added == 1 and result.pending == []
    assert ('Teacher', 'attendance_view') in mapping(fresh)

    execute(fresh, "DELETE rp FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                   "JOIN permissions p ON p.id = rp.permission_id WHERE r.name = 'Teacher' AND p.name = 'attendance_view'")
    result = RolePermissionsSeeder(defaults=later, apply_defaults=True).run(cursor)
    fresh.commit()
    cursor.close()
    assert result.added == 0 and result.earlier == 1
    assert ('Teacher', 'attendance_view') not in mapping(fresh)
