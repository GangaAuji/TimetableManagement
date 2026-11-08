"""lecture_sessions: a held row on marking, cancel and undo, the close-day job, proxies, and the slot-delete guard."""

from datetime import timedelta

import pytest

from services.lecture_sessions import close_day
from tests.factories import LECTURE_DATE, LectureDay
from tests.http_helpers import api, login

DAY_AFTER = LECTURE_DATE + timedelta(days=1)
NEXT_MONDAY = LECTURE_DATE + timedelta(days=7)


@pytest.fixture(autouse=True)
def lecture_day(monkeypatch):
    monkeypatch.setattr('services.teacher_attendance.date', LectureDay)


@pytest.fixture
def lesson(factory):
    setup = factory.academic()
    student = factory.user('Student', setup=setup)
    return setup, student


def mark(client, timetable_id, student, status='Present', when=LECTURE_DATE):
    return api(client, 'POST', f'/api/portal/attendance/mark/{timetable_id}', json={
        'attendance_date': when.isoformat(),
        'marks': [{'student_id': student['student_id'], 'status': status, 'remarks': ''}],
    })


def cancel(client, timetable_id, when=LECTURE_DATE, reason='faculty_absent', note=''):
    return api(client, 'POST', f'/api/portal/attendance/cancel/{timetable_id}', json={
        'date': when.isoformat(), 'reason': reason, 'note': note,
    })


def uncancel(client, timetable_id, when=LECTURE_DATE):
    return api(client, 'POST', f'/api/portal/attendance/uncancel/{timetable_id}', json={'date': when.isoformat()})


def sessions_of(factory, timetable_id):
    return factory.query(
        'SELECT id, session_date, status, taught_by, marked_by, source, cancel_reason, cancelled_by '
        'FROM lecture_sessions WHERE timetable_id = %s ORDER BY session_date', (timetable_id,),
    )


def marks_of(factory, timetable_id):
    return factory.query('SELECT student_id, status, session_id FROM attendance WHERE timetable_id = %s', (timetable_id,))


def audit(factory, action):
    return factory.query('SELECT user_id, entity_id, new_values FROM audit_logs WHERE action = %s ORDER BY id', (action,))


# Marking records the lecture as held

def test_marking_creates_a_held_session_and_links_the_marks(client, factory, lesson):
    setup, student = lesson
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], student).status_code == 200
    [row] = sessions_of(factory, setup['timetable_id'])
    assert (row['session_date'], row['status'], row['source']) == (LECTURE_DATE, 'held', 'teacher')
    assert row['taught_by'] == setup['teacher']['id'] and row['marked_by'] == setup['teacher']['faculty_id']
    [saved] = marks_of(factory, setup['timetable_id'])
    assert saved['session_id'] == row['id']


def test_marking_again_keeps_one_session(client, factory, lesson):
    setup, student = lesson
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], student).status_code == 200
    assert mark(client, setup['timetable_id'], student, status='Absent').status_code == 200
    assert len(sessions_of(factory, setup['timetable_id'])) == 1
    assert [row['status'] for row in marks_of(factory, setup['timetable_id'])] == ['Absent']


def test_a_refused_mark_leaves_no_session(client, factory, lesson):
    setup, _ = lesson
    outsider = factory.user('Student', setup=factory.academic())
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], outsider).status_code == 400
    assert sessions_of(factory, setup['timetable_id']) == []


def test_mobile_promotion_creates_a_held_session(db, factory, lesson):
    from api.mobile.v1.sync_attendance import _promote_log_to_attendance

    setup, student = lesson
    cursor = db.cursor(dictionary=True)
    try:
        _promote_log_to_attendance(cursor, {
            'student_id': student['student_id'], 'timetable_id': setup['timetable_id'],
            'attendance_date': LECTURE_DATE, 'status': 'Present', 'marked_by_faculty_id': setup['teacher']['faculty_id'],
            'remarks': None,
        })
        db.commit()
    finally:
        cursor.close()
    [row] = sessions_of(factory, setup['timetable_id'])
    assert (row['status'], row['source']) == ('held', 'mobile')
    assert marks_of(factory, setup['timetable_id'])[0]['session_id'] == row['id']


# Cancellation

