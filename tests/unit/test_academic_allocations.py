"""Allocation filters and the faculty.user_id save. No live database."""

from decimal import Decimal

from data_access.allocations import fetch_allocations
from services import allocations as allocation_service


class _Cursor:
    def __init__(self, fetchone_row=None, allocations=None, fail_on=None):
        self.fetchone_row = fetchone_row
        self.allocations = allocations if allocations is not None else []
        self.fail_on = fail_on
        self.calls = []
        self.closed = False
        self._reads = 0

    def execute(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError('allocation locked')
        self.calls.append((' '.join(sql.split()), params))

    def fetchone(self):
        return self.fetchone_row

    def fetchall(self):
        self._reads += 1
        if self._reads == 1:
            return self.allocations
        return [{'id': self._reads}]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, fetchone_row=None, allocations=None, fail_on=None):
        self.cursor_obj = _Cursor(fetchone_row, allocations, fail_on)
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


def test_allocation_filters_use_the_faculty_row_id():
    cursor = _Cursor()
    fetch_allocations(cursor, None, None, None)
    fetch_allocations(cursor, 4, None, None)
    fetch_allocations(cursor, None, 9, None)
    fetch_allocations(cursor, 4, 9, 2)
    assert 'WHERE' not in cursor.calls[0][0]
    assert cursor.calls[0][1] == ()
    assert 'fa.faculty_id = f.user_id' in cursor.calls[0][0]
    assert 'WHERE fa.class_id = %s' in cursor.calls[1][0]
    assert cursor.calls[1][1] == (4,)
    faculty_where = cursor.calls[2][0].split('WHERE', 1)[1]
    assert faculty_where.startswith(' f.id = %s')
    assert cursor.calls[2][1] == (9,)
    assert 'WHERE fa.class_id = %s AND f.id = %s AND s.course_id = %s' in cursor.calls[3][0]
    assert cursor.calls[3][1] == (4, 9, 2)


def test_list_converts_decimals_and_keeps_menu_order(monkeypatch):
    rows = [{'allocated_hours': Decimal('3.5'), 'workload_percentage': Decimal('100')}]
    connection = _Connection(allocations=rows)
    monkeypatch.setattr(allocation_service, '_connect', lambda: connection)
    result = allocation_service.list_allocations(0, None, None)
    assert result[0][0]['allocated_hours'] == 3.5
    assert result[0][0]['workload_percentage'] == 100.0
    queries = [call[0] for call in connection.cursor_obj.calls]
    assert queries[1] == 'SELECT * FROM faculty WHERE is_active = TRUE ORDER BY name'
    assert queries[2] == 'SELECT * FROM subjects ORDER BY name'
    assert queries[3] == 'SELECT * FROM classes ORDER BY display_order'
    assert queries[4] == 'SELECT * FROM divisions ORDER BY name'
    assert queries[5] == 'SELECT * FROM semesters ORDER BY semester_number'
    assert queries[6] == 'SELECT * FROM course_batches WHERE is_active = TRUE ORDER BY batch_name'
    assert queries[7] == 'SELECT * FROM courses WHERE is_active = TRUE ORDER BY name'
    assert connection.dictionary is True


def test_create_stores_the_faculty_user_id(monkeypatch):
    connection = _Connection(fetchone_row=(55,))
    monkeypatch.setattr(allocation_service, '_connect', lambda: connection)
    assert allocation_service.create_allocation(
        7, 3, None, None, None, None, 0, 100.0, 1, 'Regular', None, None, '',
    ) is None
    assert connection.dictionary is False
    assert connection.cursor_obj.calls[0] == ('SELECT user_id FROM faculty WHERE id = %s', (7,))
    assert connection.cursor_obj.calls[1][1][0] == 55
    assert connection.actions == ['commit', 'close']


def test_missing_faculty_does_not_commit_or_roll_back(monkeypatch):
    connection = _Connection(fetchone_row=None)
    monkeypatch.setattr(allocation_service, '_connect', lambda: connection)
    assert allocation_service.change_allocation(
        8, 7, 3, None, None, None, None, 2, 50, 0, 'Regular', None, None, '',
    ) == 'invalid_faculty'
    assert len(connection.cursor_obj.calls) == 1
    assert connection.actions == ['close']


def test_failed_delete_rolls_back(monkeypatch):
    connection = _Connection(fail_on='DELETE')
    monkeypatch.setattr(allocation_service, '_connect', lambda: connection)
    assert allocation_service.remove_allocation(8) == 'allocation locked'
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True
