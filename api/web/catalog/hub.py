"""Counts for the academic hub."""

from flask import current_app, session

from extensions import get_db_connection
from api.web.access import allowed, close
from api.web.responses import json_error, json_ok
from api.web.security import safe_count

_TABLES = (
    ('years', 'academic_years'),
    ('semesters', 'semesters'),
    ('courses', 'courses'),
    ('subjects', 'subjects'),
    ('batches', 'course_batches'),
    ('allocations', 'faculty_allocations'),
    ('departments', 'departments'),
)


def register_hub_routes(blueprint):
    @blueprint.route('/academics/summary', methods=['GET'])
    def academics_summary():
        if 'user_id' not in session:
            return json_error('Authentication required.', 401, 'unauthorized')
        if session.get('role') not in ('Admin', 'Super Admin', 'HOD'):
            return json_error('You do not have permission to do that.', 403, 'forbidden')

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            counts = {}
            for key, table in _TABLES:
                cursor.execute(f'SELECT COUNT(*) FROM {table}')
                counts[key] = safe_count(cursor.fetchone()[0])
            return json_ok({
                'counts': counts,
                'permissions': {
                    'years': allowed('academicyears_view'),
                    'courses': allowed('courses_view_course'),
                    'semesters': allowed('semesters_view'),
                    'subjects': allowed('subjects_view_subject'),
                    'batches': allowed('batches_view'),
                    'allocations': allowed('allocations_view'),
                    'departments': allowed('departments_view'),
                },
            })
        except Exception:
            current_app.logger.exception('Academic hub failed')
            return json_error('The academic hub could not be loaded.', 500, 'academics_unavailable')
        finally:
            close(cursor, connection)
