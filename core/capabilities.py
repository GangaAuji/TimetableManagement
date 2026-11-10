"""Optional features ("capabilities") and the one rule that keeps them optional.

A capability is on only when BOTH hold:
  1. the server flag ``FEATURE_<NAME>`` (config, from the environment; the operator's kill switch,
     true unless set off - like ``NOTIFICATIONS_ENABLED``), and
  2. the tenant says so: the row in ``capabilities`` has ``enabled = 1``, or there is no row yet and
     the registry default for that capability is on.

A missing table (revision 0015 not applied) means every capability is off. Capabilities whose
registry default is on are designed so that "on with nothing configured" behaves exactly like
today (e.g. rules with built-in weights); everything that needs a provider or a workflow is off.
The application never depends on a capability being on: routes behind ``require_capability``
answer 404 ``capability_off``, the UI hides the entry, background work is skipped.

Answers are cached on ``flask.g`` for the request; ``forget()`` clears them after a save.
"""

import json
from dataclasses import dataclass, field

from flask import current_app, g, has_app_context, has_request_context

TABLE = 'capabilities'


@dataclass(frozen=True)
class Capability:
    name: str
    title: str
    description: str
    phase: str
    default: bool = False                           # tenant state when no row has been saved yet
    settings: dict = field(default_factory=dict)   # key -> (kind, default); kind in int|bool|str|choice:a|b
    listed: bool = True                            # False: kept in the registry, omitted from Settings → Capabilities


CAPABILITIES = (
    Capability(
        'timetable_preferences', 'Timetable preferences and rules',
        'Faculty day/time preferences and institution rules weighed by the solver; results explain each violation.',
        'J1', True,
        {'default_weight': ('int', 3)},
    ),
    Capability(
        'timetable_versions', 'Timetable drafts and publishing',
        'Generation writes a draft; compare drafts and publish one. Published rows stay the active timetable.',
        'J2', True,
        {'keep_drafts': ('int', 10)},
    ),
    Capability(
        'timetable_grid', 'Interactive grid',
        'Drag-and-drop editing with live clash checks, faculty and room views.',
        'J3', True,
    ),
    Capability(
        'bookings', 'Room bookings',
        'Events, exams and maintenance reserve rooms on the same clash ledger the timetable uses.',
        'J4', False,
        {'requires_approval': ('bool', True)},
    ),
    Capability(
        'workload_norms', 'Workload norms',
        'Weekly hour norms per designation; the solver and reports flag over- and under-load.',
        'J5', False,
        {'enforce': ('choice:soft|hard', 'soft')},
    ),
    Capability('academic_terms', 'Academic calendar', 'Terms, teaching weeks and week-specific timetables.', 'K1'),
    Capability('syllabus', 'Syllabus coverage', 'Units per subject and lesson logs against the timetable.', 'K2'),
    Capability('assessments', 'Internal assessment', 'Marks components, entry, CO/PO attainment.', 'K3'),
    Capability('exams', 'Exam timetable', 'Exam sessions, seating and invigilation duties.', 'K4'),
    Capability(
        'two_factor', 'Second factor (TOTP)',
        'Authenticator app at sign-in, with one-time recovery codes. Optional asks only people who have enrolled. '
        'Staff requires Super Admin, Admin and HOD. Everyone requires every role. Enroll from Profile.',
        'L1', False,
        {'required': ('choice:optional|staff|everyone', 'optional')},
    ),
    Capability(
        'security_policy', 'Security policy',
        'Password length, complexity and expiry, session idle time, a limit on concurrent sessions, '
        'an admin network list, and a notice when someone signs in. Saved rules apply from the next sign-in.',
        'L1', False,
    ),
    Capability('privacy_tools', 'Privacy tools', 'Data export, erasure and retention (DPDP).', 'L2', False, {}, False),
    Capability('channels', 'Message channels', 'WhatsApp, SMS and web push beside e-mail, with routing and fallback.', 'I1', False, {}, False),
    Capability('guardians', 'Parent portal', 'Guardians see attendance and the timetable of their wards.', 'I2', False, {}, False),
    Capability(
        'calendar_feeds', 'Calendar feeds',
        'Subscribe to a personal timetable (.ics) from any calendar app.', 'I3', True, {}, False,
    ),
    Capability('attendance_policies', 'Attendance policies', 'Thresholds, condonation and shortage notices per course.', 'I4', False, {}, False),
)
BY_NAME = {item.name: item for item in CAPABILITIES}
NAMES = tuple(item.name for item in CAPABILITIES)


def flag_name(name):
    return f'FEATURE_{name.upper()}'


def flag_on(name):
    """The server-side switch: ``FEATURE_<NAME>`` in config, true unless the operator set it off.

    Outside an app context, or for an unknown name, the answer is off.
    """
    if name not in BY_NAME or not has_app_context():
        return False
    return bool(current_app.config.get(flag_name(name), True))


def table_exists(cursor, name=TABLE):
    cursor.execute(
        'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1', (name,),
    )
    return cursor.fetchone() is not None


def _parse_settings(raw):
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _cache():
    if not has_request_context():
        return None
    store = getattr(g, '_capabilities', None)
    if store is None:
        store = g._capabilities = {}
    return store


def forget():
    if has_request_context() and hasattr(g, '_capabilities'):
        del g._capabilities


