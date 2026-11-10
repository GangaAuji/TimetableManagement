"""Phase F on the live *_test database: the public /api/v1 behind API keys, the Integrations admin API,
webhook deliveries queued by real triggers and posted by the outbox worker (fake sender), and SSO settings."""

from datetime import date

import pytest

import api.web  # noqa: F401  (breaks the services.export_jobs <-> api.web import cycle)
from services import api_keys, sso, webhooks
from tests.http_helpers import api, login
from tests.integration.test_attendance_calc_live import cohort  # noqa: F401  (fixture)

pytestmark = pytest.mark.live_db


_APP = []


@pytest.fixture(autouse=True)
def _remember_app(app):
    """Service calls made directly from the test need the app config (TESTING, the encryption key); see _with_cursor."""
    _APP.append(app)
    yield
    _APP.pop()


def _with_cursor(db, work):
    cursor = db.cursor(dictionary=True)
    try:
        with _APP[-1].app_context():
            result = work(cursor)
        db.commit()
        return result
    finally:
        cursor.close()


def _key(db, scopes, **extra):
    return _with_cursor(db, lambda cursor: api_keys.create_key(cursor, name='test', scopes=scopes, created_by=None, **extra))[1]


def _get(client, path, key):
    return client.get(path, headers={'Authorization': f'Bearer {key}'})


def _run(app, sender):
    """One outbox pass as the worker runs it (inside the app context)."""
    with app.app_context():
        return webhooks.run_tenant(app, sender=sender)


def _deliveries(factory, event=None):
    where = 'WHERE event = %s' if event else ''
    return factory.query(
        f'SELECT id, endpoint_id, event, status, attempts, payload_json, response_status, last_error FROM webhook_deliveries {where} ORDER BY id',
        (event,) if event else (),
    )


# Public API ------------------------------------------------------------------

def test_the_public_api_needs_a_valid_key_with_the_right_scope(client, db, cohort):
    key = _key(db, ['catalog:read'])
    assert client.get('/api/v1/courses').status_code == 401
    assert _get(client, '/api/v1/courses', key + 'x').status_code == 401

    me = _get(client, '/api/v1/me', key)
    assert me.status_code == 200 and me.get_json()['data']['scopes'] == ['catalog:read']
    courses = _get(client, '/api/v1/courses', key)
    assert courses.status_code == 200
    assert cohort['setup']['course_id'] in {row['id'] for row in courses.get_json()['data']}
    assert 'Set-Cookie' not in courses.headers

    denied = _get(client, '/api/v1/timetable', key)
    assert denied.status_code == 403 and denied.get_json()['error']['code'] == 'forbidden'
    assert 'timetable:read' in denied.get_json()['error']['message']


def test_timetable_students_and_attendance_read_the_golden_cohort(client, db, cohort):
    key = _key(db, ['timetable:read', 'people:read', 'attendance:read'])
    setup = cohort['setup']
    timetable = _get(client, f"/api/v1/timetable?course_id={setup['course_id']}&class_id={setup['class_id']}", key)
    assert timetable.status_code == 200
    body = timetable.get_json()
    slots = {row['id']: row for row in body['data']}
    assert set(cohort['slots'].values()) <= set(slots)
    physics = slots[cohort['slots']['physics_mon']]
    assert physics['day'] == 'Monday' and physics['start_time'] == '09:00' and physics['subject']['id'] == cohort['subjects']['physics']
    assert physics['faculty']['id'] == cohort['teacher']['faculty_id']
    assert body['page']['has_more'] is False

    students = _get(client, f"/api/v1/students?class_id={setup['class_id']}&limit=2", key)
    assert students.status_code == 200 and len(students.get_json()['data']) == 2 and students.get_json()['page']['has_more'] is True
    one = _get(client, f"/api/v1/students?class_id={setup['class_id']}&limit=2&offset=2", key).get_json()
    assert len(one['data']) == 2 and one['page']['offset'] == 2
    assert 'password' not in str(students.get_json()).lower()

    sessions = _get(client, f"/api/v1/attendance/sessions?from=2026-03-01&to=2026-03-31&class_id={setup['class_id']}", key)
    assert sessions.status_code == 200
    held = [row for row in sessions.get_json()['data'] if row['status'] == 'held']
    assert len(held) >= 10
    session_id = cohort['sessions'][('physics_mon', date(2026, 3, 9))]
    marks = _get(client, f'/api/v1/attendance/sessions/{session_id}/marks', key)
    assert marks.status_code == 200
    marks_data = marks.get_json()['data']
    assert marks_data['session']['id'] == session_id and marks_data['session']['marks'] == 2
    by_student = {row['student_id']: row['status'] for row in marks_data['marks']}
    assert by_student[cohort['asha']['student_id']] == 'Present' and by_student[cohort['chen']['student_id']] == 'Present'

    report = _get(client, f"/api/v1/attendance/students/{cohort['asha']['student_id']}", key)
    assert report.status_code == 200
    data = report.get_json()['data']
    assert data['student']['id'] == cohort['asha']['student_id'] and 0 < data['overall']['percentage'] <= 100
    assert cohort['subjects']['physics'] in {subject['id'] for subject in data['subjects']}
    assert data['threshold'] > 0

    defaulters = _get(client, f"/api/v1/attendance/defaulters?threshold=75&class_id={setup['class_id']}", key)
    assert defaulters.status_code == 200
    listed = {row['student']['id'] for row in defaulters.get_json()['data']['students']}
    assert cohort['chen']['student_id'] in listed and cohort['dev']['student_id'] not in listed

    missing = _get(client, '/api/v1/attendance/sessions/999999999/marks', key)
    assert missing.status_code == 404
    bad = _get(client, '/api/v1/attendance/sessions?from=yesterday', key)
    assert bad.status_code == 400 and bad.get_json()['error']['code'] == 'invalid_parameter'


