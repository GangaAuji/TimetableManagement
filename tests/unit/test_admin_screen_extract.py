"""Audit, shift, and admin API extracts. No live database."""

from services import admin_api
from services import audit_logs
from services import shift_management


class _Cursor:
    def __init__(self, rows=None, row=None):
        self.rows = list(rows or [])
        self.row = row
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        copied = None if params is None else list(params)
        self.calls.append((' '.join(sql.split()), copied))

    def fetchone(self):
        if self.row is not None:
            return self.row
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
    def __init__(self, rows=None, row=None, dictionary=None):
        self.cursor_obj = _Cursor(rows, row)
        self.actions = []
        self.dictionary = dictionary

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        self.cursor_obj.dictionary = dictionary
        return self.cursor_obj

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')

    def close(self):
        self.actions.append('close')


def test_audit_list_counts_before_paging_and_leaves_the_connection_open(monkeypatch):
    connection = _Connection([
        {'total': 2},
        [],
        [],
        [],
        [],
        {'total_activities': 1, 'active_users': 1, 'failed_activities': 0},
        {'count': 0},
        [],
        [],
        [],
        [],
    ])
    monkeypatch.setattr(audit_logs, 'get_db_connection', lambda: connection)
    page = audit_logs.load_audit_page(4, 'login', '2026-10-01', '2026-10-02', 1)
    count_sql, count_params = connection.cursor_obj.calls[0]
    assert count_sql.startswith('SELECT COUNT(*) as total FROM (')
    assert count_params == [4, '%login%', '2026-10-01', '2026-10-02 23:59:59']
    assert 'al.user_id = %s' in count_sql
    data_sql, data_params = connection.cursor_obj.calls[1]
    assert data_sql.endswith('LIMIT %s OFFSET %s')
    assert data_params[-2:] == [50, 0]
    assert page['total_records'] == 2
    assert connection.cursor_obj.closed is True
    assert connection.actions == []


def test_missing_audit_user_leaves_the_connection_open(monkeypatch):
    connection = _Connection([None])
    monkeypatch.setattr(audit_logs, 'get_db_connection', lambda: connection)
    assert audit_logs.load_user_activity(9) == 'missing'
    assert connection.cursor_obj.closed is False
    assert connection.actions == []


def test_shift_delete_uses_the_private_connection_and_a_plain_cursor(monkeypatch):
    connection = _Connection(row=(3,))
    flashes = []
    monkeypatch.setattr(shift_management, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(shift_management, 'flash', lambda *args: flashes.append(args))
    shift_management.remove_shift_pattern(6)
    assert connection.dictionary is False
    assert connection.actions == ['rollback', 'close']
    assert 'Error deleting shift pattern' in flashes[0][0]


def test_coverage_counts_use_integer_ids(monkeypatch):
    connection = _Connection([
        [{'id': 2, 'name': 'Math', 'lpw': 3, 'phw': 1}],
        [{'subject_id': 2, 'cnt': 4}],
    ])
    monkeypatch.setattr(admin_api, 'get_db_connection', lambda: connection)
    subjects, counts = admin_api.coverage_subjects('8', '3', '1')
    sql, params = connection.cursor_obj.calls[1]
    assert 'f.user_id' not in sql
    assert tuple(params[:3]) == (8, 3, 1)
    assert counts[2] == 4
    assert subjects[0]['name'] == 'Math'
    assert connection.actions == ['close']
