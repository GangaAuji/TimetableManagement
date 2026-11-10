"""Soft timetable rules and faculty preferences (capability `timetable_preferences`).

GET /api/timetable/rules                       the institution's rules, the registry and the defaults
PUT /api/timetable/rules                       {"rules": {name: {"weight", ...params}}} - timetable_generate
GET /api/faculty/<id>/preferences              a teacher's windows (faculty row id) - faculty_view_availability
PUT /api/faculty/<id>/preferences              {"preferences": [...]} - faculty_change_availability
GET /api/portal/preferences                    the signed-in teacher's own windows
PUT /api/portal/preferences                    the signed-in teacher replaces their own windows
GET /api/timetable/workload-norms              norms per designation + every teacher's status (capability `workload_norms`)
PUT /api/timetable/workload-norms              {"norms": {"default": {min,max}, "by_designation": {...}}} - timetable_generate

Every route answers 404 `capability_off` while its capability is off.
"""

from flask import current_app, session

from api.web.access import InputError, allowed, body, close, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core import capabilities
from core.scope import current_scope
from extensions import get_db_connection
from security import log_activity
from services import workload
from services.timetable import rules as rule_set

CAPABILITY = 'timetable_preferences'
_MESSAGES = {
    'rules_unavailable': 'Timetable rules could not be loaded.',
    'rules_invalid': 'Check the rule weights and try again.',
    'rules_table_missing': 'The rules table is missing; apply the database migrations first.',
    'norms_unavailable': 'Workload norms could not be loaded.',
    'norms_invalid': 'Norms are hours per week from 0 to 60, with the minimum no higher than the maximum.',
    'preferences_unavailable': 'Preferences could not be loaded.',
    'preferences_invalid': 'Check the preference windows and try again.',
    'preferences_table_missing': 'The preferences table is missing; apply the database migrations first.',
    'faculty_not_found': 'That faculty member was not found.',
    'faculty_not_owned': 'That faculty member belongs to another institution.',
    'invalid_body': 'The request could not be accepted.',
}


