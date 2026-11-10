"""Timetable versions: list, inspect, compare, publish, discard (docs/TIMETABLE.md, "Versions").

All routes sit behind capability `timetable_versions`. Viewing needs `timetable_versions_view`,
`timetable_change` or `timetable_generate`. Publishing, renaming and discarding need
`timetable_versions_publish` or `timetable_generate`. Versions are
scoped to the institutions the caller may see (core.scope).
"""

from flask import current_app, request, session

from api.web.access import InputError, allowed, body, close, permission_denied, reject_input
from api.web.responses import json_error, json_ok
from api.web.security import safe_count, safe_text
from core import capabilities
from core.scope import current_scope
from extensions import get_db_connection
from security import log_activity
from services.timetable import versions

CAPABILITY = 'timetable_versions'

_MESSAGES = {
    'versions_unavailable': 'Timetable versions could not be loaded.',
    'versions_table_missing': 'The versions tables are missing; apply the database migrations first.',
    'version_not_found': 'That timetable version was not found.',
    'version_not_owned': 'That timetable version belongs to another institution.',
    'version_already_published': 'That version is already the live timetable.',
    'version_published': 'The live version cannot be discarded. Publish another version first.',
    'version_empty': 'That version has no slots to publish.',
    'label_invalid': 'Give the version a name of up to 120 characters.',
    'invalid_body': 'The request could not be accepted.',
}


def register_timetable_version_routes(blueprint):
    blueprint.add_url_rule('/timetable/versions', 'timetable_versions', _list, methods=['GET'])
    blueprint.add_url_rule('/timetable/versions/<int:version_id>', 'timetable_version', _one, methods=['GET'])
    blueprint.add_url_rule('/timetable/versions/<int:version_id>', 'timetable_version_rename', _rename, methods=['PUT'])
    blueprint.add_url_rule('/timetable/versions/<int:version_id>', 'timetable_version_discard', _discard, methods=['DELETE'])
    blueprint.add_url_rule('/timetable/versions/<int:version_id>/diff/<other>', 'timetable_version_diff', _diff, methods=['GET'])
    blueprint.add_url_rule('/timetable/versions/<int:version_id>/publish', 'timetable_version_publish', _publish, methods=['POST'])


def _can_publish():
    return allowed('timetable_versions_publish') or allowed('timetable_generate')


def _view_denied():
    if allowed('timetable_versions_view') or allowed('timetable_change') or allowed('timetable_generate'):
        return None
    return permission_denied('timetable_versions_view', 'versions_unavailable', _MESSAGES['versions_unavailable'])


def _gate(change=False):
    """Permission then capability then schema. Returns an error response or None."""
    if change and not _can_publish():
        denied = permission_denied('timetable_versions_publish', 'versions_unavailable', _MESSAGES['versions_unavailable'])
    else:
        denied = None if change else _view_denied()
    if denied:
        return denied
    return capabilities.require_capability(CAPABILITY)


def _public_version(row):
    score = versions.summarize_scores(versions.scores(row))
    return {
        'id': safe_count(row.get('id')),
        'label': safe_text(row.get('label') or '', 120),
        'status': safe_text(row.get('status'), 12),
        'solver': safe_text(row.get('solver') or '', 20),
        'job_id': safe_count(row.get('job_id')) or None,
        'parent_version_id': safe_count(row.get('parent_version_id')) or None,
        'institution_id': safe_count(row.get('institution_id')),
        'created_by': safe_text(row.get('created_by_name') or '', 100),
        'created_at': row['created_at'].isoformat(sep=' ', timespec='minutes') if row.get('created_at') else '',
        'published_by': safe_text(row.get('published_by_name') or '', 100),
        'published_at': row['published_at'].isoformat(sep=' ', timespec='minutes') if row.get('published_at') else '',
        'slot_count': safe_count(row.get('slot_count')),
        'cohorts': [_public_cohort(c) for c in (row.get('cohorts') or [])[:200]],
        'score': score,
    }


def _public_cohort(row):
    return {
        'course_id': safe_count(row.get('course_id')),
        'class_id': safe_count(row.get('class_id')),
        'division_id': safe_count(row.get('division_id')),
        'label': ' / '.join(part for part in (
            safe_text(row.get('course_name') or '', 100), safe_text(row.get('class_name') or '', 100),
            safe_text(row.get('division_name') or '', 100),
        ) if part),
    }


