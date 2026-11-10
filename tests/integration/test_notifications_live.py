"""Phase D: the notifications outbox on the golden cohort. No mail is sent; the sender is a fake."""

from datetime import date

import pytest

import api.web  # noqa: F401  (breaks the services.export_jobs <-> api.web import cycle)
from services import notifications
from tests.http_helpers import api, login
from tests.integration.test_attendance_calc_live import cohort  # noqa: F401  (fixture)

pytestmark = pytest.mark.live_db


def _rows(factory, **where):
    clauses = ' AND '.join(f'{key} = %s' for key in where) or '1 = 1'
    return factory.query(
        f'SELECT id, kind, recipient_user_id, recipient_email, subject, status, attempts, last_error, dedupe_key '
        f'FROM notifications WHERE {clauses} ORDER BY id',
        tuple(where.values()),
    )


def _with_cursor(db, work):
    cursor = db.cursor(dictionary=True)
    try:
        result = work(cursor)
        db.commit()
        return result
    finally:
        cursor.close()


# Triggers

def test_cancelling_a_lecture_queues_one_notice_per_roster_student_and_the_teacher(client, db, factory, cohort):
    slot = cohort['slots']['physics_thu']
    when = date(2026, 3, 26)
    login(client, cohort['teacher'])
    response = api(client, 'POST', f'/api/portal/attendance/cancel/{slot}', json={'date': when.isoformat(), 'reason': 'institution', 'note': ''})
    assert response.status_code == 200, response.get_json()
    rows = _rows(factory, kind='lecture_cancelled')
    recipients = {row['recipient_user_id'] for row in rows}
    assert recipients == {cohort['asha']['id'], cohort['ben']['id'], cohort['chen']['id'], cohort['teacher']['id']}
    assert cohort['dev']['id'] not in recipients   # division B
    assert all(row['status'] == 'queued' and row['recipient_email'].endswith('@example.org') for row in rows)
    assert 'cancelled' in rows[0]['subject'] and f'cancel:{slot}:{when}:' in rows[0]['dedupe_key']

    # Firing again queues nothing new.
    again = _with_cursor(db, lambda cursor: notifications.on_lecture_cancelled(
        cursor, timetable_id=slot, session_date=when, reason='institution',
    ))
    assert again == 0 and len(_rows(factory, kind='lecture_cancelled')) == 4


def test_an_elective_cancellation_reaches_only_the_students_who_chose_it(db, factory, cohort):
    queued = _with_cursor(db, lambda cursor: notifications.on_lecture_cancelled(
        cursor, timetable_id=cohort['slots']['german_tue'], session_date=date(2026, 3, 24), reason='exam',
    ))
    rows = _rows(factory, kind='lecture_cancelled')
    assert queued == 2 and {row['recipient_user_id'] for row in rows} == {cohort['ben']['id'], cohort['teacher']['id']}


def test_switches_suppress_their_trigger_and_the_master_switch_suppresses_all(db, factory, cohort):
    admin = factory.user('Super Admin')
    _with_cursor(db, lambda cursor: notifications.save_settings(cursor, {'cancellation_alerts': False}, admin['id']))
    queued = _with_cursor(db, lambda cursor: notifications.on_lecture_cancelled(
        cursor, timetable_id=cohort['slots']['physics_thu'], session_date=date(2026, 3, 26), reason='other',
    ))
    assert queued == 0 and _rows(factory) == []

    _with_cursor(db, lambda cursor: notifications.save_settings(cursor, {'cancellation_alerts': True, 'enabled': False}, admin['id']))
    queued = _with_cursor(db, lambda cursor: notifications.on_lecture_cancelled(
        cursor, timetable_id=cohort['slots']['physics_thu'], session_date=date(2026, 3, 26), reason='other',
    ))
    assert queued == 0 and _rows(factory) == []


