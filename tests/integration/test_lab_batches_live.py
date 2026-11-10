"""Lab batches end to end: the admin API, rosters by batch and by date, the student's timetable,
manual slots with the batch clash rule, the greedy generator and the joint solver on the *_test database."""

from datetime import date, time

import pytest

from services.attendance_calc import student_report
from tests.http_helpers import api, login
from tests.integration.test_attendance_calc_live import cohort, d  # noqa: F401


def _ok(response):
    assert response.status_code == 200, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _admin(client, factory, setup):
    admin = factory.user('Admin', setup=setup)
    login(client, admin)
    return admin


# Admin API -------------------------------------------------------------------

def test_admin_creates_lists_changes_and_deletes_lab_batches(client, factory):
    setup = factory.academic()
    year = factory.insert('academic_years', name=f'LY{factory._next()}', start_date='2026-01-01', end_date='2026-12-31')
    _admin(client, factory, setup)
    body = {'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id'],
            'academic_year_id': year, 'semester_id': None, 'name': 'A1', 'capacity': 30, 'is_active': True}
    created = _ok(api(client, 'POST', '/api/lab-batches', json=body))
    assert (created['name'], created['capacity'], created['member_count'], created['slot_count']) == ('A1', 30, 0, 0)
    assert created['course_name'] and created['class_name'] and created['division_name']

    duplicate = api(client, 'POST', '/api/lab-batches', json=body)
    assert duplicate.status_code == 400 and duplicate.get_json()['error']['code'] == 'lab_batch_exists'
    assert api(client, 'POST', '/api/lab-batches', json={**body, 'name': ''}).get_json()['error']['code'] == 'lab_batch_name_invalid'
    assert api(client, 'POST', '/api/lab-batches', json={**body, 'name': 'A2', 'capacity': 900}).get_json()['error']['code'] == 'lab_batch_capacity_invalid'
    assert api(client, 'POST', '/api/lab-batches', json={**body, 'name': 'A2', 'academic_year_id': 999999}).get_json()['error']['code'] == 'lab_batch_year_invalid'

    listed = _ok(api(client, 'GET', f"/api/lab-batches?course_id={setup['course_id']}&class_id={setup['class_id']}"))
    assert [g['name'] for g in listed['groups']] == ['A1']
    assert listed['permissions'] == {'add': True, 'change': True, 'delete': True}
    assert {'courses', 'classes', 'divisions', 'years', 'semesters'} <= set(listed)

    changed = _ok(api(client, 'PUT', f"/api/lab-batches/{created['id']}", json={'name': 'Batch 1', 'capacity': None, 'is_active': False, 'semester_id': None}))
    assert (changed['name'], changed['capacity'], changed['is_active']) == ('Batch 1', None, False)

    assert _ok(api(client, 'DELETE', f"/api/lab-batches/{created['id']}")) == {'deleted': True}
    assert api(client, 'DELETE', f"/api/lab-batches/{created['id']}").status_code == 400
    assert factory.query('SELECT id FROM lab_batch_groups WHERE id = %s', (created['id'],)) == []


def test_students_cannot_see_or_change_lab_batches(client, factory):
    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    login(client, student)
    assert api(client, 'GET', '/api/lab-batches').status_code == 403
    assert api(client, 'POST', '/api/lab-batches', json={}).status_code == 403


