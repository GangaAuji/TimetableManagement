"""
Admin Dashboard Routes
Displays statistics, charts, and quick access to core admin functions
"""

from flask import Blueprint, session
from ui.pages import render_template
from routes.admin_utils import admin_required, format_time
from services.admin_dashboard import load_admin_dashboard

dashboard_bp = Blueprint('admin', __name__, url_prefix='/admin')


@dashboard_bp.route('/dashboard')
@admin_required
def dashboard():
    """Main admin dashboard with statistics and overview"""
    page = load_admin_dashboard()
    return render_template(
        'legacy/admin/dashboard.html',
        stats=page['stats'],
        recent_proxies=page['recent_proxies'],
        upcoming_holidays=page['upcoming_holidays'],
        format_time=format_time,
    )
