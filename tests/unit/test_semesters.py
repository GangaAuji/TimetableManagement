"""Semester SQL, current-row behavior, and page normalization. No live database."""

from datetime import date
from decimal import Decimal

import pytest

from data_access.semesters import delete_semester, fetch_classes, fetch_semesters, insert_semester, update_semester
from services import semesters as semester_service


class _Cursor:
    def __init__(self, results=None, fail_on=None):
        self.calls = []
        self.results = list(results or [])
        self.fail_on = fail_on
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError('semester locked')
        self.calls.append((sql, params))

    def fetchall(self):
        if self.results:
            return self.results.pop(0)
        return []

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, results=None, fail_on=None):
        self.cursor_obj = _Cursor(results, fail_on)
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


class _BadDate:
    def isoformat(self):
        raise RuntimeError('bad date')


def test_semester_queries_keep_their_sql():
    cursor = _Cursor(results=[[{'id': 1}]])
    assert fetch_semesters(cursor) == [{'id': 1}]
    fetch_classes(cursor)
    insert_semester(cursor, 2, 1, 'Odd', '2026-06-01', '2026-12-01', 3, 1, 18.0, 30.0)
    update_semester(cursor, 9, 2, 2, 'Even', '2027-01-01', '2027-05-31', None, 0, None, None)
    delete_semester(cursor, 9)
    assert 'JOIN academic_years' in cursor.calls[0][0]
    assert 'ORDER BY s.semester_number' in cursor.calls[0][0]
    assert cursor.calls[1] == ('SELECT * FROM classes ORDER BY display_order, name', None)
    assert cursor.calls[2][1] == (2, 1, 'Odd', '2026-06-01', '2026-12-01', 3, 1, 18.0, 30.0)
    assert cursor.calls[3][1][-1] == 9
    assert cursor.calls[4] == ('DELETE FROM semesters WHERE id = %s', (9,))


def test_create_does_not_clear_other_current_semesters(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(semester_service, '_connect', lambda: connection)
    assert semester_service.create_semester(2, 1, 'Odd', '2026-06-01', '2026-12-01', '', 1, 18.0, 30.0) is None
    assert len(connection.cursor_obj.calls) == 1
    assert connection.cursor_obj.calls[0][0].strip().startswith('INSERT')
    assert connection.dictionary is False
    assert connection.actions == ['commit', 'close']


def test_change_updates_one_row(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(semester_service, '_connect', lambda: connection)
    semester_service.change_semester(9, 2, 2, 'Even', '2027-01-01', '2027-05-31', '4', 1, '18', '30')
    assert len(connection.cursor_obj.calls) == 1
    assert connection.cursor_obj.calls[0][1] == (2, 2, 'Even', '2027-01-01', '2027-05-31', '4', 1, '18', '30', 9)


def test_failed_delete_rolls_back(monkeypatch):
    connection = _Connection(fail_on='DELETE')
    monkeypatch.setattr(semester_service, '_connect', lambda: connection)
    assert semester_service.remove_semester(9) == 'semester locked'
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True


def test_list_normalizes_credits_and_dates(monkeypatch):
    rows = [{
        'min_credits': Decimal('18.0'),
        'max_credits': Decimal('30.0'),
        'start_date': date(2026, 6, 1),
        'end_date': date(2026, 12, 1),
    }]
    connection = _Connection(results=[rows, [{'id': 2}], [{'id': 3}]])
    monkeypatch.setattr(semester_service, '_connect', lambda: connection)
    semesters, years, classes = semester_service.list_semesters()
    assert semesters[0]['min_credits'] == 18.0
    assert semesters[0]['max_credits'] == 30.0
    assert semesters[0]['start_date'] == '2026-06-01'
    assert semesters[0]['end_date'] == '2026-12-01'
    assert years == [{'id': 2}]
    assert classes == [{'id': 3}]
    assert connection.dictionary is True
    assert 'ORDER BY start_date DESC' in connection.cursor_obj.calls[1][0]


def test_later_credit_values_are_still_normalized_after_a_date_error(monkeypatch):
    rows = [
        {'min_credits': Decimal('1'), 'max_credits': Decimal('2'), 'start_date': _BadDate(), 'end_date': None},
        {'min_credits': Decimal('18.5'), 'max_credits': Decimal('24')},
    ]
    connection = _Connection(results=[rows, [], []])
    monkeypatch.setattr(semester_service, '_connect', lambda: connection)
    semesters, _years, _classes = semester_service.list_semesters()
    assert semesters[1]['min_credits'] == 18.5
    assert semesters[1]['max_credits'] == 24.0
