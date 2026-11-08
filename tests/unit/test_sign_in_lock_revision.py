"""Revision 0006 statements. No live database."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / 'migrations' / 'versions' / '0006_sign_in_lock.py'
_spec = importlib.util.spec_from_file_location('sign_in_lock_revision', _PATH)
_revision = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_revision)


def test_revision_follows_the_seed_history():
    assert _revision.revision == '0006_sign_in_lock'
    assert _revision.down_revision == '0005_seed_history'


def test_upgrade_adds_only_missing_columns():
    assert [s.split()[5] for s in _revision.upgrade_statements(set())] == ['failed_window_start', 'locked_until']
    assert [s.split()[5] for s in _revision.upgrade_statements({'failed_window_start'})] == ['locked_until']
    assert _revision.upgrade_statements({'failed_window_start', 'locked_until'}) == []
    assert all('NULL DEFAULT NULL' in s for s in _revision.upgrade_statements(set()))


def test_downgrade_drops_only_existing_columns_in_reverse():
    assert _revision.downgrade_statements({'failed_window_start', 'locked_until'}) == [
        'ALTER TABLE users DROP COLUMN locked_until',
        'ALTER TABLE users DROP COLUMN failed_window_start',
    ]
    assert _revision.downgrade_statements({'locked_until'}) == ['ALTER TABLE users DROP COLUMN locked_until']
    assert _revision.downgrade_statements(set()) == []
