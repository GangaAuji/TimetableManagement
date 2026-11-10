"""Internal assessment marks and CO/PO attainment (docs/ACADEMICS.md).

Capability `assessments`. Off: the pages, the student tab and the attainment
report stay hidden, and nothing is written. Students see a mark only after
the component is locked. Attainment itself counts every entered mark.

CO attainment is the mean of each counted student's weighted percentage on
the components mapped to that CO. A student with no mark on those components
is left out. A student at or above 60 percent counts toward the NBA level:
3 when at least 70 percent of counted students reach it, 2 at 60 percent,
1 at 50 percent, otherwise 0. PO attainment is the correlation-weighted mean
of those CO percentages (weights are the map levels 1–3). The same bands,
applied to that percentage, give the PO level.
"""

import csv
import io
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from core import capabilities

CAPABILITY = 'assessments'
KINDS = ('IA', 'assignment', 'practical', 'viva', 'project')
PASS_PERCENT = Decimal('60')
LEVEL_BANDS = ((Decimal('70'), 3), (Decimal('60'), 2), (Decimal('50'), 1))
_CODE = re.compile(r'^[A-Za-z][A-Za-z0-9]{0,11}$')
_ONE = Decimal('0.1')
_HUNDRED = Decimal('0.01')
_MAX_ROWS = 2000

MESSAGES = {
    'assessment_unavailable': 'The assessment tables are missing; apply the database migrations first.',
    'assessment_invalid': 'Check the component, outcome or mapping and try again.',
    'assessment_marks_invalid': 'Marks must be from 0 up to the component maximum, with at most one decimal place.',
    'assessment_locked': 'That component is locked. Unlock it before changing marks or the scheme.',
    'assessment_in_use': 'A locked component still uses an outcome you are removing.',
    'assessment_import_invalid': 'The file needs a header row with roll_number and marks.',
    'subject_not_found': 'That subject was not found.',
    'component_not_found': 'That component was not found.',
    'capability_off': 'This feature is switched off for your institution.',
}

REPORT_FIELDS = [
    'outcome_kind', 'course_code', 'subject_code', 'subject_name', 'outcome_code', 'statement',
    'students', 'above_threshold', 'attainment_percent', 'level',
]
REPORT_LABELS = {
    'outcome_kind': 'Kind',
    'course_code': 'Course',
    'subject_code': 'Subject code',
    'subject_name': 'Subject',
    'outcome_code': 'Outcome',
    'statement': 'Statement',
    'students': 'Students counted',
    'above_threshold': 'At or above 60%',
    'attainment_percent': 'Attainment %',
    'level': 'Level',
}


class AssessmentError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES.get(code, code))


def active(cursor):
    return capabilities.enabled(cursor, CAPABILITY)


def tables_ready(cursor):
    return capabilities.table_exists(cursor, 'assessment_components') and capabilities.table_exists(cursor, 'course_outcomes')


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def _one_decimal(value, low, high):
    number = _decimal(value)
    if number is None or number < low or number > high:
        return None
    quant = number.quantize(_ONE, rounding=ROUND_HALF_UP)
    if quant != number:
        return None
    return quant


def parse_max_marks(value):
    return _one_decimal(value, Decimal('0.5'), Decimal('200'))


def parse_weight(value):
    return _one_decimal(value, Decimal('0'), Decimal('100'))


