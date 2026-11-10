"""Soft timetable rules and faculty preferences (docs/TIMETABLE.md, "Rules and preferences").

One registry of weighted rules is read by the joint solver (as objective terms), the greedy
generator (to rank its candidates) and the quality model (for its thresholds), so every path
agrees on what a good timetable is. `evaluate()` explains a timetable: which rule, who, where,
at what cost.

Capability `timetable_preferences` gates all of it. With it off - or revision 0016 not applied -
`effective_rules()` returns `legacy_rules()`, the objective the solver has always used, and no
preferences are loaded; behaviour is then unchanged.

Weights are integers 0-20: the cost of one violation. 0 switches a rule off.
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import time, timedelta

WEEKDAY_ORDER = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
RULES_TABLE = 'timetable_rules'
PREFERENCES_TABLE = 'faculty_preferences'
MAX_WEIGHT = 20
PREFERENCE_KINDS = ('preferred', 'avoid')
_TIME = re.compile(r'^\d{2}:\d{2}$')


@dataclass(frozen=True)
class Rule:
    name: str
    title: str
    description: str
    default: int
    scope: str                                     # 'faculty' or 'cohort'
    params: dict = field(default_factory=dict)     # name -> (kind, default); kind int|time


RULES = (
    Rule('faculty_preferences', 'Faculty preferences',
         'Keep sessions out of windows a teacher asked to avoid and inside the ones they prefer; '
         'cost is this weight times the preference weight (1-5).', 5, 'faculty'),
    Rule('max_hours_per_day', 'Hours per day', 'Each hour a teacher is scheduled beyond this many in one day.',
         6, 'faculty', {'hours': ('int', 5)}),
    Rule('max_consecutive_hours', 'Consecutive hours', 'Each hour a teacher teaches back to back beyond this many.',
         6, 'faculty', {'hours': ('int', 3)}),
    Rule('idle_gaps_students', 'Student idle gaps', 'Each empty slot between a class\'s first and last session of the day.',
         4, 'cohort'),
    Rule('idle_gaps_faculty', 'Faculty idle gaps', 'Each empty slot between a teacher\'s first and last session of the day.',
         2, 'faculty'),
    Rule('room_changes', 'Room changes', 'Each time a class moves to a different room between consecutive sessions.',
         1, 'cohort'),
    Rule('spread_subject', 'Spread subjects', 'Each repeat of a subject for the same class on one day (never more than two).',
         10, 'cohort'),
    Rule('lab_blocks_contiguous', 'Contiguous labs', 'Each practical hour of a subject on one day that is not next to the others.',
         4, 'cohort'),
    Rule('no_first_hour_after_evening', 'No first hour after a late finish',
         'A teacher in the last slot of one day and the first slot of the next.', 3, 'faculty'),
    Rule('lunch_window', 'Lunch window', 'Each session overlapping the lunch window (leave the times empty to disable).',
         3, 'cohort', {'start': ('time', ''), 'end': ('time', '')}),
    Rule('prefer_early', 'Prefer early slots', 'A small cost per slot index so days fill from the morning.',
         1, 'cohort'),
    Rule('workload_max', 'Weekly workload',
         'Each hour a teacher is scheduled in the week beyond the norm for their designation '
         '(Workload norms; nothing when the capability is off or no norm applies).', 6, 'faculty'),
)
BY_NAME = {rule.name: rule for rule in RULES}
NAMES = tuple(rule.name for rule in RULES)


# Rule sets ------------------------------------------------------------------------------------

def default_rules():
    """The registry defaults: what a tenant gets once the capability is on and nothing is saved."""
    return {
        rule.name: {'weight': rule.default, **{key: default for key, (_kind, default) in rule.params.items()}}
        for rule in RULES
    }


def legacy_rules():
    """The objective the joint solver used before rules existed: spread subjects (10) and early slots (1)."""
    rules = {name: {**values, 'weight': 0} for name, values in default_rules().items()}
    rules['spread_subject']['weight'] = 10
    rules['prefer_early']['weight'] = 1
    return rules


def _clean_param(kind, value):
    if kind == 'int':
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 12:
            raise ValueError('rules_invalid')
        return value
    if kind == 'time':
        if value in (None, ''):
            return ''
        if not isinstance(value, str) or not _TIME.match(value) or int(value[:2]) > 23 or int(value[3:]) > 59:
            raise ValueError('rules_invalid')
        return value
    raise ValueError('rules_invalid')


def clean_rules(payload, *, partial=False):
    """Validate a rules object against the registry. Raises ValueError('rules_invalid').

    With `partial` the result holds only the rules given (for overrides); otherwise missing rules
    take their defaults so the stored document is always complete.
    """
    if not isinstance(payload, dict) or set(payload) - set(NAMES):
        raise ValueError('rules_invalid')
    cleaned = {} if partial else default_rules()
    for name, given in payload.items():
        rule = BY_NAME[name]
        if not isinstance(given, dict) or set(given) - ({'weight'} | set(rule.params)):
            raise ValueError('rules_invalid')
        values = dict(cleaned.get(name) or {'weight': rule.default, **{k: d for k, (_, d) in rule.params.items()}})
        if 'weight' in given:
            weight = given['weight']
            if isinstance(weight, bool) or not isinstance(weight, int) or not 0 <= weight <= MAX_WEIGHT:
                raise ValueError('rules_invalid')
            values['weight'] = weight
        for key, (kind, _default) in rule.params.items():
            if key in given:
                values[key] = _clean_param(kind, given[key])
        if partial:
            cleaned[name] = {k: v for k, v in values.items() if k == 'weight' or k in given}
        else:
            cleaned[name] = values
    return cleaned


def merge_rules(base, override):
    """`base` with the weights/params in `override` applied (override already cleaned, partial)."""
    merged = {name: dict(values) for name, values in base.items()}
    for name, values in (override or {}).items():
        merged.setdefault(name, {}).update(values)
    return merged


# Storage ---------------------------------------------------------------------------------------

def table_exists(cursor, name):
    cursor.execute(
        'SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1', (name,),
    )
    return cursor.fetchone() is not None


def load_rules(cursor, institution_id=1):
    """(rules, stored): the institution's saved rules over the defaults, and whether a row exists."""
    rules = default_rules()
    if not table_exists(cursor, RULES_TABLE):
        return rules, False
    cursor.execute(f'SELECT rules_json FROM {RULES_TABLE} WHERE institution_id = %s', (int(institution_id or 1),))
    row = cursor.fetchone()
    if not row:
        return rules, False
    try:
        stored = json.loads(row['rules_json'] or '{}')
        # Keys starting with '_' hold other institution documents (e.g. `_workload`, services/workload.py).
        stored = clean_rules({k: v for k, v in stored.items() if not str(k).startswith('_')}, partial=True) if isinstance(stored, dict) else {}
    except (TypeError, ValueError):
        stored = {}
    return merge_rules(rules, stored), True


