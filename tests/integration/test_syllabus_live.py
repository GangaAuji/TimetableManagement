"""Syllabus coverage on the *_test database.

With the capability off, a topic on the mark screen or the mobile sync is ignored and the
coverage API answers 404. With it on, the mark and a mobile sync each store one lesson,
coverage is delivered / planned, and a configured academic calendar sets behind/ahead pace.
"""

import hashlib
import hmac
import json
import os
import tempfile
import time
import uuid
from datetime import time as clock

import pytest

import api.web  # noqa: F401  (breaks the services.export_jobs <-> api.web import cycle)
from services import api_keys
from services.reports_admin.accreditation import build
from services.reports_admin.renderers import render
from tests.factories import LECTURE_DATE, LectureDay
from tests.http_helpers import api, login

pytestmark = pytest.mark.live_db

DEVICE_ID = 'syllabus-device-ci'
SECRET = 'syllabus-device-secret'


@pytest.fixture(autouse=True)
def lecture_day(monkeypatch):
    monkeypatch.setattr('services.teacher_attendance.date', LectureDay)
    monkeypatch.setattr('services.syllabus.date', LectureDay)


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:500]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:500]
    return response.get_json()['error']['code']


def _mark(student, **lesson):
    body = {'attendance_date': LECTURE_DATE.isoformat(), 'marks': [{'student_id': student['student_id'], 'status': 'Present', 'remarks': ''}]}
    if lesson:
        body['lesson'] = lesson
    return body


