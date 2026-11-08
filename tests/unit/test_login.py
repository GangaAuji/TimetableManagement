"""Student and teacher sign-in. No live database."""

from datetime import datetime, timedelta

from services import login as login_service


class _Cursor:
    def __init__(self, rows, raise_on=None):
        self.rows = list(rows)
        self.raise_on = raise_on
        self.calls = []

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        if self.raise_on and self.raise_on in text:
            raise RuntimeError('mapping failed')
        self.calls.append((text, params))

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


class _Connection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class _Logger:
    def __init__(self):
        self.warnings = []

    def warning(self, message, *args):
        self.warnings.append((message, args))


class _App:
    def __init__(self):
        self.logger = _Logger()


def _bind(monkeypatch, rows, raise_on=None, password_ok=True):
    connection = _Connection()
    cursor = _Cursor(rows, raise_on)
    flashes = []
    attempts = []
    activities = []
    failures = []
    resets = []
    monkeypatch.setattr(login_service, 'get_db', lambda: (connection, cursor))
    monkeypatch.setattr(login_service, 'flash', lambda message, category: flashes.append((message, category)))
    monkeypatch.setattr(login_service, 'log_login_attempt', lambda *args, **kwargs: attempts.append(args))
    monkeypatch.setattr(login_service, 'log_activity', lambda *args, **kwargs: activities.append(args))
    monkeypatch.setattr(login_service, 'record_failed_sign_in', lambda user_id: failures.append(user_id))
    monkeypatch.setattr(login_service, 'clear_after_sign_in', lambda cursor, user: resets.append(user['id']))
    monkeypatch.setattr(login_service, 'count_unknown_username', lambda address: None)
    monkeypatch.setattr(login_service, '_spend_one_hash', lambda password: None)
    monkeypatch.setattr(login_service, 'password_matches', lambda stored, raw: password_ok and stored == 'hash' and raw == 'secret')
    monkeypatch.setattr(login_service, 'upgraded_hash', lambda stored, raw: None)
    monkeypatch.setattr(login_service.uuid, 'uuid4', lambda: 'sid-1')

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 26, 12, 0, 0)

    monkeypatch.setattr(login_service, 'datetime', _Clock)
    app = _App()
    monkeypatch.setattr(login_service, 'current_app', app)
    return connection, cursor, flashes, attempts, activities, app, failures, resets


def _user(role='Student', status='active'):
    return {'id': 7, 'password': 'hash', 'role': role, 'status': status}


def test_unknown_inactive_and_locked_accounts_do_not_commit(monkeypatch):
    connection, cursor, flashes, attempts, activities, _app, failures, _resets = _bind(monkeypatch, [None])
    session = {}
    assert login_service.sign_in('ada', 'secret', '10.0.0.8', 'browser', session) == 'render'
    assert flashes == [('Sign in failed.', 'danger')]
    assert cursor.calls[0][0].endswith("role NOT IN ('Admin', 'Super Admin')")
    assert cursor.calls[0][1] == ('ada',)
    assert connection.commits == 0
    assert attempts == [('ada', 'failed', 'Unknown account')]
    assert failures == []
    assert session == {}

    connection, _cursor, flashes, attempts, _activities, _app, failures, _resets = _bind(monkeypatch, [_user(status='inactive')])
    assert login_service.sign_in('ada', 'secret', '10.0.0.8', 'browser', {}) == 'render'
    assert flashes == [("Your account has been deactivated. Please contact the administrator for assistance.", 'warning')]
    assert connection.commits == 0
    assert attempts == [('ada', 'failed', 'Account inactive')]
    assert failures == []

    connection, _cursor, flashes, attempts, _activities, _app, failures, _resets = _bind(monkeypatch, [_user(status='locked')])
    assert login_service.sign_in('ada', 'secret', '10.0.0.8', 'browser', {}) == 'render'
    assert flashes == [("Your account has been locked due to security reasons. Please contact the administrator.", 'danger')]
    assert connection.commits == 0
    assert attempts == [('ada', 'failed', 'Account locked')]
    assert failures == []


