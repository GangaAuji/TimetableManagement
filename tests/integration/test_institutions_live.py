"""Institutions end to end on the *_test database: a tenant with one college behaves as before;
with two, each admin sees only their own catalog, shared rooms and faculty become candidates for
the other college's timetable, private ones are refused, Super Admins switch institutions, and
the institutions API manages the list."""

from tests.http_helpers import api, login, signed_in_as


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['error']['code']


def _ids(rows):
    return {row['id'] for row in rows}


def _two_colleges(factory):
    """Institution 1 (from revision 0014) with a cohort, plus a second college with its own cohort and admin."""
    college_b = factory.institution('Engineering College', code='ENGG')
    setup_a = factory.academic()
    setup_b = factory.academic(institution_id=college_b)
    admin_a = factory.user('Admin')
    factory.membership(admin_a, 1)
    admin_b = factory.user('Admin')
    factory.membership(admin_b, college_b)
    return college_b, setup_a, setup_b, admin_a, admin_b


def _slot(setup, **overrides):
    body = {
        'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id'],
        'subject_id': setup['subject_id'], 'faculty_id': setup['teacher']['faculty_id'], 'room_id': setup['room_id'],
        'day': 'Tuesday', 'start_time': '09:00', 'end_time': '10:00',
    }
    body.update(overrides)
    return body


# One institution: nothing changes ------------------------------------------------------------

def test_single_institution_tenant_shows_everything_and_no_switcher(client, factory):
    setup = factory.academic()
    other = factory.academic()
    admin = factory.user('Admin')
    login(client, admin)

    session = signed_in_as(client)
    assert (session['institution'], session['institutions'], session['organization_wide']) == (None, [], False)

    rooms = _ok(api(client, 'GET', '/api/rooms'))
    assert {setup['room_id'], other['room_id']} <= _ids(rooms['rooms'])
    assert (rooms['institutions'], rooms['institution_id']) == ([], None)
    assert all(room['owned'] for room in rooms['rooms'])
    departments = _ok(api(client, 'GET', '/api/departments'))
    assert {setup['department_id'], other['department_id']} <= _ids(departments['departments'])
    assert _ok(api(client, 'GET', f"/api/departments/{other['department_id']}"))['id'] == other['department_id']

    # Rooms and faculty save without naming an institution: they land in the only one.
    created = _ok(api(client, 'POST', '/api/rooms', json={'room_number': 'Solo-1', 'room_type': 'Classroom', 'capacity': 40, 'department_id': None}))
    [row] = factory.query('SELECT institution_id, sharing FROM rooms WHERE id = %s', (created['id'],))
    assert (row['institution_id'], row['sharing']) == (1, 'private')

    # A manual slot in another department's room: no sharing rule applies with one institution.
    _ok(api(client, 'POST', '/api/timetable/slots', json=_slot(setup, room_id=other['room_id'])))


# Two institutions: isolation ------------------------------------------------------------------

