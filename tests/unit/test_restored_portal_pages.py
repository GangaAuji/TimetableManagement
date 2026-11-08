"""Device keys and teacher assignments. No live database."""

from flask import Flask, session

from api.web import devices as device_api
from api.web import teacher as teacher_api
from api.web.access import InputError
import pytest


def test_device_form_rejects_a_short_rate_limit():
    assert device_api.device_form({
        'device_id': 'lab-phone.1',
        'device_name': 'Lab',
        'platform': 'Android',
        'owner_user_id': None,
        'rate_limit': 120,
    }) == ('lab-phone.1', 'Lab', 'Android', None, 120)
    with pytest.raises(InputError):
        device_api.device_form({'device_id': 'lab', 'rate_limit': 5})


def test_new_device_key_is_returned_once_and_cleared_from_the_session(monkeypatch):
    def fake_create(device_id, device_name, platform, owner_user_id, rate_limit, current):
        current['new_mobile_device_secret'] = 'shown-once'
        current['new_mobile_device_for'] = device_id
        return 'shown-once'

    monkeypatch.setattr(device_api, 'create_mobile_device', fake_create)
    app = Flask('devices')
    app.secret_key = 'test'
    with app.test_request_context('/api/devices', method='POST', json={
        'device_id': 'lab-phone',
        'device_name': 'Lab',
        'platform': 'Android',
        'rate_limit': 120,
    }):
        session['user_id'] = 1
        session['role'] = 'Admin'
        response, status = device_api._create()
        payload = response.get_json()
        leftover = session.get('new_mobile_device_secret')
    assert status == 200
    assert payload['data']['secret'] == 'shown-once'
    assert leftover is None


def test_attendance_filters_keep_the_date_and_optional_ids():
    from api.web.attendance import record_filters
    assert record_filters({'date': '2026-11-09', 'course_id': '4', 'class_id': '', 'division_id': '2'}) == ('2026-11-09', 4, None, 2)
    with pytest.raises(InputError):
        record_filters({'date': 'tomorrow'})


def test_faculty_proxy_row_omits_internal_ids():
    from api.web.people.faculty import proxy_row
    row = proxy_row({
        'id': 9,
        'absence_date': '2026-11-09',
        'day': 'Monday',
        'start_time': '09:00',
        'end_time': '10:00',
        'subject': 'Maths',
        'subject_id': 3,
        'original_faculty': 'Ada',
        'original_faculty_id': 4,
        'proxy_faculty': '',
        'status': 'UNASSIGNED',
        'approval_status': 'PENDING',
    })
    assert row['subject'] == 'Maths'
    assert row['proxy_faculty'] == ''
    assert 'subject_id' not in row
    assert 'original_faculty_id' not in row


def test_faculty_attendance_filters_ignore_an_unknown_status():
    from api.web.attendance import faculty_filters
    chosen = faculty_filters({
        'q': 'Ada',
        'status': 'drop',
        'date_from': '2026-10-01',
        'date_to': '2026-10-31',
        'page': '2',
        'per_page': '50',
    })
    assert chosen['status'] == ''
    assert chosen['q'] == 'Ada'
    assert chosen['page'] == 2
    assert chosen['per_page'] == 50
    with pytest.raises(InputError):
        faculty_filters({'date_from': '2026-11-02', 'date_to': '2026-10-01'})


def test_mobile_log_filters_keep_the_old_limits():
    from api.web.attendance import mobile_filters, reprocess_limit
    assert mobile_filters({
        'date': '2026-11-09',
        'processing_status': 'FAILED',
        'device_id': 'lab',
        'student_query': 'Ada',
        'limit': '900',
    }) == ('2026-11-09', 'failed', 'lab', 'Ada', 500)
    assert reprocess_limit({}) == 100
    assert reprocess_limit({'limit': 25}) == 25


def test_faculty_activity_row_keeps_shift_and_marker():
    from datetime import timedelta
    from api.web.attendance import _activity_row
    row = _activity_row({
        'faculty_id': 4,
        'faculty_name': 'Ada',
        'employee_id': 'E1',
        'department_name': 'Science',
        'attendance_date': '2026-11-09',
        'status': 'Present',
        'shift_name': 'Morning',
        'shift_start_time': timedelta(hours=9),
        'shift_end_time': timedelta(hours=13),
        'marked_by_username': 'hacker',
        'email': 'ada@example.com',
    })
    assert row['shift'] == 'Morning'
    assert row['start_time'] == '09:00'
    assert row['marked_by'] == 'hacker'
    assert 'email' not in row


def test_assignment_rows_drop_a_syllabus_that_is_not_https():
    rows = teacher_api.assignment_rows([{
        'subject': 'Maths',
        'department': 'Science',
        'course': 'FY',
        'class': 'First',
        'division': 'A',
        'syllabus_url': 'javascript:alert(1)',
    }])
    assert rows[0]['subject'] == 'Maths'
    assert rows[0]['class_name'] == 'First'
    assert rows[0]['syllabus_url'] == ''
