"""Faculty directory API. Rules match the existing admin faculty screen. No face data is returned."""

import re
from datetime import datetime

from flask import current_app, get_flashed_messages, request, session
from mysql.connector import IntegrityError
from werkzeug.security import generate_password_hash

from core.pagination import bounded_page_size, page_bounds
from extensions import get_db_connection
from api.web.access import (
    InputError,
    allowed,
    body,
    close,
    flag,
    iso_date,
    optional_text,
    permission_denied,
    reject_input,
    required_text,
    whole_number,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_clock, safe_count, safe_text

_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_CREATE_FIELDS = frozenset((
    'username', 'password', 'name', 'email', 'department_id', 'phone',
    'designation', 'employee_id', 'is_active',
))
_UPDATE_FIELDS = frozenset((
    'password', 'name', 'email', 'department_id', 'phone', 'designation', 'is_active',
))
_MESSAGES = {
    'invalid_body': 'The faculty member could not be saved.',
    'faculty_name_invalid': 'Enter a name up to 100 characters.',
    'faculty_username_invalid': 'Enter a username up to 50 characters.',
    'faculty_password_invalid': 'Enter a password up to 128 characters.',
    'faculty_email_invalid': 'Enter a valid email address.',
    'faculty_phone_invalid': 'Phone must be 20 characters or fewer.',
    'faculty_designation_invalid': 'Designation must be 50 characters or fewer.',
    'faculty_employee_invalid': 'Employee ID must be 20 characters or fewer.',
    'faculty_department_invalid': 'Choose a department.',
    'faculty_username_taken': 'That username is already in use.',
    'faculty_email_taken': 'That email is already registered for a faculty member.',
    'faculty_employee_taken': 'That employee ID is already in use.',
    'faculty_search_invalid': 'Search must be 100 characters or fewer.',
    'faculty_ids_invalid': 'Choose at least one faculty member.',
    'faculty_not_found': 'That faculty member was not found.',
    'faculty_unavailable': 'The faculty list could not be loaded.',
    'faculty_absence_invalid': 'Enter a date and a reason up to 200 characters.',
    'faculty_absence_missing': 'That absence was not found.',
    'faculty_absence_processed': 'A processed absence cannot be deleted.',
    'faculty_proxy_missing': 'That proxy record was not found.',
}


def register_faculty_routes(blueprint):
    blueprint.add_url_rule('/faculty', 'faculty_list', _list, methods=['GET'])
    blueprint.add_url_rule('/faculty', 'faculty_create', _create, methods=['POST'])
    blueprint.add_url_rule('/faculty/deactivate', 'faculty_deactivate', _deactivate, methods=['POST'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>', 'faculty_detail', _detail, methods=['GET'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>', 'faculty_update', _update, methods=['PUT'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/sessions', 'faculty_sessions', _sessions, methods=['GET'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/absences', 'faculty_absences', _absences, methods=['GET'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/absences', 'faculty_absence_add', _add_absence, methods=['POST'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/absences/<int:absence_id>/approve', 'faculty_absence_approve', _approve_absence, methods=['POST'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/absences/<int:absence_id>/reject', 'faculty_absence_reject', _reject_absence, methods=['POST'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/absences/<int:absence_id>/delete', 'faculty_absence_delete', _delete_absence, methods=['POST'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/proxy', 'faculty_proxy', _proxy, methods=['GET'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/proxy/<int:proxy_id>/approve', 'faculty_proxy_approve', _approve_proxy, methods=['POST'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/proxy/<int:proxy_id>/reject', 'faculty_proxy_reject', _reject_proxy, methods=['POST'])


def _denied(permission_name):
    return permission_denied(permission_name, 'faculty_unavailable', _MESSAGES['faculty_unavailable'])


def _fail(code, status=400):
    return json_error(_MESSAGES.get(code, 'The faculty member could not be saved.'), status, code)


def _email(value):
    text = required_text(value, 100, 'faculty_email_invalid')
    if not _EMAIL.match(text):
        raise InputError('faculty_email_invalid')
    return text


def _password(value, required):
    if not required and value in (None, ''):
        return None
    if not isinstance(value, str) or _CONTROL.search(value) or not value.strip() or len(value) > 128:
        raise InputError('faculty_password_invalid')
    return value


def _accessible_ids():
    role = session.get('role')
    if role in ('Super Admin', 'Admin'):
        return None
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if session.get('is_hod') and session.get('department_id'):
            cursor.execute('SELECT id FROM faculty WHERE department_id = %s', (session.get('department_id'),))
            return [row['id'] for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT DISTINCT up.department_id
            FROM user_permissions up
            JOIN permissions p ON up.permission_id = p.id
            WHERE up.user_id = %s
              AND p.name IN ('view_faculty', 'edit_faculty', 'add_faculty', 'delete_faculty')
              AND up.department_id IS NOT NULL
              AND up.is_active = TRUE
            """,
            (session.get('user_id'),),
        )
        department_ids = [row['department_id'] for row in cursor.fetchall()]
        if not department_ids:
            return []
        placeholders = ','.join(['%s'] * len(department_ids))
        cursor.execute(
            f'SELECT id FROM faculty WHERE department_id IN ({placeholders})',
            tuple(department_ids),
        )
        return [row['id'] for row in cursor.fetchall()]
    finally:
        close(cursor, connection)


def _scope_clause(scope, alias='f'):
    if scope is None:
        return '', []
    if not scope:
        return f' AND {alias}.id = -1', []
    placeholders = ','.join(['%s'] * len(scope))
    return f' AND {alias}.id IN ({placeholders})', list(scope)


def _in_scope(faculty_id, scope):
    return scope is None or faculty_id in scope


def _department(cursor, value):
    department_id = whole_number(value, 1000000, 'faculty_department_invalid', lower=1)
    cursor.execute('SELECT id FROM departments WHERE id = %s', (department_id,))
    if not cursor.fetchone():
        raise InputError('faculty_department_invalid')
    return department_id


def _public(row, include_username=False):
    item = {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 100),
        'email': safe_text(row.get('email'), 100),
        'phone': safe_text(row.get('phone') or '', 20),
        'employee_id': safe_text(row.get('employee_id') or '', 20),
        'designation': safe_text(row.get('designation') or '', 50),
        'department_id': safe_count(row.get('department_id')),
        'department_name': safe_text(row.get('department_name') or '', 100),
        'is_active': bool(row.get('is_active')),
    }
    if include_username or 'username' in row:
        item['username'] = safe_text(row.get('username') or '', 50)
    return item


def _permissions():
    return {
        'add': allowed('faculty_add_faculty'),
        'change': allowed('faculty_change_faculty'),
        'delete': allowed('faculty_delete_faculty'),
        'invite': allowed('users_add_user'),
    }


_FACULTY_SORTS = {
    'name': 'f.name',
    'email': 'f.email',
    'designation': 'f.designation',
    'department': 'd.name',
    'username': 'u.username',
}


def _optional_search(name):
    raw = request.args.get(name, '')
    if raw in ('', None):
        return ''
    if not isinstance(raw, str) or _CONTROL.search(raw) or len(raw) > 100:
        raise InputError('faculty_search_invalid')
    return raw.strip()


def _filters():
    search = _optional_search('search')
    department_raw = request.args.get('department', '')
    department_id = None
    if department_raw not in ('', None):
        if not str(department_raw).isdigit():
            raise InputError('faculty_department_invalid')
        department_id = whole_number(int(department_raw), 1000000, 'faculty_department_invalid', lower=1)
    page_raw = request.args.get('page', '1')
    page = 1 if not str(page_raw).isdigit() else min(max(int(page_raw), 1), 10000)
    sort = request.args.get('sort', 'name')
    if sort not in _FACULTY_SORTS:
        sort = 'name'
    order = 'DESC' if request.args.get('order', 'ASC').upper() == 'DESC' else 'ASC'
    fields = {
        'name': _optional_search('name'),
        'email': _optional_search('email'),
        'employee': _optional_search('employee'),
        'designation': _optional_search('designation'),
        'username': _optional_search('username'),
    }
    return search, department_id, page, bounded_page_size(request.args.get('per_page')), sort, order, fields


def _list():
    denied = _denied('faculty_view_faculty')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        search, department_id, page, per_page, sort, order, fields = _filters()
        scope = _accessible_ids()
        scope_sql, scope_params = _scope_clause(scope)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        where = ["u.role = 'Teacher'", "COALESCE(u.status, 'active') = 'active'"]
        params = []
        if search:
            where.append('(f.name LIKE %s OR f.email LIKE %s OR f.employee_id LIKE %s)')
            term = f'%{search}%'
            params.extend((term, term, term))
        if department_id is not None:
            where.append('f.department_id = %s')
            params.append(department_id)
        for key, column in (
            ('name', 'f.name'),
            ('email', 'f.email'),
            ('employee', 'f.employee_id'),
            ('designation', 'f.designation'),
            ('username', 'u.username'),
        ):
            value = fields[key]
            if value:
                where.append(f'{column} LIKE %s')
                params.append(f'%{value}%')
        clause = ' WHERE ' + ' AND '.join(where) + scope_sql
        bound = tuple(params) + tuple(scope_params)
        base = """
            FROM faculty f
            LEFT JOIN departments d ON f.department_id = d.id
            LEFT JOIN users u ON f.user_id = u.id
        """
        cursor.execute(f'SELECT COUNT(f.id) AS total {base} {clause}', bound)
        total = safe_count(cursor.fetchone()['total'])
        offset, total_pages = page_bounds(page, per_page, total)
        cursor.execute(
            f"""
            SELECT f.id, f.name, f.email, u.username, f.phone, f.is_active, f.employee_id,
                   f.designation, f.department_id, d.name AS department_name
            {base} {clause}
            ORDER BY {_FACULTY_SORTS[sort]} {order}
            LIMIT %s OFFSET %s
            """,
            bound + (per_page, offset),
        )
        faculty = [_public(row, include_username=True) for row in cursor.fetchall()]
        count_base = """
            FROM faculty f
            LEFT JOIN users u ON f.user_id = u.id
            WHERE u.role = 'Teacher' AND COALESCE(u.status, 'active') = 'active'
        """
        cursor.execute(f'SELECT COUNT(f.id) AS total {count_base} AND f.is_active = 1 {scope_sql}', tuple(scope_params))
        total_active = safe_count(cursor.fetchone()['total'])
        cursor.execute(f'SELECT COUNT(f.id) AS total {count_base} AND f.is_active = 0 {scope_sql}', tuple(scope_params))
        total_inactive = safe_count(cursor.fetchone()['total'])
        cursor.execute('SELECT id, name FROM departments ORDER BY name')
        departments = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
        return json_ok({
            'faculty': faculty,
            'page': page,
            'total_pages': total_pages,
            'total': total,
            'total_active': total_active,
            'total_inactive': total_inactive,
            'departments': departments,
            'permissions': _permissions(),
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Faculty list failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')
    finally:
        close(cursor, connection)


def _detail(faculty_id):
    denied = _denied('faculty_view_faculty')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        if not _in_scope(faculty_id, _accessible_ids()):
            return _fail('faculty_not_found', 404)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT f.id, f.name, f.email, f.department_id, u.username, f.phone,
                   f.employee_id, f.designation, f.is_active
            FROM faculty f
            LEFT JOIN users u ON f.user_id = u.id
            WHERE f.id = %s
            """,
            (faculty_id,),
        )
        row = cursor.fetchone()
        if not row:
            return _fail('faculty_not_found', 404)
        return json_ok(_public(row, include_username=True))
    except Exception:
        current_app.logger.exception('Faculty detail failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')
    finally:
        close(cursor, connection)


def _create():
    denied = _denied('faculty_add_faculty')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(_CREATE_FIELDS)
        username = required_text(payload.get('username'), 50, 'faculty_username_invalid')
        password = _password(payload.get('password'), True)
        name = required_text(payload.get('name'), 100, 'faculty_name_invalid')
        email = _email(payload.get('email'))
        phone = optional_text(payload.get('phone'), 20, 'faculty_phone_invalid') or None
        designation = optional_text(payload.get('designation'), 50, 'faculty_designation_invalid') or None
        employee_id = optional_text(payload.get('employee_id'), 20, 'faculty_employee_invalid')
        is_active = flag(payload.get('is_active'))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        department_id = _department(cursor, payload.get('department_id'))
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            return _fail('faculty_username_taken')
        cursor.execute('SELECT id FROM faculty WHERE email = %s', (email,))
        if cursor.fetchone():
            return _fail('faculty_email_taken')
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, 'Teacher')",
            (username, generate_password_hash(password)),
        )
        user_id = cursor.lastrowid
        if not employee_id:
            employee_id = f'EMP{datetime.now().year}{user_id:06d}'
        cursor.execute(
            """
            INSERT INTO faculty (id, user_id, name, email, department_id, employee_id, phone, designation, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, user_id, name, email, department_id, employee_id, phone, designation, 1 if is_active else 0),
        )
        connection.commit()
        return json_ok({'id': safe_count(user_id)}, 201)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Faculty create conflict')
        return _fail('faculty_employee_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Faculty create failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')
    finally:
        close(cursor, connection)


def _update(faculty_id):
    denied = _denied('faculty_change_faculty')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        if not _in_scope(faculty_id, _accessible_ids()):
            return _fail('faculty_not_found', 404)
        payload = body(_UPDATE_FIELDS)
        name = required_text(payload.get('name'), 100, 'faculty_name_invalid')
        email = _email(payload.get('email'))
        phone = optional_text(payload.get('phone'), 20, 'faculty_phone_invalid') or None
        designation = optional_text(payload.get('designation'), 50, 'faculty_designation_invalid') or None
        password = _password(payload.get('password'), False)
        is_active = flag(payload.get('is_active'))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        department_id = _department(cursor, payload.get('department_id'))
        cursor.execute('SELECT user_id FROM faculty WHERE id = %s', (faculty_id,))
        current = cursor.fetchone()
        if not current:
            return _fail('faculty_not_found', 404)
        cursor.execute('SELECT id FROM faculty WHERE email = %s AND id != %s', (email, faculty_id))
        if cursor.fetchone():
            return _fail('faculty_email_taken')
        cursor.execute(
            """
            UPDATE faculty
            SET name = %s, email = %s, department_id = %s, phone = %s, designation = %s, is_active = %s
            WHERE id = %s
            """,
            (name, email, department_id, phone, designation, 1 if is_active else 0, faculty_id),
        )
        if password and current.get('user_id'):
            cursor.execute(
                'UPDATE users SET password = %s WHERE id = %s AND role = %s',
                (generate_password_hash(password), current['user_id'], 'Teacher'),
            )
        connection.commit()
        return json_ok({'id': safe_count(faculty_id)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Faculty update conflict')
        return _fail('faculty_email_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Faculty update failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')
    finally:
        close(cursor, connection)


def _ids(value):
    if not isinstance(value, list) or not value or len(value) > 100:
        raise InputError('faculty_ids_invalid')
    ids = []
    for item in value:
        number = whole_number(item, 1000000, 'faculty_ids_invalid', lower=1)
        if number not in ids:
            ids.append(number)
    return ids


def _deactivate():
    denied = _denied('faculty_delete_faculty')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(frozenset(('ids',)))
        ids = _ids(payload.get('ids'))
        scope = _accessible_ids()
        if any(not _in_scope(faculty_id, scope) for faculty_id in ids):
            return _fail('faculty_not_found', 404)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        placeholders = ','.join(['%s'] * len(ids))
        cursor.execute(f'SELECT id, user_id FROM faculty WHERE id IN ({placeholders})', tuple(ids))
        rows = cursor.fetchall()
        if len(rows) != len(ids):
            return _fail('faculty_not_found', 404)
        cursor.execute(f'UPDATE faculty SET is_active = 0 WHERE id IN ({placeholders})', tuple(ids))
        user_ids = [row['user_id'] for row in rows if row.get('user_id')]
        if user_ids:
            user_placeholders = ','.join(['%s'] * len(user_ids))
            cursor.execute(
                f"UPDATE users SET status = 'inactive' WHERE id IN ({user_placeholders}) AND role = 'Teacher'",
                tuple(user_ids),
            )
        connection.commit()
        return json_ok({'deactivated': len(rows)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Faculty deactivate failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')
    finally:
        close(cursor, connection)


def _sessions(faculty_id):
    denied = _denied('faculty_view_faculty')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT id, name, user_id FROM faculty WHERE id = %s', (faculty_id,))
        faculty = cursor.fetchone()
        if not faculty:
            return json_error(_MESSAGES['faculty_not_found'], 404, 'faculty_not_found')
        cursor.execute(
            """
            SELECT t.day_of_week, t.start_time, t.end_time, s.name AS subject_name,
                   c.name AS class_name, d.name AS division_name, r.room_number
            FROM timetable t
            JOIN subjects s ON s.id = t.subject_id
            JOIN classes c ON c.id = t.class_id
            JOIN divisions d ON d.id = t.division_id
            LEFT JOIN rooms r ON r.id = t.room_id
            WHERE t.faculty_id = %s AND COALESCE(t.is_active, 1) = 1
            ORDER BY FIELD(t.day_of_week,'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'), t.start_time
            """,
            (faculty['user_id'],),
        )
        sessions = [
            {
                'day': safe_text(row.get('day_of_week'), 12),
                'start_time': safe_clock(row.get('start_time')),
                'end_time': safe_clock(row.get('end_time')),
                'subject': safe_text(row.get('subject_name'), 100),
                'class_name': safe_text(row.get('class_name'), 100),
                'division_name': safe_text(row.get('division_name'), 50),
                'room': safe_text(row.get('room_number') or '', 20),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'name': safe_text(faculty.get('name'), 100), 'sessions': sessions})
    except Exception:
        current_app.logger.exception('Faculty sessions failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')
    finally:
        close(cursor, connection)


def absence_row(row):
    return {
        'id': safe_count(row.get('id')),
        'date': safe_text(row.get('absence_date'), 10),
        'reason': safe_text(row.get('reason') or '', 200),
        'status': safe_text(row.get('status') or '', 20),
    }


def proxy_row(row):
    return {
        'id': safe_count(row.get('id')),
        'date': safe_text(row.get('absence_date'), 10),
        'day': safe_text(row.get('day') or '', 12),
        'start_time': safe_text(row.get('start_time') or '', 8),
        'end_time': safe_text(row.get('end_time') or '', 8),
        'subject': safe_text(row.get('subject') or '', 100),
        'original_faculty': safe_text(row.get('original_faculty') or '', 100),
        'proxy_faculty': safe_text(row.get('proxy_faculty') or '', 100),
        'status': safe_text(row.get('status') or '', 20),
        'approval': safe_text(row.get('approval_status') or '', 20),
    }


def _absences(faculty_id):
    denied = _denied('faculty_view_faculty')
    if denied:
        return denied
    try:
        from services.faculty_admin import load_faculty_absences
        return json_ok({
            'absences': [absence_row(row) for row in load_faculty_absences(faculty_id)],
            'can_change': allowed('faculty_change_faculty'),
            'can_delete': allowed('faculty_delete_faculty'),
        })
    except Exception:
        current_app.logger.exception('Faculty absences failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')


def _add_absence(faculty_id):
    denied = _denied('faculty_change_faculty')
    if denied:
        return denied
    try:
        from services.faculty_admin import add_faculty_absence
        payload = body(frozenset(('date', 'reason')))
        absence_date = iso_date(payload.get('date'), 'faculty_absence_invalid')
        reason = optional_text(payload.get('reason'), 200, 'faculty_absence_invalid')
        if add_faculty_absence(faculty_id, absence_date, reason) == 'date':
            return json_error(_MESSAGES['faculty_absence_invalid'], 400, 'faculty_absence_invalid')
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Faculty absence save failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')


def _approve_absence(faculty_id, absence_id):
    denied = _denied('faculty_change_faculty')
    if denied:
        return denied
    try:
        from services.faculty_admin import approve_faculty_absence
        body(frozenset())
        result = approve_faculty_absence(faculty_id, absence_id)
        get_flashed_messages()
        if result == 'missing':
            return json_error(_MESSAGES['faculty_absence_missing'], 404, 'faculty_absence_missing')
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        get_flashed_messages()
        current_app.logger.exception('Faculty absence approval failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')


def _reject_absence(faculty_id, absence_id):
    denied = _denied('faculty_change_faculty')
    if denied:
        return denied
    try:
        from services.faculty_admin import reject_faculty_absence
        body(frozenset())
        reject_faculty_absence(faculty_id, absence_id)
        get_flashed_messages()
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        get_flashed_messages()
        current_app.logger.exception('Faculty absence rejection failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')


def _delete_absence(faculty_id, absence_id):
    denied = _denied('faculty_delete_faculty')
    if denied:
        return denied
    try:
        from services.faculty_admin import remove_faculty_absence
        body(frozenset())
        result = remove_faculty_absence(faculty_id, absence_id)
        if result == 'missing':
            return json_error(_MESSAGES['faculty_absence_missing'], 404, 'faculty_absence_missing')
        if result == 'processed':
            return json_error(_MESSAGES['faculty_absence_processed'], 400, 'faculty_absence_processed')
        return json_ok({'deleted': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Faculty absence delete failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')


def _proxy(faculty_id):
    denied = _denied('faculty_view_faculty')
    if denied:
        return denied
    try:
        from services.faculty_admin import load_faculty_proxy_log
        return json_ok({
            'entries': [proxy_row(row) for row in load_faculty_proxy_log(faculty_id)],
            'can_change': allowed('faculty_change_faculty'),
        })
    except Exception:
        current_app.logger.exception('Faculty proxy log failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')


def _approve_proxy(faculty_id, proxy_id):
    denied = _denied('faculty_change_faculty')
    if denied:
        return denied
    try:
        from services.faculty_admin import approve_faculty_proxy
        body(frozenset())
        result, _chosen = approve_faculty_proxy(faculty_id, proxy_id, None, session.get('user_id'))
        get_flashed_messages()
        if result in ('missing', 'not_found'):
            return json_error(_MESSAGES['faculty_proxy_missing'], 404, 'faculty_proxy_missing')
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        get_flashed_messages()
        current_app.logger.exception('Faculty proxy approval failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')


def _reject_proxy(faculty_id, proxy_id):
    denied = _denied('faculty_change_faculty')
    if denied:
        return denied
    try:
        from services.faculty_admin import reject_faculty_proxy
        body(frozenset())
        result = reject_faculty_proxy(faculty_id, proxy_id, session.get('user_id'))
        get_flashed_messages()
        if result == 'missing':
            return json_error(_MESSAGES['faculty_proxy_missing'], 404, 'faculty_proxy_missing')
        return json_ok({'saved': True})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        get_flashed_messages()
        current_app.logger.exception('Faculty proxy rejection failed')
        return json_error(_MESSAGES['faculty_unavailable'], 500, 'faculty_unavailable')