def parse_mark(value, maximum):
    """None clears the mark. A number is 0 to `maximum`, one decimal place."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    number = _one_decimal(value, Decimal('0'), Decimal(maximum))
    if number is None:
        raise AssessmentError('assessment_marks_invalid')
    return number


def _percent(value):
    if value is None:
        return None
    return Decimal(value).quantize(_HUNDRED, rounding=ROUND_HALF_UP)


def _level_for_share(share):
    for band, level in LEVEL_BANDS:
        if share >= band:
            return level
    return 0


def student_score(parts):
    """Weighted percentage for one student. `parts` is (percent, weight). None when nothing was marked."""
    usable = [(Decimal(percent), Decimal(weight)) for percent, weight in parts if percent is not None]
    if not usable:
        return None
    weights = [weight if weight > 0 else Decimal(0) for _, weight in usable]
    if sum(weights) == 0:
        weights = [Decimal(1)] * len(usable)
    total = sum(weights)
    return sum(percent * weight for (percent, _), weight in zip(usable, weights)) / total


def attain(components, component_links, po_links, marks):
    """CO and PO attainment from plain rows. Percentages are rounded to two decimals.

    `components` is {id: {max_marks, weight}}. `component_links` is {co_id: [component_id]}.
    `po_links` is {po_id: [(co_id, level)]}. `marks` is {(component_id, student_id): marks or None}.
    """
    by_component = {}
    for (component_id, student_id), mark in marks.items():
        by_component.setdefault(component_id, {})[student_id] = mark

    outcomes = {}
    for co_id, component_ids in component_links.items():
        scores = []
        seen = set()
        for component_id in component_ids:
            component = components.get(component_id)
            if component is None or Decimal(component['max_marks']) <= 0:
                continue
            for student_id, mark in by_component.get(component_id, {}).items():
                if mark is None:
                    continue
                seen.add(student_id)
        for student_id in seen:
            parts = []
            for component_id in component_ids:
                component = components.get(component_id)
                if component is None:
                    continue
                mark = by_component.get(component_id, {}).get(student_id)
                percent = None if mark is None else (Decimal(mark) / Decimal(component['max_marks'])) * Decimal(100)
                parts.append((percent, component['weight']))
            score = student_score(parts)
            if score is not None:
                scores.append(score)
        if not scores:
            outcomes[co_id] = {'percent': None, 'level': None, 'students': 0, 'above': 0}
            continue
        above = sum(1 for score in scores if score >= PASS_PERCENT)
        share = Decimal(above) * 100 / Decimal(len(scores))
        outcomes[co_id] = {
            'percent': _percent(sum(scores) / Decimal(len(scores))),
            'level': _level_for_share(share),
            'students': len(scores),
            'above': above,
        }

    programs = {}
    for po_id, links in po_links.items():
        pairs = []
        for co_id, level in links:
            outcome = outcomes.get(co_id)
            if outcome is None or outcome['percent'] is None or level not in (1, 2, 3):
                continue
            pairs.append((outcome['percent'], int(level)))
        if not pairs:
            programs[po_id] = {'percent': None, 'level': None, 'outcomes': 0}
            continue
        total = sum(level for _, level in pairs)
        percent = sum(percent * level for percent, level in pairs) / Decimal(total)
        programs[po_id] = {'percent': _percent(percent), 'level': _level_for_share(percent), 'outcomes': len(pairs)}
    return {'outcomes': outcomes, 'program_outcomes': programs}


def parse_import_csv(text):
    """Rows of {roll_number, marks} from a CSV. The marks cell may be blank."""
    if not isinstance(text, str) or not text.strip():
        raise AssessmentError('assessment_import_invalid')
    reader = csv.reader(io.StringIO(text.lstrip('\ufeff')))
    try:
        header = next(reader)
    except StopIteration:
        raise AssessmentError('assessment_import_invalid')
    names = [str(cell or '').strip().lower() for cell in header]
    if 'roll_number' not in names or 'marks' not in names:
        raise AssessmentError('assessment_import_invalid')
    roll_at = names.index('roll_number')
    marks_at = names.index('marks')
    rows = []
    for cells in reader:
        if not any(str(cell or '').strip() for cell in cells):
            continue
        roll = str(cells[roll_at] if roll_at < len(cells) else '').strip()
        raw = cells[marks_at] if marks_at < len(cells) else ''
        if not roll:
            raise AssessmentError('assessment_import_invalid')
        rows.append({'roll_number': roll, 'marks': '' if raw is None else str(raw).strip()})
        if len(rows) > _MAX_ROWS:
            raise AssessmentError('assessment_import_invalid')
    if not rows:
        raise AssessmentError('assessment_import_invalid')
    return rows


def parse_import_xlsx(blob):
    """The first worksheet, same columns as the CSV import."""
    from openpyxl import load_workbook

    if not blob or len(blob) > 1_000_000:
        raise AssessmentError('assessment_import_invalid')
    try:
        book = load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    except Exception:
        raise AssessmentError('assessment_import_invalid')
    sheet = book.active
    lines = []
    for index, values in enumerate(sheet.iter_rows(values_only=True)):
        if index > _MAX_ROWS + 1:
            break
        lines.append(','.join('' if value is None else str(value) for value in values))
    book.close()
    return parse_import_csv('\n'.join(lines))


def _code(value):
    if not isinstance(value, str) or not _CODE.match(value.strip()):
        return None
    return value.strip().upper()


def _statement(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 300:
        return None
    return text


def _name(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 80:
        return None
    return text


def _subject(cursor, subject_id):
    cursor.execute(
        """
        SELECT s.id, s.name, s.course_code, s.course_id, s.class_id, c.code AS program_code, d.institution_id
        FROM subjects s
        LEFT JOIN courses c ON c.id = s.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE s.id = %s
        """,
        (subject_id,),
    )
    return cursor.fetchone()


def course_in_scope(cursor, course_id):
    cursor.execute(
        """
        SELECT c.id, d.institution_id
        FROM courses c
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE c.id = %s
        """,
        (course_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    from core.scope import current_scope

    if not current_scope(cursor).allows(row['institution_id']):
        return None
    return row


def subject_in_scope(cursor, subject_id):
    row = _subject(cursor, subject_id)
    if row is None:
        return None
    from core.scope import current_scope

    if not current_scope(cursor).allows(row['institution_id']):
        return None
    return row


def subject_choices(cursor):
    from core.scope import current_scope

    clause, params = current_scope(cursor).clause('d.institution_id')
    cursor.execute(
        f"""
        SELECT s.id, CONCAT(COALESCE(s.course_code, ''), ' ', s.name) AS name, s.course_id
        FROM subjects s
        LEFT JOIN courses c ON c.id = s.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE {clause}
        ORDER BY s.name
        LIMIT 300
        """,
        params,
    )
    return list(cursor.fetchall())


def teaches(cursor, user_id, subject_id):
    cursor.execute(
        'SELECT 1 FROM faculty_allocations WHERE faculty_id = %s AND subject_id = %s LIMIT 1',
        (user_id, subject_id),
    )
    return cursor.fetchone() is not None


def allocated_subjects(cursor, user_id):
    cursor.execute(
        """
        SELECT s.id, CONCAT(COALESCE(s.course_code, ''), ' ', s.name) AS name
        FROM faculty_allocations a
        JOIN subjects s ON s.id = a.subject_id
        WHERE a.faculty_id = %s
        GROUP BY s.id, s.course_code, s.name
        ORDER BY s.name
        """,
        (user_id,),
    )
    return list(cursor.fetchall())


def _components(cursor, subject_id):
    cursor.execute(
        """
        SELECT id, name, max_marks, weight, kind, sort_order, locked_at IS NOT NULL AS locked
        FROM assessment_components WHERE subject_id = %s ORDER BY sort_order, id
        """,
        (subject_id,),
    )
    rows = list(cursor.fetchall())
    if not rows:
        return rows
    cursor.execute(
        """
        SELECT m.component_id, o.code
        FROM component_co_map m
        JOIN course_outcomes o ON o.id = m.co_id
        WHERE m.component_id IN ({})
        ORDER BY o.sort_order, o.code
        """.format(','.join(['%s'] * len(rows))),
        tuple(row['id'] for row in rows),
    )
    codes = {}
    for link in cursor.fetchall():
        codes.setdefault(link['component_id'], []).append(link['code'])
    for row in rows:
        row['outcome_codes'] = codes.get(row['id'], [])
    return rows


def _outcomes(cursor, subject_id):
    cursor.execute(
        'SELECT id, code, statement, sort_order FROM course_outcomes WHERE subject_id = %s ORDER BY sort_order, code',
        (subject_id,),
    )
    return list(cursor.fetchall())


def _program_outcomes(cursor, course_id):
    if not course_id:
        return []
    cursor.execute(
        'SELECT id, code, statement, sort_order FROM program_outcomes WHERE course_id = %s ORDER BY sort_order, code',
        (course_id,),
    )
    return list(cursor.fetchall())


def _co_po(cursor, subject_id):
    cursor.execute(
        """
        SELECT o.code AS co_code, p.code AS po_code, m.level
        FROM co_po_map m
        JOIN course_outcomes o ON o.id = m.co_id
        JOIN program_outcomes p ON p.id = m.po_id
        WHERE o.subject_id = %s
        ORDER BY o.sort_order, p.sort_order
        """,
        (subject_id,),
    )
    return list(cursor.fetchall())


def roster(cursor, subject):
    sql = 'SELECT id, name, roll_number FROM students WHERE course_id = %s AND is_active = 1'
    params = [subject['course_id']]
    if subject.get('class_id'):
        sql += ' AND class_id = %s'
        params.append(subject['class_id'])
    sql += ' ORDER BY roll_number, name'
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def _clean_outcomes(rows):
    if not isinstance(rows, list) or len(rows) > 40:
        raise AssessmentError('assessment_invalid')
    cleaned, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise AssessmentError('assessment_invalid')
        code = _code(row.get('code'))
        statement = _statement(row.get('statement'))
        if code is None or statement is None or code in seen:
            raise AssessmentError('assessment_invalid')
        seen.add(code)
        cleaned.append({'code': code, 'statement': statement})
    return cleaned


def replace_outcomes(cursor, subject_id, rows):
    cleaned = _clean_outcomes(rows)
    existing = {row['code']: row for row in _outcomes(cursor, subject_id)}
    locked = _locked_outcome_codes(cursor, subject_id)
    removed = set(existing) - {row['code'] for row in cleaned}
    if removed & locked:
        raise AssessmentError('assessment_in_use')
    for code in removed:
        cursor.execute('DELETE FROM co_po_map WHERE co_id = %s', (existing[code]['id'],))
        cursor.execute('DELETE FROM component_co_map WHERE co_id = %s', (existing[code]['id'],))
        cursor.execute('DELETE FROM course_outcomes WHERE id = %s', (existing[code]['id'],))
    for index, row in enumerate(cleaned):
        current = existing.get(row['code'])
        if current is None:
            cursor.execute(
                'INSERT INTO course_outcomes (subject_id, code, statement, sort_order) VALUES (%s, %s, %s, %s)',
                (subject_id, row['code'], row['statement'], index),
            )
        else:
            cursor.execute(
                'UPDATE course_outcomes SET statement = %s, sort_order = %s WHERE id = %s',
                (row['statement'], index, current['id']),
            )


def replace_program_outcomes(cursor, course_id, rows):
    if not course_id:
        raise AssessmentError('assessment_invalid')
    cleaned = _clean_outcomes(rows)
    existing = {row['code']: row for row in _program_outcomes(cursor, course_id)}
    for code in set(existing) - {row['code'] for row in cleaned}:
        cursor.execute('DELETE FROM program_outcomes WHERE id = %s', (existing[code]['id'],))
    for index, row in enumerate(cleaned):
        current = existing.get(row['code'])
        if current is None:
            cursor.execute(
                'INSERT INTO program_outcomes (course_id, code, statement, sort_order) VALUES (%s, %s, %s, %s)',
                (course_id, row['code'], row['statement'], index),
            )
        else:
            cursor.execute(
                'UPDATE program_outcomes SET statement = %s, sort_order = %s WHERE id = %s',
                (row['statement'], index, current['id']),
            )


def _locked_outcome_codes(cursor, subject_id):
    cursor.execute(
        """
        SELECT DISTINCT o.code
        FROM component_co_map m
        JOIN assessment_components c ON c.id = m.component_id
        JOIN course_outcomes o ON o.id = m.co_id
        WHERE c.subject_id = %s AND c.locked_at IS NOT NULL
        """,
        (subject_id,),
    )
    return {row['code'] for row in cursor.fetchall()}


def _clean_components(rows, known_codes):
    if not isinstance(rows, list) or len(rows) > 30:
        raise AssessmentError('assessment_invalid')
    cleaned, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise AssessmentError('assessment_invalid')
        name = _name(row.get('name'))
        kind = row.get('kind')
        maximum = parse_max_marks(row.get('max_marks'))
        weight = parse_weight(row.get('weight'))
        if name is None or kind not in KINDS or maximum is None or weight is None:
            raise AssessmentError('assessment_invalid')
        codes = row.get('outcome_codes') or []
        if not isinstance(codes, list) or len(codes) > 12:
            raise AssessmentError('assessment_invalid')
        parsed = []
        for code in codes:
            token = _code(code) if isinstance(code, str) else None
            if token is None or token not in known_codes or token in parsed:
                raise AssessmentError('assessment_invalid')
            parsed.append(token)
        component_id = row.get('id')
        if component_id is not None and (isinstance(component_id, bool) or not isinstance(component_id, int) or component_id < 1):
            raise AssessmentError('assessment_invalid')
        if component_id in seen:
            raise AssessmentError('assessment_invalid')
        if component_id is not None:
            seen.add(component_id)
        cleaned.append({
            'id': component_id, 'name': name, 'kind': kind, 'max_marks': maximum, 'weight': weight, 'outcome_codes': parsed,
        })
    return cleaned


def replace_components(cursor, subject_id, rows):
    known = {row['code']: row['id'] for row in _outcomes(cursor, subject_id)}
    cleaned = _clean_components(rows, set(known))
    existing = {row['id']: row for row in _components(cursor, subject_id)}
    incoming_ids = {row['id'] for row in cleaned if row['id'] is not None}
    if incoming_ids - set(existing):
        raise AssessmentError('assessment_invalid')
    for row in cleaned:
        current = existing.get(row['id'])
        if current is None or not current['locked']:
            continue
        same = (
            Decimal(current['max_marks']) == row['max_marks']
            and Decimal(current['weight']) == row['weight']
            and current['kind'] == row['kind']
            and list(current['outcome_codes']) == row['outcome_codes']
        )
        if not same:
            raise AssessmentError('assessment_locked')
    for component_id, current in existing.items():
        if component_id not in incoming_ids:
            if current['locked']:
                raise AssessmentError('assessment_locked')
            cursor.execute('DELETE FROM assessment_components WHERE id = %s', (component_id,))
    for index, row in enumerate(cleaned):
        current = existing.get(row['id'])
        if current is None:
            cursor.execute(
                """
                INSERT INTO assessment_components (subject_id, name, max_marks, weight, kind, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (subject_id, row['name'], row['max_marks'], row['weight'], row['kind'], index),
            )
            component_id = cursor.lastrowid
        else:
            component_id = current['id']
            cursor.execute(
                'UPDATE assessment_components SET name = %s, max_marks = %s, weight = %s, kind = %s, sort_order = %s WHERE id = %s',
                (row['name'], row['max_marks'], row['weight'], row['kind'], index, component_id),
            )
            if not current['locked']:
                cursor.execute('DELETE FROM component_co_map WHERE component_id = %s', (component_id,))
        if current is None or not current['locked']:
            for code in row['outcome_codes']:
                cursor.execute(
                    'INSERT INTO component_co_map (component_id, co_id) VALUES (%s, %s)',
                    (component_id, known[code]),
                )


