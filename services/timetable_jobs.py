"""Queued timetable generation. The request only stores the job; one worker runs each class in order."""

import json
import threading
import time

from flask import current_app

from api.web.security import safe_count, safe_text
from extensions import get_db_connection
from services.job_claims import claim_next, requeue_stale

_MAX_CLASSES = 1000
_guard = threading.Lock()
_started = False


def ensure_worker(app, force=False):
    """Start the single generation worker for this process. Never under a Flask CLI command unless `force` (flask workers run)."""
    global _started
    if not force and (app.config.get('CLI_COMMAND') or not app.config.get('BACKGROUND_WORKERS', True)):
        return
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


def allocated_targets(course_id=None, scope=None):
    """Return class groups that already have a faculty allocation, oldest name first.

    `scope` (core.scope.Scope) limits the courses to the caller's institutions.
    """
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        clause = ''
        params = []
        if course_id:
            clause = ' AND s.course_id = %s'
            params.append(course_id)
        if scope is not None:
            scope_clause, scope_params = scope.course_clause('c')
            if scope_clause != '1=1':
                clause += f' AND {scope_clause}'
                params.extend(scope_params)
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


def run_pass(app, drain=False):
    """One pass over every tenant: requeue stale claims, then run one job (or all queued with `drain`). Returns jobs run."""
    from core.tenancy import tenant_context, tenants_to_serve

    ran = 0
    for tenant in tenants_to_serve(app):
        key = tenant.slug if tenant is not None else None
        try:
            with tenant_context(app, tenant):
                requeued = _requeue_interrupted()
                if requeued:
                    app.logger.warning('Timetable queue requeued %s stale job(s) for tenant %s', requeued, key or 'default')
                while True:
                    job_id = _claim_next()
                    if not job_id:
                        break
                    _process(job_id)
                    ran += 1
                    if not drain:
                        break
        except Exception:
            app.logger.exception('Timetable queue worker failed for tenant %s', key or 'default')
    return ran


def _loop(app):
    while True:
        try:
            worked = run_pass(app)
        except Exception:
            app.logger.exception('Timetable queue worker failed')
            worked = 0
        if not worked:
            time.sleep(1.5)


def _requeue_interrupted(seconds=None):
    """Requeue running generations whose worker stopped reporting. Returns how many were requeued."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        count = requeue_stale(
            cursor, 'timetable_jobs', "progress = 0, done_count = 0, message = 'Queued'", seconds,
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()
    return count


def _claim_next():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        job_id = claim_next(cursor, 'timetable_jobs')
        connection.commit()
        return job_id
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
    scores = {}
    total = len(targets)
    try:
        version_id = _open_draft(job, settings, targets)
    except Exception:
        current_app.logger.exception('Could not open a timetable draft for job %s', job_id)
        _finish(job_id, 'failed', 0, 0, 0, total, 'The timetable draft could not be created.', None)
        return
    if settings.get('solver') == 'joint':
        outcome = _process_jointly(job_id, job, settings, targets, version_id)
        if outcome is not None:
            return
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
                rules_override=settings.get('rules_override') if isinstance(settings.get('rules_override'), dict) else None,
                version_id=version_id,
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
        scores[_cohort_label(target)] = _score_entry(result)
        if total == 1:
            summary = _public_result(result)
    done_message = summary.get('message') if isinstance(summary, dict) else ''
    if total > 1:
        done_message = f'Finished {total} classes. {total - failed} generated, {failed} need attention.'
    if total > 1:
        summary = {'failures': failures} if failures else None
    summary, done_message = _close_draft(version_id, scores, summary, done_message)
    _finish(job_id, 'completed', total, assigned, unassigned, failed, done_message or 'Generation finished.', summary)


def _cohort_label(target):
    return f"{safe_count(target.get('course_id'))}-{safe_count(target.get('class_id'))}-{safe_count(target.get('division_id'))}"


def _score_entry(result):
    return {
        'quality_score': round(float(result.get('quality_score') or 0.0), 2),
        'rule_cost': safe_count(result.get('rule_cost')),
        'assigned': len(result.get('assigned') or []),
        'unassigned': len(result.get('unassigned') or []),
    }


def _open_draft(job, settings, targets):
    """Create the draft version this job writes into, or None when versions are off (direct writes as before)."""
    from services.timetable import versions
    from services.timetable.rules import institution_for_course

    clean = [t for t in targets if isinstance(t, dict)]
    if not clean:
        return None
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if not versions.active(cursor):
            return None
        version_id = versions.create_draft(
            cursor,
            institution_id=institution_for_course(cursor, clean[0].get('course_id')),
            targets=clean,
            solver=settings.get('solver') or 'greedy',
            settings=settings,
            created_by=job.get('created_by'),
            job_id=job.get('id'),
            label=settings.get('label') if isinstance(settings.get('label'), str) else None,
        )
        connection.commit()
        return version_id
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def _close_draft(version_id, scores, summary, message):
    """Store the draft's scores, or drop it when nothing was placed. Returns (summary, message)."""
    if version_id is None:
        return summary, message
    from services.timetable import versions

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        if versions.slot_count(cursor, version_id) == 0:
            versions.discard(cursor, version_id)
            connection.commit()
            return summary, f'{message} Nothing was placed, so no draft was kept.'.strip()
        versions.record_score(cursor, version_id, scores)
        connection.commit()
    except Exception:
        connection.rollback()
        current_app.logger.exception('Could not finish timetable draft %s', version_id)
        return summary, message
    finally:
        cursor.close()
        connection.close()
    summary = dict(summary) if isinstance(summary, dict) else {}
    summary['version_id'] = int(version_id)
    return summary, f'{message} Saved as a draft; compare and publish it from Timetable versions.'.strip()


