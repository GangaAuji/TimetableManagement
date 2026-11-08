"""Attendance figures for screens, exports and notifications. The only place that turns rows into percentages.

Loads students, slots, lecture sessions, marks and excuses through
data_access.attendance_calc and hands them to the pure attendance_calc
package. Nothing here computes a number itself; it only shapes the result.
"""

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from flask import current_app, has_app_context

from attendance_calc import (
    CANCELLED,
    PRACTICAL,
    THEORY,
    Excuse,
    Figures,
    Mark,
    Policy,
    Session,
    Slot,
    Student,
    StudentSummary,
    classify,
    in_roster,
    summarise,
)
from attendance_calc.summary import (
    ABSENT_OUTCOME,
    EXCUSED_OUTCOME,
    LATE_OUTCOME,
    NOT_MARKED_OUTCOME,
    OUTSIDE,
    PRESENT_OUTCOME,
    UNRECORDED_OUTCOME,
    counts_as_attended,
    counts_in_denominator,
    percentage,
)
from data_access import attendance_calc as rows

DEFAULT_THRESHOLD = Decimal('75')

OUTCOME_LABELS = {
    PRESENT_OUTCOME: 'Present',
    LATE_OUTCOME: 'Late',
    ABSENT_OUTCOME: 'Absent',
    EXCUSED_OUTCOME: 'Excused',
    NOT_MARKED_OUTCOME: 'Not marked',
    UNRECORDED_OUTCOME: 'Unrecorded',
}


def threshold_setting():
    """ATTENDANCE_THRESHOLD_PERCENT from the app config, else 75. Values outside (0, 100] fall back."""
    value = current_app.config.get('ATTENDANCE_THRESHOLD_PERCENT') if has_app_context() else None
    return parse_threshold(value) or DEFAULT_THRESHOLD


def parse_threshold(value):
    """A Decimal in (0, 100] from a setting or a query parameter, or None when it is not one."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or not 0 < number <= 100:
        return None
    return number


def policy(threshold=None):
    """The institution's policy: the recommended defaults with the configured threshold."""
    return Policy(threshold=parse_threshold(threshold) or threshold_setting())


def component_of(row):
    """Theory or Practical for a slot, from its subject's theory_practical and course_type."""
    kind = (row.get('theory_practical') or THEORY)
    if kind == PRACTICAL:
        return PRACTICAL
    if kind == THEORY:
        return THEORY
    return PRACTICAL if 'Practical' in (row.get('course_type') or '') else THEORY


def to_student(row, selections=()):
    return Student(
        id=row['id'], course_id=row['course_id'], class_id=row.get('class_id'), division_id=row.get('division_id'),
        enrolled_from=row.get('enrolled_from'), enrolled_to=row.get('enrolled_to'),
        chosen_subjects=frozenset(
            (choice['subject_id'], choice.get('semester_id'), choice.get('academic_year_id'))
            for choice in selections
        ),
    )


def to_slot(row):
    return Slot(
        id=row['id'], subject_id=row['subject_id'], course_id=row['course_id'], class_id=row['class_id'],
        division_id=row.get('division_id'), component=component_of(row), is_elective=bool(row.get('is_elective')),
        semester_id=row.get('semester_id'), academic_year_id=row.get('academic_year_id'),
        faculty_user_id=row.get('faculty_user_id'), is_active=bool(row.get('is_active', 1)),
    )


def to_session(row):
    return Session(id=row['id'], slot_id=row['timetable_id'], date=row['session_date'], status=row['status'], taught_by=row.get('taught_by'))


def to_mark(row):
    return Mark(session_id=row['session_id'], student_id=row['student_id'], status=row['status'])


def to_excuse(row):
    return Excuse(student_id=row['student_id'], date_from=row['date_from'], date_to=row['date_to'], subject_id=row.get('subject_id'))


@dataclass
class Inputs:
    """Everything the summaries of a set of students need, loaded once."""

    students: dict = field(default_factory=dict)      # id -> row
    selections: dict = field(default_factory=dict)    # student id -> [rows]
    slot_rows: dict = field(default_factory=dict)     # id -> row
    slots: dict = field(default_factory=dict)         # id -> Slot
    session_rows: dict = field(default_factory=dict)  # id -> row
    sessions: list = field(default_factory=list)      # Session
    mark_rows: dict = field(default_factory=dict)     # (session id, student id) -> row
    marks: list = field(default_factory=list)         # Mark
    excuses: list = field(default_factory=list)       # Excuse

    def student(self, student_id):
        return to_student(self.students[student_id], self.selections.get(student_id, ()))


