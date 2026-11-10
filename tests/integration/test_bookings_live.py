"""Room bookings (Phase J4) on the *_test database: a request against a timetabled slot is refused with
free rooms offered, a HOD's request waits for the room owner's approval and notifies both sides, an
approved weekly booking blocks the manual slot check and the generator, cancel and reject close a
booking, and with the capability off every route answers 404 capability_off."""

from datetime import date, timedelta

from tests.http_helpers import api, login


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['error']


def _booking(setup, **overrides):
    return {'room_id': setup['room_id'], 'title': 'Guest lecture', 'kind': 'event', 'day_of_week': 'Monday',
            'start_time': '10:00', 'end_time': '11:00', **overrides}


def _slot(setup, **overrides):
    return {
        'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id'],
        'subject_id': setup['subject_id'], 'faculty_id': setup['teacher']['id'], 'room_id': setup['room_id'],
        'day': 'Monday', 'start_time': '10:00', 'end_time': '11:00', **overrides,
    }


def test_a_request_against_a_timetabled_slot_is_refused_with_free_rooms_of_that_type(client, factory):
    factory.capability('bookings', True)
    setup = factory.academic()
    factory.execute("UPDATE rooms SET room_type = 'Classroom' WHERE id = %s", (setup['room_id'],))
    spare = factory.insert('rooms', room_number=f"S{setup['room_id']}", room_type='Classroom', department_id=setup['department_id'])
    lab = factory.insert('rooms', room_number=f"L{setup['room_id']}", room_type='Laboratory', department_id=setup['department_id'])
    login(client, factory.user('Admin', setup=setup))

    refused = _error(api(client, 'POST', '/api/bookings', json=_booking(setup, start_time='09:00', end_time='10:00')), 400)
    assert refused['code'] == 'booking_room_busy' and 'timetabled' in refused['message']
    offered = {room['id'] for room in refused['alternatives']}
    assert spare in offered and setup['room_id'] not in offered and lab not in offered, 'free rooms of the same type only'
    assert factory.query('SELECT COUNT(*) AS n FROM bookings')[0]['n'] == 0

    free = _ok(api(client, 'GET', "/api/bookings/free-rooms?day=Monday&start_time=09:00&end_time=10:00&room_type=Classroom"))
    ids = {room['id'] for room in free['rooms']}
    assert spare in ids and setup['room_id'] not in ids and lab not in ids
    later = _ok(api(client, 'GET', "/api/bookings/free-rooms?day=Monday&start_time=10:00&end_time=11:00&room_type=Classroom"))
    assert setup['room_id'] in {room['id'] for room in later['rooms']}

    assert _error(api(client, 'POST', '/api/bookings', json=_booking(setup, booking_date='2026-11-09')), 400)['code'] == 'booking_when_invalid'
    assert _error(api(client, 'POST', '/api/bookings', json=_booking(setup, end_time='09:30')), 400)['code'] == 'booking_time_invalid'
    assert _error(api(client, 'POST', '/api/bookings', json=_booking(setup, title='')), 400)['code'] == 'booking_title_invalid'
    assert _error(api(client, 'POST', '/api/bookings', json=_booking(setup, kind='party')), 400)['code'] == 'booking_kind_invalid'
    assert _error(api(client, 'POST', '/api/bookings', json=_booking(setup, room_id=999999)), 400)['code'] == 'booking_room_invalid'


