"""Queued timetable generation. The request only stores the job; one worker runs each class in order."""

import json
import threading
import time

from flask import current_app

from api.web.security import safe_count, safe_text
from extensions import get_db_connection

_MAX_CLASSES = 1000
_guard = threading.Lock()
_started = False


def ensure_worker(app):
    """Start the single generation worker for this process."""
    global _started
    with _guard:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, args=(app,), name='timetable-queue', daemon=True).start()


def enqueue_job(settings, user_id):
    """Store one generation job. A second job waits until the first finishes."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_table(cursor)
        cursor.execute(
            """
            SELECT id FROM timetable_jobs
            WHERE status IN ('queued', 'running')
            ORDER BY id ASC
            LIMIT 1
            """
        )
        existing = cursor.fetchone()
        if existing:
            connection.commit()
            return existing['id'], True
        cursor.execute(
            """
            INSERT INTO timetable_jobs (
                status, progress, total_count, done_count, assigned_count, unassigned_count,
                failed_count, settings_json, message, created_by
            ) VALUES ('queued', 0, %s, 0, 0, 0, 0, %s, %s, %s)
            """,
            (
                len(settings['targets']),
                json.dumps(settings),
                'Queued',
                user_id,
            ),
        )
        job_id = cursor.lastrowid
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
    ensure_worker(current_app._get_current_object())
    return job_id, False


def load_job(job_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        _ensure_table(cursor)
        connection.commit()
        cursor.execute(
            """
            SELECT id, status, progress, total_count, done_count, assigned_count,
                   unassigned_count, failed_count, message, summary_json
            FROM timetable_jobs
            WHERE id = %s
            """,
            (job_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        connection.close()


def allocated_targets(course_id=None):
    """Return class groups that already have a faculty allocation, oldest name first."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        clause = ''
        params = []
        if course_id:
            clause = ' AND s.course_id = %s'
            params.append(course_id)
        cursor.execute(
            f"""
            SELECT DISTINCT c.id AS course_id, c.name AS course_name,
                   cl.id AS class_id, cl.name AS class_name,
                   d.id AS division_id, d.name AS division_name
            FROM faculty_allocations fa
            JOIN subjects s ON s.id = fa.subject_id
            JOIN courses c ON c.id = s.course_id
            JOIN classes cl ON cl.id = fa.class_id
            JOIN divisions d ON d.id = fa.division_id
            WHERE fa.class_id IS NOT NULL AND fa.division_id IS NOT NULL
            {clause}
            ORDER BY c.name, cl.name, d.name
            LIMIT %s
            """,
            tuple(params) + (_MAX_CLASSES + 1,),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()
    overflow = len(rows) > _MAX_CLASSES
    targets = []
    for row in rows[:_MAX_CLASSES]:
        course = safe_text(row.get('course_name'), 100)
        class_name = safe_text(row.get('class_name'), 100)
        division = safe_text(row.get('division_name'), 100)
        targets.append({
            'course_id': safe_count(row.get('course_id')),
            'class_id': safe_count(row.get('class_id')),
            'division_id': safe_count(row.get('division_id')),
            'label': safe_text(f'{course} · {class_name} {division}', 180),
        })
    return [item for item in targets if item['course_id'] and item['class_id'] and item['division_id']], overflow


_jobs_table_ready = False


def _ensure_table(cursor):
    global _jobs_table_ready
    if _jobs_table_ready:
        return
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS timetable_jobs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            progress TINYINT UNSIGNED NOT NULL DEFAULT 0,
            total_count INT NOT NULL DEFAULT 0,
            done_count INT NOT NULL DEFAULT 0,
            assigned_count INT NOT NULL DEFAULT 0,
            unassigned_count INT NOT NULL DEFAULT 0,
            failed_count INT NOT NULL DEFAULT 0,
            settings_json MEDIUMTEXT NOT NULL,
            summary_json MEDIUMTEXT NULL,
            message VARCHAR(300) NULL,
            created_by INT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP NULL DEFAULT NULL,
            INDEX idx_timetable_jobs_status (status),
            INDEX idx_timetable_jobs_queue (status, id),
            INDEX idx_timetable_jobs_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _jobs_table_ready = True


def _loop(app):
    try:
        with app.app_context():
            _requeue_interrupted()
    except Exception:
        app.logger.exception('Timetable queue could not recover an interrupted job')
    while True:
        job_id = None
        try:
            with app.app_context():
                job_id = _claim_next()
                if job_id:
                    _process(job_id)
        except Exception:
            app.logger.exception('Timetable queue worker failed')
            job_id = None
        if not job_id:
            time.sleep(1.5)


def _requeue_interrupted():
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        _ensure_table(cursor)
        cursor.execute(
            "UPDATE timetable_jobs SET status = 'queued', progress = 0, done_count = 0, message = 'Queued' WHERE status = 'running'"
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def _claim_next():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id FROM timetable_jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            connection.rollback()
            return None
        job_id = row['id']
        cursor.execute(
            "UPDATE timetable_jobs SET status = 'running', progress = 1 WHERE id = %s AND status = 'queued'",
            (job_id,),
        )
        won = cursor.rowcount == 1
        connection.commit()
        return job_id if won else None
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def _process(job_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute('SELECT id, settings_json, created_by FROM timetable_jobs WHERE id = %s', (job_id,))
        job = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()
    if not job:
        return
    try:
        settings = json.loads(job['settings_json'] or '{}')
    except ValueError:
        settings = {}
    targets = settings.get('targets') if isinstance(settings, dict) else None
    if not isinstance(targets, list) or not targets:
        _finish(job_id, 'failed', 0, 0, 0, 0, 'The generation could not be started.', None)
        return
    from services.timetable.generator import generate_timetable_for_class

    assigned = 0
    unassigned = 0
    failed = 0
    summary = None
    failures = []
    total = len(targets)
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            failed += 1
            _mark(job_id, index + 1, total, assigned, unassigned, failed, 'A class was skipped.')
            continue
        label = safe_text(target.get('label') or 'Class', 180)
        _mark(job_id, index, total, assigned, unassigned, failed, f'Scheduling {label} ({index + 1} of {total})')
        try:
            result = generate_timetable_for_class(
                target.get('course_id'),
                target.get('class_id'),
                target.get('division_id'),
                week_start_date=settings.get('week_start_date'),
                day_start=settings.get('day_start') or '09:00',
                day_end=settings.get('day_end') or '15:00',
                lecture_minutes=settings.get('lecture_minutes') or 45,
                break_start=settings.get('break_start') or None,
                break_duration=settings.get('break_duration') or 0,
                working_days=settings.get('working_days'),
                preview_only=False,
                candidate_count=7,
                created_by=job.get('created_by'),
            )
        except Exception:
            current_app.logger.exception('Timetable generation failed for one class')
            failed += 1
            _remember_failure(failures, label, 'That class could not be generated.')
            continue
        if not isinstance(result, dict) or result.get('status') == 'error':
            failed += 1
            if total == 1 and isinstance(result, dict):
                summary = _public_result(result)
            else:
                note = result.get('message') if isinstance(result, dict) else ''
                _remember_failure(failures, label, note or 'That class could not be generated.')
            continue
        assigned += len(result.get('assigned') or [])
        unassigned += len(result.get('unassigned') or [])
        if total == 1:
            summary = _public_result(result)
    done_message = summary.get('message') if isinstance(summary, dict) else ''
    if total > 1:
        done_message = f'Finished {total} classes. {total - failed} generated, {failed} need attention.'
    if total > 1:
        summary = {'failures': failures} if failures else None
    _finish(job_id, 'completed', total, assigned, unassigned, failed, done_message or 'Generation finished.', summary)


def _remember_failure(failures, label, message):
    if len(failures) >= 20:
        return
    failures.append({'label': safe_text(label, 180), 'message': safe_text(message, 160)})


def _public_result(result):
    assigned = []
    for row in (result.get('assigned') or [])[:200]:
        if not isinstance(row, dict):
            continue
        assigned.append({
            'day': safe_text(row.get('day'), 12),
            'start_time': safe_text(row.get('start_time'), 8),
            'end_time': safe_text(row.get('end_time'), 8),
            'subject': safe_text(row.get('subject_name'), 100),
            'faculty': safe_text(row.get('faculty_name'), 100),
            'room': safe_text(row.get('room_number') or '', 20),
            'session_type': safe_text(row.get('session_type') or '', 20),
            'is_proxy': row.get('is_proxy') is True,
        })
    unassigned = []
    for row in (result.get('unassigned') or [])[:80]:
        if not isinstance(row, dict):
            continue
        unassigned.append({
            'day': safe_text(row.get('day'), 12),
            'start_time': safe_text(row.get('start_time'), 8),
            'end_time': safe_text(row.get('end_time'), 8),
            'reason': safe_text(row.get('reason') or '', 160),
        })
    proxies = []
    for row in (result.get('proxy_suggestions') or [])[:40]:
        if not isinstance(row, dict):
            continue
        proxies.append({
            'day': safe_text(row.get('day'), 12),
            'time': safe_text(row.get('time'), 24),
            'subject': safe_text(row.get('subject_name'), 100),
            'primary_faculty': safe_text(row.get('primary_faculty') or '', 100),
            'replacement_faculty': safe_text(row.get('replacement_faculty') or '', 100),
        })
    breakdown = result.get('score_breakdown') if isinstance(result.get('score_breakdown'), dict) else {}
    warnings = [
        safe_text(item, 200)
        for item in (result.get('warnings') or [])[:3]
        if isinstance(item, str) and item.strip()
    ]
    candidates = []
    for row in (result.get('top_candidates') or [])[:3]:
        if not isinstance(row, dict):
            continue
        candidates.append({
            'candidate_index': safe_count(row.get('candidate_index')),
            'quality_score': _score(row.get('quality_score')),
            'assigned_count': safe_count(row.get('assigned_count')),
            'unassigned_count': safe_count(row.get('unassigned_count')),
        })
    payload = {
        'status': safe_text(result.get('status') or 'error', 20),
        'message': safe_text(result.get('message') or 'The timetable could not be generated.', 300),
        'assigned_count': len(result.get('assigned') or []),
        'unassigned_count': len(result.get('unassigned') or []),
        'assigned': assigned,
        'unassigned': unassigned,
        'proxy_suggestions': proxies,
        'warnings': warnings,
        'top_candidates': candidates,
    }
    if 'quality_score' in result:
        payload['quality_score'] = _score(result.get('quality_score'))
        payload['score_breakdown'] = {
            'clash_risk': _ratio(breakdown.get('clash_risk')),
            'faculty_fatigue': _ratio(breakdown.get('faculty_fatigue')),
            'room_overuse': _ratio(breakdown.get('room_overuse')),
            'student_load_imbalance': _ratio(breakdown.get('student_load_imbalance')),
        }
    return payload


def _ratio(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number < 0:
        return 0.0
    return round(min(number, 1.0), 4)


def _score(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number < 0:
        return 0.0
    return round(min(number, 100.0), 2)


def _mark(job_id, done, total, assigned, unassigned, failed, message):
    progress = 1 if total <= 0 else min(99, int(done * 100 / total))
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE timetable_jobs
            SET progress = %s, done_count = %s, assigned_count = %s, unassigned_count = %s,
                failed_count = %s, message = %s
            WHERE id = %s AND status = 'running'
            """,
            (progress, done, assigned, unassigned, failed, safe_text(message, 300), job_id),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()


def _finish(job_id, status, done, assigned, unassigned, failed, message, summary):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE timetable_jobs
            SET status = %s, progress = 100, done_count = %s, assigned_count = %s,
                unassigned_count = %s, failed_count = %s, message = %s,
                summary_json = %s, finished_at = NOW()
            WHERE id = %s AND status = 'running'
            """,
            (
                status,
                done,
                assigned,
                unassigned,
                failed,
                safe_text(message, 300),
                json.dumps(summary) if summary else None,
                job_id,
            ),
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()