def test_proxy_assignment_tells_the_substitute_and_the_absent_teacher(db, factory, cohort):
    substitute = factory.user('Teacher', setup=cohort['setup'])
    proxy_id = factory.insert(
        'proxy_log', original_faculty_id=cohort['teacher']['id'], proxy_faculty_id=substitute['id'],
        timetable_id=cohort['slots']['physics_mon'], absence_date=date(2026, 3, 23), status='ASSIGNED', approval_status='APPROVED',
    )
    queued = _with_cursor(db, lambda cursor: notifications.on_proxy_assigned(cursor, proxy_id))
    rows = _rows(factory, kind='proxy_assigned')
    assert queued == 2 and {row['recipient_user_id'] for row in rows} == {substitute['id'], cohort['teacher']['id']}
    by_user = {row['recipient_user_id']: row['subject'] for row in rows}
    assert 'You are the substitute' in by_user[substitute['id']] and 'Substitute arranged' in by_user[cohort['teacher']['id']]

    unassigned = factory.insert(
        'proxy_log', original_faculty_id=cohort['teacher']['id'], proxy_faculty_id=None,
        timetable_id=cohort['slots']['physics_mon'], absence_date=date(2026, 3, 30), status='UNASSIGNED', approval_status='APPROVED',
    )
    assert _with_cursor(db, lambda cursor: notifications.on_proxy_assigned(cursor, unassigned)) == 0


def test_shift_requests_go_to_the_department_hod_and_decisions_to_the_teacher(db, factory, cohort):
    setup = cohort['setup']
    hod = factory.user('HOD', setup=setup)
    other_hod = factory.user('HOD')   # another department: never notified
    request_id = factory.insert(
        'shift_change_requests', faculty_id=cohort['teacher']['id'], day_of_week='Monday',
        current_shift_name='Morning', requested_shift_name='Afternoon', reason='Commute', status='pending',
    )
    queued = _with_cursor(db, lambda cursor: notifications.on_shift_request(cursor, request_id))
    rows = _rows(factory, kind='shift_request')
    assert queued == 1 and [row['recipient_user_id'] for row in rows] == [hod['id']]
    assert other_hod['id'] not in {row['recipient_user_id'] for row in rows}

    assert _with_cursor(db, lambda cursor: notifications.on_shift_decision(cursor, request_id)) == 0   # still pending
    factory.execute("UPDATE shift_change_requests SET status = 'approved', admin_response = 'Fine' WHERE id = %s", (request_id,))
    queued = _with_cursor(db, lambda cursor: notifications.on_shift_decision(cursor, request_id))
    rows = _rows(factory, kind='shift_decision')
    assert queued == 1 and rows[0]['recipient_user_id'] == cohort['teacher']['id'] and 'approved' in rows[0]['subject']


def test_close_day_triggers_queue_the_digest_and_defaulter_alerts_once(db, factory, cohort):
    hod = factory.user('HOD', setup=cohort['setup'])
    # German on Tue 17 Mar is the cohort's one not_marked session.
    queued = _with_cursor(db, lambda cursor: notifications.not_marked_digest(cursor, date(2026, 3, 17)))
    rows = _rows(factory, kind='not_marked_digest')
    assert queued == 1 and rows[0]['recipient_user_id'] == hod['id'] and '1 lecture(s) not marked' in rows[0]['subject']
    assert _with_cursor(db, lambda cursor: notifications.not_marked_digest(cursor, date(2026, 3, 17))) == 0
    assert _with_cursor(db, lambda cursor: notifications.not_marked_digest(cursor, date(2026, 3, 18))) == 0   # nothing unmarked

    queued = _with_cursor(db, lambda cursor: notifications.defaulter_alerts(cursor, month='2026-03', threshold=75))
    rows = _rows(factory, kind='defaulter')
    assert queued == 2 and {row['recipient_user_id'] for row in rows} == {cohort['asha']['id'], cohort['chen']['id']}
    assert all(row['dedupe_key'].endswith(':2026-03') for row in rows)
    assert _with_cursor(db, lambda cursor: notifications.defaulter_alerts(cursor, month='2026-03', threshold=75)) == 0
    # A new month alerts again.
    assert _with_cursor(db, lambda cursor: notifications.defaulter_alerts(cursor, month='2026-04', threshold=75)) == 2