def load_rows(cursor):
    """{name: {'enabled': bool, 'settings': dict, 'updated_at': ...}} for every registered capability.

    A missing table disables everything. A missing row takes the registry default (``stored`` False).
    Nothing is written.
    """
    cache = _cache()
    if cache is not None and 'rows' in cache:
        return cache['rows']
    exists = table_exists(cursor)
    rows = {
        name: {'enabled': exists and BY_NAME[name].default, 'stored': False, 'settings': {}, 'updated_at': None, 'updated_by': None}
        for name in NAMES
    }
    if exists:
        cursor.execute(f'SELECT capability, enabled, settings_json, updated_by, updated_at FROM {TABLE}')
        for row in cursor.fetchall() or []:
            name = row.get('capability')
            if name in rows:
                rows[name] = {
                    'enabled': bool(row.get('enabled')),
                    'stored': True,
                    'settings': _parse_settings(row.get('settings_json')),
                    'updated_at': row.get('updated_at'),
                    'updated_by': row.get('updated_by'),
                }
    if cache is not None:
        cache['rows'] = rows
    return rows


def enabled(cursor, name):
    """True only when the flag and the tenant row are both on."""
    if not flag_on(name):
        return False
    return bool(load_rows(cursor)[name]['enabled'])


def settings(cursor, name):
    """Effective settings: registry defaults overlaid by the stored, type-checked values."""
    spec = BY_NAME[name].settings
    values = {key: default for key, (_kind, default) in spec.items()}
    stored = load_rows(cursor)[name]['settings']
    for key, (kind, _default) in spec.items():
        if key in stored:
            cleaned = clean_setting(kind, stored[key])
            if cleaned is not None:
                values[key] = cleaned
    return values


def clean_setting(kind, value):
    """The value coerced to its kind, or None when it does not fit."""
    if kind == 'bool':
        return value if isinstance(value, bool) else None
    if kind == 'int':
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
            return None
        return value
    if kind == 'str':
        return value if isinstance(value, str) and len(value) <= 200 else None
    if kind.startswith('choice:'):
        return value if isinstance(value, str) and value in kind[7:].split('|') else None
    return None


def clean_settings(name, payload):
    """Validate a settings object against the registry; raises ValueError('capability_invalid')."""
    if not isinstance(payload, dict):
        raise ValueError('capability_invalid')
    spec = BY_NAME[name].settings
    if set(payload) - set(spec):
        raise ValueError('capability_invalid')
    values = {}
    for key, value in payload.items():
        cleaned = clean_setting(spec[key][0], value)
        if cleaned is None:
            raise ValueError('capability_invalid')
        values[key] = cleaned
    return values


def save(cursor, name, *, enabled_value=None, settings_values=None, updated_by=None):
    """Upsert the tenant row; the table must exist. Settings replace only the keys given."""
    if name not in BY_NAME:
        raise ValueError('capability_unknown')
    if not table_exists(cursor):
        raise RuntimeError('capabilities_table_missing')
    current = load_rows(cursor)[name]
    merged = dict(current['settings'])
    if settings_values is not None:
        merged.update(clean_settings(name, settings_values))
    new_enabled = current['enabled'] if enabled_value is None else bool(enabled_value)
    cursor.execute(
        f"""
        INSERT INTO {TABLE} (capability, enabled, settings_json, updated_by)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE enabled = VALUES(enabled), settings_json = VALUES(settings_json),
                                updated_by = VALUES(updated_by)
        """,
        (name, 1 if new_enabled else 0, json.dumps(merged, sort_keys=True), updated_by),
    )
    forget()


def snapshot(cursor):
    """{name: bool} of effective state - what the session payload and the UI consume."""
    rows = load_rows(cursor)
    return {name: flag_on(name) and bool(rows[name]['enabled']) for name in NAMES}


def describe(cursor):
    """Per-capability detail for the settings page (flag, row, effective, settings schema)."""
    rows = load_rows(cursor)
    exists = table_exists(cursor)
    items = []
    for item in CAPABILITIES:
        if not item.listed:
            continue
        row = rows[item.name]
        items.append({
            'name': item.name,
            'title': item.title,
            'description': item.description,
            'phase': item.phase,
            'flag': flag_on(item.name),
            'enabled': row['enabled'],
            'stored': row['stored'],
            'default': item.default,
            'effective': flag_on(item.name) and row['enabled'],
            'settings': settings(cursor, item.name),
            'schema': {key: {'kind': kind, 'default': default} for key, (kind, default) in item.settings.items()},
        })
    return {'table_exists': exists, 'capabilities': items}


def require_capability(name):
    """Route guard: a JSON 404 ``capability_off`` response when the capability is off, else None.

    Opens its own connection so callers may use it before theirs; the result is cached per request.
    """
    from api.web.access import close
    from api.web.responses import json_error
    from extensions import get_db_connection

    cache = _cache()
    if cache is not None and ('on', name) in cache:
        on = cache[('on', name)]
    else:
        on = False
        if flag_on(name):
            connection = cursor = None
            try:
                connection = get_db_connection()
                cursor = connection.cursor(dictionary=True)
                on = enabled(cursor, name)
            except Exception:
                current_app.logger.exception('Capability check failed')
                on = False
            finally:
                close(cursor, connection)
        if cache is not None:
            cache[('on', name)] = on
    if on:
        return None
    return json_error('This feature is not enabled.', 404, 'capability_off')
