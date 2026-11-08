"""Smoke test: every registered GET route answers without a server error, anonymously and as Super Admin.

The test creates its own rows (an academic setup, a user of each role) and
fills URL ids from them, so it does not depend on what another test left.
"""

from tests.http_helpers import login
from tests.route_inventory import sample_path

SKIP_SIGNED_IN = ('logout',)


def _ids(factory, setup, users):
    [role] = factory.query("SELECT id FROM roles WHERE name = 'Admin'")
    teacher = setup['teacher']
    return {
        'course_id': setup['course_id'],
        'department_id': setup['department_id'],
        'room_id': setup['room_id'],
        'subject_id': setup['subject_id'],
        'timetable_id': setup['timetable_id'],
        'faculty_id': teacher['faculty_id'],
        'faculty_user_id': teacher['id'],
        'student_id': users['Student']['student_id'],
        'user_id': users['Admin']['id'],
        'role_id': role['id'],
    }


def _sweep(app, client, overrides, skip=()):
    failures, api_gets, mobile_gets = [], [], []
    for rule in app.url_map.iter_rules():
        if 'GET' not in (rule.methods or ()) or rule.endpoint == 'static':
            continue
        if any(word in rule.endpoint for word in skip):
            continue
        path = sample_path(rule, overrides)
        if path == '/api' or path.startswith('/api/'):
            api_gets.append(path)
        if path == '/mobile-sync/v1' or path.startswith('/mobile-sync/v1/'):
            mobile_gets.append(path)
        try:
            response = client.get(path, follow_redirects=False)
        except Exception as error:
            failures.append(f'{path} raised {type(error).__name__}')
            continue
        if response.status_code >= 500:
            failures.append(f'{path} {response.status_code}')
    return failures, api_gets, mobile_gets


def test_get_routes_do_not_return_500(app, client, factory, reset_rate_limits):
    setup = factory.academic()
    users = factory.users(setup)
    overrides = _ids(factory, setup, users)

    failures, api_gets, mobile_gets = _sweep(app, client, overrides)
    assert api_gets, 'No /api GET routes are registered'
    assert mobile_gets, 'No /mobile-sync/v1 GET routes are registered'
    assert not failures, 'GET routes returned a server error (anonymous):\n' + '\n'.join(failures)

    reset_rate_limits()
    assert login(client, users['Super Admin']).status_code == 302
    failures, _, _ = _sweep(app, client, overrides, skip=SKIP_SIGNED_IN)
    assert client.get('/api/session').get_json()['data']['role'] == 'Super Admin'
    assert not failures, 'GET routes returned a server error (Super Admin):\n' + '\n'.join(failures)
