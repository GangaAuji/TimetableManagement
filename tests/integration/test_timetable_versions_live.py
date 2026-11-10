"""Timetable versions (Phase J2) on the *_test database: a generation job writes a draft and leaves the
live timetable alone, compare shows what would change, publishing flips the rows in one go and archives
the old ones, rollback re-publishes an archived version (manual slots travel with it), a multi-class
draft stays clash-free, and with the capability off generation writes live rows exactly as before."""

import json

from tests.http_helpers import api, login


def _ok(response, status=200):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['data']


def _error(response, status):
    assert response.status_code == status, response.get_data(as_text=True)[:400]
    return response.get_json()['error']['code']


def _cohort(setup):
    return {'course_id': setup['course_id'], 'class_id': setup['class_id'], 'division_id': setup['division_id']}


def _teachable(factory, setup, lectures=2, teacher=None):
    factory.execute('UPDATE subjects SET lectures_per_week = %s WHERE id = %s', (lectures, setup['subject_id']))
    factory.insert('faculty_allocations', faculty_id=(teacher or setup['teacher'])['id'], subject_id=setup['subject_id'],
                   class_id=setup['class_id'], division_id=setup['division_id'], is_primary=1)


def _run_job(app, factory, user, targets, **overrides):
    """Queue one generation and run the worker once, the way the background thread would."""
    from services import timetable_jobs

    settings = {'week_start_date': '2026-11-09', 'day_start': '09:00', 'day_end': '12:00', 'lecture_minutes': 60,
                'working_days': ['Monday', 'Tuesday'], 'solver': 'greedy', 'targets': targets, **overrides}
    with app.app_context():
        job_id, _attached = timetable_jobs.enqueue_job(settings, user['id'])
        assert timetable_jobs._claim_next() == job_id
        timetable_jobs._process(job_id)
        record = timetable_jobs.load_job(job_id)
    assert record['status'] == 'completed', record
    summary = json.loads(record['summary_json'] or '{}')
    return record, summary.get('version_id')


def _live(factory, setup):
    return factory.query(
        'SELECT id, version_id, day_of_week, start_time FROM timetable WHERE course_id = %s AND class_id = %s AND division_id = %s '
        'AND COALESCE(is_active, 1) = 1 ORDER BY day_of_week, start_time', (setup['course_id'], setup['class_id'], setup['division_id']),
    )


def test_generation_writes_a_draft_and_publishing_flips_it(app, client, factory):
    setup = factory.academic()
    _teachable(factory, setup)
    admin = factory.user('Admin', setup=setup)

    record, version_id = _run_job(app, factory, admin, [{**_cohort(setup), 'label': 'one'}], label='Autumn draft')
    assert version_id, record
    assert 'draft' in record['message']
    assert record['assigned_count'] == 2

    # The live timetable is exactly what it was: the seeded Monday lecture, no version.
    assert [row['id'] for row in _live(factory, setup)] == [setup['timetable_id']]
    drafts = factory.query('SELECT is_active FROM timetable WHERE version_id = %s', (version_id,))
    assert len(drafts) == 2 and all(row['is_active'] == 0 for row in drafts)
    [version] = factory.query('SELECT status, label, solver, job_id, parent_version_id FROM timetable_versions WHERE id = %s', (version_id,))
    assert version == {'status': 'draft', 'label': 'Autumn draft', 'solver': 'greedy', 'job_id': record['id'], 'parent_version_id': None}

    login(client, admin)
    listing = _ok(api(client, 'GET', '/api/timetable/versions'))
    assert listing['can_publish'] is True and listing['keep_drafts'] == 10
    [item] = [v for v in listing['versions'] if v['id'] == version_id]
    assert item['status'] == 'draft' and item['slot_count'] == 2 and item['score']['assigned'] == 2
    assert len(item['cohorts']) == 1 and item['cohorts'][0]['division_id'] == setup['division_id']

    job = _ok(api(client, 'GET', f"/api/timetable/jobs/{record['id']}"))
    assert job['version_id'] == version_id

    one = _ok(api(client, 'GET', f'/api/timetable/versions/{version_id}'))
    assert len(one['slots']) == 2 and one['version']['label'] == 'Autumn draft'

    compared = _ok(api(client, 'GET', f'/api/timetable/versions/{version_id}/diff/live'))
    assert compared['other'] is None and compared['can_publish'] is True
    [cohort] = compared['cohorts']
    assert len(cohort['before']) == 1 and len(cohort['after']) == 2
    assert sum(compared['totals'].values()) >= 2

    published = _ok(api(client, 'POST', f'/api/timetable/versions/{version_id}/publish'))
    assert published['published'] is True and published['cohorts'] == 1 and published['slots'] == 2 and published['skipped'] == []
    assert published['version']['status'] == 'published' and published['version']['published_by'] == admin['username']

    live = _live(factory, setup)
    assert len(live) == 2 and all(row['version_id'] == version_id for row in live)
    [old] = factory.query('SELECT is_active FROM timetable WHERE id = %s', (setup['timetable_id'],))
    assert old['is_active'] == 0
    assert factory.query(
        'SELECT COUNT(*) AS n FROM timetable_history WHERE course_id = %s AND class_id = %s AND division_id = %s',
        (setup['course_id'], setup['class_id'], setup['division_id']),
    ) == [{'n': 1}]
    assert factory.query("SELECT COUNT(*) AS n FROM user_activity_log WHERE activity_type = 'timetable_version_published'") == [{'n': 1}]

    # Publishing twice is refused; the live version cannot be discarded.
    assert _error(api(client, 'POST', f'/api/timetable/versions/{version_id}/publish'), 409) == 'version_already_published'
    assert _error(api(client, 'DELETE', f'/api/timetable/versions/{version_id}'), 409) == 'version_published'