def test_setting_members_moves_students_between_batches_with_dates(client, factory):
    setup = factory.academic()
    groups = factory.lab_batches(setup, ('A1', 'A2'))
    s1, s2, s3 = (factory.user('Student', setup=setup) for _ in range(3))
    outsider = factory.user('Student', setup=factory.academic())
    _admin(client, factory, setup)

    first = _ok(api(client, 'PUT', f"/api/lab-batches/{groups['A1']}/members", json={'student_ids': [s1['student_id'], s2['student_id']], 'on_date': '2026-03-01'}))
    assert (first['added'], first['moved'], first['removed'], first['members']) == (2, 0, 0, 2)

    second = _ok(api(client, 'PUT', f"/api/lab-batches/{groups['A2']}/members", json={'student_ids': [s2['student_id'], s3['student_id']], 'on_date': '2026-03-11'}))
    assert (second['added'], second['moved'], second['removed'], second['members']) == (1, 1, 0, 2)
    rows = factory.query(
        'SELECT lab_batch_group_id, added_at, ended_at FROM lab_batch_members WHERE student_id = %s ORDER BY added_at', (s2['student_id'],),
    )
    assert [(r['lab_batch_group_id'], r['added_at'], r['ended_at']) for r in rows] == [
        (groups['A1'], date(2026, 3, 1), date(2026, 3, 10)),
        (groups['A2'], date(2026, 3, 11), None),
    ]

    view = _ok(api(client, 'GET', f"/api/lab-batches/{groups['A1']}/members"))
    assert [m['student_id'] for m in view['members']] == [s1['student_id']]
    assert {s['id']: s['lab_batch_group_id'] for s in view['students']} == {
        s1['student_id']: groups['A1'], s2['student_id']: groups['A2'], s3['student_id']: groups['A2'],
    }
    assert [s['name'] for s in view['siblings']] == ['A1', 'A2']

    refused = api(client, 'PUT', f"/api/lab-batches/{groups['A1']}/members", json={'student_ids': [outsider['student_id']]})
    assert refused.status_code == 400 and refused.get_json()['error']['code'] == 'lab_batch_students_outside_cohort'
    assert api(client, 'PUT', f"/api/lab-batches/{groups['A1']}/members", json={'student_ids': 'x'}).get_json()['error']['code'] == 'lab_batch_students_invalid'

    emptied = _ok(api(client, 'PUT', f"/api/lab-batches/{groups['A1']}/members", json={'student_ids': [], 'on_date': '2026-04-01'}))
    assert emptied['removed'] == 1
    [row] = factory.query('SELECT ended_at FROM lab_batch_members WHERE student_id = %s', (s1['student_id'],))
    assert row['ended_at'] == date(2026, 4, 1)


def test_capacity_is_enforced_on_members_and_split(client, factory):
    setup = factory.academic()
    groups = factory.lab_batches(setup, ('A1', 'A2'), capacity=2)
    students = [factory.user('Student', setup=setup) for _ in range(5)]
    _admin(client, factory, setup)
    too_many = api(client, 'PUT', f"/api/lab-batches/{groups['A1']}/members", json={'student_ids': [s['student_id'] for s in students[:3]]})
    assert too_many.get_json()['error']['code'] == 'lab_batch_over_capacity'
    assert api(client, 'POST', f"/api/lab-batches/{groups['A1']}/split", json={}).get_json()['error']['code'] == 'lab_batch_over_capacity'


def test_split_deals_the_division_round_robin_by_roll_number(client, factory):
    setup = factory.academic()
    groups = factory.lab_batches(setup, ('A1', 'A2', 'A3'))
    students = [factory.user('Student', setup=setup) for _ in range(7)]
    for index, student in enumerate(students):
        factory.execute('UPDATE students SET roll_number = %s WHERE id = %s', (f'{index + 1:02d}', student['student_id']))
    _admin(client, factory, setup)
    result = _ok(api(client, 'POST', f"/api/lab-batches/{groups['A1']}/split", json={'on_date': '2026-02-01'}))
    assert result['groups'] == {str(groups['A1']): 3, str(groups['A2']): 2, str(groups['A3']): 2}
    rows = factory.query(
        'SELECT m.lab_batch_group_id, s.roll_number FROM lab_batch_members m JOIN students s ON s.id = m.student_id '
        'WHERE m.ended_at IS NULL AND m.lab_batch_group_id IN (%s, %s, %s) ORDER BY s.roll_number', tuple(groups.values()),
    )
    assert [r['lab_batch_group_id'] for r in rows] == [groups['A1'], groups['A2'], groups['A3']] * 2 + [groups['A1']]

    single = factory.lab_batches(factory.academic(), ('Only',))
    assert api(client, 'POST', f"/api/lab-batches/{single['Only']}/split", json={}).get_json()['error']['code'] == 'lab_batch_needs_two_groups'


