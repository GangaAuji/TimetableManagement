"""Golden tests for attendance_calc with hand-calculated percentages. No database.

Cohort FY A, three weeks, Mon 2 Mar to Fri 20 Mar 2026. Slots: Physics (Theory)
Mon and Thu; Lab (Practical) Wed; German (elective, Theory) Tue; EVS (Theory,
no division) Fri. Dated holiday Thu 12 Mar. Students: Asha (division A, no
German), Ben (division A, chose German), Chen (division A, enrolled from Mon
9 Mar), Dev (division B). See docs/DESIGN_ATTENDANCE_CALCULATION.md, 5.4.
"""

from datetime import date
from decimal import Decimal

import pytest

from academic_rules.holidays import is_working_day
from attendance_calc import (
    CANCELLED,
    HELD,
    NOT_MARKED,
    Excuse,
    Mark,
    Policy,
    Session,
    Slot,
    Student,
    can_still_reach,
    classes_needed,
    classes_that_can_be_missed,
    classify,
    countable_sessions,
    in_roster,
    meets,
    percentage,
    summarise,
    unmarked_report,
)
from attendance_calc.summary import (
    ABSENT_OUTCOME,
    EXCUSED_OUTCOME,
    NOT_MARKED_OUTCOME,
    OUTSIDE,
    PRESENT_OUTCOME,
    UNRECORDED_OUTCOME,
)

COURSE, CLASS, DIV_A, DIV_B = 1, 1, 1, 2
PHYSICS, LAB, GERMAN, EVS = 100, 101, 102, 103
TEACHER = 500

PHYSICS_MON = Slot(10, PHYSICS, COURSE, CLASS, DIV_A, faculty_user_id=TEACHER)
PHYSICS_THU = Slot(11, PHYSICS, COURSE, CLASS, DIV_A, faculty_user_id=TEACHER)
LAB_WED = Slot(12, LAB, COURSE, CLASS, DIV_A, component='Practical', faculty_user_id=TEACHER)
GERMAN_TUE = Slot(13, GERMAN, COURSE, CLASS, DIV_A, is_elective=True, faculty_user_id=TEACHER)
EVS_FRI = Slot(14, EVS, COURSE, CLASS, None, faculty_user_id=TEACHER)
SLOTS = (PHYSICS_MON, PHYSICS_THU, LAB_WED, GERMAN_TUE, EVS_FRI)

ASHA = Student(1, COURSE, CLASS, DIV_A)
BEN = Student(2, COURSE, CLASS, DIV_A, chosen_subjects=frozenset({(GERMAN, None, None)}))
CHEN = Student(3, COURSE, CLASS, DIV_A, enrolled_from=date(2026, 3, 9))
DEV = Student(4, COURSE, CLASS, DIV_B)


def d(day):
    return date(2026, 3, day)


SESSIONS = (
    Session(1, PHYSICS_MON.id, d(2), HELD),
    Session(2, PHYSICS_THU.id, d(5), HELD),
    Session(3, PHYSICS_MON.id, d(9), HELD),
    # Thu 12 Mar: holiday, no row.
    Session(4, PHYSICS_MON.id, d(16), HELD),
    Session(5, PHYSICS_THU.id, d(19), CANCELLED),
    Session(6, LAB_WED.id, d(4), HELD),
    Session(7, LAB_WED.id, d(11), HELD),
    Session(8, LAB_WED.id, d(18), HELD),
    Session(9, GERMAN_TUE.id, d(3), HELD),
    Session(10, GERMAN_TUE.id, d(10), HELD),
    Session(11, GERMAN_TUE.id, d(17), NOT_MARKED, taught_by=TEACHER),
    Session(12, EVS_FRI.id, d(6), HELD),
    Session(13, EVS_FRI.id, d(13), HELD),
    Session(14, EVS_FRI.id, d(20), HELD),
)

MARKS = (
    Mark(1, ASHA.id, 'Present'), Mark(2, ASHA.id, 'Absent'), Mark(3, ASHA.id, 'Present'), Mark(4, ASHA.id, 'Present'),
    Mark(6, ASHA.id, 'Present'), Mark(7, ASHA.id, 'Present'), Mark(8, ASHA.id, 'Absent'),
    Mark(12, ASHA.id, 'Present'), Mark(13, ASHA.id, 'Present'), Mark(14, ASHA.id, 'Absent'),
    Mark(9, BEN.id, 'Present'), Mark(10, BEN.id, 'Late'),
    Mark(3, CHEN.id, 'Present'), Mark(4, CHEN.id, 'Absent'),
    Mark(12, DEV.id, 'Present'), Mark(13, DEV.id, 'Present'), Mark(14, DEV.id, 'Present'),
)