def save_rules(cursor, institution_id, rules, updated_by=None):
    """Upsert the institution's complete rules document (already cleaned). Other `_` documents in the row are kept."""
    if not table_exists(cursor, RULES_TABLE):
        raise RuntimeError('rules_table_missing')
    document = dict(load_document(cursor, institution_id, private_only=True))
    document.update(rules)
    cursor.execute(
        f"""
        INSERT INTO {RULES_TABLE} (institution_id, rules_json, updated_by) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE rules_json = VALUES(rules_json), updated_by = VALUES(updated_by)
        """,
        (int(institution_id or 1), json.dumps(document, sort_keys=True), updated_by),
    )


def load_document(cursor, institution_id=1, *, private_only=False):
    """The raw JSON document stored for the institution ({} without a row). With `private_only`, just the `_` keys."""
    if not table_exists(cursor, RULES_TABLE):
        return {}
    cursor.execute(f'SELECT rules_json FROM {RULES_TABLE} WHERE institution_id = %s', (int(institution_id or 1),))
    row = cursor.fetchone()
    try:
        document = json.loads((row or {}).get('rules_json') or '{}')
    except (TypeError, ValueError):
        document = {}
    if not isinstance(document, dict):
        return {}
    if private_only:
        return {k: v for k, v in document.items() if str(k).startswith('_')}
    return document


