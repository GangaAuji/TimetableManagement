"""Workload norms (J5) on the *_test database: the norms API, hard enforcement in both solvers, the soft
cost otherwise, the workload report's flags and the teacher's dashboard card. Capability off -> 404 and
no columns, no card."""

import pytest

from tests.http_helpers import api, login


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['error']['code']


def _four_hours(factory):
    """A cohort whose only subject meets four times a week with one teacher; the seeded Monday 09:00 row is removed."""
    setup = factory.academic()
    factory.execute('UPDATE subjects SET lectures_per_week = 4 WHERE id = %s', (setup['subject_id'],))
    factory.execute("UPDATE faculty SET designation = 'Professor' WHERE id = %s", (setup['teacher']['faculty_id'],))
    factory.insert('faculty_allocations', faculty_id=setup['teacher']['id'], subject_id=setup['subject_id'],
                   class_id=setup['class_id'], division_id=setup['division_id'], is_primary=1)
    factory.execute('DELETE FROM timetable WHERE id = %s', (setup['timetable_id'],))
    return setup


def _active(factory, setup):
    return factory.query(
        'SELECT day_of_week, start_time FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s AND COALESCE(is_active, 1) = 1',
        (setup['course_id'], setup['class_id'], setup['division_id']),
    )


def _norms(factory, max_hours, *, enforce='soft', min_hours=None):
    factory.capability('workload_norms', True, {'enforce': enforce})
    from services import workload
    import json

    factory.execute(
        'INSERT INTO timetable_rules (institution_id, rules_json) VALUES (1, %s) ON DUPLICATE KEY UPDATE rules_json = VALUES(rules_json)',
        (json.dumps({workload.KEY: {'default': {}, 'by_designation': {'Professor': {'min': min_hours, 'max': max_hours}}}}),),
    )


def test_norms_api_saves_per_designation_and_lists_every_teachers_status(client, factory):
    setup = factory.academic()
    factory.execute("UPDATE faculty SET designation = 'Professor' WHERE id = %s", (setup['teacher']['faculty_id'],))
    factory.capability('workload_norms', True, {'enforce': 'soft'})
    login(client, factory.user('Super Admin'))
    data = _ok(api(client, 'GET', '/api/timetable/workload-norms'))
    assert data['stored'] is False and data['enforce'] == 'soft' and 'Professor' in data['designations']
    teacher = next(item for item in data['teachers'] if item['faculty_id'] == setup['teacher']['id'])
    assert teacher['status'] == 'no_norm' and teacher['hours'] == 1.0

    saved = _ok(api(client, 'PUT', '/api/timetable/workload-norms', json={'norms': {'default': {'min': 12, 'max': 18}, 'by_designation': {'Professor': {'min': 2, 'max': 4}}}}))
    assert saved['stored'] is True and saved['norms']['by_designation'] == {'Professor': {'min': 2, 'max': 4}}
    teacher = next(item for item in saved['teachers'] if item['faculty_id'] == setup['teacher']['id'])
    assert (teacher['status'], teacher['min'], teacher['max']) == ('under', 2, 4), 'one hour against a 2-4 norm'
    assert _error(api(client, 'PUT', '/api/timetable/workload-norms', json={'norms': {'default': {'min': 9, 'max': 1}}}), 400) == 'norms_invalid'
    assert factory.query("SELECT 1 FROM user_activity_log WHERE activity_type = 'workload_norms_changed'") != []

    # The rules document in the same row is untouched by the norms, and vice versa.
    rules = _ok(api(client, 'PUT', '/api/timetable/rules', json={'rules': {'spread_subject': {'weight': 3}}}))
    assert rules['rules']['spread_subject']['weight'] == 3 and '_workload' not in rules['rules']
    again = _ok(api(client, 'GET', '/api/timetable/workload-norms'))
    assert again['norms']['by_designation'] == {'Professor': {'min': 2, 'max': 4}}


def test_capability_off_hides_norms_report_columns_and_the_card(client, factory):
    setup = factory.academic()
    factory.capability('workload_norms', False)
    login(client, factory.user('Super Admin'))
    assert _error(api(client, 'GET', '/api/timetable/workload-norms'), 404) == 'capability_off'
    api(client, 'POST', '/api/session/logout')
    login(client, setup['teacher'])
    assert _ok(api(client, 'GET', '/api/portal/teacher'))['workload'] is None
    api(client, 'POST', '/api/session/logout')
    login(client, factory.user('Student', setup=setup))
    assert api(client, 'GET', '/api/timetable/workload-norms').status_code == 403


