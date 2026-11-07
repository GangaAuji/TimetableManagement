"""Academic course SQL and save flow. No live database."""

import pytest

from data_access.courses import (
    count_active_courses,
    delete_course,
    fetch_active_departments,
    fetch_courses,
    insert_course,
    update_course,
)
from services import courses as course_service


class _Cursor:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError('course locked')
        self.calls.append((sql, params))

    def fetchone(self):
        return {'count': 4}

    def fetchall(self):
        if self.calls and 'COUNT(DISTINCT' in self.calls[-1][0]:
            return [{'id': 1, 'name': 'BSc', 'subject_count': 3, 'batch_count': 1}]
        return [{'id': 2, 'name': 'Science'}]

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


def test_course_queries_keep_their_sql():
    cursor = _Cursor()
    assert count_active_courses(cursor) == 4
    assert fetch_courses(cursor)[0]['subject_count'] == 3
    fetch_active_departments(cursor)
    insert_course(cursor, 'BSc', 'BSC', 'UG', 2, 3, 6, '', 1)
    update_course(cursor, 8, 'BSc', 'BSC', 'UG', 2, 4, 8, 'Labs', 0)
    delete_course(cursor, 8)
    assert cursor.calls[0] == ('SELECT COUNT(*) AS count FROM courses WHERE is_active = TRUE', None)
    assert 'COUNT(DISTINCT s.id) as subject_count' in cursor.calls[1][0]
    assert 'ORDER BY c.program, c.name' in cursor.calls[1][0]
    assert cursor.calls[2] == ('SELECT * FROM departments WHERE is_active = TRUE ORDER BY name', None)
    assert cursor.calls[3][1] == ('BSc', 'BSC', 'UG', 2, 3, 6, '', 1)
    assert cursor.calls[4][1][-1] == 8
    assert cursor.calls[5] == ('DELETE FROM courses WHERE id = %s', (8,))


def test_list_counts_active_courses_before_the_rows(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(course_service, '_connect', lambda: connection)
    courses, departments, course_count = course_service.list_courses()
    assert course_count == 4
    assert courses[0]['name'] == 'BSc'
    assert departments[0]['name'] == 'Science'
    assert connection.dictionary is True
    assert connection.cursor_obj.calls[0][0].startswith('SELECT COUNT(*)')
    assert 'FROM courses c' in connection.cursor_obj.calls[1][0]
    assert connection.cursor_obj.calls[2][0].startswith('SELECT * FROM departments')
    assert connection.actions == ['close']


def test_create_commits_the_submitted_values(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(course_service, '_connect', lambda: connection)
    assert course_service.create_course('BSc', 'BSC', 'UG', '2', 3, 6, '', 1) is None
    assert connection.dictionary is False
    assert connection.cursor_obj.calls[0][1] == ('BSc', 'BSC', 'UG', '2', 3, 6, '', 1)
    assert connection.actions == ['commit', 'close']


def test_change_keeps_the_id_last(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(course_service, '_connect', lambda: connection)
    course_service.change_course(8, 'BSc', 'BSC', 'UG', '2', '4', '8', 'Labs', 0)
    assert connection.cursor_obj.calls[0][1] == ('BSc', 'BSC', 'UG', '2', '4', '8', 'Labs', 0, 8)


def test_failed_delete_rolls_back(monkeypatch):
    connection = _Connection(fail_on='DELETE')
    monkeypatch.setattr(course_service, '_connect', lambda: connection)
    assert course_service.remove_course(8) == 'course locked'
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True


def test_list_still_closes_when_the_count_fails(monkeypatch):
    connection = _Connection(fail_on='COUNT(*)')
    monkeypatch.setattr(course_service, '_connect', lambda: connection)
    with pytest.raises(RuntimeError, match='course locked'):
        course_service.list_courses()
    assert connection.actions == ['close']
