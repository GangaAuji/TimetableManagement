"""Admin dashboard, rooms, and teacher portal extracts. No live database."""

from datetime import date

from services import admin_dashboard
from services import admin_departments
from services import admin_rooms
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


def test_department_choices_close_the_connection(monkeypatch):
    connection = _Connection([[{'id': 2, 'name': 'Civil'}]])
    _bind(monkeypatch, admin_departments, connection)
    assert admin_departments.list_department_choices() == [{'id': 2, 'name': 'Civil'}]
    assert connection.cursor_obj.calls[0][0] == 'SELECT id, name FROM departments ORDER BY name'
    assert connection.cursor_obj.closed is True
    assert connection.actions == ['close']


def test_dashboard_counts_students_before_faculty(monkeypatch):
    rows = [{'count': 3}] * 8
    rows.append([{'room_type': 'Lab', 'count': 2}])
    rows.append([])
    rows.append([])
    rows.append([])
    rows.append([])
    rows.append([])
    rows.append([])
    connection = _Connection(rows)
    _bind(monkeypatch, admin_dashboard, connection)
    page = admin_dashboard.load_admin_dashboard()
    assert connection.cursor_obj.calls[0][0] == 'SELECT COUNT(id) as count FROM students WHERE is_active = 1'
    assert connection.cursor_obj.calls[1][0] == 'SELECT COUNT(id) as count FROM faculty WHERE is_active = 1'
    assert page['stats']['total_students'] == 3
    assert page['stats']['recent_updates'] == []
    assert connection.cursor_obj.closed is True
    assert connection.actions == []


def test_duplicate_room_does_not_roll_back(monkeypatch):
    connection = _Connection([{'taken': 1}])
    flashes = _bind(monkeypatch, admin_rooms, connection)
    payload, status = admin_rooms.create_room('A1', 'Lab', '20', '')
    assert status == 400
    assert payload['error'] == 'Room number already exists.'
    assert connection.actions == ['close']
    assert flashes == []


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
