"""Accreditation (NAAC/NBA) report datasets: defaulter list, subject-wise attendance, monthly register, faculty workload, syllabus coverage.

Each builder returns (rows, fieldnames, labels, meta) from the same
attendance_calc figures the screens show, so a binder printout agrees with
the dashboard. Filters are the cleaned dict the report API stores on the
job: course_id, class_id, division_id, subject_id, start_date, end_date,
month (YYYY-MM), threshold, department_id, faculty_id.
"""

from calendar import monthrange
from collections import OrderedDict
from datetime import date

from services.attendance_calc import cohort_reports, percent_value, policy, pooled_figures, threshold_setting

ACCREDITATION_TYPES = ('defaulters', 'subject-wise', 'monthly-register', 'faculty-workload', 'syllabus-coverage', 'co-attainment')

DEFAULTER_FIELDS = [
    'roll_number', 'full_name', 'course_name', 'class_name', 'division_name',
    'held', 'countable', 'attended', 'absent', 'not_marked', 'attendance_percentage', 'shortfall_percent', 'classes_needed',
]
SUBJECT_FIELDS = [
    'subject_code', 'subject_name', 'course_name', 'class_name', 'division_name', 'students',
    'held', 'countable', 'attended', 'present', 'late', 'absent', 'excused', 'not_marked',
    'attendance_percentage', 'students_below_threshold',
]
WORKLOAD_FIELDS = [
    'employee_id', 'faculty_name', 'department_name', 'weekly_slots', 'weekly_hours',
    'scheduled', 'held', 'cancelled', 'not_marked', 'as_proxy', 'held_percent',
]
_OUTCOME_CODES = {'present': 'P', 'late': 'L', 'absent': 'A', 'excused': 'E', 'not_marked': 'NM', 'unrecorded': '-'}


