"""Student directory API. Rules match the existing admin student screen."""

import re
from datetime import datetime

from flask import current_app, request, session
from mysql.connector import IntegrityError
from werkzeug.security import generate_password_hash

from core.pagination import bounded_page_size, page_bounds
from extensions import get_db_connection
from api.web.access import (
    InputError,
    allowed,
    body,
    close,
    optional_id,
    optional_text,
    permission_denied,
    reject_input,
    required_text,
    whole_number,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text

_CONTROL = re.compile(r'[\x00-\x1f\x7f]')
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_CREATE_FIELDS = frozenset((
    'username', 'password', 'name', 'email', 'phone', 'roll_number',
    'course_id', 'class_id', 'division_id',
))
_UPDATE_FIELDS = frozenset((
    'password', 'name', 'email', 'phone', 'roll_number',
    'course_id', 'class_id', 'division_id',
))
_SORTS = {
    'name': 's.name',
    'roll_number': 's.roll_number',
    'course': 'c.name',
    'class': 'cl.name',
    'email': 's.email',
}
_MESSAGES = {
    'invalid_body': 'The student could not be saved.',
    'student_name_invalid': 'Enter a student name up to 100 characters.',
    'student_username_invalid': 'Enter a username up to 50 characters.',
    'student_password_invalid': 'Enter a password up to 128 characters.',
    'student_email_invalid': 'Enter a valid email address.',
    'student_phone_invalid': 'Phone must be 20 characters or fewer.',
    'student_roll_invalid': 'Roll number must be 50 characters or fewer.',
    'student_course_invalid': 'Choose a course.',
    'student_class_invalid': 'Choose a valid class, or leave it empty.',
    'student_division_invalid': 'Choose a valid division, or leave it empty.',
    'student_username_taken': 'That username is already in use.',
    'student_email_taken': 'That email is already registered for a student.',
    'student_search_invalid': 'Search must be 100 characters or fewer.',
    'student_ids_invalid': 'Choose at least one student.',
    'student_not_found': 'That student was not found.',
    'students_unavailable': 'The student list could not be loaded.',
}

_LIST_FROM = """
    FROM students s
    LEFT JOIN users u ON s.user_id = u.id
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN classes cl ON s.class_id = cl.id
    LEFT JOIN divisions d ON s.division_id = d.id
"""


def register_student_routes(blueprint):
    blueprint.add_url_rule('/students', 'students_list', _list, methods=['GET'])
    blueprint.add_url_rule('/students', 'students_create', _create, methods=['POST'])
    blueprint.add_url_rule('/students/deactivate', 'students_deactivate', _deactivate, methods=['POST'])
    blueprint.add_url_rule('/students/<int:student_id>', 'students_detail', _detail, methods=['GET'])
    blueprint.add_url_rule('/students/<int:student_id>', 'students_update', _update, methods=['PUT'])


def _denied(permission_name):
    return permission_denied(permission_name, 'students_unavailable', _MESSAGES['students_unavailable'])


def _fail(code, status=400):
    return json_error(_MESSAGES.get(code, 'The student could not be saved.'), status, code)


def _email(value):
    text = required_text(value, 100, 'student_email_invalid')
    if not _EMAIL.match(text):
        raise InputError('student_email_invalid')
    return text


def _password(value, required):
    if not required and value in (None, ''):
        return None
    if not isinstance(value, str) or _CONTROL.search(value) or not value.strip() or len(value) > 128:
        raise InputError('student_password_invalid')
    return value


def _accessible_ids():
    """Same department rules as the existing student list. None means every student."""
    role = session.get('role')
    if role in ('Super Admin', 'Admin'):
        return None
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if session.get('is_hod') and session.get('department_id'):
            cursor.execute(
                """
                SELECT DISTINCT s.id
                FROM students s
                JOIN courses c ON s.course_id = c.id
                WHERE c.department_id = %s
                """,
                (session.get('department_id'),),
            )
            return [row['id'] for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT DISTINCT up.department_id
            FROM user_permissions up
            JOIN permissions p ON up.permission_id = p.id
            WHERE up.user_id = %s
              AND p.name IN ('view_students', 'edit_student', 'add_student', 'delete_student')
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
            f"""
            SELECT DISTINCT s.id
            FROM students s
            JOIN courses c ON s.course_id = c.id
            WHERE c.department_id IN ({placeholders})
            """,
            tuple(department_ids),
        )
        return [row['id'] for row in cursor.fetchall()]
    finally:
        close(cursor, connection)


def _scope_clause(scope):
    if scope is None:
        return '', []
    if not scope:
        return ' AND s.id = -1', []
    placeholders = ','.join(['%s'] * len(scope))
    return f' AND s.id IN ({placeholders})', list(scope)


def _in_scope(student_id, scope):
    return scope is None or student_id in scope


def _exists(cursor, table, row_id):
    cursor.execute(f'SELECT id FROM {table} WHERE id = %s', (row_id,))
    return cursor.fetchone() is not None


def _placement(cursor, payload):
    course_id = whole_number(payload.get('course_id'), 1000000, 'student_course_invalid', lower=1)
    class_id = optional_id(payload.get('class_id'), 'student_class_invalid')
    division_id = optional_id(payload.get('division_id'), 'student_division_invalid')
    if not _exists(cursor, 'courses', course_id):
        raise InputError('student_course_invalid')
    if class_id is not None and not _exists(cursor, 'classes', class_id):
        raise InputError('student_class_invalid')
    if division_id is not None and not _exists(cursor, 'divisions', division_id):
        raise InputError('student_division_invalid')
    return course_id, class_id, division_id


def _public(row, include_username=False):
    item = {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 100),
        'email': safe_text(row.get('email'), 100),
        'phone': safe_text(row.get('phone') or '', 20),
        'roll_number': safe_text(row.get('roll_number') or '', 50),
        'course_id': safe_count(row.get('course_id')),
        'class_id': safe_count(row.get('class_id')),
        'division_id': safe_count(row.get('division_id')),
        'course_name': safe_text(row.get('course_name') or '', 100),
        'class_name': safe_text(row.get('class_name') or '', 100),
        'division_name': safe_text(row.get('division_name') or '', 100),
    }
    if include_username:
        item['username'] = safe_text(row.get('username') or '', 50)
    return item


