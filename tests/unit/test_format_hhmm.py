"""format_hhmm keeps the previous clock-string behavior."""

from datetime import datetime, time, timedelta

from app_factory import format_time_filter
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


def test_the_template_filter_delegates():
    value = timedelta(hours=1, minutes=2)
    assert format_time_filter(value) == '01:02'
