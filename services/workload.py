"""Workload norms: weekly teaching hours a designation should carry (docs/TIMETABLE.md, "Workload norms").

The norms live in the institution's `timetable_rules` row under the `_workload` key (no schema of
their own):

    {"default": {"min": 12, "max": 18}, "by_designation": {"Professor": {"min": 8, "max": 14}, ...}}

`limits_for` resolves them per teacher (designation norm, else the default). The solvers read the
maximum: as the `workload_max` soft rule (services/timetable/rules.py) and, when the capability's
`enforce` setting is `hard`, as a cap they never exceed. `assess` flags every teacher under or over
their norm for the workload report and the teacher's dashboard card. Everything is a no-op when
capability `workload_norms` is off.
"""

from core import capabilities
from services.timetable import rules as rule_set

CAPABILITY = 'workload_norms'
KEY = '_workload'
MAX_HOURS = 60
MAX_DESIGNATIONS = 40
EMPTY = {'default': {'min': None, 'max': None}, 'by_designation': {}}


def active(cursor):
    return capabilities.enabled(cursor, CAPABILITY) and rule_set.table_exists(cursor, rule_set.RULES_TABLE)


def enforcement(cursor):
    """'soft' (cost per hour over the norm) or 'hard' (the solvers never exceed it)."""
    value = capabilities.settings(cursor, CAPABILITY).get('enforce', 'soft')
    return 'hard' if value == 'hard' else 'soft'


# Norm documents --------------------------------------------------------------------------------

def _clean_bounds(given):
    if not isinstance(given, dict) or set(given) - {'min', 'max'}:
        raise ValueError('norms_invalid')
    bounds = {}
    for key in ('min', 'max'):
        value = given.get(key)
        if value in (None, ''):
            bounds[key] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= MAX_HOURS:
            raise ValueError('norms_invalid')
        bounds[key] = round(float(value), 1)
        if bounds[key] == int(bounds[key]):
            bounds[key] = int(bounds[key])
    if bounds['min'] is not None and bounds['max'] is not None and bounds['min'] > bounds['max']:
        raise ValueError('norms_invalid')
    return bounds


def clean_norms(payload):
    """Validate a norms document from the API. Raises ValueError('norms_invalid')."""
    if not isinstance(payload, dict) or set(payload) - {'default', 'by_designation'}:
        raise ValueError('norms_invalid')
    default = _clean_bounds(payload.get('default') or {})
    by_designation = {}
    given = payload.get('by_designation') or {}
    if not isinstance(given, dict) or len(given) > MAX_DESIGNATIONS:
        raise ValueError('norms_invalid')
    for name, bounds in given.items():
        if not isinstance(name, str) or not name.strip() or len(name) > 50 or any(ord(ch) < 32 for ch in name):
            raise ValueError('norms_invalid')
        cleaned = _clean_bounds(bounds or {})
        if cleaned['min'] is None and cleaned['max'] is None:
            continue
        by_designation[name.strip()] = cleaned
    return {'default': default, 'by_designation': by_designation}


def load_norms(cursor, institution_id=1):
    """(norms, stored): the saved document over EMPTY, and whether anything is saved."""
    document = rule_set.load_document(cursor, institution_id)
    raw = document.get(KEY)
    if not isinstance(raw, dict):
        return {'default': dict(EMPTY['default']), 'by_designation': {}}, False
    try:
        return clean_norms(raw), True
    except ValueError:
        return {'default': dict(EMPTY['default']), 'by_designation': {}}, False


def save_norms(cursor, institution_id, norms, updated_by=None):
    rule_set.save_private(cursor, institution_id, KEY, norms, updated_by)


def norm_for(norms, designation):
    """(min, max) for a designation: its own entry, else the default; (None, None) when neither says anything."""
    entry = None
    if designation:
        wanted = designation.strip().lower()
        entry = next((bounds for name, bounds in norms.get('by_designation', {}).items() if name.strip().lower() == wanted), None)
    if entry is None:
        entry = norms.get('default') or {}
    return entry.get('min'), entry.get('max')


# Resolution per teacher ------------------------------------------------------------------------

def _faculty_rows(cursor, *, institution_id=None, faculty_ids=None, department_id=None):
    clauses, params = ['f.user_id IS NOT NULL', 'COALESCE(f.is_active, 1) = 1'], []
    if faculty_ids is not None:
        ids = sorted({int(item) for item in faculty_ids})
        if not ids:
            return []
        clauses.append(f"f.user_id IN ({', '.join(['%s'] * len(ids))})")
        params.extend(ids)
    if department_id:
        clauses.append('f.department_id = %s')
        params.append(int(department_id))
    if institution_id and faculty_ids is None:
        clauses.append('(d.institution_id = %s OR d.institution_id IS NULL)')
        params.append(int(institution_id))
    cursor.execute(
        f"""
        SELECT f.user_id, f.name, f.designation, f.department_id, d.name AS department_name, d.institution_id
        FROM faculty f LEFT JOIN departments d ON d.id = f.department_id
        WHERE {' AND '.join(clauses)}
        ORDER BY f.name
        """,
        tuple(params),
    )
    return cursor.fetchall()


