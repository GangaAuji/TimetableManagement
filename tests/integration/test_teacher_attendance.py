"""POST /api/portal/attendance/mark/<id>: a teacher marks only their own lecture; nobody else marks at all."""

import pytest

from tests.factories import LECTURE_DATE, LectureDay
from tests.http_helpers import api, login


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


def saved(factory, timetable_id):
    return factory.query(
        'SELECT student_id, status, marked_by, attendance_date FROM attendance WHERE timetable_id = %s',
        (timetable_id,),
    )


def test_teacher_marks_their_own_lecture(client, factory, lesson):
    setup, student = lesson
    login(client, setup['teacher'])
    response = mark(client, setup['timetable_id'], student)
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert response.get_json()['data']['saved'] == 1
    [row] = saved(factory, setup['timetable_id'])
    assert (row['student_id'], row['status'], row['marked_by']) == (
        student['student_id'], 'Present', setup['teacher']['faculty_id'],
    )
    assert row['attendance_date'] == LECTURE_DATE


def test_teacher_is_refused_another_teachers_lecture(client, factory, lesson):
    setup, student = lesson
    other = factory.user('Teacher', setup=setup)
    login(client, other)
    response = mark(client, setup['timetable_id'], student)
    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'portal_denied'
    assert saved(factory, setup['timetable_id']) == []


def test_student_is_refused(client, factory, lesson):
    setup, student = lesson
    login(client, student)
    response = mark(client, setup['timetable_id'], student)
    assert response.status_code == 403
    assert response.get_json()['error']['code'] == 'forbidden'
    assert saved(factory, setup['timetable_id']) == []


def test_no_session_is_refused(client, lesson):
    setup, student = lesson
    assert mark(client, setup['timetable_id'], student).status_code == 401


# Rosters (data_access/teacher_attendance.fetch_lecture_roster). A normal lecture takes its
# course, class and division. A whole-class lecture (no division) takes the whole class. An
# elective takes only students with a student_subject_selections row for the subject.

def _student_in(factory, setup, division_id):
    student = factory.user('Student', setup=setup)
    factory.execute('UPDATE students SET division_id = %s WHERE id = %s', (division_id, student['student_id']))
    return student


def test_division_lecture_accepts_its_division_and_refuses_another(client, factory, lesson):
    setup, student = lesson
    other_division = factory.insert('divisions', name=f'B{factory._next()}')
    outsider = _student_in(factory, setup, other_division)
    login(client, setup['teacher'])
    assert mark(client, setup['timetable_id'], student).status_code == 200
    response = mark(client, setup['timetable_id'], outsider)
    assert response.status_code == 400
    assert [row['student_id'] for row in saved(factory, setup['timetable_id'])] == [student['student_id']]


@pytest.fixture
def whole_class(factory):
    setup = factory.academic()
    factory.execute('UPDATE timetable SET division_id = NULL WHERE id = %s', (setup['timetable_id'],))
    return setup


def test_a_whole_class_lecture_without_a_division_can_be_marked(client, factory, whole_class):
    student = factory.user('Student', setup=whole_class)
    login(client, whole_class['teacher'])
    response = mark(client, whole_class['timetable_id'], student)
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert [row['student_id'] for row in saved(factory, whole_class['timetable_id'])] == [student['student_id']]


def test_a_whole_class_lecture_accepts_every_division_of_the_class(client, factory, whole_class):
    other_division = factory.insert('divisions', name=f'B{factory._next()}')
    student = _student_in(factory, whole_class, other_division)
    login(client, whole_class['teacher'])
    assert mark(client, whole_class['timetable_id'], student).status_code == 200


def test_a_whole_class_lecture_refuses_a_student_from_another_class(client, factory, whole_class):
    outsider = factory.user('Student', setup=factory.academic())
    login(client, whole_class['teacher'])
    assert mark(client, whole_class['timetable_id'], outsider).status_code == 400
    assert saved(factory, whole_class['timetable_id']) == []


def test_a_whole_class_lecture_shows_on_the_mark_page(client, factory, whole_class):
    student = factory.user('Student', setup=whole_class)
    login(client, whole_class['teacher'])
    response = client.get(f'/api/portal/attendance/mark/{whole_class["timetable_id"]}')
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert [row['id'] for row in response.get_json()['data']['students']] == [student['student_id']]


def _subject_lecture(factory, setup, **subject):
    n = factory._next()
    subject_id = factory.insert(
        'subjects', name=f'Subject {n}', course_code=f'SUB{n}', course_id=setup['course_id'], class_id=setup['class_id'],
        **subject,
    )
    return factory.insert(
        'timetable', course_id=setup['course_id'], class_id=setup['class_id'], division_id=setup['division_id'],
        day_of_week='Monday', start_time='11:00', end_time='12:00', subject_id=subject_id,
        faculty_id=setup['teacher']['faculty_id'], room_id=setup['room_id'],
    ), subject_id


_ELECTIVE = dict(
    course_type='Elective', is_elective=1,
    credits=3, theory_credits=3, practical_credits=0, marks=100, theory_marks=100, practical_marks=0,
)


