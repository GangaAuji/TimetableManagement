"""Build migrations/sql/0001_baseline.sql from a phpMyAdmin schema dump.

Usage, from the project root:

    python -m core.schema.baseline sql/college_timetable_db.sql --checks sql/college_timetable_db.checks.sql

The cleaned file keeps every table, index, constraint, and view exactly as
dumped, including engine, charset, and collation. It drops row data,
AUTO_INCREMENT counters, view DEFINER clauses, transaction and session noise,
and the stand-in tables phpMyAdmin writes before each view. Every view is
written with SQL SECURITY INVOKER. Foreign key checks are switched off at the
top of the file and restored at the bottom.

phpMyAdmin drops a table's CHECK constraints, and everything after its closing
parenthesis (engine, charset, collation, comment), when the table has any
CHECK constraint. The --checks file is a structure-only mysqldump of those
tables; their CHECK lines and table options are taken from it after checking
that the column definitions match.
"""

import re
import sys
from pathlib import Path

from core.schema.sqlfile import read_statements, split_statements

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / 'migrations'
BASELINE_REVISION = '0001_baseline'
BASELINE_SQL = MIGRATIONS_DIR / 'sql' / '0001_baseline.sql'
BASELINE_SNAPSHOT = MIGRATIONS_DIR / 'sql' / '0001_baseline.schema.json'
SUPPORTED_SERVER = '10.4.32-MariaDB'

_FK_OFF = (
    'SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS',
    'SET FOREIGN_KEY_CHECKS=0',
)
_FK_RESTORE = 'SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS'
_CHARSET_SAVE = (
    'SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT',
    'SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS',
    'SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION',
    'SET NAMES utf8mb4',
)
_CHARSET_RESTORE = (
    'SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT',
    'SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS',
    'SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION',
)

_CREATE_TABLE = re.compile(r'^CREATE TABLE `(\w+)`', re.IGNORECASE)
_CREATE_VIEW = re.compile(r'^CREATE\b.*?\bVIEW `(\w+)`', re.IGNORECASE | re.DOTALL)
_ALTER_TABLE = re.compile(r'^ALTER TABLE `(\w+)`', re.IGNORECASE)
_DEFINER = re.compile(r'\s+DEFINER=(?:`[^`]*`|\S+)@(?:`[^`]*`|\S+)', re.IGNORECASE)
_SECURITY = re.compile(r'\s+SQL SECURITY \w+', re.IGNORECASE)
_TABLE_COUNTER = re.compile(r' AUTO_INCREMENT=\d+', re.IGNORECASE)
_COLUMN_COUNTER = re.compile(r',\s*AUTO_INCREMENT=\d+', re.IGNORECASE)
_SERVER_VERSION = re.compile(r'^-- Server version:\s*(\S+)', re.MULTILINE)
_DROPPED_PREFIXES = ('SET ', 'START TRANSACTION', 'COMMIT', '/*!', 'INSERT INTO', 'DROP TABLE IF EXISTS')
_CHECK_LINE = re.compile(r'^CONSTRAINT `\w+` CHECK \(', re.IGNORECASE)
_COLUMN_AUTO_INCREMENT = re.compile(r' AUTO_INCREMENT(?=,?$)', re.IGNORECASE)
_TABLE_OPTIONS = re.compile(r'\)\s*(ENGINE=.*)$', re.IGNORECASE | re.DOTALL)


def server_version_of(dump_text):
    match = _SERVER_VERSION.search(dump_text)
    return match.group(1) if match else None


def invoker_view(statement):
    """Drop the DEFINER clause and make the view run with the caller's rights."""
    statement = _DEFINER.sub('', statement, count=1)
    head, sep, rest = statement.partition(' VIEW `')
    if not sep:
        raise ValueError(f'Not a view statement: {statement[:80]}')
    head = _SECURITY.sub('', head)
    return f'{head} SQL SECURITY INVOKER VIEW `{rest}'


def _table_parts(statement):
    """Split a CREATE TABLE into (name, column lines, CHECK lines, table options or None)."""
    name = _CREATE_TABLE.match(statement).group(1)
    head, _, tail = statement.partition('(\n')
    body, _, end = tail.rpartition('\n)')
    lines = [line.strip().rstrip(',') for line in body.split('\n') if line.strip()]
    columns = [_COLUMN_AUTO_INCREMENT.sub('', line) for line in lines if line.startswith('`')]
    checks = [line for line in lines if _CHECK_LINE.match(line)]
    options = _TABLE_OPTIONS.match(')' + end)
    return name, columns, checks, _TABLE_COUNTER.sub('', options.group(1)).strip() if options else None


def check_repairs(checks_text):
    """Return {table: (CHECK lines, table options)} from a structure-only mysqldump."""
    repairs = {}
    for statement in split_statements(checks_text):
        if _CREATE_TABLE.match(statement):
            name, columns, checks, options = _table_parts(statement)
            if options is None:
                raise ValueError(f'`{name}` in the checks file has no table options.')
            repairs[name] = (columns, checks, options)
    return repairs