def test_a_hod_request_waits_for_approval_then_blocks_manual_slots_and_the_generator(app, client, factory):
    factory.capability('bookings', True)
    setup = factory.academic()
    hod = factory.user('HOD', setup=setup)
    admin = factory.user('Admin', setup=setup)

    login(client, hod)
    listed = _ok(api(client, 'GET', '/api/bookings'))
    assert listed['requires_approval'] is True and listed['permissions'] == {'request': True, 'approve': False}
    assert setup['room_id'] in {room['id'] for room in listed['rooms']}
    requested = _ok(api(client, 'POST', '/api/bookings', json=_booking(setup)))['booking']
    assert (requested['status'], requested['day_of_week'], requested['start_time'], requested['end_time']) == ('requested', 'Monday', '10:00', '11:00')
    assert requested['booked_by'] == hod['username'] and requested['can_cancel'] is True and requested['can_decide'] is False
    kinds = [row['kind'] for row in factory.query('SELECT kind FROM notifications WHERE kind LIKE %s ORDER BY id', ('booking%',))]
    assert kinds and set(kinds) == {'booking_request'}, 'approvers are told about the request'
    recipients = {row['recipient_user_id'] for row in factory.query("SELECT recipient_user_id FROM notifications WHERE kind = 'booking_request'")}
    assert admin['id'] in recipients and hod['id'] not in recipients

    # A requested booking blocks nothing yet.
    login(client, admin)
    assert _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup)))['ok'] is True

    # The HOD cannot decide; the owner's admin can.
    login(client, hod)
    assert api(client, 'POST', f"/api/bookings/{requested['id']}/approve").status_code == 403
    login(client, admin)
    approved = _ok(api(client, 'POST', f"/api/bookings/{requested['id']}/approve", json={'note': 'Fine.'}))['booking']
    assert approved['status'] == 'approved' and approved['decided_by'] == admin['username'] and approved['decision_note'] == 'Fine.'
    assert _error(api(client, 'POST', f"/api/bookings/{requested['id']}/approve"), 400)['code'] == 'booking_decided'
    decisions = factory.query("SELECT recipient_user_id FROM notifications WHERE kind = 'booking_decision'")
    assert [row['recipient_user_id'] for row in decisions] == [hod['id']]

    # Now the room is busy for the manual slot check and add_slot at that weekly time.
    check = _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup)))
    assert check['ok'] is False and [err['code'] for err in check['errors']] == ['slot_room_booked']
    assert 'Guest lecture' in check['errors'][0]['message']
    refused = api(client, 'POST', '/api/timetable/slots', json=_slot(setup))
    assert refused.status_code == 400 and refused.get_json()['error']['code'] == 'slot_room_booked'
    assert _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup, start_time='11:00', end_time='12:00')))['ok'] is True

    # The generator treats the booking as a busy room: nothing it writes uses that room on Monday 10-11.
    from services import timetable_jobs

    factory.execute('UPDATE subjects SET lectures_per_week = %s WHERE id = %s', (3, setup['subject_id']))
    factory.insert('faculty_allocations', faculty_id=setup['teacher']['id'], subject_id=setup['subject_id'],
                   class_id=setup['class_id'], division_id=setup['division_id'], is_primary=1)
    factory.capability('timetable_versions', False)
    settings = {'week_start_date': '2026-11-09', 'day_start': '10:00', 'day_end': '13:00', 'lecture_minutes': 60,
                'working_days': ['Monday'], 'solver': 'greedy',
                'targets': [{'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id']}]}
    with app.app_context():
        job_id, _attached = timetable_jobs.enqueue_job(settings, admin['id'])
        assert timetable_jobs._claim_next() == job_id
        timetable_jobs._process(job_id)
    rows = factory.query(
        'SELECT day_of_week, start_time, room_id FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s '
        'AND COALESCE(is_active, 1) = 1 ORDER BY start_time',
        (setup['course_id'], setup['class_id'], setup['division_id']),
    )
    assert rows, 'the job placed sessions'
    for row in rows:
        if row['room_id'] == setup['room_id'] and row['day_of_week'] == 'Monday':
            assert not (timedelta(hours=10) <= row['start_time'] < timedelta(hours=11)), 'the booked hour must not use the booked room'

    assert any(row['room_id'] is None for row in rows), 'with the only room booked, the 10:00 session was placed without a room'

    # Cancel closes it; the room no longer counts as booked (the class itself is now busy at 10, nothing else).
    cancelled = _ok(api(client, 'POST', f"/api/bookings/{requested['id']}/cancel"))['booking']
    assert cancelled['status'] == 'cancelled' and cancelled['can_cancel'] is False
    after = _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup)))
    assert 'slot_room_booked' not in {err['code'] for err in after['errors']}


