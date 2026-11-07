"""format_hhmm keeps the previous clock-string behavior."""

from datetime import datetime, time, timedelta

from app_factory import format_time_filter
from routes.admin_utils import format_time as admin_format_time
from routes.faculty.attendance import format_time as attendance_format_time
from routes.faculty.teacher import format_time as teacher_format_time
from routes.students.student import format_time as student_format_time
from utils.dates import format_hhmm


def test_format_hhmm_matches_previous_rules():
    assert format_hhmm(None) == ''
    assert format_hhmm(timedelta(hours=9, minutes=5)) == '09:05'
    assert format_hhmm(timedelta(hours=26, minutes=5, seconds=59)) == '26:05'
    assert format_hhmm(time(14, 7)) == '14:07'
    assert format_hhmm(datetime(2026, 10, 26, 8, 3, 45)) == '08:03'
    assert format_hhmm('09:00:00') == '09:00:00'
    assert format_hhmm('09:00:00', keep_string=True) == '09:00:00'
    assert format_hhmm(5) == '5'


def test_existing_format_time_names_delegate():
    value = timedelta(hours=1, minutes=2)
    assert admin_format_time(value) == '01:02'
    assert teacher_format_time(value) == '01:02'
    assert attendance_format_time(value) == '01:02'
    assert format_time_filter(value) == '01:02'
    assert student_format_time('09:00:00') == '09:00:00'
    assert student_format_time(None) == ''
