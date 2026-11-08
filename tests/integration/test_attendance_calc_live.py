"""The golden scenarios (docs/DESIGN_ATTENDANCE_CALCULATION.md 5.4) through the real loader and the JSON API.

Cohort FY A, Mon 2 Mar to Fri 20 Mar 2026. Physics Mon and Thu; Lab (Practical)
Wed; German (elective) Tue; EVS (no division) Fri. Thu 12 Mar is a holiday (no
session row). Asha (A), Ben (A, chose German), Chen (A, enrolled 9 Mar), Dev
(B). The numbers asserted here are the ones tests/unit/test_attendance_calc.py
derives by hand.
"""

import csv
import io
from datetime import date, datetime, time

import pytest

from attendance_calc import Slot, Student, in_roster
from data_access.teacher_attendance import fetch_lecture_roster
from tests.http_helpers import api, login


def d(day, month=3):
    return date(2026, month, day)


@pytest.fixture
def cohort(factory):
    setup = factory.academic()
    teacher = setup['teacher']
    n = setup['timetable_id']
    division_b = factory.insert('divisions', name=f'B{n}')

    def subject(name, **extra):
        values = dict(
            name=f'{name} {n}', course_code=f'{name[:3].upper()}{n}', course_id=setup['course_id'], class_id=setup['class_id'],
            credits=3, theory_credits=3, practical_credits=0, marks=100, theory_marks=100, practical_marks=0,
        )
        values.update(extra)
        return factory.insert('subjects', **values)

    physics = setup['subject_id']
    lab = subject('Lab', theory_practical='Practical', theory_credits=0, practical_credits=3, theory_marks=0, practical_marks=100)
    german = subject('German', is_elective=1, course_type='Elective')
    evs = subject('EVS')

    def slot(subject_id, day, division=setup['division_id'], start=time(9, 0), end=time(10, 0)):
        return factory.insert(
            'timetable', course_id=setup['course_id'], class_id=setup['class_id'], division_id=division,
            day_of_week=day, start_time=start, end_time=end, subject_id=subject_id,
            faculty_id=teacher['faculty_id'], room_id=setup['room_id'],
        )

    slots = {
        'physics_mon': setup['timetable_id'],
        'physics_thu': slot(physics, 'Thursday'),
        'lab_wed': slot(lab, 'Wednesday'),
        'german_tue': slot(german, 'Tuesday'),
        'evs_fri': slot(evs, 'Friday', division=None),
    }

    def student(division=setup['division_id'], enrolled=d(1)):
        user = factory.user('Student', setup=setup)
        factory.execute('UPDATE students SET division_id = %s, created_at = %s WHERE id = %s', (division, datetime.combine(enrolled, time(8, 0)), user['student_id']))
        return user

    asha = student()
    ben = student()
    chen = student(enrolled=d(9))
    dev = student(division=division_b)
    year = factory.insert('academic_years', name=f'Y{n}', start_date=d(1, 1), end_date=d(31, 12))
    semester = factory.insert(
        'semesters', academic_year_id=year, semester_number=2, semester_name='Semester II',
        start_date=d(1), end_date=d(31), class_id=setup['class_id'],
    )
    factory.insert('student_subject_selections', student_id=ben['student_id'], subject_id=german, semester_id=semester, academic_year_id=year)

    sessions = {}

    def session(key, when, status='held'):
        sessions[(key, when)] = factory.insert(
            'lecture_sessions', timetable_id=slots[key], session_date=when, status=status,
            taught_by=teacher['id'], marked_by=teacher['faculty_id'] if status == 'held' else None, source='backfill',
        )

    for when in (d(2), d(9), d(16)):
        session('physics_mon', when)
    session('physics_thu', d(5))
    session('physics_thu', d(19), 'cancelled')
    for when in (d(4), d(11), d(18)):
        session('lab_wed', when)
    session('german_tue', d(3))
    session('german_tue', d(10))
    session('german_tue', d(17), 'not_marked')
    for when in (d(6), d(13), d(20)):
        session('evs_fri', when)

    def mark(user, key, when, status):
        factory.insert(
            'attendance', student_id=user['student_id'], timetable_id=slots[key], session_id=sessions[(key, when)],
            attendance_date=when, status=status, marked_by=teacher['faculty_id'],
        )

    for when, status in ((d(2), 'Present'), (d(9), 'Present'), (d(16), 'Present')):
        mark(asha, 'physics_mon', when, status)
    mark(asha, 'physics_thu', d(5), 'Absent')
    for when, status in ((d(4), 'Present'), (d(11), 'Present'), (d(18), 'Absent')):
        mark(asha, 'lab_wed', when, status)
    for when, status in ((d(6), 'Present'), (d(13), 'Present'), (d(20), 'Absent')):
        mark(asha, 'evs_fri', when, status)
    mark(ben, 'german_tue', d(3), 'Present')
    mark(ben, 'german_tue', d(10), 'Late')
    mark(chen, 'physics_mon', d(9), 'Present')
    mark(chen, 'physics_mon', d(16), 'Absent')
    for when in (d(6), d(13), d(20)):
        mark(dev, 'evs_fri', when, 'Present')

    return {
        'setup': setup, 'teacher': teacher, 'slots': slots, 'sessions': sessions, 'division_b': division_b,
        'year': year, 'semester': semester,
        'subjects': {'physics': physics, 'lab': lab, 'german': german, 'evs': evs},
        'asha': asha, 'ben': ben, 'chen': chen, 'dev': dev,
        'mark': mark, 'session': session,
    }


