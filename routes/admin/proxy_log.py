
from flask import Blueprint, make_response, redirect, url_for, request, flash, current_app, jsonify
from ui.pages import render_template
from security import has_permission
from services.proxy_log import load_proxy_log


proxy_bp = Blueprint('proxy', __name__, url_prefix='/admin/proxy')


@proxy_bp.route('/')
@has_permission('faculty_view_proxy')
def proxy_log():
    """Display comprehensive proxy log with faculty absence and proxy assignment details"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '', type=str)
    approval_filter = request.args.get('approval_status', '', type=str)
    date_from = request.args.get('date_from', '', type=str)
    date_to = request.args.get('date_to', '', type=str)
    proxy_logs, summary_stats, pagination = load_proxy_log(
        page, status_filter, approval_filter, date_from, date_to,
    )
    return render_template('admin/proxy_log.html',
                         proxy_logs=proxy_logs,
                         summary_stats=summary_stats,
                         pagination=pagination,
                         status_filter=status_filter,
                         approval_filter=approval_filter,
                         date_from=date_from,
                         date_to=date_to)