def replace_map(cursor, subject_id, course_id, links):
    if not isinstance(links, list) or len(links) > 200:
        raise AssessmentError('assessment_invalid')
    outcomes = {row['code']: row['id'] for row in _outcomes(cursor, subject_id)}
    programs = {row['code']: row['id'] for row in _program_outcomes(cursor, course_id)}
    cleaned, seen = [], set()
    for link in links:
        if not isinstance(link, dict):
            raise AssessmentError('assessment_invalid')
        co_code = _code(link.get('co_code')) if isinstance(link.get('co_code'), str) else None
        po_code = _code(link.get('po_code')) if isinstance(link.get('po_code'), str) else None
        level = link.get('level')
        if co_code not in outcomes or po_code not in programs or level not in (1, 2, 3) or (co_code, po_code) in seen:
            raise AssessmentError('assessment_invalid')
        seen.add((co_code, po_code))
        cleaned.append((outcomes[co_code], programs[po_code], level))
    if outcomes:
        cursor.execute(
            'DELETE FROM co_po_map WHERE co_id IN ({})'.format(','.join(['%s'] * len(outcomes))),
            tuple(outcomes.values()),
        )
    for co_id, po_id, level in cleaned:
        cursor.execute('INSERT INTO co_po_map (co_id, po_id, level) VALUES (%s, %s, %s)', (co_id, po_id, level))


