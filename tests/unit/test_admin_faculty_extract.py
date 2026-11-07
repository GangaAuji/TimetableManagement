"""Admin faculty extract. No live database."""

from services import faculty_admin


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.closed = False
        self.lastrowid = 8

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


def _bind(monkeypatch, connection):
    flashes = []
    monkeypatch.setattr(faculty_admin, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(faculty_admin, 'flash', lambda *args: flashes.append(args))
    monkeypatch.setattr(faculty_admin, 'paginate', lambda *args, **kwargs: ([], 0))
    monkeypatch.setattr(faculty_admin, 'get_accessible_faculty_ids', lambda user_id: [])
    return flashes


def test_faculty_with_no_access_skips_the_status_counts(monkeypatch):
    connection = _Connection([[], {'total': 0}])
    _bind(monkeypatch, connection)
    page = faculty_admin.list_faculty(1, '', '', 4)
    assert page['total_active_faculty'] == 0
    assert page['total_inactive_faculty'] == 0
    assert connection.cursor_obj.calls[0][0].startswith('SELECT id, name FROM departments')
    assert 'f.id = -1' in connection.cursor_obj.calls[1][0]
    assert connection.actions == []
    assert connection.cursor_obj.closed is True


def test_duplicate_faculty_username_closes_both_without_commit(monkeypatch):
    connection = _Connection([{'id': 2}])
    flashes = _bind(monkeypatch, connection)
    assert faculty_admin.add_faculty_member('ada', 'secret', 'Ada', 'a@b.c', '1', '', '', True, '') == 'duplicate'
    assert connection.cursor_obj.calls[0][1] == ['ada']
    assert flashes[0][0] == 'Username already exists.'
    assert connection.actions == ['close']


def test_admin_absence_is_stored_as_processed(monkeypatch):
    connection = _Connection([])
    _bind(monkeypatch, connection)
    monkeypatch.setattr(faculty_admin, '_admin_find_and_assign_proxy', lambda *args: None)
    assert faculty_admin.add_faculty_absence(4, '2026-10-26', 'leave') == 'ok'
    sql, params = connection.cursor_obj.calls[0]
    assert "'PROCESSED'" in sql
    assert params[0] == 4
    assert params[2] == 'leave'
    assert connection.actions == ['commit']
    assert connection.cursor_obj.closed is True