def payload(client, path):
    response = api(client, 'GET', path)
    assert response.status_code == 200, response.get_json()
    return response.get_json()['data']


def my_attendance(client, user):
    login(client, user)
    return payload(client, '/api/portal/student/attendance')


def by_name(payload, prefix):
    [row] = [row for row in payload['subjects'] if row['subject'].startswith(prefix)]
    return row


# Student screens

def test_asha_sees_held_lectures_and_pooled_totals(client, cohort):
    data = my_attendance(client, cohort['asha'])
    physics = by_name(data, 'Physics')
    assert (physics['held'], physics['countable'], physics['attended'], physics['percentage']) == (4, 4, 3, 75.0)
    assert (physics['present'], physics['absent'], physics['late']) == (3, 1, 0)
    assert by_name(data, 'Lab')['percentage'] == 66.67
    assert by_name(data, 'EVS')['percentage'] == 66.67
    assert not [row for row in data['subjects'] if row['subject'].startswith('German')]
    assert data['components']['Theory']['percentage'] == 71.43
    assert data['components']['Practical']['percentage'] == 66.67
    assert (data['countable'], data['attended'], data['percentage']) == (10, 7, 70.0)
    assert data['scheduled'] == 10
    assert (data['classes_needed'], data['classes_that_can_be_missed'], data['threshold']) == (2, 0, 75.0)
    assert isinstance(data['recent'], list)


def test_ben_counts_the_elective_and_sees_physics_without_a_figure(client, cohort):
    data = my_attendance(client, cohort['ben'])
    german = by_name(data, 'German')
    assert (german['held'], german['countable'], german['attended'], german['late'], german['not_marked']) == (2, 2, 2, 1, 1)
    assert german['percentage'] == 100.0
    physics = by_name(data, 'Physics')
    assert (physics['held'], physics['unrecorded'], physics['countable']) == (4, 4, 0)
    assert physics['percentage'] is None


def test_chen_is_counted_from_enrolment(client, cohort):
    data = my_attendance(client, cohort['chen'])
    physics = by_name(data, 'Physics')
    assert (physics['countable'], physics['attended'], physics['percentage']) == (2, 1, 50.0)
    assert data['classes_needed'] == 2


