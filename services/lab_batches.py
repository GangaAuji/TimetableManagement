"""Lab batches: the rules behind docs/DESIGN_LAB_BATCHES.md.

A split is one (course, class, division or whole class, academic year,
semester or whole year). Its groups ("A1", "A2") are rows of
lab_batch_groups; a student is in at most one group of a split at a time.
Memberships are dated (added_at, ended_at) so a move keeps the old group's
lectures up to the move; attendance_calc.roster reads those dates.
"""

from datetime import date, timedelta

from data_access import lab_batches as rows


class LabBatchError(ValueError):
    """A rule was broken; `code` names it for the API."""

    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code


def _today(on_date):
    return on_date or date.today()


def groups(cursor, **filters):
    return rows.fetch_groups(cursor, **filters)


def group(cursor, group_id):
    found = rows.fetch_group(cursor, group_id)
    if not found:
        raise LabBatchError('lab_batch_not_found')
    return found


def create_group(cursor, values):
    """Create one group. `values` has course_id, class_id, division_id, academic_year_id, semester_id, name, capacity, is_active."""
    _check_cohort(cursor, values)
    clean = {
        'course_id': values['course_id'], 'class_id': values['class_id'], 'division_id': values.get('division_id'),
        'academic_year_id': values['academic_year_id'], 'semester_id': values.get('semester_id'),
        'name': values['name'], 'capacity': values.get('capacity'), 'is_active': 1 if values.get('is_active', True) else 0,
    }
    if rows.fetch_same_named(cursor, clean):
        raise LabBatchError('lab_batch_exists')
    return rows.insert_group(cursor, clean)


def update_group(cursor, group_id, values):
    found = group(cursor, group_id)
    if values.get('semester_id') is not None:
        _exists(cursor, 'semesters', values['semester_id'], 'lab_batch_semester_invalid')
    if rows.fetch_same_named(cursor, {**found, 'name': values['name'], 'semester_id': values.get('semester_id')}, exclude_id=group_id):
        raise LabBatchError('lab_batch_exists')
    rows.update_group(cursor, group_id, {
        'name': values['name'], 'capacity': values.get('capacity'),
        'is_active': 1 if values.get('is_active', True) else 0, 'semester_id': values.get('semester_id'),
    })


def delete_group(cursor, group_id):
    if not rows.delete_group(cursor, group_id):
        raise LabBatchError('lab_batch_not_found')


def members(cursor, group_id, *, current_only=True):
    return rows.fetch_members(cursor, group_id, current_only=current_only)


def roster_view(cursor, group_id):
    """The split's students with the group each is in now: what the assignment screen shows."""
    found = group(cursor, group_id)
    siblings = rows.fetch_sibling_groups(cursor, found)
    current = rows.fetch_current_memberships(cursor, [item['id'] for item in siblings])
    students = rows.fetch_cohort_students(cursor, found['course_id'], found['class_id'], found.get('division_id'))
    return {
        'group': found,
        'siblings': siblings,
        'students': [{**student, 'lab_batch_group_id': current.get(student['id'])} for student in students],
    }


def set_members(cursor, group_id, student_ids, on_date=None):
    """Make exactly `student_ids` the group's current members from `on_date` (default today).

    A student already in a sibling group is moved: the old membership ends
    the day before. A current member not in the list leaves the group that
    day. Students outside the split's cohort are refused. Returns the counts.
    """
    found = group(cursor, group_id)
    day = _today(on_date)
    wanted = set()
    for value in student_ids:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise LabBatchError('lab_batch_students_invalid')
        wanted.add(value)
    cohort = {student['id'] for student in rows.fetch_cohort_students(cursor, found['course_id'], found['class_id'], found.get('division_id'))}
    if not wanted <= cohort:
        raise LabBatchError('lab_batch_students_outside_cohort')
    if found.get('capacity') and len(wanted) > int(found['capacity']):
        raise LabBatchError('lab_batch_over_capacity')
    siblings = sorted({item['id'] for item in rows.fetch_sibling_groups(cursor, found)} | {group_id})
    current = rows.fetch_current_memberships(cursor, siblings)
    added = moved = removed = 0
    for student_id, current_group in current.items():
        if current_group == group_id and student_id not in wanted:
            rows.end_membership(cursor, group_id, student_id, day)
            removed += 1
    for student_id in sorted(wanted):
        current_group = current.get(student_id)
        if current_group == group_id:
            continue
        if current_group is not None:
            rows.end_membership(cursor, current_group, student_id, day - timedelta(days=1))
            moved += 1
        else:
            added += 1
        rows.add_membership(cursor, group_id, student_id, day)
    return {'added': added, 'moved': moved, 'removed': removed, 'members': len(wanted)}


def auto_split(cursor, group_id, on_date=None):
    """Deal the split's students across its active groups in roll-number order, round robin, from `on_date`.

    Every student of the cohort ends up in exactly one sibling group;
    existing memberships are replaced. Capacity is respected when every
    group has one; otherwise the deal is even. Returns members per group.
    """
    found = group(cursor, group_id)
    siblings = rows.fetch_sibling_groups(cursor, found)
    if len(siblings) < 2:
        raise LabBatchError('lab_batch_needs_two_groups')
    students = rows.fetch_cohort_students(cursor, found['course_id'], found['class_id'], found.get('division_id'))
    capacities = [item.get('capacity') for item in siblings]
    if all(capacities) and sum(int(value) for value in capacities) < len(students):
        raise LabBatchError('lab_batch_over_capacity')
    buckets = {item['id']: [] for item in siblings}
    order = [item['id'] for item in siblings]
    index = 0
    for student in students:
        placed = False
        for _ in range(len(order)):
            target = order[index % len(order)]
            index += 1
            limit = next((item.get('capacity') for item in siblings if item['id'] == target), None)
            if limit and len(buckets[target]) >= int(limit):
                continue
            buckets[target].append(student['id'])
            placed = True
            break
        if not placed:
            raise LabBatchError('lab_batch_over_capacity')
    result = {}
    for target, ids in buckets.items():
        result[target] = set_members(cursor, target, ids, on_date)
    return result


def _check_cohort(cursor, values):
    _exists(cursor, 'courses', values.get('course_id'), 'lab_batch_course_invalid')
    _exists(cursor, 'classes', values.get('class_id'), 'lab_batch_class_invalid')
    if values.get('division_id') is not None:
        _exists(cursor, 'divisions', values['division_id'], 'lab_batch_division_invalid')
    _exists(cursor, 'academic_years', values.get('academic_year_id'), 'lab_batch_year_invalid')
    if values.get('semester_id') is not None:
        _exists(cursor, 'semesters', values['semester_id'], 'lab_batch_semester_invalid')


def _exists(cursor, table, row_id, code):
    if not isinstance(row_id, int) or isinstance(row_id, bool) or row_id <= 0:
        raise LabBatchError(code)
    cursor.execute(f'SELECT 1 FROM `{table}` WHERE id = %s', (row_id,))
    if cursor.fetchone() is None:
        raise LabBatchError(code)
