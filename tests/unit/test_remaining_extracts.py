"""Role changes, pagination, proxy assignment, and the timetable move. No live database."""

from datetime import date, time

from services import admin_queries
from services import roles as role_service
from services import user_actions
from services.timetable import generator


class _Cursor:
    def __init__(self, rows=None, fail_on=None):
        self.rows = list(rows or [])
        self.fail_on = fail_on
        self.calls = []
        self.closed = False
        self.rowcount = 1

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        if self.fail_on and self.fail_on in text:
            raise RuntimeError('locked')
        self.calls.append((text, params))

    def fetchone(self):
        if not self.rows:
            return None
        return self.rows.pop(0)

    def fetchall(self):
        if not self.rows:
            return []
        row = self.rows.pop(0)
        return row if isinstance(row, list) else [row]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, rows=None, fail_on=None):
        self.cursor_obj = _Cursor(rows, fail_on)
        self.actions = []
        self.dictionary = None

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        return self.cursor_obj

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')

    def close(self):
        self.actions.append('close')


def _bind(monkeypatch, module, connection):
    flashes = []
    activities = []
    monkeypatch.setattr(module, 'get_db_connection', lambda: connection)
    if hasattr(module, 'flash'):
        monkeypatch.setattr(module, 'flash', lambda message, category: flashes.append((message, category)))
    if hasattr(module, 'log_activity'):
        monkeypatch.setattr(module, 'log_activity', lambda *args, **kwargs: activities.append(args))

    class _Logger:
        def error(self, message):
            activities.append(('log', message))

    class _App:
        logger = _Logger()

    if hasattr(module, 'current_app'):
        monkeypatch.setattr(module, 'current_app', _App())
    return flashes, activities


def test_duplicate_role_does_not_roll_back(monkeypatch):
    connection = _Connection([{'id': 3}])
    flashes, activities = _bind(monkeypatch, role_service, connection)
    role_service.create_role('Admin', 'desk', [1], {'user_id': 9})
    assert flashes == [('Role already exists.', 'danger')]
    assert connection.actions == ['close']
    assert activities == []
    assert connection.cursor_obj.closed is True


def test_super_admin_role_is_not_deleted(monkeypatch):
    connection = _Connection([{'name': 'Super Admin'}])
    flashes, _activities = _bind(monkeypatch, role_service, connection)
    role_service.remove_role(1, {'user_id': 9})
    assert flashes == [('Cannot delete Super Admin role.', 'danger')]
    assert len(connection.cursor_obj.calls) == 1
    assert connection.actions == ['close']


def test_short_bulk_password_does_not_roll_back(monkeypatch):
    connection = _Connection()
    _flashes, activities = _bind(monkeypatch, user_actions, connection)
    payload, status = user_actions.apply_bulk_user_action('reset_password', ['4'], 'short', {'user_id': 9})
    assert status == 400
    assert payload['error'] == 'New password must be at least 8 characters.'
    assert connection.actions == ['close']
    assert activities == []


def test_bulk_activate_updates_teachers_and_students(monkeypatch):
    connection = _Connection([[
        {'id': 2, 'role': 'Teacher'},
        {'id': 3, 'role': 'Student'},
    ]])
    _flashes, activities = _bind(monkeypatch, user_actions, connection)
    monkeypatch.setattr(user_actions, 'account_problem', lambda cursor, actor_id, user_id, new_role=None: None)
    payload, status = user_actions.apply_bulk_user_action('activate', ['1', '2', '3'], None, {'user_id': 9})
    assert status == 200
    assert payload['message'] == 'Users activated successfully.'
    assert "role != 'Super Admin'" in connection.cursor_obj.calls[0][0]
    assert connection.cursor_obj.calls[0][1] == ['1', '2', '3']
    assert connection.cursor_obj.calls[1][1] == ['active', 2, 3]
    assert connection.cursor_obj.calls[2][0].startswith('UPDATE faculty')
    assert connection.cursor_obj.calls[3][0].startswith('UPDATE students')
    assert activities == [(9, 'bulk_activate_users', 'Affected IDs: 1,2,3')]
    assert connection.actions == ['commit', 'close']


