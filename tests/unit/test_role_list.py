"""Role list query order. No live database."""

from services import roles as role_service


class _Cursor:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.calls = []
        self.closed = False
        self._reads = 0

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        if self.fail_on and self.fail_on in text:
            raise RuntimeError('roles locked')
        self.calls.append((text, params))

    def fetchall(self):
        self._reads += 1
        if self._reads == 1:
            return [{'id': 7, 'name': 'view', 'module': 'users'}]
        if self._reads == 2:
            return [
                {'id': 1, 'name': 'Admin'},
                {'id': 2, 'name': 'Teacher'},
            ]
        if self.calls[-1][1] == ['Admin']:
            return [{'id': 3, 'username': 'ada'}]
        return [{'id': 4, 'username': 'bea'}]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, fail_on=None):
        self.cursor_obj = _Cursor(fail_on)
        self.dictionary = None
        self.closed = False

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_role_list_loads_permissions_then_roles_then_users(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(role_service, 'get_db_connection', lambda: connection)
    permissions, roles, role_users = role_service.list_roles()
    assert permissions == [{'id': 7, 'name': 'view', 'module': 'users'}]
    assert [role['name'] for role in roles] == ['Admin', 'Teacher']
    assert role_users == {
        'Admin': [{'id': 3, 'username': 'ada'}],
        'Teacher': [{'id': 4, 'username': 'bea'}],
    }
    assert connection.cursor_obj.calls[0][0] == (
        'SELECT id, name, module FROM permissions ORDER BY module, name'
    )
    assert 'GROUP_CONCAT(DISTINCT p.name) as permissions' in connection.cursor_obj.calls[1][0]
    assert connection.cursor_obj.calls[1][0].endswith('ORDER BY r.name')
    assert connection.cursor_obj.calls[2][1] == ['Admin']
    assert connection.cursor_obj.calls[3][1] == ['Teacher']
    assert connection.dictionary is True
    assert connection.cursor_obj.closed is True
    assert connection.closed is False


def test_failed_role_query_leaves_the_cursor_open(monkeypatch):
    connection = _Connection(fail_on='FROM roles')
    monkeypatch.setattr(role_service, 'get_db_connection', lambda: connection)
    try:
        role_service.list_roles()
    except RuntimeError as exc:
        assert str(exc) == 'roles locked'
    else:
        raise AssertionError('the role query error was swallowed')
    assert len(connection.cursor_obj.calls) == 1
    assert connection.cursor_obj.closed is False
    assert connection.closed is False