def save_private(cursor, institution_id, key, value, updated_by=None):
    """Store one `_`-prefixed document (e.g. `_workload`) in the institution's rules row, keeping the rules."""
    if not table_exists(cursor, RULES_TABLE):
        raise RuntimeError('rules_table_missing')
    if not str(key).startswith('_'):
        raise ValueError('private_key')
    document = load_document(cursor, institution_id)
    document[key] = value
    cursor.execute(
        f"""
        INSERT INTO {RULES_TABLE} (institution_id, rules_json, updated_by) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE rules_json = VALUES(rules_json), updated_by = VALUES(updated_by)
        """,
        (int(institution_id or 1), json.dumps(document, sort_keys=True), updated_by),
    )


def institution_for_course(cursor, course_id):
    """The institution a course's department belongs to; 1 when institutions are not in the schema."""
    try:
        cursor.execute(
            'SELECT d.institution_id FROM courses c JOIN departments d ON d.id = c.department_id WHERE c.id = %s',
            (int(course_id),),
        )
        row = cursor.fetchone()
    except Exception:
        return 1
    return int((row or {}).get('institution_id') or 1)


def _hhmm(value):
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        return f'{(total // 3600) % 24:02d}:{(total % 3600) // 60:02d}'
    if isinstance(value, time):
        return value.strftime('%H:%M')
    if isinstance(value, str):
        return value[:5]
    return ''


def load_preferences(cursor, faculty_ids=None):
    """{faculty user id: [{'day', 'start_time', 'end_time', 'kind', 'weight', 'note'}]}; empty without the table."""
    if not table_exists(cursor, PREFERENCES_TABLE):
        return {}
    if faculty_ids is not None:
        ids = sorted({int(item) for item in faculty_ids})
        if not ids:
            return {}
        marks = ','.join(['%s'] * len(ids))
        cursor.execute(
            f'SELECT id, faculty_id, day_of_week, start_time, end_time, kind, weight, note FROM {PREFERENCES_TABLE} '
            f'WHERE faculty_id IN ({marks}) ORDER BY faculty_id, day_of_week, start_time', tuple(ids),
        )
    else:
        cursor.execute(
            f'SELECT id, faculty_id, day_of_week, start_time, end_time, kind, weight, note FROM {PREFERENCES_TABLE} '
            'ORDER BY faculty_id, day_of_week, start_time',
        )
    out = defaultdict(list)
    for row in cursor.fetchall() or []:
        day_index = int(row['day_of_week'] or 0)
        if not 1 <= day_index <= 7:
            continue
        out[int(row['faculty_id'])].append({
            'id': int(row['id']),
            'day': WEEKDAY_ORDER[day_index - 1],
            'start_time': _hhmm(row['start_time']),
            'end_time': _hhmm(row['end_time']),
            'kind': row['kind'],
            'weight': max(1, min(5, int(row['weight'] or 1))),
            'note': row.get('note') or '',
        })
    return dict(out)


def clean_preferences(payload):
    """A list of preference windows from the API body. Raises ValueError('preferences_invalid')."""
    if not isinstance(payload, list) or len(payload) > 60:
        raise ValueError('preferences_invalid')
    cleaned = []
    for item in payload:
        if not isinstance(item, dict) or set(item) - {'day', 'start_time', 'end_time', 'kind', 'weight', 'note'}:
            raise ValueError('preferences_invalid')
        day = item.get('day')
        start, end = item.get('start_time'), item.get('end_time')
        kind = item.get('kind')
        weight = item.get('weight', 3)
        note = item.get('note') or ''
        if day not in WEEKDAY_ORDER or kind not in PREFERENCE_KINDS:
            raise ValueError('preferences_invalid')
        for value in (start, end):
            if not isinstance(value, str) or not _TIME.match(value) or int(value[:2]) > 23 or int(value[3:]) > 59:
                raise ValueError('preferences_invalid')
        if start >= end:
            raise ValueError('preferences_invalid')
        if isinstance(weight, bool) or not isinstance(weight, int) or not 1 <= weight <= 5:
            raise ValueError('preferences_invalid')
        if not isinstance(note, str) or len(note) > 120 or any(ord(ch) < 32 for ch in note):
            raise ValueError('preferences_invalid')
        cleaned.append({'day': day, 'start_time': start, 'end_time': end, 'kind': kind, 'weight': weight, 'note': note})
    return cleaned


