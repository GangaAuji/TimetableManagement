"""Capabilities (docs/DESIGN_CAPABILITIES.md): the on/off rule with a fake cursor, settings validation,
the route guard, and revision 0015. No live database."""

import importlib.util
from pathlib import Path

import pytest
from flask import Flask

from core import capabilities
from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision


class _Cursor:
    """Answers table_exists and the capabilities SELECT from a dict; records writes."""

    def __init__(self, rows=None, table=True):
        self.rows = rows or {}
        self.table = table
        self.writes = []
        self._result = None

    def execute(self, statement, params=None):
        if 'information_schema.TABLES' in statement:
            self._result = [(1,)] if self.table else []
        elif statement.strip().startswith('SELECT capability'):
            self._result = [
                {'capability': name, 'enabled': row.get('enabled', 0), 'settings_json': row.get('settings_json'),
                 'updated_by': None, 'updated_at': None}
                for name, row in self.rows.items()
            ]
        elif statement.strip().startswith('INSERT INTO capabilities'):
            self.writes.append(params)
            self.rows[params[0]] = {'enabled': params[1], 'settings_json': params[2]}
            self._result = []
        else:
            raise AssertionError(f'unexpected statement: {statement[:60]}')

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)

    def close(self):
        pass


def _app(**config):
    app = Flask('capabilities-unit')
    app.config.update(config)
    return app


# the rule

def test_registry_names_are_unique_and_flag_names_follow_them():
    assert len(capabilities.NAMES) == len(set(capabilities.NAMES))
    assert capabilities.flag_name('bookings') == 'FEATURE_BOOKINGS'
    assert {'timetable_preferences', 'timetable_versions', 'bookings', 'channels', 'guardians'} <= set(capabilities.NAMES)


def test_settings_list_hides_capabilities_without_a_flow():
    hidden = {'privacy_tools', 'channels', 'guardians', 'calendar_feeds', 'attendance_policies'}
    assert hidden <= set(capabilities.NAMES)
    with _app().app_context():
        names = {row['name'] for row in capabilities.describe(_Cursor())['capabilities']}
    assert 'two_factor' in names and 'timetable_grid' in names
    assert hidden.isdisjoint(names)


def test_off_without_app_context_and_for_unknown_names():
    assert capabilities.flag_on('bookings') is False
    with _app().app_context():
        assert capabilities.flag_on('not_a_capability') is False
        assert capabilities.enabled(_Cursor(), 'bookings') is False          # default off, no row


def test_missing_table_turns_everything_off_even_defaults():
    with _app().app_context():
        cursor = _Cursor(table=False)
        assert capabilities.enabled(cursor, 'timetable_preferences') is False
        assert capabilities.snapshot(cursor) == {name: False for name in capabilities.NAMES}
        assert capabilities.describe(cursor)['table_exists'] is False


def test_defaults_apply_only_until_a_row_is_saved():
    with _app().app_context():
        assert capabilities.BY_NAME['timetable_preferences'].default is True
        assert capabilities.enabled(_Cursor(), 'timetable_preferences') is True
        assert capabilities.enabled(_Cursor({'timetable_preferences': {'enabled': 0}}), 'timetable_preferences') is False
        assert capabilities.enabled(_Cursor({'bookings': {'enabled': 1}}), 'bookings') is True


def test_server_flag_overrides_the_tenant_row():
    with _app(FEATURE_BOOKINGS=False).app_context():
        cursor = _Cursor({'bookings': {'enabled': 1}})
        assert capabilities.enabled(cursor, 'bookings') is False
        item = next(row for row in capabilities.describe(cursor)['capabilities'] if row['name'] == 'bookings')
        assert (item['flag'], item['enabled'], item['effective']) == (False, True, False)


def test_answers_are_cached_per_request_and_forgotten_after_save():
    app = _app()
    with app.test_request_context('/'):
        cursor = _Cursor({'bookings': {'enabled': 1}})
        assert capabilities.enabled(cursor, 'bookings') is True
        cursor.rows['bookings']['enabled'] = 0
        assert capabilities.enabled(cursor, 'bookings') is True             # cached
        capabilities.forget()
        assert capabilities.enabled(cursor, 'bookings') is False


# settings