def _repair_table(statement, repair):
    name, columns, checks, options = _table_parts(statement)
    expected_columns, repair_checks, repair_options = repair
    if columns != expected_columns:
        raise ValueError(f'Columns of `{name}` differ between the dump and the checks file.')
    if checks or options is not None:
        raise ValueError(f'`{name}` already has CHECK constraints or table options in the dump.')
    body = statement[: statement.rindex('\n)')]
    added = ''.join(f',\n  {line}' for line in repair_checks)
    return f'{body}{added}\n) {repair_options}'


def clean_dump(dump_text, checks_text=None):
    """Return the baseline SQL text for a phpMyAdmin dump."""
    repairs = check_repairs(checks_text) if checks_text else {}
    repaired = set()
    statements = split_statements(dump_text)
    views = [statement for statement in statements if _CREATE_VIEW.match(statement) and not _CREATE_TABLE.match(statement)]
    view_names = {_CREATE_VIEW.match(statement).group(1) for statement in views}

    tables = []
    indexes = []
    counters = []
    constraints = []
    for statement in statements:
        upper = statement.upper()
        table = _CREATE_TABLE.match(statement)
        if table:
            name = table.group(1)
            if name in view_names:
                continue
            if name in repairs:
                statement = _repair_table(statement, repairs[name])
                repaired.add(name)
            elif _table_parts(statement)[3] is None:
                raise ValueError(
                    f'`{name}` has no table options; phpMyAdmin drops them along with CHECK constraints. '
                    'Pass a structure-only mysqldump of it with --checks.'
                )
            tables.append(_TABLE_COUNTER.sub('', statement))
            continue
        if statement in views:
            continue
        if upper.startswith(_DROPPED_PREFIXES):
            continue
        if _ALTER_TABLE.match(statement):
            if ' ADD CONSTRAINT ' in upper and ' FOREIGN KEY ' in upper:
                constraints.append(statement)
            elif ' AUTO_INCREMENT' in upper and ' MODIFY ' in upper:
                counters.append(_COLUMN_COUNTER.sub('', statement))
            else:
                indexes.append(statement)
            continue
        raise ValueError(f'Unexpected statement in dump: {statement[:120]}')

    if not tables:
        raise ValueError('The dump has no CREATE TABLE statements.')
    if set(repairs) - repaired:
        raise ValueError(f'Tables in the checks file but not in the dump: {sorted(set(repairs) - repaired)}')

    body = list(_CHARSET_SAVE) + list(_FK_OFF)
    body += tables + indexes + counters + constraints
    body += [invoker_view(statement) for statement in views]
    body += [_FK_RESTORE] + list(_CHARSET_RESTORE)

    version = server_version_of(dump_text) or 'unknown server'
    header = (
        f'-- Baseline schema for college_timetable_db on {version}.\n'
        '-- Generated by `python -m core.schema.baseline` from a phpMyAdmin dump.\n'
        + (f'-- CHECK constraints and table options of {len(repaired)} tables come from a mysqldump.\n' if repaired else '')
        +
        f'-- {len(tables)} tables, {len(views)} views. Do not edit by hand.\n'
        '-- Never change this file after a database has been upgraded or stamped.\n\n'
    )
    return header + ';\n\n'.join(body) + ';\n'


def baseline_objects(statements):
    """Return (tables, views) in the order the baseline creates them."""
    tables = []
    views = []
    for statement in statements:
        table = _CREATE_TABLE.match(statement)
        if table:
            tables.append(table.group(1))
            continue
        view = _CREATE_VIEW.match(statement)
        if view:
            views.append(view.group(1))
    return tables, views


def baseline_statements():
    return read_statements(BASELINE_SQL)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    checks_text = None
    if '--checks' in args:
        at = args.index('--checks')
        if at + 1 >= len(args):
            args = []
        else:
            checks_text = Path(args[at + 1]).read_text(encoding='utf-8')
            del args[at:at + 2]
    if len(args) not in (1, 2):
        print(
            'Usage: python -m core.schema.baseline <phpmyadmin dump> [--checks <mysqldump --no-data>] [output]',
            file=sys.stderr,
        )
        return 2
    source = Path(args[0])
    target = Path(args[1]) if len(args) == 2 else BASELINE_SQL
    dump_text = source.read_text(encoding='utf-8')
    version = server_version_of(dump_text)
    if version != SUPPORTED_SERVER:
        print(f'Warning: dump is from {version}, the supported server is {SUPPORTED_SERVER}.', file=sys.stderr)
    cleaned = clean_dump(dump_text, checks_text)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(cleaned, encoding='utf-8', newline='\n')
    tables, views = baseline_objects(split_statements(cleaned))
    print(f'Wrote {target} ({len(tables)} tables, {len(views)} views).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
