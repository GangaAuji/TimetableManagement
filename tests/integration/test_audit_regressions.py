"""Regression tests for the bugs found in the audit. Each one fails with its file(s) reverted to HEAD ef1008b,
except the sign-in lock wait, which was introduced and fixed after HEAD.
"""

import os
import time as time_module
from datetime import time, timedelta

import pytest

from academic_rules.availability import manual_add_availability_block
from tests.factories import LECTURE_DATE, LectureDay
from tests.http_helpers import SAME_ORIGIN, api, csrf_token, login, signed_in_as

LOCKOUT_ATTEMPTS = 5


# Login fallback (services/login.py, data_access/login.py)

@pytest.mark.parametrize('role', ('Student', 'Teacher'))
def test_an_unlinked_account_does_not_borrow_the_first_linked_record(client, factory, role):
    factory.user(role)
    unlinked = factory.user(role, link=False)
    response = login(client, unlinked, '/login')
    assert response.status_code != 302
    assert signed_in_as(client) is None


# Failed logins lock the account (services/login.py)

@pytest.mark.parametrize('role, path', [('Student', '/login'), ('Admin', '/admin/login')])
def test_repeated_failed_logins_lock_the_account(client, factory, role, path):
    user = factory.user(role)
    for _ in range(LOCKOUT_ATTEMPTS):
        login(client, user, path, password='Wrong-Pass-1')
    [row] = factory.query(
        'SELECT status, failed_attempts, locked_until > NOW() AS locked FROM users WHERE id = %s', (user['id'],),
    )
    assert (row['status'], row['failed_attempts'], row['locked']) == ('active', LOCKOUT_ATTEMPTS, 1)
    assert login(client, user, path).status_code != 302
    assert signed_in_as(client) is None


def test_fewer_failed_logins_do_not_lock(client, factory):
    user = factory.user('Student')
    for _ in range(LOCKOUT_ATTEMPTS - 1):
        login(client, user, password='Wrong-Pass-1')
    assert login(client, user).status_code == 302


# Legacy /admin/users/export checked users_view_user (routes/user_management/actions.py)

def _hod_with(factory, client, *permissions):
    hod = factory.user('HOD')
    for name in permissions:
        factory.grant(hod, name)
    login(client, hod)
    return hod


def test_legacy_user_export_needs_users_export_data(client, factory):
    _hod_with(factory, client, 'users_view_user')
    assert client.get('/admin/users/export').status_code == 403


def test_legacy_user_export_with_users_export_data(client, factory):
    _hod_with(factory, client, 'users_export_data')
    response = client.get('/admin/users/export')
    assert response.status_code == 200
    assert response.mimetype == 'text/csv'


def test_legacy_user_export_without_a_session_is_401(client):
    assert client.get('/admin/users/export').status_code == 401


# Report download used its own check, not the shared one (api/web/reports.py)

def _report(app, factory):
    owner = factory.user('Admin')
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'reports')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'regression-users.csv')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('id,username\n')
    return factory.insert(
        'processed_reports', report_type='users-export', status='completed', row_count=0,
        file_name='regression-users.csv', file_path=path, created_by=owner['id'],
    )


def test_a_denied_report_download_is_the_standard_denial_and_is_audited(app, client, factory):
    report_id = _report(app, factory)
    hod = _hod_with(factory, client)
    response = client.get(f'/api/reports/{report_id}/download')
    assert response.status_code == 403
    assert response.get_json()['error'] == {'code': 'forbidden', 'message': 'You do not have permission to do that.'}
    audited = factory.query(
        "SELECT 1 FROM user_activity_log WHERE user_id = %s AND activity_type = 'reports_download_denied'",
        (hod['id'],),
    )
    assert audited


def test_a_permitted_report_download_succeeds(app, client, factory):
    report_id = _report(app, factory)
    _hod_with(factory, client, 'reports_export')
    assert client.get(f'/api/reports/{report_id}/download').status_code == 200


# Teacher marked any student on any date (services/teacher_attendance.py)

@pytest.fixture
def lecture_day(monkeypatch):
    monkeypatch.setattr('services.teacher_attendance.date', LectureDay)


def _mark(client, setup, student_id, when=LECTURE_DATE):
    return api(client, 'POST', f'/api/portal/attendance/mark/{setup["timetable_id"]}', json={
        'attendance_date': when.isoformat(),
        'marks': [{'student_id': student_id, 'status': 'Present', 'remarks': ''}],
    })


def _marked(factory, setup):
    return factory.query('SELECT student_id FROM attendance WHERE timetable_id = %s', (setup['timetable_id'],))


def test_teacher_cannot_mark_a_student_from_another_class(client, factory, lecture_day):
    setup = factory.academic()
    outsider = factory.user('Student', setup=factory.academic())
    login(client, setup['teacher'])
    response = _mark(client, setup, outsider['student_id'])
    assert response.status_code == 400
    assert _marked(factory, setup) == []


@pytest.mark.parametrize('days', (-7, -1, 7))
def test_teacher_cannot_mark_another_date(client, factory, lecture_day, days):
    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    login(client, setup['teacher'])
    response = _mark(client, setup, student['student_id'], LECTURE_DATE + timedelta(days=days))
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'portal_date'
    assert _marked(factory, setup) == []


# faculty_availability.day_of_week is tinyint 1-7; the query passed 'Monday' (academic_rules/availability.py)

def test_manual_add_honours_an_unavailable_block_on_that_weekday(db, factory):
    teacher = factory.user('Teacher')
    factory.insert('faculty_availability', faculty_id=teacher['faculty_id'], day_of_week=1,
                   is_available=0, start_time=time(9), end_time=time(11))
    cursor = db.cursor(dictionary=True)
    try:
        message = manual_add_availability_block(cursor, teacher['faculty_id'], 'Monday', time(9), time(10))
        other_day = manual_add_availability_block(cursor, teacher['faculty_id'], 'Tuesday', time(9), time(10))
    finally:
        cursor.close()
        db.commit()
    assert message == 'Faculty is marked unavailable during the selected time.'
    assert other_day is None


# Sign-in held a lock on the users row while log_activity wrote on another connection (services/login.py)

@pytest.mark.parametrize('role', ('Student', 'Admin'))
def test_a_successful_login_is_recorded_in_the_activity_log(client, factory, role):
    user = factory.user(role)
    assert login(client, user).status_code == 302
    rows = factory.query(
        "SELECT 1 FROM user_activity_log WHERE user_id = %s AND activity_type IN ('login', 'admin_login')",
        (user['id'],),
    )
    assert rows


@pytest.mark.parametrize('role', ('Student', 'Admin'))
def test_login_with_the_default_lock_wait_takes_under_two_seconds(default_lock_wait_app, db, factory, reset_rate_limits, role):
    client = default_lock_wait_app.test_client()
    with default_lock_wait_app.app_context():
        from extensions import get_db_connection

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT @@SESSION.innodb_lock_wait_timeout')
        assert cursor.fetchone()[0] > 2, 'this test needs the server default lock wait'
        connection.close()
    user = factory.user(role)
    token = csrf_token(client)
    started = time_module.perf_counter()
    response = client.post('/admin/login' if role == 'Admin' else '/login', headers={'Origin': SAME_ORIGIN},
                           data={'username': user['username'], 'password': user['password'], 'csrf_token': token})
    elapsed = time_module.perf_counter() - started
    assert response.status_code == 302
    assert elapsed < 2, f'sign-in took {elapsed:.1f} s'
