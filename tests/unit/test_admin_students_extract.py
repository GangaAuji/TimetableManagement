"""Admin student extract. No live database."""

from services import admin_students


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.closed = False
        self.lastrowid = 15

    def execute(self, sql, params=None):
        copied = None if params is None else (params if isinstance(params, tuple) else list(params))
        self.calls.append((' '.join(sql.split()), copied))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)

    def fetchall(self):
        if not self.rows:
            return []
        value = self.rows.pop(0)
        return value if isinstance(value, list) else [value]

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


def _bind(monkeypatch, connection, accessible):
    flashes = []
    monkeypatch.setattr(admin_students, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(admin_students, 'get_accessible_student_ids', lambda user_id: accessible)
    monkeypatch.setattr(admin_students, 'flash', lambda *args: flashes.append(args))
    return flashes


def test_student_list_with_no_access_leaves_the_connection_open(monkeypatch):
    connection = _Connection([
        {'total': 0},
        [],
        [],
        [],
        [],
        {'total': 0},
    ])
    _bind(monkeypatch, connection, [])
    page = admin_students.list_students(1, '', '', 's.name;drop', 'DESC', 4)
    count_sql, count_params = connection.cursor_obj.calls[0]
    assert 's.id = -1' in count_sql
    assert count_params == ()
    assert 'drop' not in connection.cursor_obj.calls[1][0]
    assert 'ORDER BY s.name DESC' in connection.cursor_obj.calls[1][0]
    assert connection.cursor_obj.calls[-1][0] == 'SELECT 0 AS total'
    assert connection.cursor_obj.calls[-1][1] is None
    assert page['total_active_students'] == 0
    assert connection.cursor_obj.closed is True
    assert connection.actions == []


def test_duplicate_student_username_closes_both_without_commit(monkeypatch):
    connection = _Connection([{'id': 3}])
    flashes = _bind(monkeypatch, connection, None)
    assert admin_students.add_student('ada', 'secret', 'Ada', 'a@b.c', '', '', '', '', '') == 'duplicate'
    sql, params = connection.cursor_obj.calls[0]
    assert sql == 'SELECT id FROM users WHERE username = %s'
    assert params == ['ada']
    assert flashes[0][0] == 'Username already exists.'
    assert connection.actions == ['close']
    assert connection.cursor_obj.closed is True


def test_bulk_invite_user_insert_stores_email_and_active_status(monkeypatch):
    import sys
    import types
    connection = _Connection([None, None])
    _bind(monkeypatch, connection, None)
    monkeypatch.setitem(sys.modules, 'pandas', types.ModuleType('pandas'))

    class _Form(dict):
        pass

    class _Files(dict):
        pass

    result = admin_students.invite_students(_Files(), _Form({
        'students_data': 'Ada, ada@school.edu, ada',
        'default_course_id': '2',
    }))
    assert result == 'manage'
    insert_sql, insert_params = connection.cursor_obj.calls[2]
    assert "role, email, status" in insert_sql
    assert insert_params[2] == 'ada@school.edu'
    assert connection.actions[0] == 'commit'
    assert connection.actions[-1] == 'close'