def pct(text):
    return Decimal(text)


def figures(summary, subject_id):
    return summary.subjects[subject_id].figures


# 1. Normal lecture

def test_normal_lecture_counts_held_sessions_only():
    physics = figures(summarise(ASHA, SLOTS, SESSIONS, MARKS), PHYSICS)
    assert (physics.held, physics.countable, physics.attended) == (4, 4, 3)
    assert (physics.present, physics.absent, physics.late) == (3, 1, 0)
    assert physics.percentage == pct('75.00')
    assert classes_needed(3, 4, 75) == 0
    assert classes_that_can_be_missed(3, 4, 75) == 0


# 2. Elective

def test_elective_counts_only_for_students_who_chose_it():
    ben = summarise(BEN, SLOTS, SESSIONS, MARKS)
    german = figures(ben, GERMAN)
    assert (german.held, german.countable, german.attended, german.not_marked) == (2, 2, 2, 1)
    assert german.percentage == pct('100.00')
    asha = summarise(ASHA, SLOTS, SESSIONS, MARKS)
    assert GERMAN not in asha.subjects
    assert asha.overall.countable == 10


def test_unmarked_lecture_counts_against_the_student_only_when_the_policy_says_so():
    strict = Policy(unmarked_counts_as_absent=True)
    german = figures(summarise(BEN, SLOTS, SESSIONS, MARKS, policy=strict), GERMAN)
    assert (german.countable, german.attended, german.not_marked) == (3, 2, 1)
    assert german.percentage == pct('66.67')


# 3. No division

def test_whole_class_lecture_is_in_every_division():
    asha = figures(summarise(ASHA, SLOTS, SESSIONS, MARKS), EVS)
    dev = summarise(DEV, SLOTS, SESSIONS, MARKS)
    assert asha.percentage == pct('66.67')
    assert figures(dev, EVS).percentage == pct('100.00')
    assert set(dev.subjects) == {EVS}


# 4. Cancelled

def test_cancelled_session_is_in_no_count():
    physics = figures(summarise(ASHA, SLOTS, SESSIONS, MARKS), PHYSICS)
    assert physics.held == 4
    thursday = [s for s in SESSIONS if s.slot_id == PHYSICS_THU.id]
    assert [s.id for s in countable_sessions(thursday, PHYSICS_THU, ASHA, (), Policy(), MARKS)] == [2]
    assert classify(SESSIONS[4], PHYSICS_THU, ASHA, None, (), Policy()) == OUTSIDE


# 5. Holiday

def test_holiday_has_no_session_and_a_makeup_lecture_on_it_counts():
    holidays = [{'holiday_date': d(12), 'day_of_week': None, 'is_recurring': 0, 'applies_to_program': 'Both'}]
    assert is_working_day(d(12), 'UG', holidays) is False
    assert is_working_day(d(5), 'UG', holidays) is True
    makeup = SESSIONS + (Session(15, PHYSICS_THU.id, d(12), HELD),)
    marks = MARKS + (Mark(15, ASHA.id, 'Present'),)
    physics = figures(summarise(ASHA, SLOTS, makeup, marks), PHYSICS)
    assert (physics.held, physics.countable, physics.attended) == (5, 5, 4)
    assert physics.percentage == pct('80.00')


def test_recurring_holiday_blocks_its_weekday_for_its_program_only():
    holidays = [{'holiday_date': None, 'day_of_week': 'Saturday', 'is_recurring': 1, 'applies_to_program': 'PG'}]
    saturday = date(2026, 3, 7)
    assert is_working_day(saturday, 'PG', holidays) is False
    assert is_working_day(saturday, 'UG', holidays) is True
    assert is_working_day(saturday, None, holidays) is False
    assert is_working_day(date(2026, 3, 6), 'PG', holidays) is True


# 6. Excused absence

EXCUSE = (Excuse(ASHA.id, d(4), d(6)),)


def test_excused_absence_leaves_the_denominator_by_default():
    summary = summarise(ASHA, SLOTS, SESSIONS, MARKS, EXCUSE)
    physics = figures(summary, PHYSICS)
    assert (physics.held, physics.countable, physics.attended, physics.excused) == (4, 3, 3, 1)
    assert physics.percentage == pct('100.00')
    # A Present mark inside the excused range still counts as present.
    assert figures(summary, LAB).percentage == pct('66.67')
    assert figures(summary, EVS).percentage == pct('66.67')
    assert summary.overall.excused == 1
    assert summary.overall.percentage == pct('77.78')


