"""Academic terms on the *_test database.

With the capability off, a saved exam term changes nothing: generation still uses that Monday and
close-day still writes the session. With it on, that Monday is not generated, close-day skips it,
an existing unmarked session is cancelled (reason calendar), and the term API reports scheduled,
conducted and attended.
"""

from datetime import date

from services.lecture_sessions import close_day
from services.timetable.generator import generate_timetable_for_class
from tests.http_helpers import api, login

MONDAY = date(2026, 11, 9)
WEEK_END = date(2026, 11, 15)


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['error']['code']


def _year(factory):
    return factory.insert('academic_years', name=f'Y{factory._next()}', start_date='2026-01-01', end_date='2026-12-31')


def _terms(factory, year_id):
    factory.insert('academic_terms', institution_id=1, academic_year_id=year_id, name='Teaching', kind='teaching',
                   start_date=MONDAY, end_date=WEEK_END)
    factory.insert('academic_terms', institution_id=1, academic_year_id=year_id, name='Exam day', kind='exam',
                   start_date=MONDAY, end_date=MONDAY)


def _placed_days(factory, setup):
    return {row['day_of_week'] for row in factory.query(
        'SELECT day_of_week FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s AND COALESCE(is_active, 1) = 1',
        (setup['course_id'], setup['class_id'], setup['division_id']),
    )}


def test_capability_off_ignores_terms_and_the_api_is_hidden(app, client, factory):
    setup = factory.academic()
    year_id = _year(factory)
    _terms(factory, year_id)
    factory.execute('UPDATE subjects SET lectures_per_week = 1 WHERE id = %s', (setup['subject_id'],))
    factory.execute('DELETE FROM timetable WHERE id = %s', (setup['timetable_id'],))
    factory.insert('faculty_allocations', faculty_id=setup['teacher']['id'], subject_id=setup['subject_id'],
                   class_id=setup['class_id'], division_id=setup['division_id'], is_primary=1)
    with app.app_context():
        result = generate_timetable_for_class(
            setup['course_id'], setup['class_id'], setup['division_id'], week_start_date='2026-11-09',
            day_start='09:00', day_end='11:00', lecture_minutes=60, working_days=['Monday', 'Tuesday'], candidate_count=1,
        )
    assert result['status'] == 'success', result.get('message')
    assert 'Monday' in _placed_days(factory, setup)

    login(client, factory.user('Super Admin'))
    assert _error(api(client, 'GET', '/api/academic-terms'), 404) == 'capability_off'


def test_teaching_term_gates_generation_close_day_and_cancels_exam_sessions(app, client, factory, db):
    setup = factory.academic()
    year_id = _year(factory)
    _terms(factory, year_id)
    factory.capability('academic_terms', True)
    with app.app_context():
        counts = close_day(db, MONDAY, today=date(2026, 11, 10))
    assert counts['outside_term'] >= 1
    assert factory.query('SELECT id FROM lecture_sessions WHERE timetable_id = %s', (setup['timetable_id'],)) == []
    factory.execute(
        "INSERT INTO lecture_sessions (timetable_id, session_date, status, source) VALUES (%s, %s, 'not_marked', 'admin')",
        (setup['timetable_id'], MONDAY),
    )
    with app.app_context():
        from services.academic_calendar import sweep

        cursor = db.cursor(dictionary=True)
        try:
            assert sweep(cursor) == 1
        finally:
            cursor.close()
    [session] = factory.query('SELECT status, cancel_reason FROM lecture_sessions WHERE timetable_id = %s', (setup['timetable_id'],))
    assert (session['status'], session['cancel_reason']) == ('cancelled', 'calendar')

    factory.execute('DELETE FROM lecture_sessions WHERE timetable_id = %s', (setup['timetable_id'],))
    factory.execute('DELETE FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s',
                    (setup['course_id'], setup['class_id'], setup['division_id']))
    factory.execute('UPDATE subjects SET lectures_per_week = 1 WHERE id = %s', (setup['subject_id'],))
    factory.insert('faculty_allocations', faculty_id=setup['teacher']['id'], subject_id=setup['subject_id'],
                   class_id=setup['class_id'], division_id=setup['division_id'], is_primary=1)
    with app.app_context():
        result = generate_timetable_for_class(
            setup['course_id'], setup['class_id'], setup['division_id'], week_start_date='2026-11-09',
            day_start='09:00', day_end='11:00', lecture_minutes=60, working_days=['Monday', 'Tuesday'], candidate_count=1,
        )
    assert result['status'] == 'success', result.get('message')
    assert 'Monday' not in _placed_days(factory, setup) and 'Tuesday' in _placed_days(factory, setup)

    login(client, factory.user('Super Admin'))
    data = _ok(api(client, 'GET', '/api/academic-terms'))
    assert {term['kind'] for term in data['terms']} == {'teaching', 'exam'}
    assert set(data['totals']) >= {'scheduled', 'conducted', 'attended'} and data['weeks']
    assert _error(api(client, 'POST', '/api/academic-terms', json={
        'name': 'Overlap', 'kind': 'break', 'start_date': '2026-11-10', 'end_date': '2026-11-12', 'academic_year_id': year_id,
    }), 400) == 'term_overlap'
    saved = _ok(api(client, 'POST', '/api/academic-terms', json={
        'name': 'Winter break', 'kind': 'break', 'start_date': '2026-12-20', 'end_date': '2026-12-31', 'academic_year_id': year_id,
    }))
    assert saved['cancelled_sessions'] == 0 and any(term['name'] == 'Winter break' for term in saved['terms'])
    api(client, 'POST', '/api/session/logout')
    login(client, factory.user('Student', setup=setup))
    assert api(client, 'GET', '/api/academic-terms').status_code == 403