def load_inputs(cursor, student_rows, date_from=None, date_to=None):
    inputs = Inputs(students={row['id']: row for row in student_rows})
    student_ids = list(inputs.students)
    if not student_ids:
        return inputs
    for choice in rows.fetch_selections(cursor, student_ids):
        inputs.selections.setdefault(choice['student_id'], []).append(choice)
    cohorts = {(row['course_id'], row['class_id']) for row in student_rows if row.get('course_id') and row.get('class_id')}
    for slot in rows.fetch_slots(cursor, cohorts, student_ids):
        inputs.slot_rows[slot['id']] = slot
        inputs.slots[slot['id']] = to_slot(slot)
    for session in rows.fetch_sessions(cursor, list(inputs.slots), date_from, date_to):
        inputs.session_rows[session['id']] = session
        inputs.sessions.append(to_session(session))
    for mark in rows.fetch_marks(cursor, student_ids, list(inputs.session_rows)):
        inputs.mark_rows[(mark['session_id'], mark['student_id'])] = mark
        inputs.marks.append(to_mark(mark))
    inputs.excuses = [to_excuse(row) for row in rows.fetch_excuses(cursor, student_ids)]
    return inputs


@dataclass
class Report:
    """One student's figures with the rows behind them."""

    student: dict
    summary: StudentSummary
    inputs: Inputs

    @property
    def student_id(self):
        return self.student['id']

    @property
    def overall(self):
        return self.summary.overall

    def subject_name(self, subject_id):
        for row in self.inputs.slot_rows.values():
            if row['subject_id'] == subject_id:
                return row.get('subject_name') or ''
        return ''

    def outcomes(self, subject_id=None):
        """(session row, slot row, outcome, mark row or None) for every session that counts for this student, oldest first."""
        student = self.inputs.student(self.student_id)
        excuses = [excuse for excuse in self.inputs.excuses if excuse.student_id == self.student_id]
        result = []
        for session in self.inputs.sessions:
            slot = self.inputs.slots.get(session.slot_id)
            if slot is None or (subject_id is not None and slot.subject_id != subject_id):
                continue
            mark_row = self.inputs.mark_rows.get((session.id, self.student_id))
            mark = to_mark(mark_row) if mark_row else None
            outcome = classify(session, slot, student, mark, excuses, self.summary.policy)
            if outcome == OUTSIDE:
                continue
            result.append((self.inputs.session_rows[session.id], self.inputs.slot_rows[slot.id], outcome, mark_row))
        return result

    def cancelled(self, subject_id=None):
        """Cancelled sessions of the student's slots, for information only; they are in no count."""
        student = self.inputs.student(self.student_id)
        result = []
        for session in self.inputs.sessions:
            slot = self.inputs.slots.get(session.slot_id)
            if slot is None or session.status != CANCELLED or (subject_id is not None and slot.subject_id != subject_id):
                continue
            if in_roster(slot, student, session.date):
                result.append((self.inputs.session_rows[session.id], self.inputs.slot_rows[slot.id]))
        return result


def student_report_from(inputs, student_id, chosen_policy):
    """The report for one of the students the inputs were loaded for."""
    student = inputs.student(student_id)
    summary = summarise(student, inputs.slots.values(), inputs.sessions, inputs.marks, inputs.excuses, chosen_policy)
    return Report(student=inputs.students[student_id], summary=summary, inputs=inputs)


def student_report(cursor, student_id=None, *, user_id=None, policy_=None, date_from=None, date_to=None):
    """The report for one student (by students.id or users.id), or None when there is no such student."""
    row = rows.fetch_student(cursor, student_id) if student_id is not None else rows.fetch_student_by_user(cursor, user_id)
    if not row:
        return None
    inputs = load_inputs(cursor, [row], date_from, date_to)
    return student_report_from(inputs, row['id'], policy_ or policy())


def cohort_reports(cursor, *, course_id=None, class_id=None, division_id=None, policy_=None, active_only=True, date_from=None, date_to=None):
    """Reports for every (active) student of a cohort, in roll-number order. The whole institution when no filter is given."""
    student_rows = rows.fetch_students(cursor, course_id=course_id, class_id=class_id, division_id=division_id, active_only=active_only)
    inputs = load_inputs(cursor, student_rows, date_from, date_to)
    chosen = policy_ or policy()
    return [student_report_from(inputs, row['id'], chosen) for row in student_rows]