def _public_slot(slot):
    return {
        'id': safe_count(slot.get('id')),
        'course_id': safe_count(slot.get('course_id')),
        'class_id': safe_count(slot.get('class_id')),
        'division_id': safe_count(slot.get('division_id')),
        'day': safe_text(slot.get('day'), 12),
        'start_time': safe_text(slot.get('start_time'), 5),
        'end_time': safe_text(slot.get('end_time'), 5),
        'subject': safe_text(slot.get('subject_name') or '', 100),
        'faculty': safe_text(slot.get('faculty_name') or '', 100),
        'room': safe_text(slot.get('room_number') or '', 20),
        'batch': safe_text(slot.get('batch_name') or '', 60),
    }


def _public_change(change):
    def cell(value):
        if not value:
            return None
        return {
            'day': safe_text(value.get('day'), 12), 'start_time': safe_text(value.get('start_time'), 5),
            'end_time': safe_text(value.get('end_time'), 5), 'room': safe_text(value.get('room_number') or '', 20),
        }

    return {
        'kind': safe_text(change.get('kind'), 16),
        'subject': safe_text(change.get('subject_name') or '', 100),
        'faculty': safe_text(change.get('faculty_name') or '', 100),
        'batch': safe_text(change.get('batch_name') or '', 60),
        'before': cell(change.get('before')),
        'after': cell(change.get('after')),
    }


def _owned(cursor, version_id):
    """(row, error): the version when it exists and is in scope."""
    row = versions.load(cursor, version_id)
    if not row:
        return None, json_error(_MESSAGES['version_not_found'], 404, 'version_not_found')
    if not current_scope(cursor).allows(row.get('institution_id')):
        return None, json_error(_MESSAGES['version_not_owned'], 403, 'version_not_owned')
    return row, None


def _cohort_filter():
    course = safe_count(request.args.get('course_id'))
    klass = safe_count(request.args.get('class_id'))
    division = safe_count(request.args.get('division_id'))
    if course and klass and division:
        return {'course_id': course, 'class_id': klass, 'division_id': division}
    return None


def _list():
    gate = _gate()
    if gate:
        return gate
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not versions.table_exists(cursor):
            return json_error(_MESSAGES['versions_table_missing'], 409, 'versions_table_missing')
        status = request.args.get('status') or None
        rows = versions.list_versions(
            cursor, scope_clause=current_scope(cursor).clause('v.institution_id'), cohort=_cohort_filter(),
            status=status if status in versions.STATUSES else None,
        )
        return json_ok({
            'versions': [_public_version(row) for row in rows],
            'can_publish': _can_publish(),
            'keep_drafts': versions.keep_drafts(cursor),
        })
    except Exception:
        current_app.logger.exception('Timetable versions list failed')
        return json_error(_MESSAGES['versions_unavailable'], 500, 'versions_unavailable')
    finally:
        close(cursor, connection)


def _one(version_id):
    gate = _gate()
    if gate:
        return gate
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not versions.table_exists(cursor):
            return json_error(_MESSAGES['versions_table_missing'], 409, 'versions_table_missing')
        row, error = _owned(cursor, version_id)
        if error:
            return error
        return json_ok({
            'version': _public_version(row),
            'slots': [_public_slot(slot) for slot in versions.version_slots(cursor, version_id)],
            'can_publish': _can_publish(),
        })
    except Exception:
        current_app.logger.exception('Timetable version load failed')
        return json_error(_MESSAGES['versions_unavailable'], 500, 'versions_unavailable')
    finally:
        close(cursor, connection)


def _diff(version_id, other):
    """Compare `version_id` (after) with `other` (before): another version id or `live`."""
    gate = _gate()
    if gate:
        return gate
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not versions.table_exists(cursor):
            return json_error(_MESSAGES['versions_table_missing'], 409, 'versions_table_missing')
        row, error = _owned(cursor, version_id)
        if error:
            return error
        after = versions.version_slots(cursor, version_id)
        if other == 'live':
            before = versions.live_slots(cursor, row['cohorts'])
            other_public = None
        else:
            other_id = safe_count(other)
            if not other_id:
                raise InputError('invalid_body')
            other_row, error = _owned(cursor, other_id)
            if error:
                return error
            before = versions.version_slots(cursor, other_id)
            other_public = _public_version(other_row)
        result = versions.diff(before, after)
        cohort_names = {(c['course_id'], c['class_id'], c['division_id']): _public_cohort(c)['label'] for c in row['cohorts']}
        return json_ok({
            'version': _public_version(row),
            'other': other_public,
            'totals': {safe_text(k, 16): safe_count(v) for k, v in result['totals'].items()},
            'cohorts': [
                {
                    'course_id': c['course_id'], 'class_id': c['class_id'], 'division_id': c['division_id'],
                    'label': cohort_names.get((c['course_id'], c['class_id'], c['division_id']), ''),
                    'counts': {safe_text(k, 16): safe_count(v) for k, v in c['counts'].items()},
                    'changes': [_public_change(change) for change in c['changes'][:400]],
                    'before': [_public_slot(slot) for slot in c['before']],
                    'after': [_public_slot(slot) for slot in c['after']],
                }
                for c in result['cohorts']
            ],
            'faculty': [
                {
                    'faculty': safe_text(item.get('faculty_name') or '', 100),
                    'moved': safe_count(item.get('moved')), 'added': safe_count(item.get('added')),
                    'removed': safe_count(item.get('removed')), 'room_changed': safe_count(item.get('room_changed')),
                }
                for item in result['faculty'][:100]
            ],
            'can_publish': _can_publish() and row['status'] != 'published',
        })
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        current_app.logger.exception('Timetable version diff failed')
        return json_error(_MESSAGES['versions_unavailable'], 500, 'versions_unavailable')
    finally:
        close(cursor, connection)


