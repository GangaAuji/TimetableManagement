"""Admin JSON lookups. These screens use the shared database helper."""

from data_access.admin_api import (
    fetch_allocation_faculty,
    fetch_classes,
    fetch_course_subjects,
    fetch_coverage_subjects,
    fetch_divisions,
    fetch_eligible_subjects,
    fetch_faculty_for_subject,
    fetch_latest_quality_run,
    fetch_quality_samples,
    fetch_scheduled_counts,
)
from extensions import get_db_connection


def _cursor():
    connection = get_db_connection()
    return connection, connection.cursor(dictionary=True)


def list_classes():
    """Return classes. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        return fetch_classes(cursor)
    finally:
        cursor.close()
        connection.close()


def list_divisions():
    """Return divisions. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        return fetch_divisions(cursor)
    finally:
        cursor.close()
        connection.close()


def faculty_for_subject(subject_id):
    """Return faculty for one subject. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        return fetch_faculty_for_subject(cursor, subject_id)
    finally:
        cursor.close()
        connection.close()


def eligible_subject_payload(course_id, class_id, division_id):
    """Return eligible and missing subjects. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        eligible_rows = fetch_eligible_subjects(cursor, course_id, class_id, division_id)
        eligible_subject_ids = [row['id'] for row in eligible_rows]
        faculty_map = {subject_id: [] for subject_id in eligible_subject_ids}
        if eligible_subject_ids:
            for row in fetch_allocation_faculty(cursor, eligible_subject_ids, class_id, division_id):
                faculty_map[row['subject_id']].append({
                    'name': row['faculty_name'],
                    'is_primary': bool(row['is_primary']),
                })
        eligible = []
        for row in eligible_rows:
            eligible.append({
                'id': row['id'],
                'name': row['name'],
                'course_code': row['course_code'],
                'theory_practical': row['theory_practical'],
                'lectures_per_week': int(row['lectures_per_week'] or 0),
                'practical_hours_per_week': float(row['practical_hours_per_week'] or 0),
                'faculty': faculty_map.get(row['id'], []),
            })
        all_course_subjects = fetch_course_subjects(cursor, course_id, class_id)
        missing = [
            {'id': row['id'], 'name': row['name'], 'course_code': row['course_code']}
            for row in all_course_subjects if row['id'] not in eligible_subject_ids
        ]
        return {'status': 'ok', 'eligible': eligible, 'missing': missing}
    finally:
        cursor.close()
        connection.close()


def coverage_subjects(course_id, class_id, division_id):
    """Return subjects and scheduled counts. Both the cursor and connection are closed."""
    connection, cursor = _cursor()
    try:
        subjects = fetch_coverage_subjects(cursor, course_id, class_id)
        subject_ids = [subject['id'] for subject in subjects]
        scheduled_counts = {}
        if subject_ids:
            for row in fetch_scheduled_counts(cursor, course_id, class_id, division_id, subject_ids):
                scheduled_counts[int(row['subject_id'])] = int(row['cnt'])
        return subjects, scheduled_counts
    finally:
        cursor.close()
        connection.close()


def quality_sample_counts():
    """Return quality sample counts. A missing table leaves the counts at zero."""
    training_samples = 0
    accepted_samples = 0
    rejected_samples = 0
    last_run_at = None
    last_run_score = None
    connection, cursor = _cursor()
    try:
        try:
            sample_row = fetch_quality_samples(cursor) or {}
            training_samples = int(sample_row.get('total_samples') or 0)
            accepted_samples = int(sample_row.get('accepted_samples') or 0)
            rejected_samples = int(sample_row.get('rejected_samples') or 0)
        except Exception:
            training_samples = 0
            accepted_samples = 0
            rejected_samples = 0
        try:
            latest_row = fetch_latest_quality_run(cursor) or {}
            last_run_at = latest_row.get('created_at')
            if latest_row.get('quality_score') is not None:
                last_run_score = float(latest_row.get('quality_score'))
        except Exception:
            last_run_at = None
            last_run_score = None
    finally:
        cursor.close()
        connection.close()
    return {
        'training_samples': training_samples,
        'accepted_samples': accepted_samples,
        'rejected_samples': rejected_samples,
        'last_run_at': last_run_at,
        'last_run_score': last_run_score,
    }