def test_bulk_action_naming_a_protected_account_or_yourself_is_refused(monkeypatch):
    for ids, problem in ((['2', '3'], 'protected'), (['2', '9'], None)):
        connection = _Connection([])
        _flashes, activities = _bind(monkeypatch, user_actions, connection)
        monkeypatch.setattr(
            user_actions, 'account_problem', lambda cursor, actor_id, user_id, new_role=None: problem,
        )
        _payload, status = user_actions.apply_bulk_user_action('deactivate', ids, None, {'user_id': 9})
        assert status == 403
        assert connection.cursor_obj.calls == []
        assert activities == []
        assert 'commit' not in connection.actions


def test_user_export_leaves_the_connection_open(monkeypatch):
    connection = _Connection([[{'id': 4, 'username': 'ada'}]])
    _bind(monkeypatch, user_actions, connection)
    rows = user_actions.export_user_rows('Teacher', 'active', 'ada')
    assert rows == [{'id': 4, 'username': 'ada'}]
    sql, params = connection.cursor_obj.calls[0]
    assert 'WHERE u.role = %s AND u.status = %s AND (u.username LIKE %s)' in sql
    assert params == ['Teacher', 'active', '%ada%']
    assert connection.cursor_obj.closed is True
    assert connection.actions == []


def test_pagination_counts_before_the_page_and_rejects_a_query_without_from(monkeypatch):
    connection = _Connection([{'total': 25}, [{'id': 1}]])
    monkeypatch.setattr(admin_queries, 'get_db_connection', lambda: connection)
    rows, pages = admin_queries.query_page('SELECT id FROM users WHERE status = %s', ('active',), 2, 10)
    assert rows == [{'id': 1}]
    assert pages == 3
    assert connection.cursor_obj.calls[0][0] == 'SELECT COUNT(*) AS total FROM users WHERE status = %s'
    assert connection.cursor_obj.calls[0][1] == ('active',)
    assert connection.cursor_obj.calls[1][1] == ('active', 10, 10)
    assert connection.cursor_obj.closed is True
    assert connection.actions == []

    connection = _Connection()
    monkeypatch.setattr(admin_queries, 'get_db_connection', lambda: connection)
    try:
        admin_queries.query_page('SELECT 1', (), 1)
    except ValueError as exc:
        assert str(exc) == 'Query for pagination must include a FROM clause.'
    else:
        raise AssertionError('the missing FROM clause was accepted')
    assert connection.cursor_obj.closed is False
    assert connection.actions == []


def test_proxy_assignment_ignores_the_active_flag_and_leaves_the_connection_open(monkeypatch):
    connection = _Connection([
        [{'id': 8, 'subject_id': 3, 'start_time': time(9, 0), 'end_time': time(10, 0)}],
        [{'faculty_id': 15}],
    ])
    monkeypatch.setattr(admin_queries, 'get_db_connection', lambda: connection)
    seen = []
    monkeypatch.setattr(
        admin_queries,
        'faculty_timetable_free',
        lambda *args, **kwargs: seen.append(kwargs) or True,
    )
    admin_queries.assign_admin_proxy(4, date(2026, 10, 26), {'user_id': 9})
    assert seen == [{'active_only': False}]
    assert connection.cursor_obj.calls[0][1] == (4, 'Monday')
    assert connection.cursor_obj.calls[1][1] == (3, 4)
    assert connection.cursor_obj.calls[2][1] == (4, 15, 8, date(2026, 10, 26), 'ASSIGNED', 9)
    assert "approval_status, approval_date, approved_by" in connection.cursor_obj.calls[2][0]
    assert connection.actions == ['commit']
    assert connection.cursor_obj.closed is True


def test_timetable_generation_lives_on_the_service():
    assert generator.WEEKDAY_ORDER[0] == 'Monday'
    slots = generator.build_time_slots(time(9, 0), time(10, 0), 30)
    assert slots == [(time(9, 0), time(9, 30)), (time(9, 30), time(10, 0))]