def defaulters(cursor, *, threshold=None, course_id=None, class_id=None, division_id=None):
    """Students whose overall percentage is below the threshold, lowest first. Students with nothing countable are not defaulters."""
    chosen = policy(threshold)
    reports = cohort_reports(cursor, course_id=course_id, class_id=class_id, division_id=division_id, policy_=chosen)
    below = [report for report in reports if report.overall.percentage is not None and report.overall.percentage < chosen.threshold]
    below.sort(key=lambda report: (report.overall.percentage, str(report.student.get('roll_number') or ''), report.student_id))
    return below, chosen


def figures_dict(figures):
    """Counts as ints and the percentage as a float with two places, or None when nothing is countable."""
    return {
        'held': figures.held,
        'countable': figures.countable,
        'present': figures.present,
        'late': figures.late,
        'absent': figures.absent,
        'excused': figures.excused,
        'not_marked': figures.not_marked,
        'unrecorded': figures.unrecorded,
        'attended': figures.attended,
        'percentage': percent_value(figures.percentage),
    }


def percent_value(value):
    return None if value is None else float(value)


def outcome_label(outcome):
    return OUTCOME_LABELS.get(outcome, outcome)


def pooled_figures(reports):
    """One Figures for a group of reports: every count summed, the percentage from the pooled counts."""
    counts = dict.fromkeys(_COUNT_FIELDS, 0)
    for report in reports:
        for name in _COUNT_FIELDS:
            counts[name] += getattr(report.overall, name)
    return Figures(**counts, percentage=percentage(counts['attended'], counts['countable']))


_COUNT_FIELDS = ('held', 'countable', 'present', 'late', 'absent', 'excused', 'not_marked', 'unrecorded', 'attended')


def period_statistics(cursor, date_from, date_to, **filters):
    """The institution's (or a cohort's) pooled figures for the sessions between the dates, with the number of
    students who had something countable and of distinct lectures held."""
    reports = cohort_reports(cursor, date_from=date_from, date_to=date_to, **filters)
    total = pooled_figures(reports)
    students = sum(1 for report in reports if report.overall.countable)
    lectures = set()
    for report in reports:
        for session, _slot, _outcome, _mark in report.outcomes():
            lectures.add(session['id'])
    return {**figures_dict(total), 'students': students, 'lectures': len(lectures)}


def daily_trend(reports):
    """Per session date, oldest first: the pooled counts and percentage across the reports."""
    tallies = defaultdict(lambda: {'countable': 0, 'attended': 0, 'present': 0, 'late': 0, 'absent': 0, 'excused': 0, 'not_marked': 0})
    for report in reports:
        chosen = report.summary.policy
        for session, _slot, outcome, _mark in report.outcomes():
            tally = tallies[session['session_date']]
            if outcome in tally:
                tally[outcome] += 1
            if counts_in_denominator(outcome, chosen):
                tally['countable'] += 1
            if counts_as_attended(outcome, chosen):
                tally['attended'] += 1
    return [
        {'date': day.isoformat(), **tally, 'percentage': percent_value(percentage(tally['attended'], tally['countable']))}
        for day, tally in sorted(tallies.items())
    ]


def cohort_figures(reports, keys=('course_name', 'class_name', 'division_name')):
    """Pooled figures per cohort (by the named student columns), in cohort order, with the number of students."""
    groups = OrderedDict()
    for report in reports:
        groups.setdefault(tuple(report.student.get(key) for key in keys), []).append(report)
    result = []
    for group, members in groups.items():
        total = pooled_figures(members)
        result.append({**dict(zip(keys, group)), 'students': len(members), **figures_dict(total)})
    return result


def monthly_breakdown(report, subject_id=None, months=6):
    """Per calendar month, newest first: the counts and the percentage, from the same outcomes as the summary."""
    tallies = defaultdict(lambda: {'present': 0, 'late': 0, 'absent': 0, 'excused': 0, 'not_marked': 0, 'unrecorded': 0, 'countable': 0, 'attended': 0})
    for session, _slot, outcome, _mark in report.outcomes(subject_id):
        key = session['session_date'].strftime('%Y-%m')
        tally = tallies[key]
        tally[outcome] += 1
        if counts_in_denominator(outcome, report.summary.policy):
            tally['countable'] += 1
        if counts_as_attended(outcome, report.summary.policy):
            tally['attended'] += 1
    result = []
    for key in sorted(tallies, reverse=True)[:months]:
        tally = tallies[key]
        result.append({'month': key, **tally, 'percentage': percent_value(percentage(tally['attended'], tally['countable']))})
    return result
