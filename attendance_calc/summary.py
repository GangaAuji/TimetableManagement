"""Per-subject, per-component and overall figures for one student. Pure; the caller loads the rows."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from attendance_calc.projection import classes_needed, classes_that_can_be_missed
from attendance_calc.roster import in_roster
from attendance_calc.types import (
    ABSENT,
    CANCELLED,
    COMPONENTS,
    EXCUSED_EXCLUDE,
    EXCUSED_PRESENT,
    HELD,
    LATE,
    NOT_MARKED,
    PRESENT,
    Excuse,
    Figures,
    Mark,
    Policy,
    Session,
    Slot,
    Student,
    StudentSummary,
    SubjectFigures,
    UnmarkedLecture,
)

# Outcomes of classify(). Each says whether the session is in the denominator and in the numerator.
OUTSIDE = 'outside'        # cancelled, or the student is not in the roster that day
PRESENT_OUTCOME = 'present'
LATE_OUTCOME = 'late'
ABSENT_OUTCOME = 'absent'
EXCUSED_OUTCOME = 'excused'
NOT_MARKED_OUTCOME = 'not_marked'   # the lecture was never marked
UNRECORDED_OUTCOME = 'unrecorded'   # the lecture was marked but this student has no row

_HUNDREDTH = Decimal('0.01')


def _excused(excuses, student: Student, slot: Slot, session: Session) -> bool:
    for excuse in excuses:
        if excuse.student_id != student.id:
            continue
        if excuse.subject_id is not None and excuse.subject_id != slot.subject_id:
            continue
        if excuse.date_from <= session.date <= excuse.date_to:
            return True
    return False


def classify(session: Session, slot: Slot, student: Student, mark: Mark | None, excuses, policy: Policy) -> str:
    """Say what one session means for one student.

    A cancelled session, or a day the student is outside the roster, is
    OUTSIDE. A mark for the student on the session is evidence that they were
    in the roster that day (a transfer or an enrolment date does not hide
    marks the teacher saved). A Present or Late mark counts as that. An absence
    (an Absent mark, no mark on a held lecture, or a lecture nobody marked) is
    EXCUSED when an excuse covers the date; otherwise an Absent mark is ABSENT,
    a missing mark on a held lecture is UNRECORDED, and an unmarked lecture is
    NOT_MARKED.
    """
    if session.slot_id != slot.id or session.status == CANCELLED:
        return OUTSIDE
    if mark is None and not in_roster(slot, student, session.date):
        return OUTSIDE
    if mark is not None and mark.status == PRESENT:
        return PRESENT_OUTCOME
    if mark is not None and mark.status == LATE:
        return LATE_OUTCOME
    if _excused(excuses, student, slot, session):
        return EXCUSED_OUTCOME
    if mark is not None and mark.status == ABSENT:
        return ABSENT_OUTCOME
    if session.status == NOT_MARKED:
        return NOT_MARKED_OUTCOME
    return UNRECORDED_OUTCOME


def counts_in_denominator(outcome: str, policy: Policy) -> bool:
    if outcome in (PRESENT_OUTCOME, LATE_OUTCOME, ABSENT_OUTCOME):
        return True
    if outcome == EXCUSED_OUTCOME:
        return policy.excused_mode == EXCUSED_PRESENT
    if outcome in (NOT_MARKED_OUTCOME, UNRECORDED_OUTCOME):
        return policy.unmarked_counts_as_absent
    return False


def counts_as_attended(outcome: str, policy: Policy) -> bool:
    if outcome == PRESENT_OUTCOME:
        return True
    if outcome == LATE_OUTCOME:
        return policy.late_counts_as_present
    if outcome == EXCUSED_OUTCOME:
        return policy.excused_mode == EXCUSED_PRESENT
    return False


def countable_sessions(sessions, slot: Slot, student: Student, excuses, policy: Policy, marks=()) -> list:
    """Sessions of the slot that are in this student's denominator, in date order."""
    by_session = {(mark.session_id, mark.student_id): mark for mark in marks}
    kept = []
    for session in sorted(sessions, key=lambda item: (item.date, item.id)):
        if session.slot_id != slot.id:
            continue
        outcome = classify(session, slot, student, by_session.get((session.id, student.id)), excuses, policy)
        if counts_in_denominator(outcome, policy):
            kept.append(session)
    return kept