def test_teacher_cancels_a_lecture_and_marking_is_then_refused(client, factory, lesson):
    setup, student = lesson
    login(client, setup['teacher'])
    response = cancel(client, setup['timetable_id'], reason='faculty_absent', note='Sick')
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    [row] = sessions_of(factory, setup['timetable_id'])
    assert (row['status'], row['cancel_reason'], row['cancelled_by']) == ('cancelled', 'faculty_absent', setup['teacher']['id'])
    refused = mark(client, setup['timetable_id'], student)
    assert refused.status_code == 409 and refused.get_json()['error']['code'] == 'portal_cancelled'
    assert marks_of(factory, setup['timetable_id']) == []
    page = client.get(f'/api/portal/attendance/mark/{setup["timetable_id"]}').get_json()['data']
    assert page['cancelled'] is True and page['session_status'] == 'cancelled'
    [entry] = audit(factory, 'lecture_session_cancelled')
    assert entry['user_id'] == setup['teacher']['id'] and entry['entity_id'] == row['id']


def test_cancelling_a_marked_lecture_is_refused_for_the_teacher(client, factory, lesson):
    setup, student = lesson
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], student).status_code == 200
    response = cancel(client, setup['timetable_id'])
    assert response.status_code == 409 and response.get_json()['error']['code'] == 'portal_marked'
    assert sessions_of(factory, setup['timetable_id'])[0]['status'] == 'held'
    assert len(marks_of(factory, setup['timetable_id'])) == 1


def test_cancel_needs_the_lecture_weekday_and_a_known_reason(client, factory, lesson):
    setup, _ = lesson
    login(client, setup['teacher'])
    assert cancel(client, setup['timetable_id'], when=DAY_AFTER).status_code == 400
    assert cancel(client, setup['timetable_id'], reason='rain').status_code == 400
    assert sessions_of(factory, setup['timetable_id']) == []


def test_another_teacher_cannot_cancel(client, factory, lesson):
    setup, _ = lesson
    login(client, factory.user('Teacher', setup=setup))
    assert cancel(client, setup['timetable_id']).status_code == 403
    assert sessions_of(factory, setup['timetable_id']) == []


def test_undoing_a_cancellation(client, factory, lesson):
    setup, student = lesson
    login(client, setup['teacher'])
    # A future lecture: the row disappears again.
    assert cancel(client, setup['timetable_id'], when=NEXT_MONDAY).status_code == 200
    response = uncancel(client, setup['timetable_id'], when=NEXT_MONDAY)
    assert response.status_code == 200 and response.get_json()['data']['status'] == 'removed'
    assert sessions_of(factory, setup['timetable_id']) == []
    # Nothing to undo.
    assert uncancel(client, setup['timetable_id'], when=NEXT_MONDAY).status_code == 404
    # A past lecture goes back to not_marked.
    past = LECTURE_DATE - timedelta(days=7)
    assert cancel(client, setup['timetable_id'], when=past).status_code == 200
    assert uncancel(client, setup['timetable_id'], when=past).get_json()['data']['status'] == 'not_marked'
    assert [(r['session_date'], r['status']) for r in sessions_of(factory, setup['timetable_id'])] == [(past, 'not_marked')]
    assert len(audit(factory, 'lecture_session_restored')) == 2


def test_admin_cancels_a_marked_lecture_only_with_clear_marks(client, factory, lesson, monkeypatch):
    class _DayAfter(LectureDay):
        @classmethod
        def today(cls):
            return DAY_AFTER

    monkeypatch.setattr('api.web.attendance.date', _DayAfter)
    setup, student = lesson
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], student).status_code == 200
    [row] = sessions_of(factory, setup['timetable_id'])
    admin = client.application.test_client()
    login(admin, factory.user('Super Admin'))
    refused = api(admin, 'POST', f'/api/attendance/sessions/{row["id"]}/cancel', json={'reason': 'institution', 'note': ''})
    assert refused.status_code == 409 and refused.get_json()['error']['code'] == 'session_marked'
    assert len(marks_of(factory, setup['timetable_id'])) == 1
    cleared = api(admin, 'POST', f'/api/attendance/sessions/{row["id"]}/cancel',
                  json={'reason': 'institution', 'note': 'Strike', 'clear_marks': True})
    assert cleared.status_code == 200, cleared.get_data(as_text=True)[:300]
    assert marks_of(factory, setup['timetable_id']) == []
    assert sessions_of(factory, setup['timetable_id'])[0]['status'] == 'cancelled'
    [entry] = audit(factory, 'lecture_session_cancelled')
    assert '"marks_cleared": 1' in entry['new_values']
    restored = api(admin, 'POST', f'/api/attendance/sessions/{row["id"]}/uncancel', json={})
    assert restored.status_code == 200 and restored.get_json()['data']['status'] == 'not_marked'


