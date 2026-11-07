"""Registered mobile devices. Device secrets are not returned."""

from flask import current_app, session

from extensions import get_db_connection
from api.web.access import close
from api.web.responses import json_error, json_ok
from api.web.security import safe_stamp, safe_text

_MESSAGES = {'devices_unavailable': 'The page could not be loaded.'}


def register_device_routes(blueprint):
    blueprint.add_url_rule('/devices', 'devices_list', _list, methods=['GET'])


def _list():
    if 'user_id' not in session:
        return json_error('Authentication required.', 401, 'unauthorized')
    if session.get('role') not in ('Admin', 'Super Admin'):
        return json_error('You do not have permission to do that.', 403, 'forbidden')
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT md.device_name, md.platform, md.is_active, md.last_used_at, md.created_at, u.username AS owner
            FROM mobile_devices md
            LEFT JOIN users u ON u.id = md.owner_user_id
            ORDER BY md.created_at DESC
            LIMIT 100
            """
        )
        devices = [
            {
                'name': safe_text(row.get('device_name') or '', 80),
                'platform': safe_text(row.get('platform') or '', 40),
                'owner': safe_text(row.get('owner') or '', 50),
                'is_active': bool(row.get('is_active')),
                'last_used': safe_stamp(row.get('last_used_at')),
                'created_at': safe_stamp(row.get('created_at')),
            }
            for row in cursor.fetchall()
        ]
        return json_ok({'devices': devices})
    except Exception:
        current_app.logger.exception('Device list failed')
        return json_error(_MESSAGES['devices_unavailable'], 500, 'devices_unavailable')
    finally:
        close(cursor, connection)
