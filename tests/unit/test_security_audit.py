"""Regression checks for the release security audit. No live database."""

import importlib.util
import inspect
import threading
from datetime import date, datetime, time
from pathlib import Path

from flask import Flask, session

from academic_rules.availability import manual_add_availability_block
from academic_rules.weekdays import weekday_name, weekday_number
from api.web import reports as report_api
from api.web import roles as role_api
from api.web import user_access
from routes.user_management.actions import export_activity_log, export_users
from security import passwords
from security.rate_limit import _UPSERT, record_fixed_window, shared_allow
from services import teacher_attendance

_SECURITY_REVISION = Path(__file__).resolve().parents[2] / 'migrations' / 'versions' / '0003_security_schema.py'
_spec = importlib.util.spec_from_file_location('security_schema_revision', _SECURITY_REVISION)
_revision = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_revision)
role_level_statements = _revision.role_level_statements


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((' '.join(sql.split()), params))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)

    def fetchall(self):
        if not self.rows:
            return []
        row = self.rows.pop(0)
        if row is None:
            return []
        if isinstance(row, list):
            return row
        return [row]

    def close(self):
        pass


class _Connection:
    def __init__(self, rows):
        self.cursor_obj = _Cursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, dictionary=False):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def test_plaintext_password_is_upgraded_and_a_hash_is_verified():
    stored = passwords.hash_password('correct-horse')
    assert passwords.is_password_hash(stored)
    assert stored != 'correct-horse'
    assert passwords.password_matches(stored, 'correct-horse') is True
    assert passwords.password_matches(stored, 'wrong') is False
    assert passwords.upgraded_hash(stored, 'correct-horse') is None
    assert passwords.password_matches('correct-horse', 'correct-horse') is True
    upgraded = passwords.upgraded_hash('correct-horse', 'correct-horse')
    assert passwords.is_password_hash(upgraded)
    assert 'correct-horse' not in upgraded
    assert passwords.password_matches('correct-horse', 'nope') is False


def test_view_permission_cannot_export_users():
    app = Flask('app')
    app.secret_key = 'test'
    seen = []

    def _check(user_id, permission_name):
        seen.append(permission_name)
        return permission_name == 'users_view_user', None, False

    import routes.user_management.actions as actions
    original = actions.check_user_permission
    actions.check_user_permission = _check
    try:
        with app.test_request_context('/admin/users/export'):
            session['user_id'] = 3
            session['role'] = 'Admin'
            denied = export_users()
            allowed = None
        assert denied == ('You do not have permission to do that.', 403)
        assert seen == ['users_export_data']
        with app.test_request_context('/admin/users/export'):
            session.clear()
            assert export_users()[1] == 401
    finally:
        actions.check_user_permission = original
    assert allowed is None


def test_export_permission_reaches_the_csv_and_the_api_uses_the_same_name():
    app = Flask('app')
    app.secret_key = 'test'
    import routes.user_management.actions as actions
    original_check = actions.check_user_permission
    original_rows = actions.export_user_rows
    actions.check_user_permission = lambda user_id, permission_name: (permission_name == 'users_export_data', None, False)
    actions.export_user_rows = lambda role, status, search: [
        {'id': 1, 'username': 'ada', 'role': 'Admin', 'status': 'active', 'last_login': ''},
    ]
    try:
        with app.test_request_context('/admin/users/export'):
            session['user_id'] = 3
            session['role'] = 'Admin'
            response = export_users()
        assert response.mimetype == 'text/csv'
        assert b'ada' in response.get_data()
    finally:
        actions.check_user_permission = original_check
        actions.export_user_rows = original_rows

    captured = []

    def _denied(name, code, message):
        captured.append(name)
        return 'denied'

    original = user_access.permission_denied
    user_access.permission_denied = _denied
    try:
        assert user_access._export() == 'denied'
    finally:
        user_access.permission_denied = original
    assert captured == ['users_export_data']


def test_activity_export_does_not_use_the_user_view_permission():
    assert 'users_view_user' not in inspect.getsource(export_activity_log)
    assert 'users_view_activity_log' in inspect.getsource(export_activity_log)


def test_denied_report_download_uses_permission_denied(monkeypatch):
    calls = []

    def _deny(permission, code, message):
        calls.append(permission)
        return {'denied': permission}

    monkeypatch.setattr(report_api, '_may_download', lambda record: False)
    monkeypatch.setattr(report_api, 'permission_denied', _deny)
    record = {'report_type': 'users-export', 'created_by': 9, 'status': 'completed'}
    app = Flask('app')
    app.secret_key = 'test'
    with app.test_request_context('/api/reports/4/download'):
        session['user_id'] = 3
        assert report_api._download_denied(record) == {'denied': 'reports_export'}
    assert calls == ['reports_export']
    monkeypatch.setattr(report_api, '_may_download', lambda record: True)
    with app.test_request_context('/api/reports/4/download'):
        session['user_id'] = 9
        assert report_api._download_denied(record) is None


