"""Admin attendance screens. faculty."""

from flask import Blueprint, request, jsonify, session, flash, redirect, url_for, make_response
from ui.pages import render_template
from core.pagination import page_bounds
from extensions import get_db_connection
from datetime import datetime, timedelta

from services.attendance_admin._common import _table_exists, _decimal_to_number

def faculty_attendance_overview():
    """Faculty attendance dashboard (shift-based)."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'faculty_attendance'):
            flash(
                "faculty_attendance table not found. Run `flask db upgrade`.",
                "warning",
            )
            return render_template(
                'admin/attendance/faculty_overview.html',
                overall_stats={
                    'total_faculty': 0,
                    'total_records': 0,
                    'total_present': 0,
                    'total_late': 0,
                    'total_absent': 0,
                    'overall_percentage': 0.0,
                },
                today_by_shift=[],
                recent_activity=[],
                faculty_summary=[],
                recent_activity_filters={
                    'q': '',
                    'status': '',
                    'date_from': '',
                    'date_to': '',
                    'per_page': 20,
                },
                recent_activity_pagination={
                    'page': 1,
                    'per_page': 20,
                    'total_count': 0,
                    'total_pages': 1,
                    'has_prev': False,
                    'has_next': False,
                    'start_index': 0,
                    'end_index': 0,
                },
            )

        # Recent activity filters + pagination for high-volume attendance logs.
        ra_page = request.args.get('ra_page', 1, type=int) or 1
        ra_page = max(ra_page, 1)

        ra_per_page = request.args.get('ra_per_page', 20, type=int) or 20
        if ra_per_page not in (20, 50, 100):
            ra_per_page = 20

        ra_status = (request.args.get('ra_status') or '').strip()
        if ra_status not in ('Present', 'Late', 'Absent'):
            ra_status = ''

        ra_query = (request.args.get('ra_q') or '').strip()
        ra_date_from = (request.args.get('ra_date_from') or '').strip()
        ra_date_to = (request.args.get('ra_date_to') or '').strip()

        if ra_date_from:
            try:
                datetime.strptime(ra_date_from, '%Y-%m-%d')
            except ValueError:
                ra_date_from = ''

        if ra_date_to:
            try:
                datetime.strptime(ra_date_to, '%Y-%m-%d')
            except ValueError:
                ra_date_to = ''

        ra_where_clauses = ['1=1']
        ra_params = []

        if ra_status:
            ra_where_clauses.append('fa.status = %s')
            ra_params.append(ra_status)

        if ra_date_from:
            ra_where_clauses.append('fa.attendance_date >= %s')
            ra_params.append(ra_date_from)

        if ra_date_to:
            ra_where_clauses.append('fa.attendance_date <= %s')
            ra_params.append(ra_date_to)

        if ra_query:
            like_query = f'%{ra_query}%'
            ra_where_clauses.append(
                """
                (
                    f.name LIKE %s
                    OR f.employee_id LIKE %s
                    OR d.name LIKE %s
                    OR COALESCE(u.username, '') LIKE %s
                    OR COALESCE(fa.shift_name, '') LIKE %s
                    OR COALESCE(fa.shift_code, '') LIKE %s
                )
                """
            )
            ra_params.extend([like_query, like_query, like_query, like_query, like_query, like_query])

        ra_where_sql = ' AND '.join(ra_where_clauses)

        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT faculty_id) AS total_faculty,
                COUNT(*) AS total_records,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS total_absent,
                ROUND(
                    (
                        SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) * 100,
                    2
                ) AS overall_percentage
            FROM faculty_attendance
            WHERE attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            """
        )
        overall_stats = cursor.fetchone() or {}
        overall_stats = {
            'total_faculty': int(overall_stats.get('total_faculty') or 0),
            'total_records': int(overall_stats.get('total_records') or 0),
            'total_present': int(overall_stats.get('total_present') or 0),
            'total_late': int(overall_stats.get('total_late') or 0),
            'total_absent': int(overall_stats.get('total_absent') or 0),
            'overall_percentage': float(overall_stats.get('overall_percentage') or 0),
        }

        cursor.execute(
            """
            SELECT
                COALESCE(NULLIF(shift_name, ''), 'General Availability') AS shift_name,
                COUNT(*) AS total_marked,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS late_count,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS absent_count
            FROM faculty_attendance
            WHERE attendance_date = CURDATE()
            GROUP BY shift_key, shift_name
            ORDER BY shift_name
            """
        )
        today_by_shift = cursor.fetchall() or []
        for row in today_by_shift:
            row['total_marked'] = int(row.get('total_marked') or 0)
            row['present_count'] = int(row.get('present_count') or 0)
            row['late_count'] = int(row.get('late_count') or 0)
            row['absent_count'] = int(row.get('absent_count') or 0)

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN users u ON u.id = fa.marked_by_user_id
            WHERE {ra_where_sql}
            """,
            tuple(ra_params),
        )
        ra_total_count_row = cursor.fetchone() or {}
        ra_total_count = int(ra_total_count_row.get('total_count') or 0)
        ra_total_pages = page_bounds(ra_page, ra_per_page, ra_total_count, minimum_pages=1)[1]
        if ra_page > ra_total_pages:
            ra_page = ra_total_pages
        ra_offset = (ra_page - 1) * ra_per_page

        cursor.execute(
            f"""
            SELECT
                fa.attendance_date,
                fa.status,
                fa.shift_name,
                fa.shift_start_time,
                fa.shift_end_time,
                fa.marked_at,
                fa.source,
                f.id AS faculty_id,
                f.name AS faculty_name,
                f.employee_id,
                d.name AS department_name,
                u.username AS marked_by_username
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            LEFT JOIN users u ON u.id = fa.marked_by_user_id
            WHERE {ra_where_sql}
            ORDER BY fa.marked_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*ra_params, ra_per_page, ra_offset]),
        )
        recent_activity = cursor.fetchall() or []
        for row in recent_activity:
            for key in ('attendance_date', 'marked_at'):
                value = row.get(key)
                if isinstance(value, datetime):
                    if key == 'attendance_date':
                        row[key] = value.strftime('%Y-%m-%d')
                    else:
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute(
            """
            SELECT
                f.id AS faculty_id,
                f.name AS faculty_name,
                f.employee_id,
                d.name AS department_name,
                COUNT(*) AS total_shifts,
                SUM(CASE WHEN fa.status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN fa.status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN fa.status = 'Absent' THEN 1 ELSE 0 END) AS total_absent,
                ROUND(
                    (
                        SUM(CASE WHEN fa.status IN ('Present', 'Late') THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) * 100,
                    2
                ) AS attendance_percentage
            FROM faculty_attendance fa
            JOIN faculty f ON f.id = fa.faculty_id
            LEFT JOIN departments d ON d.id = f.department_id
            WHERE fa.attendance_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY f.id, f.name, f.employee_id, d.name
            ORDER BY attendance_percentage ASC, f.name ASC
            LIMIT 100
            """
        )
        faculty_summary = cursor.fetchall() or []
        for row in faculty_summary:
            row['total_shifts'] = int(row.get('total_shifts') or 0)
            row['total_present'] = int(row.get('total_present') or 0)
            row['total_late'] = int(row.get('total_late') or 0)
            row['total_absent'] = int(row.get('total_absent') or 0)
            row['attendance_percentage'] = float(row.get('attendance_percentage') or 0)

        recent_activity_filters = {
            'q': ra_query,
            'status': ra_status,
            'date_from': ra_date_from,
            'date_to': ra_date_to,
            'per_page': ra_per_page,
        }

        recent_activity_pagination = {
            'page': ra_page,
            'per_page': ra_per_page,
            'total_count': ra_total_count,
            'total_pages': ra_total_pages,
            'has_prev': ra_page > 1,
            'has_next': ra_page < ra_total_pages,
            'start_index': (ra_offset + 1) if ra_total_count > 0 else 0,
            'end_index': min(ra_offset + len(recent_activity), ra_total_count),
        }

        return render_template(
            'admin/attendance/faculty_overview.html',
            overall_stats=overall_stats,
            today_by_shift=today_by_shift,
            recent_activity=recent_activity,
            faculty_summary=faculty_summary,
            recent_activity_filters=recent_activity_filters,
            recent_activity_pagination=recent_activity_pagination,
        )
    except Exception as e:
        print(f"Error in faculty attendance overview: {e}")
        import traceback
        traceback.print_exc()
        flash("An error occurred while loading faculty attendance data.", "danger")
        return render_template(
            'admin/attendance/faculty_overview.html',
            overall_stats={
                'total_faculty': 0,
                'total_records': 0,
                'total_present': 0,
                'total_late': 0,
                'total_absent': 0,
                'overall_percentage': 0.0,
            },
            today_by_shift=[],
            recent_activity=[],
            faculty_summary=[],
            recent_activity_filters={
                'q': '',
                'status': '',
                'date_from': '',
                'date_to': '',
                'per_page': 20,
            },
            recent_activity_pagination={
                'page': 1,
                'per_page': 20,
                'total_count': 0,
                'total_pages': 1,
                'has_prev': False,
                'has_next': False,
                'start_index': 0,
                'end_index': 0,
            },
        )
    finally:
        cursor.close()
        connection.close()


