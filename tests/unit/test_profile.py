"""Profile reads and saves. No live database."""

from services import profile as profile_service


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        self.calls.append((' '.join(sql.split()), params))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, rows):
        self.cursor_obj = _Cursor(rows)
        self.actions = []

    def cursor(self, dictionary=False):
        return self.cursor_obj

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')

    def close(self):
        self.actions.append('close')


def _bind(monkeypatch, rows):
    connection = _Connection(rows)
    activities = []
    monkeypatch.setattr(profile_service, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(profile_service, 'log_activity', lambda *args: activities.append(args))
    monkeypatch.setattr(profile_service, 'check_password_hash', lambda stored, raw: stored == 'hash' and raw == 'old-secret')
    monkeypatch.setattr(profile_service, 'generate_password_hash', lambda raw: f'hashed:{raw}')
    return connection, activities


def test_teacher_profile_uses_the_faculty_email_when_the_account_email_is_empty(monkeypatch):
    user = {
        'id': 4, 'username': 'ada', 'role': 'Teacher', 'email': None,
        'profile_photo': '', 'phone': None, 'address': None, 'bio': None,
        'date_of_birth': None, 'status': None, 'last_login': None,
        'created_at': None, 'department_id': 2, 'is_hod': 0,
    }
    connection, _activities = _bind(monkeypatch, [user, {'name': 'Civil'}, {'email': 'ada@school'}])
    loaded = profile_service.load_profile({'user_id': 4, 'role': 'Teacher'})
    assert loaded['email'] == 'ada@school'
    assert loaded['profile_photo'] == 'default-avatar.svg'
    assert loaded['department_name'] == 'Civil'
    assert loaded['status'] == 'active'
    assert connection.cursor_obj.closed is True
    assert connection.actions == ['close']


def test_profile_save_without_a_photo_updates_the_faculty_email(monkeypatch):
    connection, activities = _bind(monkeypatch, [])
    session = {'user_id': 4, 'role': 'Teacher'}
    assert profile_service.save_profile(session, 'ada@school', '9', '', '', '', None) == 'ok'
    assert 'profile_photo' not in connection.cursor_obj.calls[0][0]
    assert connection.cursor_obj.calls[1][0].startswith('UPDATE faculty')
    assert connection.cursor_obj.calls[1][1] == ['ada@school', 4]
    assert activities == [(4, 'update_profile', 'Updated user profile')]
    assert connection.actions == ['commit', 'close']


def test_wrong_password_does_not_roll_back(monkeypatch):
    connection, activities = _bind(monkeypatch, [{'password': 'hash'}])
    assert profile_service.change_password({'user_id': 4}, 'nope', 'long-secret') == 'wrong'
    assert len(connection.cursor_obj.calls) == 1
    assert connection.actions == ['close']
    assert activities == []


def test_password_change_stores_the_new_hash(monkeypatch):
    connection, activities = _bind(monkeypatch, [{'password': 'hash'}])
    assert profile_service.change_password({'user_id': 4}, 'old-secret', 'long-secret') == 'ok'
    assert connection.cursor_obj.calls[1][1] == ['hashed:long-secret', 4]
    assert activities == [(4, 'change_password', 'Changed password')]
    assert connection.actions == ['commit', 'close']
