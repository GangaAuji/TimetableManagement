"""Who may manage which accounts and roles (security/authority.py), in the JSON API and the legacy routes.

roles.hierarchy_level: Super Admin 1, Admin 2, HOD 3, Teacher 4, Student 5. An
actor manages only accounts with a larger level; only a Super Admin manages a
Super Admin. Granting permissions needs users_manage_permissions, and only
permissions the actor holds.
"""

import pytest

from tests.http_helpers import SAME_ORIGIN, api, csrf_token, form_post, login

_ACCOUNT_RIGHTS = ('users_change_user', 'users_change_password', 'users_delete_user', 'users_add_user')


def _actor(factory, client, role='Admin', *permissions):
    actor = factory.user(role)
    for name in permissions:
        factory.grant(actor, name)
    login(client, actor)
    return actor


def _edit(client, user, **changes):
    payload = {'username': user['username'], 'role': user['role'], 'status': 'active', 'email': '',
               'department_id': None, 'is_hod': False}
    payload.update(changes)
    return api(client, 'POST', f'/api/users/{user["id"]}', json=payload)


def _row(factory, user):
    [row] = factory.query('SELECT role, status, password FROM users WHERE id = %s', (user['id'],))
    return row


def _held_and_unheld(factory):
    """One permission the Admin role holds and one it does not."""
    held = sorted(factory.role_permissions('Admin'))
    names = {row['name'] for row in factory.query('SELECT name FROM permissions')}
    unheld = sorted(names - set(held) - {'users_manage_permissions'})
    return held[0], unheld[0]


def _direct_grants(factory, user):
    return {row['name'] for row in factory.query(
        'SELECT p.name FROM user_permissions up JOIN permissions p ON p.id = up.permission_id '
        'WHERE up.user_id = %s AND up.is_active = 1', (user['id'],),
    )}


# Accounts, JSON API

@pytest.mark.parametrize('call', ('edit', 'deactivate', 'status', 'password', 'unlock'))
def test_an_admin_cannot_touch_a_super_admin(client, factory, call):
    root = factory.user('Super Admin')
    before = _row(factory, root)
    _actor(factory, client, 'Admin', *_ACCOUNT_RIGHTS)
    if call == 'edit':
        response = _edit(client, root, role='Admin')
    else:
        response = api(client, 'POST', f'/api/users/{root["id"]}/{call}')
    assert response.status_code == 403, response.get_data(as_text=True)[:300]
    assert _row(factory, root) == before


def test_an_admin_cannot_manage_another_admin(client, factory):
    other = factory.user('Admin')
    _actor(factory, client, 'Admin', *_ACCOUNT_RIGHTS)
    assert _edit(client, other, status='inactive').status_code == 403
    assert api(client, 'POST', f'/api/users/{other["id"]}/password').status_code == 403
    assert _row(factory, other)['status'] == 'active'


@pytest.mark.parametrize('role', ('Admin', 'Super Admin'))
def test_an_admin_cannot_raise_an_account_to_their_level_or_above(client, factory, role):
    teacher = factory.user('Teacher')
    _actor(factory, client, 'Admin', *_ACCOUNT_RIGHTS)
    assert _edit(client, teacher, role=role).status_code == 403
    assert _row(factory, teacher)['role'] == 'Teacher'
    response = api(client, 'POST', '/api/users', json={'username': 'climber_1', 'password': 'Harness-Pass-9', 'role': role})
    assert response.status_code == 403
    assert factory.query("SELECT 1 FROM users WHERE username = 'climber_1'") == []


def test_an_admin_manages_junior_accounts(client, factory):
    teacher = factory.user('Teacher')
    _actor(factory, client, 'Admin', *_ACCOUNT_RIGHTS)
    assert _edit(client, teacher, email='moved@example.org').status_code == 200
    assert api(client, 'POST', f'/api/users/{teacher["id"]}/password').status_code == 200
    assert api(client, 'POST', f'/api/users/{teacher["id"]}/status').status_code == 200


def test_a_super_admin_manages_another_super_admin(client, factory):
    other = factory.user('Super Admin')
    _actor(factory, client, 'Super Admin')
    assert _edit(client, other, email='root2@example.org').status_code == 200
    assert api(client, 'POST', f'/api/users/{other["id"]}/password').status_code == 200
    assert api(client, 'POST', f'/api/users/{other["id"]}/deactivate').status_code == 200
    assert _row(factory, other)['status'] == 'inactive'


def test_the_last_active_super_admin_cannot_be_removed(client, factory):
    root = _actor(factory, client, 'Super Admin')
    assert api(client, 'POST', f'/api/users/{root["id"]}/deactivate').status_code == 403
    assert api(client, 'POST', f'/api/users/{root["id"]}/status').status_code == 403
    assert _edit(client, root, role='Admin').status_code == 403
    assert _row(factory, root)['role'] == 'Super Admin'


