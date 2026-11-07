"""User lookup. No live database."""

from services import users as user_service


class _Cursor:
    def __init__(self, user, fail=False):
        self.user = user
        self.fail = fail
        self.calls = []
        self.closed = False
        self._reads = 0

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError('lookup failed')
        self.calls.append((' '.join(sql.split()), params))

    def fetchone(self):
        return self.user

    def fetchall(self):
        self._reads += 1
        return [{'name': 'Student'}, {'name': 'Teacher'}]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, user=None, fail=False):
        self.cursor_obj = _Cursor(user, fail)
        self.dictionary = None
        self.closed = False

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_found_user_loads_roles_and_keeps_the_response_shape(monkeypatch):
    user = {
        'id': 4,
        'username': 'ada',
        'role': 'Teacher',
        'status': 'active',
        'is_hod': 1,
        'department_id': 2,
        'last_login': 'yesterday',
    }
    connection = _Connection(user)
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    payload, status = user_service.find_user(4)
    assert status == 200
    assert payload == {
        'id': 4,
        'username': 'ada',
        'role': 'Teacher',
        'status': 'active',
        'display_name': 'ada',
        'email': None,
        'is_hod': 1,
        'department_id': 2,
        'available_roles': ['Student', 'Teacher'],
    }
    assert 'last_login' not in payload
    assert connection.cursor_obj.calls[0] == (
        'SELECT id, username, email, role, status, last_login, is_hod, department_id FROM users WHERE id = %s',
        [4],
    )
    assert connection.cursor_obj.calls[1][0] == 'SELECT name FROM roles ORDER BY name'
    assert connection.dictionary is True
    assert connection.cursor_obj.closed is True
    assert connection.closed is True


def test_missing_user_does_not_load_roles(monkeypatch):
    connection = _Connection(None)
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    assert user_service.find_user(4) == ({'error': 'User not found'}, 404)
    assert len(connection.cursor_obj.calls) == 1
    assert connection.cursor_obj.closed is True
    assert connection.closed is True


def test_failed_lookup_still_closes(monkeypatch):
    connection = _Connection(fail=True)
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    try:
        user_service.find_user(4)
    except RuntimeError as exc:
        assert str(exc) == 'lookup failed'
    else:
        raise AssertionError('the lookup error was swallowed')
    assert connection.cursor_obj.closed is True
    assert connection.closed is True
