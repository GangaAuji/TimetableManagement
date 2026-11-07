"""Admin department dropdown."""

from data_access.departments import fetch_department_choices
from extensions import get_db_connection


def list_department_choices():
    """Return department ids and names. Both the cursor and connection are closed."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        departments = fetch_department_choices(cursor)
        return [{'id': row['id'], 'name': row['name']} for row in departments]
    finally:
        cursor.close()
        connection.close()