def test_openapi_document_is_served_and_lists_every_route(client):
    response = client.get('/api/v1/openapi.json')
    assert response.status_code == 200
    document = response.get_json()
    assert document['openapi'].startswith('3.1') and '/timetable' in document['paths'] and '/attendance/defaulters' in document['paths']
    assert document['components']['securitySchemes']['ApiKey']['type'] == 'http'
    index = client.get('/api/v1')
    assert index.status_code == 200 and index.get_json()['data']['openapi'].endswith('/api/v1/openapi.json')


def test_expired_and_revoked_keys_stop_working(client, db, factory):
    from datetime import datetime, timedelta

    key = _key(db, ['catalog:read'], expires_at=datetime.utcnow() + timedelta(days=1))
    assert _get(client, '/api/v1/departments', key).status_code == 200
    factory.execute('UPDATE api_keys SET expires_at = %s WHERE key_prefix = %s', (datetime.utcnow() - timedelta(minutes=1), api_keys.split_key(key)[0]))
    assert _get(client, '/api/v1/departments', key).status_code == 401
    key2 = _key(db, ['catalog:read'])
    row = factory.query('SELECT id FROM api_keys WHERE key_prefix = %s', (api_keys.split_key(key2)[0],))[0]
    _with_cursor(db, lambda cursor: api_keys.revoke_key(cursor, row['id']))
    assert _get(client, '/api/v1/departments', key2).status_code == 401


# Integrations admin API --------------------------------------------------------

def test_admin_creates_a_key_sees_the_plaintext_once_then_revokes_it(client, factory):
    admin = factory.user('Super Admin')
    login(client, admin)
    created = api(client, 'POST', '/api/integrations/api-keys', json={'name': 'ERP export', 'scopes': ['catalog:read', 'people:read'], 'expires_at': '2099-12-31'})
    assert created.status_code == 200, created.get_json()
    data = created.get_json()['data']
    plaintext = data['key']
    assert plaintext.startswith('ttk_') and data['api_keys'][0]['name'] == 'ERP export' and data['api_keys'][0]['scopes'] == ['catalog:read', 'people:read']
    assert 'key' not in data['api_keys'][0] and data['api_keys'][0]['expires_at'].startswith('2099-12-31')

    overview = api(client, 'GET', '/api/integrations')
    assert overview.status_code == 200
    assert plaintext not in overview.get_data(as_text=True)
    assert overview.get_json()['data']['openapi_url'].endswith('/api/v1/openapi.json')
    assert {scope['name'] for scope in overview.get_json()['data']['scopes']} == set(api_keys.SCOPES)

    assert _get(client, '/api/v1/students', plaintext).status_code == 200
    revoked = api(client, 'DELETE', f"/api/integrations/api-keys/{data['id']}")
    assert revoked.status_code == 200 and revoked.get_json()['data']['api_keys'][0]['revoked_at']
    assert _get(client, '/api/v1/students', plaintext).status_code == 401

    bad = api(client, 'POST', '/api/integrations/api-keys', json={'name': 'x', 'scopes': []})
    assert bad.status_code == 400 and bad.get_json()['error']['code'] == 'api_key_scopes_invalid'
    past = api(client, 'POST', '/api/integrations/api-keys', json={'name': 'x', 'scopes': ['catalog:read'], 'expires_at': '2001-01-01'})
    assert past.status_code == 400 and past.get_json()['error']['code'] == 'api_key_expires_invalid'