def test_excused_absence_counts_as_present_in_present_mode():
    summary = summarise(ASHA, SLOTS, SESSIONS, MARKS, EXCUSE, Policy(excused_mode='present'))
    physics = figures(summary, PHYSICS)
    assert (physics.countable, physics.attended, physics.excused) == (4, 4, 1)
    assert physics.percentage == pct('100.00')


def test_subject_excuse_applies_to_that_subject_only():
    lab_only = (Excuse(ASHA.id, d(18), d(18), subject_id=LAB),)
    summary = summarise(ASHA, SLOTS, SESSIONS, MARKS, lab_only)
    assert figures(summary, LAB).percentage == pct('100.00')
    assert figures(summary, PHYSICS).percentage == pct('75.00')


# 7. Mid-semester student

def test_student_enrolled_mid_semester_is_counted_from_enrolment():
    summary = summarise(CHEN, SLOTS, SESSIONS, MARKS)
    physics = figures(summary, PHYSICS)
    assert (physics.held, physics.countable, physics.attended) == (2, 2, 1)
    assert physics.percentage == pct('50.00')
    assert classes_needed(1, 2, 75) == 2
    assert in_roster(PHYSICS_MON, CHEN, d(2)) is False and in_roster(PHYSICS_MON, CHEN, d(9)) is True


# 8. Unmarked lecture

def test_unmarked_lecture_is_excluded_and_reported():
    german = figures(summarise(BEN, SLOTS, SESSIONS, MARKS), GERMAN)
    assert german.not_marked == 1 and german.countable == 2
    [row] = unmarked_report(SESSIONS, SLOTS)
    assert (row.session_id, row.slot_id, row.date, row.subject_id, row.taught_by) == (11, 13, d(17), GERMAN, TEACHER)


def test_unmarked_report_falls_back_to_the_slot_teacher():
    [row] = unmarked_report([Session(99, GERMAN_TUE.id, d(24), NOT_MARKED)], SLOTS)
    assert row.taught_by == TEACHER


# Pooled totals, components, projections

def test_overall_and_components_are_pooled_not_averaged():
    summary = summarise(ASHA, SLOTS, SESSIONS, MARKS)
    assert summary.components['Theory'].percentage == pct('71.43')      # 5/7
    assert summary.components['Practical'].percentage == pct('66.67')   # 2/3
    assert (summary.overall.attended, summary.overall.countable) == (7, 10)
    assert summary.overall.percentage == pct('70.00')                   # not the 69.44 mean
    assert summary.classes_needed == 2 and summary.classes_that_can_be_missed == 0
    assert summary.subjects[LAB].components == ('Practical',)


def test_projections():
    assert classes_needed(7, 10, 75) == 2 and meets(9, 12, 75) is True
    assert classes_needed(0, 0, 75) == 0
    assert classes_needed(3, 4, Decimal('75')) == 0
    assert classes_needed(3, 4, 100) is None and classes_needed(4, 4, 100) == 0
    assert classes_that_can_be_missed(9, 10, 75) == 2                   # 9/12 = 75 %
    assert classes_that_can_be_missed(0, 0, 75) == 0
    assert can_still_reach(7, 10, 75, 0) is False
    assert can_still_reach(7, 10, 75, 2) is True
    assert can_still_reach(7, 10, 75, None) is None
    with pytest.raises(ValueError):
        classes_needed(5, 4, 75)
    with pytest.raises(ValueError):
        classes_needed(1, 4, 0)


def test_percentage_is_none_with_nothing_countable_and_never_above_100():
    assert percentage(0, 0) is None
    assert percentage(2, 3) == pct('66.67')
    nobody = Student(9, COURSE, CLASS, DIV_A, enrolled_from=d(30))
    summary = summarise(nobody, SLOTS, SESSIONS, MARKS)
    assert summary.subjects == {} and summary.overall.percentage is None and summary.overall.countable == 0
    assert summary.classes_needed is None and summary.classes_that_can_be_missed is None


def test_late_counts_as_present_unless_the_policy_says_otherwise():
    assert figures(summarise(BEN, SLOTS, SESSIONS, MARKS), GERMAN).late == 1
    strict = figures(summarise(BEN, SLOTS, SESSIONS, MARKS, policy=Policy(late_counts_as_present=False)), GERMAN)
    assert (strict.countable, strict.attended) == (2, 1) and strict.percentage == pct('50.00')