def test_admin_cancels_by_slot_and_date_and_lists_sessions(client, factory, lesson):
    setup, _ = lesson
    login(client, factory.user('Super Admin'))
    response = api(client, 'POST', '/api/attendance/sessions/cancel', json={
        'timetable_id': setup['timetable_id'], 'date': NEXT_MONDAY.isoformat(), 'reason': 'exam', 'note': '',
    })
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    listed = client.get(f'/api/attendance/sessions?status=cancelled&timetable_id={setup["timetable_id"]}').get_json()['data']['sessions']
    assert [(row['date'], row['status'], row['reason'], row['source']) for row in listed] == [
        (NEXT_MONDAY.isoformat(), 'cancelled', 'exam', 'admin'),
    ]
    assert client.get('/api/attendance/sessions?status=bogus').status_code == 400
    assert api(client, 'POST', '/api/attendance/sessions/999999/cancel', json={'reason': 'other'}).status_code == 404


def test_session_endpoints_need_attendance_permissions(client, factory, lesson):
    setup, student = lesson
    login(client, student)
    assert client.get('/api/attendance/sessions').status_code == 403
    assert api(client, 'POST', '/api/attendance/sessions/cancel', json={
        'timetable_id': setup['timetable_id'], 'date': NEXT_MONDAY.isoformat(), 'reason': 'exam',
    }).status_code == 403


# Proxies

def _approve_proxy(factory, setup, proxy, when):
    factory.insert(
        'proxy_log', original_faculty_id=setup['teacher']['id'], proxy_faculty_id=proxy['id'],
        timetable_id=setup['timetable_id'], absence_date=when, status='ASSIGNED', approval_status='APPROVED',
    )


def test_approved_proxy_marks_on_the_proxy_date_only(client, factory, lesson):
    setup, student = lesson
    proxy = factory.user('Teacher', setup=setup)
    _approve_proxy(factory, setup, proxy, NEXT_MONDAY)
    login(client, proxy)
    assert mark(client, setup['timetable_id'], student).status_code == 403
    assert client.get(f'/api/portal/attendance/mark/{setup["timetable_id"]}').status_code == 403
    _approve_proxy(factory, setup, proxy, LECTURE_DATE)
    page = client.get(f'/api/portal/attendance/mark/{setup["timetable_id"]}')
    assert page.status_code == 200 and page.get_json()['data']['is_owner'] is False
    assert mark(client, setup['timetable_id'], student).status_code == 200
    [row] = sessions_of(factory, setup['timetable_id'])
    assert row['taught_by'] == proxy['id'] and row['marked_by'] == proxy['faculty_id']
    [saved] = marks_of(factory, setup['timetable_id'])
    assert saved['session_id'] == row['id']


def test_pending_proxy_may_not_mark(client, factory, lesson):
    setup, student = lesson
    proxy = factory.user('Teacher', setup=setup)
    factory.insert(
        'proxy_log', original_faculty_id=setup['teacher']['id'], proxy_faculty_id=proxy['id'],
        timetable_id=setup['timetable_id'], absence_date=LECTURE_DATE, status='ASSIGNED', approval_status='PENDING',
    )
    login(client, proxy)
    assert mark(client, setup['timetable_id'], student).status_code == 403


# close-day

def test_close_day_writes_not_marked_for_working_weekday_slots_once(db, factory, lesson):
    setup, _ = lesson
    counts = close_day(db, LECTURE_DATE, today=DAY_AFTER)
    assert counts['created'] >= 1 and counts['dry_run'] is False
    [row] = sessions_of(factory, setup['timetable_id'])
    assert (row['session_date'], row['status'], row['source'], row['taught_by']) == (LECTURE_DATE, 'not_marked', 'close_day', setup['teacher']['id'])
    again = close_day(db, LECTURE_DATE, today=DAY_AFTER)
    assert again['created'] == 0 and again['existing'] >= 1
    assert len(sessions_of(factory, setup['timetable_id'])) == 1
    assert len(audit(factory, 'attendance_close_day')) == 2


