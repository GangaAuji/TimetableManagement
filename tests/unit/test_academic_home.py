"""Academic home counts. No live database."""

from services import academic_home as home


class _Cursor:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
        self.closed = False
        self._reads = 0

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError('home failed')
        self.calls.append(' '.join(sql.split()))

    def fetchone(self):
        self._reads += 1
        if self._reads <= 7:
            return {'count': self._reads}
        if self._reads == 8:
            return {'id': 11, 'name': '2026'}
        return {'id': 22, 'semester_name': 'Odd'}

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, fail=False):
        self.cursor_obj = _Cursor(fail)
        self.dictionary = None
        self.closed = False

    def cursor(self, dictionary=False):
        self.dictionary = dictionary
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_home_reads_counts_before_the_current_rows(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(home, '_connect', lambda: connection)
    assert home.academic_home() == (1, 2, 3, 4, 5, 6, 7, {'id': 11, 'name': '2026'}, {'id': 22, 'semester_name': 'Odd'})
    assert connection.cursor_obj.calls == [
        'SELECT COUNT(*) as count FROM academic_years',
        'SELECT COUNT(*) as count FROM semesters',
        'SELECT COUNT(*) as count FROM courses',
        'SELECT COUNT(*) as count FROM subjects',
        'SELECT COUNT(*) as count FROM course_batches',
        'SELECT COUNT(*) as count FROM faculty_allocations',
        'SELECT COUNT(*) as count FROM departments',
        'SELECT * FROM academic_years WHERE is_current = TRUE ORDER BY start_date DESC LIMIT 1',
        'SELECT * FROM semesters WHERE is_current = TRUE ORDER BY start_date DESC LIMIT 1',
    ]
    assert connection.dictionary is True
    assert connection.cursor_obj.closed is True
    assert connection.closed is True


def test_failed_home_read_still_closes(monkeypatch):
    connection = _Connection(fail=True)
    monkeypatch.setattr(home, '_connect', lambda: connection)
    try:
        home.academic_home()
    except RuntimeError as exc:
        assert str(exc) == 'home failed'
    else:
        raise AssertionError('the home error was swallowed')
    assert connection.cursor_obj.closed is True
    assert connection.closed is True
