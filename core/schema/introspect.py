"""Read one schema from information_schema and compare it with another.

Every value is stored as text (or None) so a snapshot round-trips through JSON
unchanged. AUTO_INCREMENT counters, row counts, view DEFINERs, and the
alembic_version table are never read.
"""

import json

IGNORED_TABLES = ('alembic_version',)

_TABLES = """
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
"""

_COLUMNS = """
SELECT c.TABLE_NAME, c.COLUMN_NAME, c.ORDINAL_POSITION, c.COLUMN_TYPE, c.IS_NULLABLE,
       c.COLUMN_DEFAULT, c.EXTRA, c.CHARACTER_SET_NAME, c.COLLATION_NAME,
       c.COLUMN_COMMENT, c.GENERATION_EXPRESSION
FROM information_schema.COLUMNS c
JOIN information_schema.TABLES t
  ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
WHERE c.TABLE_SCHEMA = %s AND t.TABLE_TYPE = 'BASE TABLE'
"""

_INDEXES = """
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, SUB_PART,
       INDEX_TYPE, COLLATION
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = %s
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
"""

_FOREIGN_KEYS = """
SELECT k.TABLE_NAME, k.CONSTRAINT_NAME, k.COLUMN_NAME, k.ORDINAL_POSITION,
       k.REFERENCED_TABLE_SCHEMA, k.REFERENCED_TABLE_NAME, k.REFERENCED_COLUMN_NAME,
       r.UPDATE_RULE, r.DELETE_RULE
FROM information_schema.KEY_COLUMN_USAGE k
JOIN information_schema.REFERENTIAL_CONSTRAINTS r
  ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
 AND r.TABLE_NAME = k.TABLE_NAME
 AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
WHERE k.TABLE_SCHEMA = %s AND k.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION
"""

_CHECKS = """
SELECT TABLE_NAME, CONSTRAINT_NAME, CHECK_CLAUSE
FROM information_schema.CHECK_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = %s
"""

_VIEWS = """
SELECT TABLE_NAME, VIEW_DEFINITION, CHECK_OPTION, SECURITY_TYPE,
       CHARACTER_SET_CLIENT, COLLATION_CONNECTION
FROM information_schema.VIEWS
WHERE TABLE_SCHEMA = %s
"""

_TRIGGERS = """
SELECT TRIGGER_NAME, EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION, ACTION_STATEMENT
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = %s
"""

_ROUTINES = """
SELECT ROUTINE_NAME, ROUTINE_TYPE, ROUTINE_DEFINITION
FROM information_schema.ROUTINES
WHERE ROUTINE_SCHEMA = %s
"""

_EVENTS = """
SELECT EVENT_NAME, EVENT_DEFINITION, STATUS
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = %s
"""

SECTIONS = ('tables', 'columns', 'indexes', 'foreign_keys', 'checks', 'views', 'triggers', 'routines', 'events')

_LABELS = {
    'tables': 'table',
    'columns': 'column',
    'indexes': 'index',
    'foreign_keys': 'foreign key',
    'checks': 'check constraint',
    'views': 'view',
    'triggers': 'trigger',
    'routines': 'routine',
    'events': 'event',
}


def _text(value):
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8')
    return str(value)


def _rows(cursor, sql, schema):
    cursor.execute(sql, (schema,))
    names = [description[0].upper() for description in cursor.description]
    return [{name: _text(value) for name, value in zip(names, row)} for row in cursor.fetchall()]


def _ignored(table):
    return table in IGNORED_TABLES


def server_version(cursor):
    cursor.execute('SELECT VERSION()')
    return _text(cursor.fetchone()[0])