def test_whole_class_lecture_is_in_both_divisions(client, cohort):
    dev = my_attendance(client, cohort['dev'])
    assert [row['subject'][:3] for row in dev['subjects']] == ['EVS']
    assert by_name(dev, 'EVS')['percentage'] == 100.0
    asha = my_attendance(client, cohort['asha'])
    assert by_name(asha, 'EVS')['countable'] == 3


def test_subject_detail_lists_every_session_and_the_month(client, cohort):
    login(client, cohort['asha'])
    data = payload(client, f"/api/portal/student/attendance/{cohort['subjects']['physics']}")
    assert data['percentage'] == 75.0 and data['held'] == 4
    assert [(row['date'], row['status']) for row in data['records']] == [
        ('2026-03-16', 'Present'), ('2026-03-09', 'Present'), ('2026-03-05', 'Absent'), ('2026-03-02', 'Present'),
    ]
    assert data['records'][0]['marked_by'].startswith('Teacher')
    [month] = data['months']
    assert (month['month'], month['countable'], month['attended'], month['percentage']) == ('2026-03', 4, 3, 75.0)
    assert api(client, 'GET', f"/api/portal/student/attendance/{cohort['subjects']['german']}").status_code == 404


def test_student_home_uses_the_same_figures_and_the_roster_rule(client, cohort):
    login(client, cohort['asha'])
    data = payload(client, '/api/portal/student')
    assert data['attendance'] == {
        'total_lectures': 10, 'total_present': 7, 'total_absent': 3, 'excused': 0, 'not_marked': 0,
        'percentage': 70.0, 'classes_needed': 2, 'threshold': 75.0,
    }
    subjects = {row['subject'][:3] for row in data['sessions']}
    assert 'EVS' in subjects and 'Ger' not in subjects and 'Phy' in subjects
    ben = client.application.test_client()
    login(ben, cohort['ben'])
    assert 'Ger' in {row['subject'][:3] for row in payload(ben, '/api/portal/student')['sessions']}


def test_student_with_nothing_countable_shows_no_percentage(client, factory):
    fresh = factory.user('Student')
    login(client, fresh)
    data = payload(client, '/api/portal/student/attendance')
    assert data['percentage'] is None and data['subjects'] == [] and data['classes_needed'] is None
    home = payload(client, '/api/portal/student')
    assert home['attendance']['percentage'] is None and home['attendance']['total_lectures'] == 0


def test_portal_attendance_view_agrees(client, cohort):
    login(client, cohort['asha'])
    data = payload(client, '/api/portal/attendance')
    assert data['overall']['percentage'] == 70.0 and data['classes_needed'] == 2
    assert {row['subject'][:3]: row['percentage'] for row in data['subjects']} == {'Phy': 75.0, 'Lab': 66.67, 'EVS': 66.67}


# Semester scoping and cancelled sessions

def test_slot_with_a_semester_counts_that_semesters_dates_only(client, factory, cohort):
    factory.execute('UPDATE timetable SET semester_id = %s WHERE id = %s', (cohort['semester'], cohort['slots']['physics_thu']))
    cohort['session']('physics_thu', d(2, 4))
    cohort['mark'](cohort['asha'], 'physics_thu', d(2, 4), 'Present')
    data = my_attendance(client, cohort['asha'])
    assert by_name(data, 'Physics')['held'] == 4   # 2 Apr is outside Semester II
    factory.execute('UPDATE timetable SET semester_id = NULL WHERE id = %s', (cohort['slots']['physics_thu'],))
    data = my_attendance(client, cohort['asha'])
    assert (by_name(data, 'Physics')['held'], by_name(data, 'Physics')['percentage']) == (5, 80.0)


def test_cancelled_session_is_in_no_count(cohort, client):
    data = my_attendance(client, cohort['asha'])
    assert by_name(data, 'Physics')['held'] == 4   # 19 Mar cancelled


# Admin: defaulters, threshold, export

