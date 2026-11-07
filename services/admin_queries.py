"""Shared admin pagination and proxy assignment."""

from academic_rules.clashes import faculty_timetable_free
from core.pagination import page_bounds
from data_access.admin_queries import (
    fetch_absence_lectures,
    fetch_proxy_candidates,
    insert_proxy_log,
)
from extensions import get_db_connection


def query_page(query, params, page, per_page=10):
    """Return one page of rows and the page count. The connection stays open."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    from_clause_index = query.upper().find(' FROM ')
    if from_clause_index == -1:
        raise ValueError("Query for pagination must include a FROM clause.")
    count_query = f"SELECT COUNT(*) AS total {query[from_clause_index:]}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()['total']
    offset, total_pages = page_bounds(page, per_page, total)
    data_query = f"{query} LIMIT %s OFFSET %s"
    cursor.execute(data_query, params + (per_page, offset))
    results = cursor.fetchall()
    cursor.close()
    return results, total_pages


def faculty_is_free(cursor, faculty_id, day, start_time, end_time):
    """Return whether a faculty member has no overlapping timetable row."""
    return faculty_timetable_free(
        cursor, faculty_id, day, start_time, end_time, active_only=False,
    )


def assign_admin_proxy(absent_faculty_id, absence_date, session):
    """Assign a proxy for each lecture on the absence weekday. The connection stays open."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    day_of_week = absence_date.strftime('%A')
    affected_lectures = fetch_absence_lectures(cursor, absent_faculty_id, day_of_week)
    for lecture in affected_lectures:
        timetable_id = lecture['id']
        subject_id = lecture['subject_id']
        start_time = lecture['start_time']
        end_time = lecture['end_time']
        potential_proxies = fetch_proxy_candidates(cursor, subject_id, absent_faculty_id)
        assigned_proxy_id = next(
            (
                proxy['faculty_id']
                for proxy in potential_proxies
                if faculty_is_free(cursor, proxy['faculty_id'], day_of_week, start_time, end_time)
            ),
            None,
        )
        status = 'ASSIGNED' if assigned_proxy_id else 'UNASSIGNED'
        insert_proxy_log(
            cursor,
            (absent_faculty_id, assigned_proxy_id, timetable_id, absence_date, status, session.get('user_id')),
        )
    connection.commit()
    cursor.close()
