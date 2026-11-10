"""Face attendance safeguards: encrypted templates, consent, passive liveness, the decision audit, session codes."""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta

import pytest

import api.web  # noqa: F401  (breaks the services.export_jobs <-> api.web import cycle)
from services.face import safeguards, templates
from tests.factories import LECTURE_DATE, LectureDay
from tests.http_helpers import api, login

DEVICE_ID = 'device-ci-1'
SECRET = 'device-secret-for-tests'
TEMPLATE = [1.0] + [0.0] * 191


@pytest.fixture(autouse=True)
def lecture_day(monkeypatch):
    monkeypatch.setattr('services.teacher_attendance.date', LectureDay)


@pytest.fixture
def lesson(factory):
    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    factory.insert(
        'mobile_devices', device_id=DEVICE_ID, device_name='CI tablet', platform='android',
        owner_user_id=setup['teacher']['id'], api_key_secret=SECRET, is_active=1, rate_limit_per_minute=1000,
    )
    return setup, student


def consent(factory, user, version='2026-01'):
    return factory.insert('face_consents', user_id=user['id'], notice_version=version, given_at=datetime.utcnow(), source='admin')


def signed(client, method, path, payload=None):
    body = json.dumps(payload).encode('utf-8') if payload is not None else b''
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    to_sign = '\n'.join([method, path, timestamp, nonce, hashlib.sha256(body).hexdigest()])
    signature = hmac.new(SECRET.encode('utf-8'), to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {
        'X-Mobile-Device-Id': DEVICE_ID, 'X-Mobile-Timestamp': timestamp, 'X-Mobile-Nonce': nonce,
        'X-Mobile-Signature': signature, 'Content-Type': 'application/json',
    }
    return client.open(path, method=method, data=body, headers=headers)


def event(student, timetable_id, **extra):
    base = {
        'event_uuid': uuid.uuid4().hex, 'student_id': student['student_id'], 'timetable_id': timetable_id,
        'attendance_date': LECTURE_DATE.isoformat(), 'status': 'Present', 'confidence': 0.91,
        'captured_at': f'{LECTURE_DATE.isoformat()}T09:05:00Z',
    }
    base.update(extra)
    return base


def sync(client, *events):
    return signed(client, 'POST', '/mobile-sync/v1/attendance/sync', {'device_id': DEVICE_ID, 'events': list(events)})


def audit_rows(factory, student=None):
    clause, params = ('WHERE student_id = %s', (student['student_id'],)) if student else ('', ())
    return factory.query(f'SELECT decision, reason, confidence, frame_hash FROM face_recognition_audit {clause} ORDER BY id', params)


def stored_template(factory, user):
    rows = factory.query('SELECT embedding_json FROM mobile_face_templates WHERE user_id = %s', (user['id'],))
    return rows[0]['embedding_json'] if rows else None


# Encryption at rest

def test_uploaded_templates_are_encrypted_and_served_decrypted_only_with_consent(client, factory, lesson):
    setup, student = lesson
    refused = signed(client, 'POST', f"/mobile-sync/v1/users/{student['id']}/face-template", {'faceTemplate': TEMPLATE})
    assert refused.status_code == 403 and 'consent' in refused.get_json()['error']
    assert stored_template(factory, student) is None

    consent(factory, student)
    saved = signed(client, 'POST', f"/mobile-sync/v1/users/{student['id']}/face-template", {'faceTemplate': TEMPLATE})
    assert saved.status_code == 200, saved.get_json()
    stored = stored_template(factory, student)
    assert templates.is_encrypted(stored) and '1.0' not in stored
    with client.application.app_context():
        assert templates.decode_template(stored)[0] == pytest.approx(1.0)

    listing = signed(client, 'GET', '/mobile-sync/v1/users').get_json()
    mine = [row for row in listing['users'] if row['user_id'] == student['id']]
    assert mine and mine[0]['has_face_template'] is True and mine[0]['face_template'][0] == pytest.approx(1.0)

    factory.execute('UPDATE face_consents SET withdrawn_at = UTC_TIMESTAMP() WHERE user_id = %s', (student['id'],))
    listing = signed(client, 'GET', '/mobile-sync/v1/users').get_json()
    mine = [row for row in listing['users'] if row['user_id'] == student['id']]
    assert mine and mine[0]['has_face_template'] is False and mine[0]['face_template'] is None


def test_plaintext_templates_are_read_and_the_cli_encrypts_and_rotates_them(app, factory, lesson, monkeypatch):
    setup, student = lesson
    consent(factory, student)
    factory.insert('mobile_face_templates', user_id=student['id'], embedding_json=json.dumps(TEMPLATE), is_active=1)
    runner = app.test_cli_runner()

    status = runner.invoke(args=['face', 'status'])
    assert status.exit_code == 0, status.output
    assert 'plaintext 1' in status.output and 'Key: configured' in status.output

    encrypt = runner.invoke(args=['face', 'encrypt-templates'])
    assert encrypt.exit_code == 0, encrypt.output
    assert 'rewritten 1' in encrypt.output
    first = stored_template(factory, student)
    assert templates.is_encrypted(first)
    assert runner.invoke(args=['face', 'encrypt-templates']).output.strip().endswith('already current 1, unreadable 0')

    rotate = runner.invoke(args=['face', 'rotate-key'])
    assert rotate.exit_code != 0 and 'FACE_TEMPLATE_KEY_PREVIOUS' in rotate.output

    from cryptography.fernet import Fernet
    new_key = Fernet.generate_key().decode('ascii')
    monkeypatch.setitem(app.config, 'FACE_TEMPLATE_KEY_PREVIOUS', app.config['FACE_TEMPLATE_KEY'])
    monkeypatch.setitem(app.config, 'FACE_TEMPLATE_KEY', new_key)
    rotate = runner.invoke(args=['face', 'rotate-key'])
    assert rotate.exit_code == 0, rotate.output
    second = stored_template(factory, student)
    assert second != first and templates.is_encrypted(second)
    monkeypatch.setitem(app.config, 'FACE_TEMPLATE_KEY_PREVIOUS', None)
    with app.app_context():
        assert templates.decode_template(second)[0] == pytest.approx(1.0)
        assert templates.decode_template(first) is None  # the retired key no longer reads the old row

    generated = runner.invoke(args=['face', 'generate-key'])
    assert generated.exit_code == 0
    Fernet(generated.output.strip().encode('ascii'))


def test_templates_fall_back_to_plaintext_without_a_key_and_health_reports_it(make_app, client):
    plain = make_app(FACE_TEMPLATE_KEY=None)
    with plain.app_context():
        assert templates.encode_template([0.5, 0.5]) == '[0.5,0.5]'
        assert templates.key_problem() and 'FACE_TEMPLATE_KEY' in templates.key_problem()
    assert plain.test_client().get('/health').get_json()['checks']['face_key'] == 'missing'
    assert client.get('/health').get_json()['checks']['face_key'] == 'configured'


# Passive liveness and the audit

def test_every_recognition_is_audited_and_weak_ones_are_rejected(client, factory, lesson):
    setup, student = lesson
    consent(factory, student)
    factory.insert('mobile_face_templates', user_id=student['id'], embedding_json=templates.encode_template(TEMPLATE), is_active=1)

    weak = sync(client, event(student, setup['timetable_id'], confidence=0.42))
    assert weak.status_code == 400
    assert 'confidence' in weak.get_json()['results'][0]['message']

    spoof = sync(client, event(student, setup['timetable_id'], liveness_score=0.1))
    assert spoof.status_code == 400 and 'Liveness' in spoof.get_json()['results'][0]['message']

    good = sync(client, event(student, setup['timetable_id'], frame_hash='frame-A', liveness_score=0.9))
    assert good.status_code == 200, good.get_json()
    assert good.get_json()['accepted'] == 1

    replay = sync(client, event(student, setup['timetable_id'], frame_hash='frame-A'))
    assert replay.status_code == 400 and 'already used' in replay.get_json()['results'][0]['message']

    rows = audit_rows(factory, student)
    assert [(row['decision'], row['reason']) for row in rows] == [
        ('rejected', 'low_confidence'), ('rejected', 'low_liveness'), ('accepted', 'ok'), ('rejected', 'duplicate_frame'),
    ]
    assert float(rows[2]['confidence']) == pytest.approx(0.91) and rows[2]['frame_hash'] == safeguards.frame_hash_of('frame-A')
    assert factory.query('SELECT status FROM attendance WHERE student_id = %s', (student['student_id'],)) == [{'status': 'Present'}]
    assert factory.query('SELECT COUNT(*) AS n FROM attendance_logs WHERE student_id = %s', (student['student_id'],))[0]['n'] == 1


def test_recognition_needs_consent_and_a_fresh_template_but_manual_marks_do_not(client, factory, lesson, make_app):
    setup, student = lesson
    refused = sync(client, event(student, setup['timetable_id']))
    assert refused.status_code == 400 and 'consented' in refused.get_json()['results'][0]['message']

    consent(factory, student)
    factory.insert(
        'mobile_face_templates', user_id=student['id'], embedding_json=templates.encode_template(TEMPLATE), is_active=1,
        created_at=datetime.utcnow() - timedelta(days=800), updated_at=datetime.utcnow() - timedelta(days=800),
    )
    stale = sync(client, event(student, setup['timetable_id']))
    assert stale.status_code == 400 and 're-enrol' in stale.get_json()['results'][0]['message']

    manual = sync(client, event(student, setup['timetable_id'], status='Absent', confidence=None, source='manual'))
    assert manual.status_code == 200 and manual.get_json()['accepted'] == 1
    assert [(row['decision'], row['reason']) for row in audit_rows(factory, student)] == [
        ('rejected', 'no_consent'), ('rejected', 'template_too_old'), ('accepted', 'manual'),
    ]


# Session codes

def test_devices_mark_only_the_lecture_the_teacher_opened(make_app, factory, lesson):
    setup, student = lesson
    consent(factory, student)
    factory.insert('mobile_face_templates', user_id=student['id'], embedding_json=templates.encode_template(TEMPLATE), is_active=1)
    app = make_app(FACE_REQUIRE_SESSION_CODE=True, FACE_SESSION_CODE_MINUTES=30)
    client = app.test_client()

    without = sync(client, event(student, setup['timetable_id']))
    assert without.status_code == 400 and 'session code' in without.get_json()['results'][0]['message']

    login(client, setup['teacher'])
    opened = api(client, 'POST', f"/api/portal/attendance/open/{setup['timetable_id']}", json={'date': LECTURE_DATE.isoformat()})
    assert opened.status_code == 200, opened.get_json()
    code = opened.get_json()['data']['session_code']
    assert len(code) == 8 and opened.get_json()['data']['expires_at']
    [session_row] = factory.query(
        'SELECT status, session_code, session_code_expires_at FROM lecture_sessions WHERE timetable_id = %s', (setup['timetable_id'],),
    )
    assert session_row['status'] == 'held' and session_row['session_code'] == code

    wrong = sync(client, event(student, setup['timetable_id'], session_code='NOPE1234'))
    assert wrong.status_code == 400 and 'does not match' in wrong.get_json()['results'][0]['message']

    right = sync(client, event(student, setup['timetable_id'], session_code=code.lower()))
    assert right.status_code == 200, right.get_json()

    closed = api(client, 'POST', f"/api/portal/attendance/close/{setup['timetable_id']}", json={'date': LECTURE_DATE.isoformat()})
    assert closed.status_code == 200 and closed.get_json()['data']['status'] == 'closed'
    late = sync(client, event(student, setup['timetable_id'], session_code=code))
    assert late.status_code == 400 and 'expired' in late.get_json()['results'][0]['message']

    reasons = [row['reason'] for row in audit_rows(factory, student)]
    assert reasons == ['session_code_required', 'session_code_invalid', 'ok', 'session_code_expired']


def test_the_device_owner_opens_a_lecture_from_the_device(client, factory, lesson):
    setup, student = lesson
    other = factory.user('Teacher', setup=setup)
    stranger = signed(client, 'POST', '/mobile-sync/v1/sessions/open', {
        'timetable_id': setup['timetable_id'], 'attendance_date': LECTURE_DATE.isoformat(), 'user_id': other['id'],
    })
    assert stranger.status_code == 403

    opened = signed(client, 'POST', '/mobile-sync/v1/sessions/open', {
        'timetable_id': setup['timetable_id'], 'attendance_date': LECTURE_DATE.isoformat(),
    })
    assert opened.status_code == 200, opened.get_json()
    payload = opened.get_json()
    assert len(payload['session_code']) == 8 and payload['expires_at'].endswith('Z')
    [row] = factory.query('SELECT source, status, session_code FROM lecture_sessions WHERE id = %s', (payload['session_id'],))
    assert (row['source'], row['status'], row['session_code']) == ('mobile', 'held', payload['session_code'])


def test_only_the_teacher_or_proxy_may_open_and_a_cancelled_lecture_cannot_be_opened(client, factory, lesson):
    setup, _ = lesson
    other = factory.user('Teacher', setup=setup)
    login(client, other)
    assert api(client, 'POST', f"/api/portal/attendance/open/{setup['timetable_id']}", json={'date': LECTURE_DATE.isoformat()}).status_code == 403

    login(client, setup['teacher'])
    cancelled = api(client, 'POST', f"/api/portal/attendance/cancel/{setup['timetable_id']}", json={
        'date': LECTURE_DATE.isoformat(), 'reason': 'faculty_absent', 'note': '',
    })
    assert cancelled.status_code == 200
    refused = api(client, 'POST', f"/api/portal/attendance/open/{setup['timetable_id']}", json={'date': LECTURE_DATE.isoformat()})
    assert refused.status_code == 409 and refused.get_json()['error']['code'] == 'portal_cancelled'


# Consent and retention

def test_withdrawing_consent_deletes_templates_and_the_purge_honours_retention(client, factory, lesson, app):
    setup, student = lesson
    login(client, student)
    before = api(client, 'GET', '/api/account/face-consent').get_json()['data']
    assert before == {'required': True, 'notice_version': '2026-01', 'given': False, 'given_at': '', 'has_template': False}

    assert api(client, 'POST', '/api/account/face-consent', json={'agree': False}).status_code == 400
    given = api(client, 'POST', '/api/account/face-consent', json={'agree': True}).get_json()['data']
    assert given['given'] is True and given['given_at']
    factory.insert('mobile_face_templates', user_id=student['id'], embedding_json=templates.encode_template(TEMPLATE), is_active=1)
    assert api(client, 'GET', '/api/account/face-consent').get_json()['data']['has_template'] is True

    withdrawn = api(client, 'DELETE', '/api/account/face-consent').get_json()['data']
    assert withdrawn['given'] is False and withdrawn['has_template'] is False and withdrawn['templates_deleted'] == 1
    assert factory.query('SELECT action FROM audit_logs WHERE action LIKE %s ORDER BY id', ('face_consent_%',)) == [
        {'action': 'face_consent_given'}, {'action': 'face_consent_withdrawn'},
    ]

    # Retention: a withdrawn person's template that was not deleted (older data) goes after FACE_RETENTION_DAYS.
    other = factory.user('Student', setup=setup)
    factory.insert('face_consents', user_id=other['id'], notice_version='2026-01', given_at=datetime.utcnow() - timedelta(days=60),
                   withdrawn_at=datetime.utcnow() - timedelta(days=10), source='web')
    factory.insert('mobile_face_templates', user_id=other['id'], embedding_json=templates.encode_template(TEMPLATE), is_active=1)
    left = factory.user('Student', setup=setup, status='inactive')
    consent(factory, left)
    factory.insert('mobile_face_templates', user_id=left['id'], embedding_json=templates.encode_template(TEMPLATE), is_active=1)
    factory.execute('UPDATE users SET updated_at = %s WHERE id = %s', (datetime.utcnow() - timedelta(days=40), left['id']))

    runner = app.test_cli_runner()
    dry = runner.invoke(args=['face', 'purge', '--dry-run'])
    assert dry.exit_code == 0 and 'withdrawn 0, inactive users 1' in dry.output and 'nothing was deleted' in dry.output
    assert stored_template(factory, other) and stored_template(factory, left)

    applied = runner.invoke(args=['face', 'purge', '--days', '5'])
    assert applied.exit_code == 0, applied.output
    assert 'withdrawn 1, inactive users 1' in applied.output
    assert stored_template(factory, other) is None and stored_template(factory, left) is None

    cli = runner.invoke(args=['face', 'consent', str(student['id']), 'give'])
    assert cli.exit_code == 0 and 'Consent recorded' in cli.output
    cli = runner.invoke(args=['face', 'consent', str(student['id']), 'withdraw'])
    assert cli.exit_code == 0 and '1 consent row(s) closed' in cli.output


def test_the_nightly_job_runs_the_purge(app, factory, lesson):
    from services.attendance_jobs import run_once

    setup, student = lesson
    factory.insert('face_consents', user_id=student['id'], notice_version='2026-01', given_at=datetime.utcnow() - timedelta(days=90),
                   withdrawn_at=datetime.utcnow() - timedelta(days=45), source='web')
    factory.insert('mobile_face_templates', user_id=student['id'], embedding_json=templates.encode_template(TEMPLATE), is_active=1)
    run_once(app, today=LECTURE_DATE + timedelta(days=1))
    assert stored_template(factory, student) is None