def _process_jointly(job_id, job, settings, targets, version_id=None):
    """Solve every target in one CP-SAT model. Returns True when the job was finished here, None to fall back to greedy."""
    from services.timetable.joint_solver import SolverUnavailable, cohort_key, solve_targets

    clean = [t for t in targets if isinstance(t, dict)]
    total = len(targets)
    _mark(job_id, 0, total, 0, 0, 0, f'Solving {len(clean)} class(es) jointly')
    connection = get_db_connection()
    try:
        results = solve_targets(connection, clean, settings, created_by=job.get('created_by'), version_id=version_id)
    except SolverUnavailable:
        current_app.logger.warning('Joint solver requested but ortools is missing; using the greedy generator')
        _mark(job_id, 0, total, 0, 0, 0, 'Joint solver unavailable; scheduling class by class')
        return None
    except Exception:
        current_app.logger.exception('Joint timetable solve failed')
        _close_draft(version_id, {}, None, '')
        _finish(job_id, 'failed', total, 0, 0, total, 'The joint solver could not run.', None)
        return True
    finally:
        connection.close()
    assigned = unassigned = failed = 0
    failures = []
    summary = None
    scores = {}
    for target in targets:
        if not isinstance(target, dict):
            failed += 1
            continue
        result = results.get(cohort_key(target))
        label = safe_text(target.get('label') or 'Class', 180)
        if not isinstance(result, dict) or result.get('status') == 'error':
            failed += 1
            if total == 1 and isinstance(result, dict):
                summary = _public_result(result)
            else:
                _remember_failure(failures, label, (result or {}).get('message') or 'That class could not be generated.')
            continue
        assigned += len(result.get('assigned') or [])
        unassigned += len(result.get('unassigned') or [])
        scores[_cohort_label(target)] = _score_entry(result)
        if total == 1:
            summary = _public_result(result)
    done_message = summary.get('message') if isinstance(summary, dict) else ''
    if total > 1:
        done_message = f'Solved {total} classes jointly. {total - failed} generated, {failed} need attention.'
        summary = {'failures': failures} if failures else None
    summary, done_message = _close_draft(version_id, scores, summary, done_message)
    _finish(job_id, 'completed', total, assigned, unassigned, failed, done_message or 'Generation finished.', summary)
    return True


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
    violations = []
    for row in (result.get('violations') or [])[:60]:
        if not isinstance(row, dict):
            continue
        violations.append({
            'rule': safe_text(row.get('rule'), 40),
            'title': safe_text(row.get('title'), 60),
            'scope': safe_text(row.get('scope'), 10),
            'faculty': safe_text(row.get('faculty_name') or '', 100),
            'day': safe_text(row.get('day'), 12),
            'start_time': safe_text(row.get('start_time'), 8),
            'end_time': safe_text(row.get('end_time'), 8),
            'cost': safe_count(row.get('cost')),
            'detail': safe_text(row.get('detail') or '', 160),
        })
    rule_costs = result.get('rule_costs') if isinstance(result.get('rule_costs'), dict) else {}
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
        'violations': violations,
        'rule_cost': safe_count(result.get('rule_cost')),
        'rule_costs': {safe_text(key, 40): safe_count(value) for key, value in list(rule_costs.items())[:20]},
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
                failed_count = %s, message = %s, heartbeat_at = UTC_TIMESTAMP()
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