def test_admin_of_one_college_sees_only_that_college(client, factory):
    college_b, setup_a, setup_b, _, admin_b = _two_colleges(factory)
    login(client, admin_b)

    session = signed_in_as(client)
    assert session['institution']['id'] == college_b and session['institution']['code'] == 'ENGG'
    assert [row['id'] for row in session['institutions']] == [college_b]

    departments = _ok(api(client, 'GET', '/api/departments'))
    assert _ids(departments['departments']) == {setup_b['department_id']}
    assert [row['id'] for row in departments['institutions']] == [college_b]
    assert departments['institution_id'] == college_b
    assert _ids(_ok(api(client, 'GET', '/api/courses'))['courses']) == {setup_b['course_id']}
    assert _ids(_ok(api(client, 'GET', '/api/rooms'))['rooms']) == {setup_b['room_id']}
    faculty = _ok(api(client, 'GET', '/api/faculty'))
    assert _ids(faculty['faculty']) == {setup_b['teacher']['faculty_id']}
    assert [row['id'] for row in faculty['departments']] == [setup_b['department_id']]
    assert faculty['departments'][0]['institution_id'] == college_b
    assert _ids(_ok(api(client, 'GET', '/api/subjects'))['subjects']) == {setup_b['subject_id']}

    # College A's rows are not found, not forbidden: their existence is not revealed.
    assert _error(api(client, 'GET', f"/api/departments/{setup_a['department_id']}"), 400) == 'department_not_found'
    assert _error(api(client, 'GET', f"/api/rooms/{setup_a['room_id']}"), 404) == 'room_not_found'
    assert _error(api(client, 'GET', f"/api/faculty/{setup_a['teacher']['faculty_id']}"), 404) == 'faculty_not_found'
    assert _error(api(client, 'GET', f"/api/courses/{setup_a['course_id']}"), 400) == 'course_not_found'

    # Nor can college A's rows be changed, or new rows be placed in college A.
    room = {'room_number': 'X', 'room_type': 'Classroom', 'capacity': 10, 'department_id': None}
    assert _error(api(client, 'PUT', f"/api/rooms/{setup_a['room_id']}", json=room), 403) == 'room_not_owned'
    assert _error(api(client, 'POST', '/api/rooms', json={**room, 'institution_id': 1}), 400) == 'institution_invalid'
    department = {'name': 'Intruder', 'code': 'INT', 'description': '', 'head_of_department': '', 'is_active': True}
    assert _error(api(client, 'POST', '/api/departments', json={**department, 'institution_id': 1}), 400) == 'institution_invalid'
    assert _error(api(client, 'PUT', f"/api/departments/{setup_a['department_id']}", json=department), 403) == 'department_not_owned'
    assert _error(api(client, 'POST', '/api/rooms', json={**room, 'department_id': setup_a['department_id']}), 400) == 'department_invalid'

    # A new room without an institution lands in the admin's own college.
    created = _ok(api(client, 'POST', '/api/rooms', json=room))
    [row] = factory.query('SELECT institution_id FROM rooms WHERE id = %s', (created['id'],))
    assert row['institution_id'] == college_b

    # The switcher refuses institutions the admin is not a member of.
    assert _error(api(client, 'POST', '/api/session/institution', json={'institution_id': 1}), 403) == 'institution_forbidden'
    assert _error(api(client, 'POST', '/api/session/institution', json={'institution_id': None}), 400) == 'institution_required'
    assert _error(api(client, 'POST', '/api/session/institution', json={'institution_id': 999999}), 404) == 'institution_not_found'
    assert _ok(api(client, 'POST', '/api/session/institution', json={'institution_id': college_b}))['institution']['id'] == college_b


def test_teacher_signs_into_their_department_institution(client, factory):
    college_b, _, setup_b, _, _ = _two_colleges(factory)
    login(client, setup_b['teacher'])
    session = signed_in_as(client)
    assert session['institution']['id'] == college_b
    assert [row['id'] for row in session['institutions']] == [college_b]


# Sharing ---------------------------------------------------------------------------------------

