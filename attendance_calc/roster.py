"""The one roster rule. data_access.teacher_attendance.fetch_lecture_roster is its SQL twin."""

from datetime import date

from attendance_calc.types import Slot, Student


def in_roster(slot: Slot, student: Student, on: date) -> bool:
    """Return whether the student belongs to the slot's lecture on that date.

    Same course and class. Same division when the slot has one; a slot with no
    division takes the whole class. An elective slot needs a chosen-subject
    entry for its subject whose semester and year match the slot's when the
    slot names them. A slot with a lab batch needs that batch. When enrolment
    dates are set, the date must fall inside them.
    """
    if student.course_id != slot.course_id or student.class_id != slot.class_id:
        return False
    if slot.division_id is not None and student.division_id != slot.division_id:
        return False
    if slot.is_elective and not _chose(slot, student):
        return False
    if slot.batch_id is not None and slot.batch_id not in student.batch_ids:
        return False
    if student.enrolled_from is not None and on < student.enrolled_from:
        return False
    if student.enrolled_to is not None and on > student.enrolled_to:
        return False
    return True


def _chose(slot: Slot, student: Student) -> bool:
    for subject_id, semester_id, academic_year_id in student.chosen_subjects:
        if subject_id != slot.subject_id:
            continue
        if slot.semester_id is not None and semester_id != slot.semester_id:
            continue
        if slot.academic_year_id is not None and academic_year_id != slot.academic_year_id:
            continue
        return True
    return False