def _component(cursor, component_id):
    cursor.execute(
        """
        SELECT c.id, c.subject_id, c.name, c.max_marks, c.weight, c.kind, c.locked_at IS NOT NULL AS locked
        FROM assessment_components c WHERE c.id = %s
        """,
        (component_id,),
    )
    return cursor.fetchone()


def component_in_scope(cursor, component_id):
    row = _component(cursor, component_id)
    if row is None or subject_in_scope(cursor, row['subject_id']) is None:
        return None
    return row


def marks_grid(cursor, component):
    subject = _subject(cursor, component['subject_id'])
    students = roster(cursor, subject)
    marks = {}
    if students:
        cursor.execute(
            'SELECT student_id, marks FROM assessment_marks WHERE component_id = %s AND student_id IN ({})'.format(
                ','.join(['%s'] * len(students))
            ),
            (component['id'], *(row['id'] for row in students)),
        )
        marks = {row['student_id']: row['marks'] for row in cursor.fetchall()}
    return [
        {
            'student_id': row['id'],
            'name': row['name'],
            'roll_number': row['roll_number'] or '',
            'marks': None if marks.get(row['id']) is None else Decimal(marks[row['id']]),
        }
        for row in students
    ]


def save_marks(cursor, component, rows, entered_by):
    if component['locked']:
        raise AssessmentError('assessment_locked')
    if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
        raise AssessmentError('assessment_marks_invalid')
    subject = _subject(cursor, component['subject_id'])
    allowed_ids = {row['id'] for row in roster(cursor, subject)}
    maximum = Decimal(component['max_marks'])
    for row in rows:
        student_id = row.get('student_id') if isinstance(row, dict) else None
        if not isinstance(row, dict) or isinstance(student_id, bool) or not isinstance(student_id, int) or student_id not in allowed_ids:
            raise AssessmentError('assessment_marks_invalid')
        mark = parse_mark(row.get('marks'), maximum)
        if mark is None:
            cursor.execute(
                'DELETE FROM assessment_marks WHERE component_id = %s AND student_id = %s',
                (component['id'], row['student_id']),
            )
        else:
            cursor.execute(
                """
                INSERT INTO assessment_marks (component_id, student_id, marks, entered_by, locked_at)
                VALUES (%s, %s, %s, %s, NULL)
                ON DUPLICATE KEY UPDATE marks = VALUES(marks), entered_by = VALUES(entered_by), locked_at = NULL
                """,
                (component['id'], row['student_id'], mark, entered_by),
            )


