"""Sign-in: each role on its own form, the wrong form refused, the session reported, locked accounts refused."""

import pytest

from tests.http_helpers import login, signed_in_as

STUDENT_FORM = ('Student', 'Teacher', 'HOD')
ADMIN_FORM = ('Admin', 'HOD', 'Super Admin')


def _assert_signed_in(client, response, user):
    assert response.status_code == 302, response.get_data(as_text=True)[:300]
    account = signed_in_as(client)
    assert account is not None
    assert (account['username'], account['role']) == (user['username'], user['role'])


def _assert_refused(client, response):
    assert response.status_code != 302
    assert signed_in_as(client) is None


@pytest.mark.parametrize('role', STUDENT_FORM)
def test_login_form_signs_in(client, factory, role):
    user = factory.user(role)
    _assert_signed_in(client, login(client, user, '/login'), user)


@pytest.mark.parametrize('role', STUDENT_FORM)
def test_login_form_refuses_a_wrong_password(client, factory, role):
    user = factory.user(role)
    _assert_refused(client, login(client, user, '/login', password='Wrong-Pass-1'))


@pytest.mark.parametrize('role', ADMIN_FORM)
def test_admin_form_signs_in(client, factory, role):
    user = factory.user(role)
    _assert_signed_in(client, login(client, user, '/admin/login'), user)


@pytest.mark.parametrize('role', ADMIN_FORM)
def test_admin_form_refuses_a_wrong_password(client, factory, role):
    user = factory.user(role)
    _assert_refused(client, login(client, user, '/admin/login', password='Wrong-Pass-1'))


@pytest.mark.parametrize('role', ('Admin', 'Super Admin'))
def test_admin_roles_are_refused_on_the_login_form(client, factory, role):
    _assert_refused(client, login(client, factory.user(role), '/login'))


@pytest.mark.parametrize('role', ('Student', 'Teacher'))
def test_student_and_teacher_are_refused_on_the_admin_form(client, factory, role):
    _assert_refused(client, login(client, factory.user(role), '/admin/login'))


def test_session_reports_permissions_for_the_account(client, factory):
    user = factory.user('HOD')
    assert signed_in_as(client) is None
    login(client, user, '/admin/login')
    account = signed_in_as(client)
    assert account['unrestricted'] is False
    assert set(account['permissions']) == factory.role_permissions('HOD')


def test_session_reports_super_admin_as_unrestricted(client, factory):
    login(client, factory.user('Super Admin'))
    assert signed_in_as(client)['unrestricted'] is True


def test_signing_out_clears_the_session(client, factory):
    login(client, factory.user('Teacher'))
    assert signed_in_as(client) is not None
    client.get('/logout')
    assert signed_in_as(client) is None


@pytest.mark.parametrize('role, path', [('Student', '/login'), ('Teacher', '/login'), ('HOD', '/admin/login'), ('Admin', '/admin/login')])
def test_a_locked_account_is_refused_with_the_right_password(client, factory, role, path):
    user = factory.user(role, status='locked')
    _assert_refused(client, login(client, user, path))


def test_an_inactive_account_is_refused(client, factory):
    _assert_refused(client, login(client, factory.user('Student', status='inactive')))


@pytest.mark.parametrize('role', ('Student', 'Teacher'))
def test_an_unlinked_account_is_refused(client, factory, role):
    factory.academic()
    factory.user('Student')
    _assert_refused(client, login(client, factory.user(role, link=False)))
    [attempt] = factory.query('SELECT failure_reason FROM login_attempts ORDER BY id DESC LIMIT 1')
    assert 'not linked' in attempt['failure_reason']


def test_the_database_refuses_a_second_faculty_row_for_one_user(factory):
    import mysql.connector

    teacher = factory.user('Teacher')
    with pytest.raises(mysql.connector.IntegrityError, match='idx_faculty_user_id'):
        factory.insert('faculty', id=teacher['id'] + 100000, user_id=teacher['id'], name='Second',
                       email='second-faculty@example.org', department_id=teacher['department_id'], employee_id='EMP-2ND')


def test_the_database_refuses_a_second_student_row_for_one_user(factory):
    import mysql.connector

    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    with pytest.raises(mysql.connector.IntegrityError, match='idx_students_user_id'):
        factory.insert('students', id=student['id'] + 100000, user_id=student['id'], name='Second',
                       email='second-student@example.org', course_id=setup['course_id'], class_id=setup['class_id'],
                       division_id=setup['division_id'], admission_id='ADM-2ND', roll_number='2ND')


@pytest.mark.parametrize('role, lookup', [('Student', 'fetch_student_links'), ('Teacher', 'fetch_faculty_links')])
def test_two_linked_rows_are_refused(client, factory, monkeypatch, role, lookup):
    import services.login

    user = factory.user(role)
    real = getattr(services.login, lookup)

    def doubled(cursor, user_id):
        rows = real(cursor, user_id)
        return rows + [dict(rows[0], id=rows[0]['id'] + 100000)]

    monkeypatch.setattr(services.login, lookup, doubled)
    _assert_refused(client, login(client, user))