def test_attendance_rejects_another_class_a_bad_date_and_keeps_one_upsert(monkeypatch):
    today = date(2026, 11, 9)
    lecture = {
        'course_id': 2, 'class_id': 4, 'division_id': 6, 'day_of_week': 'Monday',
    }
    enrolled = [{'id': 15}, {'id': 16}]
    connection = _Connection([
        {'id': 8},
        lecture,
        enrolled,
    ])

    class _Today(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(teacher_attendance, 'date', _Today)
    monkeypatch.setattr(teacher_attendance, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(teacher_attendance, 'flash', lambda *args: None)
    saved = teacher_attendance.save_teacher_attendance(7, 30, {
        'attendance_date': '2026-11-09',
        'status_15': 'Present',
        'remarks_15': '',
    })
    assert saved == 1
    upsert = connection.cursor_obj.calls[-1][0]
    assert 'ON DUPLICATE KEY UPDATE' in upsert
    assert connection.cursor_obj.calls[-1][1][0] == 15
    assert connection.commits == 1

    outsider = _Connection([{'id': 8}, lecture, enrolled])
    monkeypatch.setattr(teacher_attendance, 'get_db_connection', lambda: outsider)
    assert teacher_attendance.save_teacher_attendance(7, 30, {
        'attendance_date': '2026-11-09',
        'status_99': 'Present',
    }) == 'student'
    assert outsider.commits == 0
    assert not any('INSERT INTO attendance' in call[0] for call in outsider.cursor_obj.calls)

    missing = _Connection([None])
    monkeypatch.setattr(teacher_attendance, 'get_db_connection', lambda: missing)
    assert teacher_attendance.save_teacher_attendance(7, 30, {
        'attendance_date': '2026-11-09',
        'status_15': 'Present',
    }) == 'missing'

    denied = _Connection([{'id': 8}, None])
    monkeypatch.setattr(teacher_attendance, 'get_db_connection', lambda: denied)
    assert teacher_attendance.save_teacher_attendance(7, 30, {
        'attendance_date': '2026-11-09',
        'status_15': 'Present',
    }) == 'denied'

    wrong_day = _Connection([{'id': 8}, lecture, enrolled])
    monkeypatch.setattr(teacher_attendance, 'get_db_connection', lambda: wrong_day)
    assert teacher_attendance.save_teacher_attendance(7, 30, {
        'attendance_date': '2026-11-08',
        'status_15': 'Present',
    }) == 'date'
    assert wrong_day.commits == 0


def test_get_roles_does_not_execute_ddl():
    app = Flask('app')
    app.secret_key = 'test'
    connection = _Connection([[]])
    original = role_api.get_db_connection
    role_api.get_db_connection = lambda: connection
    try:
        with app.test_request_context('/api/roles'):
            session['user_id'] = 1
            session['role'] = 'Super Admin'
            response, status = role_api._list()
    finally:
        role_api.get_db_connection = original
    assert status == 200
    text = ' '.join(call[0] for call in connection.cursor_obj.calls)
    assert 'ALTER ' not in text
    assert 'CREATE ' not in text
    assert 'DROP ' not in text
    assert 'UPDATE ' not in text
    assert response.get_json()['success'] is True


def test_security_migration_is_idempotent():
    clean = role_level_statements(False)
    existing = role_level_statements(True)
    assert any(item.startswith('ALTER TABLE roles') for item in clean)
    assert not any(item.startswith('ALTER TABLE roles') for item in existing)
    assert any(item.startswith('CREATE TABLE IF NOT EXISTS rate_limit_counters') for item in clean)
    assert any(item.startswith('CREATE TABLE IF NOT EXISTS rate_limit_counters') for item in existing)
    assert sum("name = 'Teacher'" in item for item in existing) == 1
    again = role_level_statements(True)
    assert again == existing


def _lockout_run(monkeypatch, row, max_attempts=5):
    from security import lockout

    calls = []
    actions = []
    logs = []

    class _LockCursor(_Cursor):
        def execute(self, sql, params=None):
            calls.append((' '.join(sql.split()), params))

        def fetchone(self):
            return row

        def close(self):
            pass

    class _Conn:
        def cursor(self, dictionary=False):
            return _LockCursor([])

        def commit(self):
            actions.append('commit')

        def rollback(self):
            actions.append('rollback')

        def close(self):
            actions.append('close')

    app = Flask(__name__)
    app.config['SIGN_IN_MAX_FAILED_ATTEMPTS'] = max_attempts
    monkeypatch.setattr(lockout, 'get_db_connection', lambda: _Conn())
    monkeypatch.setattr(
        lockout, 'log_activity', lambda user_id, kind, *args, cursor=None, **kwargs: logs.append((kind, cursor is not None)),
    )
    with app.app_context():
        locked = lockout.record_failed_sign_in(7)
    return locked, calls, actions, logs


def test_a_wrong_password_inside_the_window_is_counted(monkeypatch):
    row = {'failed_attempts': 2, 'locked_until': None, 'locked_now': 0, 'window_over': 0}
    locked, calls, actions, logs = _lockout_run(monkeypatch, row)
    assert locked is False
    assert 'FOR UPDATE' in calls[0][0]
    assert 'failed_window_start = failed_window_start' in calls[1][0]
    assert 'locked_until = NULL' in calls[1][0]
    assert calls[1][1] == (3, 7)
    assert logs == []
    assert actions == ['commit', 'close']


def test_the_fifth_failure_locks_for_a_while_and_is_audited(monkeypatch):
    row = {'failed_attempts': 4, 'locked_until': None, 'locked_now': 0, 'window_over': 0}
    locked, calls, actions, logs = _lockout_run(monkeypatch, row)
    assert locked is True
    assert 'locked_until = NOW() + INTERVAL %s MINUTE' in calls[1][0]
    assert "status" not in calls[1][0]
    assert calls[1][1] == (5, 15, 7)
    assert logs == [('account_locked', True)]
    assert actions == ['commit', 'close']


def test_an_old_window_or_an_expired_lock_starts_the_count_again(monkeypatch):
    row = {'failed_attempts': 4, 'locked_until': None, 'locked_now': 0, 'window_over': 1}
    locked, calls, _actions, logs = _lockout_run(monkeypatch, row)
    assert locked is False
    assert 'failed_window_start = NOW()' in calls[1][0]
    assert calls[1][1] == (1, 7)
    assert logs == []

    row = {'failed_attempts': 5, 'locked_until': datetime(2026, 1, 1), 'locked_now': 0, 'window_over': 0}
    locked, calls, _actions, logs = _lockout_run(monkeypatch, row)
    assert locked is False
    assert calls[1][1] == (1, 7)
    assert logs == [('account_unlocked', True)]


def test_failures_during_a_lock_are_not_counted(monkeypatch):
    row = {'failed_attempts': 5, 'locked_until': datetime(2026, 1, 1), 'locked_now': 1, 'window_over': 0}
    locked, calls, actions, logs = _lockout_run(monkeypatch, row)
    assert locked is True
    assert len(calls) == 1
    assert logs == []
    assert actions == ['rollback', 'close']


def test_bad_lockout_settings_fall_back_to_the_defaults(monkeypatch):
    row = {'failed_attempts': 4, 'locked_until': None, 'locked_now': 0, 'window_over': 0}
    locked, _calls, _actions, _logs = _lockout_run(monkeypatch, row, max_attempts='nope')
    assert locked is True


def test_workers_share_one_rate_window_and_it_expires():
    store = {}
    assert record_fixed_window(store, 'auth', 2, 10, 0) is True
    assert record_fixed_window(store, 'auth', 2, 10, 1) is True
    assert record_fixed_window(store, 'auth', 2, 10, 2) is False
    assert record_fixed_window(store, 'auth', 2, 10, 12) is True
    shared = {}
    results = []
    lock = threading.Lock()

    def _hit():
        allowed = record_fixed_window(shared, 'api', 10, 60, 100)
        with lock:
            results.append(allowed)

    threads = [threading.Thread(target=_hit) for _ in range(25)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 10
    assert 'X-Forwarded-For' not in inspect.getsource(shared_allow)
    assert 'ON DUPLICATE KEY UPDATE' in _UPSERT

    class _RateCursor:
        def __init__(self):
            self.hits = 0

        def execute(self, sql, params=None):
            if sql.strip().startswith('INSERT'):
                self.hits += 1
            self.row = {'hits': self.hits}

        def fetchone(self):
            return self.row

    cursor = _RateCursor()
    assert shared_allow(cursor, 'auth:1', 1, 600) is True
    assert shared_allow(cursor, 'auth:1', 1, 600) is False


def test_weekday_names_match_availability_numbers():
    expected = {
        'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 'Thursday': 4,
        'Friday': 5, 'Saturday': 6, 'Sunday': 7,
    }
    for name, number in expected.items():
        assert weekday_number(name) == number
        assert weekday_number(number) == number
        assert weekday_name(number) == name
        assert weekday_name(name) == name
    assert weekday_name('Monday') != 1
    sunday = datetime(2026, 11, 8, 23, 30)
    monday = date(2026, 11, 9)
    assert weekday_number(sunday) == 7
    assert weekday_number(monday) == 1
    assert weekday_name(sunday) == 'Sunday'

    class _Avail:
        def __init__(self):
            self.calls = []
            self._rows = [{'cnt': 0}]

        def execute(self, sql, params=None):
            self.calls.append(params)

        def fetchone(self):
            return self._rows.pop(0)

    cursor = _Avail()
    assert manual_add_availability_block(cursor, 4, 'Monday', time(9, 0), time(10, 0)) is None
    assert cursor.calls[0][1] == 1
    assert all(not isinstance(call[1], str) for call in cursor.calls)
