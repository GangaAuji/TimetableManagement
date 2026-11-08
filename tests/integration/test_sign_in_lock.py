"""Time-based sign-in lock (security/lockout.py) and sign-in rate limits (security/rate_limit.py)."""

import pytest

from tests.http_helpers import SAME_ORIGIN, api, csrf_token, login, signed_in_as

ATTEMPTS = 5
WRONG = 'Wrong-Pass-1'


def sign_in(client, username, password, path='/login', address=None, headers=None):
    data = {'username': username, 'password': password, 'csrf_token': csrf_token(client)}
    extra = {'environ_base': {'REMOTE_ADDR': address}} if address else {}
    return client.post(path, data=data, headers={'Origin': SAME_ORIGIN, **(headers or {})}, **extra)


def _fail(client, user, times=ATTEMPTS, path=None):
    path = path or ('/admin/login' if user['role'] in ('Admin', 'Super Admin') else '/login')
    for _ in range(times):
        sign_in(client, user['username'], WRONG, path)


def _lock_state(factory, user):
    [row] = factory.query(
        'SELECT status, failed_attempts, failed_window_start, locked_until, locked_until > NOW() AS locked '
        'FROM users WHERE id = %s', (user['id'],),
    )
    return row


def _actions(factory, user_id, action):
    return factory.query(
        'SELECT user_id, entity_id FROM audit_logs WHERE action = %s AND entity_id = %s', (action, user_id),
    )


def _expire(factory, user):
    factory.execute(
        'UPDATE users SET locked_until = NOW() - INTERVAL 1 MINUTE, '
        'failed_window_start = NOW() - INTERVAL 20 MINUTE WHERE id = %s', (user['id'],),
    )


def test_five_failures_lock_the_account_for_a_while_and_audit_it(client, factory):
    user = factory.user('Student')
    _fail(client, user)
    row = _lock_state(factory, user)
    assert (row['status'], row['failed_attempts'], row['locked']) == ('active', ATTEMPTS, 1)
    assert _actions(factory, user['id'], 'account_locked') == [{'user_id': user['id'], 'entity_id': user['id']}]
    [minutes] = factory.query(
        'SELECT TIMESTAMPDIFF(MINUTE, NOW(), locked_until) AS left_ FROM users WHERE id = %s', (user['id'],),
    )
    assert 13 <= minutes['left_'] <= 15


def test_the_right_password_during_a_lock_is_refused(client, factory):
    user = factory.user('Student')
    _fail(client, user)
    response = login(client, user)
    assert response.status_code == 401
    assert signed_in_as(client) is None
    [attempt] = factory.query(
        "SELECT failure_reason FROM login_attempts WHERE username = %s AND status = 'failed' "
        'ORDER BY id DESC LIMIT 1', (user['username'],),
    )
    assert attempt['failure_reason'] == 'Account locked'


def test_failures_during_a_lock_do_not_extend_it(client, factory):
    user = factory.user('Student')
    _fail(client, user)
    before = _lock_state(factory, user)
    _fail(client, user, times=2)
    after = _lock_state(factory, user)
    assert (after['failed_attempts'], after['locked_until']) == (ATTEMPTS, before['locked_until'])


def test_unknown_username_and_wrong_password_get_the_same_answer(client, factory):
    user = factory.user('Student')
    unknown = sign_in(client, 'nobody_at_all', WRONG)
    wrong = sign_in(client, user['username'], WRONG)
    _fail(client, user, times=ATTEMPTS)
    locked_wrong = sign_in(client, user['username'], WRONG)
    locked_right = sign_in(client, user['username'], user['password'])
    answers = {(r.status_code, r.mimetype, r.get_data()) for r in (unknown, wrong, locked_wrong, locked_right)}
    assert answers == {(401, 'text/plain', b'Sign in failed.')}


def test_a_lock_ends_by_itself(client, factory):
    user = factory.user('Student')
    _fail(client, user)
    _expire(factory, user)
    assert login(client, user).status_code == 302
    row = _lock_state(factory, user)
    assert (row['failed_attempts'], row['failed_window_start'], row['locked_until']) == (0, None, None)
    assert _actions(factory, user['id'], 'account_unlocked')


def test_a_failure_after_an_expired_lock_starts_a_new_count(client, factory):
    user = factory.user('Student')
    _fail(client, user)
    _expire(factory, user)
    _fail(client, user, times=1)
    row = _lock_state(factory, user)
    assert (row['failed_attempts'], row['locked_until']) == (1, None)


def test_failures_outside_the_window_stop_counting(client, factory):
    user = factory.user('Student')
    factory.execute(
        'UPDATE users SET failed_attempts = 4, failed_window_start = NOW() - INTERVAL 16 MINUTE WHERE id = %s',
        (user['id'],),
    )
    _fail(client, user, times=1)
    row = _lock_state(factory, user)
    assert (row['failed_attempts'], row['locked_until']) == (1, None)
    assert login(client, user).status_code == 302


def test_a_successful_sign_in_resets_the_counter(client, factory):
    user = factory.user('Student')
    _fail(client, user, times=ATTEMPTS - 1)
    assert login(client, user).status_code == 302
    row = _lock_state(factory, user)
    assert (row['failed_attempts'], row['failed_window_start']) == (0, None)


