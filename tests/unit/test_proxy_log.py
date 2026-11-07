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