def read_schema(cursor, schema):
    """Return {section: {object key: {attribute: text}}} for one schema."""
    result = {section: {} for section in SECTIONS}

    for row in _rows(cursor, _TABLES, schema):
        if _ignored(row['TABLE_NAME']):
            continue
        result['tables'][row['TABLE_NAME']] = {
            'engine': row['ENGINE'],
            'collation': row['TABLE_COLLATION'],
            'comment': row['TABLE_COMMENT'],
        }

    for row in _rows(cursor, _COLUMNS, schema):
        if _ignored(row['TABLE_NAME']):
            continue
        result['columns'][f"{row['TABLE_NAME']}.{row['COLUMN_NAME']}"] = {
            'position': row['ORDINAL_POSITION'],
            'type': row['COLUMN_TYPE'],
            'nullable': row['IS_NULLABLE'],
            'default': row['COLUMN_DEFAULT'],
            'extra': row['EXTRA'],
            'charset': row['CHARACTER_SET_NAME'],
            'collation': row['COLLATION_NAME'],
            'comment': row['COLUMN_COMMENT'],
            'generated': row['GENERATION_EXPRESSION'],
        }

    for row in _rows(cursor, _INDEXES, schema):
        if _ignored(row['TABLE_NAME']):
            continue
        key = f"{row['TABLE_NAME']}.{row['INDEX_NAME']}"
        index = result['indexes'].setdefault(key, {
            'unique': 'no' if row['NON_UNIQUE'] == '1' else 'yes',
            'type': row['INDEX_TYPE'],
            'columns': [],
        })
        column = row['COLUMN_NAME']
        if row['SUB_PART']:
            column += f"({row['SUB_PART']})"
        if row['COLLATION'] == 'D':
            column += ' DESC'
        index['columns'].append(column)

    for row in _rows(cursor, _FOREIGN_KEYS, schema):
        key = f"{row['TABLE_NAME']}.{row['CONSTRAINT_NAME']}"
        foreign_key = result['foreign_keys'].setdefault(key, {
            'table': row['TABLE_NAME'],
            'references_schema': 'same' if row['REFERENCED_TABLE_SCHEMA'] == schema else row['REFERENCED_TABLE_SCHEMA'],
            'references': row['REFERENCED_TABLE_NAME'],
            'columns': [],
            'referenced_columns': [],
            'on_update': row['UPDATE_RULE'],
            'on_delete': row['DELETE_RULE'],
        })
        foreign_key['columns'].append(row['COLUMN_NAME'])
        foreign_key['referenced_columns'].append(row['REFERENCED_COLUMN_NAME'])

    for row in _rows(cursor, _CHECKS, schema):
        result['checks'][f"{row['TABLE_NAME']}.{row['CONSTRAINT_NAME']}"] = {'clause': row['CHECK_CLAUSE']}

    qualifier = f'`{schema}`.'
    for row in _rows(cursor, _VIEWS, schema):
        result['views'][row['TABLE_NAME']] = {
            'definition': (row['VIEW_DEFINITION'] or '').replace(qualifier, ''),
            'check_option': row['CHECK_OPTION'],
            'security': row['SECURITY_TYPE'],
            'charset_client': row['CHARACTER_SET_CLIENT'],
            'collation_connection': row['COLLATION_CONNECTION'],
        }

    for row in _rows(cursor, _TRIGGERS, schema):
        result['triggers'][row['TRIGGER_NAME']] = {
            'table': row['EVENT_OBJECT_TABLE'],
            'timing': row['ACTION_TIMING'],
            'event': row['EVENT_MANIPULATION'],
            'statement': (row['ACTION_STATEMENT'] or '').replace(qualifier, ''),
        }

    for row in _rows(cursor, _ROUTINES, schema):
        result['routines'][row['ROUTINE_NAME']] = {
            'type': row['ROUTINE_TYPE'],
            'definition': (row['ROUTINE_DEFINITION'] or '').replace(qualifier, ''),
        }

    for row in _rows(cursor, _EVENTS, schema):
        result['events'][row['EVENT_NAME']] = {
            'definition': (row['EVENT_DEFINITION'] or '').replace(qualifier, ''),
            'status': row['STATUS'],
        }

    return result


def _describe(value):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 160 else text[:157] + '...'


def _first_difference(expected, found):
    index = next((i for i, (a, b) in enumerate(zip(expected, found)) if a != b), min(len(expected), len(found)))
    start = max(0, index - 40)
    return f'first difference at character {index}: baseline ...{expected[start:index + 40]!r}, found ...{found[start:index + 40]!r}'


def compare(expected, found):
    """List every difference between two read_schema() results. Empty means identical."""
    differences = []
    for section in SECTIONS:
        label = _LABELS[section]
        want = expected.get(section, {})
        have = found.get(section, {})
        for key in sorted(set(want) - set(have)):
            differences.append(f'missing {label} `{key}`')
        for key in sorted(set(have) - set(want)):
            differences.append(f'unexpected {label} `{key}`: {_describe(have[key])}')
        for key in sorted(set(want) & set(have)):
            for attribute in sorted(set(want[key]) | set(have[key])):
                a = want[key].get(attribute)
                b = have[key].get(attribute)
                if a == b:
                    continue
                if isinstance(a, str) and isinstance(b, str) and (len(a) > 160 or len(b) > 160):
                    detail = _first_difference(a, b)
                else:
                    detail = f'baseline {_describe(a)}, found {_describe(b)}'
                differences.append(f'{label} `{key}` {attribute}: {detail}')
    return differences


def missing_fk_targets(schema):
    """List foreign keys whose referenced table or column does not exist in the schema."""
    problems = []
    for key, foreign_key in sorted(schema['foreign_keys'].items()):
        if foreign_key['references_schema'] != 'same':
            problems.append(f'foreign key `{key}` points at another schema `{foreign_key["references_schema"]}`')
            continue
        target = foreign_key['references']
        if target not in schema['tables']:
            problems.append(f'foreign key `{key}` points at missing table `{target}`')
            continue
        for column in foreign_key['referenced_columns']:
            if f'{target}.{column}' not in schema['columns']:
                problems.append(f'foreign key `{key}` points at missing column `{target}`.`{column}`')
    return problems


def snapshot(schema, server):
    return {'server_version': server, 'schema': schema}


def write_snapshot(path, schema, server):
    text = json.dumps(snapshot(schema, server), indent=1, sort_keys=True, ensure_ascii=False)
    path.write_text(text + '\n', encoding='utf-8', newline='\n')


def load_snapshot(path):
    return json.loads(path.read_text(encoding='utf-8'))