def test_rollback_republishes_an_archived_version_and_manual_slots_follow_it(app, client, factory):
    setup = factory.academic()
    _teachable(factory, setup)
    admin = factory.user('Admin', setup=setup)
    login(client, admin)

    _record, first = _run_job(app, factory, admin, [_cohort(setup)])
    _ok(api(client, 'POST', f'/api/timetable/versions/{first}/publish'))
    _record, second = _run_job(app, factory, admin, [_cohort(setup)], working_days=['Wednesday', 'Thursday'])
    [row] = factory.query('SELECT parent_version_id FROM timetable_versions WHERE id = %s', (second,))
    assert row['parent_version_id'] == first

    compared = _ok(api(client, 'GET', f'/api/timetable/versions/{second}/diff/{first}'))
    assert compared['other']['id'] == first
    assert compared['totals'].get('moved', 0) + compared['totals'].get('added', 0) == 2, compared['totals']
    [teacher] = factory.query('SELECT name FROM faculty WHERE user_id = %s', (setup['teacher']['id'],))
    assert compared['faculty'] and compared['faculty'][0]['faculty'] == teacher['name']

    _ok(api(client, 'POST', f'/api/timetable/versions/{second}/publish'))
    statuses = {r['id']: r['status'] for r in factory.query('SELECT id, status FROM timetable_versions WHERE id IN (%s, %s)', (first, second))}
    assert statuses == {first: 'archived', second: 'published'}
    assert all(row['version_id'] == second for row in _live(factory, setup))

    # A manual slot added while the second version is live belongs to it.
    added = _ok(api(client, 'POST', '/api/timetable/slots', json={
        **_cohort(setup), 'subject_id': setup['subject_id'], 'faculty_id': setup['teacher']['id'],
        'day': 'Friday', 'start_time': '09:00', 'end_time': '10:00',
    }))
    [manual] = factory.query('SELECT version_id, is_active FROM timetable WHERE id = %s', (added['id'],))
    assert manual == {'version_id': second, 'is_active': 1}

    # Rollback: publish the archived version again. Its two rows come back; the second version's three go.
    rolled = _ok(api(client, 'POST', f'/api/timetable/versions/{first}/publish'))
    assert rolled['version']['status'] == 'published'
    live = _live(factory, setup)
    assert len(live) == 2 and all(row['version_id'] == first for row in live)
    assert factory.query('SELECT COUNT(*) AS n FROM timetable WHERE version_id = %s AND COALESCE(is_active, 1) = 0', (second,)) == [{'n': 3}]
    assert factory.query('SELECT status FROM timetable_versions WHERE id = %s', (second,)) == [{'status': 'archived'}]

    # The archived version can be renamed and then discarded, taking its inactive rows with it.
    assert _ok(api(client, 'PUT', f'/api/timetable/versions/{second}', json={'label': 'Rejected'}))['label'] == 'Rejected'
    assert _error(api(client, 'PUT', f'/api/timetable/versions/{second}', json={'label': ''}), 400) == 'label_invalid'
    assert _ok(api(client, 'DELETE', f'/api/timetable/versions/{second}'))['discarded'] is True
    assert factory.query('SELECT COUNT(*) AS n FROM timetable WHERE version_id = %s', (second,)) == [{'n': 0}]
    assert factory.query('SELECT COUNT(*) AS n FROM timetable_versions WHERE id = %s', (second,)) == [{'n': 0}]
    assert _error(api(client, 'GET', f'/api/timetable/versions/{second}'), 404) == 'version_not_found'