def faculty_attendance_details(faculty_id):
    """Detailed attendance view for a specific faculty member."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        if not _table_exists(cursor, 'faculty_attendance'):
            flash(
                "faculty_attendance table not found. Run `flask db upgrade`.",
                "warning",
            )
            return redirect(url_for('attendance_admin.faculty_attendance_overview'))

        cursor.execute(
            """
            SELECT
                f.id,
                f.name,
                f.employee_id,
                f.email,
                f.phone,
                f.designation,
                d.name AS department_name
            FROM faculty f
            LEFT JOIN departments d ON d.id = f.department_id
            WHERE f.id = %s
            """,
            (faculty_id,),
        )
        faculty = cursor.fetchone()

        if not faculty:
            flash("Faculty member not found.", "danger")
            return redirect(url_for('attendance_admin.faculty_attendance_overview'))

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_shifts,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS total_present,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS total_late,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS total_absent,
                ROUND(
                    (
                        SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) * 100,
                    2
                ) AS overall_percentage
            FROM faculty_attendance
            WHERE faculty_id = %s
            """,
            (faculty_id,),
        )
        overall_stats = cursor.fetchone() or {}
        overall_stats = {
            'total_shifts': int(overall_stats.get('total_shifts') or 0),
            'total_present': int(overall_stats.get('total_present') or 0),
            'total_late': int(overall_stats.get('total_late') or 0),
            'total_absent': int(overall_stats.get('total_absent') or 0),
            'overall_percentage': float(overall_stats.get('overall_percentage') or 0),
        }

        cursor.execute(
            """
            SELECT
                COALESCE(NULLIF(shift_name, ''), 'General Availability') AS shift_name,
                COUNT(*) AS total_shifts,
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_count,
                SUM(CASE WHEN status = 'Late' THEN 1 ELSE 0 END) AS late_count,
                SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) AS absent_count,
                ROUND(
                    (
                        SUM(CASE WHEN status IN ('Present', 'Late') THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) * 100,
                    2
                ) AS attendance_percentage,
                MIN(attendance_date) AS first_marked,
                MAX(attendance_date) AS last_marked
            FROM faculty_attendance
            WHERE faculty_id = %s
            GROUP BY shift_key, shift_name
            ORDER BY shift_name
            """,
            (faculty_id,),
        )
        shift_wise = cursor.fetchall() or []
        for row in shift_wise:
            row['total_shifts'] = int(row.get('total_shifts') or 0)
            row['present_count'] = int(row.get('present_count') or 0)
            row['late_count'] = int(row.get('late_count') or 0)
            row['absent_count'] = int(row.get('absent_count') or 0)
            row['attendance_percentage'] = float(row.get('attendance_percentage') or 0)
            for key in ('first_marked', 'last_marked'):
                value = row.get(key)
                if isinstance(value, datetime):
                    row[key] = value.strftime('%Y-%m-%d')

        cursor.execute(
            """
            SELECT
                fa.attendance_date,
                fa.status,
                fa.shift_name,
                fa.shift_start_time,
                fa.shift_end_time,
                fa.source,
                fa.captured_at,
                fa.confidence,
                fa.remarks,
                fa.marked_at,
                u.username AS marked_by_username
            FROM faculty_attendance fa
            LEFT JOIN users u ON u.id = fa.marked_by_user_id
            WHERE fa.faculty_id = %s
            ORDER BY fa.marked_at DESC
            LIMIT 100
            """,
            (faculty_id,),
        )
        recent_records = cursor.fetchall() or []
        for row in recent_records:
            row['confidence'] = _decimal_to_number(row.get('confidence'))
            for key in ('attendance_date', 'captured_at', 'marked_at'):
                value = row.get(key)
                if isinstance(value, datetime):
                    if key == 'attendance_date':
                        row[key] = value.strftime('%Y-%m-%d')
                    else:
                        row[key] = value.strftime('%Y-%m-%d %H:%M:%S')

        return render_template(
            'admin/attendance/faculty_details.html',
            faculty=faculty,
            overall_stats=overall_stats,
            shift_wise=shift_wise,
            recent_records=recent_records,
        )
    except Exception as e:
        print(f"Error fetching faculty attendance details: {e}")
        import traceback
        traceback.print_exc()
        flash("An error occurred while loading faculty attendance details.", "danger")
        return redirect(url_for('attendance_admin.faculty_attendance_overview'))
    finally:
        cursor.close()
        connection.close()
