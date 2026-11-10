import os
import re

from config.base import Config

FORBIDDEN_DATABASES = frozenset({'college_timetable_db', 'college_timetable_db_test'})
TEST_DB_PREFIX = 'college_timetable_ci_'
TEST_DB_SUFFIX = '_test'
_SAFE_NAME = re.compile(r'[a-z0-9_]{1,64}')


def test_database_problem(name):
    """Return why `name` may not be used as a test database, or None.

    Tests create and drop this database, so only college_timetable_ci_*_test
    names are accepted, and the two real databases are refused by name.
    """
    name = name or ''
    if name.lower() in FORBIDDEN_DATABASES:
        return f'{name!r} is a real database; tests must never use it.'
    if not name.startswith(TEST_DB_PREFIX):
        return f'{name!r} does not start with {TEST_DB_PREFIX!r}.'
    if not name.endswith(TEST_DB_SUFFIX):
        return f'{name!r} does not end with {TEST_DB_SUFFIX!r}.'
    if not _SAFE_NAME.fullmatch(name):
        return f'{name!r} may contain only lowercase letters, digits and underscores (64 at most).'
    return None


class TestingConfig(Config):
    """Settings for pytest. The database comes from MYSQL_DB and must be a *_test name."""

    TESTING = True
    MYSQL_DB = os.environ.get('MYSQL_DB')
    # Tests that exercise tenancy set this on a subclass to a college_timetable_ci_*_test name.
    TENANT_REGISTRY_DB = None
    QUALITY_MODEL_RETRAIN_INTERVAL_MINUTES = 0
    BACKGROUND_WORKERS = False
    CONFIGURE_LOGGING = False
    # A fixed, non-secret key so face templates written by tests are encrypted the way production ones are.
    FACE_TEMPLATE_KEY = 'dGVzdC1vbmx5LWtleS1ub3QtZm9yLXByb2QtdXNlISE='
    FACE_CONSENT_REQUIRED = True
    # The outbox is exercised with a fake sender; no SMTP server is ever contacted from tests.
    SMTP_HOST = None
    NOTIFICATION_RETRY_SECONDS = 5
    # A lock conflict fails in 2 s instead of the server default (50 s), so a
    # test that hits one fails quickly. test_audit_regressions.py also signs in
    # with the default wait.
    MYSQL_INIT_COMMAND = 'SET SESSION innodb_lock_wait_timeout = 2'