def test_multi_class_draft_sees_its_sibling_rows_so_publishing_cannot_clash(app, factory):
    first = factory.academic()
    second = factory.academic()
    _teachable(factory, first, lectures=3)
    _teachable(factory, second, lectures=3, teacher=first['teacher'])   # one teacher, six hours, six cells
    admin = factory.user('Admin', setup=first)

    _record, version_id = _run_job(app, factory, admin, [{**_cohort(first), 'label': 'first'}, {**_cohort(second), 'label': 'second'}])
    assert version_id
    assert factory.query('SELECT COUNT(*) AS n FROM timetable WHERE version_id = %s', (version_id,)) == [{'n': 6}]
    clashes = factory.query(
        'SELECT day_of_week, start_time, COUNT(*) AS n FROM timetable WHERE version_id = %s AND faculty_id = %s '
        'GROUP BY day_of_week, start_time HAVING n > 1', (version_id, first['teacher']['id']),
    )
    assert clashes == [], 'the second cohort saw the first cohort\'s draft rows as busy'
    cohorts = factory.query('SELECT course_id FROM timetable_version_cohorts WHERE version_id = %s ORDER BY course_id', (version_id,))
    assert [c['course_id'] for c in cohorts] == sorted([first['course_id'], second['course_id']])


def test_capability_off_generation_writes_live_rows_as_before(app, client, factory):
    factory.capability('timetable_versions', False)
    setup = factory.academic()
    _teachable(factory, setup)
    admin = factory.user('Admin', setup=setup)

    record, version_id = _run_job(app, factory, admin, [_cohort(setup)])
    assert version_id is None and 'draft' not in record['message']
    live = _live(factory, setup)
    assert len(live) == 2 and all(row['version_id'] is None for row in live)
    assert factory.query('SELECT COUNT(*) AS n FROM timetable_versions') == [{'n': 0}]

    login(client, admin)
    assert _error(api(client, 'GET', '/api/timetable/versions'), 404) == 'capability_off'


def test_versions_need_permission_and_stay_within_the_institution(app, client, factory):
    setup = factory.academic()
    _teachable(factory, setup)
    admin = factory.user('Admin', setup=setup)
    _record, version_id = _run_job(app, factory, admin, [_cohort(setup)])

    login(client, factory.user('Student', setup=setup))
    assert _error(api(client, 'GET', '/api/timetable/versions'), 403) == 'forbidden'
    client.get('/logout')

    college_b = factory.institution('Engineering College', code='ENGG')
    admin_b = factory.user('Admin')
    factory.membership(admin_b, college_b)
    login(client, admin_b)
    assert _ok(api(client, 'GET', '/api/timetable/versions'))['versions'] == []
    assert _error(api(client, 'GET', f'/api/timetable/versions/{version_id}'), 403) == 'version_not_owned'
    assert _error(api(client, 'POST', f'/api/timetable/versions/{version_id}/publish'), 403) == 'version_not_owned'
    assert factory.query('SELECT status FROM timetable_versions WHERE id = %s', (version_id,)) == [{'status': 'draft'}]
