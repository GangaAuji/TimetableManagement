"""Phase D: NAAC/NBA report datasets on the golden cohort, and the CSV/XLSX/PDF renderers through the export queue."""

import csv
import os

import pytest

import api.web  # noqa: F401  (breaks the services.export_jobs <-> api.web import cycle)
from services import export_jobs
from services.reports_admin import accreditation
from services.reports_admin.renderers import render
from tests.http_helpers import api, login
from tests.integration.test_attendance_calc_live import cohort  # noqa: F401  (fixture)

pytestmark = pytest.mark.live_db

MARCH = {'start_date': '2026-03-01', 'end_date': '2026-03-31'}


def _build(db, kind, **filters):
    cursor = db.cursor(dictionary=True)
    try:
        return accreditation.build(cursor, kind, filters)
    finally:
        cursor.close()


def _cohort_filters(cohort):
    setup = cohort['setup']
    return {'course_id': setup['course_id'], 'class_id': setup['class_id']}


def test_defaulter_list_is_the_students_below_the_threshold_lowest_first(db, cohort):
    rows, fieldnames, labels, meta = _build(db, 'defaulters', threshold=75, **MARCH, **_cohort_filters(cohort))
    names = {cohort['asha']['student_id']: 'asha', cohort['chen']['student_id']: 'chen'}
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, roll_number FROM students WHERE id IN (%s, %s)', tuple(names))
        roll = {row['roll_number']: names[row['id']] for row in cursor.fetchall()}
    finally:
        cursor.close()
    listed = [(roll[row['roll_number']], row['attendance_percentage'], row['shortfall_percent'], row['classes_needed']) for row in rows]
    assert listed == [('chen', 50.0, 25.0, 2), ('asha', 70.0, 5.0, 2)]
    assert fieldnames[:2] == ['roll_number', 'full_name'] and labels == {'shortfall_percent': 'Shortfall %'}
    assert meta['threshold'] == '75%' and meta['defaulters'] == 2 and meta['students_in_cohort'] >= 4


def test_subject_wise_pools_every_student_in_the_subject_roster(db, cohort):
    physics = cohort['subjects']['physics']
    rows, fieldnames, _labels, meta = _build(db, 'subject-wise', subject_id=physics, **MARCH, **_cohort_filters(cohort))
    assert len(rows) == 1
    row = rows[0]
    # Asha (P, P, P, A), Ben (no marks), Chen (P, A from 9 Mar): four presents over three students
    assert row['students'] == 3 and row['present'] == 4 and row['attended'] == 4
    assert row['subject_code'] and row['subject_name']
    assert row['attendance_percentage'] is not None and 'students_below_threshold' in fieldnames
    assert 'threshold' in meta


def test_monthly_register_has_one_column_per_lecture_day(db, cohort):
    physics = cohort['subjects']['physics']
    rows, fieldnames, labels, meta = _build(db, 'monthly-register', month='2026-03', subject_id=physics, **_cohort_filters(cohort))
    day_columns = [name for name in fieldnames if name.startswith('d')]
    assert day_columns == ['d02', 'd05', 'd09', 'd16']  # Thu 12 is a holiday, Thu 19 was cancelled
    assert labels['d05'] == '05 Thu'
    by_id = {}
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, roll_number FROM students WHERE id IN (%s, %s)', (cohort['asha']['student_id'], cohort['chen']['student_id']))
        by_roll = {row['roll_number']: row['id'] for row in cursor.fetchall()}
    finally:
        cursor.close()
    for row in rows:
        if row['roll_number'] in by_roll:
            by_id[by_roll[row['roll_number']]] = row
    asha = by_id[cohort['asha']['student_id']]
    assert (asha['d02'], asha['d05'], asha['d09'], asha['d16'], asha['held'], asha['attended']) == ('P', 'A', 'P', 'P', 4, 3)
    chen = by_id[cohort['chen']['student_id']]
    assert chen.get('d02') is None and chen.get('d05') is None and (chen['d09'], chen['d16']) == ('P', 'A')
    assert meta['month'] == 'March 2026' and meta['lecture_days'] == 4


def test_monthly_register_rejects_a_bad_month(db, cohort):
    with pytest.raises(ValueError):
        _build(db, 'monthly-register', month='March', **_cohort_filters(cohort))


def test_faculty_workload_counts_scheduled_held_cancelled_and_not_marked(db, cohort):
    teacher = cohort['teacher']
    rows, fieldnames, labels, _meta = _build(db, 'faculty-workload', faculty_id=teacher['id'], **MARCH)
    assert len(rows) == 1
    row = rows[0]
    assert (row['scheduled'], row['held'], row['cancelled'], row['not_marked'], row['as_proxy']) == (14, 12, 1, 1, 0)
    assert row['weekly_slots'] == 5 and row['weekly_hours'] == 5.0
    assert row['held_percent'] == round(12 * 100.0 / 13, 2)
    assert labels['held_percent'] == 'Held %' and fieldnames[0] == 'employee_id'


def test_build_rejects_unknown_types(db):
    with pytest.raises(ValueError):
        _build(db, 'nope')


# Renderers

