"""Teacher portal extract. No live database."""

from datetime import date

from services import teacher_portal


class _Cursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        self.calls.append((' '.join(sql.split()), params))

    def fetchone(self):
        if not self.rows:
            return None
        value = self.rows.pop(0)
        return value if not isinstance(value, list) else value[0]

    def fetchall(self):
        if not self.rows:
            return []
        value = self.rows.pop(0)
        return value if isinstance(value, list) else [value]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, rows=None):
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


def _bind(monkeypatch, module, connection):
    flashes = []
    monkeypatch.setattr(module, 'get_db_connection', lambda: connection)
    if hasattr(module, 'flash'):
        monkeypatch.setattr(module, 'flash', lambda message, category: flashes.append((message, category)))
    if hasattr(module, 'current_app'):
        class _Logger:
            def error(self, message):
                flashes.append(('log', message))
            def exception(self, message):
                flashes.append(('log', message))
        class _App:
            logger = _Logger()
        monkeypatch.setattr(module, 'current_app', _App())
    return flashes


def test_teacher_absence_inserts_unprocessed(monkeypatch):
    connection = _Connection()
    _bind(monkeypatch, teacher_portal, connection)
    assert teacher_portal.add_absence(4, '2026-10-26', 'ill') == 'ok'
    sql, params = connection.cursor_obj.calls[0]
    assert "status) VALUES (%s, %s, %s, 'UNPROCESSED')" in sql
    assert params == (4, date(2026, 10, 26), 'ill')
    assert connection.actions == ['commit']
    assert connection.cursor_obj.closed is True


def test_availability_commits_the_delete_before_inserts(monkeypatch):
    connection = _Connection([{'user_id': 9}])
    flashes = _bind(monkeypatch, teacher_portal, connection)
    assert teacher_portal.save_availability(4, {}) == 'ok'
    assert connection.cursor_obj.calls[1][0] == 'DELETE FROM faculty_availability WHERE faculty_id = %s'
    assert connection.cursor_obj.calls[1][1] == [9]
    assert connection.actions[0] == 'commit'
    assert flashes == [('Availability updated successfully.', 'success')]
    assert connection.actions[-1] == 'close'
