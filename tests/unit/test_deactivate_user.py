"""User deactivation. No live database."""

from services import users as user_service


class _Cursor:
    def __init__(self, row, fail_on=None):
        self.row = row
        self.fail_on = fail_on
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        if self.fail_on and self.fail_on in text:
            raise RuntimeError('delete locked')
        self.calls.append((text, params))

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, row=None, fail_on=None):
        self.cursor_obj = _Cursor(row, fail_on)
        self.actions = []

    def cursor(self, dictionary=False):
        return self.cursor_obj

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')

    def close(self):
        self.actions.append('close')


def _bind(monkeypatch, connection, activities):
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(user_service, 'log_activity', lambda *args: activities.append(args))

    class _Logger:
        def error(self, message):
            activities.append(('log', message))

    class _App:
        logger = _Logger()

    monkeypatch.setattr(user_service, 'current_app', _App())


def test_missing_and_super_admin_are_not_deactivated(monkeypatch):
    activities = []
    connection = _Connection(None)
    _bind(monkeypatch, connection, activities)
    assert user_service.deactivate_user(4, {'user_id': 1}) == 'missing'
    assert connection.actions == ['close']
    assert activities == []

    connection = _Connection({'username': 'root', 'role': 'Super Admin'})
    _bind(monkeypatch, connection, activities)
    assert user_service.deactivate_user(4, {'user_id': 1}) == 'protected'
    assert len(connection.cursor_obj.calls) == 1
    assert connection.actions == ['close']


def test_teacher_deactivation_marks_the_faculty_row(monkeypatch):
    activities = []
    connection = _Connection({'username': 'ada', 'role': 'Teacher'})
    _bind(monkeypatch, connection, activities)
    assert user_service.deactivate_user(4, {'user_id': 9}) == 'ok'
    assert [call[0] for call in connection.cursor_obj.calls] == [
        'SELECT username, role FROM users WHERE id = %s',
        "UPDATE users SET status = 'inactive' WHERE id = %s",
        'UPDATE faculty SET is_active = 0 WHERE user_id = %s',
    ]
    assert activities == [(9, 'delete_user', 'Soft-deleted user ada (ID: 4)')]
    assert connection.actions == ['commit', 'close']


def test_failed_deactivation_rolls_back(monkeypatch):
    activities = []
    connection = _Connection({'username': 'ada', 'role': 'Student'}, fail_on='UPDATE users')
    _bind(monkeypatch, connection, activities)
    assert user_service.deactivate_user(4, {'user_id': 9}) == 'error'
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True
    assert activities[-1][1] == 'Error deleting user: delete locked'
