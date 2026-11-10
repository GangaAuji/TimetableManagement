"""Timetable versions: drafts, compare, publish and rollback (docs/TIMETABLE.md, "Versions").

Everything here is a no-op unless capability `timetable_versions` is on and revision 0017 is
applied (`active()`). With it on, generation writes a *draft*: new rows with `is_active = 0` and
`version_id` set, so the published timetable is untouched until someone publishes the draft.
Publishing flips the rows for every cohort the draft covers in one transaction, archives the old
rows to `timetable_history` as the generator always did, and marks superseded versions archived.
Rollback is publishing an archived version again.

Readers never change: they keep selecting `COALESCE(is_active, 1) = 1`.
"""

import json
from collections import defaultdict
from datetime import datetime, time, timedelta

from core import capabilities

CAPABILITY = 'timetable_versions'
STATUSES = ('draft', 'published', 'archived')
MAX_LABEL = 120
MAX_LIST = 100
DEFAULT_KEEP = 10
_MAX_SLOTS = 5000

_COHORT = 'course_id = %s AND class_id = %s AND division_id = %s'


def _has_table(cursor, name):
    cursor.execute(
        'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1', (name,),
    )
    return cursor.fetchone() is not None


def _has_column(cursor, table, column):
    cursor.execute(
        'SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s LIMIT 1',
        (table, column),
    )
    return cursor.fetchone() is not None


def table_exists(cursor):
    """Revision 0017 applied: both tables and the `timetable.version_id` column."""
    return (
        _has_table(cursor, 'timetable_versions')
        and _has_table(cursor, 'timetable_version_cohorts')
        and _has_column(cursor, 'timetable', 'version_id')
    )


def active(cursor):
    """Whether generation should write drafts: capability on and schema present."""
    return capabilities.enabled(cursor, CAPABILITY) and table_exists(cursor)