def test_rejection_and_cancel_by_the_requester_and_dated_bookings_are_listed_in_a_window(client, factory):
    factory.capability('bookings', True)
    setup = factory.academic()
    hod = factory.user('HOD', setup=setup)
    admin = factory.user('Admin', setup=setup)
    next_monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)

    login(client, hod)
    weekly = _ok(api(client, 'POST', '/api/bookings', json=_booking(setup)))['booking']
    dated = _ok(api(client, 'POST', '/api/bookings', json=_booking(
        setup, day_of_week=None, booking_date=next_monday.isoformat(), start_time='11:00', end_time='12:00', title='Exam', kind='exam',
    )))['booking']
    assert dated['booking_date'] == next_monday.isoformat() and dated['day_of_week'] is None

    login(client, admin)
    rejected = _ok(api(client, 'POST', f"/api/bookings/{weekly['id']}/reject", json={'note': 'Hall needed.'}))['booking']
    assert rejected['status'] == 'rejected' and rejected['decision_note'] == 'Hall needed.'
    # The admin's own booking of a room their institution owns is approved at once.
    own = _ok(api(client, 'POST', '/api/bookings', json=_booking(setup, title='Staff meeting', start_time='12:00', end_time='13:00')))['booking']
    assert own['status'] == 'approved' and own['decided_by'] == admin['username']
    # A second approved booking cannot overlap it, in either direction (weekly vs dated).
    clash = _error(api(client, 'POST', '/api/bookings', json=_booking(
        setup, day_of_week=None, booking_date=next_monday.isoformat(), start_time='12:30', end_time='13:30',
    )), 400)
    assert clash['code'] == 'booking_room_booked' and 'Staff meeting' in clash['message']

    login(client, hod)
    assert _ok(api(client, 'POST', f"/api/bookings/{dated['id']}/cancel"))['booking']['status'] == 'cancelled'
    assert api(client, 'POST', f"/api/bookings/{own['id']}/cancel").status_code == 403, 'not theirs, no approve permission'

    everything = _ok(api(client, 'GET', '/api/bookings'))['bookings']
    statuses = {row['id']: row['status'] for row in everything}
    assert {key: statuses.get(key) for key in (weekly['id'], dated['id'], own['id'])} == {weekly['id']: 'rejected', dated['id']: 'cancelled', own['id']: 'approved'}
    assert [row['id'] for row in _ok(api(client, 'GET', '/api/bookings?status=approved'))['bookings']] == [own['id']]
    window = _ok(api(client, 'GET', f"/api/bookings?from={(next_monday + timedelta(days=1)).isoformat()}"))['bookings']
    assert dated['id'] not in {row['id'] for row in window} and own['id'] in {row['id'] for row in window}
    assert _error(api(client, 'GET', '/api/bookings?status=maybe'), 400)['code'] == 'booking_filter_invalid'


def test_bookings_need_the_capability_and_room_permissions(client, factory):
    setup = factory.academic()
    login(client, factory.user('Admin', setup=setup))
    assert _error(api(client, 'GET', '/api/bookings'), 404)['code'] == 'capability_off'
    assert _error(api(client, 'POST', '/api/bookings', json=_booking(setup)), 404)['code'] == 'capability_off'
    # Off: the slot check ignores the bookings table entirely.
    assert _ok(api(client, 'POST', '/api/timetable/check', json=_slot(setup)))['ok'] is True

    factory.capability('bookings', True)
    login(client, factory.user('Student', setup=setup))
    assert api(client, 'GET', '/api/bookings').status_code == 403
    assert api(client, 'POST', '/api/bookings', json=_booking(setup)).status_code == 403
    login(client, factory.user('Teacher', setup=setup))
    assert api(client, 'GET', '/api/bookings').status_code == 403, 'teachers have no room permission by default'
