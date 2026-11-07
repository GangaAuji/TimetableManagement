"""User list filters. No live database."""

from services import users as user_service


class _Cursor:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.calls = []
        self.closed = False
        self._reads = 0

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        if self.fail_on and self.fail_on in text:
            raise RuntimeError('users locked')
        self.calls.append((text, params))

    def fetchall(self):
        self._reads += 1
        if self._reads == 1:
            return [{'name': 'Teacher'}]
        return [{'id': 1, 'username': 'ada'}]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()
        self.dictionary = None
        self.closed = False

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_user_filters_keep_role_status_and_username_order(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    users, roles = user_service.list_users('', '', '')
    assert roles == [{'name': 'Teacher'}]
    assert users == [{'id': 1, 'username': 'ada'}]
    assert 'WHERE' not in connection.cursor_obj.calls[1][0]
    assert connection.cursor_obj.calls[1][1] == []
    assert connection.cursor_obj.calls[0][0] == 'SELECT name FROM roles ORDER BY name'

    connection = _Connection()
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    user_service.list_users('Teacher', 'active', 'ada')
    sql, params = connection.cursor_obj.calls[1]
    assert 'WHERE u.role = %s AND u.status = %s AND (u.username LIKE %s)' in sql
    assert 'u.username as display_name' in sql
    assert sql.endswith('ORDER BY u.username')
    assert params == ['Teacher', 'active', '%ada%']
    assert connection.dictionary is True
    assert connection.cursor_obj.closed is True
    assert connection.closed is False


def test_failed_user_query_leaves_the_cursor_open(monkeypatch):
    connection = _Connection()
    connection.cursor_obj.fail_on = 'FROM users'
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    try:
        user_service.list_users('Teacher', '', '')
    except RuntimeError as exc:
        assert str(exc) == 'users locked'
    else:
        raise AssertionError('the user query error was swallowed')
    assert connection.cursor_obj.closed is False
    assert connection.closed is False
    assert len(connection.cursor_obj.calls) == 1
