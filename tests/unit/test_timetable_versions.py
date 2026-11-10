"""Timetable versions (Phase J2): the pure diff, score summaries, draft pruning and revision 0017."""

import importlib.util
from pathlib import Path

import pytest

from core.schema.baseline import MIGRATIONS_DIR
from core.schema.status import head_revision
from services.timetable import versions


def _slot(day, start, end, subject=1, faculty=10, room=None, batch=None, cohort=(1, 1, 1), name=None, sid=0):
    return {
        'id': sid, 'course_id': cohort[0], 'class_id': cohort[1], 'division_id': cohort[2],
        'day': day, 'start_time': start, 'end_time': end,
        'subject_id': subject, 'subject_name': name or f'S{subject}', 'faculty_id': faculty, 'faculty_name': f'F{faculty}',
        'room_id': room, 'room_number': f'R{room}' if room else '', 'lab_batch_group_id': batch, 'batch_name': '',
        'version_id': None, 'is_active': True,
    }


# Diff ---------------------------------------------------------------------------------------------

def test_diff_classifies_unchanged_moved_added_removed_and_room_changes():
    before = [
        _slot('Monday', '09:00', '09:45', subject=1, room=1),
        _slot('Monday', '09:45', '10:30', subject=2, room=1),
        _slot('Tuesday', '09:00', '09:45', subject=3, room=2),
        _slot('Wednesday', '09:00', '09:45', subject=4, room=2),
    ]
    after = [
        _slot('Monday', '09:00', '09:45', subject=1, room=1),            # unchanged
        _slot('Monday', '09:45', '10:30', subject=2, room=3),            # room changed
        _slot('Thursday', '09:00', '09:45', subject=3, room=2),          # moved
        _slot('Friday', '09:00', '09:45', subject=5, room=2),            # added (subject 4 removed)
    ]
    result = versions.diff(before, after)
    assert result['totals'] == {'unchanged': 1, 'room_changed': 1, 'moved': 1, 'added': 1, 'removed': 1}
    cohort = result['cohorts'][0]
    kinds = {(c['kind'], c['subject_name']) for c in cohort['changes']}
    assert kinds == {('room_changed', 'S2'), ('moved', 'S3'), ('added', 'S5'), ('removed', 'S4')}
    moved = next(c for c in cohort['changes'] if c['kind'] == 'moved')
    assert moved['before']['day'] == 'Tuesday' and moved['after']['day'] == 'Thursday'
    # The unchanged slot is not listed among the changes but is counted.
    assert all(c['kind'] != 'unchanged' for c in cohort['changes'])
    assert cohort['counts']['unchanged'] == 1
    # Everything involved the same teacher, so the faculty summary has one row with the change counts.
    assert result['faculty'] == [{'faculty_id': 10, 'faculty_name': 'F10', 'moved': 1, 'added': 1, 'removed': 1, 'room_changed': 1}]


def test_diff_pairs_repeated_sessions_by_count_and_keeps_cohorts_apart():
    before = [
        _slot('Monday', '09:00', '09:45'), _slot('Monday', '09:45', '10:30'),
        _slot('Monday', '09:00', '09:45', cohort=(1, 1, 2), faculty=11),
    ]
    after = [
        _slot('Monday', '09:00', '09:45'), _slot('Tuesday', '09:45', '10:30'),   # one of two sessions moved
        _slot('Monday', '09:00', '09:45', cohort=(1, 1, 2), faculty=11),
    ]
    result = versions.diff(before, after)
    assert [c['division_id'] for c in result['cohorts']] == [1, 2]
    assert result['cohorts'][0]['counts'] == {'unchanged': 1, 'moved': 1}
    assert result['cohorts'][1]['counts'] == {'unchanged': 1}
    assert result['totals'] == {'unchanged': 2, 'moved': 1}


def test_diff_of_a_cohort_without_live_rows_reports_everything_added():
    after = [_slot('Monday', '09:00', '09:45'), _slot('Monday', '09:45', '10:30', subject=2)]
    result = versions.diff([], after)
    assert result['totals'] == {'added': 2}
    assert result['cohorts'][0]['before'] == [] and len(result['cohorts'][0]['after']) == 2


def test_diff_treats_different_batches_as_different_sessions():
    before = [_slot('Monday', '09:00', '10:30', subject=7, batch=1)]
    after = [_slot('Monday', '09:00', '10:30', subject=7, batch=2)]
    result = versions.diff(before, after)
    assert result['totals'] == {'added': 1, 'removed': 1}


# Scores -------------------------------------------------------------------------------------------

