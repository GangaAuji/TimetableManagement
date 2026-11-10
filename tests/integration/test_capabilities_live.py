"""Capabilities on the *_test database: the session reports the effective map, admins read the
list, Super Admins switch features and settings, invalid input is refused, the audit log records
the change, and a server flag set off wins over the tenant switch."""

from tests.http_helpers import api, login, signed_in_as


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['error']['code']


def _by_name(payload):
    return {item['name']: item for item in payload['capabilities']}


def test_session_reports_defaults_and_toggles_follow_saves(client, factory):
    admin = factory.user('Super Admin')
    login(client, admin)
    session = signed_in_as(client)
    assert session['capabilities']['timetable_preferences'] is True      # default on once migrated
    assert session['capabilities']['bookings'] is False                  # default off

    listing = _ok(api(client, 'GET', '/api/capabilities'))
    assert listing['table_exists'] is True and listing['can_change'] is True
    bookings = _by_name(listing)['bookings']
    assert (bookings['flag'], bookings['enabled'], bookings['stored'], bookings['effective']) == (True, False, False, False)
    assert bookings['settings'] == {'requires_approval': True}

    saved = _ok(api(client, 'PUT', '/api/capabilities/bookings', json={'enabled': True, 'settings': {'requires_approval': False}}))
    bookings = _by_name(saved)['bookings']
    assert (bookings['enabled'], bookings['stored'], bookings['effective']) == (True, True, True)
    assert bookings['settings'] == {'requires_approval': False}
    assert signed_in_as(client)['capabilities']['bookings'] is True

    saved = _ok(api(client, 'PUT', '/api/capabilities/timetable_preferences', json={'enabled': False}))
    assert _by_name(saved)['timetable_preferences']['effective'] is False
    assert signed_in_as(client)['capabilities']['timetable_preferences'] is False

    rows = factory.query("SELECT activity_type FROM user_activity_log WHERE activity_type = 'capability_changed'")
    assert len(rows) == 2


def test_invalid_input_is_refused(client, factory):
    login(client, factory.user('Super Admin'))
    assert _error(api(client, 'PUT', '/api/capabilities/not_real', json={'enabled': True}), 404) == 'capability_unknown'
    assert _error(api(client, 'PUT', '/api/capabilities/bookings', json={'enabled': 'yes'}), 400) == 'capability_invalid'
    assert _error(api(client, 'PUT', '/api/capabilities/bookings', json={'settings': {'stray': 1}}), 400) == 'capability_invalid'
    assert _error(api(client, 'PUT', '/api/capabilities/workload_norms', json={'settings': {'enforce': 'maybe'}}), 400) == 'capability_invalid'
    assert _error(api(client, 'PUT', '/api/capabilities/bookings', json={'other': True}), 400) == 'invalid_body'
    assert factory.query('SELECT id FROM capabilities') == []


def test_admin_reads_but_cannot_change_and_teachers_see_nothing(client, factory):
    setup = factory.academic()
    admin = factory.user('Admin')
    login(client, admin)
    # Admin has neither settings permission by default (Super Admin only).
    assert _error(api(client, 'GET', '/api/capabilities'), 403) == 'forbidden'
    factory.grant(admin, 'admin_view_settings')
    listing = _ok(api(client, 'GET', '/api/capabilities'))
    assert listing['can_change'] is False
    assert _error(api(client, 'PUT', '/api/capabilities/bookings', json={'enabled': True}), 403) == 'forbidden'
    # Every signed-in user still gets the effective map on the session.
    assert set(signed_in_as(client)['capabilities']) >= {'bookings', 'timetable_preferences'}
    api(client, 'POST', '/api/session/logout')

    login(client, setup['teacher'])
    assert _error(api(client, 'GET', '/api/capabilities'), 403) == 'forbidden'
    assert signed_in_as(client)['capabilities']['bookings'] is False


def test_server_flag_off_hides_the_feature_despite_the_tenant_switch(app, client, factory):
    factory.capability('bookings', True)
    login(client, factory.user('Super Admin'))
    assert signed_in_as(client)['capabilities']['bookings'] is True
    app.config['FEATURE_BOOKINGS'] = False
    try:
        assert signed_in_as(client)['capabilities']['bookings'] is False
        item = _by_name(_ok(api(client, 'GET', '/api/capabilities')))['bookings']
        assert (item['flag'], item['enabled'], item['effective']) == (False, True, False)
    finally:
        app.config['FEATURE_BOOKINGS'] = True