def test_a_student_without_a_mark_on_a_marked_lecture_is_unrecorded():
    session = Session(1, PHYSICS_MON.id, d(2), HELD)
    assert classify(session, PHYSICS_MON, BEN, None, (), Policy()) == UNRECORDED_OUTCOME
    ben = figures(summarise(BEN, SLOTS, SESSIONS, MARKS), PHYSICS)
    assert (ben.held, ben.unrecorded, ben.countable) == (4, 4, 0) and ben.percentage is None
    strict = figures(summarise(BEN, SLOTS, SESSIONS, MARKS, policy=Policy(unmarked_counts_as_absent=True)), PHYSICS)
    assert (strict.countable, strict.attended) == (4, 0) and strict.percentage == pct('0.00')


def test_classify_outcomes():
    policy = Policy()
    assert classify(SESSIONS[1], PHYSICS_THU, ASHA, MARKS[1], (), policy) == ABSENT_OUTCOME
    assert classify(SESSIONS[1], PHYSICS_THU, ASHA, MARKS[1], EXCUSE, policy) == EXCUSED_OUTCOME
    assert classify(SESSIONS[10], GERMAN_TUE, BEN, None, (), policy) == NOT_MARKED_OUTCOME
    assert classify(SESSIONS[10], GERMAN_TUE, ASHA, None, (), policy) == OUTSIDE
    assert classify(SESSIONS[0], PHYSICS_THU, ASHA, MARKS[0], (), policy) == OUTSIDE   # session of another slot


def test_a_mark_puts_the_student_in_the_roster_for_that_session():
    # Dev is in division B, but the teacher marked her in a division A Physics lecture: the mark counts.
    marked = MARKS + (Mark(1, DEV.id, 'Present'),)
    assert classify(SESSIONS[0], PHYSICS_MON, DEV, marked[-1], (), Policy()) == PRESENT_OUTCOME
    dev = summarise(DEV, SLOTS, SESSIONS, marked)
    assert (figures(dev, PHYSICS).held, figures(dev, PHYSICS).attended) == (1, 1)
    assert dev.overall.countable == 4 and dev.overall.percentage == pct('100.00')
    # Chen's enrolment starts 9 Mar; a mark on 2 Mar still counts, the unmarked 5 Mar lecture still does not.
    early = MARKS + (Mark(1, CHEN.id, 'Absent'),)
    chen = figures(summarise(CHEN, SLOTS, SESSIONS, early), PHYSICS)
    assert (chen.countable, chen.absent, chen.unrecorded) == (3, 2, 0)
    # A cancelled session with a mark stays outside.
    assert classify(SESSIONS[4], PHYSICS_THU, ASHA, Mark(5, ASHA.id, 'Present'), (), Policy()) == OUTSIDE


# Roster rule

def test_roster_rule():
    on = d(2)
    assert in_roster(PHYSICS_MON, ASHA, on) and not in_roster(PHYSICS_MON, DEV, on)
    assert in_roster(EVS_FRI, DEV, on) and in_roster(EVS_FRI, ASHA, on)
    assert in_roster(GERMAN_TUE, BEN, on) and not in_roster(GERMAN_TUE, ASHA, on)
    other_class = Student(8, COURSE, 2, DIV_A)
    assert not in_roster(EVS_FRI, other_class, on)
    scoped = Slot(20, GERMAN, COURSE, CLASS, DIV_A, is_elective=True, semester_id=7, academic_year_id=3)
    chose_other_semester = Student(5, COURSE, CLASS, DIV_A, chosen_subjects=frozenset({(GERMAN, 8, 3)}))
    chose_this = Student(6, COURSE, CLASS, DIV_A, chosen_subjects=frozenset({(GERMAN, 7, 3)}))
    assert not in_roster(scoped, chose_other_semester, on) and in_roster(scoped, chose_this, on)
    batch_slot = Slot(21, LAB, COURSE, CLASS, DIV_A, batch_id=40)
    assert in_roster(batch_slot, Student(7, COURSE, CLASS, DIV_A, batch_ids=frozenset({40})), on)
    assert not in_roster(batch_slot, ASHA, on)
    left = Student(9, COURSE, CLASS, DIV_A, enrolled_to=d(10))
    assert in_roster(PHYSICS_MON, left, d(9)) and not in_roster(PHYSICS_MON, left, d(16))