def _options(cursor):
    cursor.execute('SELECT id, name FROM courses ORDER BY name')
    courses = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
    cursor.execute('SELECT id, name FROM classes ORDER BY display_order, name')
    classes = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
    cursor.execute('SELECT id, name FROM divisions ORDER BY name')
    divisions = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 100)} for row in cursor.fetchall()]
    return courses, classes, divisions


def _permissions():
    return {
        'add': allowed('students_add_student'),
        'change': allowed('students_change_student'),
        'delete': allowed('students_delete_student'),
        'invite': allowed('students_bulk_invite'),
    }


def _optional_search(name):
    raw = request.args.get(name, '')
    if raw in ('', None):
        return ''
    if not isinstance(raw, str) or _CONTROL.search(raw) or len(raw) > 100:
        raise InputError('student_search_invalid')
    return raw.strip()


def _query_filters():
    search = _optional_search('search')
    course_raw = request.args.get('course', '')
    course_id = None
    if course_raw not in ('', None):
        if not str(course_raw).isdigit():
            raise InputError('student_course_invalid')
        course_id = whole_number(int(course_raw), 1000000, 'student_course_invalid', lower=1)
    page_raw = request.args.get('page', '1')
    page = 1 if not str(page_raw).isdigit() else min(int(page_raw), 10000)
    page = max(page, 1)
    sort = request.args.get('sort', 'name')
    if sort not in _SORTS:
        sort = 'name'
    order = 'DESC' if request.args.get('order', 'ASC').upper() == 'DESC' else 'ASC'
    fields = {
        'name': _optional_search('name'),
        'roll': _optional_search('roll'),
        'email': _optional_search('email'),
        'class_name': _optional_search('class_name'),
        'course_name': _optional_search('course_name'),
    }
    return search, course_id, page, sort, order, bounded_page_size(request.args.get('per_page')), fields