# Rosters and figures ---------------------------------------------------------

def test_a_student_who_moves_batches_keeps_the_old_batch_lectures_up_to_the_move(db, factory, cohort):  # noqa: F811
    setup = cohort['setup']
    groups = factory.lab_batches(setup, ('A1', 'A2'))
    factory.execute('UPDATE timetable SET lab_batch_group_id = %s WHERE id = %s', (groups['A1'], cohort['slots']['lab_wed']))
    a2_slot = factory.insert(
        'timetable', course_id=setup['course_id'], class_id=setup['class_id'], division_id=setup['division_id'],
        day_of_week='Wednesday', start_time=time(9), end_time=time(10), subject_id=cohort['subjects']['lab'],
        faculty_id=cohort['teacher']['faculty_id'], room_id=setup['room_id'], lab_batch_group_id=groups['A2'],
    )
    for when in (d(4), d(11), d(18)):
        factory.insert('lecture_sessions', timetable_id=a2_slot, session_date=when, status='held',
                       taught_by=cohort['teacher']['id'], marked_by=cohort['teacher']['faculty_id'], source='backfill')
    ben = cohort['ben']
    factory.enrol_in_batch(groups['A1'], ben, added_at=d(1, 1), ended_at=d(10))
    factory.enrol_in_batch(groups['A2'], ben, added_at=d(11))

    cursor = db.cursor(dictionary=True)
    try:
        report = student_report(cursor, ben['student_id'])
    finally:
        cursor.close()
    lab = [(session['session_date'], slot['id'], outcome) for session, slot, outcome, _ in report.outcomes(cohort['subjects']['lab'])]
    assert lab == [
        (d(4), cohort['slots']['lab_wed'], 'unrecorded'),
        (d(11), a2_slot, 'unrecorded'),
        (d(18), a2_slot, 'unrecorded'),
    ]
    assert report.summary.subjects[cohort['subjects']['lab']].figures.held == 3


def test_marks_keep_counting_after_a_batch_slot_is_narrowed(db, factory, cohort):  # noqa: F811
    """Asha was never put in a batch, but her saved Lab marks are evidence she was there."""
    setup = cohort['setup']
    groups = factory.lab_batches(setup, ('A1', 'A2'))
    factory.execute('UPDATE timetable SET lab_batch_group_id = %s WHERE id = %s', (groups['A1'], cohort['slots']['lab_wed']))
    cursor = db.cursor(dictionary=True)
    try:
        report = student_report(cursor, cohort['asha']['student_id'])
    finally:
        cursor.close()
    lab = report.summary.subjects[cohort['subjects']['lab']].figures
    assert (lab.held, lab.countable, lab.attended) == (3, 3, 2)


def test_student_home_lists_only_their_own_batch_slot(client, factory, cohort):  # noqa: F811
    setup = cohort['setup']
    groups = factory.lab_batches(setup, ('A1', 'A2'))
    factory.execute('UPDATE timetable SET lab_batch_group_id = %s WHERE id = %s', (groups['A1'], cohort['slots']['lab_wed']))
    factory.insert(
        'timetable', course_id=setup['course_id'], class_id=setup['class_id'], division_id=setup['division_id'],
        day_of_week='Wednesday', start_time=time(11), end_time=time(12), subject_id=cohort['subjects']['lab'],
        faculty_id=cohort['teacher']['faculty_id'], room_id=setup['room_id'], lab_batch_group_id=groups['A2'],
    )
    factory.enrol_in_batch(groups['A2'], cohort['asha'])
    login(client, cohort['asha'])
    home = _ok(api(client, 'GET', '/api/portal/student'))
    labs = [(row['day'], row['start_time']) for row in home['sessions'] if row['subject'].startswith('Lab')]
    assert labs == [('Wednesday', '11:00')]


