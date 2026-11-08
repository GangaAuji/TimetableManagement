"""Sensitive endpoints: 401 with no session, 403 without the permission, success with it.

The HOD defaults hold none of these permissions, so a HOD is the user
without the permission and the same HOD given a direct user grant is the
user with it.
"""

import os
from dataclasses import dataclass
from typing import Callable

import pytest

from tests.http_helpers import SAME_ORIGIN, api, csrf_token, login


@dataclass
class Case:
    permission: str
    call: Callable  # (client, context) -> response
    succeeded: Callable = lambda response, context: response.status_code == 200


def _put_role_permissions(client, context):
    return api(client, 'PUT', f'/api/roles/{context["teacher_role_id"]}/permissions',
               json={'permission_ids': context['teacher_permission_ids']})


def _grant_user_permission(client, context):
    return api(client, 'POST', f'/api/users/{context["target"]["id"]}/permissions',
               json={'permission_name': 'attendance_view', 'department_id': None})


def _reset_password(client, context):
    return api(client, 'POST', f'/api/users/{context["target"]["id"]}/password', json={})


def _export_users(client, context):
    return client.get('/api/users/export')


def _update_attendance(client, context):
    data = {'attendance_id': context['attendance_id'], 'status': 'Present', 'remarks': 'harness',
            'csrf_token': csrf_token(client)}
    return client.post('/admin/attendance/manage/update', data=data, headers={'Origin': SAME_ORIGIN})


def _attendance_updated(response, context):
    [row] = context['factory'].query('SELECT status FROM attendance WHERE id = %s', (context['attendance_id'],))
    return response.status_code == 200 and row['status'] == 'Present'


def _save_settings(client, context):
    return client.post('/api/settings', data={'site_title': 'Harness Title'}, content_type='multipart/form-data',
                       headers={'Origin': SAME_ORIGIN, 'X-CSRFToken': csrf_token(client)})


def _download_report(client, context):
    return client.get(f'/api/reports/{context["report_id"]}/download')


CASES = {
    'PUT /api/roles/<id>/permissions': Case('roles_change_role', _put_role_permissions),
    'POST /api/users/<id>/permissions': Case('users_manage_permissions', _grant_user_permission),
    'POST /api/users/<id>/password': Case('users_change_password', _reset_password),
    'GET /api/users/export': Case('users_export_data', _export_users),
    'POST /admin/attendance/manage/update': Case('attendance_manage', _update_attendance, _attendance_updated),
    'POST /api/settings': Case('admin_change_settings', _save_settings),
    'GET /api/reports/<id>/download': Case('reports_export', _download_report),
}


@pytest.fixture
def context(app, factory):
    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    owner = factory.user('Admin')
    [role] = factory.query("SELECT id FROM roles WHERE name = 'Teacher'")
    permission_ids = [
        row['id'] for row in factory.query(
            'SELECT rp.permission_id AS id FROM role_permissions rp WHERE rp.role_id = %s', (role['id'],)
        )
    ]
    session_id = factory.insert(
        'lecture_sessions', timetable_id=setup['timetable_id'], session_date='2026-11-02', status='held',
        taught_by=setup['teacher']['id'], marked_by=setup['teacher']['faculty_id'], source='teacher',
    )
    attendance_id = factory.insert(
        'attendance', student_id=student['student_id'], timetable_id=setup['timetable_id'], session_id=session_id,
        attendance_date='2026-11-02', status='Absent', marked_by=setup['teacher']['faculty_id'],
    )
    reports = os.path.join(app.config['UPLOAD_FOLDER'], 'reports')
    os.makedirs(reports, exist_ok=True)
    path = os.path.join(reports, 'harness-users.csv')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('id,username\n')
    report_id = factory.insert(
        'processed_reports', report_type='users-export', status='completed', row_count=0,
        file_name='harness-users.csv', file_path=path, created_by=owner['id'],
    )
    return {
        'factory': factory, 'target': setup['teacher'], 'teacher_role_id': role['id'],
        'teacher_permission_ids': permission_ids, 'attendance_id': attendance_id, 'report_id': report_id,
    }


def _hod(factory, client, permission=None):
    hod = factory.user('HOD')
    assert permission not in factory.role_permissions('HOD')
    if permission:
        factory.grant(hod, permission)
    assert login(client, hod).status_code == 302
    return hod


@pytest.mark.parametrize('name', CASES)
def test_no_session_is_401(client, context, name):
    response = CASES[name].call(client, context)
    assert response.status_code == 401, response.get_data(as_text=True)[:200]


@pytest.mark.parametrize('name', [name for name in CASES if name != 'POST /admin/attendance/manage/update'])
def test_without_the_permission_is_403(client, factory, context, name):
    _hod(factory, client)
    response = CASES[name].call(client, context)
    assert response.status_code == 403, response.get_data(as_text=True)[:200]
    assert response.get_json()['error']['code'] == 'forbidden'


def test_without_the_permission_the_attendance_form_changes_nothing(client, factory, context):
    _hod(factory, client)
    response = _update_attendance(client, context)
    assert response.status_code == 302
    assert not _attendance_updated(response, context)


@pytest.mark.xfail(strict=True, reason=(
    'POST /admin/attendance/manage/update uses the legacy security.has_permission decorator, which '
    'redirects (302) instead of answering 403 when the permission is missing.'
))
def test_without_the_permission_the_attendance_form_is_403(client, factory, context):
    _hod(factory, client)
    assert _update_attendance(client, context).status_code == 403


@pytest.mark.parametrize('name', CASES)
def test_with_the_permission_succeeds(client, factory, context, name):
    case = CASES[name]
    _hod(factory, client, case.permission)
    response = case.call(client, context)
    assert case.succeeded(response, context), (response.status_code, response.get_data(as_text=True)[:300])
