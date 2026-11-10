"""Tenancy without a database: hostname parsing, validation, the resolver's caching, session binding, path scoping."""

import pytest
from flask import Flask, g

from core.tenancy import (
    Tenant,
    bind,
    current_tenant,
    registry_enabled,
    scoped_model_path,
    scoped_relative_dir,
    scoped_storage_dir,
    tenant_context,
    tenants_to_serve,
)
from core.tenancy.registry import (
    Registry,
    default_database_name,
    normalise_host,
    valid_database_name,
    valid_hostname,
    valid_slug,
)
from core.tenancy.request import SESSION_KEY, bind_session, stamp_session

ALPHA = Tenant(slug='alpha', hostname='alpha.example.test', db_name='college_timetable_ci_alpha_test')


@pytest.mark.parametrize('raw, expected', [
    ('Alpha.Example.TEST:5000', 'alpha.example.test'),
    ('alpha.example.test', 'alpha.example.test'),
    ('  alpha.example.test ', 'alpha.example.test'),
    ('[::1]:5000', '::1'),
    ('', ''),
    (None, ''),
])
def test_normalise_host(raw, expected):
    assert normalise_host(raw) == expected


@pytest.mark.parametrize('slug, ok', [
    ('abc', True), ('abc-college', True), ('a', True), ('a' * 40, True),
    ('-abc', False), ('abc-', False), ('ABC', False), ('a b', False), ('a' * 41, False), ('', False), (None, False),
])
def test_valid_slug(slug, ok):
    assert valid_slug(slug) is ok


@pytest.mark.parametrize('hostname, ok', [
    ('abc.example.test', True), ('localhost', True), ('a-b.c', True),
    ('Abc.example.test', False), ('abc.example.test:80', False), ('http://abc', False), ('-abc.example', False), ('', False),
])
def test_valid_hostname(hostname, ok):
    assert valid_hostname(hostname) is ok


def test_database_names():
    assert default_database_name('abc-college') == 'college_timetable_abc_college'
    assert valid_database_name('college_timetable_abc')
    assert not valid_database_name('college-timetable')
    assert not valid_database_name('x' * 65)


def test_registry_is_disabled_without_the_setting():
    assert registry_enabled({'TENANT_REGISTRY_DB': None}) is False
    assert registry_enabled({'TENANT_REGISTRY_DB': '  '}) is False
    assert registry_enabled({'TENANT_REGISTRY_DB': 'registry'}) is True


def test_resolve_caches_hostname_lookups_until_they_expire():
    registry = Registry({'database': 'registry'}, cache_seconds=30)
    calls = []

    def lookup(hostname):
        calls.append(hostname)
        return ALPHA if hostname == ALPHA.hostname else None

    registry.by_hostname = lookup
    assert registry.resolve('ALPHA.example.test:8000', now=0) == ALPHA
    assert registry.resolve('alpha.example.test', now=10) == ALPHA
    assert registry.resolve('nobody.example.test', now=10) is None
    assert registry.resolve('nobody.example.test', now=20) is None
    assert calls == ['alpha.example.test', 'nobody.example.test']
    assert registry.resolve('alpha.example.test', now=31) == ALPHA
    assert calls[-1] == 'alpha.example.test' and len(calls) == 3
    registry.forget()
    assert registry.resolve('alpha.example.test', now=31) == ALPHA
    assert len(calls) == 4
    assert registry.resolve('', now=0) is None


def test_session_binding():
    fresh = {}
    assert bind_session(fresh, 'alpha') is False
    assert fresh == {}

    signed_in_here = {'user_id': 1, SESSION_KEY: 'alpha'}
    assert bind_session(signed_in_here, 'alpha') is False
    assert signed_in_here['user_id'] == 1

    other_college = {'user_id': 1, SESSION_KEY: 'beta'}
    assert bind_session(other_college, 'alpha') is True
    assert other_college == {}

    unstamped_sign_in = {'user_id': 1}
    assert bind_session(unstamped_sign_in, 'alpha') is True
    assert unstamped_sign_in == {}

    anonymous_elsewhere = {SESSION_KEY: 'beta', '_csrf_initialized': True}
    assert bind_session(anonymous_elsewhere, 'alpha') is True
    assert anonymous_elsewhere == {}


