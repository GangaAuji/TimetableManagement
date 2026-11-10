"""The interactive grid on the *_test database: POST /api/timetable/check reports every rule a move would break
(and the soft-rule cost of a clean one) without writing, and the teacher and room views span cohorts."""

from tests.http_helpers import api, login


def _ok(response):
    assert response.status_code == 200, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['error']['code']


def _slot(setup, **overrides):
    return {
        'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id'],
        'subject_id': setup['subject_id'], 'faculty_id': setup['teacher']['id'], 'room_id': setup['room_id'],
        'day': 'Monday', 'start_time': '09:00', 'end_time': '10:00', **overrides,
    }


def test_check_lists_every_clash_and_exclude_id_lets_a_slot_move_onto_itself(client, factory):
    setup = factory.academic()
    login(client, factory.user('Admin', setup=setup))
    before = factory.query('SELECT COUNT(*) AS n FROM timetable')[0]['n']

    # The existing Monday 9-10 lecture occupies the class, the teacher and the room.
    clash = _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup)))
    assert clash['ok'] is False and clash['faculty_id'] == setup['teacher']['id']
    assert [err['code'] for err in clash['errors']] == ['slot_class_busy', 'slot_faculty_busy', 'slot_room_busy']
    assert all(err['message'] for err in clash['errors']) and clash['rule_cost'] is None

    moved = _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup, exclude_id=setup['timetable_id'])))
    assert moved['ok'] is True and moved['errors'] == []

    # Without a teacher the allocated one is reported; with none allocated the check says so.
    nobody = _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup, faculty_id=None, day='Tuesday')))
    assert nobody['ok'] is False and [err['code'] for err in nobody['errors']] == ['slot_no_faculty']

    assert _error(api(client, 'POST', '/api/timetable/check', json=_slot(setup, day='Funday')), 400) == 'slot_invalid'
    assert _error(api(client, 'POST', '/api/timetable/check', json=_slot(setup, exclude_id='x')), 400) == 'slot_invalid'
    assert factory.query('SELECT COUNT(*) AS n FROM timetable')[0]['n'] == before, 'checks never write'


def test_check_reports_the_soft_rule_cost_of_a_clean_move(client, factory):
    setup = factory.academic()
    factory.capability('timetable_preferences', True)
    login(client, factory.user('Admin', setup=setup))

    # Physics again on Monday repeats the subject for the class that day: spread_subject costs points.
    repeat = _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup, start_time='11:00', end_time='12:00')))
    assert repeat['ok'] is True and repeat['errors'] == []
    cost = repeat['rule_cost']
    assert cost is not None and cost['after'] == cost['before'] + cost['delta'] and cost['delta'] > 0
    assert 'spread_subject' in {v['rule'] for v in cost['violations']}
    assert all({'rule', 'title', 'cost', 'faculty', 'detail'} <= set(v) for v in cost['violations'])

    # The same hour on another day costs less than the repeat.
    elsewhere = _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup, day='Tuesday')))
    assert elsewhere['ok'] is True and elsewhere['rule_cost']['delta'] < cost['delta']

    factory.capability('timetable_preferences', False)
    off = _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup, start_time='11:00', end_time='12:00')))
    assert off['ok'] is True and off['rule_cost'] is None


def test_teacher_and_room_views_span_cohorts_and_carry_the_ids_the_grid_moves(client, factory):
    first = factory.academic()
    second = factory.academic()
    # The same teacher also meets the second cohort, in the second cohort's room, on Wednesday.
    other = factory.lecture(second, first['teacher'], day='Wednesday')
    login(client, factory.user('Admin', setup=first))

    by_class = _ok(api(client, 'GET', f"/api/timetable?course={first['course_id']}&class={first['class_id']}&division={first['division_id']}"))
    assert by_class['view'] == 'class' and [row['id'] for row in by_class['sessions']] == [first['timetable_id']]
    [row] = by_class['sessions']
    assert (row['course_id'], row['class_id'], row['division_id'], row['subject_id'], row['faculty_id'], row['room_id']) == (
        first['course_id'], first['class_id'], first['division_id'], first['subject_id'], first['teacher']['id'], first['room_id'],
    )
    assert row['cohort'] and ' / ' in row['cohort']
    assert {item['id'] for item in by_class['faculty']} >= {first['teacher']['id']}
    assert {item['id'] for item in by_class['rooms']} >= {first['room_id'], second['room_id']}

    by_teacher = _ok(api(client, 'GET', f"/api/timetable?faculty={first['teacher']['id']}"))
    assert by_teacher['view'] == 'faculty'
    assert [(row['id'], row['day']) for row in by_teacher['sessions']] == [(first['timetable_id'], 'Monday'), (other, 'Wednesday')]
    assert len({row['cohort'] for row in by_teacher['sessions']}) == 2
    assert by_teacher['faculty'] and by_teacher['rooms'] and by_teacher['subjects'] == [] and by_teacher['lab_batches'] == []

    by_room = _ok(api(client, 'GET', f"/api/timetable?room={second['room_id']}"))
    assert by_room['view'] == 'room' and [row['id'] for row in by_room['sessions']] == [second['timetable_id'], other]

    empty = _ok(api(client, 'GET', '/api/timetable'))
    assert empty['view'] == 'class' and empty['sessions'] == []
    assert _error(api(client, 'GET', '/api/timetable?faculty=abc'), 400) == 'timetable_selection_invalid'


def test_students_and_teachers_without_the_permission_cannot_check_or_browse_by_teacher(client, factory):
    setup = factory.academic()
    login(client, factory.user('Student', setup=setup))
    assert api(client, 'POST', '/api/timetable/check', json=_slot(setup)).status_code == 403
    assert api(client, 'GET', f"/api/timetable?faculty={setup['teacher']['id']}").status_code == 403


def test_check_mirrors_add_slot_on_the_same_payload(client, factory):
    setup = factory.academic()
    login(client, factory.user('Admin', setup=setup))
    payload = _slot(setup, day='Thursday', start_time='10:00', end_time='11:00')
    assert _ok(api(client, 'POST', '/api/timetable/check', json=payload))['ok'] is True
    created = _ok(api(client, 'POST', '/api/timetable/slots', json=payload))
    again = _ok(api(client, 'POST', '/api/timetable/check', json=payload))
    assert again['ok'] is False and again['errors'][0]['code'] == 'slot_class_busy'
    refused = api(client, 'POST', '/api/timetable/slots', json=payload)
    assert refused.status_code == 400 and refused.get_json()['error']['code'] == again['errors'][0]['code']
    # Moving the new slot one hour later is clean; the grid does DELETE then POST.
    later = {**payload, 'start_time': '11:00', 'end_time': '12:00', 'exclude_id': created['id']}
    assert _ok(api(client, 'POST', '/api/timetable/check', json=later))['ok'] is True
    assert _ok(api(client, 'DELETE', f"/api/timetable/slots/{created['id']}")) == {'outcome': 'deleted'}
    later.pop('exclude_id')
    assert _ok(api(client, 'POST', '/api/timetable/slots', json=later))['id']