def test_overview_lists_defaulters_from_the_module(client, factory, cohort):
    admin = factory.user('Admin')
    login(client, admin)
    data = payload(client, '/api/attendance/overview')
    assert data['threshold'] == 75.0
    names = {cohort['asha']['student_id']: 'asha', cohort['chen']['student_id']: 'chen', cohort['ben']['student_id']: 'ben', cohort['dev']['student_id']: 'dev'}
    listed = [(names.get(row['student_id']), row['percentage'], row['classes_needed']) for row in data['defaulters'] if row['student_id'] in names]
    assert listed == [('chen', 50.0, 2), ('asha', 70.0, 2)]
    assert data['defaulter_count'] >= 2
    assert data['not_marked_count'] >= 1
    lower = payload(client, '/api/attendance/overview?threshold=60')
    assert lower['threshold'] == 60.0
    listed = [names.get(row['student_id']) for row in lower['defaulters'] if row['student_id'] in names]
    assert listed == ['chen']
    assert api(client, 'GET', '/api/attendance/overview?threshold=0').status_code == 400
    assert api(client, 'GET', '/api/attendance/overview?threshold=abc').status_code == 400


def test_defaulter_export_works_again(client, factory, cohort):
    admin = factory.user('Admin')
    login(client, admin)
    response = client.get('/admin/attendance/export/defaulters')
    assert response.status_code == 200 and response.headers['Content-Type'].startswith('text/csv')
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    assert rows[0][:5] == ['Roll Number', 'Name', 'Course', 'Class', 'Division']
    assert 'Percentage' in rows[0] and 'Classes Needed' in rows[0]
    chen = [row for row in rows[1:] if row[0] == cohort['chen']['username'].split('_')[-1]]
    assert len(chen) == 1
    percentage = rows[0].index('Percentage')
    assert chen[0][percentage] == '50.00%' and chen[0][rows[0].index('Classes Needed')] == '2'
    assert client.get('/admin/attendance/export/defaulters?threshold=101').status_code == 400


def test_defaulters_need_the_permission(client, factory):
    login(client, factory.user('Teacher'))
    assert api(client, 'GET', '/api/attendance/overview').status_code == 403


# Admin: period statistics, charts, overview export, report dataset (Phase 3)

class MarchDay(date):
    """A date whose today() is Fri 20 Mar 2026, the cohort's last lecture day."""

    @classmethod
    def today(cls):
        return d(20)


def cohort_names(factory, setup):
    def name(table, row_id):
        return factory.query(f'SELECT name FROM {table} WHERE id = %s', (row_id,))[0]['name']
    return name('courses', setup['course_id']), name('classes', setup['class_id']), name('divisions', setup['division_id'])


def test_period_statistics_pool_the_cohort(db, cohort):
    from services.attendance_calc import period_statistics

    setup = cohort['setup']
    cursor = db.cursor(dictionary=True)
    try:
        stats = period_statistics(cursor, d(1), d(31), course_id=setup['course_id'], class_id=setup['class_id'])
    finally:
        cursor.close()
    # Asha 10/10/7, Ben 12 held 2/2 (+1 not marked, 10 unrecorded), Chen 6 held 2/1 (4 unrecorded), Dev 3/3/3
    assert (stats['students'], stats['lectures'], stats['held'], stats['countable'], stats['attended']) == (4, 13, 31, 17, 13)
    assert (stats['present'], stats['late'], stats['absent'], stats['not_marked'], stats['unrecorded']) == (12, 1, 4, 1, 14)
    assert stats['percentage'] == 76.47


def test_overview_carries_the_period_figures(client, factory, cohort):
    login(client, factory.user('Admin'))
    data = payload(client, '/api/attendance/overview')
    assert data['period_days'] == 30
    for key in ('total_students', 'total_lectures', 'total_records', 'total_present', 'total_late', 'total_absent', 'total_excused', 'total_not_marked'):
        assert isinstance(data[key], int), key
    assert data['percentage'] is None or isinstance(data['percentage'], float)