def test_wrong_password_is_logged_and_not_committed(monkeypatch):
    connection, cursor, flashes, attempts, activities, _app, failures, resets = _bind(monkeypatch, [_user()], password_ok=False)
    assert login_service.sign_in('ada', 'nope', '10.0.0.8', 'browser', {}) == 'render'
    assert attempts == [('ada', 'failed', 'Invalid password')]
    assert flashes == [('Sign in failed.', 'danger')]
    assert failures == [7]
    assert resets == []
    assert connection.commits == 0
    assert activities == []
    assert len(cursor.calls) == 1


def test_student_sign_in_keeps_session_and_query_order(monkeypatch):
    profile = {'department_id': 3, 'is_hod': 0, 'profile_photo': ''}
    student = {'id': 15, 'name': 'Ada', 'email': 'ada@school', 'course_id': 2, 'class_id': 4, 'division_id': 6}
    connection, cursor, flashes, attempts, activities, _app, _failures, resets = _bind(
        monkeypatch, [_user(), student, profile],
    )
    session = {}
    assert login_service.sign_in('ada', 'secret', '10.0.0.8', 'browser', session) == 'redirect'
    assert [call[0].split(' ', 1)[0] for call in cursor.calls] == ['SELECT', 'SELECT', 'INSERT', 'UPDATE', 'SELECT']
    assert 'LIMIT 1' not in ' '.join(call[0] for call in cursor.calls)
    assert 'WHERE user_id = %s' in cursor.calls[1][0]
    assert cursor.calls[2][1] == ('sid-1', 7, '10.0.0.8', 'browser', datetime(2026, 10, 26, 12, 0, 0) + timedelta(days=7))
    assert cursor.calls[3][1] == (7,)
    assert connection.commits == 1
    assert attempts == [('ada', 'success')]
    assert activities == [(7, 'login', 'User ada logged in as Student')]
    assert resets == [7]
    assert session['student_id'] == 15
    assert session.get('faculty_id') is None
    assert session['name'] == 'Ada'
    assert session['profile_photo'] == 'default-avatar.svg'
    assert session['department_id'] == 3
    assert flashes == []


def test_teacher_sign_in_uses_only_the_linked_row(monkeypatch):
    profile = {'department_id': 3, 'is_hod': 1, 'profile_photo': 'ada.png'}
    faculty = {'id': 21, 'name': 'Grace', 'email': 'grace@school', 'department_id': 9}
    _connection, cursor, flashes, _attempts, _activities, _app, _failures, resets = _bind(
        monkeypatch, [_user(role='Teacher'), faculty, profile],
    )
    session = {}
    assert login_service.sign_in('grace', 'secret', '10.0.0.8', 'browser', session) == 'redirect'
    assert cursor.calls[1][1] == (7,)
    assert 'LIMIT 1' not in cursor.calls[1][0]
    assert session['faculty_id'] == 21
    assert session['name'] == 'Grace'
    assert session['department_id'] == 9
    assert resets == [7]
    assert flashes == []


def test_teacher_without_a_link_is_denied(monkeypatch):
    connection, cursor, flashes, _attempts, _activities, _app, _failures, resets = _bind(
        monkeypatch, [_user(role='Teacher'), None],
    )
    session = {}
    assert login_service.sign_in('grace', 'secret', '10.0.0.8', 'browser', session) == 'render'
    assert 'LIMIT 1' not in ' '.join(call[0] for call in cursor.calls)
    assert session == {}
    assert flashes == [('This account is not linked to a faculty record.', 'danger')]
    assert connection.commits == 0
    assert resets == []


def test_several_student_rows_do_not_pick_one(monkeypatch):
    first = {'id': 15, 'name': 'Ada', 'email': 'ada@school', 'course_id': 2, 'class_id': 4, 'division_id': 6}
    second = {'id': 16, 'name': 'Bea', 'email': 'bea@school', 'course_id': 2, 'class_id': 4, 'division_id': 6}
    connection, _cursor, flashes, _attempts, _activities, _app, _failures, _resets = _bind(
        monkeypatch, [_user(), [first, second]],
    )
    session = {}
    assert login_service.sign_in('ada', 'secret', '10.0.0.8', 'browser', session) == 'render'
    assert session == {}
    assert connection.commits == 0
    assert flashes == [('This account is not linked to a student record.', 'danger')]