def test_a_super_admin_may_step_down_when_another_remains(client, factory):
    factory.user('Super Admin')
    root = _actor(factory, client, 'Super Admin')
    assert _edit(client, root, role='Admin').status_code == 200
    assert _row(factory, root)['role'] == 'Admin'


def test_bulk_actions_refuse_a_protected_account(client, factory):
    other = factory.user('Admin')
    teacher = factory.user('Teacher')
    _actor(factory, client, 'Admin', *_ACCOUNT_RIGHTS)
    response = api(client, 'POST', '/api/users/bulk', json={'action': 'deactivate', 'ids': [teacher['id'], other['id']]})
    assert response.status_code == 403
    assert _row(factory, teacher)['status'] == 'active'


# Permission grants, JSON API

def test_granting_needs_users_manage_permissions(client, factory):
    teacher = factory.user('Teacher')
    held, _ = _held_and_unheld(factory)
    _actor(factory, client, 'Admin', 'users_change_user')
    group = factory.insert('permission_groups', name='Harness group')
    for path, payload in (
        (f'/api/users/{teacher["id"]}/permissions', {'permission_name': held}),
        (f'/api/users/{teacher["id"]}/permissions/bulk', {'permission_names': [held]}),
        (f'/api/users/{teacher["id"]}/groups', {'group_id': group}),
    ):
        response = api(client, 'POST', path, json=payload)
        assert response.status_code == 403, path
        assert response.get_json()['error']['code'] == 'forbidden'
    assert _direct_grants(factory, teacher) == set()


def test_users_manage_permissions_is_in_the_canon_and_granted_to_no_role_but_super_admin(factory):
    from seeders.data.permissions import PERMISSIONS

    [entry] = [item for item in PERMISSIONS if item.name == 'users_manage_permissions']
    assert entry.enforced is True
    holders = factory.query(
        'SELECT r.name FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id '
        "JOIN roles r ON r.id = rp.role_id WHERE p.name = 'users_manage_permissions'"
    )
    assert holders == [{'name': 'Super Admin'}]


def test_only_held_permissions_can_be_granted(client, factory):
    teacher = factory.user('Teacher')
    held, unheld = _held_and_unheld(factory)
    _actor(factory, client, 'Admin', 'users_manage_permissions')
    assert api(client, 'POST', f'/api/users/{teacher["id"]}/permissions', json={'permission_name': held}).status_code == 200
    response = api(client, 'POST', f'/api/users/{teacher["id"]}/permissions', json={'permission_name': unheld})
    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'user_permission_unheld'
    response = api(client, 'POST', f'/api/users/{teacher["id"]}/permissions/bulk',
                   json={'permission_names': [held, unheld]})
    assert response.status_code == 403
    assert _direct_grants(factory, teacher) == {held}


def test_granting_to_a_senior_account_is_refused(client, factory):
    root = factory.user('Super Admin')
    other = factory.user('Admin')
    held, _ = _held_and_unheld(factory)
    _actor(factory, client, 'Admin', 'users_manage_permissions')
    for target in (root, other):
        response = api(client, 'POST', f'/api/users/{target["id"]}/permissions', json={'permission_name': held})
        assert response.status_code == 403
        assert response.get_json()['error']['code'] == 'user_protected'
        assert _direct_grants(factory, target) == set()


def test_a_group_with_an_unheld_permission_is_refused(client, factory):
    teacher = factory.user('Teacher')
    held, unheld = _held_and_unheld(factory)
    _actor(factory, client, 'Admin', 'users_manage_permissions')
    ids = {row['name']: row['id'] for row in factory.query(
        'SELECT id, name FROM permissions WHERE name IN (%s, %s)', (held, unheld),
    )}
    safe = factory.insert('permission_groups', name='Harness held')
    factory.insert('permission_group_permissions', group_id=safe, permission_id=ids[held])
    risky = factory.insert('permission_groups', name='Harness unheld')
    factory.insert('permission_group_permissions', group_id=risky, permission_id=ids[unheld])
    assert api(client, 'POST', f'/api/users/{teacher["id"]}/groups', json={'group_id': risky}).status_code == 403
    assert api(client, 'POST', f'/api/users/{teacher["id"]}/groups', json={'group_id': safe}).status_code == 200
    groups = factory.query('SELECT group_id FROM user_permission_groups WHERE user_id = %s', (teacher['id'],))
    assert groups == [{'group_id': safe}]


def test_a_super_admin_may_grant_anything(client, factory):
    teacher = factory.user('Teacher')
    _, unheld = _held_and_unheld(factory)
    _actor(factory, client, 'Super Admin', 'users_manage_permissions')
    assert api(client, 'POST', f'/api/users/{teacher["id"]}/permissions', json={'permission_name': unheld}).status_code == 200