def keep_drafts(cursor):
    value = capabilities.settings(cursor, CAPABILITY).get('keep_drafts', DEFAULT_KEEP)
    try:
        return max(1, min(100, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_KEEP


def _cohort(target):
    return (int(target['course_id']), int(target['class_id']), int(target['division_id']))


def _hhmm(value):
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        return f'{total // 3600:02d}:{(total % 3600) // 60:02d}'
    if isinstance(value, (time, datetime)):
        return value.strftime('%H:%M')
    text = str(value or '')
    return text[:5] if len(text) >= 5 else text


def _json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


# Drafts -------------------------------------------------------------------------------------------

def published_version_for(cursor, course_id, class_id, division_id):
    """The published version currently covering a cohort, or None (legacy rows have none)."""
    cursor.execute(
        """
        SELECT v.id FROM timetable_versions v
        JOIN timetable_version_cohorts c ON c.version_id = v.id
        WHERE v.status = 'published' AND c.course_id = %s AND c.class_id = %s AND c.division_id = %s
        ORDER BY v.published_at DESC LIMIT 1
        """,
        (int(course_id), int(class_id), int(division_id)),
    )
    row = cursor.fetchone()
    return int(row['id']) if row else None


def create_draft(cursor, *, institution_id, targets, solver, settings=None, created_by=None, job_id=None, label=None):
    """Insert a draft version covering `targets` and return its id. Prunes old drafts past `keep_drafts`."""
    cohorts = sorted({_cohort(target) for target in targets if isinstance(target, dict)})
    if not cohorts:
        raise ValueError('version_no_cohorts')
    parent = published_version_for(cursor, *cohorts[0])
    text = (label or '').strip()[:MAX_LABEL] or f"Generated {datetime.now().strftime('%d %b %Y %H:%M')}"
    stored = {k: v for k, v in (settings or {}).items() if k != 'targets'}
    cursor.execute(
        """
        INSERT INTO timetable_versions (institution_id, label, status, solver, job_id, parent_version_id, settings_json, created_by)
        VALUES (%s, %s, 'draft', %s, %s, %s, %s, %s)
        """,
        (int(institution_id or 1), text, str(solver or 'greedy')[:20], job_id, parent, json.dumps(stored), created_by),
    )
    version_id = int(cursor.lastrowid)
    cursor.executemany(
        'INSERT INTO timetable_version_cohorts (version_id, course_id, class_id, division_id) VALUES (%s, %s, %s, %s)',
        [(version_id,) + cohort for cohort in cohorts],
    )
    prune_drafts(cursor, int(institution_id or 1), keep_drafts(cursor), protect=version_id)
    return version_id


def prune_drafts(cursor, institution_id, keep, *, protect=None):
    """Delete the oldest drafts of an institution beyond `keep`. Returns how many went."""
    cursor.execute(
        "SELECT id FROM timetable_versions WHERE institution_id = %s AND status = 'draft' ORDER BY created_at DESC, id DESC",
        (int(institution_id),),
    )
    ids = [int(row['id']) for row in cursor.fetchall() if protect is None or int(row['id']) != protect]
    removed = 0
    for version_id in ids[max(0, keep - (1 if protect else 0)):]:
        _delete_rows(cursor, version_id)
        cursor.execute('DELETE FROM timetable_versions WHERE id = %s', (version_id,))
        removed += 1
    return removed


def _delete_rows(cursor, version_id):
    """Remove a version's inactive rows. Active rows (a published version) are never touched here."""
    cursor.execute('DELETE FROM timetable WHERE version_id = %s AND COALESCE(is_active, 1) = 0', (int(version_id),))


def record_score(cursor, version_id, scores):
    """Store per-cohort scores: {"course-class-division": {quality_score, rule_cost, assigned, unassigned}}."""
    cursor.execute('UPDATE timetable_versions SET score_json = %s WHERE id = %s', (json.dumps(scores), int(version_id)))


def slot_count(cursor, version_id):
    cursor.execute('SELECT COUNT(*) AS n FROM timetable WHERE version_id = %s', (int(version_id),))
    return int((cursor.fetchone() or {}).get('n') or 0)


def busy_clause(version_id, alias='t'):
    """SQL for rows the greedy generator must treat as busy while writing draft `version_id`.

    Active rows of cohorts outside the version, plus the version's own draft rows (other cohorts of
    the same job placed earlier). Live rows of cohorts the version will replace are ignored.
    """
    return (
        f"((COALESCE({alias}.is_active, 1) = 1 AND NOT EXISTS ("
        f"SELECT 1 FROM timetable_version_cohorts vc WHERE vc.version_id = %s AND vc.course_id = {alias}.course_id "
        f"AND vc.class_id = {alias}.class_id AND vc.division_id = {alias}.division_id)) OR {alias}.version_id = %s)",
        (int(version_id), int(version_id)),
    )


# Publish -------------------------------------------------------------------------------------------

def load(cursor, version_id):
    cursor.execute(
        """
        SELECT v.id, v.institution_id, v.label, v.status, v.solver, v.job_id, v.parent_version_id, v.settings_json,
               v.score_json, v.created_by, v.created_at, v.published_by, v.published_at,
               cu.username AS created_by_name, pu.username AS published_by_name
        FROM timetable_versions v
        LEFT JOIN users cu ON cu.id = v.created_by
        LEFT JOIN users pu ON pu.id = v.published_by
        WHERE v.id = %s
        """,
        (int(version_id),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    row['cohorts'] = cohorts_of(cursor, version_id)
    row['slot_count'] = slot_count(cursor, version_id)
    return row


def cohorts_of(cursor, version_id):
    cursor.execute(
        """
        SELECT vc.course_id, vc.class_id, vc.division_id, c.name AS course_name, cl.name AS class_name, d.name AS division_name
        FROM timetable_version_cohorts vc
        LEFT JOIN courses c ON c.id = vc.course_id
        LEFT JOIN classes cl ON cl.id = vc.class_id
        LEFT JOIN divisions d ON d.id = vc.division_id
        WHERE vc.version_id = %s
        ORDER BY c.name, cl.name, d.name
        """,
        (int(version_id),),
    )
    return cursor.fetchall()


def publish(cursor, version_id, *, published_by=None):
    """Make `version_id` the live timetable for every cohort it has rows for. Caller commits.

    Returns {'cohorts': n, 'slots': n, 'skipped': [cohorts without rows]}. Raises ValueError
    ('version_not_found', 'version_already_published', 'version_empty').
    """
    from services.webhooks import on_timetable_published

    version = load(cursor, version_id)
    if not version:
        raise ValueError('version_not_found')
    if version['status'] == 'published':
        raise ValueError('version_already_published')
    published = 0
    slots = 0
    skipped = []
    for cohort in version['cohorts']:
        key = (int(cohort['course_id']), int(cohort['class_id']), int(cohort['division_id']))
        cursor.execute(f'SELECT COUNT(*) AS n FROM timetable WHERE version_id = %s AND {_COHORT}', (int(version_id),) + key)
        count = int((cursor.fetchone() or {}).get('n') or 0)
        if not count:
            skipped.append(cohort)
            continue
        try:
            cursor.execute(
                f"""
                INSERT INTO timetable_history
                (course_id, class_id, division_id, day_of_week, start_time, end_time, subject_id, faculty_id, room_id, archived_at)
                SELECT course_id, class_id, division_id, day_of_week, start_time, end_time, subject_id, faculty_id, room_id, NOW()
                FROM timetable WHERE {_COHORT} AND COALESCE(is_active, 1) = 1 AND (version_id IS NULL OR version_id <> %s)
                """,
                key + (int(version_id),),
            )
        except Exception:
            pass
        cursor.execute(
            f'UPDATE timetable SET is_active = 0 WHERE {_COHORT} AND COALESCE(is_active, 1) = 1 AND (version_id IS NULL OR version_id <> %s)',
            key + (int(version_id),),
        )
        cursor.execute(f'UPDATE timetable SET is_active = 1 WHERE {_COHORT} AND version_id = %s', key + (int(version_id),))
        published += 1
        slots += count
        on_timetable_published(
            cursor, course_id=key[0], class_id=key[1], division_id=key[2], reason='published', slot_count=count,
            solver=version.get('solver'),
        )
    if not published:
        raise ValueError('version_empty')
    cursor.execute(
        """
        UPDATE timetable_versions v SET v.status = 'archived'
        WHERE v.status = 'published' AND v.id <> %s
          AND NOT EXISTS (SELECT 1 FROM timetable t WHERE t.version_id = v.id AND COALESCE(t.is_active, 1) = 1)
        """,
        (int(version_id),),
    )
    cursor.execute(
        "UPDATE timetable_versions SET status = 'published', published_by = %s, published_at = NOW() WHERE id = %s",
        (published_by, int(version_id)),
    )
    return {'cohorts': published, 'slots': slots, 'skipped': skipped}


def discard(cursor, version_id):
    """Delete a draft or archived version and its inactive rows. Raises ValueError for published ones."""
    version = load(cursor, version_id)
    if not version:
        raise ValueError('version_not_found')
    if version['status'] == 'published':
        raise ValueError('version_published')
    _delete_rows(cursor, version_id)
    cursor.execute('DELETE FROM timetable_versions WHERE id = %s', (int(version_id),))
    return version


def rename(cursor, version_id, label):
    text = str(label or '').strip()
    if not text or len(text) > MAX_LABEL:
        raise ValueError('label_invalid')
    cursor.execute('UPDATE timetable_versions SET label = %s WHERE id = %s', (text, int(version_id)))
    return text


# Listing and slots ---------------------------------------------------------------------------------

def list_versions(cursor, *, scope_clause=('1=1', ()), cohort=None, status=None, limit=MAX_LIST):
    clauses = [scope_clause[0]]
    params = list(scope_clause[1])
    if cohort:
        clauses.append(
            'v.id IN (SELECT vc.version_id FROM timetable_version_cohorts vc WHERE vc.course_id = %s AND vc.class_id = %s AND vc.division_id = %s)'
        )
        params.extend(_cohort(cohort))
    if status in STATUSES:
        clauses.append('v.status = %s')
        params.append(status)
    cursor.execute(
        f"""
        SELECT v.id, v.institution_id, v.label, v.status, v.solver, v.job_id, v.parent_version_id, v.score_json,
               v.created_by, v.created_at, v.published_by, v.published_at,
               cu.username AS created_by_name, pu.username AS published_by_name,
               (SELECT COUNT(*) FROM timetable t WHERE t.version_id = v.id) AS slot_count,
               (SELECT COUNT(*) FROM timetable_version_cohorts vc WHERE vc.version_id = v.id) AS cohort_count
        FROM timetable_versions v
        LEFT JOIN users cu ON cu.id = v.created_by
        LEFT JOIN users pu ON pu.id = v.published_by
        WHERE {' AND '.join(clauses)}
        ORDER BY FIELD(v.status, 'published', 'draft', 'archived'), v.created_at DESC, v.id DESC
        LIMIT %s
        """,
        tuple(params) + (int(limit),),
    )
    rows = cursor.fetchall()
    for row in rows:
        row['cohorts'] = cohorts_of(cursor, row['id'])
    return rows


_SLOT_SELECT = """
    SELECT t.id, t.course_id, t.class_id, t.division_id, t.day_of_week, t.start_time, t.end_time, t.subject_id,
           COALESCE(s.name, '') AS subject_name, t.faculty_id, COALESCE(f.name, '') AS faculty_name,
           t.room_id, COALESCE(r.room_number, '') AS room_number, t.lab_batch_group_id,
           COALESCE(g.name, '') AS batch_name, t.version_id, COALESCE(t.is_active, 1) AS is_active
    FROM timetable t
    LEFT JOIN subjects s ON s.id = t.subject_id
    LEFT JOIN faculty f ON f.user_id = t.faculty_id
    LEFT JOIN rooms r ON r.id = t.room_id
    LEFT JOIN lab_batch_groups g ON g.id = t.lab_batch_group_id
"""


def version_slots(cursor, version_id):
    cursor.execute(f'{_SLOT_SELECT} WHERE t.version_id = %s ORDER BY t.course_id, t.class_id, t.division_id, t.day_of_week, t.start_time LIMIT %s', (int(version_id), _MAX_SLOTS))
    return [_slot(row) for row in cursor.fetchall()]


def live_slots(cursor, cohorts):
    """Active rows of the given cohorts (what students and teachers see today)."""
    keys = sorted({_cohort(c) for c in cohorts})
    if not keys:
        return []
    clause = ' OR '.join(['(t.course_id = %s AND t.class_id = %s AND t.division_id = %s)'] * len(keys))
    params = tuple(value for key in keys for value in key)
    cursor.execute(
        f'{_SLOT_SELECT} WHERE ({clause}) AND COALESCE(t.is_active, 1) = 1 ORDER BY t.course_id, t.class_id, t.division_id, t.day_of_week, t.start_time LIMIT %s',
        params + (_MAX_SLOTS,),
    )
    return [_slot(row) for row in cursor.fetchall()]


def _slot(row):
    return {
        'id': int(row['id']),
        'course_id': int(row['course_id']),
        'class_id': int(row['class_id']),
        'division_id': int(row['division_id'] or 0),
        'day': str(row['day_of_week']),
        'start_time': _hhmm(row['start_time']),
        'end_time': _hhmm(row['end_time']),
        'subject_id': int(row['subject_id'] or 0),
        'subject_name': row.get('subject_name') or '',
        'faculty_id': int(row['faculty_id'] or 0),
        'faculty_name': row.get('faculty_name') or '',
        'room_id': int(row['room_id']) if row.get('room_id') else None,
        'room_number': row.get('room_number') or '',
        'lab_batch_group_id': int(row['lab_batch_group_id']) if row.get('lab_batch_group_id') else None,
        'batch_name': row.get('batch_name') or '',
        'version_id': int(row['version_id']) if row.get('version_id') else None,
        'is_active': bool(row.get('is_active', 1)),
    }


# Compare -------------------------------------------------------------------------------------------

def _cohort_key(slot):
    return (slot['course_id'], slot['class_id'], slot['division_id'])


def _session_key(slot):
    return (slot['subject_id'], slot['faculty_id'], slot['lab_batch_group_id'])


def _cell_key(slot):
    return (slot['day'], slot['start_time'], slot['end_time'])


def _change(kind, before, after):
    base = after or before
    return {
        'kind': kind,
        'subject_id': base['subject_id'],
        'subject_name': base['subject_name'],
        'faculty_id': base['faculty_id'],
        'faculty_name': base['faculty_name'],
        'batch_name': base['batch_name'],
        'before': {'day': before['day'], 'start_time': before['start_time'], 'end_time': before['end_time'], 'room_number': before['room_number']} if before else None,
        'after': {'day': after['day'], 'start_time': after['start_time'], 'end_time': after['end_time'], 'room_number': after['room_number']} if after else None,
    }


def diff(left, right):
    """Compare two slot lists (`left` = before, `right` = after). Pure.

    Per cohort: `unchanged`, `room_changed` (same cell and session, other room), `moved` (same
    session, other cell), `removed` (only on the left), `added` (only on the right). Also per-faculty
    counts of changes, so a HOD sees who is affected before publishing.
    """
    by_cohort = defaultdict(lambda: ([], []))
    for slot in left:
        by_cohort[_cohort_key(slot)][0].append(slot)
    for slot in right:
        by_cohort[_cohort_key(slot)][1].append(slot)
    cohorts = []
    totals = defaultdict(int)
    by_faculty = defaultdict(lambda: {'faculty_id': 0, 'faculty_name': '', 'moved': 0, 'added': 0, 'removed': 0, 'room_changed': 0})
    for key in sorted(by_cohort):
        before, after = by_cohort[key]
        changes = _diff_cohort(before, after)
        counts = defaultdict(int)
        for change in changes:
            counts[change['kind']] += 1
            totals[change['kind']] += 1
            if change['kind'] != 'unchanged':
                entry = by_faculty[change['faculty_id']]
                entry['faculty_id'] = change['faculty_id']
                entry['faculty_name'] = change['faculty_name']
                entry[change['kind']] += 1
        cohorts.append({
            'course_id': key[0], 'class_id': key[1], 'division_id': key[2],
            'counts': dict(counts),
            'changes': [change for change in changes if change['kind'] != 'unchanged'],
            'before': before,
            'after': after,
        })
    return {
        'totals': dict(totals),
        'cohorts': cohorts,
        'faculty': sorted(by_faculty.values(), key=lambda item: (-(item['moved'] + item['added'] + item['removed'] + item['room_changed']), item['faculty_name'])),
    }


def _diff_cohort(before, after):
    left_by_cell = defaultdict(list)
    for slot in before:
        left_by_cell[_cell_key(slot)].append(slot)
    changes = []
    loose_right = []
    for slot in after:
        candidates = left_by_cell.get(_cell_key(slot)) or []
        match = next((c for c in candidates if _session_key(c) == _session_key(slot)), None)
        if match is None:
            loose_right.append(slot)
            continue
        candidates.remove(match)
        changes.append(_change('unchanged' if match['room_id'] == slot['room_id'] else 'room_changed', match, slot))
    loose_left = [slot for cells in left_by_cell.values() for slot in cells]
    left_by_session = defaultdict(list)
    for slot in loose_left:
        left_by_session[_session_key(slot)].append(slot)
    for slot in loose_right:
        pool = left_by_session.get(_session_key(slot))
        if pool:
            changes.append(_change('moved', pool.pop(0), slot))
        else:
            changes.append(_change('added', None, slot))
    for pool in left_by_session.values():
        for slot in pool:
            changes.append(_change('removed', slot, None))
    order = {'removed': 0, 'added': 1, 'moved': 2, 'room_changed': 3, 'unchanged': 4}
    return sorted(changes, key=lambda change: (order[change['kind']], change['subject_name'], change['faculty_name']))


def scores(version_row):
    """The stored score document of a version row, or {}."""
    parsed = _json((version_row or {}).get('score_json'))
    return parsed if isinstance(parsed, dict) else {}


def summarize_scores(score_doc):
    """Average quality and total rule cost over the cohorts of a score document."""
    items = [v for v in (score_doc or {}).values() if isinstance(v, dict)]
    if not items:
        return {'quality_score': None, 'rule_cost': None, 'assigned': 0, 'unassigned': 0}
    quality = [float(v.get('quality_score') or 0) for v in items if v.get('quality_score') is not None]
    return {
        'quality_score': round(sum(quality) / len(quality), 2) if quality else None,
        'rule_cost': sum(int(v.get('rule_cost') or 0) for v in items),
        'assigned': sum(int(v.get('assigned') or 0) for v in items),
        'unassigned': sum(int(v.get('unassigned') or 0) for v in items),
    }