def _int(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError('Report filters must be whole numbers.')


def _cohort(filters):
    return {
        'course_id': _int(filters.get('course_id')),
        'class_id': _int(filters.get('class_id')),
        'division_id': _int(filters.get('division_id')),
    }


def _dates(filters):
    return filters.get('start_date') or None, filters.get('end_date') or None


def _month_bounds(value):
    """'YYYY-MM' -> (first day, last day). The current month when empty."""
    if value:
        try:
            year, month = (int(part) for part in str(value).split('-', 1))
            first = date(year, month, 1)
        except (TypeError, ValueError):
            raise ValueError('month must look like 2026-03.')
    else:
        today = date.today()
        first = date(today.year, today.month, 1)
    return first, date(first.year, first.month, monthrange(first.year, first.month)[1])


def _meta(filters, **extra):
    meta = OrderedDict()
    for key in ('course_name', 'class_name', 'division_name', 'subject_name', 'department_name', 'faculty_name'):
        if filters.get(key):
            meta[key.replace('_name', '')] = filters[key]
    start, end = _dates(filters)
    if start or end:
        meta['period'] = f'{start or "start"} to {end or "today"}'
    meta.update({key: value for key, value in extra.items() if value not in (None, '')})
    return meta


# 1. Defaulter list

def defaulter_rows(cursor, filters):
    """Students below the threshold, lowest first; students with nothing countable are not defaulters."""
    chosen = policy(filters.get('threshold'))
    start, end = _dates(filters)
    reports = cohort_reports(cursor, policy_=chosen, date_from=start, date_to=end, **_cohort(filters))
    below = [
        report for report in reports
        if report.overall.percentage is not None and report.overall.percentage < chosen.threshold
    ]
    below.sort(key=lambda report: (report.overall.percentage, str(report.student.get('roll_number') or ''), report.student_id))
    rows = []
    for report in below:
        student, overall = report.student, report.overall
        rows.append({
            'roll_number': student.get('roll_number'),
            'full_name': student.get('name'),
            'course_name': student.get('course_name'),
            'class_name': student.get('class_name'),
            'division_name': student.get('division_name'),
            'held': overall.held, 'countable': overall.countable, 'attended': overall.attended,
            'absent': overall.absent, 'not_marked': overall.not_marked,
            'attendance_percentage': percent_value(overall.percentage),
            'shortfall_percent': float(chosen.threshold - overall.percentage),
            'classes_needed': report.summary.classes_needed,
        })
    meta = _meta(filters, threshold=f'{chosen.threshold}%', students_in_cohort=len(reports), defaulters=len(rows))
    return rows, list(DEFAULTER_FIELDS), {'shortfall_percent': 'Shortfall %'}, meta


# 2. Subject-wise attendance

def subject_rows(cursor, filters):
    """One row per subject of the cohort: pooled figures over every student in its roster, and how many are below the threshold."""
    chosen = policy(filters.get('threshold'))
    start, end = _dates(filters)
    reports = cohort_reports(cursor, policy_=chosen, date_from=start, date_to=end, **_cohort(filters))
    wanted = _int(filters.get('subject_id'))
    groups = OrderedDict()
    for report in reports:
        for subject_id, figures in report.summary.subjects.items():
            if wanted and subject_id != wanted:
                continue
            slot = next((row for row in report.inputs.slot_rows.values() if row['subject_id'] == subject_id), {})
            key = (subject_id, report.student.get('course_name'), report.student.get('class_name'), report.student.get('division_name'))
            group = groups.setdefault(key, {
                'subject_code': slot.get('subject_code') or slot.get('course_code') or '',
                'subject_name': slot.get('subject_name') or report.subject_name(subject_id),
                'course_name': key[1], 'class_name': key[2], 'division_name': key[3],
                'figures': [], 'below': 0,
            })
            group['figures'].append(figures.figures)
            if figures.figures.percentage is not None and figures.figures.percentage < chosen.threshold:
                group['below'] += 1
    rows = []
    for group in groups.values():
        pooled = _pool(group['figures'])
        rows.append({
            'subject_code': group['subject_code'], 'subject_name': group['subject_name'],
            'course_name': group['course_name'], 'class_name': group['class_name'], 'division_name': group['division_name'],
            'students': len(group['figures']),
            'held': pooled['held'], 'countable': pooled['countable'], 'attended': pooled['attended'],
            'present': pooled['present'], 'late': pooled['late'], 'absent': pooled['absent'],
            'excused': pooled['excused'], 'not_marked': pooled['not_marked'],
            'attendance_percentage': pooled['percentage'],
            'students_below_threshold': group['below'],
        })
    rows.sort(key=lambda row: (row['course_name'] or '', row['class_name'] or '', row['division_name'] or '', row['subject_name'] or ''))
    meta = _meta(filters, threshold=f'{chosen.threshold}%', students=len(reports))
    return rows, list(SUBJECT_FIELDS), {}, meta


def _pool(figure_list):
    counts = {'held': 0, 'countable': 0, 'attended': 0, 'present': 0, 'late': 0, 'absent': 0, 'excused': 0, 'not_marked': 0}
    for figures in figure_list:
        for key in counts:
            counts[key] += getattr(figures, key)
    counts['percentage'] = round(counts['attended'] * 100.0 / counts['countable'], 2) if counts['countable'] else None
    return counts


# 3. Monthly attendance register

def register_rows(cursor, filters):
    """Student x lecture-date matrix for one month (one subject, or every subject of the cohort), with totals.

    Cells: P present, L late, A absent, E excused, NM not marked, - no
    mark recorded, blank when the student had no lecture that day.
    """
    first, last = _month_bounds(filters.get('month'))
    subject_id = _int(filters.get('subject_id'))
    reports = cohort_reports(cursor, date_from=first.isoformat(), date_to=last.isoformat(), **_cohort(filters))
    dates = sorted({
        session['session_date'] for report in reports for session, _slot, _outcome, _mark in report.outcomes(subject_id)
    })
    columns = [f'd{day.day:02d}' for day in dates]
    labels = {column: day.strftime('%d %a') for column, day in zip(columns, dates)}
    rows = []
    for report in reports:
        cells = {}
        for session, _slot, outcome, _mark in report.outcomes(subject_id):
            column = f"d{session['session_date'].day:02d}"
            code = _OUTCOME_CODES.get(outcome, outcome[:2].upper())
            cells[column] = code if column not in cells else f'{cells[column]}/{code}'
        figures = report.summary.subjects[subject_id].figures if subject_id and subject_id in report.summary.subjects else report.overall
        if subject_id and subject_id not in report.summary.subjects:
            figures = None
        row = {
            'roll_number': report.student.get('roll_number'), 'full_name': report.student.get('name'),
            'held': figures.held if figures else 0, 'attended': figures.attended if figures else 0,
            'attendance_percentage': percent_value(figures.percentage) if figures else None,
        }
        row.update(cells)
        rows.append(row)
    fieldnames = ['roll_number', 'full_name', *columns, 'held', 'attended', 'attendance_percentage']
    subject_name = ''
    if subject_id:
        for report in reports:
            subject_name = report.subject_name(subject_id)
            if subject_name:
                break
    meta = _meta(filters, month=first.strftime('%B %Y'), subject=subject_name or filters.get('subject_name'),
                 lecture_days=len(dates), legend='P present, L late, A absent, E excused, NM not marked')
    return rows, fieldnames, labels, meta


# 4. Faculty workload

def workload_rows(cursor, filters):
    """Per faculty member: weekly scheduled slots and hours, and in the period the lectures scheduled, held, cancelled, not marked, and taken as proxy."""
    start, end = _dates(filters)
    department_id = _int(filters.get('department_id'))
    faculty_id = _int(filters.get('faculty_id'))
    clauses, params = ['1 = 1'], []
    if department_id:
        clauses.append('f.department_id = %s')
        params.append(department_id)
    if faculty_id:
        clauses.append('(f.user_id = %s OR f.id = %s)')
        params.extend([faculty_id, faculty_id])
    where = ' AND '.join(clauses)
    cursor.execute(
        f"""
        SELECT f.user_id, f.name AS faculty_name, f.employee_id, d.name AS department_name,
               COUNT(t.id) AS weekly_slots,
               COALESCE(SUM(TIME_TO_SEC(TIMEDIFF(t.end_time, t.start_time))), 0) / 3600 AS weekly_hours
        FROM faculty f
        LEFT JOIN departments d ON d.id = f.department_id
        LEFT JOIN timetable t ON t.faculty_id = f.user_id AND COALESCE(t.is_active, 1) = 1
        WHERE {where} AND COALESCE(f.is_active, 1) = 1
        GROUP BY f.user_id, f.name, f.employee_id, d.name
        ORDER BY d.name, f.name
        """,
        tuple(params),
    )
    faculty = OrderedDict((row['user_id'], row) for row in cursor.fetchall())
    if not faculty:
        return [], list(WORKLOAD_FIELDS), {}, _meta(filters)

    period_clauses, period_params = [], []
    if start:
        period_clauses.append('ls.session_date >= %s')
        period_params.append(start)
    if end:
        period_clauses.append('ls.session_date <= %s')
        period_params.append(end)
    period_where = (' AND ' + ' AND '.join(period_clauses)) if period_clauses else ''
    placeholders = ','.join(['%s'] * len(faculty))
    cursor.execute(
        f"""
        SELECT t.faculty_id AS owner, ls.taught_by, ls.status, COUNT(*) AS n
        FROM lecture_sessions ls
        JOIN timetable t ON t.id = ls.timetable_id
        WHERE (t.faculty_id IN ({placeholders}) OR ls.taught_by IN ({placeholders})){period_where}
        GROUP BY t.faculty_id, ls.taught_by, ls.status
        """,
        tuple(list(faculty) * 2 + period_params),
    )
    tallies = {user_id: {'scheduled': 0, 'held': 0, 'cancelled': 0, 'not_marked': 0, 'as_proxy': 0} for user_id in faculty}
    for row in cursor.fetchall():
        owner, taught_by, status, n = row['owner'], row['taught_by'], row['status'], int(row['n'])
        if owner in tallies:
            tallies[owner]['scheduled'] += n
            tallies[owner][status] = tallies[owner].get(status, 0) + n
        if taught_by in tallies and taught_by != owner and status == 'held':
            tallies[taught_by]['as_proxy'] += n
    # Workload norms (capability `workload_norms`): designation, norm and an under/ok/over flag per teacher.
    from services import workload

    norms = {row['faculty_id']: row for row in workload.assess(cursor, faculty_ids=list(faculty))}
    fieldnames = list(WORKLOAD_FIELDS)
    labels = {'held_percent': 'Held %', 'as_proxy': 'Taken as proxy'}
    if norms:
        fieldnames[3:3] = ['designation']
        fieldnames[6:6] = ['norm_min', 'norm_max', 'workload_flag']
        labels.update({'norm_min': 'Norm min (h)', 'norm_max': 'Norm max (h)', 'workload_flag': 'Workload'})
    rows = []
    for user_id, info in faculty.items():
        tally = tallies[user_id]
        countable = tally['scheduled'] - tally['cancelled']
        row = {
            'employee_id': info.get('employee_id'), 'faculty_name': info.get('faculty_name'),
            'department_name': info.get('department_name'),
            'weekly_slots': int(info.get('weekly_slots') or 0), 'weekly_hours': round(float(info.get('weekly_hours') or 0), 2),
            'scheduled': tally['scheduled'], 'held': tally['held'], 'cancelled': tally['cancelled'],
            'not_marked': tally['not_marked'], 'as_proxy': tally['as_proxy'],
            'held_percent': round(tally['held'] * 100.0 / countable, 2) if countable else None,
        }
        if norms:
            norm = norms.get(user_id) or {}
            row.update({
                'designation': norm.get('designation') or '', 'norm_min': norm.get('min'), 'norm_max': norm.get('max'),
                'workload_flag': norm.get('status') or 'no_norm',
            })
        rows.append(row)
    flagged = sum(1 for row in rows if row.get('workload_flag') in ('under', 'over'))
    meta = _meta(filters, faculty_members=len(rows), **({'outside_norm': flagged} if norms else {}))
    return rows, fieldnames, labels, meta


def coverage_rows(cursor, filters):
    """Planned versus delivered hours per unit. Empty when capability `syllabus` is off."""
    from services.syllabus import report

    return report(cursor, filters)


def attainment_rows(cursor, filters):
    """CO and PO attainment. Empty when capability `assessments` is off."""
    from services.assessment import report

    return report(cursor, filters)


BUILDERS = {
    'defaulters': defaulter_rows,
    'subject-wise': subject_rows,
    'monthly-register': register_rows,
    'faculty-workload': workload_rows,
    'syllabus-coverage': coverage_rows,
    'co-attainment': attainment_rows,
}


def build(cursor, report_type, filters):
    """(rows, fieldnames, labels, meta) for one accreditation report type."""
    builder = BUILDERS.get(report_type)
    if builder is None:
        raise ValueError('unknown accreditation report')
    return builder(cursor, filters or {})


__all__ = ['ACCREDITATION_TYPES', 'BUILDERS', 'build', 'pooled_figures', 'threshold_setting']