def test_shared_room_and_faculty_are_candidates_and_private_ones_are_refused(client, factory):
    college_b, setup_a, setup_b, _, admin_b = _two_colleges(factory)
    shared_lab = factory.insert('rooms', room_number='Shared Lab', room_type='Laboratory', capacity=30, department_id=setup_a['department_id'])
    factory.share('room', shared_lab, college_b)
    hall = factory.insert('rooms', room_number='Hall', room_type='Auditorium', capacity=300, department_id=None, sharing='organization')
    private_room = setup_a['room_id']
    shared_teacher = setup_a['teacher']
    factory.share('faculty', shared_teacher['faculty_id'], college_b)
    private_teacher = factory.user('Teacher', setup=setup_a)
    login(client, admin_b)

    rooms = _ok(api(client, 'GET', '/api/rooms'))
    by_id = {room['id']: room for room in rooms['rooms']}
    assert set(by_id) == {setup_b['room_id'], shared_lab, hall}
    assert (by_id[shared_lab]['owned'], by_id[shared_lab]['sharing'], by_id[shared_lab]['institution_id']) == (False, 'listed', 1)
    assert (by_id[hall]['owned'], by_id[hall]['sharing']) == (False, 'organization')
    assert by_id[setup_b['room_id']]['owned'] is True
    assert _ok(api(client, 'GET', f'/api/rooms/{shared_lab}'))['owned'] is False

    faculty = _ok(api(client, 'GET', '/api/faculty'))
    members = {row['id']: row for row in faculty['faculty']}
    assert set(members) == {setup_b['teacher']['faculty_id'], shared_teacher['faculty_id']}
    assert members[shared_teacher['faculty_id']]['owned'] is False
    assert members[shared_teacher['faculty_id']]['institution_id'] == 1

    # Shared resources may be used but not changed by the borrowing college.
    room = {'room_number': 'Taken', 'room_type': 'Laboratory', 'capacity': 30, 'department_id': None}
    assert _error(api(client, 'PUT', f'/api/rooms/{shared_lab}', json=room), 403) == 'room_not_owned'
    update = {'name': 'Renamed', 'email': 'renamed@example.org', 'phone': '', 'designation': '', 'password': '',
              'department_id': setup_b['department_id'], 'is_active': True, 'sharing': 'private', 'shared_with': []}
    assert _error(api(client, 'PUT', f"/api/faculty/{shared_teacher['faculty_id']}", json=update), 403) == 'faculty_not_owned'

    # Manual slots for college B's cohort: shared room and teacher are accepted, private ones refused.
    _ok(api(client, 'POST', '/api/timetable/slots', json=_slot(setup_b, room_id=shared_lab, faculty_id=shared_teacher['faculty_id'])))
    _ok(api(client, 'POST', '/api/timetable/slots', json=_slot(setup_b, room_id=hall, start_time='10:00', end_time='11:00')))
    refused = api(client, 'POST', '/api/timetable/slots', json=_slot(setup_b, room_id=private_room, start_time='11:00', end_time='12:00'))
    assert _error(refused, 400) == 'slot_room_not_shared'
    refused = api(client, 'POST', '/api/timetable/slots', json=_slot(setup_b, faculty_id=private_teacher['faculty_id'], start_time='11:00', end_time='12:00'))
    assert _error(refused, 400) == 'slot_faculty_not_shared'
    # College A's own cohort is out of reach entirely.
    assert _error(api(client, 'POST', '/api/timetable/slots', json=_slot(setup_a, start_time='13:00', end_time='14:00')), 400) == 'timetable_selection_invalid'

    # The clash rule is unchanged: one shared lab is still booked once per slot across colleges.
    login(client, factory.user('Super Admin'))
    clash = api(client, 'POST', '/api/timetable/slots', json=_slot(setup_a, room_id=shared_lab, faculty_id=private_teacher['faculty_id']))
    assert _error(clash, 400) == 'slot_room_busy'


def test_owner_lists_a_room_to_another_college_through_the_api(client, factory):
    college_b, setup_a, setup_b, admin_a, admin_b = _two_colleges(factory)
    login(client, admin_a)
    body = {'room_number': 'Listed Lab', 'room_type': 'Laboratory', 'capacity': 24, 'department_id': setup_a['department_id'],
            'sharing': 'listed', 'shared_with': [college_b]}
    created = _ok(api(client, 'POST', '/api/rooms', json=body))
    room = _ok(api(client, 'GET', f"/api/rooms/{created['id']}"))
    assert (room['owned'], room['sharing'], room['shared_with'], room['institution_id']) == (True, 'listed', [college_b], 1)
    assert _error(api(client, 'POST', '/api/rooms', json={**body, 'room_number': 'Bad', 'shared_with': [999999]}), 400) == 'shared_with_invalid'
    assert _error(api(client, 'POST', '/api/rooms', json={**body, 'room_number': 'Bad', 'sharing': 'everyone'}), 400) == 'sharing_invalid'

    login(client, admin_b)
    assert created['id'] in _ids(_ok(api(client, 'GET', '/api/rooms'))['rooms'])

    # Making it private again removes it from college B's candidates.
    login(client, admin_a)
    _ok(api(client, 'PUT', f"/api/rooms/{created['id']}", json={**body, 'sharing': 'private', 'shared_with': []}))
    assert factory.query('SELECT 1 FROM resource_shares WHERE resource_type = %s AND resource_id = %s', ('room', created['id'])) == []
    login(client, admin_b)
    assert created['id'] not in _ids(_ok(api(client, 'GET', '/api/rooms'))['rooms'])


# Super Admin and the institutions API -----------------------------------------------------------