def _list():
    denied = _denied('students_view_student')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        search, course_id, page, sort, order, per_page, fields = _query_filters()
        scope = _accessible_ids()
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        where = [
            "u.role = 'Student'",
            "COALESCE(u.status, 'active') = 'active'",
            'COALESCE(s.is_active, 1) = 1',
        ]
        params = []
        scope_sql, scope_params = _scope_clause(scope)
        if search:
            where.append('(s.name LIKE %s OR s.email LIKE %s OR s.admission_id LIKE %s OR s.roll_number LIKE %s)')
            term = f'%{search}%'
            params.extend((term, term, term, term))
        if course_id is not None:
            where.append('s.course_id = %s')
            params.append(course_id)
        for key, column in (
            ('name', 's.name'),
            ('roll', 's.roll_number'),
            ('email', 's.email'),
            ('class_name', 'cl.name'),
            ('course_name', 'c.name'),
        ):
            value = fields[key]
            if value:
                where.append(f'{column} LIKE %s')
                params.append(f'%{value}%')
        clause = ' WHERE ' + ' AND '.join(where) + scope_sql
        bound = tuple(params) + tuple(scope_params)
        cursor.execute(f'SELECT COUNT(s.id) AS total {_LIST_FROM} {clause}', bound)
        total = safe_count(cursor.fetchone()['total'])
        offset, total_pages = page_bounds(page, per_page, total)
        cursor.execute(
            f"""
            SELECT s.id, s.name, s.email, s.phone, s.roll_number, s.course_id, s.class_id, s.division_id,
                   c.name AS course_name, cl.name AS class_name, d.name AS division_name
            {_LIST_FROM} {clause}
            ORDER BY {_SORTS[sort]} {order}
            LIMIT %s OFFSET %s
            """,
            bound + (per_page, offset),
        )
        students = [_public(row) for row in cursor.fetchall()]
        active_where = """
            FROM students s
            LEFT JOIN users u ON s.user_id = u.id
            WHERE u.role = 'Student'
              AND COALESCE(u.status, 'active') = 'active'
              AND COALESCE(s.is_active, 1) = 1
        """
        cursor.execute(f'SELECT COUNT(s.id) AS total {active_where} {scope_sql}', tuple(scope_params))
        total_active = safe_count(cursor.fetchone()['total'])
        courses, classes, divisions = _options(cursor)
        return json_ok({
            'students': students,
            'page': page,
            'total_pages': total_pages,
            'total': total,
            'total_active': total_active,
            'courses': courses,
            'classes': classes,
            'divisions': divisions,
            'permissions': _permissions(),
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Student list failed')
        return json_error(_MESSAGES['students_unavailable'], 500, 'students_unavailable')
    finally:
        close(cursor, connection)


def _detail(student_id):
    denied = _denied('students_view_student')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        if not _in_scope(student_id, _accessible_ids()):
            return _fail('student_not_found', 404)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT s.id, s.name, s.email, s.phone, s.roll_number, s.course_id, s.class_id, s.division_id, u.username
            FROM students s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = %s AND COALESCE(s.is_active, 1) = 1
            """,
            (student_id,),
        )
        row = cursor.fetchone()
        if not row:
            return _fail('student_not_found', 404)
        return json_ok(_public(row, include_username=True))
    except Exception:
        current_app.logger.exception('Student detail failed')
        return json_error(_MESSAGES['students_unavailable'], 500, 'students_unavailable')
    finally:
        close(cursor, connection)


def _create():
    denied = _denied('students_add_student')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(_CREATE_FIELDS)
        username = required_text(payload.get('username'), 50, 'student_username_invalid')
        password = _password(payload.get('password'), True)
        name = required_text(payload.get('name'), 100, 'student_name_invalid')
        email = _email(payload.get('email'))
        phone = optional_text(payload.get('phone'), 20, 'student_phone_invalid') or None
        roll_number = optional_text(payload.get('roll_number'), 50, 'student_roll_invalid') or None
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        course_id, class_id, division_id = _placement(cursor, payload)
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            return _fail('student_username_taken')
        cursor.execute('SELECT id FROM students WHERE email = %s', (email,))
        if cursor.fetchone():
            return _fail('student_email_taken')
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, 'Student')",
            (username, generate_password_hash(password)),
        )
        user_id = cursor.lastrowid
        admission_id = f'ADM{datetime.now().year}{user_id:06d}'
        cursor.execute(
            """
            INSERT INTO students
                (id, user_id, name, email, phone, roll_number, course_id, class_id, division_id, admission_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, user_id, name, email, phone, roll_number, course_id, class_id, division_id, admission_id),
        )
        connection.commit()
        return json_ok({'id': safe_count(user_id)}, 201)
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Student create conflict')
        return _fail('student_username_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Student create failed')
        return json_error(_MESSAGES['students_unavailable'], 500, 'students_unavailable')
    finally:
        close(cursor, connection)


def _update(student_id):
    denied = _denied('students_change_student')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        if not _in_scope(student_id, _accessible_ids()):
            return _fail('student_not_found', 404)
        payload = body(_UPDATE_FIELDS)
        name = required_text(payload.get('name'), 100, 'student_name_invalid')
        email = _email(payload.get('email'))
        phone = optional_text(payload.get('phone'), 20, 'student_phone_invalid') or None
        roll_number = optional_text(payload.get('roll_number'), 50, 'student_roll_invalid') or None
        password = _password(payload.get('password'), False)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        course_id, class_id, division_id = _placement(cursor, payload)
        cursor.execute(
            'SELECT user_id FROM students WHERE id = %s AND COALESCE(is_active, 1) = 1',
            (student_id,),
        )
        current = cursor.fetchone()
        if not current:
            return _fail('student_not_found', 404)
        cursor.execute('SELECT id FROM students WHERE email = %s AND id != %s', (email, student_id))
        if cursor.fetchone():
            return _fail('student_email_taken')
        cursor.execute(
            """
            UPDATE students
            SET name = %s, email = %s, phone = %s, roll_number = %s,
                course_id = %s, class_id = %s, division_id = %s
            WHERE id = %s
            """,
            (name, email, phone, roll_number, course_id, class_id, division_id, student_id),
        )
        if password:
            cursor.execute(
                'UPDATE users SET password = %s WHERE id = %s AND role = %s',
                (generate_password_hash(password), current['user_id'], 'Student'),
            )
        connection.commit()
        return json_ok({'id': safe_count(student_id)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except IntegrityError:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Student update conflict')
        return _fail('student_email_taken')
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Student update failed')
        return json_error(_MESSAGES['students_unavailable'], 500, 'students_unavailable')
    finally:
        close(cursor, connection)


def _id_list(value):
    if not isinstance(value, list) or not value or len(value) > 100:
        raise InputError('student_ids_invalid')
    ids = []
    for item in value:
        number = whole_number(item, 1000000, 'student_ids_invalid', lower=1)
        if number not in ids:
            ids.append(number)
    return ids


def _deactivate():
    denied = _denied('students_delete_student')
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        payload = body(frozenset(('ids',)))
        ids = _id_list(payload.get('ids'))
        scope = _accessible_ids()
        if any(not _in_scope(student_id, scope) for student_id in ids):
            return _fail('student_not_found', 404)
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        placeholders = ','.join(['%s'] * len(ids))
        cursor.execute(
            f'SELECT id, user_id FROM students WHERE id IN ({placeholders}) AND COALESCE(is_active, 1) = 1',
            tuple(ids),
        )
        rows = cursor.fetchall()
        if len(rows) != len(ids):
            return _fail('student_not_found', 404)
        cursor.execute(
            f'UPDATE students SET is_active = 0 WHERE id IN ({placeholders})',
            tuple(ids),
        )
        user_ids = [row['user_id'] for row in rows if row.get('user_id')]
        if user_ids:
            user_placeholders = ','.join(['%s'] * len(user_ids))
            cursor.execute(
                f"""
                UPDATE users SET status = 'inactive'
                WHERE id IN ({user_placeholders}) AND role = 'Student'
                """,
                tuple(user_ids),
            )
        connection.commit()
        return json_ok({'deactivated': len(rows)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Student deactivate failed')
        return json_error(_MESSAGES['students_unavailable'], 500, 'students_unavailable')
    finally:
        close(cursor, connection)
