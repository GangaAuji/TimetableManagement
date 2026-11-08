"""Writes that update the actor's own users row and then write an audit row.

user_activity_log and audit_logs have foreign keys to users, so inserting
them needs a shared lock on the actor's row. These writes used to call
log_activity on a second connection while the request's transaction still
held that row; the audit insert waited out the lock timeout and the row was
lost. log_activity now takes the request's cursor, so the change and its
audit row commit or roll back together.
"""

import time

import pytest

from tests.http_helpers import ADMIN_FORM_ROLES, SAME_ORIGIN, api, csrf_token, login


def _logged(factory, user, activity):
    return factory.query(
        'SELECT 1 FROM user_activity_log WHERE user_id = %s AND activity_type = %s', (user['id'], activity),
    )


def _audited(factory, user, action):
    return factory.query(
        'SELECT username FROM audit_logs WHERE user_id = %s AND action = %s', (user['id'], action),
    )


def _change_own_password(client, user):
    return api(client, 'POST', '/api/account/password',
               json={'current_password': user['password'], 'new_password': 'Harness-Pass-2'})


def _rename_own_role(client, factory):
    [role] = factory.query("SELECT id, hierarchy_level FROM roles WHERE name = 'HOD'")
    return api(client, 'PUT', f'/api/roles/{role["id"]}',
               json={'name': 'Head of Department', 'description': 'renamed', 'hierarchy_level': role['hierarchy_level']})


def _edit_own_account(client, user):
    return client.post(
        f'/admin/users/edit/{user["id"]}',
        headers={'Origin': SAME_ORIGIN, 'X-Requested-With': 'XMLHttpRequest'},
        data={'username': user['username'], 'role': user['role'], 'status': 'active',
              'email': f'{user["username"]}@changed.example.org', 'csrf_token': csrf_token(client)},
    )


def _hod_who_edits_roles(factory):
    hod = factory.user('HOD')
    factory.grant(hod, 'roles_change_role')
    return hod


def test_changing_your_own_password_is_audited(client, factory):
    user = factory.user('Teacher')
    login(client, user)
    assert _change_own_password(client, user).status_code == 200
    assert _logged(factory, user, 'change_password')
    assert _audited(factory, user, 'change_password') == [{'username': user['username']}]


def test_renaming_your_own_role_is_audited(client, factory):
    hod = _hod_who_edits_roles(factory)
    login(client, hod)
    assert _rename_own_role(client, factory).status_code == 200
    assert _logged(factory, hod, 'edit_role')
    [row] = factory.query('SELECT role FROM users WHERE id = %s', (hod['id'],))
    assert row['role'] == 'Head of Department'


def test_renaming_a_role_you_do_not_hold_is_audited(client, factory):
    hod = _hod_who_edits_roles(factory)
    [role] = factory.query("SELECT id, hierarchy_level FROM roles WHERE name = 'Teacher'")
    login(client, hod)
    response = api(client, 'PUT', f'/api/roles/{role["id"]}',
                   json={'name': 'Lecturer', 'description': 'renamed', 'hierarchy_level': role['hierarchy_level'] or 4})
    assert response.status_code == 200
    assert _logged(factory, hod, 'edit_role')


def test_editing_your_own_account_on_the_legacy_screen_is_audited(client, factory):
    root = factory.user('Super Admin')
    login(client, root)
    response = _edit_own_account(client, root)
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert _logged(factory, root, 'edit_user')
    [row] = factory.query('SELECT email FROM users WHERE id = %s', (root['id'],))
    assert row['email'] == f'{root["username"]}@changed.example.org'


def test_an_audit_failure_rolls_the_change_back(client, factory, monkeypatch):
    user = factory.user('Teacher')
    login(client, user)
    [before] = factory.query('SELECT password FROM users WHERE id = %s', (user['id'],))

    def _broken(cursor, *args, **kwargs):
        raise RuntimeError('audit table unavailable')

    monkeypatch.setattr('security._write_activity', _broken)
    assert _change_own_password(client, user).status_code == 500
    [after] = factory.query('SELECT password FROM users WHERE id = %s', (user['id'],))
    assert after == before


@pytest.mark.parametrize('case', ('password', 'role', 'legacy_edit'))
def test_own_row_writes_take_under_two_seconds_with_the_default_lock_wait(
        default_lock_wait_app, db, factory, reset_rate_limits, case):
    client = default_lock_wait_app.test_client()
    with default_lock_wait_app.app_context():
        from extensions import get_db_connection

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT @@SESSION.innodb_lock_wait_timeout')
        assert cursor.fetchone()[0] > 2, 'this test needs the server default lock wait'
        connection.close()
    if case == 'password':
        user = factory.user('Teacher')
    elif case == 'role':
        user = _hod_who_edits_roles(factory)
    else:
        user = factory.user('Super Admin')
    path = '/admin/login' if user['role'] in ADMIN_FORM_ROLES else '/login'
    assert login(client, user, path).status_code == 302
    started = time.perf_counter()
    if case == 'password':
        response, activity = _change_own_password(client, user), 'change_password'
    elif case == 'role':
        response, activity = _rename_own_role(client, factory), 'edit_role'
    else:
        response, activity = _edit_own_account(client, user), 'edit_user'
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert elapsed < 2, f'{case} took {elapsed:.1f} s'
    assert _logged(factory, user, activity)