def test_super_admin_sees_the_organization_and_switches_into_one_college(client, factory):
    college_b, setup_a, setup_b, _, _ = _two_colleges(factory)
    login(client, factory.user('Super Admin'))

    session = signed_in_as(client)
    assert (session['institution'], session['organization_wide']) == (None, True)
    assert _ids(session['institutions']) == {1, college_b}
    assert {setup_a['department_id'], setup_b['department_id']} <= _ids(_ok(api(client, 'GET', '/api/departments'))['departments'])
    assert {setup_a['room_id'], setup_b['room_id']} <= _ids(_ok(api(client, 'GET', '/api/rooms'))['rooms'])

    switched = _ok(api(client, 'POST', '/api/session/institution', json={'institution_id': college_b}))
    assert switched['institution']['id'] == college_b
    assert _ids(_ok(api(client, 'GET', '/api/departments'))['departments']) == {setup_b['department_id']}
    assert _ids(_ok(api(client, 'GET', '/api/rooms'))['rooms']) == {setup_b['room_id']}
    assert _error(api(client, 'GET', f"/api/departments/{setup_a['department_id']}"), 400) == 'department_not_found'

    back = _ok(api(client, 'POST', '/api/session/institution', json={'institution_id': None}))
    assert back['institution'] is None
    assert {setup_a['department_id'], setup_b['department_id']} <= _ids(_ok(api(client, 'GET', '/api/departments'))['departments'])


def test_institutions_api_manages_the_list_and_keeps_one_active(client, factory):
    college_b, setup_a, _, _, admin_b = _two_colleges(factory)
    login(client, admin_b)
    assert api(client, 'GET', '/api/institutions').status_code == 403

    login(client, factory.user('Super Admin'))
    listing = _ok(api(client, 'GET', '/api/institutions'))
    assert listing['organization']['id'] == 1 and listing['permissions'] == {'change': True}
    by_id = {row['id']: row for row in listing['institutions']}
    assert by_id[1]['code'] == 'MAIN' and by_id[college_b]['code'] == 'ENGG'
    assert by_id[1]['departments'] >= 1 and by_id[1]['rooms'] >= 1

    organization = _ok(api(client, 'PUT', '/api/institutions/organization', json={'name': 'Pillai Group', 'short_name': 'PG'}))
    assert (organization['organization']['name'], organization['organization']['short_name']) == ('Pillai Group', 'PG')

    created = _ok(api(client, 'POST', '/api/institutions', json={'name': 'School of Law', 'code': 'law', 'short_name': 'Law'}), 201)['institution']
    assert (created['code'], created['is_active'], created['departments']) == ('LAW', True, 0)
    assert _error(api(client, 'POST', '/api/institutions', json={'name': 'Again', 'code': 'LAW'}), 400) == 'institution_code_taken'
    assert _error(api(client, 'POST', '/api/institutions', json={'name': 'Bad', 'code': 'has space'}), 400) == 'institution_code_invalid'
    assert _error(api(client, 'POST', '/api/institutions', json={'name': 'Bad', 'code': 'X', 'extra': 1}), 400) == 'invalid_body'

    changed = _ok(api(client, 'PUT', f"/api/institutions/{created['id']}", json={'name': 'School of Law', 'code': 'LAW', 'is_active': False}))['institution']
    assert changed['is_active'] is False
    _ok(api(client, 'PUT', f'/api/institutions/{college_b}', json={'name': 'Engineering College', 'code': 'ENGG', 'is_active': False}))
    last = api(client, 'PUT', '/api/institutions/1', json={'name': by_id[1]['name'], 'code': 'MAIN', 'is_active': False})
    assert _error(last, 400) == 'institution_last_active'
    assert _error(api(client, 'PUT', '/api/institutions/999999', json={'name': 'Nobody', 'code': 'NOB'}), 404) == 'institution_not_found'

    # With every other college inactive the tenant is single-institution again: no switcher.
    session = signed_in_as(client)
    assert (session['institution'], session['institutions']) == (None, [])
    members = _ok(api(client, 'GET', f'/api/institutions/{college_b}/members'))['members']
    assert [member['user_id'] for member in members] == [admin_b['id']]
