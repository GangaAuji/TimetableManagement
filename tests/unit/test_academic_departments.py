"""Academic department SQL and save flow. No live database."""

import pytest

from data_access.departments import (
    delete_department,
    fetch_departments,
    insert_department,
    update_department,
)
from services import departments as department_service


class _Cursor:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError('department locked')
        self.calls.append((sql, params))

    def fetchall(self):
        return [{'id': 1, 'name': 'Science', 'course_count': 2}]

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


def test_department_queries_keep_their_sql():
    cursor = _Cursor()
    assert fetch_departments(cursor) == [{'id': 1, 'name': 'Science', 'course_count': 2}]
    insert_department(cursor, 'Science', 'SCI', 'Labs', 'Ada', 1)
    update_department(cursor, 4, 'Science', 'SCI', '', 'Ada', 0)
    delete_department(cursor, 4)
    assert 'COUNT(c.id) as course_count' in cursor.calls[0][0]
    assert 'GROUP BY d.id' in cursor.calls[0][0]
    assert 'ORDER BY d.name' in cursor.calls[0][0]
    assert cursor.calls[1][1] == ('Science', 'SCI', 'Labs', 'Ada', 1)
    assert cursor.calls[2][1] == ('Science', 'SCI', '', 'Ada', 0, 4)
    assert cursor.calls[3] == ('DELETE FROM departments WHERE id = %s', (4,))


def test_create_commits_on_a_plain_cursor(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(department_service, '_connect', lambda: connection)
    assert department_service.create_department('Science', 'SCI', '', '', 1) is None
    assert connection.dictionary is False
    assert connection.actions == ['commit', 'close']


def test_change_keeps_the_id_last(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(department_service, '_connect', lambda: connection)
    department_service.change_department(4, 'Science', 'SCI', 'Labs', 'Ada', 0)
    assert connection.cursor_obj.calls[0][1][-1] == 4
    assert connection.actions[0] == 'commit'


def test_failed_delete_rolls_back(monkeypatch):
    connection = _Connection(fail_on='DELETE')
    monkeypatch.setattr(department_service, '_connect', lambda: connection)
    assert department_service.remove_department(4) == 'department locked'
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True


def test_list_uses_a_dictionary_cursor(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(department_service, '_connect', lambda: connection)
    assert department_service.list_departments()[0]['course_count'] == 2
    assert connection.dictionary is True
    assert connection.actions == ['close']


def test_list_still_closes_when_the_read_fails(monkeypatch):
    connection = _Connection(fail_on='SELECT')
    monkeypatch.setattr(department_service, '_connect', lambda: connection)
    with pytest.raises(RuntimeError, match='department locked'):
        department_service.list_departments()
    assert connection.actions == ['close']
