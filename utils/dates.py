"""Clock formatting shared by admin, teacher, and student views."""

from datetime import timedelta
from typing import Any


def format_hhmm(value: Any, *, keep_string: bool = False) -> str:
    """Format a time or timedelta as HH:MM."""
    if value is None:
        return ''
    if keep_string and isinstance(value, str):
        return value
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}'
    if hasattr(value, 'strftime'):
        return value.strftime('%H:%M')
    return str(value)