# Legacy routes

@pytest.mark.parametrize('path', ('edit', 'delete', 'reset_password', 'toggle_status', 'unlock'))
def test_legacy_routes_refuse_an_admin_on_a_super_admin(client, factory, path):
    root = factory.user('Super Admin')
    before = _row(factory, root)
    _actor(factory, client, 'Admin', *_ACCOUNT_RIGHTS)
    data = {'username': root['username'], 'role': 'Admin', 'status': 'inactive'} if path == 'edit' else {}
    response = client.post(
        f'/admin/users/{path}/{root["id"]}', data={**data, 'csrf_token': csrf_token(client)},
        headers={'Origin': SAME_ORIGIN, 'X-Requested-With': 'XMLHttpRequest'},
    )
    assert response.status_code == 403, response.get_data(as_text=True)[:300]
    assert _row(factory, root) == before


def test_legacy_add_refuses_a_senior_role(client, factory):
    _actor(factory, client, 'Admin', *_ACCOUNT_RIGHTS)
    form_post(client, '/admin/users/add', {'username': 'climber_2', 'password': 'Harness-Pass-9',
                                           'role': 'Super Admin', 'status': 'active', 'email': ''})
    assert factory.query("SELECT 1 FROM users WHERE username = 'climber_2'") == []


def test_legacy_grants_need_users_manage_permissions_and_held_permissions(client, factory):
    teacher = factory.user('Teacher')
    held, unheld = _held_and_unheld(factory)
    actor = _actor(factory, client, 'Admin', 'users_change_user')
    path = f'/admin/users/permissions/{teacher["id"]}/grant'
    denied = form_post(client, path, {'permission_name': held})
    assert denied.status_code == 302
    assert _direct_grants(factory, teacher) == set()
    factory.grant(actor, 'users_manage_permissions')
    assert form_post(client, path, {'permission_name': unheld}).status_code == 403
    assert form_post(client, '/admin/users/permissions/bulk_grant',
                     {'user_ids': [teacher['id']], 'permission_names': [unheld]}).status_code == 403
    assert form_post(client, path, {'permission_name': held}).status_code == 200
    assert _direct_grants(factory, teacher) == {held}


# Roles

def _role(factory, name):
    [row] = factory.query('SELECT id, name, hierarchy_level FROM roles WHERE name = %s', (name,))
    return row


def _hod_with_roles(factory, client, *extra):
    return _actor(factory, client, 'HOD', 'roles_view_role', 'roles_change_role', *extra)


def test_a_senior_role_cannot_be_edited(client, factory):
    _hod_with_roles(factory, client)
    admin = _role(factory, 'Admin')
    response = api(client, 'PUT', f'/api/roles/{admin["id"]}',
                   json={'name': 'Admin', 'description': 'mine now', 'hierarchy_level': 2})
    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'role_protected'


def test_a_role_cannot_be_raised_above_the_actor(client, factory):
    _hod_with_roles(factory, client)
    teacher = _role(factory, 'Teacher')
    response = api(client, 'PUT', f'/api/roles/{teacher["id"]}',
                   json={'name': 'Teacher', 'description': '', 'hierarchy_level': 1})
    assert response.status_code == 403
    assert _role(factory, 'Teacher')['hierarchy_level'] == teacher['hierarchy_level']


def test_a_new_role_cannot_outrank_the_actor(client, factory):
    _hod_with_roles(factory, client, 'roles_add_role')
    response = api(client, 'POST', '/api/roles', json={'name': 'Overlord', 'description': '', 'hierarchy_level': 1})
    assert response.status_code == 403
    assert factory.query("SELECT 1 FROM roles WHERE name = 'Overlord'") == []
    assert api(client, 'POST', '/api/roles',
               json={'name': 'Lab Assistant', 'description': '', 'hierarchy_level': 6}).status_code == 201


def test_only_held_permissions_can_be_added_to_a_role(client, factory):
    hod = _hod_with_roles(factory, client)
    teacher = _role(factory, 'Teacher')
    current = {row['permission_id'] for row in factory.query(
        'SELECT permission_id FROM role_permissions WHERE role_id = %s', (teacher['id'],),
    )}
    held = factory.role_permissions('HOD') | {'roles_view_role', 'roles_change_role'}
    rows = factory.query('SELECT id, name FROM permissions')
    unheld_id = next(row['id'] for row in rows if row['name'] not in held and row['id'] not in current)
    held_id = next(row['id'] for row in rows if row['name'] in held and row['id'] not in current)
    path = f'/api/roles/{teacher["id"]}/permissions'
    response = api(client, 'PUT', path, json={'permission_ids': sorted(current | {unheld_id})})
    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'role_permission_unheld'
    assert api(client, 'PUT', path, json={'permission_ids': sorted(current | {held_id})}).status_code == 200
    assert hod