def save_preferences(cursor, faculty_id, preferences):
    """Replace a teacher's preference windows (already cleaned)."""
    if not table_exists(cursor, PREFERENCES_TABLE):
        raise RuntimeError('preferences_table_missing')
    cursor.execute(f'DELETE FROM {PREFERENCES_TABLE} WHERE faculty_id = %s', (int(faculty_id),))
    for item in preferences:
        cursor.execute(
            f'INSERT INTO {PREFERENCES_TABLE} (faculty_id, day_of_week, start_time, end_time, kind, weight, note) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (
                int(faculty_id), WEEKDAY_ORDER.index(item['day']) + 1, item['start_time'] + ':00', item['end_time'] + ':00',
                item['kind'], item['weight'], item['note'] or None,
            ),
        )


def effective_rules(cursor, institution_id=1, settings=None):
    """(rules, preferences_on): what a generation run should optimise for.

    Capability off (or table missing) -> legacy objective, no preferences. On -> the institution's
    rules with `settings['rules_override']` applied.
    """
    from core import capabilities

    if not capabilities.enabled(cursor, 'timetable_preferences'):
        return legacy_rules(), False
    rules, _stored = load_rules(cursor, institution_id)
    override = (settings or {}).get('rules_override')
    if isinstance(override, dict) and override:
        try:
            rules = merge_rules(rules, clean_rules(override, partial=True))
        except ValueError:
            pass
    return rules, True


# Evaluation --------------------------------------------------------------------------------------

def _overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def _minutes(value):
    return int(value[:2]) * 60 + int(value[3:5]) if isinstance(value, str) and len(value) >= 5 else 0


def weekly_hours(rows):
    """{faculty_id: hours} over rows with day/start_time/end_time/faculty_id (HH:MM strings)."""
    totals = defaultdict(float)
    for row in rows:
        if row.get('faculty_id') is None:
            continue
        totals[int(row['faculty_id'])] += max(0, _minutes(row['end_time']) - _minutes(row['start_time'])) / 60.0
    return dict(totals)