def register_timetable_rule_routes(blueprint):
    blueprint.add_url_rule('/timetable/rules', 'timetable_rules', _rules, methods=['GET'])
    blueprint.add_url_rule('/timetable/rules', 'timetable_rules_save', _save_rules, methods=['PUT'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/preferences', 'faculty_preferences', _preferences, methods=['GET'])
    blueprint.add_url_rule('/faculty/<int:faculty_id>/preferences', 'faculty_preferences_save', _save_preferences, methods=['PUT'])
    blueprint.add_url_rule('/portal/preferences', 'portal_preferences', _own_preferences, methods=['GET'])
    blueprint.add_url_rule('/portal/preferences', 'portal_preferences_save', _save_own_preferences, methods=['PUT'])
    blueprint.add_url_rule('/timetable/workload-norms', 'workload_norms', _norms, methods=['GET'])
    blueprint.add_url_rule('/timetable/workload-norms', 'workload_norms_save', _save_norms, methods=['PUT'])


# Workload norms ---------------------------------------------------------------------------------

def _norms_payload(cursor):
    institution_id = _institution_id(cursor)
    norms, stored = workload.load_norms(cursor, institution_id)
    teachers = [
        {
            'faculty_id': row['faculty_id'], 'name': safe_text(row['name'], 100), 'designation': safe_text(row['designation'], 50),
            'department_name': safe_text(row['department_name'], 100), 'hours': row['hours'],
            'min': row['min'], 'max': row['max'], 'status': row['status'],
        }
        for row in workload.assess(cursor, institution_id=institution_id)
    ]
    return {
        'institution_id': institution_id,
        'norms': norms,
        'stored': stored,
        'enforce': workload.enforcement(cursor),
        'designations': workload.designations(cursor, institution_id),
        'teachers': teachers,
        'max_hours': workload.MAX_HOURS,
        'can_change': allowed('workload_norms_change') or allowed('timetable_generate'),
    }


def _norms_view_denied():
    if allowed('workload_norms_view') or allowed('timetable_generate') or allowed('reports_view_timetable'):
        return None
    return permission_denied('workload_norms_view', 'norms_unavailable', _MESSAGES['norms_unavailable'])


def _norms_change_denied():
    if allowed('workload_norms_change') or allowed('timetable_generate'):
        return None
    return permission_denied('workload_norms_change', 'norms_unavailable', _MESSAGES['norms_unavailable'])


def _norms():
    denied = _norms_view_denied()
    if denied:
        return denied
    off = capabilities.require_capability(workload.CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not rule_set.table_exists(cursor, rule_set.RULES_TABLE):
            return json_error(_MESSAGES['rules_table_missing'], 409, 'rules_table_missing')
        return json_ok(_norms_payload(cursor))
    except Exception:
        current_app.logger.exception('Workload norms failed')
        return json_error(_MESSAGES['norms_unavailable'], 500, 'norms_unavailable')
    finally:
        close(cursor, connection)


def _save_norms():
    denied = _norms_change_denied()
    if denied:
        return denied
    off = capabilities.require_capability(workload.CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        payload = body(frozenset(('norms',)))
        try:
            norms = workload.clean_norms(payload.get('norms'))
        except ValueError as exc:
            raise InputError(str(exc))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        institution_id = _institution_id(cursor)
        try:
            workload.save_norms(cursor, institution_id, norms, session.get('user_id'))
        except RuntimeError:
            connection.rollback()
            return json_error(_MESSAGES['rules_table_missing'], 409, 'rules_table_missing')
        log_activity(
            session.get('user_id'), 'workload_norms_changed', 'Workload norms changed',
            entity_type='timetable_rules', entity_id=institution_id, new_values=norms, cursor=cursor,
        )
        connection.commit()
        return json_ok({'saved': True, **_norms_payload(cursor)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Workload norms save failed')
        return json_error(_MESSAGES['norms_unavailable'], 500, 'norms_unavailable')
    finally:
        close(cursor, connection)


# Rules ------------------------------------------------------------------------------------------

def _registry():
    return [
        {
            'name': rule.name, 'title': rule.title, 'description': rule.description, 'scope': rule.scope,
            'default_weight': rule.default,
            'params': {key: {'kind': kind, 'default': default} for key, (kind, default) in rule.params.items()},
        }
        for rule in rule_set.RULES
    ]


def _institution_id(cursor):
    scope = current_scope(cursor)
    return int(scope.institution_id or 1)


def _rules_payload(cursor):
    institution_id = _institution_id(cursor)
    rules, stored = rule_set.load_rules(cursor, institution_id)
    return {
        'institution_id': institution_id,
        'rules': rules,
        'stored': stored,
        'defaults': rule_set.default_rules(),
        'registry': _registry(),
        'max_weight': rule_set.MAX_WEIGHT,
        'can_change': allowed('timetable_rules_change') or allowed('timetable_generate'),
    }


def _rules_view_denied():
    if allowed('timetable_rules_view') or allowed('timetable_generate'):
        return None
    return permission_denied('timetable_rules_view', 'rules_unavailable', _MESSAGES['rules_unavailable'])


def _rules_change_denied():
    if allowed('timetable_rules_change') or allowed('timetable_generate'):
        return None
    return permission_denied('timetable_rules_change', 'rules_unavailable', _MESSAGES['rules_unavailable'])


def _rules():
    denied = _rules_view_denied()
    if denied:
        return denied
    off = capabilities.require_capability(CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        return json_ok(_rules_payload(cursor))
    except Exception:
        current_app.logger.exception('Timetable rules failed')
        return json_error(_MESSAGES['rules_unavailable'], 500, 'rules_unavailable')
    finally:
        close(cursor, connection)


def _save_rules():
    denied = _rules_change_denied()
    if denied:
        return denied
    off = capabilities.require_capability(CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        payload = body(frozenset(('rules',)))
        try:
            rules = rule_set.clean_rules(payload.get('rules'))
        except ValueError as exc:
            raise InputError(str(exc))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        institution_id = _institution_id(cursor)
        try:
            rule_set.save_rules(cursor, institution_id, rules, session.get('user_id'))
        except RuntimeError:
            connection.rollback()
            return json_error(_MESSAGES['rules_table_missing'], 409, 'rules_table_missing')
        log_activity(
            session.get('user_id'), 'timetable_rules_changed', 'Timetable rules changed',
            entity_type='timetable_rules', entity_id=institution_id, new_values=rules, cursor=cursor,
        )
        connection.commit()
        return json_ok({'saved': True, **_rules_payload(cursor)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Timetable rules save failed')
        return json_error(_MESSAGES['rules_unavailable'], 500, 'rules_unavailable')
    finally:
        close(cursor, connection)


# Preferences ------------------------------------------------------------------------------------

def _public_preferences(items):
    return [
        {
            'day': safe_text(item.get('day'), 12),
            'start_time': safe_text(item.get('start_time'), 5),
            'end_time': safe_text(item.get('end_time'), 5),
            'kind': safe_text(item.get('kind'), 10),
            'weight': max(1, min(5, safe_count(item.get('weight')) or 1)),
            'note': safe_text(item.get('note') or '', 120),
        }
        for item in items
    ]


def _faculty_row(cursor, faculty_id):
    """(row, error) for a faculty row id within the current institution scope."""
    cursor.execute(
        'SELECT f.id, f.user_id, f.name, d.institution_id FROM faculty f LEFT JOIN departments d ON d.id = f.department_id WHERE f.id = %s',
        (faculty_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None, json_error(_MESSAGES['faculty_not_found'], 404, 'faculty_not_found')
    # The Teacher role carries the availability permissions for its own record only.
    if session.get('role') == 'Teacher' and int(row.get('user_id') or 0) != int(session.get('user_id') or -1):
        return None, json_error('You do not have permission to do that.', 403, 'forbidden')
    scope = current_scope(cursor)
    if not scope.allows(row.get('institution_id')):
        return None, json_error(_MESSAGES['faculty_not_owned'], 403, 'faculty_not_owned')
    return row, None


def _own_row(cursor):
    cursor.execute(
        'SELECT id, user_id, name FROM faculty WHERE id = %s OR user_id = %s LIMIT 1',
        (session.get('faculty_id') or 0, session.get('user_id')),
    )
    return cursor.fetchone()


def _preferences_payload(cursor, row, can_change):
    items = rule_set.load_preferences(cursor, [row['user_id']]).get(int(row['user_id']), [])
    return {
        'faculty_id': safe_count(row.get('id')),
        'faculty_name': safe_text(row.get('name'), 100),
        'preferences': _public_preferences(items),
        'kinds': list(rule_set.PREFERENCE_KINDS),
        'can_change': can_change,
    }


def _preferences(faculty_id):
    denied = permission_denied('faculty_view_availability', 'preferences_unavailable', _MESSAGES['preferences_unavailable'])
    if denied and not allowed('faculty_change_availability'):
        return denied
    off = capabilities.require_capability(CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        row, error = _faculty_row(cursor, faculty_id)
        if error:
            return error
        return json_ok(_preferences_payload(cursor, row, allowed('faculty_change_availability')))
    except Exception:
        current_app.logger.exception('Faculty preferences failed')
        return json_error(_MESSAGES['preferences_unavailable'], 500, 'preferences_unavailable')
    finally:
        close(cursor, connection)


def _replace(cursor, connection, row, payload):
    try:
        preferences = rule_set.clean_preferences(payload.get('preferences'))
    except ValueError as exc:
        raise InputError(str(exc))
    try:
        rule_set.save_preferences(cursor, row['user_id'], preferences)
    except RuntimeError:
        connection.rollback()
        return json_error(_MESSAGES['preferences_table_missing'], 409, 'preferences_table_missing')
    log_activity(
        session.get('user_id'), 'faculty_preferences_changed', f"Preferences changed for {row.get('name') or 'a teacher'}",
        entity_type='faculty', entity_id=row.get('id'), new_values={'windows': len(preferences)}, cursor=cursor,
    )
    connection.commit()
    return None


def _save_preferences(faculty_id):
    denied = permission_denied('faculty_change_availability', 'preferences_unavailable', _MESSAGES['preferences_unavailable'])
    if denied:
        return denied
    off = capabilities.require_capability(CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        payload = body(frozenset(('preferences',)))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        row, error = _faculty_row(cursor, faculty_id)
        if error:
            return error
        failed = _replace(cursor, connection, row, payload)
        if failed:
            return failed
        return json_ok({'saved': True, **_preferences_payload(cursor, row, True)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Faculty preferences save failed')
        return json_error(_MESSAGES['preferences_unavailable'], 500, 'preferences_unavailable')
    finally:
        close(cursor, connection)


def _teacher_denied():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Teacher':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    return None


def _own_preferences():
    denied = _teacher_denied()
    if denied:
        return denied
    off = capabilities.require_capability(CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        row = _own_row(cursor)
        if not row:
            return json_error(_MESSAGES['faculty_not_found'], 404, 'faculty_not_found')
        return json_ok(_preferences_payload(cursor, row, True))
    except Exception:
        current_app.logger.exception('Own preferences failed')
        return json_error(_MESSAGES['preferences_unavailable'], 500, 'preferences_unavailable')
    finally:
        close(cursor, connection)


def _save_own_preferences():
    denied = _teacher_denied()
    if denied:
        return denied
    off = capabilities.require_capability(CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        payload = body(frozenset(('preferences',)))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        row = _own_row(cursor)
        if not row:
            return json_error(_MESSAGES['faculty_not_found'], 404, 'faculty_not_found')
        failed = _replace(cursor, connection, row, payload)
        if failed:
            return failed
        return json_ok({'saved': True, **_preferences_payload(cursor, row, True)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Own preferences save failed')
        return json_error(_MESSAGES['preferences_unavailable'], 500, 'preferences_unavailable')
    finally:
        close(cursor, connection)