def test_settings_overlay_defaults_and_ignore_values_of_the_wrong_kind():
    with _app().app_context():
        assert capabilities.settings(_Cursor(), 'bookings') == {'requires_approval': True}
        cursor = _Cursor({'bookings': {'enabled': 1, 'settings_json': '{"requires_approval": false, "stray": 1}'}})
        assert capabilities.settings(cursor, 'bookings') == {'requires_approval': False}
        cursor = _Cursor({'bookings': {'enabled': 1, 'settings_json': '{"requires_approval": "yes"}'}})
        assert capabilities.settings(cursor, 'bookings') == {'requires_approval': True}
        cursor = _Cursor({'bookings': {'enabled': 1, 'settings_json': 'not json'}})
        assert capabilities.settings(cursor, 'bookings') == {'requires_approval': True}


def test_clean_settings_rejects_unknown_keys_and_wrong_kinds():
    assert capabilities.clean_settings('workload_norms', {'enforce': 'hard'}) == {'enforce': 'hard'}
    assert capabilities.clean_settings('two_factor', {'required': 'staff'}) == {'required': 'staff'}
    assert capabilities.clean_settings('timetable_versions', {'keep_drafts': 3}) == {'keep_drafts': 3}
    for bad in ({'enforce': 'maybe'}, {'other': 1}, 'x', {'enforce': 1}):
        with pytest.raises(ValueError):
            capabilities.clean_settings('workload_norms', bad)
    with pytest.raises(ValueError):
        capabilities.clean_settings('timetable_versions', {'keep_drafts': True})
    with pytest.raises(ValueError):
        capabilities.clean_settings('timetable_versions', {'keep_drafts': -1})


def test_save_upserts_merging_settings_and_keeping_the_switch_when_not_given():
    with _app().app_context():
        cursor = _Cursor({'bookings': {'enabled': 1, 'settings_json': '{"requires_approval": true}'}})
        capabilities.save(cursor, 'bookings', settings_values={'requires_approval': False}, updated_by=7)
        assert cursor.writes[-1] == ('bookings', 1, '{"requires_approval": false}', 7)
        capabilities.save(cursor, 'bookings', enabled_value=False, updated_by=7)
        assert cursor.writes[-1] == ('bookings', 0, '{"requires_approval": false}', 7)
        with pytest.raises(ValueError):
            capabilities.save(cursor, 'nope', enabled_value=True)
        with pytest.raises(RuntimeError):
            capabilities.save(_Cursor(table=False), 'bookings', enabled_value=True)


# the route guard

def test_require_capability_answers_404_capability_off_and_none_when_on(monkeypatch):
    app = _app(FEATURE_BOOKINGS=True)

    class _Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def cursor(self, dictionary=True):
            return self._cursor

        def close(self):
            pass

    with app.test_request_context('/'):
        monkeypatch.setattr('extensions.get_db_connection', lambda: _Connection(_Cursor({'bookings': {'enabled': 0}})))
        response, status = capabilities.require_capability('bookings')
        assert status == 404 and response.get_json()['error']['code'] == 'capability_off'
    with app.test_request_context('/'):
        monkeypatch.setattr('extensions.get_db_connection', lambda: _Connection(_Cursor({'bookings': {'enabled': 1}})))
        assert capabilities.require_capability('bookings') is None
    with _app(FEATURE_BOOKINGS=False).test_request_context('/'):
        monkeypatch.setattr('extensions.get_db_connection', lambda: (_ for _ in ()).throw(AssertionError('flag off: no query')))
        assert capabilities.require_capability('bookings')[1] == 404


# revision 0015

def _load_0015():
    path = Path(MIGRATIONS_DIR) / 'versions' / '0015_capabilities.py'
    spec = importlib.util.spec_from_file_location('revision_0015', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _Bind:
    def __init__(self, present):
        self.present = set(present)

    def execute(self, statement, params):
        return _Result((1,) if params['table'] in self.present else None)


def test_0015_follows_0014_and_creates_only_the_missing_table(monkeypatch):
    assert head_revision() >= '0015_capabilities'
    module = _load_0015()
    assert module.down_revision == '0014_institutions'
    executed = []
    monkeypatch.setattr(module.op, 'execute', lambda statement: executed.append(statement))

    monkeypatch.setattr(module.op, 'get_bind', lambda: _Bind(set()))
    module.upgrade()
    assert len(executed) == 1 and 'CREATE TABLE capabilities' in executed[0]
    assert 'uq_capability_name' in executed[0] and 'settings_json' in executed[0]

    executed.clear()
    monkeypatch.setattr(module.op, 'get_bind', lambda: _Bind({'capabilities'}))
    module.upgrade()
    assert executed == []
    module.downgrade()
    assert executed == ['DROP TABLE `capabilities`']
