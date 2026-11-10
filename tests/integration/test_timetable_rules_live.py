"""Timetable rules and faculty preferences on the *_test database: the rules API per institution, the
preferences API for admins and the teacher's own portal, the capability switch answering 404 when off,
and both solvers honouring an avoid window and explaining what they could not honour."""

import pytest

from tests.http_helpers import api, login


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['error']['code']


def test_rules_api_reads_defaults_saves_and_scopes_by_institution(client, factory):
    admin = factory.user('Super Admin')
    login(client, admin)
    data = _ok(api(client, 'GET', '/api/timetable/rules'))
    assert data['stored'] is False and data['rules'] == data['defaults'] and data['can_change'] is True
    assert {item['name'] for item in data['registry']} == set(data['rules'])

    saved = _ok(api(client, 'PUT', '/api/timetable/rules', json={'rules': {'idle_gaps_students': {'weight': 9}, 'lunch_window': {'start': '12:30', 'end': '13:30'}}}))
    assert saved['stored'] is True and saved['rules']['idle_gaps_students']['weight'] == 9
    assert saved['rules']['lunch_window'] == {'weight': 3, 'start': '12:30', 'end': '13:30'}
    assert saved['rules']['spread_subject']['weight'] == 10, 'unspecified rules keep their defaults'
    assert factory.query('SELECT institution_id FROM timetable_rules') == [{'institution_id': 1}]
    assert _error(api(client, 'PUT', '/api/timetable/rules', json={'rules': {'spread_subject': {'weight': 99}}}), 400) == 'rules_invalid'
    assert _error(api(client, 'PUT', '/api/timetable/rules', json={'weights': {}}), 400) == 'invalid_body'
    assert factory.query("SELECT activity_type FROM user_activity_log WHERE activity_type = 'timetable_rules_changed'") != []

    # A second college keeps its own rules.
    college_b = factory.institution('Engineering College', code='ENGG')
    admin_b = factory.user('Admin')
    factory.membership(admin_b, college_b)
    factory.grant(admin_b, 'timetable_generate')
    api(client, 'POST', '/api/session/logout')
    login(client, admin_b)
    data = _ok(api(client, 'GET', '/api/timetable/rules'))
    assert data['institution_id'] == college_b and data['stored'] is False and data['rules']['idle_gaps_students']['weight'] == 4


def test_capability_off_hides_rules_and_preferences(client, factory):
    factory.capability('timetable_preferences', False)
    setup = factory.academic()
    login(client, factory.user('Super Admin'))
    assert _error(api(client, 'GET', '/api/timetable/rules'), 404) == 'capability_off'
    assert _error(api(client, 'PUT', '/api/timetable/rules', json={'rules': {}}), 404) == 'capability_off'
    assert _error(api(client, 'GET', f"/api/faculty/{setup['teacher']['faculty_id']}/preferences"), 404) == 'capability_off'
    api(client, 'POST', '/api/session/logout')
    login(client, setup['teacher'])
    assert _error(api(client, 'GET', '/api/portal/preferences'), 404) == 'capability_off'


def test_preferences_api_for_admins_and_the_teachers_own_portal(client, factory):
    setup = factory.academic()
    teacher = setup['teacher']
    windows = [
        {'day': 'Monday', 'start_time': '09:00', 'end_time': '10:00', 'kind': 'avoid', 'weight': 5, 'note': 'School run'},
        {'day': 'Friday', 'start_time': '14:00', 'end_time': '17:00', 'kind': 'preferred', 'weight': 2},
    ]
    # The teacher edits their own windows through the portal.
    login(client, teacher)
    data = _ok(api(client, 'GET', '/api/portal/preferences'))
    assert data['preferences'] == [] and data['can_change'] is True and data['faculty_id'] == teacher['faculty_id']
    saved = _ok(api(client, 'PUT', '/api/portal/preferences', json={'preferences': windows}))
    assert [item['day'] for item in saved['preferences']] == ['Monday', 'Friday']
    assert saved['preferences'][0]['note'] == 'School run' and saved['preferences'][1]['note'] == ''
    assert _error(api(client, 'PUT', '/api/portal/preferences', json={'preferences': [{'day': 'Monday', 'start_time': '10:00', 'end_time': '09:00', 'kind': 'avoid'}]}), 400) == 'preferences_invalid'
    # The Teacher role holds the availability permissions, but only for its own record.
    other = factory.user('Teacher', setup=setup)
    assert len(_ok(api(client, 'GET', f"/api/faculty/{teacher['faculty_id']}/preferences"))['preferences']) == 2
    assert _error(api(client, 'GET', f"/api/faculty/{other['faculty_id']}/preferences"), 403) == 'forbidden'
    assert _error(api(client, 'PUT', f"/api/faculty/{other['faculty_id']}/preferences", json={'preferences': []}), 403) == 'forbidden'
    api(client, 'POST', '/api/session/logout')

    # An HOD views (faculty_view_availability) but may not change; an Admin holds both and replaces the windows.
    hod = factory.user('HOD', setup=setup)
    login(client, hod)
    data = _ok(api(client, 'GET', f"/api/faculty/{teacher['faculty_id']}/preferences"))
    assert len(data['preferences']) == 2 and data['can_change'] is False
    assert _error(api(client, 'PUT', f"/api/faculty/{teacher['faculty_id']}/preferences", json={'preferences': []}), 403) == 'forbidden'
    api(client, 'POST', '/api/session/logout')
    admin = factory.user('Admin')
    login(client, admin)
    saved = _ok(api(client, 'PUT', f"/api/faculty/{teacher['faculty_id']}/preferences", json={'preferences': windows[:1]}))
    assert len(saved['preferences']) == 1 and saved['can_change'] is True
    assert factory.query('SELECT COUNT(*) AS n FROM faculty_preferences WHERE faculty_id = %s', (teacher['id'],)) == [{'n': 1}]
    assert _error(api(client, 'GET', '/api/faculty/999999/preferences'), 404) == 'faculty_not_found'
    # Students never reach it.
    api(client, 'POST', '/api/session/logout')
    login(client, factory.user('Student', setup=setup))
    assert _error(api(client, 'GET', '/api/portal/preferences'), 403) == 'forbidden'


