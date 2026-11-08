"""Admin sign-in. No live database."""

from datetime import datetime, timedelta

from services import login as login_service


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


class _Connection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class _Logger:
    def __init__(self):
        self.debugs = []
        self.errors = []

    def debug(self, message):
        self.debugs.append(message)

    def error(self, message):
        self.errors.append(message)

    def exception(self, message):
        self.errors.append(message)


class _App:
    def __init__(self):
        self.logger = _Logger()


def _bind(monkeypatch, rows, password_ok=True, password_error=None):
    connection = _Connection()
    cursor = _Cursor(rows)
    flashes = []
    attempts = []
    activities = []
    failures = []
    resets = []
    app = _App()
    monkeypatch.setattr(login_service, 'get_db', lambda: (connection, cursor))
    monkeypatch.setattr(login_service, 'flash', lambda message, category: flashes.append((message, category)))
    monkeypatch.setattr(login_service, 'log_login_attempt', lambda *args, **kwargs: attempts.append(args))
    monkeypatch.setattr(login_service, 'log_activity', lambda *args, **kwargs: activities.append(args))
    monkeypatch.setattr(login_service, 'record_failed_sign_in', lambda user_id: failures.append(user_id))
    monkeypatch.setattr(login_service, 'clear_after_sign_in', lambda cursor, user: resets.append(user['id']))
    monkeypatch.setattr(login_service, 'count_unknown_username', lambda address: None)
    monkeypatch.setattr(login_service, '_spend_one_hash', lambda password: None)
    monkeypatch.setattr(login_service, 'current_app', app)
    monkeypatch.setattr(login_service.uuid, 'uuid4', lambda: 'sid-9')

    def _check(stored, raw):
        if password_error:
            raise RuntimeError(password_error)
        return password_ok and stored == 'hash' and raw == 'secret'

    monkeypatch.setattr(login_service, 'password_matches', _check)
    monkeypatch.setattr(login_service, 'upgraded_hash', lambda stored, raw: None)

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 26, 12, 0, 0)

    monkeypatch.setattr(login_service, 'datetime', _Clock)
    return connection, cursor, flashes, attempts, activities, app, failures, resets


def _user(role='Admin', status='active'):
    return {'id': 4, 'password': 'hash', 'role': role, 'status': status}


def test_unknown_and_blocked_admin_accounts_do_not_commit(monkeypatch):
    connection, cursor, flashes, attempts, _activities, _app, failures, _resets = _bind(monkeypatch, [None])
    assert login_service.sign_in_admin('ada', 'secret', '10.0.0.8', 'browser', {}) == 'render'
    assert cursor.calls[0][0].endswith("role IN ('Admin', 'Super Admin', 'HOD')")
    assert flashes == [('Sign in failed.', 'danger')]
    assert connection.commits == 0
    assert attempts == [('ada', 'failed', 'Unknown account')]
    assert failures == []

    connection, _cursor, flashes, attempts, _activities, _app, failures, _resets = _bind(monkeypatch, [_user(status='inactive')])
    assert login_service.sign_in_admin('ada', 'secret', '10.0.0.8', 'browser', {}) == 'render'
    assert flashes == [('Your admin account has been deactivated. Please contact the system administrator.', 'warning')]
    assert connection.commits == 0
    assert attempts == [('ada', 'failed', 'Account inactive')]
    assert failures == []

    connection, _cursor, flashes, attempts, _activities, _app, failures, _resets = _bind(monkeypatch, [_user(status='locked')])
    session = {}
    assert login_service.sign_in_admin('ada', 'secret', '10.0.0.8', 'browser', session) == 'render'
    assert flashes == [('Your admin account has been locked due to security reasons. Please contact the system administrator.', 'danger')]
    assert connection.commits == 0
    assert session == {}
    assert failures == []


def test_password_check_error_stays_on_the_login_response(monkeypatch):
    connection, cursor, flashes, attempts, activities, app, _failures, _resets = _bind(
        monkeypatch, [_user()], password_error='bad hash',
    )
    assert login_service.sign_in_admin('ada', 'secret', '10.0.0.8', 'browser', {}) == 'render'
    assert app.logger.errors == ['Sign-in could not check the password']
    assert 'bad hash' not in app.logger.errors[0]
    assert flashes == [('Sign in failed.', 'danger')]
    assert connection.commits == 0
    assert attempts == []
    assert activities == []
    assert len(cursor.calls) == 1


def test_wrong_admin_password_uses_its_own_failure_reason(monkeypatch):
    connection, _cursor, flashes, attempts, activities, _app, failures, resets = _bind(monkeypatch, [_user()], password_ok=False)
    assert login_service.sign_in_admin('ada', 'nope', '10.0.0.8', 'browser', {}) == 'render'
    assert attempts == [('ada', 'failed', 'Invalid admin password')]
    assert flashes == [('Sign in failed.', 'danger')]
    assert failures == [4]
    assert resets == []
    assert connection.commits == 0
    assert activities == []


def test_admin_sign_in_stores_the_username_as_the_display_name(monkeypatch):
    profile = {'department_id': 2, 'is_hod': 1, 'profile_photo': None}
    connection, cursor, flashes, attempts, activities, _app, _failures, resets = _bind(
        monkeypatch, [_user(role='HOD'), profile],
    )
    session = {}
    assert login_service.sign_in_admin('ada', 'secret', '10.0.0.8', 'browser', session) == 'redirect'
    assert [call[0].split(' ', 1)[0] for call in cursor.calls] == ['SELECT', 'INSERT', 'UPDATE', 'SELECT']
    assert 'students' not in cursor.calls[-1][0]
    assert 'faculty' not in cursor.calls[-1][0]
    assert cursor.calls[1][1] == ('sid-9', 4, '10.0.0.8', 'browser', datetime(2026, 10, 26, 12, 0, 0) + timedelta(days=7))
    assert connection.commits == 1
    assert attempts == [('ada', 'success')]
    assert activities == [(4, 'admin_login', 'Admin ada logged in with role HOD')]
    assert session['name'] == 'ada'
    assert session['role'] == 'HOD'
    assert session['profile_photo'] == 'default-avatar.svg'
    assert session['is_hod'] == 1
    assert session.get('faculty_id') is None
    assert resets == [4]
    assert flashes == []
