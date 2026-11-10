"""Overlap checks. No request or session state."""

from datetime import time


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def times_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """Return whether two time spans share any minute."""
    return _minutes(a_start) < _minutes(b_end) and _minutes(a_end) > _minutes(b_start)


def cohort_slots_clash(batch_a, batch_b) -> bool:
    """Whether two slots of one cohort (same course, class and division) that share a time clash.

    Two different lab batches of the division may meet at the same time:
    their students are disjoint. A whole-division slot (no batch) clashes
    with everything, and a batch clashes with itself.
    """
    if batch_a is None or batch_b is None:
        return True
    return batch_a == batch_b


def cohort_timetable_clashes(cursor, course_id, class_id, division_id, day, start_time, end_time, *, lab_batch_group_id=None, exclude_id=None):
    """Active timetable rows of the cohort in the span that the new slot would clash with (cohort_slots_clash)."""
    clauses = [
        'course_id = %s', 'class_id = %s', 'day_of_week = %s', 'COALESCE(is_active, 1) = 1',
        'NOT (end_time <= %s OR start_time >= %s)',
    ]
    params = [course_id, class_id, day, start_time, end_time]
    if division_id is None:
        pass  # a whole-class slot clashes with every division's slot at that time
    else:
        clauses.append('(division_id = %s OR division_id IS NULL)')
        params.append(division_id)
    if lab_batch_group_id is not None:
        clauses.append('(lab_batch_group_id IS NULL OR lab_batch_group_id = %s)')
        params.append(lab_batch_group_id)
    if exclude_id is not None:
        clauses.append('id <> %s')
        params.append(exclude_id)
    cursor.execute(
        f"SELECT id, division_id, lab_batch_group_id, start_time, end_time FROM timetable WHERE {' AND '.join(clauses)}",
        tuple(params),
    )
    return cursor.fetchall()


def faculty_timetable_free(cursor, faculty_id, day, start_time, end_time, *, active_only: bool) -> bool:
    """Return whether this faculty has no timetable row in the span."""
    active_sql = " AND COALESCE(is_active, 1) = 1" if active_only else ""
    cursor.execute(
        f"""
        SELECT 1
        FROM timetable
        WHERE faculty_id = %s
          AND day_of_week = %s
          AND NOT (end_time <= %s OR start_time >= %s){active_sql}
        LIMIT 1
        """,
        (faculty_id, day, start_time, end_time),
    )
    return cursor.fetchone() is None