def limits_for(cursor, *, institution_id=1, faculty_ids=None):
    """{faculty user id: {'min', 'max', 'designation'}} for teachers a norm applies to; {} when inactive."""
    if not active(cursor):
        return {}
    norms, _stored = load_norms(cursor, institution_id)
    if norms['default']['max'] is None and norms['default']['min'] is None and not norms['by_designation']:
        return {}
    limits = {}
    for row in _faculty_rows(cursor, institution_id=institution_id, faculty_ids=faculty_ids):
        low, high = norm_for(norms, row.get('designation'))
        if low is None and high is None:
            continue
        limits[int(row['user_id'])] = {'min': low, 'max': high, 'designation': row.get('designation') or ''}
    return limits


def max_hours(cursor, *, institution_id=1, faculty_ids=None):
    """{faculty user id: max weekly hours} — what the solvers and rules.evaluate(norms=...) take."""
    return {fid: entry['max'] for fid, entry in limits_for(cursor, institution_id=institution_id, faculty_ids=faculty_ids).items() if entry['max'] is not None}


def weekly_hours(cursor, faculty_ids=None, *, exclude_clause=None, exclude_params=()):
    """{faculty user id: hours} of live timetable rows, optionally excluding cohorts (`exclude_clause` on alias t)."""
    clauses, params = ['t.faculty_id IS NOT NULL', 'COALESCE(t.is_active, 1) = 1'], []
    if faculty_ids is not None:
        ids = sorted({int(item) for item in faculty_ids})
        if not ids:
            return {}
        clauses.append(f"t.faculty_id IN ({', '.join(['%s'] * len(ids))})")
        params.extend(ids)
    if exclude_clause:
        clauses.append(f'NOT ({exclude_clause})')
        params.extend(exclude_params)
    cursor.execute(
        f"""
        SELECT t.faculty_id, COALESCE(SUM(TIME_TO_SEC(TIMEDIFF(t.end_time, t.start_time))), 0) / 3600 AS hours
        FROM timetable t WHERE {' AND '.join(clauses)} GROUP BY t.faculty_id
        """,
        tuple(params),
    )
    return {int(row['faculty_id']): round(float(row['hours'] or 0), 2) for row in cursor.fetchall()}


def status_of(hours, low, high):
    if high is not None and hours > float(high) + 1e-9:
        return 'over'
    if low is not None and hours < float(low) - 1e-9:
        return 'under'
    return 'ok' if (low is not None or high is not None) else 'no_norm'


def assess(cursor, *, institution_id=None, faculty_ids=None, department_id=None):
    """Per teacher: hours this week against their norm. [] when the capability is off.

    Without `institution_id` each teacher is judged by their department's institution's norms.
    Rows: {faculty_id, name, designation, department_id, department_name, hours, min, max, status}
    with status over | under | ok | no_norm, over and under first.
    """
    if not active(cursor):
        return []
    rows = _faculty_rows(cursor, institution_id=institution_id, faculty_ids=faculty_ids, department_id=department_id)
    hours = weekly_hours(cursor, [row['user_id'] for row in rows]) if rows else {}
    norms_by_institution = {}
    out = []
    for row in rows:
        owner = int(institution_id or row.get('institution_id') or 1)
        if owner not in norms_by_institution:
            norms_by_institution[owner] = load_norms(cursor, owner)[0]
        low, high = norm_for(norms_by_institution[owner], row.get('designation'))
        taught = hours.get(int(row['user_id']), 0.0)
        out.append({
            'faculty_id': int(row['user_id']), 'name': row.get('name') or '', 'designation': row.get('designation') or '',
            'department_id': row.get('department_id'), 'department_name': row.get('department_name') or '',
            'hours': taught, 'min': low, 'max': high, 'status': status_of(taught, low, high),
        })
    order = {'over': 0, 'under': 1, 'ok': 2, 'no_norm': 3}
    out.sort(key=lambda item: (order[item['status']], -item['hours'], item['name']))
    return out


def designations(cursor, institution_id=None):
    """Distinct designations in use, for the norms editor."""
    clause, params = '', ()
    if institution_id:
        clause, params = ' AND (d.institution_id = %s OR d.institution_id IS NULL)', (int(institution_id),)
    cursor.execute(
        f"SELECT DISTINCT TRIM(f.designation) AS designation FROM faculty f LEFT JOIN departments d ON d.id = f.department_id "
        f"WHERE f.designation IS NOT NULL AND TRIM(f.designation) <> ''{clause} ORDER BY designation",
        params,
    )
    return [row['designation'] for row in cursor.fetchall()]
