"""Logout. No live database."""

from services import login as login_service


class _Cursor:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError('session locked')
        self.calls.append((' '.join(sql.split()), params))

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self):
        self.commits = 0
        self.closed = False

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def _bind(monkeypatch, cursor):
    connection = _Connection()
    activities = []
    monkeypatch.setattr(login_service, 'get_db', lambda: (connection, cursor))
    monkeypatch.setattr(
        login_service,
        'log_activity',
        lambda *args: activities.append(args),
    )
    return connection, activities


def test_anonymous_logout_only_clears_the_session(monkeypatch):
    cursor = _Cursor()
    connection, activities = _bind(monkeypatch, cursor)
    session = {}
    login_service.sign_out(session)
    assert session == {}
    assert activities == []
    assert cursor.calls == []
    assert connection.commits == 0
    assert cursor.closed is False


def test_logout_without_a_session_id_still_logs_the_user(monkeypatch):
    cursor = _Cursor()
    connection, activities = _bind(monkeypatch, cursor)
    session = {'user_id': 7}
    login_service.sign_out(session)
    assert activities == [(7, 'logout', 'User unknown logged out')]
    assert cursor.calls == []
    assert connection.commits == 0
    assert session == {}


def test_logout_deactivates_the_session_before_clearing_it(monkeypatch):
    cursor = _Cursor()
    connection, activities = _bind(monkeypatch, cursor)
    seen = {}

    def _log(user_id, activity_type, description):
        seen['during_log'] = {'user_id': user_id, 'session_id': session.get('session_id')}
        activities.append((user_id, activity_type, description))

    monkeypatch.setattr(login_service, 'log_activity', _log)
    session = {'user_id': 7, 'username': 'ada', 'session_id': 'sid-1', 'role': 'Student'}
    login_service.sign_out(session)
    assert seen['during_log'] == {'user_id': 7, 'session_id': 'sid-1'}
    assert activities == [(7, 'logout', 'User ada logged out')]
    assert cursor.calls == [(
        'UPDATE user_sessions SET is_active = 0 WHERE session_id = %s',
        ('sid-1',),
    )]
    assert connection.commits == 1
    assert connection.closed is False
    assert cursor.closed is True
    assert session == {}


def test_failed_deactivation_leaves_the_session_in_place(monkeypatch):
    cursor = _Cursor(fail=True)
    connection, activities = _bind(monkeypatch, cursor)
    session = {'user_id': 7, 'username': 'ada', 'session_id': 'sid-1'}
    try:
        login_service.sign_out(session)
    except RuntimeError as exc:
        assert str(exc) == 'session locked'
    else:
        raise AssertionError('the logout error was swallowed')
    assert activities == [(7, 'logout', 'User ada logged out')]
    assert connection.commits == 0
    assert cursor.closed is False
    assert session['session_id'] == 'sid-1'
