"""Subject filters, credit rules, and the two semester checks. No live database."""

from decimal import Decimal

import pytest

from data_access.subjects import fetch_subjects
from services import subjects as subject_service


class _Cursor:
    def __init__(self, fetchone_rows=None, fetchall_rows=None, fail_on=None):
        self.fetchone_rows = list(fetchone_rows or [])
        self.fetchall_rows = list(fetchall_rows or [])
        self.fail_on = fail_on
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError('subject locked')
        self.calls.append((' '.join(sql.split()), params))

    def fetchone(self):
        if self.fetchone_rows:
            return self.fetchone_rows.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_rows:
            return self.fetchall_rows.pop(0)
        return []

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, fetchone_rows=None, fetchall_rows=None, fail_on=None, dictionary_default=False):
        self.cursor_obj = _Cursor(fetchone_rows, fetchall_rows, fail_on)
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


def _saved_values(connection):
    return connection.cursor_obj.calls[-1][1]


def test_subject_filters_only_add_class_and_course_clauses():
    cursor = _Cursor(fetchall_rows=[[]])
    fetch_subjects(cursor, None, None)
    fetch_subjects(cursor, 3, None)
    fetch_subjects(cursor, None, 5)
    fetch_subjects(cursor, 3, 5)
    assert 'WHERE' not in cursor.calls[0][0]
    assert cursor.calls[0][1] == ()
    assert 'fa.faculty_id = f.user_id' in cursor.calls[0][0]
    assert 'WHERE s.class_id = %s' in cursor.calls[1][0]
    assert 'course_id' not in cursor.calls[1][0].split('WHERE', 1)[1]
    assert cursor.calls[1][1] == (3,)
    assert cursor.calls[2][1] == (5,)
    assert 'WHERE s.class_id = %s AND s.course_id = %s' in cursor.calls[3][0]
    assert cursor.calls[3][1] == (3, 5)


def test_list_converts_decimal_numbers_and_keeps_query_order(monkeypatch):
    subjects = [{'credits': Decimal('3.0'), 'marks': '100', 'theory_marks': None}]
    connection = _Connection(fetchall_rows=[subjects, [{'id': 1}], [{'id': 2}], [{'id': 3}]])
    monkeypatch.setattr(subject_service, '_connect', lambda: connection)
    rows, courses, classes, semesters = subject_service.list_subjects(0, None)
    assert rows[0]['credits'] == 3.0
    assert rows[0]['marks'] == '100'
    assert rows[0]['theory_marks'] is None
    assert courses == [{'id': 1}]
    assert classes == [{'id': 2}]
    assert semesters == [{'id': 3}]
    assert connection.dictionary is True
    assert connection.cursor_obj.calls[1][0] == 'SELECT * FROM courses WHERE is_active = TRUE ORDER BY name'
    assert connection.cursor_obj.calls[2][0] == 'SELECT * FROM classes ORDER BY display_order'
    assert connection.cursor_obj.calls[3][0] == 'SELECT * FROM semesters ORDER BY semester_number'
    assert 'WHERE' not in connection.cursor_obj.calls[0][0]


def test_new_subject_uses_the_program_limit_and_theory_mode(monkeypatch):
    missing = _Connection(fetchone_rows=[None])
    monkeypatch.setattr(subject_service, '_connect', lambda: missing)
    assert subject_service.create_subject(
        'Math', 'M1', 9, None, None, 'Core', 'Theory', 3, 3, 1, 100, 70, 30, 3, 0, 0, '', '',
    ) == 'Invalid course selected'
    assert missing.actions == ['rollback', 'close']
    assert missing.dictionary is True

    limited = _Connection(fetchone_rows=[
        {'name': 'Civil Engineering', 'program': 'UG', 'total_semesters': 0},
        {'semester_number': 9},
    ])
    monkeypatch.setattr(subject_service, '_connect', lambda: limited)
    assert subject_service.create_subject(
        'Math', 'M1', 9, None, 12, 'Core', 'Theory', 5, 3, 2, 100, 60, 40, 3, 2, 0, '', '',
    ) == 'Selected semester exceeds allowed semesters for the course (max 8).'
    assert 'SELECT name, program, total_semesters' in limited.cursor_obj.calls[0][0]

    saved = _Connection(fetchone_rows=[{'name': 'Arts', 'program': 'UG', 'total_semesters': 6}])
    monkeypatch.setattr(subject_service, '_connect', lambda: saved)
    assert subject_service.create_subject(
        'Math', 'M1', 9, None, None, 'Core', 'Theory', 5, 3, 2, 100, 60, 40, 3, 2, 0, '', '',
    ) is None
    values = _saved_values(saved)
    assert values[7:13] == (3.0, 3, 0.0, 60, 60, 0)
    assert saved.actions == ['commit', 'close']


def test_edit_uses_the_stored_semester_total(monkeypatch):
    connection = _Connection(fetchone_rows=[
        {'program': 'UG', 'total_semesters': 6, 'name': 'Civil Engineering'},
        {'semester_number': 7},
    ])
    monkeypatch.setattr(subject_service, '_connect', lambda: connection)
    message = subject_service.change_subject(
        4, 'Math', 'M1', 9, None, 8, 'Core', 'Practical', 4, 1, 3, 50, 10, 40, 1, 3, 0, '', '',
    )
    assert message == 'Selected semester exceeds total semesters for the course (6).'
    assert connection.cursor_obj.calls[0][0] == 'SELECT program, total_semesters FROM courses WHERE id = %s'
    assert connection.actions == ['rollback', 'close']


def test_failed_delete_rolls_back_on_a_plain_cursor(monkeypatch):
    connection = _Connection(fail_on='DELETE')
    monkeypatch.setattr(subject_service, '_connect', lambda: connection)
    assert subject_service.remove_subject(4) == 'subject locked'
    assert connection.dictionary is False
    assert connection.actions == ['rollback', 'close']
    assert connection.cursor_obj.closed is True