def _publish(version_id):
    gate = _gate(change=True)
    if gate:
        return gate
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not versions.table_exists(cursor):
            return json_error(_MESSAGES['versions_table_missing'], 409, 'versions_table_missing')
        row, error = _owned(cursor, version_id)
        if error:
            return error
        try:
            outcome = versions.publish(cursor, version_id, published_by=session.get('user_id'))
        except ValueError as exc:
            connection.rollback()
            code = str(exc)
            status = 404 if code == 'version_not_found' else 409
            return json_error(_MESSAGES.get(code, _MESSAGES['versions_unavailable']), status, code)
        log_activity(
            session.get('user_id'), 'timetable_version_published', f"Published timetable version #{version_id} ({row.get('label') or ''})",
            entity_type='timetable_version', entity_id=version_id,
            new_values={'cohorts': outcome['cohorts'], 'slots': outcome['slots'], 'from_status': row.get('status')}, cursor=cursor,
        )
        connection.commit()
        fresh = versions.load(cursor, version_id)
        return json_ok({
            'published': True,
            'version': _public_version(fresh),
            'cohorts': outcome['cohorts'],
            'slots': outcome['slots'],
            'skipped': [_public_cohort(c) for c in outcome['skipped']],
        })
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Timetable version publish failed')
        return json_error(_MESSAGES['versions_unavailable'], 500, 'versions_unavailable')
    finally:
        close(cursor, connection)


def _discard(version_id):
    gate = _gate(change=True)
    if gate:
        return gate
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not versions.table_exists(cursor):
            return json_error(_MESSAGES['versions_table_missing'], 409, 'versions_table_missing')
        row, error = _owned(cursor, version_id)
        if error:
            return error
        try:
            versions.discard(cursor, version_id)
        except ValueError as exc:
            connection.rollback()
            code = str(exc)
            return json_error(_MESSAGES.get(code, _MESSAGES['versions_unavailable']), 409, code)
        log_activity(
            session.get('user_id'), 'timetable_version_discarded', f"Discarded timetable version #{version_id} ({row.get('label') or ''})",
            entity_type='timetable_version', entity_id=version_id, old_values={'status': row.get('status'), 'slots': row.get('slot_count')},
            cursor=cursor,
        )
        connection.commit()
        return json_ok({'discarded': True, 'id': version_id})
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Timetable version discard failed')
        return json_error(_MESSAGES['versions_unavailable'], 500, 'versions_unavailable')
    finally:
        close(cursor, connection)


def _rename(version_id):
    gate = _gate(change=True)
    if gate:
        return gate
    connection = cursor = None
    try:
        payload = body(frozenset(('label',)))
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        if not versions.table_exists(cursor):
            return json_error(_MESSAGES['versions_table_missing'], 409, 'versions_table_missing')
        row, error = _owned(cursor, version_id)
        if error:
            return error
        try:
            label = versions.rename(cursor, version_id, payload.get('label'))
        except ValueError as exc:
            raise InputError(str(exc))
        connection.commit()
        return json_ok({'id': version_id, 'label': safe_text(label, 120)})
    except InputError as exc:
        return reject_input(_MESSAGES, exc.code)
    except Exception:
        if connection is not None:
            connection.rollback()
        current_app.logger.exception('Timetable version rename failed')
        return json_error(_MESSAGES['versions_unavailable'], 500, 'versions_unavailable')
    finally:
        close(cursor, connection)
