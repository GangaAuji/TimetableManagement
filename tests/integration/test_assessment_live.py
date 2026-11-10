"""Internal assessment on the *_test database.

With the capability off the scheme, the student tab and the public marks stay hidden.
With it on, a lock is what lets the student see a mark, and attainment matches the worked example.
"""

import os
import tempfile

import pytest

import api.web  # noqa: F401  (breaks the services.export_jobs <-> api.web import cycle)
from services import api_keys
from services.reports_admin.accreditation import build
from services.reports_admin.renderers import render
from tests.http_helpers import api, login

pytestmark = pytest.mark.live_db


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:800]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:800]
    return response.get_json()['error']['code']


def _key(app, db):
    cursor = db.cursor(dictionary=True)
    try:
        with app.app_context():
            plaintext = api_keys.create_key(cursor, name='assessment internals', scopes=['catalog:read'], created_by=None)[1]
        db.commit()
        return plaintext
    finally:
        cursor.close()


def test_assessment_off_hides_marks_and_on_locks_them_before_students_see_them(client, app, db, factory):
    setup = factory.academic()
    first = factory.user('Student', setup=setup)
    second = factory.user('Student', setup=setup)
    factory.insert(
        'faculty_allocations', faculty_id=setup['teacher']['id'], subject_id=setup['subject_id'],
        class_id=setup['class_id'], division_id=setup['division_id'], is_primary=1,
    )
    login(client, factory.user('Super Admin'))
    assert _error(api(client, 'GET', '/api/assessments'), 404) == 'capability_off'
    assert 'co-attainment' not in {item['id'] for item in _ok(api(client, 'GET', '/api/reports'))['types']}
    assert _error(api(client, 'POST', '/api/reports', json={'report_type': 'co-attainment', 'format': 'csv'}), 404) == 'capability_off'

    factory.capability('assessments', True)
    _ok(api(client, 'PUT', f"/api/assessments/subjects/{setup['subject_id']}/outcomes", json={'outcomes': [
        {'code': 'CO1', 'statement': 'Solve problems in one dimension.'},
        {'code': 'CO2', 'statement': 'Apply the work-energy relation.'},
    ]}))
    _ok(api(client, 'PUT', f"/api/assessments/courses/{setup['course_id']}/outcomes", json={'outcomes': [
        {'code': 'PO1', 'statement': 'Engineering knowledge.'},
    ]}))
    saved = _ok(api(client, 'PUT', f"/api/assessments/subjects/{setup['subject_id']}/components", json={'components': [
        {'name': 'IA 1', 'max_marks': 20, 'weight': 20, 'kind': 'IA', 'outcome_codes': ['CO1']},
        {'name': 'Assignment', 'max_marks': 10, 'weight': 10, 'kind': 'assignment', 'outcome_codes': ['CO1', 'CO2']},
        {'name': 'Practical', 'max_marks': 20, 'weight': 20, 'kind': 'practical', 'outcome_codes': ['CO2']},
    ]}))
    components = {row['name']: row for row in saved['components']}
    _ok(api(client, 'PUT', f"/api/assessments/subjects/{setup['subject_id']}/map", json={'links': [
        {'co_code': 'CO1', 'po_code': 'PO1', 'level': 3},
        {'co_code': 'CO2', 'po_code': 'PO1', 'level': 1},
    ]}))
    ia = components['IA 1']['id']
    marks = {
        first['student_id']: (16, 8, 10),
        second['student_id']: (10, 6, 16),
    }
    for name, index in (('IA 1', 0), ('Assignment', 1), ('Practical', 2)):
        _ok(api(client, 'PUT', f"/api/assessments/components/{components[name]['id']}/marks", json={'marks': [
            {'student_id': student_id, 'marks': values[index]} for student_id, values in marks.items()
        ]}))

    login(client, first)
    assert _ok(api(client, 'GET', '/api/portal/student/assessments'))['subjects'] == []
    assert _error(api(client, 'GET', '/api/assessments'), 403) == 'forbidden'

    login(client, factory.user('Super Admin'))
    _ok(api(client, 'POST', f'/api/assessments/components/{ia}/lock'))
    assert _error(api(client, 'PUT', f'/api/assessments/components/{ia}/marks', json={'marks': [
        {'student_id': first['student_id'], 'marks': 1},
    ]}), 409) == 'assessment_locked'

    login(client, first)
    visible = _ok(api(client, 'GET', '/api/portal/student/assessments'))['subjects']
    assert len(visible) == 1 and visible[0]['components'] == [{'name': 'IA 1', 'kind': 'IA', 'max_marks': 20.0, 'marks': 16.0}]

    login(client, setup['teacher'])
    mine = _ok(api(client, 'GET', '/api/portal/teacher/assessments'))['subjects']
    assert any(row['id'] == setup['subject_id'] for row in mine)
    assert _error(api(client, 'PUT', f'/api/assessments/components/{ia}/marks', json={'marks': [
        {'student_id': first['student_id'], 'marks': 18},
    ]}), 409) == 'assessment_locked'
    assignment = components['Assignment']['id']
    _ok(api(client, 'PUT', f'/api/assessments/components/{assignment}/marks', json={'marks': [
        {'student_id': first['student_id'], 'marks': 8},
        {'student_id': second['student_id'], 'marks': 6},
    ]}))

    login(client, factory.user('Super Admin'))
    page = _ok(api(client, 'GET', f"/api/assessments?subject_id={setup['subject_id']}"))
    by_code = {row['code']: row for row in page['attainment']['outcomes']}
    assert by_code['CO1']['percent'] == pytest.approx(66.67) and by_code['CO1']['level'] == 1
    assert by_code['CO2']['percent'] == pytest.approx(66.67) and by_code['CO2']['level'] == 3
    assert page['attainment']['program_outcomes'][0]['code'] == 'PO1'
    assert page['attainment']['program_outcomes'][0]['percent'] == pytest.approx(66.67)
    assert page['attainment']['program_outcomes'][0]['level'] == 2

    imported = _ok(api(client, 'POST', f"/api/assessments/components/{assignment}/import", json={
        'csv': f"roll_number,marks\n{factory.query('SELECT roll_number FROM students WHERE id = %s', (first['student_id'],))[0]['roll_number']},9\nNO-SUCH,1\n",
    }))
    assert imported['import']['saved'] == 1 and imported['import']['unknown'] == ['NO-SUCH']

    cursor = db.cursor(dictionary=True)
    try:
        with app.app_context():
            rows, fields, _labels, meta = build(cursor, 'co-attainment', {'subject_id': setup['subject_id']})
    finally:
        cursor.close()
    assert fields[0] == 'outcome_kind' and meta['rows'] == 3
    assert {row['outcome_code'] for row in rows} == {'CO1', 'CO2', 'PO1'}
    handle, path = tempfile.mkstemp(suffix='.csv')
    os.close(handle)
    try:
        render(path, 'csv', fields, rows, title='CO and PO attainment')
        with open(path, encoding='utf-8') as stored:
            exported = stored.read()
    finally:
        os.remove(path)
    assert 'CO1' in exported and 'PO1' in exported

    key = _key(app, db)
    public = client.get(f"/api/v1/subjects/{setup['subject_id']}/internals", headers={'Authorization': f'Bearer {key}'})
    assert public.status_code == 200, public.get_data(as_text=True)[:500]
    names = [row['name'] for row in public.get_json()['data']['components']]
    assert names == ['IA 1']

    factory.capability('assessments', False)
    login(client, factory.user('Super Admin'))
    assert _error(api(client, 'GET', '/api/assessments'), 404) == 'capability_off'
    hidden = client.get(f"/api/v1/subjects/{setup['subject_id']}/internals", headers={'Authorization': f'Bearer {key}'})
    assert hidden.status_code == 404