def test_scores_and_summary_tolerate_missing_or_broken_documents():
    assert versions.scores({'score_json': None}) == {}
    assert versions.scores({'score_json': 'not json'}) == {}
    assert versions.scores(None) == {}
    doc = {'1-1-1': {'quality_score': 80, 'rule_cost': 4, 'assigned': 10, 'unassigned': 1}, '1-1-2': {'quality_score': 60, 'rule_cost': 2, 'assigned': 8, 'unassigned': 0}}
    assert versions.summarize_scores(doc) == {'quality_score': 70.0, 'rule_cost': 6, 'assigned': 18, 'unassigned': 1}
    assert versions.summarize_scores({}) == {'quality_score': None, 'rule_cost': None, 'assigned': 0, 'unassigned': 0}


# Pruning and helpers (fake cursor) ------------------------------------------------------------------

class _Cursor:
    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.statements = []
        self._rows = []

    def execute(self, statement, params=()):
        self.statements.append((' '.join(statement.split()), tuple(params)))
        if statement.lstrip().startswith('SELECT id FROM timetable_versions'):
            self._rows = [{'id': value} for value in self.drafts]
        elif statement.lstrip().startswith('DELETE FROM timetable_versions'):
            self.drafts.remove(params[0])
            self._rows = []
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


def test_prune_drafts_keeps_the_newest_and_the_protected_one():
    cursor = _Cursor(drafts=[9, 8, 7, 6, 5, 4])   # newest first, 9 is the draft just created
    removed = versions.prune_drafts(cursor, 1, keep=3, protect=9)
    assert removed == 3
    assert cursor.drafts == [9, 8, 7]
    deletes = [params for sql, params in cursor.statements if sql.startswith('DELETE FROM timetable WHERE version_id')]
    assert deletes == [(6,), (5,), (4,)]
    assert all('COALESCE(is_active, 1) = 0' in sql for sql, _ in cursor.statements if sql.startswith('DELETE FROM timetable WHERE'))


def test_prune_drafts_without_protection_keeps_exactly_keep():
    cursor = _Cursor(drafts=[3, 2, 1])
    assert versions.prune_drafts(cursor, 1, keep=2) == 1
    assert cursor.drafts == [3, 2]
    assert versions.prune_drafts(_Cursor(drafts=[1]), 1, keep=5) == 0


def test_busy_clause_counts_other_draft_rows_and_ignores_live_rows_of_covered_cohorts():
    sql, params = versions.busy_clause(42, alias='t')
    assert params == (42, 42)
    assert 'NOT EXISTS' in sql and 'timetable_version_cohorts vc' in sql and 't.version_id = %s' in sql
    assert 'COALESCE(t.is_active, 1) = 1' in sql


def test_rename_rejects_blank_or_long_labels():
    with pytest.raises(ValueError):
        versions.rename(_Cursor([]), 1, '   ')
    with pytest.raises(ValueError):
        versions.rename(_Cursor([]), 1, 'x' * 121)
    cursor = _Cursor([])
    assert versions.rename(cursor, 1, '  Autumn draft  ') == 'Autumn draft'


def test_hhmm_handles_time_timedelta_and_text():
    from datetime import time, timedelta

    assert versions._hhmm(time(9, 5)) == '09:05'
    assert versions._hhmm(timedelta(hours=13, minutes=30)) == '13:30'
    assert versions._hhmm('09:00:00') == '09:00'
    assert versions._hhmm(None) == ''


# Revision 0017 -------------------------------------------------------------------------------------

def _load_0017():
    path = Path(MIGRATIONS_DIR) / 'versions' / '0017_timetable_versions.py'
    spec = importlib.util.spec_from_file_location('revision_0017', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0017_follows_0016_and_creates_only_what_is_missing():
    assert head_revision() >= '0017_timetable_versions'
    module = _load_0017()
    assert module.down_revision == '0016_timetable_preferences'
    names = [name for name, _, _ in module.OBJECTS]
    assert names == ['timetable_versions', 'timetable_version_cohorts', 'timetable.version_id', 'fk_timetable_version']
    assert names.index('timetable.version_id') < names.index('fk_timetable_version')

    fresh = module.upgrade_statements(set())
    assert len(fresh) == 4 and 'CREATE TABLE timetable_versions' in fresh[0]
    partial = module.upgrade_statements({'timetable_versions', 'timetable_version_cohorts'})
    assert [s.split()[0:3] for s in partial] == [['ALTER', 'TABLE', 'timetable'], ['ALTER', 'TABLE', 'timetable']]
    assert module.upgrade_statements(set(names)) == []

    drops = module.downgrade_statements(set(names))
    assert drops[0].startswith('ALTER TABLE timetable DROP FOREIGN KEY') and drops[-1] == 'DROP TABLE timetable_versions'
    assert module.downgrade_statements({'timetable_versions'}) == ['DROP TABLE timetable_versions']


def test_capability_registry_has_timetable_versions_on_by_default_with_keep_drafts():
    from core.capabilities import BY_NAME

    capability = BY_NAME['timetable_versions']
    assert capability.default is True and capability.phase.startswith('J')
    assert capability.settings['keep_drafts'] == ('int', 10)
