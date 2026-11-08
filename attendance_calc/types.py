"""Inputs and outputs of the attendance calculation. Plain frozen dataclasses, no database."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

HELD = 'held'
CANCELLED = 'cancelled'
NOT_MARKED = 'not_marked'
SESSION_STATUSES = frozenset((HELD, CANCELLED, NOT_MARKED))

PRESENT = 'Present'
ABSENT = 'Absent'
LATE = 'Late'
MARK_STATUSES = frozenset((PRESENT, ABSENT, LATE))

THEORY = 'Theory'
PRACTICAL = 'Practical'
COMPONENTS = (THEORY, PRACTICAL)

EXCUSED_EXCLUDE = 'exclude'
EXCUSED_PRESENT = 'present'


@dataclass(frozen=True)
class Slot:
    """One timetable row: a weekly lecture of one subject for one cohort."""

    id: int
    subject_id: int
    course_id: int
    class_id: int
    division_id: int | None = None
    component: str = THEORY
    is_elective: bool = False
    semester_id: int | None = None
    academic_year_id: int | None = None
    faculty_user_id: int | None = None
    is_active: bool = True
    batch_id: int | None = None


@dataclass(frozen=True)
class Session:
    """One lecture_sessions row: slot X on date D was held, cancelled, or never marked."""

    id: int
    slot_id: int
    date: date
    status: str = HELD
    taught_by: int | None = None


@dataclass(frozen=True)
class Mark:
    """One attendance row."""

    session_id: int
    student_id: int
    status: str


@dataclass(frozen=True)
class Student:
    id: int
    course_id: int
    class_id: int | None = None
    division_id: int | None = None
    enrolled_from: date | None = None
    enrolled_to: date | None = None
    # (subject_id, semester_id or None, academic_year_id or None) from student_subject_selections, not Withdrawn.
    chosen_subjects: frozenset = field(default_factory=frozenset)
    batch_ids: frozenset = field(default_factory=frozenset)


@dataclass(frozen=True)
class Excuse:
    """An approved excuse: the student's absences in the range do not count against them."""

    student_id: int
    date_from: date
    date_to: date
    subject_id: int | None = None


@dataclass(frozen=True)
class Policy:
    """The institution's answers to the open questions. Every number depends on these."""

    unmarked_counts_as_absent: bool = False
    late_counts_as_present: bool = True
    excused_mode: str = EXCUSED_EXCLUDE
    threshold: Decimal = Decimal('75')


@dataclass(frozen=True)
class Figures:
    """Counts for one subject, one component, or the whole student."""

    held: int = 0
    countable: int = 0
    present: int = 0
    late: int = 0
    absent: int = 0
    excused: int = 0
    not_marked: int = 0
    unrecorded: int = 0
    attended: int = 0
    percentage: Decimal | None = None


@dataclass(frozen=True)
class SubjectFigures:
    subject_id: int
    components: tuple
    figures: Figures


@dataclass(frozen=True)
class StudentSummary:
    student_id: int
    subjects: dict
    components: dict
    overall: Figures
    policy: Policy
    classes_needed: int | None = None
    classes_that_can_be_missed: int | None = None


@dataclass(frozen=True)
class UnmarkedLecture:
    session_id: int
    slot_id: int
    date: date
    subject_id: int | None
    taught_by: int | None
