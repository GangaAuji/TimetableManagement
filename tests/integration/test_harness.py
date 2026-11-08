"""The test harness itself: the app uses the test database, factories build each role, and isolation restores."""

import pytest

from tests.factories import ROLES
from tests.http_helpers import csrf_token


def test_the_app_uses_the_test_database(app, test_database):
    assert app.config['TESTING'] is True
    assert app.config['MYSQL_DB'] == test_database.name
    assert app.config['BACKGROUND_WORKERS'] is False
    with app.app_context():
        from extensions import get_db_connection

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT DATABASE()')
        assert cursor.fetchone()[0] == test_database.name
        connection.close()


def test_mobile_schema_lookups_use_the_connections_database(app):
    from api.mobile.v1.sync_attendance import _column_exists, _table_exists

    with app.app_context():
        from extensions import get_db_connection

        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            assert _table_exists(cursor, 'attendance_logs') is True
            assert _table_exists(cursor, 'no_such_table') is False
            assert _column_exists(cursor, 'attendance_logs', 'event_uuid') is True
        finally:
            cursor.close()
            connection.close()


def test_a_testing_app_refuses_a_non_test_database():
    from app import create_app
    from config.testing import TestingConfig

    class Wrong(TestingConfig):
        MYSQL_DB = 'college_timetable_db'

    with pytest.raises(RuntimeError, match='Refusing'):
        create_app(Wrong)


def test_factories_build_every_role_with_linked_rows(factory):
    setup = factory.academic()
    users = factory.users(setup)
    assert set(users) == set(ROLES)
    assert users['Teacher']['faculty_id'] == users['Teacher']['id']
    assert users['Student']['student_id'] == users['Student']['id']
    [student] = factory.query('SELECT class_id, division_id FROM students WHERE id = %s', (users['Student']['id'],))
    assert (student['class_id'], student['division_id']) == (setup['class_id'], setup['division_id'])
    [lecture] = factory.query('SELECT faculty_id FROM timetable WHERE id = %s', (setup['timetable_id'],))
    assert lecture['faculty_id'] == setup['teacher']['faculty_id']


def test_isolation_restores_changed_tables(test_database, factory):
    factory.users()
    factory.execute("UPDATE branding_settings SET setting_value = 'changed' WHERE setting_key = 'site_title'")
    restored = test_database.baseline.restore(test_database.connection)
    assert {'users', 'branding_settings', 'faculty', 'students'} <= set(restored)
    assert test_database.baseline.changed(test_database.connection) == []
    assert factory.query('SELECT COUNT(*) AS n FROM users')[0]['n'] == 0


def test_csrf_token_comes_from_the_api_with_the_same_cookie_jar(client):
    first = csrf_token(client)
    assert first and csrf_token(client)
    response = client.post('/api/session/logout', headers={'Origin': 'http://localhost'})
    assert response.status_code == 403
    response = client.post('/api/session/logout', headers={'Origin': 'http://localhost', 'X-CSRFToken': first})
    assert response.status_code == 401, 'the token is accepted; the route then requires a session'
