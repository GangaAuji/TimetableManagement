"""Baseline SQL, statement splitting, schema comparison, and the autogenerate block. No live database."""

import copy
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from core.schema.baseline import (
    BASELINE_SQL,
    MIGRATIONS_DIR,
    ROOT,
    SUPPORTED_SERVER,
    baseline_objects,
    baseline_statements,
    clean_dump,
)
from core.schema.introspect import compare, missing_fk_targets
from core.schema.sqlfile import split_statements

LIVE_DUMP = ROOT / 'sql' / 'college_timetable_db.sql'
CHECKS_DUMP = ROOT / 'sql' / 'college_timetable_db.checks.sql'

SAMPLE_DUMP = """-- phpMyAdmin SQL Dump
-- Server version: 10.4.32-MariaDB

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";
/*!40101 SET NAMES utf8mb4 */;

CREATE TABLE `users` (
  `id` int(11) NOT NULL,
  `note` varchar(20) DEFAULT 'a;b' COMMENT 'it''s -- not a comment'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `users` (`id`, `note`) VALUES (1, 'x;y'), (2, 'it\\'s');

CREATE TABLE `v_users` (
`id` int(11)
);

DROP TABLE IF EXISTS `v_users`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_users`  AS SELECT `users`.`id` AS `id` FROM `users` WHERE `users`.`note` like '%a%' ;

ALTER TABLE `users`
  ADD PRIMARY KEY (`id`);

ALTER TABLE `users`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=158;

ALTER TABLE `users`
  ADD CONSTRAINT `fk_self` FOREIGN KEY (`id`) REFERENCES `users` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
"""


def test_split_keeps_semicolons_inside_quotes_and_drops_comments():
    statements = split_statements(
        "-- note; here\nSELECT 'a;b', \"c;d\", `e;f`; /* x; y */ SELECT 'it''s', 'x\\';y';\n"
        "/*!40101 SET NAMES utf8mb4 */;\n# trailing; comment\n"
    )
    assert statements == [
        "SELECT 'a;b', \"c;d\", `e;f`",
        "SELECT 'it''s', 'x\\';y'",
        '/*!40101 SET NAMES utf8mb4 */',
    ]


def test_split_rejects_an_unterminated_quote():
    with pytest.raises(ValueError):
        split_statements("SELECT 'open;")


def test_clean_dump_keeps_structure_and_drops_data_counters_and_definer():
    statements = split_statements(clean_dump(SAMPLE_DUMP))
    text = ';'.join(statements)
    assert 'INSERT' not in text
    assert 'AUTO_INCREMENT=' not in text
    assert 'DEFINER' not in text
    assert 'START TRANSACTION' not in text and 'COMMIT' not in text and 'time_zone' not in text
    assert statements[:6] == [
        'SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT',
        'SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS',
        'SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION',
        'SET NAMES utf8mb4',
        'SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS',
        'SET FOREIGN_KEY_CHECKS=0',
    ]
    assert statements[-4] == 'SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS'
    body = statements[6:-4]
    assert body[0].startswith('CREATE TABLE `users`')
    assert "COLLATE=utf8mb4_general_ci" in body[0]
    assert "'it''s -- not a comment'" in body[0]
    assert body[1] == 'ALTER TABLE `users`\n  ADD PRIMARY KEY (`id`)'
    assert body[2] == 'ALTER TABLE `users`\n  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT'
    assert body[3].startswith('ALTER TABLE `users`\n  ADD CONSTRAINT `fk_self`')
    assert body[4] == (
        'CREATE ALGORITHM=UNDEFINED SQL SECURITY INVOKER VIEW `v_users`  AS SELECT `users`.`id` AS `id` '
        "FROM `users` WHERE `users`.`note` like '%a%'"
    )
    assert len(body) == 5
    assert baseline_objects(statements) == (['users'], ['v_users'])


def test_clean_dump_refuses_an_unknown_statement():
    with pytest.raises(ValueError):
        clean_dump(SAMPLE_DUMP + '\nCREATE TRIGGER `t` BEFORE INSERT ON `users` FOR EACH ROW SET @x = 1;\n')


