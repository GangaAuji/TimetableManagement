"""Attendance calculation. Pure functions; every screen, export and notification gets its numbers here.

No Flask, no SQL, no clock. `data_access/attendance_calc.py` (later phase)
loads the inputs and `services/attendance_calc.py` is the entry point for
callers. See docs/DESIGN_ATTENDANCE_CALCULATION.md, section 2.
"""

from attendance_calc.projection import can_still_reach, classes_needed, classes_that_can_be_missed, meets
from attendance_calc.roster import in_roster
from attendance_calc.summary import classify, countable_sessions, percentage, summarise, unmarked_report
from attendance_calc.types import (
    ABSENT,
    CANCELLED,
    COMPONENTS,
    EXCUSED_EXCLUDE,
    EXCUSED_PRESENT,
    HELD,
    LATE,
    MARK_STATUSES,
    NOT_MARKED,
    PRACTICAL,
    PRESENT,
    SESSION_STATUSES,
    THEORY,
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

__all__ = [
    'ABSENT', 'CANCELLED', 'COMPONENTS', 'EXCUSED_EXCLUDE', 'EXCUSED_PRESENT', 'HELD', 'LATE', 'MARK_STATUSES',
    'NOT_MARKED', 'PRACTICAL', 'PRESENT', 'SESSION_STATUSES', 'THEORY',
    'Excuse', 'Figures', 'Mark', 'Policy', 'Session', 'Slot', 'Student', 'StudentSummary', 'SubjectFigures',
    'UnmarkedLecture',
    'can_still_reach', 'classes_needed', 'classes_that_can_be_missed', 'classify', 'countable_sessions', 'in_roster',
    'meets', 'percentage', 'summarise', 'unmarked_report',
]
