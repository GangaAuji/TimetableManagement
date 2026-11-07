"""Academic batch SQL and save flow. No live database."""

import pytest

from data_access.batches import delete_batch, fetch_batches, insert_batch, update_batch
from services import batches as batch_service


class _Cursor:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on
        self.closed = False
        self._fetch_index = 0

    def execute(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError('batch locked')
        self.calls.append((' '.join(sql.split()), params))

    def fetchall(self):
        self._fetch_index += 1
        if self._fetch_index == 1:
            return [{'id': 1, 'batch_name': 'A', 'course_name': 'BSc'}]
        if self._fetch_index == 2:
            return [{'id': 2, 'name': 'BSc'}]
        return [{'id': 3, 'name': '2025-26'}]

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, fail_on=None):
        self.cursor_obj = _Cursor(fail_on)
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


def test_batch_queries_keep_their_sql():
    cursor = _Cursor()
    assert fetch_batches(cursor)[0]['batch_name'] == 'A'
    insert_batch(cursor, 2, 'A', None, '2026', '2029', 0, 1, 1)
    update_batch(cursor, 8, 2, 'A', 3, '2026', '2029', 40, 2, 0)
    delete_batch(cursor, 8)
    assert 'ORDER BY cb.start_year DESC, c.name' in cursor.calls[0][0]
    assert cursor.calls[1][1] == (2, 'A', None, '2026', '2029', 0, 1, 1)
    assert cursor.calls[2][1][-1] == 8
    assert cursor.calls[3] == ('DELETE FROM course_batches WHERE id = %s', (8,))


def test_list_loads_batches_then_active_courses_then_years(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(batch_service, '_connect', lambda: connection)
    batches, courses, years = batch_service.list_batches()
    assert batches[0]['course_name'] == 'BSc'
    assert courses[0]['name'] == 'BSc'
    assert years[0]['name'] == '2025-26'
    assert connection.dictionary is True
    assert connection.cursor_obj.calls[1][0] == 'SELECT * FROM courses WHERE is_active = TRUE ORDER BY name'
    assert 'ORDER BY start_date DESC' in connection.cursor_obj.calls[2][0]
    assert connection.actions == ['close']


def test_create_keeps_an_empty_year_as_null(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(batch_service, '_connect', lambda: connection)
    assert batch_service.create_batch(2, 'A', None, '2026', '2029', 0, 1, 1) is None
    assert connection.dictionary is False
    assert connection.cursor_obj.calls[0][1][2] is None
    assert connection.actions == ['commit', 'close']


def test_change_keeps_the_id_last(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(batch_service, '_connect', lambda: connection)
    batch_service.change_batch(8, '2', 'A', '3', '2026', '2029', 40, 2, 0)
    assert connection.cursor_obj.calls[0][1] == ('2', 'A', '3', '2026', '2029', 40, 2, 0, 8)


def test_failed_delete_rolls_back(monkeypatch):
    connection = _Connection(fail_on='DELETE')
    monkeypatch.setattr(batch_service, '_connect', lambda: connection)
    assert batch_service.remove_batch(8) == 'batch locked'
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True