def test_committed_baseline_has_the_expected_shape():
    text = BASELINE_SQL.read_text(encoding='utf-8')
    assert f'on {SUPPORTED_SERVER}.' in text.splitlines()[0]
    statements = baseline_statements()
    tables, views = baseline_objects(statements)
    assert len(tables) == 54 and len(set(tables)) == 54
    assert len(views) == 10
    for marker in ('AUTO_INCREMENT=', 'DEFINER', 'INSERT INTO', 'START TRANSACTION', 'COMMIT', 'SQL_MODE', 'time_zone'):
        assert marker not in text
    view_statements = [statement for statement in statements if ' VIEW `' in statement and statement.startswith('CREATE ALGORITHM')]
    assert len(view_statements) == 10
    assert all(' SQL SECURITY INVOKER VIEW `' in statement for statement in view_statements)
    assert statements[5] == 'SET FOREIGN_KEY_CHECKS=0'
    assert statements[-4] == 'SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS'
    assert 'rate_limit_counters' not in tables


def test_committed_baseline_keeps_check_constraints_and_table_options():
    tables = [statement for statement in baseline_statements() if statement.startswith('CREATE TABLE')]
    assert all(') ENGINE=InnoDB ' in statement for statement in tables)
    checks = [line for statement in tables for line in statement.split('\n') if ' CHECK (' in line]
    assert len(checks) == 10
    assert sum('CONSTRAINT `chk_' in line for line in checks) == 8


_CHECKS_DUMP = """/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `rooms` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `capacity` int(11) DEFAULT 60,
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_room_capacity` CHECK (`capacity` > 0)
) ENGINE=InnoDB AUTO_INCREMENT=33 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Rooms';
"""

_ROOMS_WITHOUT_OPTIONS = """
CREATE TABLE `rooms` (
  `id` int(11) NOT NULL,
  `capacity` int(11) DEFAULT 60
) ;
"""


def test_clean_dump_restores_checks_and_options_phpmyadmin_dropped():
    statements = split_statements(clean_dump(SAMPLE_DUMP + _ROOMS_WITHOUT_OPTIONS, _CHECKS_DUMP))
    rooms = next(statement for statement in statements if statement.startswith('CREATE TABLE `rooms`'))
    assert rooms == (
        'CREATE TABLE `rooms` (\n'
        '  `id` int(11) NOT NULL,\n'
        '  `capacity` int(11) DEFAULT 60,\n'
        '  CONSTRAINT `chk_room_capacity` CHECK (`capacity` > 0)\n'
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Rooms'"
    )


def test_clean_dump_refuses_a_table_without_options_or_with_different_columns():
    with pytest.raises(ValueError, match='no table options'):
        clean_dump(SAMPLE_DUMP + _ROOMS_WITHOUT_OPTIONS)
    with pytest.raises(ValueError, match='Columns of `rooms` differ'):
        clean_dump(SAMPLE_DUMP + _ROOMS_WITHOUT_OPTIONS.replace('DEFAULT 60', 'DEFAULT 50'), _CHECKS_DUMP)
    with pytest.raises(ValueError, match='not in the dump'):
        clean_dump(SAMPLE_DUMP, _CHECKS_DUMP)


@pytest.mark.skipif(
    not (LIVE_DUMP.exists() and CHECKS_DUMP.exists()), reason='the local dumps are not in sql/',
)
def test_committed_baseline_is_what_the_cleaner_produces_from_the_dump():
    expected = clean_dump(LIVE_DUMP.read_text(encoding='utf-8'), CHECKS_DUMP.read_text(encoding='utf-8'))
    assert BASELINE_SQL.read_text(encoding='utf-8') == expected


def test_revision_chain_is_linear_from_the_baseline():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    scripts = ScriptDirectory.from_config(config)
    chain = [script.revision for script in scripts.walk_revisions('base', 'heads')]
    assert list(reversed(chain))[:2] == ['0001_baseline', '0002_catch_up']
    assert len(scripts.get_heads()) == 1
    assert scripts.get_revision('0001_baseline').down_revision is None
    assert not (MIGRATIONS_DIR / 'versions' / '0001_baseline_existing_schema.py').exists()