def import_marks(cursor, component, rows, entered_by):
    if component['locked']:
        raise AssessmentError('assessment_locked')
    subject = _subject(cursor, component['subject_id'])
    by_roll = {str(row['roll_number']): row['id'] for row in roster(cursor, subject) if row.get('roll_number')}
    applied, unknown = [], []
    for row in rows:
        student_id = by_roll.get(str(row['roll_number']))
        if student_id is None:
            unknown.append(str(row['roll_number']))
            continue
        applied.append({'student_id': student_id, 'marks': row['marks']})
    if not applied:
        raise AssessmentError('assessment_import_invalid')
    save_marks(cursor, component, applied, entered_by)
    return {'saved': len(applied), 'unknown': unknown}


def set_locked(cursor, component, locked, user_id):
    if locked:
        cursor.execute(
            'UPDATE assessment_components SET locked_at = UTC_TIMESTAMP(), locked_by = %s WHERE id = %s',
            (user_id, component['id']),
        )
        cursor.execute(
            'UPDATE assessment_marks SET locked_at = UTC_TIMESTAMP() WHERE component_id = %s',
            (component['id'],),
        )
    else:
        cursor.execute(
            'UPDATE assessment_components SET locked_at = NULL, locked_by = NULL WHERE id = %s',
            (component['id'],),
        )
        cursor.execute('UPDATE assessment_marks SET locked_at = NULL WHERE component_id = %s', (component['id'],))