def test_integrations_need_the_settings_permissions(client, factory):
    teacher = factory.user('Teacher')
    login(client, teacher)
    assert api(client, 'GET', '/api/integrations').status_code == 403
    assert api(client, 'POST', '/api/integrations/api-keys', json={'name': 'x', 'scopes': ['catalog:read']}).status_code == 403
    client.get('/logout')
    assert api(client, 'GET', '/api/integrations').status_code == 401
    assert api(client, 'GET', '/api/sso').status_code == 200   # the sign-in page may ask


def test_webhook_endpoint_lifecycle(client, factory):
    admin = factory.user('Super Admin')
    login(client, admin)
    created = api(client, 'POST', '/api/integrations/webhooks', json={'name': 'ERP', 'url': 'https://erp.example.org/hooks/tt', 'events': ['attendance.marked']})
    assert created.status_code == 200, created.get_json()
    data = created.get_json()['data']
    secret = data['secret']
    assert secret.startswith('whsec_') and data['webhooks'][0]['events'] == ['attendance.marked'] and data['webhooks'][0]['is_active']
    stored = factory.query('SELECT secret_enc FROM webhook_endpoints WHERE id = %s', (data['id'],))[0]['secret_enc']
    assert stored.startswith('enc:v1:') and secret not in stored

    changed = api(client, 'PUT', f"/api/integrations/webhooks/{data['id']}", json={'name': 'ERP', 'url': 'https://erp.example.org/hooks/tt2', 'events': ['*'], 'is_active': False, 'rotate_secret': True})
    assert changed.status_code == 200
    assert changed.get_json()['data']['secret'] != secret and changed.get_json()['data']['webhooks'][0]['events'] == ['*']
    assert changed.get_json()['data']['webhooks'][0]['is_active'] is False

    bad_url = api(client, 'POST', '/api/integrations/webhooks', json={'name': 'x', 'url': 'ftp://erp.example.org', 'events': ['*']})
    assert bad_url.status_code == 400 and bad_url.get_json()['error']['code'] == 'webhook_url_invalid'
    no_events = api(client, 'POST', '/api/integrations/webhooks', json={'name': 'x', 'url': 'https://erp.example.org', 'events': ['nope']})
    assert no_events.status_code == 400 and no_events.get_json()['error']['code'] == 'webhook_events_invalid'

    deleted = api(client, 'DELETE', f"/api/integrations/webhooks/{data['id']}")
    assert deleted.status_code == 200 and deleted.get_json()['data']['webhooks'] == []
    assert api(client, 'DELETE', f"/api/integrations/webhooks/{data['id']}").status_code == 400


# Webhook triggers and the outbox ---------------------------------------------

@pytest.fixture
def endpoint(db):
    """An active endpoint for every event. Returns (id, secret)."""
    return _with_cursor(db, lambda cursor: webhooks.create_endpoint(cursor, name='all', url='https://receiver.example.org/hook', events=['*'], created_by=None))