def test_after_close_day_runs_both_triggers_and_never_raises(app, db, factory, cohort):
    factory.user('HOD', setup=cohort['setup'])
    with app.app_context():
        counts = notifications.after_close_day(app, db, today=date(2026, 3, 18))
    assert counts['not_marked_digest'] == 1 and counts['defaulter'] >= 2


def test_a_recipient_without_an_address_is_recorded_as_skipped(db, factory, cohort):
    factory.execute("UPDATE users SET email = NULL WHERE id = %s", (cohort['asha']['id'],))
    factory.execute("UPDATE students SET email = '' WHERE id = %s", (cohort['asha']['student_id'],))
    queued = _with_cursor(db, lambda cursor: notifications.enqueue(
        cursor, kind='test', subject='s', body='b', recipient_user_id=cohort['asha']['id'],
    ))
    rows = _rows(factory, kind='test')
    assert queued is None and rows[0]['status'] == 'skipped' and 'no email' in rows[0]['last_error']


# Sending

def test_run_tenant_sends_queued_mail_and_retries_failures_with_backoff(app, db, factory):
    admin = factory.user('Super Admin')
    first = _with_cursor(db, lambda cursor: notifications.queue_test_message(cursor, to='one@example.org', user_id=admin['id']))
    second = _with_cursor(db, lambda cursor: notifications.queue_test_message(cursor, to='two@example.org', user_id=admin['id']))
    delivered = []

    def sender(account, *, to, subject, body, reply_to=None):
        if to == 'two@example.org':
            raise TimeoutError('smtp timed out')
        delivered.append((account['source'], to, subject))

    with app.app_context():
        app.config['SMTP_HOST'] = 'smtp.example.test'
        try:
            counts = notifications.run_tenant(app, drain=True, sender=sender)
            assert counts == {'sent': 1, 'retry': 1, 'failed': 0, 'deferred': 0}
            # The failed row is queued for later; nothing is claimable until its backoff passes.
            assert notifications.run_tenant(app, drain=True, sender=sender) == {'sent': 0, 'retry': 0, 'failed': 0, 'deferred': 0}
        finally:
            app.config['SMTP_HOST'] = None
    assert delivered == [('server', 'one@example.org', '[Timetable] Test notification')] or delivered[0][1] == 'one@example.org'
    sent = _rows(factory, id=first)[0]
    retry = _rows(factory, id=second)[0]
    assert (sent['status'], sent['attempts']) == ('sent', 1)
    assert (retry['status'], retry['attempts']) == ('queued', 1) and 'TimeoutError' in retry['last_error']

    factory.execute('UPDATE notifications SET available_at = UTC_TIMESTAMP() - INTERVAL 1 SECOND WHERE id = %s', (second,))
    with app.app_context():
        app.config['SMTP_HOST'] = 'smtp.example.test'
        try:
            assert notifications.run_tenant(app, drain=True, sender=lambda account, **kw: delivered.append(kw['to']))['sent'] == 1
        finally:
            app.config['SMTP_HOST'] = None
    assert _rows(factory, id=second)[0]['status'] == 'sent'


def test_without_any_smtp_account_rows_stay_queued_and_no_attempt_is_burnt(app, db, factory):
    queued = _with_cursor(db, lambda cursor: notifications.queue_test_message(cursor, to='one@example.org'))
    with app.app_context():
        assert app.config.get('SMTP_HOST') is None
        counts = notifications.run_tenant(app, drain=True)
    assert counts['deferred'] == 1 and counts['sent'] == 0
    row = _rows(factory, id=queued)[0]
    assert (row['status'], row['attempts']) == ('queued', 0) and 'No SMTP account' in row['last_error']


