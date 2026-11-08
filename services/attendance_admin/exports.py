"""Admin attendance exports and chart data, all from services.attendance_calc."""

from flask import request, jsonify, make_response
from extensions import get_db_connection
from services.attendance_calc import cohort_figures, cohort_reports, daily_trend, defaulters, parse_threshold
from datetime import date, datetime, timedelta
import csv
import io

CHART_DAYS = 30


def _percent_cell(value):
    return '' if value is None else f"{value:.2f}%"


def export_overview():
    """Today's figures per cohort (course, class, division) as CSV. Cohorts with no lecture today are left out."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        today = date.today()
        reports = cohort_reports(cursor, date_from=today, date_to=today)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Course', 'Class', 'Division', 'Students', 'Held', 'Countable', 'Attended',
                         'Present', 'Late', 'Absent', 'Excused', 'Not Marked', 'Percentage'])
        for row in cohort_figures(reports):
            if not row['held']:
                continue
            writer.writerow([
                _cell(row['course_name']),
                _cell(row['class_name']),
                _cell(row['division_name']),
                row['students'],
                row['held'],
                row['countable'],
                row['attended'],
                row['present'],
                row['late'],
                row['absent'],
                row['excused'],
                row['not_marked'],
                _percent_cell(row['percentage']),
            ])

        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=attendance_overview_{datetime.now().strftime("%Y%m%d")}.csv'
        return response

    finally:
        cursor.close()
        connection.close()


def export_defaulters():
    """
    Export defaulters list to CSV.
    """
    threshold = request.args.get('threshold')
    if threshold is not None and parse_threshold(threshold) is None:
        return make_response('Enter a threshold between 1 and 100.', 400)
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        below, chosen = defaulters(cursor, threshold=threshold)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Roll Number', 'Name', 'Course', 'Class', 'Division',
                         'Held', 'Countable', 'Attended', 'Present', 'Late', 'Absent', 'Excused', 'Not Marked',
                         'Percentage', 'Classes Needed', 'Email', 'Phone'])
        for report in below:
            student = report.student
            overall = report.overall
            needed = report.summary.classes_needed
            writer.writerow([
                _cell(student.get('roll_number')),
                _cell(student.get('name')),
                _cell(student.get('course_name')),
                _cell(student.get('class_name')),
                _cell(student.get('division_name')),
                overall.held,
                overall.countable,
                overall.attended,
                overall.present,
                overall.late,
                overall.absent,
                overall.excused,
                overall.not_marked,
                f"{overall.percentage:.2f}%",
                '' if needed is None else needed,
                _cell(student.get('email')),
                _cell(student.get('phone')),
            ])

        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = (
            f'attachment; filename=attendance_defaulters_{int(chosen.threshold)}pct_{datetime.now().strftime("%Y%m%d")}.csv'
        )
        return response

    finally:
        cursor.close()
        connection.close()


def _cell(value):
    """A CSV cell that a spreadsheet will not run as a formula."""
    text = '' if value is None else str(value)
    if text[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + text
    return text


def charts_data():
    """Chart data for the last 30 days: `trend` (counts per lecture date) or `distribution` (percentage per class)."""
    chart_type = request.args.get('type', 'trend')
    if chart_type not in ('trend', 'distribution'):
        return jsonify({'error': 'Invalid chart type'}), 400
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        today = date.today()
        reports = cohort_reports(cursor, date_from=today - timedelta(days=CHART_DAYS), date_to=today)

        if chart_type == 'trend':
            points = daily_trend(reports)
            return jsonify({
                'labels': [point['date'] for point in points],
                'datasets': [
                    {'label': 'Present', 'data': [point['present'] for point in points], 'color': '#10b981'},
                    {'label': 'Absent', 'data': [point['absent'] for point in points], 'color': '#ef4444'},
                    {'label': 'Late', 'data': [point['late'] for point in points], 'color': '#f59e0b'},
                    {'label': 'Excused', 'data': [point['excused'] for point in points], 'color': '#6366f1'},
                    {'label': 'Not marked', 'data': [point['not_marked'] for point in points], 'color': '#9ca3af'},
                ],
            })

        classes = [row for row in cohort_figures(reports, keys=('course_name', 'class_name')) if row['percentage'] is not None]
        classes.sort(key=lambda row: -row['percentage'])
        classes = classes[:10]
        return jsonify({
            'labels': [f"{row['course_name']} {row['class_name']}" for row in classes],
            'data': [row['percentage'] for row in classes],
        })

    finally:
        cursor.close()
        connection.close()
