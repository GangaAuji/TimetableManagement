"""Admin report screens. attendance."""

from ui.pages import render_template


def attendance_report():
    """The React shell; the report itself is the 'attendance' dataset in services.reports_admin.dataset."""
    return render_template('admin/reports/attendance.html')