def _bundle(cursor, subject_ids):
    if not subject_ids:
        return [], [], [], [], []
    marks_sql = ','.join(['%s'] * len(subject_ids))
    params = tuple(subject_ids)
    cursor.execute(
        f"""
        SELECT id, subject_id, name, max_marks, weight, kind
        FROM assessment_components WHERE subject_id IN ({marks_sql}) ORDER BY sort_order, id
        """,
        params,
    )
    components = list(cursor.fetchall())
    cursor.execute(
        f'SELECT id, subject_id, code, statement FROM course_outcomes WHERE subject_id IN ({marks_sql}) ORDER BY sort_order, code',
        params,
    )
    outcomes = list(cursor.fetchall())
    course_ids = []
    cursor.execute(
        f'SELECT DISTINCT course_id FROM subjects WHERE id IN ({marks_sql}) AND course_id IS NOT NULL',
        params,
    )
    course_ids = [row['course_id'] for row in cursor.fetchall()]
    programs = []
    if course_ids:
        cursor.execute(
            'SELECT id, course_id, code, statement FROM program_outcomes WHERE course_id IN ({}) ORDER BY sort_order, code'.format(
                ','.join(['%s'] * len(course_ids))
            ),
            tuple(course_ids),
        )
        programs = list(cursor.fetchall())
    links = []
    po_links = []
    if components:
        cursor.execute(
            'SELECT component_id, co_id FROM component_co_map WHERE component_id IN ({})'.format(','.join(['%s'] * len(components))),
            tuple(row['id'] for row in components),
        )
        links = list(cursor.fetchall())
    if outcomes:
        cursor.execute(
            'SELECT co_id, po_id, level FROM co_po_map WHERE co_id IN ({})'.format(','.join(['%s'] * len(outcomes))),
            tuple(row['id'] for row in outcomes),
        )
        po_links = list(cursor.fetchall())
    marks = []
    if components:
        cursor.execute(
            'SELECT component_id, student_id, marks FROM assessment_marks WHERE component_id IN ({})'.format(
                ','.join(['%s'] * len(components))
            ),
            tuple(row['id'] for row in components),
        )
        marks = list(cursor.fetchall())
    return components, outcomes, programs, links, po_links, marks


