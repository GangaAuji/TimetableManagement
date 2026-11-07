"""User creation. No live database."""

from services import users as user_service


class _Cursor:
    def __init__(self, row=None, fail_on=None):
        self.row = row
        self.fail_on = fail_on
        self.calls = []
        self.lastrowid = 15
        self.closed = False

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        if self.fail_on and self.fail_on in text:
            raise RuntimeError('user locked')
        self.calls.append((text, params))

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, row=None, fail_on=None):
        self.cursor_obj = _Cursor(row, fail_on)
        self.dictionary = None
        self.actions = []

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        return self.cursor_obj

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')

    def close(self):
        self.actions.append('close')


class _Logger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


class _App:
    def __init__(self):
        self.logger = _Logger()


def _bind(monkeypatch, connection, activities=None):
    flashes = []
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(user_service, 'flash', lambda message, category: flashes.append((message, category)))
    monkeypatch.setattr(user_service, 'current_app', _App())
    monkeypatch.setattr(
        user_service,
        'generate_password_hash',
        lambda password: f'hashed:{password}',
    )
    monkeypatch.setattr(
        user_service,
        'log_activity',
        lambda *args: activities.append(args) if activities is not None else None,
    )
    return flashes


def test_taken_username_does_not_insert_or_roll_back(monkeypatch):
    connection = _Connection(row={'id': 3})
    flashes = _bind(monkeypatch, connection)
    user_service.create_user('ada', 'secret', 'Teacher', 'active', 'ada@school', {'user_id': 1})
    assert connection.cursor_obj.calls == [('SELECT id FROM users WHERE username = %s', ['ada'])]
    assert flashes == [('Username already exists.', 'danger')]
    assert connection.actions == ['close']
    assert connection.cursor_obj.closed is True
    assert connection.dictionary is True


def test_create_user_hashes_the_password_and_logs_before_commit(monkeypatch):
    connection = _Connection()
    activities = []
    flashes = _bind(monkeypatch, connection, activities)
    user_service.create_user('ada', 'secret', 'Teacher', 'active', 'ada@school', {'user_id': 9})
    assert connection.cursor_obj.calls[1] == (
        'INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)',
        ['ada', 'hashed:secret', 'Teacher', 'active'],
    )
    assert activities == [(9, 'create_user', 'Created new user: ada with role Teacher')]
    assert connection.actions == ['commit', 'close']
    assert flashes == [('User created successfully.', 'success')]


def test_blank_password_is_stored_empty(monkeypatch):
    connection = _Connection()
    _bind(monkeypatch, connection, [])
    user_service.create_user('ada', '', 'Student', 'active', 'ada@school', {'user_id': 9})
    assert connection.cursor_obj.calls[1][1][1] == ''


def test_failed_insert_rolls_back_and_still_closes(monkeypatch):
    connection = _Connection(fail_on='INSERT INTO users')
    flashes = _bind(monkeypatch, connection, [])
    user_service.create_user('ada', 'secret', 'Teacher', 'active', None, {'user_id': 9})
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True
    assert flashes == [('Error creating user. Please try again.', 'danger')]
    assert user_service.current_app.logger.errors == ['Error creating user: user locked']
