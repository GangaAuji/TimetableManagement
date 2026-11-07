"""Overlap checks keep the previous boundary and inactive-row rules."""

from datetime import time

from academic_rules.clashes import faculty_timetable_free, times_overlap
from routes.admin_utils import _is_faculty_free
from routes.faculty.teacher import is_faculty_available


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.sql = ''
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self.row


def test_times_overlap_uses_the_previous_boundaries():
    morning = (time(9, 0), time(10, 0))
    later = (time(10, 0), time(11, 0))
    overlap = (time(9, 30), time(10, 30))
    assert times_overlap(*morning, *later) is False
    assert times_overlap(*later, *morning) is False
    assert times_overlap(*morning, *overlap) is True
    assert times_overlap(*morning, *morning) is True


def test_faculty_free_check_leaves_inactive_rows_in_place():
    busy = _Cursor({'x': 1})
    assert faculty_timetable_free(busy, 4, 'Monday', time(9, 0), time(10, 0), active_only=False) is False
    assert 'is_active' not in busy.sql
    assert busy.params == (4, 'Monday', time(9, 0), time(10, 0))

    free = _Cursor(None)
    assert _is_faculty_free(free, 4, 'Monday', time(9, 0), time(10, 0)) is True
    assert is_faculty_available(free, 4, 'Monday', time(9, 0), time(10, 0)) is True
    assert 'is_active' not in free.sql

    active = _Cursor(None)
    assert faculty_timetable_free(active, 4, 'Monday', time(9, 0), time(10, 0), active_only=True) is True
    assert 'COALESCE(is_active, 1) = 1' in active.sql
