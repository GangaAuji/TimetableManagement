"""Lab batch API: groups a division is split into for practicals, and which students are in each.

Uses the course-batch permissions (batches_view/add/change/delete): the same
people who manage intake batches manage lab batches.
"""

from flask import current_app, request, session
from mysql.connector import IntegrityError

from api.web.access import (
    InputError,
    allowed,
    body,
    close,
    flag,
    iso_date,
    optional_id,
    permission_denied,
    reject_input,
    required_text,
    whole_number,
)
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core.db import transaction
from core.scope import current_scope
from data_access import institutions as institutions_store
from extensions import get_db_connection
from security import log_activity
from services import lab_batches
from services.lab_batches import LabBatchError

FIELDS = frozenset((
    'course_id', 'class_id', 'division_id', 'academic_year_id', 'semester_id', 'name', 'capacity', 'is_active',
))
MEMBER_FIELDS = frozenset(('student_ids', 'on_date'))
SPLIT_FIELDS = frozenset(('on_date',))
MESSAGES = {
    'invalid_body': 'The request could not be accepted.',
    'lab_batch_name_invalid': 'Enter a batch name up to 20 characters.',
    'lab_batch_course_invalid': 'Choose a course.',
    'lab_batch_class_invalid': 'Choose a class.',
    'lab_batch_division_invalid': 'Choose a valid division, or leave it empty to split the whole class.',
    'lab_batch_year_invalid': 'Choose an academic year.',
    'lab_batch_semester_invalid': 'Choose a valid semester, or leave it empty.',
    'lab_batch_capacity_invalid': 'Capacity must be between 1 and 500, or empty.',
    'lab_batch_date_invalid': 'Enter the date the change applies from as YYYY-MM-DD.',
    'lab_batch_students_invalid': 'Choose students by id.',
    'lab_batch_students_outside_cohort': 'Every student must belong to the class and division this batch splits.',
    'lab_batch_over_capacity': 'That is more students than the batch capacity.',
    'lab_batch_needs_two_groups': 'Create at least two batches for this class before splitting students.',
    'lab_batch_exists': 'A batch with that name already exists for this class and year.',
    'lab_batch_not_found': 'That lab batch was not found.',
    'lab_batches_unavailable': 'Lab batches could not be loaded.',
}


def _public(row):
    return {
        'id': safe_count(row.get('id')),
        'course_id': safe_count(row.get('course_id')),
        'course_name': safe_text(row.get('course_name'), 100),
        'class_id': safe_count(row.get('class_id')),
        'class_name': safe_text(row.get('class_name'), 100),
        'division_id': safe_count(row.get('division_id')) or None,
        'division_name': safe_text(row.get('division_name') or '', 100),
        'academic_year_id': safe_count(row.get('academic_year_id')),
        'academic_year_name': safe_text(row.get('academic_year_name'), 50),
        'semester_id': safe_count(row.get('semester_id')) or None,
        'semester_name': safe_text(row.get('semester_name') or '', 50),
        'name': safe_text(row.get('name'), 20),
        'capacity': safe_count(row.get('capacity')) or None,
        'is_active': bool(row.get('is_active')),
        'member_count': safe_count(row.get('member_count')),
        'slot_count': safe_count(row.get('slot_count')),
    }


def _student(row):
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 100),
        'roll_number': safe_text(row.get('roll_number') or '', 30),
        'email': safe_text(row.get('email') or '', 190),
        'lab_batch_group_id': safe_count(row.get('lab_batch_group_id')) or None,
    }


def _member(row):
    return {
        'student_id': safe_count(row.get('student_id')),
        'name': safe_text(row.get('name'), 100),
        'roll_number': safe_text(row.get('roll_number') or '', 30),
        'added_at': row['added_at'].isoformat() if row.get('added_at') else None,
        'ended_at': row['ended_at'].isoformat() if row.get('ended_at') else None,
    }


def _filters():
    out = {}
    for name in ('course_id', 'class_id', 'division_id', 'academic_year_id'):
        raw = request.args.get(name, '')
        if raw in ('', None):
            continue
        if not str(raw).isdigit():
            raise InputError('invalid_body')
        out[name] = int(raw)
    return out


def _values(payload, *, creating):
    values = {
        'name': required_text(payload.get('name'), 20, 'lab_batch_name_invalid'),
        'capacity': optional_id(payload.get('capacity'), 'lab_batch_capacity_invalid'),
        'is_active': flag(payload.get('is_active', True)),
        'semester_id': optional_id(payload.get('semester_id'), 'lab_batch_semester_invalid'),
    }
    if values['capacity'] is not None and values['capacity'] > 500:
        raise InputError('lab_batch_capacity_invalid')
    if creating:
        values['course_id'] = whole_number(payload.get('course_id'), 1000000, 'lab_batch_course_invalid', lower=1)
        values['class_id'] = whole_number(payload.get('class_id'), 1000000, 'lab_batch_class_invalid', lower=1)
        values['division_id'] = optional_id(payload.get('division_id'), 'lab_batch_division_invalid')
        values['academic_year_id'] = whole_number(payload.get('academic_year_id'), 1000000, 'lab_batch_year_invalid', lower=1)
    return values