def test_mobile_roster_and_sync_follow_the_batch(client, factory):
    setup = factory.academic()
    groups = factory.lab_batches(setup, ('A1', 'A2'))
    factory.execute('UPDATE timetable SET lab_batch_group_id = %s WHERE id = %s', (groups['A1'], setup['timetable_id']))
    inside = factory.user('Student', setup=setup)
    outside = factory.user('Student', setup=setup)
    factory.enrol_in_batch(groups['A1'], inside)
    factory.enrol_in_batch(groups['A2'], outside)
    login(client, setup['teacher'])
    response = client.get(f"/api/portal/attendance/mark/{setup['timetable_id']}")
    assert response.status_code == 200
    data = response.get_json()['data']
    assert [row['id'] for row in data['students']] == [inside['student_id']]


# Manual slots ----------------------------------------------------------------

def test_two_batches_may_share_a_time_but_the_whole_division_may_not(client, factory):
    setup = factory.academic()
    groups = factory.lab_batches(setup, ('A1', 'A2'))
    other_setup = factory.academic()
    foreign = factory.lab_batches(other_setup, ('B1',))
    second_teacher = factory.user('Teacher', setup=setup)
    _admin(client, factory, setup)
    base = {'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id'],
            'subject_id': setup['subject_id'], 'day': 'Tuesday', 'start_time': '10:00', 'end_time': '11:00'}
    first = _ok(api(client, 'POST', '/api/timetable/slots', json={**base, 'faculty_id': setup['teacher']['id'], 'lab_batch_group_id': groups['A1']}))
    second = _ok(api(client, 'POST', '/api/timetable/slots', json={**base, 'faculty_id': second_teacher['id'], 'lab_batch_group_id': groups['A2']}))
    assert first['id'] and second['id'] and first['id'] != second['id']

    same_batch = api(client, 'POST', '/api/timetable/slots', json={**base, 'faculty_id': second_teacher['id'], 'lab_batch_group_id': groups['A1']})
    assert same_batch.get_json()['error']['code'] == 'slot_batch_busy'
    whole = api(client, 'POST', '/api/timetable/slots', json={**base, 'faculty_id': second_teacher['id']})
    assert whole.get_json()['error']['code'] == 'slot_class_busy'
    busy = api(client, 'POST', '/api/timetable/slots', json={**base, 'start_time': '11:00', 'end_time': '12:00', 'faculty_id': setup['teacher']['id'], 'lab_batch_group_id': groups['A1']})
    assert busy.status_code == 200, 'the teacher is free at 11'
    clash = api(client, 'POST', '/api/timetable/slots', json={**base, 'start_time': '11:00', 'end_time': '12:00', 'faculty_id': setup['teacher']['id'], 'lab_batch_group_id': groups['A2']})
    assert clash.get_json()['error']['code'] == 'slot_faculty_busy'
    stranger = api(client, 'POST', '/api/timetable/slots', json={**base, 'start_time': '12:00', 'end_time': '13:00', 'faculty_id': second_teacher['id'], 'lab_batch_group_id': foreign['B1']})
    assert stranger.get_json()['error']['code'] == 'slot_batch_invalid'

    view = _ok(api(client, 'GET', f"/api/timetable?course={setup['course_id']}&class={setup['class_id']}&division={setup['division_id']}"))
    tuesday = [(row['start_time'], row['lab_batch']) for row in view['sessions'] if row['day'] == 'Tuesday']
    assert tuesday == [('10:00', 'A1'), ('10:00', 'A2'), ('11:00', 'A1')]
    assert [b['name'] for b in view['lab_batches']] == ['A1', 'A2']
    assert view['can_edit'] is True

    removed = _ok(api(client, 'DELETE', f"/api/timetable/slots/{second['id']}"))
    assert removed == {'outcome': 'deleted'}
    assert api(client, 'DELETE', f"/api/timetable/slots/{second['id']}").status_code == 404


