"""Academic dropdown lookups. No live database."""

from services import academic_lookups as lookups


class _Cursor:
    def __init__(self, rows=None, fail=False):
        self.rows = rows if rows is not None else [{'id': 1}]
        self.fail = fail
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError('lookup failed')
        self.calls.append((' '.join(sql.split()), params))

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, rows=None, fail=False):
        self.cursor_obj = _Cursor(rows, fail)
        self.dictionary = None
        self.closed = False

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        return self.cursor_obj

    def close(self):
        self.closed = True


def _patch(monkeypatch, connection):
    monkeypatch.setattr(lookups, '_connect', lambda: connection)


def test_courses_by_department_keeps_the_active_filter(monkeypatch):
    connection = _Connection([{'id': 4, 'name': 'Civil'}])
    _patch(monkeypatch, connection)
    assert lookups.courses_for_department(2) == [{'id': 4, 'name': 'Civil'}]
    sql, params = connection.cursor_obj.calls[0]
    assert sql == (
        'SELECT id, name, code, program FROM courses '
        'WHERE department_id = %s AND is_active = TRUE ORDER BY name'
    )
    assert params == (2,)
    assert connection.dictionary is True
    assert connection.cursor_obj.closed is True
    assert connection.closed is True


def test_remaining_lookups_keep_their_queries(monkeypatch):
    expected = [
        (
            lookups.subjects_for_course,
            8,
            'SELECT id, name, course_code, credits, course_type FROM subjects '
            'WHERE course_id = %s ORDER BY name',
        ),
        (
            lookups.faculty_for_department,
            3,
            'SELECT id, name, email, designation FROM faculty '
            'WHERE department_id = %s AND is_active = TRUE ORDER BY name',
        ),
        (
            lookups.semesters_for_year,
            5,
            'SELECT id, semester_number, semester_name, is_current FROM semesters '
            'WHERE academic_year_id = %s ORDER BY semester_number',
        ),
        (
            lookups.batches_for_course,
            6,
            'SELECT id, batch_name, start_year, end_year, current_semester FROM course_batches '
            'WHERE course_id = %s AND is_active = TRUE ORDER BY start_year DESC',
        ),
    ]
    for function, record_id, query in expected:
        connection = _Connection()
        _patch(monkeypatch, connection)
        assert function(record_id) == [{'id': 1}]
        assert connection.cursor_obj.calls == [(query, (record_id,))]


def test_failed_lookup_still_closes(monkeypatch):
    connection = _Connection(fail=True)
    _patch(monkeypatch, connection)
    try:
        lookups.faculty_for_department(3)
    except RuntimeError as exc:
        assert str(exc) == 'lookup failed'
    else:
        raise AssertionError('the lookup error was swallowed')
    assert connection.cursor_obj.closed is True
    assert connection.closed is True