def _guard_course(cursor, course_id):
    """Raise when the course belongs to an institution outside the caller's scope."""
    if not current_scope(cursor).allows(institutions_store.institution_of_course(cursor, course_id)):
        raise LabBatchError('lab_batch_course_invalid')


def _guard_group(cursor, group_id):
    """Raise 'not found' when the group's course is outside the caller's scope."""
    scope = current_scope(cursor)
    if not scope.multiple:
        return
    cursor.execute('SELECT course_id FROM lab_batch_groups WHERE id = %s', (group_id,))
    row = cursor.fetchone()
    if row is None or not scope.allows(institutions_store.institution_of_course(cursor, row['course_id'])):
        raise LabBatchError('lab_batch_not_found')


def _in_scope(cursor, rows):
    scope = current_scope(cursor)
    if not scope.multiple:
        return rows
    clause, params = scope.course_clause('c')
    cursor.execute(f'SELECT c.id FROM courses c WHERE {clause}', params)
    visible = {int(row['id']) for row in cursor.fetchall()}
    return [row for row in rows if int(row.get('course_id') or 0) in visible]


def _options(cursor):
    clause, params = current_scope(cursor).course_clause('c')
    cursor.execute(f'SELECT c.id, c.name FROM courses c WHERE COALESCE(c.is_active, 1) = 1 AND {clause} ORDER BY c.name', params)
    courses = [{'id': safe_count(r['id']), 'name': safe_text(r['name'], 100)} for r in cursor.fetchall()]
    cursor.execute('SELECT id, name FROM classes ORDER BY name')
    classes = [{'id': safe_count(r['id']), 'name': safe_text(r['name'], 100)} for r in cursor.fetchall()]
    cursor.execute('SELECT id, name FROM divisions ORDER BY name')
    divisions = [{'id': safe_count(r['id']), 'name': safe_text(r['name'], 100)} for r in cursor.fetchall()]
    cursor.execute('SELECT id, name FROM academic_years ORDER BY start_date DESC')
    years = [{'id': safe_count(r['id']), 'name': safe_text(r['name'], 50)} for r in cursor.fetchall()]
    cursor.execute('SELECT id, semester_name FROM semesters ORDER BY start_date DESC, semester_name')
    semesters = [{'id': safe_count(r['id']), 'name': safe_text(r['semester_name'], 50)} for r in cursor.fetchall()]
    return {'courses': courses, 'classes': classes, 'divisions': divisions, 'years': years, 'semesters': semesters}


def _permissions():
    return {'add': allowed('batches_add'), 'change': allowed('batches_change'), 'delete': allowed('batches_delete')}


def _audit(action, group_id, details, new_values=None):
    try:
        log_activity(session.get('user_id'), action, details, entity_type='lab_batch_group', entity_id=group_id, new_values=new_values)
    except Exception:
        current_app.logger.exception('Lab batch audit failed')