def test_charts_come_from_the_module(client, factory, cohort, monkeypatch):
    monkeypatch.setattr('services.attendance_admin.exports.date', MarchDay)
    login(client, factory.user('Admin'))
    trend = client.get('/admin/attendance/charts/data?type=trend').get_json()
    by_label = {series['label']: dict(zip(trend['labels'], series['data'])) for series in trend['datasets']}
    assert by_label['Present']['2026-03-02'] >= 1          # Asha, Physics
    assert by_label['Late']['2026-03-10'] >= 1             # Ben, German
    assert by_label['Not marked']['2026-03-17'] >= 1       # German, nobody marked
    assert by_label['Absent']['2026-03-20'] >= 1           # Asha, EVS
    distribution = client.get('/admin/attendance/charts/data?type=distribution').get_json()
    course, class_name, _division = cohort_names(factory, cohort['setup'])
    assert dict(zip(distribution['labels'], distribution['data']))[f'{course} {class_name}'] == 76.47
    assert client.get('/admin/attendance/charts/data?type=pie').status_code == 400


def test_overview_export_lists_todays_cohorts(client, factory, cohort, monkeypatch):
    monkeypatch.setattr('services.attendance_admin.exports.date', MarchDay)
    login(client, factory.user('Admin'))
    response = client.get('/admin/attendance/export/overview')
    assert response.status_code == 200 and response.headers['Content-Type'].startswith('text/csv')
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    header = rows[0]
    assert header[:4] == ['Course', 'Class', 'Division', 'Students'] and header[-1] == 'Percentage'
    setup = cohort['setup']
    course, class_name, division_name = cohort_names(factory, setup)
    ours = {row[header.index('Division')]: row for row in rows[1:] if row[0] == course and row[1] == class_name}
    division_a = ours[division_name]
    assert (division_a[header.index('Students')], division_a[header.index('Held')], division_a[header.index('Countable')]) == ('3', '3', '1')
    assert division_a[header.index('Percentage')] == '0.00%'   # Asha absent; Ben and Chen unrecorded
    division_b = ours[f"B{setup['timetable_id']}"]
    assert division_b[header.index('Percentage')] == '100.00%'  # Dev present


def test_report_dataset_lists_the_whole_cohort(db, cohort):
    from services.reports_admin.dataset import ATTENDANCE_FIELDS, _build_report_export_dataset

    setup = cohort['setup']
    cursor = db.cursor(dictionary=True)
    try:
        rows, fieldnames = _build_report_export_dataset(cursor, 'attendance', {
            'start_date': '2026-03-01', 'end_date': '2026-03-31',
            'course_id': str(setup['course_id']), 'class_id': str(setup['class_id']), 'division_id': '',
        })
        with pytest.raises(ValueError):
            _build_report_export_dataset(cursor, 'attendance', {'course_id': 'abc'})
    finally:
        cursor.close()
    assert fieldnames == ATTENDANCE_FIELDS
    by_id = {row['student_id']: row for row in rows}
    asha = by_id[cohort['asha']['student_id']]
    assert (asha['held'], asha['total_classes'], asha['present'], asha['absent'], asha['attendance_percentage'], asha['classes_needed']) == (10, 10, 7, 3, 70.0, 2)
    ben = by_id[cohort['ben']['student_id']]
    assert (ben['total_classes'], ben['late'], ben['not_marked'], ben['attendance_percentage']) == (2, 1, 1, 100.0)
    assert by_id[cohort['dev']['student_id']]['attendance_percentage'] == 100.0


# Teacher: session-based history with roster figures (Phase 3)