def evaluate(entries, rules, preferences=None, *, slot_starts=None, external=(), cohort_label=None, norms=None,
             norm_external=None, norm_fixed_hours=None):
    """Explain a timetable against the rules.

    `entries` are result rows (`day`, `start_time` HH:MM, `end_time`, `faculty_id`, `subject_id`,
    `room_id`, `lab_batch_group_id`, `session_type`, optional `faculty_name`) of one cohort.
    `external` rows (same shape, at least day/start_time/end_time/faculty_id) are other sessions
    the same teachers already have; they count for faculty rules but are not reported.
    `slot_starts` is the ordered list of slot start strings; derived from the rows when omitted.
    `norms` is {faculty_id: max weekly hours} (services/workload.py); without it `workload_max` is
    not evaluated. The hours counted are `entries` plus `norm_external` when given (teaching rows
    only), else `external` — which may include absence blocks that are not teaching — plus
    `norm_fixed_hours` {faculty_id: hours} already taught elsewhere.

    Returns {'cost': int, 'by_rule': {rule: cost}, 'violations': [...]}; a violation carries
    rule, title, scope, faculty_id, faculty_name, day, start_time, end_time, cost, detail.
    """
    preferences = preferences or {}
    weight = {name: int((rules.get(name) or {}).get('weight') or 0) for name in NAMES}
    param = lambda name, key: (rules.get(name) or {}).get(key, BY_NAME[name].params[key][1])  # noqa: E731

    starts = list(slot_starts) if slot_starts else sorted({row['start_time'] for row in list(entries) + list(external)})
    index = {start: position for position, start in enumerate(starts)}
    last_slot = len(starts) - 1
    violations = []
    by_rule = defaultdict(int)

    def report(rule, cost, *, day='', start='', end='', faculty_id=None, faculty_name='', detail=''):
        if cost <= 0:
            return
        by_rule[rule] += cost
        violations.append({
            'rule': rule, 'title': BY_NAME[rule].title, 'scope': BY_NAME[rule].scope,
            'faculty_id': faculty_id, 'faculty_name': faculty_name or '', 'cohort': cohort_label,
            'day': day, 'start_time': start, 'end_time': end, 'cost': int(cost), 'detail': detail,
        })

    def slot_of(row):
        return index.get(row['start_time'])

    own = [row for row in entries if slot_of(row) is not None]
    faculty_day = defaultdict(dict)       # (faculty, day) -> {slot: row or None(external)}
    faculty_names = {}
    for row in own:
        if row.get('faculty_id') is None:
            continue
        faculty_day[(int(row['faculty_id']), row['day'])][slot_of(row)] = row
        if row.get('faculty_name'):
            faculty_names[int(row['faculty_id'])] = row['faculty_name']
    for row in external:
        slot = slot_of(row)
        if slot is None or row.get('faculty_id') is None:
            continue
        faculty_day[(int(row['faculty_id']), row['day'])].setdefault(slot, None)

    def own_end(slots):
        last = max(slots)
        return starts[last + 1] if last + 1 < len(starts) else starts[last]

    # Faculty rules ------------------------------------------------------------------------------
    for (faculty_id, day), cells in faculty_day.items():
        if not any(row is not None for row in cells.values()):
            continue                                  # nothing of ours on this day
        slots = sorted(cells)
        name = faculty_names.get(faculty_id, '')
        hours = param('max_hours_per_day', 'hours')
        over = len(slots) - int(hours)
        if weight['max_hours_per_day'] and over > 0:
            report('max_hours_per_day', weight['max_hours_per_day'] * over, day=day, start=starts[slots[0]], end=own_end(slots),
                   faculty_id=faculty_id, faculty_name=name, detail=f'{len(slots)} hours on {day} (limit {hours})')
        limit = int(param('max_consecutive_hours', 'hours'))
        if weight['max_consecutive_hours']:
            run = [slots[0]]
            for slot in slots[1:] + [None]:
                if slot is not None and slot == run[-1] + 1:
                    run.append(slot)
                    continue
                if len(run) > limit:
                    report('max_consecutive_hours', weight['max_consecutive_hours'] * (len(run) - limit), day=day,
                           start=starts[run[0]], end=own_end(run), faculty_id=faculty_id, faculty_name=name,
                           detail=f'{len(run)} consecutive hours (limit {limit})')
                run = [slot] if slot is not None else []
        if weight['idle_gaps_faculty']:
            gaps = (slots[-1] - slots[0] + 1) - len(slots)
            report('idle_gaps_faculty', weight['idle_gaps_faculty'] * gaps, day=day, start=starts[slots[0]], end=own_end(slots),
                   faculty_id=faculty_id, faculty_name=name, detail=f'{gaps} idle slot(s) between sessions')
        if weight['faculty_preferences']:
            for slot, row in cells.items():
                if row is None:
                    continue
                for pref in preferences.get(faculty_id, []):
                    if pref['day'] != day or pref['kind'] != 'avoid':
                        continue
                    if _overlaps(row['start_time'], row['end_time'], pref['start_time'], pref['end_time']):
                        report('faculty_preferences', weight['faculty_preferences'] * pref['weight'], day=day,
                               start=row['start_time'], end=row['end_time'], faculty_id=faculty_id, faculty_name=name,
                               detail=f"Asked to avoid {pref['start_time']}-{pref['end_time']}" + (f" ({pref['note']})" if pref.get('note') else ''))
    if weight['no_first_hour_after_evening'] and last_slot > 0:
        for faculty_id in {fid for fid, _day in faculty_day}:
            for previous, following in zip(WEEKDAY_ORDER, WEEKDAY_ORDER[1:]):
                late = faculty_day.get((faculty_id, previous), {})
                early = faculty_day.get((faculty_id, following), {})
                if last_slot in late and 0 in early and (late[last_slot] is not None or early[0] is not None):
                    report('no_first_hour_after_evening', weight['no_first_hour_after_evening'], day=following, start=starts[0],
                           end=own_end([0]), faculty_id=faculty_id, faculty_name=faculty_names.get(faculty_id, ''),
                           detail=f'Last slot on {previous}, first slot on {following}')
    # Weekly workload: the teacher's hours across every cohort against the norm for their designation.
    if weight['workload_max'] and norms:
        totals = weekly_hours(list(own) + list(external if norm_external is None else norm_external))
        for faculty_id, hours in (norm_fixed_hours or {}).items():
            totals[int(faculty_id)] = totals.get(int(faculty_id), 0.0) + float(hours or 0)
        own_ids = {int(row['faculty_id']) for row in own if row.get('faculty_id') is not None}
        for faculty_id in sorted(own_ids):
            limit = norms.get(faculty_id)
            if limit is None:
                continue
            over = totals.get(faculty_id, 0.0) - float(limit)
            if over > 0:
                report('workload_max', weight['workload_max'] * int(-(-over // 1)), faculty_id=faculty_id,
                       faculty_name=faculty_names.get(faculty_id, ''),
                       detail=f'{totals[faculty_id]:g} hours this week (norm {float(limit):g})')
    # Preferred windows are a bonus (negative cost), not a violation.
    bonus = 0
    if weight['faculty_preferences']:
        for row in own:
            for pref in preferences.get(int(row['faculty_id']), []) if row.get('faculty_id') is not None else []:
                if pref['kind'] == 'preferred' and pref['day'] == row['day'] and _overlaps(row['start_time'], row['end_time'], pref['start_time'], pref['end_time']):
                    bonus += weight['faculty_preferences'] * pref['weight']

    # Cohort rules -------------------------------------------------------------------------------
    cohort_day = defaultdict(list)
    for row in own:
        cohort_day[row['day']].append(row)
    for day, rows in cohort_day.items():
        whole = [row for row in rows if not row.get('lab_batch_group_id')]
        slots = sorted({slot_of(row) for row in rows})
        if weight['idle_gaps_students'] and slots:
            gaps = (slots[-1] - slots[0] + 1) - len(slots)
            report('idle_gaps_students', weight['idle_gaps_students'] * gaps, day=day, start=starts[slots[0]], end=own_end(slots),
                   detail=f'{gaps} idle slot(s) for students')
        if weight['room_changes']:
            by_slot = {slot_of(row): row for row in whole}
            changes = 0
            for slot in sorted(by_slot):
                before = by_slot.get(slot - 1)
                if before and before.get('room_id') and by_slot[slot].get('room_id') and before['room_id'] != by_slot[slot]['room_id']:
                    changes += 1
            report('room_changes', weight['room_changes'] * changes, day=day, detail=f'{changes} room change(s)')
        groups = defaultdict(list)
        for row in rows:
            groups[(row.get('subject_id'), row.get('lab_batch_group_id'))].append(row)
        for (subject_id, _batch), group in groups.items():
            if weight['spread_subject'] and len(group) > 1:
                report('spread_subject', weight['spread_subject'] * (len(group) - 1), day=day, start=group[0]['start_time'],
                       end=group[0]['end_time'], detail=f"{group[0].get('subject_name') or subject_id} {len(group)} times on {day}")
            practicals = sorted({slot_of(row) for row in group if (row.get('session_type') or '').lower().startswith('prac')})
            if weight['lab_blocks_contiguous'] and len(practicals) > 1:
                adjacent = sum(1 for a, b in zip(practicals, practicals[1:]) if b == a + 1)
                loose = len(practicals) - 1 - adjacent
                report('lab_blocks_contiguous', weight['lab_blocks_contiguous'] * loose, day=day, start=starts[practicals[0]],
                       end=own_end(practicals), detail=f"{group[0].get('subject_name') or subject_id}: practical hours not contiguous")
        lunch_start, lunch_end = param('lunch_window', 'start'), param('lunch_window', 'end')
        if weight['lunch_window'] and lunch_start and lunch_end and lunch_start < lunch_end:
            for row in rows:
                if _overlaps(row['start_time'], row['end_time'], lunch_start, lunch_end):
                    report('lunch_window', weight['lunch_window'], day=day, start=row['start_time'], end=row['end_time'],
                           faculty_id=row.get('faculty_id'), faculty_name=row.get('faculty_name') or '',
                           detail=f'Session inside the lunch window {lunch_start}-{lunch_end}')
    lateness = sum(slot_of(row) for row in own) * weight['prefer_early'] if weight['prefer_early'] else 0
    by_rule['prefer_early'] += lateness

    violations.sort(key=lambda item: (-item['cost'], WEEKDAY_ORDER.index(item['day']) if item['day'] in WEEKDAY_ORDER else 9, item['start_time']))
    total = sum(by_rule.values()) - bonus
    return {'cost': int(total), 'by_rule': {name: int(cost) for name, cost in by_rule.items() if cost}, 'bonus': int(bonus), 'violations': violations}
