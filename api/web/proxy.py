"""Proxy log for administrators and the signed-in teacher."""

from flask import current_app, session

from extensions import get_db_connection
from api.web.access import close, permission_denied
from api.web.responses import json_error, json_ok
from api.web.security import safe_stamp, safe_text

_MESSAGES = {'proxy_unavailable': 'The page could not be loaded.'}


def register_proxy_routes(blueprint):
    blueprint.add_url_rule('/proxy', 'proxy_list', _list, methods=['GET'])
    blueprint.add_url_rule('/portal/proxy', 'teacher_proxy', _teacher, methods=['GET'])


def _list():
    denied = permission_denied('faculty_view_proxy', 'proxy_unavailable', _MESSAGES['proxy_unavailable'])
    if denied:
        return denied
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT pl.absence_date, pl.status, pl.approval_status,
                   orig_f.name AS original_faculty, proxy_f.name AS proxy_faculty,
                   s.name AS subject_name, c.name AS class_name, d.name AS division_name
            FROM proxy_log pl
            JOIN timetable t ON pl.timetable_id = t.id
            JOIN faculty orig_f ON pl.original_faculty_id = orig_f.user_id
            LEFT JOIN faculty proxy_f ON pl.proxy_faculty_id = proxy_f.user_id
            JOIN subjects s ON t.subject_id = s.id
            JOIN classes c ON t.class_id = c.id
            JOIN divisions d ON t.division_id = d.id
            ORDER BY pl.absence_date DESC
            LIMIT 80
            """
        )
        rows = [
            {
                'date': safe_stamp(row.get('absence_date'))[:10],
                'status': safe_text(row.get('status') or '', 20),
                'approval': safe_text(row.get('approval_status') or '', 20),
                'original_faculty': safe_text(row.get('original_faculty') or '', 100),
                'proxy_faculty': safe_text(row.get('proxy_faculty') or '', 100),
                'subject': safe_text(row.get('subject_name') or '', 100),
                'class_name': safe_text(row.get('class_name') or '', 100),
                'division_name': safe_text(row.get('division_name') or '', 50),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'entries': rows})
    except Exception:
        current_app.logger.exception('Proxy list failed')
        return json_error(_MESSAGES['proxy_unavailable'], 500, 'proxy_unavailable')
    finally:
        close(cursor, connection)


def _teacher():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') != 'Teacher':
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT user_id FROM faculty WHERE id = %s OR user_id = %s LIMIT 1',
            (session.get('faculty_id') or 0, session.get('user_id')),
        )
        faculty = cursor.fetchone()
        if not faculty:
            return json_error(_MESSAGES['proxy_unavailable'], 404, 'proxy_unavailable')
        cursor.execute(
            """
            SELECT p.absence_date, p.status, p.approval_status, s.name AS subject_name,
                   ofc.name AS original_name, pfc.name AS proxy_name
            FROM proxy_log p
            JOIN timetable t ON t.id = p.timetable_id
            JOIN subjects s ON s.id = t.subject_id
            LEFT JOIN faculty ofc ON ofc.user_id = p.original_faculty_id
            LEFT JOIN faculty pfc ON pfc.user_id = p.proxy_faculty_id
            WHERE p.original_faculty_id = %s OR p.proxy_faculty_id = %s
            ORDER BY p.absence_date DESC
            LIMIT 40
            """,
            (faculty['user_id'], faculty['user_id']),
        )
        rows = [
            {
                'date': safe_stamp(row.get('absence_date'))[:10],
                'subject': safe_text(row.get('subject_name'), 100),
                'original': safe_text(row.get('original_name') or '', 100),
                'proxy': safe_text(row.get('proxy_name') or '', 100),
                'status': safe_text(row.get('status') or '', 20),
                'approval': safe_text(row.get('approval_status') or '', 20),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'entries': rows})
    except Exception:
        current_app.logger.exception('Teacher proxy failed')
        return json_error(_MESSAGES['proxy_unavailable'], 500, 'proxy_unavailable')
    finally:
        close(cursor, connection)
