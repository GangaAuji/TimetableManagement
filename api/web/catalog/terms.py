"""Academic terms (capability `academic_terms`).

GET  /api/academic-terms          the institution's terms, years, semesters, teaching weeks, totals
POST /api/academic-terms          academicyears_add
PUT  /api/academic-terms/<id>     academicyears_change
DELETE /api/academic-terms/<id>   academicyears_delete

404 `capability_off` while the capability is off. Saving a term cancels unmarked sessions that
now fall in an exam, break or internship term (reason `calendar`).
"""

from datetime import date, timedelta

from flask import current_app, session

from api.web.access import InputError, allowed, body, close, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core import capabilities
from core.scope import current_scope
from extensions import get_db_connection
from security import log_activity
from services import academic_calendar as calendar

FIELDS = frozenset(('name', 'kind', 'start_date', 'end_date', 'academic_year_id', 'semester_id'))
_MESSAGES = {
    'terms_unavailable': 'Academic terms could not be loaded.',
    'term_invalid': 'Give a name, a kind and dates inside the academic year.',
    'term_overlap': 'Those dates overlap another term for this institution.',
    'term_not_found': 'That term was not found.',
    'terms_table_missing': 'The academic terms table is missing; apply the database migrations first.',
    'invalid_body': 'The request could not be accepted.',
}


def register_term_routes(blueprint):
    blueprint.add_url_rule('/academic-terms', 'academic_terms', _terms, methods=['GET'])
    blueprint.add_url_rule('/academic-terms', 'academic_terms_create', _create, methods=['POST'])
    blueprint.add_url_rule('/academic-terms/<int:term_id>', 'academic_terms_update', _update, methods=['PUT'])
    blueprint.add_url_rule('/academic-terms/<int:term_id>', 'academic_terms_delete', _delete, methods=['DELETE'])


def _institution(cursor):
    scope = current_scope(cursor)
    return int(scope.institution_id or 1)


def _iso(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()[:10]
    return safe_text(value, 10)


def _public(row):
    return {
        'id': safe_count(row.get('id')),
        'name': safe_text(row.get('name'), 80),
        'kind': safe_text(row.get('kind'), 20),
        'start_date': _iso(row.get('start_date')),
        'end_date': _iso(row.get('end_date')),
        'academic_year_id': safe_count(row.get('academic_year_id')),
        'year_name': safe_text(row.get('year_name'), 20),
        'semester_id': safe_count(row.get('semester_id')) or None,
        'semester_name': safe_text(row.get('semester_name') or '', 50),
    }


def _payload(cursor, institution_id):
    rows = calendar.list_terms(cursor, institution_id if current_scope(cursor).multiple else None)
    scope = current_scope(cursor)
    rows = [row for row in rows if scope.allows(row.get('institution_id'))]
    terms = [
        {'name': row['name'], 'kind': row['kind'], 'start': row['start_date'], 'end': row['end_date']}
        for row in rows
    ]
    weeks = [
        {'name': safe_text(item['name'], 80), 'week_start': item['week_start'].isoformat(), 'teaching_days': item['teaching_days']}
        for item in calendar.teaching_weeks(terms)
    ]
    today = date.today()
    totals = calendar.period_totals(cursor, institution_id, today - timedelta(days=30), today)
    cursor.execute('SELECT id, name FROM academic_years ORDER BY start_date DESC')
    years = [{'id': safe_count(row['id']), 'name': safe_text(row['name'], 20)} for row in cursor.fetchall()]
    cursor.execute('SELECT id, semester_name, academic_year_id FROM semesters ORDER BY start_date DESC')
    semesters = [
        {'id': safe_count(row['id']), 'name': safe_text(row['semester_name'], 50), 'academic_year_id': safe_count(row['academic_year_id'])}
        for row in cursor.fetchall()
    ]
    return {
        'terms': [_public(row) for row in rows],
        'weeks': weeks[:60],
        'totals': totals,
        'years': years,
        'semesters': semesters,
        'kinds': list(calendar.KINDS),
        'permissions': {
            'add': allowed('academic_terms_change') or allowed('academicyears_add'),
            'change': allowed('academic_terms_change') or allowed('academicyears_change'),
            'delete': allowed('academic_terms_change') or allowed('academicyears_delete'),
        },
    }


def _view_denied():
    if allowed('academic_terms_view') or allowed('academicyears_view'):
        return None
    return permission_denied('academic_terms_view', 'terms_unavailable', _MESSAGES['terms_unavailable'])


def _write_denied(fallback):
    if allowed('academic_terms_change') or allowed(fallback):
        return None
    return permission_denied('academic_terms_change', 'terms_unavailable', _MESSAGES['terms_unavailable'])


def _terms():
    denied = _view_denied()
    if denied:
        return denied
    off = capabilities.require_capability(calendar.CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not calendar.table_exists(cursor):
            return json_error(_MESSAGES['terms_table_missing'], 409, 'terms_table_missing')
        return json_ok(_payload(cursor, _institution(cursor)))
    except Exception:
        current_app.logger.exception('Academic terms failed')
        return json_error(_MESSAGES['terms_unavailable'], 500, 'terms_unavailable')
    finally:
        close(cursor, connection)


def _write(term_id):
    connection = cursor = None
    try:
        payload = body(FIELDS)
        try:
            term = calendar.clean_term(payload)
        except ValueError as exc:
            raise InputError(str(exc))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        institution_id = _institution(cursor)
        try:
            saved_id = calendar.save_term(cursor, institution_id, term, term_id)
        except RuntimeError:
            connection.rollback()
            return json_error(_MESSAGES['terms_table_missing'], 409, 'terms_table_missing')
        except ValueError as exc:
            connection.rollback()
            raise InputError(str(exc))
        cancelled = calendar.sweep(cursor)
        log_activity(
            session.get('user_id'), 'academic_term_saved', f"Academic term '{term['name']}' saved",
            entity_type='academic_term', entity_id=saved_id,
            new_values={'kind': term['kind'], 'cancelled_sessions': cancelled}, cursor=cursor,
        )
        connection.commit()
        return json_ok({'saved': True, 'id': saved_id, 'cancelled_sessions': cancelled, **_payload(cursor, institution_id)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Academic term save failed')
        return json_error(_MESSAGES['terms_unavailable'], 500, 'terms_unavailable')
    finally:
        close(cursor, connection)


def _create():
    denied = _write_denied('academicyears_add')
    if denied:
        return denied
    off = capabilities.require_capability(calendar.CAPABILITY)
    if off:
        return off
    return _write(None)


def _update(term_id):
    denied = _write_denied('academicyears_change')
    if denied:
        return denied
    off = capabilities.require_capability(calendar.CAPABILITY)
    if off:
        return off
    return _write(term_id)


def _delete(term_id):
    denied = _write_denied('academicyears_delete')
    if denied:
        return denied
    off = capabilities.require_capability(calendar.CAPABILITY)
    if off:
        return off
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        institution_id = _institution(cursor)
        if not calendar.delete_term(cursor, institution_id, term_id):
            return json_error(_MESSAGES['term_not_found'], 404, 'term_not_found')
        log_activity(
            session.get('user_id'), 'academic_term_deleted', 'Academic term deleted',
            entity_type='academic_term', entity_id=term_id, cursor=cursor,
        )
        connection.commit()
        return json_ok({'deleted': True, **_payload(cursor, institution_id)})
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Academic term delete failed')
        return json_error(_MESSAGES['terms_unavailable'], 500, 'terms_unavailable')
    finally:
        close(cursor, connection)
