"""User edits. No live database."""

from datetime import datetime

from services import users as user_service


class _Cursor:
    def __init__(self, rows, fail_on=None):
        self.rows = list(rows)
        self.fail_on = fail_on
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        if self.fail_on and self.fail_on in text:
            raise RuntimeError('edit locked')
        self.calls.append((text, params))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, rows, fail_on=None):
        self.cursor_obj = _Cursor(rows, fail_on)
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


def _bind(monkeypatch, rows, activities=None, fail_on=None, problem=None, last_super_admin=False, unlocks=None):
    connection = _Connection(rows, fail_on)
    monkeypatch.setattr(user_service, 'account_problem', lambda cursor, actor_id, user_id, new_role=None: problem)
    monkeypatch.setattr(
        user_service, 'removes_last_super_admin', lambda cursor, user_id, role, status: last_super_admin,
    )
    monkeypatch.setattr(
        user_service, 'unlock_account',
        lambda cursor, user_id, actor_id: unlocks.append(user_id) if unlocks is not None else None,
    )
    monkeypatch.setattr(user_service, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(user_service, 'current_app', _App())
    monkeypatch.setattr(user_service, 'generate_password_hash', lambda password: f'hashed:{password}')
    monkeypatch.setattr(
        user_service,
        'log_activity',
        lambda *args, **kwargs: activities.append(args) if activities is not None else None,
    )

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 26)

    monkeypatch.setattr(user_service, 'datetime', _Clock)
    return connection


def test_role_labels_map_before_they_are_saved():
    assert user_service.normalize_role('teachers') == 'Teacher'
    assert user_service.normalize_role('Faculties') == 'Teacher'
    assert user_service.normalize_role('students') == 'Student'
    assert user_service.normalize_role('super admins') == 'Super Admin'
    assert user_service.normalize_role('HOD') == 'HOD'


def test_missing_user_and_conflicts_do_not_roll_back(monkeypatch):
    connection = _bind(monkeypatch, [None])
    assert user_service.change_user(4, 'ada', '', 'Teacher', 'active', '', None, False, {'user_id': 1}) == 'missing'
    assert connection.actions == ['close']
    assert len(connection.cursor_obj.calls) == 1

    connection = _bind(monkeypatch, [{'id': 4, 'role': 'Student'}, {'id': 9}])
    assert user_service.change_user(4, 'ada', '', 'Teacher', 'active', 'ada@school', None, False, {'user_id': 1}) == 'username'
    assert connection.actions == ['close']
    assert 'email' not in connection.cursor_obj.calls[-1][0]

    connection = _bind(monkeypatch, [{'id': 4, 'role': 'Student'}, None, {'id': 8}])
    assert user_service.change_user(4, 'ada', '', 'Admin', 'active', 'ada@school', '', False, {'user_id': 1}) == 'email'
    assert connection.cursor_obj.calls[2][1] == ['ada@school', 4]
    assert connection.actions == ['close']


def test_blank_email_skips_the_email_check(monkeypatch):
    connection = _bind(monkeypatch, [{'id': 4, 'role': 'Admin'}, None], [])
    assert user_service.change_user(4, 'ada', '', 'Admin', 'active', '', '', False, {'user_id': 1}) == 'ok'
    assert all('email = %s' not in call[0] for call in connection.cursor_obj.calls)
    assert 'password=%s' not in connection.cursor_obj.calls[2][0]
    assert connection.cursor_obj.calls[2][1][1] is None
    assert connection.cursor_obj.calls[3][0] == 'UPDATE students SET is_active = 0 WHERE user_id = %s'
    assert connection.cursor_obj.calls[4][0] == 'UPDATE faculty SET is_active = 0 WHERE user_id = %s'


def test_teacher_edit_updates_the_faculty_row_and_then_its_active_flag(monkeypatch):
    faculty = {'id': 21, 'user_id': 4, 'name': 'Ada', 'email': 'old@school', 'phone': '1', 'department_id': 2}
    student = {'name': 'Ada Student', 'phone': '9', 'course_id': 3}
    activities = []
    connection = _bind(monkeypatch, [{'id': 4, 'role': 'Student'}, None, None, faculty, student], activities)
    assert user_service.change_user(
        4, 'ada', 'long-secret', 'Teacher', 'inactive', 'ada@school', '8', True, {'user_id': 9},
    ) == 'ok'
    update = connection.cursor_obj.calls[3]
    assert 'password=%s' in update[0]
    assert update[1] == ['ada', 'ada@school', 'hashed:long-secret', 'Teacher', 'inactive', 8, True, 4]
    assert connection.cursor_obj.calls[6][0].startswith('UPDATE faculty')
    assert connection.cursor_obj.calls[6][1][5] == 21
    assert connection.cursor_obj.calls[8] == (
        'UPDATE faculty SET is_active = %s WHERE user_id = %s',
        [0, 4],
    )
    assert activities == [(9, 'edit_user', 'Updated user ada (ID: 4)')]
    assert connection.actions == ['commit', 'close']
    assert connection.dictionary is True


def test_protected_accounts_are_refused_before_any_write(monkeypatch):
    connection = _bind(monkeypatch, [{'id': 4, 'role': 'Super Admin', 'status': 'active'}], problem='protected')
    assert user_service.change_user(4, 'root', '', 'Teacher', 'active', '', '', False, {'user_id': 2}) == 'protected'
    assert len(connection.cursor_obj.calls) == 1
    assert connection.actions == ['close']

    connection = _bind(monkeypatch, [{'id': 4, 'role': 'Super Admin', 'status': 'active'}], last_super_admin=True)
    assert user_service.change_user(4, 'root', '', 'Super Admin', 'inactive', '', '', False, {'user_id': 4}) == 'protected'
    assert connection.actions == ['close']


def test_activating_a_locked_account_unlocks_it(monkeypatch):
    unlocks = []
    _bind(monkeypatch, [{'id': 4, 'role': 'Admin', 'status': 'locked', 'locked_until': None}, None], [], unlocks=unlocks)
    assert user_service.change_user(4, 'ada', '', 'Admin', 'active', '', '', False, {'user_id': 1}) == 'ok'
    assert unlocks == [4]

    unlocks = []
    _bind(monkeypatch, [{'id': 4, 'role': 'Admin', 'status': 'active', 'locked_until': None}, None], [], unlocks=unlocks)
    assert user_service.change_user(4, 'ada', '', 'Admin', 'active', '', '', False, {'user_id': 1}) == 'ok'
    assert unlocks == []


def test_bad_department_id_rolls_back(monkeypatch):
    connection = _bind(monkeypatch, [{'id': 4, 'role': 'Admin'}, None])
    assert user_service.change_user(4, 'ada', '', 'Admin', 'active', '', 'abc', False, {'user_id': 1}) == 'error'
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True
    assert 'edit locked' not in user_service.current_app.logger.errors[0]
    assert 'invalid literal' in user_service.current_app.logger.errors[0]