def test_a_super_admin_gets_the_same_temporary_lock(client, factory):
    root = factory.user('Super Admin')
    _fail(client, root)
    row = _lock_state(factory, root)
    assert (row['status'], row['locked']) == ('active', 1)
    assert _actions(factory, root['id'], 'account_locked')
    assert login(client, root).status_code != 302
    _expire(factory, root)
    assert login(client, root).status_code == 302


def test_a_lock_is_per_account(client, factory):
    locked = factory.user('Student')
    other = factory.user('Student')
    _fail(client, locked)
    assert login(client, other).status_code == 302


def test_a_manual_locked_status_still_blocks(client, factory):
    user = factory.user('Student', status='locked')
    assert login(client, user).status_code != 302
    assert signed_in_as(client) is None


def _admin(factory, client):
    admin = factory.user('Admin')
    factory.grant(admin, 'users_change_user')
    login(client, admin)
    return admin


def test_admin_unlock_clears_the_lock_and_is_audited(client, factory):
    user = factory.user('Teacher')
    _fail(client, user)
    admin = _admin(factory, client)
    response = api(client, 'POST', f'/api/users/{user["id"]}/unlock')
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    row = _lock_state(factory, user)
    assert (row['failed_attempts'], row['failed_window_start'], row['locked_until']) == (0, None, None)
    assert {'user_id': admin['id'], 'entity_id': user['id']} in _actions(factory, user['id'], 'account_unlocked')
    client.get('/logout')
    assert login(client, user).status_code == 302


def test_admin_unlock_also_clears_a_manual_lock(client, factory):
    user = factory.user('Teacher', status='locked')
    _admin(factory, client)
    assert api(client, 'POST', f'/api/users/{user["id"]}/unlock').status_code == 200
    assert _lock_state(factory, user)['status'] == 'active'


def test_an_admin_cannot_unlock_a_super_admin(client, factory):
    root = factory.user('Super Admin')
    _fail(client, root)
    _admin(factory, client)
    assert api(client, 'POST', f'/api/users/{root["id"]}/unlock').status_code == 403
    assert _lock_state(factory, root)['locked'] == 1


def test_unlock_needs_users_change_user(client, factory):
    user = factory.user('Teacher')
    hod = factory.user('HOD')
    login(client, hod)
    assert api(client, 'POST', f'/api/users/{user["id"]}/unlock').status_code == 403


# Rate limits

def _buckets(factory, prefix):
    return {row['bucket'] for row in factory.query(
        'SELECT bucket FROM rate_limit_counters WHERE bucket LIKE %s', (prefix + '%',),
    )}


@pytest.fixture
def small_limits(make_app, db, reset_rate_limits):
    return make_app(SIGN_IN_LIMIT_PER_ACCOUNT=3, SIGN_IN_UNKNOWN_LIMIT_PER_ADDRESS=3).test_client()


def test_unknown_usernames_are_counted_per_address_only(small_limits, factory):
    for n in range(3):
        assert sign_in(small_limits, f'nobody_{n}', WRONG).status_code == 401
    assert _buckets(factory, 'auth-unknown:') == {'auth-unknown:127.0.0.1'}
    user = factory.user('Student')
    assert sign_in(small_limits, user['username'], user['password']).status_code == 429
    assert sign_in(small_limits, user['username'], user['password'], address='10.9.9.9').status_code == 302
    row = _lock_state(factory, user)
    assert (row['failed_attempts'], row['locked_until']) == (0, None)


def test_the_account_limit_is_per_address_and_username(small_limits, factory):
    first = factory.user('Student')
    second = factory.user('Student')
    for _ in range(3):
        sign_in(small_limits, first['username'], WRONG)
    assert sign_in(small_limits, first['username'], first['password']).status_code == 429
    assert sign_in(small_limits, second['username'], second['password']).status_code == 302
    assert sign_in(small_limits, first['username'], first['password'], address='10.9.9.9').status_code == 302


def test_forwarded_headers_are_ignored_by_default(client, factory):
    user = factory.user('Student')
    sign_in(client, user['username'], WRONG, headers={'X-Forwarded-For': '203.0.113.7'})
    assert _buckets(factory, 'auth-address:') == {'auth-address:127.0.0.1'}


def test_a_trusted_proxy_hands_over_the_client_address(make_app, db, reset_rate_limits, factory):
    client = make_app(TRUSTED_PROXY_COUNT=1, SIGN_IN_LIMIT_PER_ACCOUNT=3).test_client()
    user = factory.user('Student')
    for _ in range(3):
        sign_in(client, user['username'], WRONG, headers={'X-Forwarded-For': '203.0.113.7'})
    assert _buckets(factory, 'auth-address:') == {'auth-address:203.0.113.7'}
    blocked = sign_in(client, user['username'], user['password'], headers={'X-Forwarded-For': '203.0.113.7'})
    assert blocked.status_code == 429
    other = sign_in(client, user['username'], user['password'], headers={'X-Forwarded-For': '203.0.113.8'})
    assert other.status_code == 302


def test_a_trusted_proxy_uses_only_the_last_hop(make_app, db, reset_rate_limits, factory):
    client = make_app(TRUSTED_PROXY_COUNT=1).test_client()
    sign_in(client, 'nobody', WRONG, headers={'X-Forwarded-For': '198.51.100.1, 203.0.113.7'})
    assert _buckets(factory, 'auth-address:') == {'auth-address:203.0.113.7'}