def test_marking_attendance_queues_one_delivery_which_the_worker_posts_signed(app, client, db, factory, cohort, endpoint, monkeypatch):
    from tests.factories import LECTURE_DATE, LectureDay

    monkeypatch.setattr('services.teacher_attendance.date', LectureDay)   # marks are taken "today", on the slot's weekday
    endpoint_id, secret = endpoint
    slot = cohort['slots']['physics_mon']
    login(client, cohort['teacher'])
    response = api(client, 'POST', f'/api/portal/attendance/mark/{slot}', json={
        'attendance_date': LECTURE_DATE.isoformat(),
        'marks': [
            {'student_id': cohort['asha']['student_id'], 'status': 'Present'},
            {'student_id': cohort['ben']['student_id'], 'status': 'Absent'},
            {'student_id': cohort['chen']['student_id'], 'status': 'Late'},
        ],
    })
    assert response.status_code == 200, response.get_json()
    rows = _deliveries(factory, 'attendance.marked')
    assert len(rows) == 1 and rows[0]['status'] == 'queued' and rows[0]['endpoint_id'] == endpoint_id
    import json

    payload = json.loads(rows[0]['payload_json'])
    assert payload['event'] == 'attendance.marked' and payload['data']['timetable_id'] == slot and payload['data']['date'] == LECTURE_DATE.isoformat()
    assert (payload['data']['present'], payload['data']['absent'], payload['data']['late'], payload['data']['marks']) == (1, 1, 1, 3)
    assert payload['data']['source'] == 'teacher' and payload['data']['subject']['id'] == cohort['subjects']['physics']

    posted = []

    def sender(url, body, headers, timeout):
        posted.append((url, body, headers))
        return 200

    counts = _run(app, sender)
    assert counts == {'sent': 1, 'retry': 0, 'failed': 0}
    url, body, headers = posted[0]
    assert url == 'https://receiver.example.org/hook' and body == rows[0]['payload_json']
    assert webhooks.verify(secret, headers['X-Timetable-Timestamp'], body, headers['X-Timetable-Signature'])
    assert headers['X-Timetable-Event'] == 'attendance.marked'
    after = _deliveries(factory, 'attendance.marked')[0]
    assert after['status'] == 'sent' and after['attempts'] == 1 and after['response_status'] == 200
    assert factory.query('SELECT last_status FROM webhook_endpoints WHERE id = %s', (endpoint_id,))[0]['last_status'] == 'sent'
    assert _run(app, sender) == {'sent': 0, 'retry': 0, 'failed': 0}   # nothing left


def test_a_failing_receiver_is_retried_later_and_can_be_retried_by_hand(app, client, db, factory, cohort, endpoint):
    _with_cursor(db, lambda cursor: webhooks.on_timetable_published(
        cursor, course_id=cohort['setup']['course_id'], class_id=cohort['setup']['class_id'], division_id=cohort['setup']['division_id'], reason='generated',
    ))
    app.config['WEBHOOK_MAX_ATTEMPTS'] = 2
    try:
        assert _run(app, lambda *a: 503) == {'sent': 0, 'retry': 1, 'failed': 0}
        row = _deliveries(factory, 'timetable.published')[0]
        assert row['status'] == 'queued' and row['attempts'] == 1 and row['last_error'] == 'HTTP 503'
        assert _run(app, lambda *a: 503) == {'sent': 0, 'retry': 0, 'failed': 0}   # not available yet (backoff)
        factory.execute('UPDATE webhook_deliveries SET available_at = UTC_TIMESTAMP() WHERE id = %s', (row['id'],))
        assert _run(app, lambda *a: 503) == {'sent': 0, 'retry': 0, 'failed': 1}
        assert _deliveries(factory, 'timetable.published')[0]['status'] == 'failed'

        admin = factory.user('Super Admin')
        login(client, admin)
        listed = api(client, 'GET', '/api/integrations/webhooks/deliveries')
        assert listed.status_code == 200 and listed.get_json()['data']['deliveries'][0]['status'] == 'failed'
        retried = api(client, 'POST', f"/api/integrations/webhooks/deliveries/{row['id']}/retry")
        assert retried.status_code == 200
        assert _run(app, lambda *a: 200) == {'sent': 1, 'retry': 0, 'failed': 0}
        assert api(client, 'POST', f"/api/integrations/webhooks/deliveries/{row['id']}/retry").status_code == 400
    finally:
        app.config.pop('WEBHOOK_MAX_ATTEMPTS', None)


def test_adding_and_removing_a_slot_publishes_the_timetable(db, factory, cohort, endpoint):
    from services.timetable_slots import add_slot, remove_slot
    from datetime import time

    setup = cohort['setup']
    slot_id = _with_cursor(db, lambda cursor: add_slot(
        cursor, course_id=setup['course_id'], class_id=setup['class_id'], division_id=setup['division_id'], subject_id=cohort['subjects']['evs'],
        day='Tuesday', start_time=time(14, 0), end_time=time(15, 0), faculty_id=cohort['teacher']['faculty_id'],
    ))
    assert _with_cursor(db, lambda cursor: remove_slot(cursor, slot_id)) == 'deleted'
    import json

    reasons = [json.loads(row['payload_json'])['data']['reason'] for row in _deliveries(factory, 'timetable.published')]
    assert reasons == ['slot_added', 'slot_deleted']


