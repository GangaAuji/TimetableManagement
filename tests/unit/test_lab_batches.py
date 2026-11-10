"""Lab batches without a database: revision 0012 statements, the roster rule with dated memberships,
the SQL twin's batch clause, and the cohort clash rule."""

import importlib.util
from datetime import date
from pathlib import Path

from academic_rules.clashes import cohort_slots_clash
from attendance_calc import Slot, Student, in_roster
from core.schema.status import head_revision
from data_access.teacher_attendance import roster_clauses
from services.attendance_calc import to_slot, to_student

_PATH = Path(__file__).resolve().parents[2] / 'migrations' / 'versions' / '0012_lab_batches.py'
_spec = importlib.util.spec_from_file_location('lab_batches_revision', _PATH)
_revision = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_revision)

ALL = {'lab_batch_groups', 'lab_batch_members', 'timetable.lab_batch_group_id', 'idx_timetable_lab_batch', 'fk_timetable_lab_batch'}


def test_0012_follows_notifications():
    assert head_revision() >= '0012_lab_batches'
    assert _revision.revision == '0012_lab_batches'
    assert _revision.down_revision == '0011_notifications'


def test_upgrade_creates_only_what_is_missing_in_dependency_order():
    statements = _revision.upgrade_statements(set())
    assert len(statements) == 5
    assert statements[0].lstrip().startswith('CREATE TABLE lab_batch_groups')
    assert statements[1].lstrip().startswith('CREATE TABLE lab_batch_members')
    assert 'ADD COLUMN lab_batch_group_id' in statements[2]
    assert 'ADD KEY idx_timetable_lab_batch' in statements[3]
    assert 'REFERENCES lab_batch_groups (id) ON DELETE SET NULL' in statements[4]
    assert _revision.upgrade_statements(ALL) == []
    partial = _revision.upgrade_statements({'lab_batch_groups', 'lab_batch_members', 'timetable.lab_batch_group_id'})
    assert [s.split()[5] for s in partial] == ['idx_timetable_lab_batch', 'fk_timetable_lab_batch']


def test_tables_follow_the_design():
    groups = _revision.LAB_BATCH_GROUPS
    assert 'UNIQUE KEY uq_lab_batch_group (course_id, class_id, division_id, academic_year_id, semester_id, name)' in groups
    assert 'capacity int(11) DEFAULT NULL' in groups
    members = _revision.LAB_BATCH_MEMBERS
    assert 'UNIQUE KEY uq_lab_batch_member (lab_batch_group_id, student_id)' in members
    assert 'ended_at date DEFAULT NULL' in members
    assert 'REFERENCES lab_batch_groups (id) ON DELETE CASCADE' in members
    assert 'REFERENCES students (id) ON DELETE CASCADE' in members


def test_downgrade_drops_only_what_exists_in_reverse():
    assert _revision.downgrade_statements(ALL) == [
        'ALTER TABLE timetable DROP FOREIGN KEY fk_timetable_lab_batch',
        'ALTER TABLE timetable DROP KEY idx_timetable_lab_batch',
        'ALTER TABLE timetable DROP COLUMN lab_batch_group_id',
        'DROP TABLE lab_batch_members',
        'DROP TABLE lab_batch_groups',
    ]
    assert _revision.downgrade_statements(set()) == []


# Roster rule --------------------------------------------------------------

SLOT = Slot(21, 5, 1, 2, 3, component='Practical', batch_id=40)
WHOLE = Slot(22, 5, 1, 2, 3, component='Practical')


def test_dated_memberships_decide_a_batch_slot_by_date():
    moved = Student(7, 1, 2, 3, batch_memberships=frozenset({
        (40, date(2026, 1, 1), date(2026, 3, 15)),
        (41, date(2026, 3, 16), None),
    }))
    assert in_roster(SLOT, moved, date(2026, 3, 10))
    assert not in_roster(SLOT, moved, date(2026, 3, 20))
    assert in_roster(Slot(23, 5, 1, 2, 3, batch_id=41), moved, date(2026, 3, 20))
    assert in_roster(WHOLE, moved, date(2026, 3, 20)), 'a whole-division slot ignores batches'


def test_plain_batch_ids_apply_when_no_dated_memberships_are_given():
    assert in_roster(SLOT, Student(7, 1, 2, 3, batch_ids=frozenset({40})), date(2026, 3, 10))
    assert not in_roster(SLOT, Student(8, 1, 2, 3), date(2026, 3, 10))


def test_to_student_and_to_slot_carry_the_batch_columns():
    student = to_student(
        {'id': 7, 'course_id': 1, 'class_id': 2, 'division_id': 3},
        memberships=[
            {'lab_batch_group_id': 40, 'added_at': date(2026, 1, 1), 'ended_at': date(2026, 3, 15)},
            {'lab_batch_group_id': 41, 'added_at': date(2026, 3, 16), 'ended_at': None},
        ],
    )
    assert student.batch_ids == frozenset({41})
    assert (40, date(2026, 1, 1), date(2026, 3, 15)) in student.batch_memberships
    slot = to_slot({'id': 21, 'subject_id': 5, 'course_id': 1, 'class_id': 2, 'division_id': 3, 'lab_batch_group_id': 40, 'theory_practical': 'Practical'})
    assert slot.batch_id == 40 and slot.component == 'Practical'


def test_sql_twin_adds_a_dated_membership_clause_for_batch_slots():
    lecture = {'course_id': 1, 'class_id': 2, 'division_id': 3, 'lab_batch_group_id': 40}
    clauses, params = roster_clauses(lecture)
    assert any('lab_batch_members' in clause and 'CURDATE()' in clause for clause in clauses)
    assert params == [1, 2, 3, 40]
    clauses, params = roster_clauses(lecture, date(2026, 3, 10))
    assert params == [1, 2, 3, 40, date(2026, 3, 10), date(2026, 3, 10)]
    assert not any('lab_batch_members' in clause for clause in roster_clauses({'course_id': 1, 'class_id': 2})[0])


def test_cohort_clash_rule_lets_different_batches_share_a_time():
    assert cohort_slots_clash(None, None)
    assert cohort_slots_clash(None, 40)
    assert cohort_slots_clash(40, None)
    assert cohort_slots_clash(40, 40)
    assert not cohort_slots_clash(40, 41)