def attainment_of(components, outcomes, links, po_links, marks):
    """One attainment pass. A PO uses every loaded CO that maps to it."""
    component_ids = {row['id'] for row in components}
    co_ids = {row['id'] for row in outcomes}
    component_links = {co_id: [] for co_id in co_ids}
    for link in links:
        if link['component_id'] in component_ids and link['co_id'] in co_ids:
            component_links[link['co_id']].append(link['component_id'])
    po_groups = {}
    for row in po_links:
        if row['co_id'] in co_ids:
            po_groups.setdefault(row['po_id'], []).append((row['co_id'], int(row['level'])))
    mark_map = {
        (row['component_id'], row['student_id']): None if row['marks'] is None else Decimal(row['marks'])
        for row in marks if row['component_id'] in component_ids
    }
    return attain({row['id']: row for row in components}, component_links, po_groups, mark_map)


def summary_for(cursor, subject):
    """CO figures for this subject. PO figures use every subject of its course."""
    cursor.execute('SELECT id FROM subjects WHERE course_id = %s', (subject['course_id'],))
    subject_ids = [row['id'] for row in cursor.fetchall()] or [subject['id']]
    components, outcomes, programs, links, po_links, marks = _bundle(cursor, subject_ids)
    figures = attainment_of(components, outcomes, links, po_links, marks)
    return {
        'outcomes': [
            {
                'code': row['code'], 'statement': row['statement'],
                **_public_figure(figures['outcomes'].get(row['id'])),
            }
            for row in outcomes if row['subject_id'] == subject['id']
        ],
        'program_outcomes': [
            {
                'code': row['code'], 'statement': row['statement'],
                **_public_figure(figures['program_outcomes'].get(row['id'])),
            }
            for row in programs
        ],
    }


def _public_figure(figure):
    figure = figure or {'percent': None, 'level': None, 'students': 0, 'above': 0}
    percent = figure.get('percent')
    return {
        'percent': None if percent is None else float(percent),
        'level': figure.get('level'),
        'students': int(figure.get('students') or 0),
        'above': int(figure.get('above') or 0),
    }


def page(cursor, subject_id):
    subject = subject_in_scope(cursor, subject_id) if subject_id else None
    if subject_id and subject is None:
        return None
    body = {
        'subjects': subject_choices(cursor),
        'subject': None if subject is None else {
            'id': subject['id'], 'name': subject['name'], 'course_id': subject['course_id'], 'course_code': subject['course_code'] or '',
        },
        'components': [],
        'outcomes': [],
        'program_outcomes': [],
        'co_po': [],
        'attainment': {'outcomes': [], 'program_outcomes': []},
    }
    if subject is None:
        return body
    body['components'] = _components(cursor, subject['id'])
    body['outcomes'] = _outcomes(cursor, subject['id'])
    body['program_outcomes'] = _program_outcomes(cursor, subject['course_id'])
    body['co_po'] = _co_po(cursor, subject['id'])
    body['attainment'] = summary_for(cursor, subject)
    return body


def student_results(cursor, user_id):
    cursor.execute(
        'SELECT id, course_id, class_id FROM students WHERE user_id = %s AND is_active = 1',
        (user_id,),
    )
    student = cursor.fetchone()
    if student is None:
        return []
    cursor.execute(
        """
        SELECT s.id AS subject_id, s.name AS subject_name, s.course_code, c.name AS component_name, c.kind, c.max_marks, m.marks
        FROM assessment_marks m
        JOIN assessment_components c ON c.id = m.component_id AND c.locked_at IS NOT NULL
        JOIN subjects s ON s.id = c.subject_id
        WHERE m.student_id = %s AND m.locked_at IS NOT NULL AND m.marks IS NOT NULL
          AND s.course_id = %s AND (s.class_id IS NULL OR s.class_id = %s)
        ORDER BY s.name, c.sort_order, c.id
        """,
        (student['id'], student['course_id'], student['class_id']),
    )
    grouped = {}
    for row in cursor.fetchall():
        item = grouped.setdefault(row['subject_id'], {
            'subject_id': row['subject_id'], 'name': row['subject_name'], 'code': row['course_code'] or '', 'components': [],
        })
        item['components'].append({
            'name': row['component_name'], 'kind': row['kind'],
            'max_marks': float(row['max_marks']), 'marks': float(row['marks']),
        })
    return list(grouped.values())