def test_close_day_dry_run_writes_nothing(db, factory, lesson):
    setup, _ = lesson
    counts = close_day(db, LECTURE_DATE, dry_run=True, today=DAY_AFTER)
    assert counts['created'] >= 1
    assert sessions_of(factory, setup['timetable_id']) == [] and audit(factory, 'attendance_close_day') == []


def test_close_day_skips_other_weekdays_holidays_retired_slots_and_other_semesters(db, factory, lesson):
    setup, _ = lesson
    close_day(db, DAY_AFTER, today=DAY_AFTER + timedelta(days=1))           # a Tuesday: the Monday slot is not due
    assert sessions_of(factory, setup['timetable_id']) == []
    holiday = factory.insert('institution_holidays', holiday_date=LECTURE_DATE, name='Test holiday', applies_to_program='UG', is_recurring=0)
    counts = close_day(db, LECTURE_DATE, today=DAY_AFTER)
    assert counts['holiday'] >= 1 and sessions_of(factory, setup['timetable_id']) == []
    factory.execute('DELETE FROM institution_holidays WHERE id = %s', (holiday,))
    year = factory.insert('academic_years', name=f'Y{factory._next()}', start_date='2025-06-01', end_date='2026-05-31')
    semester = factory.insert('semesters', academic_year_id=year, semester_number=1, semester_name='Old',
                              start_date='2025-06-01', end_date='2025-11-30')
    factory.execute('UPDATE timetable SET semester_id = %s WHERE id = %s', (semester, setup['timetable_id']))
    counts = close_day(db, LECTURE_DATE, today=DAY_AFTER)
    assert counts['outside_semester'] >= 1 and sessions_of(factory, setup['timetable_id']) == []
    factory.execute('UPDATE timetable SET semester_id = NULL, is_active = 0 WHERE id = %s', (setup['timetable_id'],))
    close_day(db, LECTURE_DATE, today=DAY_AFTER)
    assert sessions_of(factory, setup['timetable_id']) == []


def test_close_day_refuses_today_and_the_future(db):
    with pytest.raises(ValueError):
        close_day(db, LECTURE_DATE, today=LECTURE_DATE)


def test_close_day_leaves_held_and_cancelled_rows_alone_and_names_the_proxy(client, db, factory, lesson):
    setup, student = lesson
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], student).status_code == 200
    close_day(db, LECTURE_DATE, today=DAY_AFTER)
    assert [row['status'] for row in sessions_of(factory, setup['timetable_id'])] == ['held']
    other = factory.academic()
    proxy = factory.user('Teacher', setup=other)
    _approve_proxy(factory, other, proxy, LECTURE_DATE)
    close_day(db, LECTURE_DATE, today=DAY_AFTER)
    [row] = sessions_of(factory, other['timetable_id'])
    assert (row['status'], row['taught_by']) == ('not_marked', proxy['id'])
    listed = client.get(f'/api/attendance/sessions?status=not_marked&timetable_id={other["timetable_id"]}')
    assert listed.status_code == 403   # a teacher has no attendance_view


