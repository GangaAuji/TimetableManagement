"""Worker claims: locked_by and heartbeat_at on claim, stale-only requeue, one pass of `flask workers run --once`."""

import json

import pytest

import api.web  # noqa: F401  (the API package imports services.export_jobs, which imports api.web.security back)
from services import export_jobs, timetable_jobs
from services.job_claims import WORKER_ID, claim_next, requeue_stale

pytestmark = pytest.mark.live_db


def _queue_export(factory, admin):
    return factory.insert(
        'processed_reports',
        report_type='users-export', status='queued', filters_json='{}', row_count=0, file_name='', file_path='',
        created_by=admin['id'], progress=0,
    )


def _row(factory, table, job_id):
    return factory.query(f'SELECT status, progress, locked_by, heartbeat_at FROM `{table}` WHERE id = %s', (job_id,))[0]


def test_claim_records_the_worker_and_a_heartbeat(app, factory):
    admin = factory.user('Super Admin')
    job_id = _queue_export(factory, admin)
    with app.app_context():
        assert export_jobs._claim_next() == job_id
        assert export_jobs._claim_next() is None
    row = _row(factory, 'processed_reports', job_id)
    assert row['status'] == 'running' and row['locked_by'] == WORKER_ID and row['heartbeat_at'] is not None

    before = row['heartbeat_at']
    factory.execute("UPDATE processed_reports SET heartbeat_at = heartbeat_at - INTERVAL 10 SECOND WHERE id = %s", (job_id,))
    with app.app_context():
        export_jobs._progress(job_id, 50)
    after = _row(factory, 'processed_reports', job_id)
    assert after['progress'] == 50 and after['heartbeat_at'] >= before


def test_only_stale_claims_are_requeued(app, factory):
    admin = factory.user('Super Admin')
    fresh = _queue_export(factory, admin)
    stale = _queue_export(factory, admin)
    with app.app_context():
        assert export_jobs._claim_next() == fresh
        assert export_jobs._claim_next() == stale
    factory.execute(
        "UPDATE processed_reports SET heartbeat_at = UTC_TIMESTAMP() - INTERVAL 2 HOUR, locked_by = 'host:1:dead' WHERE id = %s",
        (stale,),
    )
    with app.app_context():
        assert export_jobs._requeue_interrupted() == 1
    assert _row(factory, 'processed_reports', fresh)['status'] == 'running'
    requeued = _row(factory, 'processed_reports', stale)
    assert requeued['status'] == 'queued' and requeued['locked_by'] is None and requeued['heartbeat_at'] is None
    assert requeued['progress'] == 0

    # A running row with no heartbeat at all (written before 0009) counts as stale.
    factory.execute("UPDATE processed_reports SET heartbeat_at = NULL WHERE id = %s", (fresh,))
    with app.app_context():
        assert export_jobs._requeue_interrupted() == 1


def test_timetable_claims_use_the_same_rules(app, factory):
    admin = factory.user('Super Admin')
    job_id = factory.insert(
        'timetable_jobs',
        status='queued', progress=0, total_count=1, done_count=0, assigned_count=0, unassigned_count=0,
        failed_count=0, settings_json=json.dumps({'targets': []}), message='Queued', created_by=admin['id'],
    )
    with app.app_context():
        assert timetable_jobs._claim_next() == job_id
        timetable_jobs._mark(job_id, 0, 4, 0, 0, 0, 'Scheduling')
    row = _row(factory, 'timetable_jobs', job_id)
    assert row['locked_by'] == WORKER_ID and row['heartbeat_at'] is not None
    with app.app_context():
        assert timetable_jobs._requeue_interrupted() == 0
        assert timetable_jobs._requeue_interrupted(seconds=0) == 1
    assert _row(factory, 'timetable_jobs', job_id)['status'] == 'queued'


def test_claim_helpers_work_on_a_plain_cursor(db):
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("DELETE FROM processed_reports")
        assert claim_next(cursor, 'processed_reports') is None
        assert requeue_stale(cursor, 'processed_reports', 'progress = 0') == 0
        db.commit()
    finally:
        cursor.close()


def test_workers_run_once_drains_the_queues_and_writes_a_heartbeat(make_app, factory, tmp_path):
    admin = factory.user('Super Admin')
    heartbeat = tmp_path / 'workers.heartbeat'
    app = make_app(WORKERS_HEARTBEAT_FILE=str(heartbeat), ATTENDANCE_CLOSE_DAY_HOUR=-1)
    job_id = factory.insert(
        'timetable_jobs',
        status='queued', progress=0, total_count=0, done_count=0, assigned_count=0, unassigned_count=0,
        failed_count=0, settings_json=json.dumps({}), message='Queued', created_by=admin['id'],
    )
    result = app.test_cli_runner().invoke(args=['workers', 'run', '--once'])
    assert result.exit_code == 0, result.output
    counts = json.loads(result.output.strip().splitlines()[-1])
    assert counts['timetables'] >= 1
    assert _row(factory, 'timetable_jobs', job_id)['status'] == 'failed'  # no targets: finished as failed, not stuck
    beat = json.loads(heartbeat.read_text(encoding='utf-8'))
    assert beat['mode'] == 'once' and beat['worker_id'] == WORKER_ID

    status = app.test_cli_runner().invoke(args=['workers', 'status'])
    assert status.exit_code == 0, status.output
    assert 'Workers healthy.' in status.output

    health = app.test_client().get('/health').get_json()
    assert health['checks']['workers']['worker_id'] == WORKER_ID
    assert isinstance(health['checks']['disk_free_mb'], int)

    app.config['REQUIRE_WORKERS'] = True
    app.config['WORKERS_STALE_SECONDS'] = -1
    response = app.test_client().get('/health')
    assert response.status_code == 503
    assert 'heartbeat' in response.get_json()['reason']