def test_render_writes_csv_xlsx_and_pdf(tmp_path, db, cohort):
    rows, fieldnames, labels, meta = _build(db, 'defaulters', threshold=75, **MARCH, **_cohort_filters(cohort))
    for fmt in ('csv', 'xlsx', 'pdf'):
        target = tmp_path / f'defaulters.{fmt}'
        assert render(str(target), fmt, fieldnames, rows, title='Defaulter list', meta=meta, labels=labels) == 2
        assert target.stat().st_size > 0

    with open(tmp_path / 'defaulters.csv', newline='', encoding='utf-8') as handle:
        header = next(csv.reader(handle))
    assert header[0] == 'roll_number' and 'Shortfall %' in header  # raw names, explicit labels only

    from openpyxl import load_workbook
    sheet = load_workbook(tmp_path / 'defaulters.xlsx', read_only=True).active
    cells = [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
    assert cells[0][0] == 'Defaulter list'
    header_row = next(row for row in cells if row[0] == 'Roll number')
    assert 'Shortfall %' in header_row and len(cells) >= cells.index(header_row) + 3

    with open(tmp_path / 'defaulters.pdf', 'rb') as handle:
        assert handle.read(5) == b'%PDF-'


def test_render_rejects_unknown_formats(tmp_path):
    with pytest.raises(ValueError):
        render(str(tmp_path / 'x.doc'), 'doc', ['a'], [])


# Through the API and the export queue

def _queue(client, payload):
    response = api(client, 'POST', '/api/reports', json=payload)
    return response.status_code, response.get_json()


def test_reports_api_offers_the_accreditation_types_and_formats(client, factory):
    owner = factory.user('Super Admin')
    login(client, owner)
    data = api(client, 'GET', '/api/reports').get_json()['data']
    ids = [item['id'] for item in data['types']]
    assert {'defaulters', 'subject-wise', 'monthly-register', 'faculty-workload'} <= set(ids)
    assert [item['id'] for item in data['options']['formats']] == ['csv', 'xlsx', 'pdf']
    assert 'subjects' in data['options'] and 'departments' in data['options']


def test_reports_api_validates_the_new_filters(client, factory):
    owner = factory.user('Super Admin')
    login(client, owner)
    assert _queue(client, {'report_type': 'defaulters', 'format': 'docx'})[0] == 400
    assert _queue(client, {'report_type': 'defaulters', 'threshold': '150'})[0] == 400
    assert _queue(client, {'report_type': 'monthly-register', 'month': '2026-3', 'course_id': 1, 'class_id': 1})[0] == 400
    assert _queue(client, {'report_type': 'monthly-register', 'month': '2026-03'})[0] == 400  # cohort required


def test_queued_accreditation_report_is_rendered_in_the_requested_format(app, client, factory, cohort):
    owner = factory.user('Super Admin')
    login(client, owner)
    filters = {'report_type': 'defaulters', 'format': 'xlsx', 'threshold': 75, **MARCH, **_cohort_filters(cohort)}
    status, body = _queue(client, filters)
    assert status == 200, body
    job_id = body['data']['id']
    stored = factory.query('SELECT filters_json FROM processed_reports WHERE id = %s', (job_id,))[0]['filters_json']
    assert '"format": "xlsx"' in stored

    with app.app_context():
        assert export_jobs._claim_next() == job_id
        export_jobs._process(job_id)
    row = factory.query('SELECT status, row_count, file_name, file_path FROM processed_reports WHERE id = %s', (job_id,))[0]
    assert row['status'] == 'completed' and row['row_count'] == 2
    assert row['file_name'].startswith('defaulters_') and row['file_name'].endswith('.xlsx')
    assert os.path.isfile(row['file_path'])
    try:
        response = client.get(f'/api/reports/{job_id}/download')
        assert response.status_code == 200
        assert response.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        assert response.data[:2] == b'PK'
    finally:
        response.close()
        os.remove(row['file_path'])


def test_queued_pdf_report_downloads_as_pdf(app, client, factory, cohort):
    owner = factory.user('Super Admin')
    login(client, owner)
    status, body = _queue(client, {'report_type': 'faculty-workload', 'format': 'pdf', 'faculty_id': cohort['teacher']['id'], **MARCH})
    assert status == 200, body
    job_id = body['data']['id']
    with app.app_context():
        assert export_jobs._claim_next() == job_id
        export_jobs._process(job_id)
    row = factory.query('SELECT status, row_count, file_name, file_path FROM processed_reports WHERE id = %s', (job_id,))[0]
    assert row['status'] == 'completed' and row['row_count'] == 1 and row['file_name'].endswith('.pdf')
    try:
        response = client.get(f'/api/reports/{job_id}/download')
        assert response.status_code == 200 and response.mimetype == 'application/pdf'
        assert response.data[:5] == b'%PDF-'
    finally:
        response.close()
        os.remove(row['file_path'])


def test_a_report_without_a_format_defaults_to_csv(app, client, factory, cohort):
    owner = factory.user('Super Admin')
    login(client, owner)
    status, body = _queue(client, {'report_type': 'attendance', **MARCH, **_cohort_filters(cohort)})
    assert status == 200, body
    job_id = body['data']['id']
    with app.app_context():
        assert export_jobs._claim_next() == job_id
        export_jobs._process(job_id)
    row = factory.query('SELECT status, file_name, file_path FROM processed_reports WHERE id = %s', (job_id,))[0]
    assert row['status'] == 'completed' and row['file_name'].endswith('.csv')
    try:
        with open(row['file_path'], newline='', encoding='utf-8') as handle:
            header = next(csv.reader(handle))
        assert header[0] == 'student_id'
    finally:
        os.remove(row['file_path'])