def test_an_inactive_or_unsubscribed_endpoint_gets_nothing(db, factory, cohort):
    only_timetable = _with_cursor(db, lambda cursor: webhooks.create_endpoint(cursor, name='tt', url='https://a.example.org/h', events=['timetable.published'], created_by=None))[0]
    inactive = _with_cursor(db, lambda cursor: webhooks.create_endpoint(cursor, name='off', url='https://b.example.org/h', events=['*'], created_by=None))[0]
    _with_cursor(db, lambda cursor: webhooks.update_endpoint(cursor, inactive, name='off', url='https://b.example.org/h', events=['*'], is_active=False))
    session_id = cohort['sessions'][('physics_mon', date(2026, 3, 9))]
    _with_cursor(db, lambda cursor: webhooks.on_attendance_marked(cursor, session_id=session_id, timetable_id=cohort['slots']['physics_mon'], session_date=date(2026, 3, 9)))
    assert _deliveries(factory) == []
    _with_cursor(db, lambda cursor: webhooks.on_defaulters(cursor, threshold=75.0, students=[{'student_id': 1}]))
    assert _deliveries(factory) == []
    _with_cursor(db, lambda cursor: webhooks.on_timetable_published(cursor, course_id=1, class_id=1, division_id=None, reason='generated', slot_count=3))
    rows = _deliveries(factory)
    assert len(rows) == 1 and rows[0]['endpoint_id'] == only_timetable


# SSO settings ----------------------------------------------------------------

def test_sso_settings_round_trip_and_public_descriptor(client, factory):
    assert api(client, 'GET', '/api/sso').get_json()['data'] == {'enabled': False}
    admin = factory.user('Super Admin')
    login(client, admin)
    incomplete = api(client, 'PUT', '/api/integrations/sso', json={'enabled': True, 'provider': 'google'})
    assert incomplete.status_code == 400 and incomplete.get_json()['error']['code'] == 'sso_incomplete'

    saved = api(client, 'PUT', '/api/integrations/sso', json={
        'enabled': True, 'provider': 'google', 'issuer': '', 'client_id': 'abc.apps.googleusercontent.com', 'client_secret': 'top-secret',
        'allowed_domains': 'college.edu', 'link_by_email': True, 'button_label': 'Staff sign in',
    })
    assert saved.status_code == 200, saved.get_json()
    settings = saved.get_json()['data']['sso']
    assert settings['enabled'] and settings['issuer'] == 'https://accounts.google.com' and settings['has_client_secret']
    assert 'top-secret' not in saved.get_data(as_text=True)
    assert saved.get_json()['data']['sso_redirect_uri'].endswith('/auth/sso/callback')
    stored = factory.query('SELECT client_secret_enc FROM sso_settings WHERE id = 1')[0]['client_secret_enc']
    assert stored.startswith('enc:v1:')

    client.get('/logout')
    public = api(client, 'GET', '/api/sso').get_json()['data']
    assert public == {'enabled': True, 'provider': 'google', 'button_label': 'Staff sign in'}

    # /auth/sso/start sends the browser to the provider with PKCE and state; discovery is faked.
    import services.sso as sso_module

    document = {'issuer': 'https://accounts.google.com', 'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth',
                'token_endpoint': 'https://oauth2.googleapis.com/token', 'jwks_uri': 'https://www.googleapis.com/oauth2/v3/certs'}
    original = sso_module._get_json
    sso_module._cache.clear()
    sso_module._get_json = lambda url, timeout=10: document
    try:
        start = client.get('/auth/sso/start')
        assert start.status_code == 302
        location = start.headers['Location']
        assert location.startswith('https://accounts.google.com/o/oauth2/v2/auth?') and 'code_challenge_method=S256' in location
        assert 'hd=college.edu' in location and 'client_id=abc.apps.googleusercontent.com' in location
        with client.session_transaction() as flask_session:
            flow = flask_session[sso.SESSION_KEY]
        assert f"state={flow['state']}" in location and f"nonce={flow['nonce']}" in location
        # A callback with the wrong state is refused and sends the browser back to the sign-in page.
        back = client.get('/auth/sso/callback?state=wrong&code=abc')
        assert back.status_code == 302 and 'sso_error=sso_state_mismatch' in back.headers['Location']
    finally:
        sso_module._get_json = original
        sso_module._cache.clear()