def test_close_day_cli_reports_counts(app, db, factory, lesson, monkeypatch):
    import core.attendance_cli as cli

    class _Today(LectureDay):
        @classmethod
        def today(cls):
            return DAY_AFTER

    monkeypatch.setattr(cli, 'date', _Today)
    result = app.test_cli_runner().invoke(args=['attendance', 'close-day', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert LECTURE_DATE.isoformat() in result.output and 'Dry run: nothing was written.' in result.output
    assert 'device absences to write 0' in result.output
    assert sessions_of(factory, lesson[0]['timetable_id']) == []
    result = app.test_cli_runner().invoke(args=['attendance', 'close-day'])
    assert result.exit_code == 0, result.output
    assert sessions_of(factory, lesson[0]['timetable_id'])[0]['status'] == 'not_marked'
    refused = app.test_cli_runner().invoke(args=['attendance', 'close-day', '--date', DAY_AFTER.isoformat()])
    assert refused.exit_code != 0 and 'Only past days' in refused.output


# Close-day writes Absent for roster students a device did not detect (design Q10)

def promote(db, setup, student, **extra):
    from api.mobile.v1.sync_attendance import _promote_log_to_attendance

    row = {
        'student_id': student['student_id'], 'timetable_id': setup['timetable_id'], 'attendance_date': LECTURE_DATE,
        'status': 'Present', 'marked_by_faculty_id': setup['teacher']['faculty_id'], 'marked_by_user_id': setup['teacher']['id'],
        'remarks': None,
    }
    row.update(extra)
    cursor = db.cursor(dictionary=True)
    try:
        _promote_log_to_attendance(cursor, row)
        db.commit()
    finally:
        cursor.close()


def test_close_day_marks_undetected_roster_students_absent_after_a_mobile_session(db, factory, lesson):
    setup, seen = lesson
    unseen = factory.user('Student', setup=setup)
    left = factory.user('Student', setup=setup)
    factory.execute('UPDATE students SET is_active = 0 WHERE id = %s', (left['student_id'],))
    promote(db, setup, seen)
    counts = close_day(db, LECTURE_DATE, dry_run=True, today=DAY_AFTER)
    assert counts['absent_filled'] == 1
    assert len(marks_of(factory, setup['timetable_id'])) == 1
    counts = close_day(db, LECTURE_DATE, today=DAY_AFTER)
    assert counts['absent_filled'] == 1
    [session] = sessions_of(factory, setup['timetable_id'])
    rows = {row['student_id']: row for row in factory.query(
        'SELECT student_id, status, session_id, marked_by, remarks FROM attendance WHERE timetable_id = %s', (setup['timetable_id'],),
    )}
    assert rows[seen['student_id']]['status'] == 'Present'
    filled = rows[unseen['student_id']]
    assert (filled['status'], filled['session_id'], filled['marked_by']) == ('Absent', session['id'], setup['teacher']['faculty_id'])
    assert 'device' in filled['remarks']
    assert left['student_id'] not in rows
    assert close_day(db, LECTURE_DATE, today=DAY_AFTER)['absent_filled'] == 0


def test_close_day_does_not_fill_absences_for_teacher_marked_sessions(client, db, factory, lesson):
    setup, student = lesson
    factory.user('Student', setup=setup)
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], student).status_code == 200
    counts = close_day(db, LECTURE_DATE, today=DAY_AFTER)
    assert counts['absent_filled'] == 0 and len(marks_of(factory, setup['timetable_id'])) == 1


# A device's mark is accepted only for a roster student from a teacher who may mark the slot

def test_mobile_promotion_refuses_a_student_outside_the_roster(db, factory, lesson):
    from api.mobile.v1.sync_attendance import MarkRefused

    setup, _ = lesson
    outsider = factory.user('Student', setup=factory.academic())
    with pytest.raises(MarkRefused):
        promote(db, setup, outsider)
    assert sessions_of(factory, setup['timetable_id']) == [] and marks_of(factory, setup['timetable_id']) == []


def test_mobile_promotion_refuses_a_marker_who_may_not_mark_the_slot(db, factory, lesson):
    from api.mobile.v1.sync_attendance import MarkRefused

    setup, student = lesson
    other = factory.user('Teacher', setup=setup)
    with pytest.raises(MarkRefused):
        promote(db, setup, student, marked_by_faculty_id=other['faculty_id'], marked_by_user_id=other['id'])
    assert marks_of(factory, setup['timetable_id']) == []
    _approve_proxy(factory, setup, other, LECTURE_DATE)
    promote(db, setup, student, marked_by_faculty_id=other['faculty_id'], marked_by_user_id=other['id'])
    [row] = sessions_of(factory, setup['timetable_id'])
    assert (row['status'], row['taught_by']) == ('held', other['id'])


# The slot-delete guard

def test_a_slot_with_sessions_cannot_be_deleted(client, factory, lesson):
    import mysql.connector

    setup, student = lesson
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], student).status_code == 200
    with pytest.raises(mysql.connector.Error) as failure:
        factory.execute('DELETE FROM timetable WHERE id = %s', (setup['timetable_id'],))
    assert failure.value.errno == 1451
    factory.connection.rollback()
    assert len(sessions_of(factory, setup['timetable_id'])) == 1
