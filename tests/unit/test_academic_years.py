"""Academic year SQL and save flow. No live database."""

import pytest

from data_access.academic_years import (
    clear_current_academic_years,
    delete_academic_year,
    fetch_academic_years,
    insert_academic_year,
    update_academic_year,
)
from services import academic_years as years


class _Cursor:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError('year locked')
        self.calls.append((sql, params))

    def fetchall(self):
        return [{'id': 1, 'name': '2025-26'}]

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


def test_year_queries_keep_their_sql():
    cursor = _Cursor()
    assert fetch_academic_years(cursor) == [{'id': 1, 'name': '2025-26'}]
    clear_current_academic_years(cursor)
    clear_current_academic_years(cursor, except_id=4)
    insert_academic_year(cursor, '2026-27', '2026-06-01', '2027-05-31', 1, 'Next')
    update_academic_year(cursor, 4, '2026-27', '2026-06-01', '2027-05-31', 0, '')
    delete_academic_year(cursor, 4)
    assert cursor.calls[0][0].strip().startswith('SELECT * FROM academic_years')
    assert 'ORDER BY start_date DESC' in cursor.calls[0][0]
    assert cursor.calls[1] == ('UPDATE academic_years SET is_current = 0', None)
    assert cursor.calls[2] == ('UPDATE academic_years SET is_current = 0 WHERE id != %s', (4,))
    assert cursor.calls[3][1] == ('2026-27', '2026-06-01', '2027-05-31', 1, 'Next')
    assert cursor.calls[4][1] == ('2026-27', '2026-06-01', '2027-05-31', 0, '', 4)
    assert cursor.calls[5] == ('DELETE FROM academic_years WHERE id = %s', (4,))


def test_create_clears_the_current_year_only_when_marked_current(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(years, '_connect', lambda: connection)
    assert years.create_academic_year('2026-27', '2026-06-01', '2027-05-31', 0, '') is None
    assert connection.cursor_obj.calls[0][0].strip().startswith('INSERT')
    assert connection.actions == ['commit', 'close']
    assert connection.dictionary is False

    current = _Connection()
    monkeypatch.setattr(years, '_connect', lambda: current)
    years.create_academic_year('2026-27', '2026-06-01', '2027-05-31', 1, '')
    assert current.cursor_obj.calls[0] == ('UPDATE academic_years SET is_current = 0', None)
    assert current.cursor_obj.calls[1][0].strip().startswith('INSERT')


def test_change_leaves_other_years_unless_this_one_is_current(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(years, '_connect', lambda: connection)
    years.change_academic_year(4, '2026-27', '2026-06-01', '2027-05-31', 1, 'Next')
    assert connection.cursor_obj.calls[0][1] == (4,)
    assert connection.cursor_obj.calls[1][1][-1] == 4
    assert connection.actions[0] == 'commit'


def test_failed_delete_rolls_back_and_returns_the_error(monkeypatch):
    connection = _Connection(fail_on='DELETE')
    monkeypatch.setattr(years, '_connect', lambda: connection)
    assert years.remove_academic_year(4) == 'year locked'
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True


def test_list_uses_a_dictionary_cursor(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(years, '_connect', lambda: connection)
    assert years.list_academic_years() == [{'id': 1, 'name': '2025-26'}]
    assert connection.dictionary is True
    assert connection.actions == ['close']


def test_list_still_closes_when_the_read_fails(monkeypatch):
    connection = _Connection(fail_on='SELECT')
    monkeypatch.setattr(years, '_connect', lambda: connection)
    with pytest.raises(RuntimeError, match='year locked'):
        years.list_academic_years()
    assert connection.actions == ['close']