def test_removing_a_slot_with_recorded_lectures_retires_it(client, factory):
    setup = factory.academic()
    factory.insert('lecture_sessions', timetable_id=setup['timetable_id'], session_date='2026-11-02', status='held',
                   taught_by=setup['teacher']['id'], marked_by=setup['teacher']['faculty_id'], source='teacher')
    _admin(client, factory, setup)
    assert _ok(api(client, 'DELETE', f"/api/timetable/slots/{setup['timetable_id']}")) == {'outcome': 'retired'}
    [row] = factory.query('SELECT is_active FROM timetable WHERE id = %s', (setup['timetable_id'],))
    assert row['is_active'] == 0


# Generators ------------------------------------------------------------------

def _practical_cohort(factory, hours=2, batches=('A1', 'A2')):
    """A division with one theory subject (2 lectures) and one practical subject (`hours` hours), two teachers, two labs."""
    setup = factory.academic()
    groups = factory.lab_batches(setup, batches)
    students = [factory.user('Student', setup=setup) for _ in range(4)]
    for index, student in enumerate(students):
        factory.enrol_in_batch(groups[batches[index % len(batches)]], student)
    n = factory._next()
    lab_subject = factory.insert(
        'subjects', name=f'Chem Lab {n}', course_code=f'CHL{n}', course_id=setup['course_id'], class_id=setup['class_id'],
        theory_practical='Practical', course_type='Core Practical', lectures_per_week=0, practical_hours_per_week=hours,
        credits=2, theory_credits=0, practical_credits=2, marks=50, theory_marks=0, practical_marks=50,
    )
    factory.execute('UPDATE subjects SET lectures_per_week = 2 WHERE id = %s', (setup['subject_id'],))
    second = factory.user('Teacher', setup=setup)
    for subject_id, teacher in ((setup['subject_id'], setup['teacher']), (lab_subject, setup['teacher']), (lab_subject, second)):
        factory.insert('faculty_allocations', faculty_id=teacher['id'], subject_id=subject_id, class_id=setup['class_id'],
                       division_id=setup['division_id'], is_primary=1)
    for label in ('L1', 'L2'):
        factory.insert('rooms', room_number=f'{label}-{n}', room_type='Laboratory', capacity=30, department_id=setup['department_id'])
    factory.execute("UPDATE rooms SET room_type = 'Classroom', capacity = 80 WHERE id = %s", (setup['room_id'],))
    factory.execute('DELETE FROM timetable WHERE id = %s', (setup['timetable_id'],))
    setup['lab_subject'] = lab_subject
    setup['groups'] = groups
    return setup


def _rows(factory, setup):
    return factory.query(
        'SELECT day_of_week, start_time, subject_id, faculty_id, lab_batch_group_id, room_id FROM timetable '
        'WHERE course_id = %s AND class_id = %s AND division_id = %s AND COALESCE(is_active, 1) = 1 ORDER BY day_of_week, start_time, lab_batch_group_id',
        (setup['course_id'], setup['class_id'], setup['division_id']),
    )


def test_greedy_generator_schedules_each_batch_and_runs_them_in_parallel(app, factory):
    from services.timetable.generator import generate_timetable_for_class

    setup = _practical_cohort(factory)
    with app.app_context():
        result = generate_timetable_for_class(
            setup['course_id'], setup['class_id'], setup['division_id'], week_start_date='2026-11-09',
            day_start='09:00', day_end='13:00', lecture_minutes=60, working_days=['Monday', 'Tuesday', 'Wednesday'],
            candidate_count=5, created_by=None,
        )
    assert result['status'] == 'success', result.get('message')
    rows = _rows(factory, setup)
    practicals = [r for r in rows if r['subject_id'] == setup['lab_subject']]
    assert len(practicals) == 4, 'two hours times two batches'
    assert {r['lab_batch_group_id'] for r in practicals} == set(setup['groups'].values())
    theory = [r for r in rows if r['subject_id'] == setup['subject_id']]
    assert len(theory) == 2 and all(r['lab_batch_group_id'] is None for r in theory)
    parallel = {}
    for r in practicals:
        parallel.setdefault((r['day_of_week'], str(r['start_time'])), set()).add(r['lab_batch_group_id'])
    assert any(len(batches) == 2 for batches in parallel.values()), 'two free teachers and two labs allow parallel batches'
    for key, batches in parallel.items():
        if len(batches) == 2:
            pair = [r for r in practicals if (r['day_of_week'], str(r['start_time'])) == key]
            assert len({r['faculty_id'] for r in pair}) == 2 and len({r['room_id'] for r in pair}) == 2
    theory_cells = {(r['day_of_week'], str(r['start_time'])) for r in theory}
    assert not theory_cells & set(parallel), 'a whole-division hour never shares a slot with a batch'