def test_tenant_smtp_settings_are_used_and_the_password_round_trips_encrypted(app, db, factory):
    admin = factory.user('Super Admin')
    with app.app_context():
        _with_cursor(db, lambda cursor: notifications.save_settings(
            cursor, {'smtp_host': 'mail.college.test', 'smtp_port': 2525, 'smtp_user': 'tt', 'smtp_from': 'tt@college.test'},
            admin['id'], password='s3cret',
        ))
        stored = factory.query('SELECT smtp_password_enc FROM notification_settings WHERE id = 1')[0]['smtp_password_enc']
        assert stored.startswith('enc:v1:') and 's3cret' not in stored
        cursor = db.cursor(dictionary=True)
        try:
            account = notifications.smtp_account(cursor)
            assert (account['source'], account['host'], account['port'], account['user'], account['password']) == \
                ('tenant', 'mail.college.test', 2525, 'tt', 's3cret')
            settings = notifications.load_settings(cursor)
            assert settings['has_password'] is True and 'smtp_password' not in settings and 'smtp_password_enc' not in settings
            # Saving other fields keeps the password; clear_password removes it.
            notifications.save_settings(cursor, {'reply_to': 'office@college.test'}, admin['id'])
            assert notifications.smtp_account(cursor)['password'] == 's3cret'
            notifications.save_settings(cursor, {}, admin['id'], clear_password=True)
            assert notifications.smtp_account(cursor)['password'] is None
            db.commit()
        finally:
            cursor.close()


# API

def test_settings_api_round_trips_without_ever_returning_the_password(client, factory):
    owner = factory.user('Super Admin')
    login(client, owner)
    response = api(client, 'GET', '/api/notifications/settings')
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['settings']['has_password'] is False and data['status']['delivery'] == 'none' and data['can_change'] is True

    response = api(client, 'PUT', '/api/notifications/settings', json={
        'smtp_host': 'mail.college.test', 'smtp_port': 587, 'smtp_user': 'tt', 'smtp_password': 'pw', 'smtp_from': 'tt@college.test',
        'defaulter_alerts': False,
    })
    assert response.status_code == 200, response.get_json()
    data = response.get_json()['data']
    assert data['settings']['has_password'] is True and data['settings']['defaulter_alerts'] is False
    assert data['status']['delivery'] == 'tenant' and 'pw' not in response.get_data(as_text=True)
    assert 'smtp_password' not in data['settings']

    assert api(client, 'PUT', '/api/notifications/settings', json={'smtp_port': 70000}).status_code == 400
    assert api(client, 'PUT', '/api/notifications/settings', json={'smtp_from': 'not-an-address'}).status_code == 400
    assert api(client, 'PUT', '/api/notifications/settings', json={'enabled': 'yes'}).status_code == 400
    assert api(client, 'PUT', '/api/notifications/settings', json={'unknown': 1}).status_code == 400

    response = api(client, 'POST', '/api/notifications/test', json={'to': 'ops@college.test'})
    assert response.status_code == 200 and response.get_json()['data']['queued'] is True
    assert api(client, 'POST', '/api/notifications/test', json={'to': 'nope'}).status_code == 400

    response = api(client, 'GET', '/api/notifications')
    rows = response.get_json()['data']['notifications']
    assert response.status_code == 200 and rows[0]['kind'] == 'test' and rows[0]['status'] == 'queued'


def test_settings_api_needs_the_settings_permissions(client, factory):
    teacher = factory.user('Teacher')
    login(client, teacher)
    assert api(client, 'GET', '/api/notifications/settings').status_code == 403
    assert api(client, 'PUT', '/api/notifications/settings', json={'enabled': False}).status_code == 403
    assert api(client, 'GET', '/api/notifications').status_code == 403