def locked_internals(cursor, subject_id):
    """Locked components and their marks, for the public API. None when the subject is missing."""
    subject = _subject(cursor, subject_id)
    if subject is None:
        return None
    cursor.execute(
        """
        SELECT c.id, c.name, c.kind, c.max_marks
        FROM assessment_components c
        WHERE c.subject_id = %s AND c.locked_at IS NOT NULL
        ORDER BY c.sort_order, c.id
        """,
        (subject_id,),
    )
    components = list(cursor.fetchall())
    marks = {}
    if components:
        cursor.execute(
            """
            SELECT m.component_id, s.roll_number, m.marks
            FROM assessment_marks m
            JOIN students s ON s.id = m.student_id
            WHERE m.component_id IN ({}) AND m.marks IS NOT NULL
            ORDER BY s.roll_number
            """.format(','.join(['%s'] * len(components))),
            tuple(row['id'] for row in components),
        )
        for row in cursor.fetchall():
            marks.setdefault(row['component_id'], []).append({
                'roll_number': row['roll_number'] or '', 'marks': float(row['marks']),
            })
    return {
        'subject_id': int(subject['id']),
        'name': subject['name'],
        'code': subject['course_code'] or '',
        'components': [
            {
                'name': row['name'], 'kind': row['kind'], 'max_marks': float(row['max_marks']),
                'marks': marks.get(row['id'], []),
            }
            for row in components
        ],
    }


def _filtered_subjects(cursor, filters, scoped):
    where, params = ['1=1'], []
    if scoped:
        from core.scope import current_scope

        clause, scope_params = current_scope(cursor).clause('d.institution_id')
        where.append(clause)
        params.extend(scope_params)
    if filters.get('subject_id'):
        where.append('s.id = %s')
        params.append(int(filters['subject_id']))
    if filters.get('course_id'):
        where.append('s.course_id = %s')
        params.append(int(filters['course_id']))
    if filters.get('department_id'):
        where.append('d.id = %s')
        params.append(int(filters['department_id']))
    cursor.execute(
        f"""
        SELECT s.id, s.name, s.course_code, s.course_id, c.code AS program_code
        FROM subjects s
        LEFT JOIN courses c ON c.id = s.course_id
        LEFT JOIN departments d ON d.id = c.department_id
        WHERE {' AND '.join(where)}
        ORDER BY s.name
        """,
        tuple(params),
    )
    return list(cursor.fetchall())


def report(cursor, filters):
    """(rows, fieldnames, labels, meta). Empty when the capability is off."""
    if not active(cursor) or not tables_ready(cursor):
        return [], list(REPORT_FIELDS), dict(REPORT_LABELS), {'attainment': 'off'}
    listed = _filtered_subjects(cursor, filters or {}, True)
    if not listed:
        return [], list(REPORT_FIELDS), dict(REPORT_LABELS), {'outcomes': 0}
    course_ids = {row['course_id'] for row in listed if row.get('course_id')}
    subjects = [row for row in _filtered_subjects(cursor, {}, True) if row.get('course_id') in course_ids] or listed
    listed_ids = {row['id'] for row in listed}
    components, outcomes, programs, links, po_links, marks = _bundle(cursor, [row['id'] for row in subjects])
    figures = attainment_of(components, outcomes, links, po_links, marks)
    by_id = {row['id']: row for row in subjects}
    rows = []
    for outcome in outcomes:
        if outcome['subject_id'] not in listed_ids:
            continue
        subject = by_id.get(outcome['subject_id'])
        if subject is None:
            continue
        rows.append(_report_row('CO', subject, outcome, figures['outcomes'].get(outcome['id'], {})))
    hosts = {}
    for row in subjects:
        hosts.setdefault(row['course_id'], row)
    seen_po = set()
    for program in programs:
        if program['id'] in seen_po or program['course_id'] not in hosts:
            continue
        seen_po.add(program['id'])
        figure = figures['program_outcomes'].get(program['id']) or {}
        host = hosts[program['course_id']]
        rows.append({
            'outcome_kind': 'PO',
            'course_code': host.get('program_code') or '',
            'subject_code': '',
            'subject_name': '',
            'outcome_code': program['code'],
            'statement': program['statement'],
            'students': figure.get('outcomes') or 0,
            'above_threshold': '',
            'attainment_percent': None if figure.get('percent') is None else float(figure['percent']),
            'level': '' if figure.get('level') is None else figure['level'],
        })
    return rows, list(REPORT_FIELDS), dict(REPORT_LABELS), {'rows': len(rows)}


def _report_row(kind, subject, outcome, figure):
    return {
        'outcome_kind': kind,
        'course_code': subject.get('program_code') or '',
        'subject_code': subject.get('course_code') or '',
        'subject_name': subject.get('name') or '',
        'outcome_code': outcome['code'],
        'statement': outcome['statement'],
        'students': int(figure.get('students') or 0),
        'above_threshold': int(figure.get('above') or 0),
        'attainment_percent': None if figure.get('percent') is None else float(figure['percent']),
        'level': '' if figure.get('level') is None else figure['level'],
    }