def register_lab_batch_routes(blueprint):
    @blueprint.route('/lab-batches', methods=['GET'])
    def list_lab_batches():
        denied = permission_denied('batches_view', 'lab_batches_unavailable', MESSAGES['lab_batches_unavailable'])
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            filters = _filters()
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            groups = [_public(row) for row in _in_scope(cursor, lab_batches.groups(cursor, **filters))]
            return json_ok({'groups': groups, **_options(cursor), 'permissions': _permissions()})
        except InputError as exc:
            return reject_input(MESSAGES, exc.code)
        except Exception:
            current_app.logger.exception('Lab batch list failed')
            return json_error(MESSAGES['lab_batches_unavailable'], 500, 'lab_batches_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/lab-batches', methods=['POST'])
    def create_lab_batch():
        denied = permission_denied('batches_add', 'lab_batches_unavailable', MESSAGES['lab_batches_unavailable'])
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            values = _values(body(FIELDS), creating=True)
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            _guard_course(cursor, values['course_id'])
            with transaction(connection):
                group_id = lab_batches.create_group(cursor, values)
            _audit('lab_batch_created', group_id, f"Created lab batch {values['name']}", new_values=values)
            return json_ok(_public(lab_batches.group(cursor, group_id)))
        except (InputError, LabBatchError) as exc:
            return reject_input(MESSAGES, exc.code)
        except IntegrityError:
            return reject_input(MESSAGES, 'lab_batch_exists')
        except Exception:
            current_app.logger.exception('Lab batch create failed')
            return json_error(MESSAGES['lab_batches_unavailable'], 500, 'lab_batches_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/lab-batches/<int:group_id>', methods=['PUT'])
    def update_lab_batch(group_id):
        denied = permission_denied('batches_change', 'lab_batches_unavailable', MESSAGES['lab_batches_unavailable'])
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            values = _values(body(FIELDS), creating=False)
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            _guard_group(cursor, group_id)
            with transaction(connection):
                lab_batches.update_group(cursor, group_id, values)
            _audit('lab_batch_changed', group_id, f"Changed lab batch {values['name']}", new_values=values)
            return json_ok(_public(lab_batches.group(cursor, group_id)))
        except (InputError, LabBatchError) as exc:
            return reject_input(MESSAGES, exc.code)
        except IntegrityError:
            return reject_input(MESSAGES, 'lab_batch_exists')
        except Exception:
            current_app.logger.exception('Lab batch update failed')
            return json_error(MESSAGES['lab_batches_unavailable'], 500, 'lab_batches_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/lab-batches/<int:group_id>', methods=['DELETE'])
    def delete_lab_batch(group_id):
        denied = permission_denied('batches_delete', 'lab_batches_unavailable', MESSAGES['lab_batches_unavailable'])
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            _guard_group(cursor, group_id)
            with transaction(connection):
                lab_batches.delete_group(cursor, group_id)
            _audit('lab_batch_deleted', group_id, f'Deleted lab batch #{group_id}')
            return json_ok({'deleted': True})
        except LabBatchError as exc:
            return reject_input(MESSAGES, exc.code)
        except Exception:
            current_app.logger.exception('Lab batch delete failed')
            return json_error(MESSAGES['lab_batches_unavailable'], 500, 'lab_batches_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/lab-batches/<int:group_id>/members', methods=['GET'])
    def lab_batch_members(group_id):
        denied = permission_denied('batches_view', 'lab_batches_unavailable', MESSAGES['lab_batches_unavailable'])
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            _guard_group(cursor, group_id)
            view = lab_batches.roster_view(cursor, group_id)
            return json_ok({
                'group': _public(view['group']),
                'siblings': [{'id': safe_count(s['id']), 'name': safe_text(s['name'], 20), 'capacity': safe_count(s.get('capacity')) or None} for s in view['siblings']],
                'students': [_student(row) for row in view['students']],
                'members': [_member(row) for row in lab_batches.members(cursor, group_id)],
                'permissions': _permissions(),
            })
        except LabBatchError as exc:
            return reject_input(MESSAGES, exc.code)
        except Exception:
            current_app.logger.exception('Lab batch members failed')
            return json_error(MESSAGES['lab_batches_unavailable'], 500, 'lab_batches_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/lab-batches/<int:group_id>/members', methods=['PUT'])
    def set_lab_batch_members(group_id):
        denied = permission_denied('batches_change', 'lab_batches_unavailable', MESSAGES['lab_batches_unavailable'])
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            payload = body(MEMBER_FIELDS)
            ids = payload.get('student_ids')
            if not isinstance(ids, list) or len(ids) > 1000:
                raise InputError('lab_batch_students_invalid')
            on_date = iso_date(payload.get('on_date'), 'lab_batch_date_invalid', required=False)
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            _guard_group(cursor, group_id)
            with transaction(connection):
                counts = lab_batches.set_members(cursor, group_id, ids, _date(on_date))
            _audit('lab_batch_members_changed', group_id, f'Set {counts["members"]} member(s) of lab batch #{group_id}', new_values=counts)
            return json_ok({**counts, 'members_list': [_member(row) for row in lab_batches.members(cursor, group_id)]})
        except (InputError, LabBatchError) as exc:
            return reject_input(MESSAGES, exc.code)
        except Exception:
            current_app.logger.exception('Lab batch members update failed')
            return json_error(MESSAGES['lab_batches_unavailable'], 500, 'lab_batches_unavailable')
        finally:
            close(cursor, connection)

    @blueprint.route('/lab-batches/<int:group_id>/split', methods=['POST'])
    def split_lab_batches(group_id):
        denied = permission_denied('batches_change', 'lab_batches_unavailable', MESSAGES['lab_batches_unavailable'])
        if denied is not None:
            return denied
        connection = cursor = None
        try:
            payload = body(SPLIT_FIELDS)
            on_date = iso_date(payload.get('on_date'), 'lab_batch_date_invalid', required=False)
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            _guard_group(cursor, group_id)
            with transaction(connection):
                result = lab_batches.auto_split(cursor, group_id, _date(on_date))
            summary = {str(key): value['members'] for key, value in result.items()}
            _audit('lab_batch_split', group_id, 'Dealt students across lab batches', new_values=summary)
            return json_ok({'groups': summary})
        except (InputError, LabBatchError) as exc:
            return reject_input(MESSAGES, exc.code)
        except Exception:
            current_app.logger.exception('Lab batch split failed')
            return json_error(MESSAGES['lab_batches_unavailable'], 500, 'lab_batches_unavailable')
        finally:
            close(cursor, connection)


def _date(value):
    from datetime import date

    return date.fromisoformat(value) if value else None