class _Tally:
    __slots__ = ('held', 'countable', 'present', 'late', 'absent', 'excused', 'not_marked', 'unrecorded', 'attended')

    def __init__(self):
        for name in self.__slots__:
            setattr(self, name, 0)

    def add(self, outcome: str, session_status: str, policy: Policy):
        if session_status == HELD:
            self.held += 1
        if outcome == PRESENT_OUTCOME:
            self.present += 1
        elif outcome == LATE_OUTCOME:
            self.late += 1
        elif outcome == ABSENT_OUTCOME:
            self.absent += 1
        elif outcome == EXCUSED_OUTCOME:
            self.excused += 1
        elif outcome == NOT_MARKED_OUTCOME:
            self.not_marked += 1
        elif outcome == UNRECORDED_OUTCOME:
            self.unrecorded += 1
        if counts_in_denominator(outcome, policy):
            self.countable += 1
        if counts_as_attended(outcome, policy):
            self.attended += 1

    def figures(self) -> Figures:
        return Figures(
            held=self.held, countable=self.countable, present=self.present, late=self.late, absent=self.absent,
            excused=self.excused, not_marked=self.not_marked, unrecorded=self.unrecorded, attended=self.attended,
            percentage=percentage(self.attended, self.countable),
        )


def percentage(attended: int, countable: int) -> Decimal | None:
    """attended * 100 / countable to two places, or None when nothing is countable."""
    if countable <= 0:
        return None
    return (Decimal(attended) * 100 / Decimal(countable)).quantize(_HUNDREDTH, rounding=ROUND_HALF_UP)


def summarise(student: Student, slots, sessions, marks, excuses=(), policy: Policy | None = None) -> StudentSummary:
    """Figures per subject, per component, and overall, pooled (sum over sum, not a mean of percentages).

    `slots` are the timetable rows to consider, `sessions` their lecture_sessions
    rows, `marks` the attendance rows (any student's rows may be passed; only
    this student's are read). Sessions of slots not passed are ignored. A
    subject the student is never in the roster for is not reported.
    """
    policy = policy or Policy()
    slot_by_id = {slot.id: slot for slot in slots}
    mark_by_session = {mark.session_id: mark for mark in marks if mark.student_id == student.id}
    subject_tallies = defaultdict(_Tally)
    subject_components = defaultdict(set)
    component_tallies = {name: _Tally() for name in COMPONENTS}
    overall = _Tally()
    for session in sorted(sessions, key=lambda item: (item.date, item.id)):
        slot = slot_by_id.get(session.slot_id)
        if slot is None:
            continue
        outcome = classify(session, slot, student, mark_by_session.get(session.id), excuses, policy)
        if outcome == OUTSIDE:
            continue
        subject_tallies[slot.subject_id].add(outcome, session.status, policy)
        subject_components[slot.subject_id].add(slot.component)
        component_tallies.setdefault(slot.component, _Tally()).add(outcome, session.status, policy)
        overall.add(outcome, session.status, policy)
    subjects = {
        subject_id: SubjectFigures(subject_id, tuple(sorted(subject_components[subject_id])), tally.figures())
        for subject_id, tally in sorted(subject_tallies.items())
    }
    components = {name: tally.figures() for name, tally in component_tallies.items() if tally.held or tally.countable or tally.not_marked}
    total = overall.figures()
    # With nothing countable there is no percentage, and no projection either: both show as a dash.
    has_data = total.countable > 0
    return StudentSummary(
        student_id=student.id,
        subjects=subjects,
        components=components,
        overall=total,
        policy=policy,
        classes_needed=classes_needed(total.attended, total.countable, policy.threshold) if has_data else None,
        classes_that_can_be_missed=classes_that_can_be_missed(total.attended, total.countable, policy.threshold) if has_data else None,
    )


def unmarked_report(sessions, slots) -> list:
    """Lectures nobody marked, oldest first, with the slot's subject and the teacher responsible that day."""
    slot_by_id = {slot.id: slot for slot in slots}
    rows = []
    for session in sessions:
        if session.status != NOT_MARKED:
            continue
        slot = slot_by_id.get(session.slot_id)
        taught_by = session.taught_by if session.taught_by is not None else (slot.faculty_user_id if slot else None)
        rows.append(UnmarkedLecture(session.id, session.slot_id, session.date, slot.subject_id if slot else None, taught_by))
    rows.sort(key=lambda row: (row.date, row.slot_id, row.session_id))
    return rows