@pytest.fixture
def elective(factory):
    setup = factory.academic()
    year = factory.insert('academic_years', name='2026-27', start_date='2026-06-01', end_date='2027-05-31')
    semester = factory.insert('semesters', academic_year_id=year, semester_number=1, semester_name='Semester I',
                              start_date='2026-06-01', end_date='2026-11-30')
    timetable_id, subject_id = _subject_lecture(factory, setup, **_ELECTIVE)
    chose = factory.user('Student', setup=setup)
    did_not = factory.user('Student', setup=setup)
    factory.insert('student_subject_selections', student_id=chose['student_id'], subject_id=subject_id,
                   semester_id=semester, academic_year_id=year, is_confirmed=1)
    return {
        'setup': setup, 'timetable_id': timetable_id, 'subject_id': subject_id, 'chose': chose,
        'did_not': did_not, 'semester_id': semester, 'academic_year_id': year,
    }


def test_elective_lecture_accepts_a_student_who_chose_it(client, factory, elective):
    login(client, elective['setup']['teacher'])
    assert mark(client, elective['timetable_id'], elective['chose']).status_code == 200
    assert len(saved(factory, elective['timetable_id'])) == 1


def test_elective_lecture_refuses_a_student_who_did_not_choose_it(client, factory, elective):
    login(client, elective['setup']['teacher'])
    assert mark(client, elective['timetable_id'], elective['did_not']).status_code == 400
    assert saved(factory, elective['timetable_id']) == []


def test_elective_lecture_refuses_a_withdrawn_choice(client, factory, elective):
    factory.execute(
        "UPDATE student_subject_selections SET status = 'Withdrawn' WHERE student_id = %s",
        (elective['chose']['student_id'],),
    )
    login(client, elective['setup']['teacher'])
    assert mark(client, elective['timetable_id'], elective['chose']).status_code == 400


def test_elective_lecture_refuses_a_choice_from_another_semester(client, factory, elective):
    other = factory.insert('semesters', academic_year_id=elective['academic_year_id'], semester_number=2,
                           semester_name='Semester II', start_date='2026-12-01', end_date='2027-05-31')
    factory.execute('UPDATE timetable SET semester_id = %s, academic_year_id = %s WHERE id = %s',
                    (other, elective['academic_year_id'], elective['timetable_id']))
    login(client, elective['setup']['teacher'])
    assert mark(client, elective['timetable_id'], elective['chose']).status_code == 400


def test_elective_choice_does_not_cross_divisions(client, factory, elective):
    other_division = factory.insert('divisions', name=f'B{factory._next()}')
    factory.execute('UPDATE students SET division_id = %s WHERE id = %s',
                    (other_division, elective['chose']['student_id']))
    login(client, elective['setup']['teacher'])
    assert mark(client, elective['timetable_id'], elective['chose']).status_code == 400


def test_a_whole_class_elective_takes_choosers_from_every_division(client, factory, elective):
    factory.execute('UPDATE timetable SET division_id = NULL WHERE id = %s', (elective['timetable_id'],))
    other_division = factory.insert('divisions', name=f'B{factory._next()}')
    factory.execute('UPDATE students SET division_id = %s WHERE id = %s',
                    (other_division, elective['chose']['student_id']))
    login(client, elective['setup']['teacher'])
    assert mark(client, elective['timetable_id'], elective['chose']).status_code == 200
    assert mark(client, elective['timetable_id'], elective['did_not']).status_code == 400


def test_an_elective_course_type_without_the_flag_still_needs_a_choice(client, factory, elective):
    factory.execute('UPDATE subjects SET is_elective = 0 WHERE id = %s', (elective['subject_id'],))
    login(client, elective['setup']['teacher'])
    assert mark(client, elective['timetable_id'], elective['did_not']).status_code == 400
    assert mark(client, elective['timetable_id'], elective['chose']).status_code == 200


# Lab batches. The schema has no lab sub-batch tables; timetable.course_batch_id is a
# course intake (admission year), not a lab group. docs/DESIGN_LAB_BATCHES.md proposes the
# tables for timetable v2.

@pytest.fixture
def batch_lab(factory):
    setup = factory.academic()
    ours = factory.insert('course_batches', course_id=setup['course_id'], batch_name='Lab A', start_year=2026, end_year=2029)
    other = factory.insert('course_batches', course_id=setup['course_id'], batch_name='Lab B', start_year=2026, end_year=2029)
    timetable_id, _ = _subject_lecture(
        factory, setup, course_type='Core Practical', theory_practical='Practical',
        credits=2, theory_credits=0, practical_credits=2, marks=50, theory_marks=0, practical_marks=50,
    )
    factory.execute('UPDATE timetable SET course_batch_id = %s WHERE id = %s', (ours, timetable_id))
    inside = factory.user('Student', setup=setup)
    outside = factory.user('Student', setup=setup)
    factory.execute('UPDATE students SET course_batch_id = %s WHERE id = %s', (ours, inside['student_id']))
    factory.execute('UPDATE students SET course_batch_id = %s WHERE id = %s', (other, outside['student_id']))
    return setup, timetable_id, inside, outside


def test_batch_lecture_accepts_a_student_in_the_batch(client, factory, batch_lab):
    setup, timetable_id, inside, _ = batch_lab
    login(client, setup['teacher'])
    assert mark(client, timetable_id, inside).status_code == 200


@pytest.mark.xfail(strict=True, reason=(
    'No lab sub-batch tables exist yet, so a practical takes the whole division. '
    'See docs/DESIGN_LAB_BATCHES.md (timetable v2).'
))
def test_batch_lecture_refuses_a_student_in_another_batch(client, factory, batch_lab):
    setup, timetable_id, _, outside = batch_lab
    login(client, setup['teacher'])
    assert mark(client, timetable_id, outside).status_code == 400
    assert saved(factory, timetable_id) == []