def _schema():
    return {
        'tables': {
            'users': {'engine': 'InnoDB', 'collation': 'utf8mb4_unicode_ci', 'comment': ''},
            'roles': {'engine': 'InnoDB', 'collation': 'utf8mb4_unicode_ci', 'comment': ''},
        },
        'columns': {
            'users.id': {'type': 'int(11)', 'nullable': 'NO', 'default': None},
            'users.role_id': {'type': 'int(11)', 'nullable': 'YES', 'default': 'NULL'},
            'roles.id': {'type': 'int(11)', 'nullable': 'NO', 'default': None},
        },
        'indexes': {'users.PRIMARY': {'unique': 'yes', 'type': 'BTREE', 'columns': ['id']}},
        'foreign_keys': {
            'users.fk_role': {
                'table': 'users', 'references_schema': 'same', 'references': 'roles',
                'columns': ['role_id'], 'referenced_columns': ['id'],
                'on_update': 'RESTRICT', 'on_delete': 'SET NULL',
            },
        },
        'checks': {},
        'views': {'v_users': {'definition': 'select 1', 'security': 'INVOKER'}},
        'triggers': {},
        'routines': {},
        'events': {},
    }


def test_compare_reports_each_kind_of_difference():
    expected = _schema()
    found = copy.deepcopy(expected)
    assert compare(expected, found) == []

    found['columns']['users.role_id']['nullable'] = 'NO'
    found['columns']['users.extra'] = {'type': 'int(11)', 'nullable': 'YES', 'default': 'NULL'}
    del found['indexes']['users.PRIMARY']
    found['foreign_keys']['users.fk_role']['on_delete'] = 'CASCADE'
    found['views']['v_users']['security'] = 'DEFINER'
    found['tables']['roles']['collation'] = 'utf8mb4_general_ci'

    assert compare(expected, found) == [
        'table `roles` collation: baseline "utf8mb4_unicode_ci", found "utf8mb4_general_ci"',
        'unexpected column `users.extra`: {"type": "int(11)", "nullable": "YES", "default": "NULL"}',
        'column `users.role_id` nullable: baseline "YES", found "NO"',
        'missing index `users.PRIMARY`',
        'foreign key `users.fk_role` on_delete: baseline "SET NULL", found "CASCADE"',
        'view `v_users` security: baseline "INVOKER", found "DEFINER"',
    ]


def test_compare_points_at_the_first_change_in_a_long_definition():
    expected = _schema()
    found = copy.deepcopy(expected)
    expected['views']['v_users']['definition'] = 'select ' + 'a' * 200 + ' from x'
    found['views']['v_users']['definition'] = 'select ' + 'a' * 200 + ' from y'
    [line] = compare(expected, found)
    assert line.startswith('view `v_users` definition: first difference at character 213')


def test_missing_fk_targets_names_the_table_or_column():
    schema = _schema()
    assert missing_fk_targets(schema) == []
    del schema['columns']['roles.id']
    assert missing_fk_targets(schema) == ['foreign key `users.fk_role` points at missing column `roles`.`id`']
    del schema['tables']['roles']
    assert missing_fk_targets(schema) == ['foreign key `users.fk_role` points at missing table `roles`']


_AUTOGENERATE_SCRIPT = textwrap.dedent(
    """
    import sys
    from flask import Flask
    from flask_migrate import Migrate, migrate
    from flask_sqlalchemy import SQLAlchemy

    app = Flask('autogenerate_probe')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqldb://nobody:nothing@127.0.0.1:1/autogenerate_probe_test'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db = SQLAlchemy(app)
    Migrate(app, db, directory=sys.argv[1])
    with app.app_context():
        migrate(directory=sys.argv[1], message='should not be written')
    """
)


def test_flask_db_migrate_refuses_autogenerate_without_touching_a_database():
    before = sorted(path.name for path in (MIGRATIONS_DIR / 'versions').iterdir())
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run(
        [sys.executable, '-c', _AUTOGENERATE_SCRIPT, str(MIGRATIONS_DIR)],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert 'Autogenerate is disabled: hand-written revisions only.' in output
    assert 'Can\'t connect' not in output and 'OperationalError' not in output
    after = sorted(path.name for path in (MIGRATIONS_DIR / 'versions').iterdir())
    assert after == before


def test_create_app_registers_db_adopt(monkeypatch):
    import app_factory

    monkeypatch.setattr(app_factory, '_start_quality_model_retrainer', lambda app: None)
    app = app_factory.create_app()
    assert 'db-adopt' in app.cli.commands
    result = app.test_cli_runner().invoke(args=['db-adopt', '--help'])
    assert result.exit_code == 0
    assert '--check' in result.output