def test_stamp_session_marks_a_fresh_sign_in_only():
    session = {'user_id': 7}
    stamp_session(session, 'alpha')
    assert session[SESSION_KEY] == 'alpha'
    anonymous = {}
    stamp_session(anonymous, 'alpha')
    assert anonymous == {}


def test_paths_are_scoped_only_while_a_tenant_is_bound():
    app = Flask('tenancy-unit')
    assert scoped_relative_dir('uploads/profiles') == 'uploads/profiles'
    with tenant_context(app, ALPHA):
        assert current_tenant() == ALPHA
        assert scoped_relative_dir('uploads/profiles') == 'uploads/alpha/profiles'
        assert scoped_relative_dir('/uploads/') == 'uploads/alpha'
        assert scoped_storage_dir('/srv/uploads').replace('\\', '/') == '/srv/uploads/alpha'
        assert scoped_model_path('/srv/models/model.json').replace('\\', '/') == '/srv/models/alpha/model.json'
        assert scoped_model_path(None) is None
    with app.app_context():
        assert current_tenant() is None
        assert scoped_storage_dir('/srv/uploads') == '/srv/uploads'
        assert scoped_model_path('/srv/models/model.json') == '/srv/models/model.json'


def test_bind_refuses_a_real_database_in_a_testing_app():
    app = Flask('tenancy-unit')
    app.config['TESTING'] = True
    with app.app_context():
        with pytest.raises(RuntimeError, match='real database'):
            bind(Tenant(slug='prod', hostname='prod.example.test', db_name='college_timetable_db'))
        assert current_tenant() is None
        bind(ALPHA)
        assert g.tenant == ALPHA


def test_connection_settings_follow_the_bound_tenant_and_refuse_an_unbound_registry_app():
    from models.db import connection_settings

    app = Flask('tenancy-unit')
    app.config.update(MYSQL_HOST='h', MYSQL_USER='u', MYSQL_PASSWORD='p', MYSQL_DB='single', TENANT_REGISTRY_DB=None)
    with app.app_context():
        assert connection_settings()['database'] == 'single'
        bind(ALPHA)
        assert connection_settings()['database'] == ALPHA.db_name
    app.config['TENANT_REGISTRY_DB'] = 'registry'
    with app.app_context():
        with pytest.raises(RuntimeError, match='No tenant is bound'):
            connection_settings()
        bind(ALPHA)
        assert connection_settings()['database'] == ALPHA.db_name


def test_single_database_mode_serves_one_unnamed_tenant():
    app = Flask('tenancy-unit')
    app.config['TENANT_REGISTRY_DB'] = None
    assert tenants_to_serve(app) == [None]


def test_create_app_refuses_a_real_registry_name_in_testing(monkeypatch):
    from app import create_app
    from config.testing import TestingConfig

    class BadRegistry(TestingConfig):
        TENANT_REGISTRY_DB = 'college_timetable_db'

    with pytest.raises(RuntimeError, match='TENANT_REGISTRY_DB'):
        create_app(BadRegistry)


def test_tenant_commands_are_registered_and_tenant_option_needs_a_registry():
    from app import create_app
    from config.testing import TestingConfig

    app = create_app(TestingConfig)
    assert 'tenant' in app.cli.commands
    runner = app.test_cli_runner()
    assert runner.invoke(args=['tenant', '--help']).exit_code == 0
    result = runner.invoke(args=['seed', 'run', '--tenant', 'alpha'])
    assert result.exit_code != 0
    assert 'needs TENANT_REGISTRY_DB' in result.output
    result = runner.invoke(args=['tenant', 'list'])
    assert result.exit_code != 0
    assert 'TENANT_REGISTRY_DB is not set' in result.output