def test_sso_callback_signs_in_a_linked_staff_user(app, client, db, factory):
    """The whole callback with a fake provider: token exchange and JWKS are replaced, the id_token is really verified."""
    import base64
    import json
    import time

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    import services.sso as sso_module

    admin = factory.user('Super Admin')
    hod = factory.user('HOD')
    factory.execute('UPDATE users SET email = %s WHERE id = %s', ('hod@college.edu', hod['id']))
    student = factory.user('Student')
    factory.execute('UPDATE users SET email = %s WHERE id = %s', ('stu@college.edu', student['id']))
    _with_cursor(db, lambda cursor: sso_module.save_settings(cursor, {
        'enabled': True, 'provider': 'oidc', 'issuer': 'https://idp.example.org', 'client_id': 'tt-client', 'allowed_domains': 'college.edu',
        'link_by_email': True,
    }, admin['id'], client_secret='s3cret'))

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private.public_key().public_numbers()

    def b64(data):
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

    keys = {'keys': [{'kty': 'RSA', 'kid': 'k', 'n': b64(numbers.n.to_bytes(256, 'big')), 'e': b64(numbers.e.to_bytes(3, 'big'))}]}
    document = {'issuer': 'https://idp.example.org', 'authorization_endpoint': 'https://idp.example.org/auth',
                'token_endpoint': 'https://idp.example.org/token', 'jwks_uri': 'https://idp.example.org/jwks'}
    exchanged = []

    def token_for(email, nonce, sub='sub-1'):
        now = int(time.time())
        header = b64(json.dumps({'alg': 'RS256', 'kid': 'k'}).encode())
        payload = b64(json.dumps({'iss': 'https://idp.example.org', 'aud': 'tt-client', 'sub': sub, 'exp': now + 300, 'iat': now,
                                  'nonce': nonce, 'email': email, 'email_verified': True}).encode())
        signature = private.sign(f'{header}.{payload}'.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f'{header}.{payload}.{b64(signature)}'

    def run(email, sub='sub-1'):
        start = client.get('/auth/sso/start')
        assert start.status_code == 302
        with client.session_transaction() as flask_session:
            flow = flask_session[sso.SESSION_KEY]
        sso_module._post_form = lambda url, data, timeout=10: exchanged.append(data) or {'id_token': token_for(email, flow['nonce'], sub)}
        return client.get(f"/auth/sso/callback?state={flow['state']}&code=the-code")

    original_get, original_post = sso_module._get_json, sso_module._post_form
    sso_module._cache.clear()
    sso_module._get_json = lambda url, timeout=10: keys if url.endswith('/jwks') else document
    try:
        done = run('hod@college.edu')
        assert done.status_code == 302 and done.headers['Location'].endswith('/admin')
        assert exchanged[-1]['client_secret'] == 's3cret' and exchanged[-1]['code'] == 'the-code' and exchanged[-1]['code_verifier']
        me = api(client, 'GET', '/api/session')
        assert me.status_code == 200 and me.get_json()['data']['authenticated'] and me.get_json()['data']['username'] == hod['username']
        identity = factory.query('SELECT user_id, subject, email FROM sso_identities WHERE issuer = %s', ('https://idp.example.org',))
        assert identity == [{'user_id': hod['id'], 'subject': 'sub-1', 'email': 'hod@college.edu'}]
        assert factory.query('SELECT COUNT(*) AS n FROM user_sessions WHERE user_id = %s AND is_active = 1', (hod['id'],))[0]['n'] == 1
        client.get('/logout')

        # The same subject signs in again even after the email changes at the provider; no second identity row.
        again = run('renamed@college.edu')
        assert again.status_code == 302 and again.headers['Location'].endswith('/admin')
        assert factory.query('SELECT COUNT(*) AS n FROM sso_identities')[0]['n'] == 1
        client.get('/logout')

        # A student's email never links; an unknown email never creates an account; a foreign domain is refused.
        refused = run('stu@college.edu', sub='sub-2')
        assert 'sso_error=sso_no_account' in refused.headers['Location']
        assert 'sso_error=sso_no_account' in run('nobody@college.edu', sub='sub-3').headers['Location']
        assert 'sso_error=sso_domain_not_allowed' in run('hod@other.edu', sub='sub-4').headers['Location']
        assert factory.query('SELECT COUNT(*) AS n FROM sso_identities')[0]['n'] == 1
        with client.session_transaction() as flask_session:
            assert 'user_id' not in flask_session

        # The admin sees the link and can remove it.
        login(client, admin)
        overview = api(client, 'GET', '/api/integrations').get_json()['data']
        assert overview['sso_identities'][0]['username'] == hod['username'] and overview['sso_identities'][0]['email'] == 'renamed@college.edu'
        unlinked = api(client, 'DELETE', f"/api/integrations/sso/identities/{overview['sso_identities'][0]['id']}")
        assert unlinked.status_code == 200 and unlinked.get_json()['data']['sso_identities'] == []
    finally:
        sso_module._get_json, sso_module._post_form = original_get, original_post
        sso_module._cache.clear()