def test_history_lists_every_recorded_lecture_and_the_roster(client, cohort):
    login(client, cohort['teacher'])
    data = payload(client, f"/api/portal/attendance/history/{cohort['slots']['german_tue']}")
    by_date = {row['date']: row for row in data['history']}
    assert by_date['2026-03-17']['status'] == 'not_marked' and by_date['2026-03-17']['total'] == 0
    assert (by_date['2026-03-10']['status'], by_date['2026-03-10']['late']) == ('held', 1)
    [ben] = data['students']   # the elective's roster is Ben alone
    assert ben['student_id'] == cohort['ben']['student_id']
    assert (ben['held'], ben['countable'], ben['attended'], ben['not_marked'], ben['percentage']) == (2, 2, 2, 1, 100.0)
    assert data['threshold'] == 75.0
    physics = payload(client, f"/api/portal/attendance/history/{cohort['slots']['physics_thu']}")
    assert {row['date']: row['status'] for row in physics['history']}['2026-03-19'] == 'cancelled'
    assert {row['date']: row['cancel_reason'] for row in physics['history']}['2026-03-19'] == ''
    figures = {row['student_id']: row for row in physics['students']}
    assert figures[cohort['asha']['student_id']]['percentage'] == 75.0      # Physics pooled over both slots
    assert figures[cohort['ben']['student_id']]['percentage'] is None       # never marked: shown, with a dash
    assert cohort['dev']['student_id'] not in figures                       # division B


def test_history_takes_a_date_range(client, cohort):
    login(client, cohort['teacher'])
    data = payload(client, f"/api/portal/attendance/history/{cohort['slots']['physics_mon']}?from=2026-03-09&to=2026-03-16")
    asha = {row['student_id']: row for row in data['students']}[cohort['asha']['student_id']]
    assert (asha['held'], asha['attended']) == (2, 2)
    assert api(client, 'GET', f"/api/portal/attendance/history/{cohort['slots']['physics_mon']}?from=2026-03-16&to=2026-03-09").status_code == 400
    assert api(client, 'GET', f"/api/portal/attendance/history/{cohort['slots']['physics_mon']}?from=soon").status_code == 400


def test_history_is_only_for_the_slots_teacher(client, factory, cohort):
    login(client, factory.user('Teacher'))
    assert api(client, 'GET', f"/api/portal/attendance/history/{cohort['slots']['physics_mon']}").status_code in (403, 404)


# The SQL roster agrees with in_roster

def _slot(cohort, key, subject, division, is_elective=False):
    setup = cohort['setup']
    return Slot(cohort['slots'][key], subject, setup['course_id'], setup['class_id'], division, is_elective=is_elective)


def test_fetch_lecture_roster_agrees_with_in_roster(db, cohort):
    setup = cohort['setup']
    subjects = cohort['subjects']
    cursor = db.cursor(dictionary=True)
    try:
        cases = {
            'physics_mon': _slot(cohort, 'physics_mon', subjects['physics'], setup['division_id']),
            'german_tue': _slot(cohort, 'german_tue', subjects['german'], setup['division_id'], is_elective=True),
            'evs_fri': _slot(cohort, 'evs_fri', subjects['evs'], None),
        }
        people = {
            'asha': Student(cohort['asha']['student_id'], setup['course_id'], setup['class_id'], setup['division_id']),
            'ben': Student(cohort['ben']['student_id'], setup['course_id'], setup['class_id'], setup['division_id'],
                           chosen_subjects=frozenset({(subjects['german'], cohort['semester'], cohort['year'])})),
            'dev': Student(cohort['dev']['student_id'], setup['course_id'], setup['class_id'], cohort['division_b']),
        }
        for key, slot in cases.items():
            lecture = {
                'course_id': slot.course_id, 'class_id': slot.class_id, 'division_id': slot.division_id,
                'subject_id': slot.subject_id, 'is_elective': slot.is_elective,
            }
            sql_ids = {row['id'] for row in fetch_lecture_roster(cursor, lecture)}
            for name, student in people.items():
                assert (student.id in sql_ids) == in_roster(slot, student, d(2)), (key, name)
    finally:
        cursor.close()
