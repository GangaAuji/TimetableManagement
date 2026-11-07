"""Shared checks for JSON API writes and reads."""

import re
from datetime import date

from flask import current_app, request, session

from api.web.responses import json_error
from api.web.security import safe_count, safe_text
from security import check_user_permission

_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]')
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
PAGE_SIZES = frozenset((10, 25, 50, 100))


def page_window(max_page=10000):
    """Return the requested page and page size, limited to the shared list sizes."""
    page = safe_count(request.args.get('page') or 1)
    if page < 1 or page > max_page:
        page = 1
    per_page = safe_count(request.args.get('per_page') or 25)
    if per_page not in PAGE_SIZES:
        per_page = 25
    return page, per_page


class InputError(Exception):
    def __init__(self, code):
        self.code = code


def permission_denied(permission_name, unavailable_code, unavailable_message, *, log_message='Permission check failed', include_error=False):
    """Return a JSON denial, or None when the session may continue."""
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') == 'Super Admin':
        return None
    try:
        has_perm, _, _ = check_user_permission(session.get('user_id'), permission_name)
    except Exception as exc:
        if include_error:
            current_app.logger.exception(log_message, exc)
        else:
            current_app.logger.exception(log_message)
        return json_error(unavailable_message, 500, unavailable_code)
    if not has_perm:
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    return None


def allowed(permission_name):
    if session.get('role') == 'Super Admin':
        return True
    try:
        has_perm, _, _ = check_user_permission(session.get('user_id'), permission_name)
    except Exception:
        return False
    return bool(has_perm)


def reject_input(messages, code):
    return json_error(messages.get(code, 'The request could not be accepted.'), 400, code)


def body(fields):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - fields:
        raise InputError('invalid_body')
    return payload


def required_text(value, limit, code):
    if not isinstance(value, str) or _CONTROL_CHARS.search(value):
        raise InputError(code)
    text = value.strip()
    if not text or len(text) > limit:
        raise InputError(code)
    return text


def optional_text(value, limit, code):
    if value is None:
        return ''
    if not isinstance(value, str) or _CONTROL_CHARS.search(value):
        raise InputError(code)
    text = value.strip()
    if len(text) > limit:
        raise InputError(code)
    return text


def flag(value):
    if not isinstance(value, bool):
        raise InputError('invalid_body')
    return value


def iso_date(value, code, required=True):
    if value in (None, '') and not required:
        return None
    if not isinstance(value, str) or not _DATE.match(value):
        raise InputError(code)
    try:
        date.fromisoformat(value)
    except ValueError:
        raise InputError(code)
    return value


def whole_number(value, upper, code, lower=0):
    number = safe_count(value)
    if isinstance(value, bool) or number < lower or number > upper or safe_text(value, 8) != str(number):
        raise InputError(code)
    return number


def optional_id(value, code):
    if value in (None, '', 0):
        return None
    return whole_number(value, 1000000, code, lower=1)


def decimal_number(value, upper, code, lower=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(code)
    number = float(value)
    if number < lower or number > upper:
        raise InputError(code)
    return round(number, 1)


def as_date(value):
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()[:10]
    return safe_text(value, 10)


def as_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number < 0:
        return 0
    return round(number, 1)


def close(cursor, connection):
    if cursor is not None:
        cursor.close()
    if connection is not None:
        connection.close()