def _two_hours(factory):
    """A cohort whose only subject meets twice a week with one teacher; the seeded Monday 09:00 row is removed."""
    setup = factory.academic()
    factory.execute('UPDATE subjects SET lectures_per_week = 2 WHERE id = %s', (setup['subject_id'],))
    factory.insert('faculty_allocations', faculty_id=setup['teacher']['id'], subject_id=setup['subject_id'],
                   class_id=setup['class_id'], division_id=setup['division_id'], is_primary=1)
    factory.execute('DELETE FROM timetable WHERE id = %s', (setup['timetable_id'],))
    return setup


def _active(factory, setup):
    return factory.query(
        'SELECT day_of_week, start_time FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s AND COALESCE(is_active, 1) = 1 '
        'ORDER BY FIELD(day_of_week, "Monday", "Tuesday"), start_time',
        (setup['course_id'], setup['class_id'], setup['division_id']),
    )


def test_joint_solver_honours_an_avoid_window_and_reports_violations(app, factory):
    pytest.importorskip('ortools')
    from services.timetable.joint_solver import cohort_key, solve_targets
    from extensions import get_db_connection

    setup = _two_hours(factory)
    # The teacher avoids Monday and Tuesday mornings strongly; with two days of three slots the solver can oblige.
    factory.execute(
        "INSERT INTO faculty_preferences (faculty_id, day_of_week, start_time, end_time, kind, weight) VALUES "
        "(%s, 1, '09:00:00', '11:00:00', 'avoid', 5), (%s, 2, '09:00:00', '11:00:00', 'avoid', 5)",
        (setup['teacher']['id'], setup['teacher']['id']),
    )
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
    assert result['status'] == 'success', result.get('message')
    assert {str(row['start_time']) for row in _active(factory, setup)} == {'11:00:00'}, 'both hours land at 11:00, outside the avoid windows'
    assert result['violations'] == [] and result['rule_cost'] >= 0

    # Make the window impossible to honour (the whole day) and the result explains the cost.
    factory.execute("UPDATE faculty_preferences SET end_time = '12:00:00' WHERE faculty_id = %s", (setup['teacher']['id'],))
    with app.app_context():
        connection = get_db_connection()
        try:
            results = solve_targets(connection, targets, settings, time_limit=10)
        finally:
            connection.close()
    result = results[cohort_key(targets[0])]
    assert result['status'] == 'success'
    assert len(result['violations']) == 2 and {item['rule'] for item in result['violations']} == {'faculty_preferences'}
    assert result['violations'][0]['faculty_id'] == setup['teacher']['id'] and 'Asked to avoid' in result['violations'][0]['detail']
    assert result['rule_costs']['faculty_preferences'] == 50


def test_greedy_generator_ranks_candidates_by_rule_cost_and_explains(app, factory):
    from services.timetable.generator import generate_timetable_for_class

    setup = _two_hours(factory)
    factory.execute(
        "INSERT INTO faculty_preferences (faculty_id, day_of_week, start_time, end_time, kind, weight) VALUES (%s, 1, '09:00:00', '12:00:00', 'avoid', 5)",
        (setup['teacher']['id'],),
    )
    with app.app_context():
        result = generate_timetable_for_class(
            setup['course_id'], setup['class_id'], setup['division_id'], week_start_date='2026-11-09',
            day_start='09:00', day_end='12:00', lecture_minutes=60, working_days=['Monday', 'Tuesday'], candidate_count=5,
        )
    assert result['status'] == 'success', result.get('message')
    assert all('rule_cost' in item for item in result['top_candidates'])
    # The greedy generator fills days in order, so its candidates may all sit on Monday; what it
    # guarantees is the explanation: one violation of 25 per hour inside the avoided window.
    monday = [row for row in _active(factory, setup) if row['day_of_week'] == 'Monday']
    avoided = [item for item in result['violations'] if item['rule'] == 'faculty_preferences']
    assert len(avoided) == len(monday) and all(item['day'] == 'Monday' for item in avoided)
    assert result['rule_costs'].get('faculty_preferences', 0) == 25 * len(monday)
    if len(monday) == 2:
        assert any(item['rule'] == 'spread_subject' for item in result['violations']), 'the same subject twice on Monday is reported too'


def test_generation_api_accepts_a_rules_override(client, factory):
    setup = factory.academic()
    admin = factory.user('Super Admin')
    login(client, admin)
    body = {'scope': 'one', 'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id'],
            'week_start_date': '2026-11-09', 'rules_override': {'idle_gaps_students': {'weight': 20}}}
    data = _ok(api(client, 'POST', '/api/timetable/generate', json=body))
    assert data['id'] > 0
    [job] = factory.query('SELECT settings_json FROM timetable_jobs WHERE id = %s', (data['id'],))
    assert '"idle_gaps_students": {"weight": 20}' in job['settings_json']
    body['rules_override'] = {'idle_gaps_students': {'weight': 999}}
    assert _error(api(client, 'POST', '/api/timetable/generate', json=body), 400) == 'invalid_body'
