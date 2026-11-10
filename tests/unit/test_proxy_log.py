"""Proxy log query order. No live database."""

from services import proxy_log as proxy_service


class _Cursor:
    def __init__(self):
        self.calls = []
        self.closed = False
        self._reads = 0

    def execute(self, sql, params=None):
        self.calls.append((' '.join(sql.split()), list(params or [])))

    def fetchone(self):
        self._reads += 1
        if self._reads == 1:
            return {'total': 25}
        return {
            'total_records': 40,
            'assigned_count': 10,
            'unassigned_count': 2,
            'pending_approval': 3,
            'approved_count': 4,
            'rejected_count': 1,
        }

    def fetchall(self):
        return [{
            'id': 7,
            'absence_date': '2026-10-26',
            'status': 'ASSIGNED',
            'approval_status': 'APPROVED',
            'approval_date': None,
            'approval_notes': None,
            'original_faculty_name': 'Ada',
            'original_employee_id': 'E1',
            'proxy_faculty_name': 'Bea',
            'proxy_employee_id': 'E2',
            'day_of_week': 'Monday',
            'start_time': None,
            'end_time': None,
            'subject_name': 'Maths',
            'class_name': 'FY',
            'division_name': 'A',
            'department_name': 'Civil',
            'approved_by_username': 'admin',
        }]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()
        self.closed = False

    def cursor(self, dictionary=False):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_proxy_log_counts_before_the_page_and_then_loads_unfiltered_totals(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(proxy_service, 'get_db_connection', lambda: connection)
    logs, stats, pagination = proxy_service.load_proxy_log(1, 'ASSIGNED', 'APPROVED', '2026-10-01', '2026-10-31')
    count_sql, count_params = connection.cursor_obj.calls[0]
    page_sql, page_params = connection.cursor_obj.calls[1]
    stats_sql, stats_params = connection.cursor_obj.calls[2]
    assert count_sql.startswith('SELECT COUNT(*) AS total FROM proxy_log pl')
    assert 'ORDER BY' not in count_sql
    assert 'LIMIT' not in count_sql
    assert 'AND pl.status = %s AND pl.approval_status = %s AND pl.absence_date >= %s AND pl.absence_date <= %s' in count_sql
    assert count_params == ['ASSIGNED', 'APPROVED', '2026-10-01', '2026-10-31']
    assert page_sql.endswith('ORDER BY pl.absence_date DESC, t.start_time ASC LIMIT %s OFFSET %s')
    assert page_params == ['ASSIGNED', 'APPROVED', '2026-10-01', '2026-10-31', 20, 0]
    assert 'WHERE' not in stats_sql
    assert stats_params == []
    assert stats['total_records'] == 40
    assert logs[0]['original_faculty_name'] == 'Ada'
    assert pagination == {
        'page': 1,
        'per_page': 20,
        'total': 25,
        'total_pages': 2,
        'has_prev': False,
        'has_next': True,
        'prev_num': None,
        'next_num': 2,
    }
    assert connection.cursor_obj.closed is True
    assert connection.closed is False


class _DecisionCursor:
    def __init__(self, ones, alls=None):
        self.ones = list(ones)
        self.alls = list(alls or [])
        self.calls = []
        self.rowcount = 0
        self.closed = False

    def execute(self, sql, params=None):
        text = ' '.join(sql.split())
        self.calls.append((text, list(params or [])))
        if text.startswith('UPDATE'):
            self.rowcount = 1

    def fetchone(self):
        if not self.ones:
            return None
        return self.ones.pop(0)

    def fetchall(self):
        if not self.alls:
            return []
        return self.alls.pop(0)

    def close(self):
        self.closed = True


class _DecisionConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.actions = []

    def cursor(self, dictionary=False):
        return self.cursor_obj

    def commit(self):
        self.actions.append('commit')

    def rollback(self):
        self.actions.append('rollback')

    def close(self):
        self.actions.append('close')


def _request(**overrides):
    row = {
        'id': 4,
        'original_faculty_id': 9,
        'proxy_faculty_id': None,
        'absence_date': '2026-11-09',
        'status': 'UNASSIGNED',
        'approval_status': 'PENDING',
        'day_of_week': 'Monday',
        'start_time': '09:00:00',
        'end_time': '10:00:00',
        'subject_id': 3,
    }
    row.update(overrides)
    return row


def _bind_decision(monkeypatch, cursor, free=True):
    connection = _DecisionConnection(cursor)
    notices = []
    monkeypatch.setattr(proxy_service, 'get_db_connection', lambda: connection)
    monkeypatch.setattr(proxy_service, 'faculty_timetable_free', lambda *args, **kwargs: free)
    monkeypatch.setattr(proxy_service, '_notify', lambda _cursor, proxy_id: notices.append(proxy_id))
    return connection, notices


def test_approving_a_proxy_request_maps_the_chosen_faculty(monkeypatch):
    cursor = _DecisionCursor(
        [_request(), None],
        [[{'user_id': 12, 'name': 'Bea', 'employee_id': 'E2'}]],
    )
    connection, notices = _bind_decision(monkeypatch, cursor)
    assert proxy_service.decide_proxy_request(4, 'approve', 12, None, 7) == 'ok'
    update = cursor.calls[-1]
    assert "status = 'ASSIGNED'" in update[0]
    assert "approval_status = 'APPROVED'" in update[0]
    assert update[1] == [12, 7, None, 4]
    assert notices == [4]
    assert connection.actions == ['commit', 'close']
    assert cursor.closed is True


def test_approving_uses_the_substitute_the_teacher_named(monkeypatch):
    cursor = _DecisionCursor(
        [_request(proxy_faculty_id=15), {'user_id': 15, 'name': 'Cara', 'employee_id': 'E3'}, None],
        [[]],
    )
    _bind_decision(monkeypatch, cursor)
    assert proxy_service.decide_proxy_request(4, 'approve', None, 'Covered', 7) == 'ok'
    assert cursor.calls[-1][1] == [15, 7, 'Covered', 4]


def test_rejecting_a_proxy_request_leaves_the_assignment_status(monkeypatch):
    cursor = _DecisionCursor([_request(status='ASSIGNED', proxy_faculty_id=12)])
    connection, notices = _bind_decision(monkeypatch, cursor)
    assert proxy_service.decide_proxy_request(4, 'reject', None, 'Not available', 7) == 'ok'
    sql, params = cursor.calls[-1]
    assert "approval_status = 'REJECTED'" in sql
    assert 'status =' not in sql.replace('approval_status', '')
    assert params == [7, 'Not available', 4]
    assert notices == []
    assert connection.actions == ['commit', 'close']


def test_approval_requires_a_faculty_member_who_is_free(monkeypatch):
    cursor = _DecisionCursor([_request()])
    _bind_decision(monkeypatch, cursor)
    assert proxy_service.decide_proxy_request(4, 'approve', None, None, 7) == 'choice'
    assert not any(sql.startswith('UPDATE') for sql, _params in cursor.calls)

    busy = _DecisionCursor([_request()], [[{'user_id': 12, 'name': 'Bea', 'employee_id': 'E2'}]])
    _bind_decision(monkeypatch, busy, free=False)
    assert proxy_service.decide_proxy_request(4, 'approve', 12, None, 7) == 'busy'
    assert not any(sql.startswith('UPDATE') for sql, _params in busy.calls)


def test_a_decided_proxy_request_cannot_be_changed(monkeypatch):
    cursor = _DecisionCursor([_request(approval_status='APPROVED')])
    connection, _notices = _bind_decision(monkeypatch, cursor)
    assert proxy_service.decide_proxy_request(4, 'reject', None, None, 7) == 'closed'
    assert len(cursor.calls) == 1
    assert connection.actions == ['close']


def test_proxy_log_closes_the_connection_when_the_page_asks(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(proxy_service, 'get_db_connection', lambda: connection)
    proxy_service.load_proxy_log(1, '', '', '', '', close_connection=True)
    assert connection.cursor_obj.closed is True
    assert connection.closed is True
