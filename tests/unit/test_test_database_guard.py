"""The test-database guard: only college_timetable_ci_*_test names, settings only from .env.test."""

import os
from pathlib import Path

import dotenv
import pytest

from config.testing import test_database_problem as database_problem

TEST_ENV_FILE = Path(__file__).resolve().parents[2] / '.env.test'
DATABASE_SETTINGS = ('MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DB')


@pytest.mark.parametrize('name', [
    'college_timetable_ci_test',
    'college_timetable_ci_fresh_test',
    'college_timetable_ci_admin_cli_test',
])
def test_ci_test_names_are_accepted(name):
    assert database_problem(name) is None


@pytest.mark.parametrize('name', [
    'college_timetable_db',
    'college_timetable_db_test',
    'COLLEGE_TIMETABLE_DB',
    'college_timetable_test',
    'college_timetable_ci',
    'college_timetable_ci_live',
    'other_college_timetable_ci_test',
    'College_Timetable_CI_test',
    'college_timetable_ci_x`; DROP DATABASE college_timetable_db; -- _test',
    'college_timetable_ci_' + 'x' * 60 + '_test',
    '',
    None,
])
def test_other_names_are_refused(name):
    assert database_problem(name)


def test_the_real_databases_are_refused_by_name():
    assert 'real database' in database_problem('college_timetable_db')
    assert 'real database' in database_problem('college_timetable_db_test')


def test_live_helpers_use_the_same_guard():
    from tests.integration.live_helpers import checked_name, scratch_name

    with pytest.raises(RuntimeError):
        checked_name('college_timetable_db_test')
    assert database_problem(scratch_name('probe')) is None


def test_database_settings_come_from_env_test():
    values = dotenv.dotenv_values(TEST_ENV_FILE)
    for name in DATABASE_SETTINGS:
        if values.get(name) is not None:
            assert os.environ.get(name) == values[name], f'{name} does not come from {TEST_ENV_FILE.name}'
    assert values.get('MYSQL_DB'), f'{TEST_ENV_FILE.name} must set MYSQL_DB'


def test_the_testing_config_uses_the_env_test_database():
    from config import Config

    assert Config.TESTING is True
    assert Config.MYSQL_DB == dotenv.dotenv_values(TEST_ENV_FILE)['MYSQL_DB']