def test_joint_solver_places_two_divisions_sharing_a_teacher_without_a_clash(app, factory):
    pytest.importorskip('ortools')
    from services.timetable.joint_solver import cohort_key, solve_targets

    first = _practical_cohort(factory, hours=1, batches=('A1', 'A2'))
    second = factory.academic()
    factory.execute('UPDATE subjects SET lectures_per_week = 2 WHERE id = %s', (second['subject_id'],))
    # The second division's subject is taught by the first division's teacher: a shared faculty member.
    factory.insert('faculty_allocations', faculty_id=first['teacher']['id'], subject_id=second['subject_id'],
                   class_id=second['class_id'], division_id=second['division_id'], is_primary=1)
    factory.execute('DELETE FROM timetable WHERE id = %s', (second['timetable_id'],))
    targets = [
        {'course_id': first['course_id'], 'class_id': first['class_id'], 'division_id': first['division_id'], 'label': 'first'},
        {'course_id': second['course_id'], 'class_id': second['class_id'], 'division_id': second['division_id'], 'label': 'second'},
    ]
    settings = {'week_start_date': '2026-11-09', 'day_start': '09:00', 'day_end': '12:00', 'lecture_minutes': 60,
                'working_days': ['Monday', 'Tuesday'], 'solver': 'joint'}
    from extensions import get_db_connection

    with app.app_context():
        connection = get_db_connection()
        try:
            results = solve_targets(connection, targets, settings, time_limit=10)
        finally:
            connection.close()
    for target in targets:
        result = results[cohort_key(target)]
        assert result['status'] == 'success', result.get('message')
        assert result['unassigned'] == []
        assert result['solver'] == 'joint' and 'quality_score' in result
    teacher_cells = factory.query(
        'SELECT day_of_week, start_time, COUNT(*) AS n FROM timetable WHERE faculty_id = %s AND COALESCE(is_active, 1) = 1 '
        'GROUP BY day_of_week, start_time HAVING n > 1', (first['teacher']['id'],),
    )
    assert teacher_cells == [], 'the shared teacher is never in two divisions at once'
    first_rows = _rows(factory, first)
    assert sorted(r['lab_batch_group_id'] for r in first_rows if r['subject_id'] == first['lab_subject']) == sorted(first['groups'].values())
    assert len(_rows(factory, second)) == 2


def test_joint_job_runs_through_the_queue(app, factory):
    pytest.importorskip('ortools')
    from services import timetable_jobs

    setup = factory.academic()
    factory.execute('UPDATE subjects SET lectures_per_week = 2 WHERE id = %s', (setup['subject_id'],))
    factory.insert('faculty_allocations', faculty_id=setup['teacher']['id'], subject_id=setup['subject_id'],
                   class_id=setup['class_id'], division_id=setup['division_id'], is_primary=1)
    admin = factory.user('Admin', setup=setup)
    settings = {'week_start_date': '2026-11-09', 'day_start': '09:00', 'day_end': '12:00', 'lecture_minutes': 60,
                'working_days': ['Monday', 'Tuesday'], 'solver': 'joint',
                'targets': [{'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id'], 'label': 'one'}]}
    with app.app_context():
        job_id, _attached = timetable_jobs.enqueue_job(settings, admin['id'])
        assert timetable_jobs._claim_next() == job_id
        timetable_jobs._process(job_id)
        record = timetable_jobs.load_job(job_id)
    assert record['status'] == 'completed', record
    assert record['assigned_count'] == 2 and record['failed_count'] == 0
    assert 'jointly' in (record['message'] or '')