def test_hard_norm_caps_the_greedy_generator_and_the_joint_solver(app, factory):
    pytest.importorskip('ortools')
    from extensions import get_db_connection
    from services.timetable.generator import generate_timetable_for_class
    from services.timetable.joint_solver import cohort_key, solve_targets

    setup = _four_hours(factory)
    _norms(factory, 2, enforce='hard')
    with app.app_context():
        result = generate_timetable_for_class(
            setup['course_id'], setup['class_id'], setup['division_id'], week_start_date='2026-11-09',
            day_start='09:00', day_end='12:00', lecture_minutes=60, working_days=['Monday', 'Tuesday'], candidate_count=3,
        )
    assert result['status'] in ('success', 'partial'), result.get('message')
    assert len(_active(factory, setup)) == 2, 'the professor may teach two hours a week'
    assert result['unassigned'], 'the other two hours stay open'

    factory.execute('DELETE FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s',
                    (setup['course_id'], setup['class_id'], setup['division_id']))
    targets = [{'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id'], 'label': 'one'}]
    settings = {'week_start_date': '2026-11-09', 'day_start': '09:00', 'day_end': '12:00', 'lecture_minutes': 60,
                'working_days': ['Monday', 'Tuesday'], 'solver': 'joint'}
    with app.app_context():
        connection = get_db_connection()
        try:
            results = solve_targets(connection, targets, settings, time_limit=10)
        finally:
            connection.close()
    result = results[cohort_key(targets[0])]
    assert result['status'] in ('success', 'partial'), result.get('message')
    assert len(_active(factory, setup)) == 2 and len(result['unassigned']) == 2

    # Soft: everything is placed and the two hours over the norm are reported as a workload_max cost.
    factory.execute('DELETE FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s',
                    (setup['course_id'], setup['class_id'], setup['division_id']))
    factory.capability('workload_norms', True, {'enforce': 'soft'})
    with app.app_context():
        connection = get_db_connection()
        try:
            results = solve_targets(connection, targets, settings, time_limit=10)
        finally:
            connection.close()
    result = results[cohort_key(targets[0])]
    assert result['status'] == 'success' and len(_active(factory, setup)) == 4
    over = [item for item in result['violations'] if item['rule'] == 'workload_max']
    assert len(over) == 1 and over[0]['faculty_id'] == setup['teacher']['id'] and '4 hours this week (norm 2)' in over[0]['detail']
    assert result['rule_costs']['workload_max'] == 12


def test_workload_report_flags_and_the_teacher_card(app, client, factory, db):
    from services.reports_admin import accreditation

    def build():
        cursor = db.cursor(dictionary=True)
        try:
            with app.app_context():   # the capability switch is read inside an app context
                return accreditation.build(cursor, 'faculty-workload', {'faculty_id': setup['teacher']['id']})
        finally:
            cursor.close()

    setup = factory.academic()
    factory.execute("UPDATE faculty SET designation = 'Professor' WHERE id = %s", (setup['teacher']['faculty_id'],))
    factory.capability('workload_norms', False)
    rows, fieldnames, labels, meta = build()
    assert 'workload_flag' not in fieldnames and 'workload_flag' not in rows[0] and 'outside_norm' not in meta

    _norms(factory, 4, min_hours=2)
    rows, fieldnames, labels, meta = build()
    assert fieldnames[3] == 'designation' and fieldnames[6:9] == ['norm_min', 'norm_max', 'workload_flag']
    assert rows[0]['designation'] == 'Professor' and (rows[0]['norm_min'], rows[0]['norm_max']) == (2, 4)
    assert rows[0]['workload_flag'] == 'under' and meta['outside_norm'] == 1 and labels['workload_flag'] == 'Workload'

    login(client, setup['teacher'])
    card = _ok(api(client, 'GET', '/api/portal/teacher'))['workload']
    assert card == {'hours': 1.0, 'min': 2, 'max': 4, 'status': 'under', 'designation': 'Professor'}

    # Add three more hours and the teacher is over.
    for start, end in (('10:00', '11:00'), ('11:00', '12:00'), ('12:00', '13:00')):
        factory.lecture(setup, setup['teacher'], 'Tuesday', start, end)
    card = _ok(api(client, 'GET', '/api/portal/teacher'))['workload']
    assert card['hours'] == 4.0 and card['status'] == 'ok'
    factory.lecture(setup, setup['teacher'], 'Wednesday', '09:00', '10:00')
    assert _ok(api(client, 'GET', '/api/portal/teacher'))['workload']['status'] == 'over'
