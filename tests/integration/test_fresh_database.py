"""A fresh database: upgrade to head, seed, boot the real app, and use the report, timetable and branding endpoints.

It builds its own scratch *_test database through create_app(config), with
the export and timetable workers on, and drops it at the end.
"""

import logging
import time

import pytest

from config.testing import TestingConfig
from core.schema.status import head_revision
from tests.integration.live_helpers import drop, migrate, recreate, scratch_name, server_connection, stamped

pytestmark = pytest.mark.live_db

_DONE = ('completed', 'failed')
_SAME_ORIGIN = {'Origin': 'http://localhost'}


@pytest.fixture(scope='module')
def database():
    name = scratch_name('fresh')
    connection = server_connection()
    cursor = connection.cursor()
    try:
        recreate(cursor, name)
        migrate(name, 'upgrade', 'head')
        cursor.execute(
            f"INSERT INTO `{name}`.users (username, password, role) VALUES ('fresh_admin', '!', 'Super Admin')"
        )
        yield cursor, name, cursor.lastrowid
    finally:
        drop(cursor, name)
        connection.close()


@pytest.fixture(scope='module')
def fresh_config(database, tmp_path_factory):
    _, name, _ = database

    class FreshConfig(TestingConfig):
        MYSQL_DB = name
        WTF_CSRF_ENABLED = False
        PROPAGATE_EXCEPTIONS = False
        REQUIRE_MIGRATED_DB = True
        BACKGROUND_WORKERS = True
        UPLOAD_FOLDER = str(tmp_path_factory.mktemp('uploads'))

    return FreshConfig


@pytest.fixture(scope='module')
def app(fresh_config):
    from app import create_app

    return create_app(fresh_config)


@pytest.fixture
def client(app, database):
    _, _, admin_id = database
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = admin_id
        session['username'] = 'fresh_admin'
        session['role'] = 'Super Admin'
    return client


def _data(response):
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    payload = response.get_json()
    assert payload['success'] is True
    return payload['data']


def _wait(fetch, done, seconds=60):
    deadline = time.monotonic() + seconds
    while True:
        value = fetch()
        if done(value) or time.monotonic() > deadline:
            return value
        time.sleep(0.5)


def test_fresh_database_is_at_head(database):
    cursor, name, _ = database
    assert stamped(cursor, name) == [head_revision()]


def test_seed_run_adds_the_branding_defaults_once(app, database):
    cursor, name, _ = database
    runner = app.test_cli_runner()
    first = runner.invoke(args=['seed', 'run'])
    assert first.exit_code == 0, first.output
    assert 'branding_settings: 22 added, 0 already present.' in first.output
    second = runner.invoke(args=['seed', 'run'])
    assert 'branding_settings: 0 added, 22 already present.' in second.output
    cursor.execute(f'SELECT COUNT(*) FROM `{name}`.branding_settings')
    assert cursor.fetchone()[0] == 22


def test_health_is_ok_at_head(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.get_json()['status'] == 'healthy'


def test_branding_endpoints_read_the_seeded_rows(client, database):
    cursor, name, _ = database
    assert _data(client.get('/api/branding'))['site_title'] == 'Timetable Management System'
    cursor.execute(f"UPDATE `{name}`.branding_settings SET setting_value = 'Fresh College' WHERE setting_key = 'site_title'")
    assert _data(client.get('/api/branding'))['site_title'] == 'Fresh College'
    assert client.get('/admin/branding/').status_code < 400


def test_reports_list_queue_and_download(client):
    listing = _data(client.get('/api/reports'))
    assert listing['can_generate'] is True
    queued = _data(client.post('/api/reports', json={'report_type': 'audit-logs'}, headers=_SAME_ORIGIN))
    report_id = queued['id']

    def status():
        reports = _data(client.get('/api/reports'))['reports']
        return next((item['status'] for item in reports if item['id'] == report_id), None)

    assert _wait(status, lambda value: value in _DONE) == 'completed'
    assert client.get(f'/api/reports/{report_id}/download').status_code == 200


def test_timetable_view_generate_and_job_status(client):
    view = _data(client.get('/api/timetable'))
    assert view['can_generate'] is True
    response = client.post('/api/timetable/generate', json={'scope': 'all'}, headers=_SAME_ORIGIN)
    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'timetable_targets_empty'

    queued = _data(client.post(
        '/api/timetable/generate',
        json={'scope': 'one', 'course_id': 999, 'class_id': 999, 'division_id': 999},
        headers=_SAME_ORIGIN,
    ))
    assert queued['attached'] is False
    job = _wait(lambda: _data(client.get(f'/api/timetable/jobs/{queued["id"]}')), lambda value: value['status'] in _DONE)
    assert job['status'] in _DONE
    assert job['total'] == 1 and job['done'] == 1


def test_health_is_503_on_a_database_behind_head(app, client, database, fresh_config):
    cursor, name, _ = database
    migrate(name, 'downgrade', '0003_security_schema')
    try:
        response = client.get('/health')
        assert response.status_code == 503
        reason = response.get_json()['reason']
        assert '0003_security_schema' in reason and head_revision() in reason and '`flask db upgrade`' in reason

        records = []

        class _Collect(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = _Collect(level=logging.ERROR)
        logging.getLogger('app').addHandler(handler)
        try:
            from app import create_app

            create_app(fresh_config)
        finally:
            logging.getLogger('app').removeHandler(handler)
        assert any('Database schema check failed' in text and '0003_security_schema' in text for text in records)
    finally:
        migrate(name, 'upgrade', 'head')
    assert stamped(cursor, name) == [head_revision()]
    assert client.get('/health').status_code == 200