def _signed(client, payload):
    body = json.dumps(payload).encode('utf-8')
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    path = '/mobile-sync/v1/attendance/sync'
    to_sign = '\n'.join(['POST', path, timestamp, nonce, hashlib.sha256(body).hexdigest()])
    signature = hmac.new(SECRET.encode('utf-8'), to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {
        'X-Mobile-Device-Id': DEVICE_ID, 'X-Mobile-Timestamp': timestamp, 'X-Mobile-Nonce': nonce,
        'X-Mobile-Signature': signature, 'Content-Type': 'application/json',
    }
    return client.open(path, method='POST', data=body, headers=headers)


def _event(student, timetable_id, **extra):
    base = {
        'event_uuid': uuid.uuid4().hex, 'student_id': student['student_id'], 'timetable_id': timetable_id,
        'attendance_date': '2026-11-10', 'status': 'Present', 'source': 'manual',
        'captured_at': '2026-11-10T11:05:00Z',
    }
    base.update(extra)
    return base


def _key(app, db):
    cursor = db.cursor(dictionary=True)
    try:
        with app.app_context():
            plaintext = api_keys.create_key(cursor, name='syllabus coverage', scopes=['catalog:read'], created_by=None)[1]
        db.commit()
        return plaintext
    finally:
        cursor.close()


def test_syllabus_off_stores_nothing_and_on_records_lessons_and_coverage(client, app, db, factory):
    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    tuesday = factory.lecture(setup, setup['teacher'], day='Tuesday', start=clock(11, 0), end=clock(12, 0))
    factory.insert(
        'mobile_devices', device_id=DEVICE_ID, device_name='Syllabus tablet', platform='android',
        owner_user_id=setup['teacher']['id'], api_key_secret=SECRET, is_active=1, rate_limit_per_minute=1000,
    )
    login(client, factory.user('Super Admin'))

    assert _error(api(client, 'GET', '/api/syllabus'), 404) == 'capability_off'
    types = _ok(api(client, 'GET', '/api/reports'))['types']
    assert 'syllabus-coverage' not in {item['id'] for item in types}
    assert _error(api(client, 'POST', '/api/reports', json={'report_type': 'syllabus-coverage', 'format': 'csv'}), 404) == 'capability_off'

    login(client, setup['teacher'])
    page = _ok(api(client, 'GET', f"/api/portal/attendance/mark/{setup['timetable_id']}"))
    assert 'syllabus' not in page
    saved = _ok(api(client, 'POST', f"/api/portal/attendance/mark/{setup['timetable_id']}", json=_mark(student, unit_id=1, topic='Ignored', hours=1)))
    assert saved['saved'] == 1
    assert factory.query('SELECT id FROM lesson_logs') == []

    synced = _signed(client, {'device_id': DEVICE_ID, 'events': [_event(student, tuesday, unit_id=1, topic='Ignored too', hours=1)]})
    assert synced.status_code == 200, synced.get_data(as_text=True)[:500]
    assert factory.query('SELECT id FROM lesson_logs') == []

    factory.capability('syllabus', True)
    login(client, factory.user('Super Admin'))
    created = _ok(api(client, 'PUT', f"/api/syllabus/{setup['subject_id']}", json={'units': [
        {'unit_no': 1, 'title': 'Kinematics', 'planned_hours': 4},
        {'unit_no': 2, 'title': 'Dynamics', 'planned_hours': 4},
    ]}))
    assert [row['title'] for row in created['coverage']['units']] == ['Kinematics', 'Dynamics']
    assert created['coverage']['units'][0]['pace'] == 'no_pace'
    assert _error(api(client, 'PUT', f"/api/syllabus/{setup['subject_id']}", json={'units': [{'unit_no': 1, 'title': '', 'planned_hours': 1}]}), 400) == 'syllabus_invalid'

    login(client, setup['teacher'])
    marked = _ok(api(client, 'GET', f"/api/portal/attendance/mark/{setup['timetable_id']}"))
    unit_id = marked['syllabus']['units'][0]['id']
    assert _error(api(client, 'POST', f"/api/portal/attendance/mark/{setup['timetable_id']}", json=_mark(student, unit_id=999999, topic='Nope', hours=1)), 400) == 'lesson_unit'
    assert factory.query('SELECT id FROM lesson_logs') == []
    _ok(api(client, 'POST', f"/api/portal/attendance/mark/{setup['timetable_id']}", json=_mark(student, unit_id=unit_id, topic='Displacement', hours=1)))
    [log] = factory.query('SELECT topic, hours, unit_id FROM lesson_logs')
    assert log['topic'] == 'Displacement' and float(log['hours']) == 1 and log['unit_id'] == unit_id

    login(client, factory.user('Super Admin'))
    coverage = _ok(api(client, 'GET', f"/api/syllabus?subject_id={setup['subject_id']}"))['coverage']
    first = coverage['units'][0]
    assert first['delivered_hours'] == 1 and first['percent'] == 25 and first['pace'] == 'no_pace'

    cursor = db.cursor(dictionary=True)
    try:
        with app.app_context():
            rows, fields, _labels, meta = build(cursor, 'syllabus-coverage', {'subject_id': setup['subject_id']})
    finally:
        cursor.close()
    assert fields[0] == 'subject_code' and meta['units'] == 2
    assert rows[0]['pace'] == 'no_pace' and rows[0]['delivered_hours'] == 1
    handle, path = tempfile.mkstemp(suffix='.csv')
    os.close(handle)
    try:
        render(path, 'csv', fields, rows, title='Syllabus coverage')
        with open(path, encoding='utf-8') as stored:
            exported = stored.read()
    finally:
        os.remove(path)
    assert 'Displacement' not in exported and 'Kinematics' in exported

    key = _key(app, db)
    public = client.get(f"/api/v1/subjects/{setup['subject_id']}/coverage", headers={'Authorization': f'Bearer {key}'})
    assert public.status_code == 200
    assert public.get_json()['data']['units'][0]['percent'] == 25

    mobile = _signed(client, {'device_id': DEVICE_ID, 'events': [_event(student, tuesday, unit_id=unit_id, topic='Velocity', hours=1)]})
    assert mobile.status_code == 200, mobile.get_data(as_text=True)[:500]
    assert mobile.get_json()['accepted'] == 1
    topics = {row['topic'] for row in factory.query('SELECT topic FROM lesson_logs')}
    assert topics == {'Displacement', 'Velocity'}

    login(client, factory.user('Super Admin'))
    after = _ok(api(client, 'GET', f"/api/syllabus?subject_id={setup['subject_id']}"))['coverage']['units'][0]
    assert after['delivered_hours'] == 2 and after['percent'] == 50
    assert _error(api(client, 'PUT', f"/api/syllabus/{setup['subject_id']}", json={'units': [
        {'id': created['coverage']['units'][1]['id'], 'unit_no': 2, 'title': 'Dynamics', 'planned_hours': 4},
    ]}), 409) == 'syllabus_in_use'

    kept = created['coverage']['units']
    _ok(api(client, 'PUT', f"/api/syllabus/{setup['subject_id']}", json={'units': [
        {'id': kept[0]['id'], 'unit_no': 1, 'title': 'Kinematics', 'planned_hours': 40},
        {'id': kept[1]['id'], 'unit_no': 2, 'title': 'Dynamics', 'planned_hours': 4},
    ]}))
    factory.capability('academic_terms', True)
    year_id = factory.insert('academic_years', name=f'Syl{factory._next()}', start_date='2026-01-01', end_date='2026-12-31')
    factory.insert(
        'academic_terms', institution_id=1, academic_year_id=year_id, name='Teaching', kind='teaching',
        start_date='2026-08-03', end_date='2026-12-20',
    )
    paced = _ok(api(client, 'GET', f"/api/syllabus?subject_id={setup['subject_id']}"))['coverage']
    assert paced['elapsed_weeks'] and paced['total_weeks'] and paced['elapsed_weeks'] < paced['total_weeks']
    assert paced['units'][0]['pace'] == 'behind'
    assert paced['units'][0]['expected_hours'] == pytest.approx(round(40 * paced['elapsed_weeks'] / paced['total_weeks'], 1), abs=0.05)

    factory.capability('syllabus', False)
    assert _error(api(client, 'GET', '/api/syllabus'), 404) == 'capability_off'
    hidden = client.get(f"/api/v1/subjects/{setup['subject_id']}/coverage", headers={'Authorization': f'Bearer {key}'})
    assert hidden.status_code == 404 and hidden.get_json()['error']['code'] == 'capability_off'
    login(client, factory.user('Student', setup=setup))
    factory.capability('syllabus', True)
    assert _error(api(client, 'GET', '/api/syllabus'), 403) == 'forbidden'
