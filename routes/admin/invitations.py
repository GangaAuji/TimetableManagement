from flask import Blueprint, render_template, redirect, url_for, session, request, flash, current_app, jsonify
from datetime import time, timedelta, datetime

import math
import secrets
from forms import InvitationForm
from database import get_db_connection
from security import has_permission


invitations_bp = Blueprint(
    'invitations',
    __name__,
    url_prefix='/admin/invitations'
)

# --- Registration Invitation Management ---
@invitations_bp.route('/')
@has_permission('users_change_user')
def manage_invitations():
    """List and manage registration invitations"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '', type=str)
    status_filter = request.args.get('status', '', type=str)
    per_page = 15
    
    # Create form for CSRF protection
    form = InvitationForm()
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    
    query_base = """
        FROM registration_invitations ri
        LEFT JOIN courses c ON ri.course_id = c.id
        LEFT JOIN departments d ON ri.department_id = d.id
        LEFT JOIN users u ON ri.created_by = u.id
    """
    
    conditions = []
    params = []
    
    if search:
        conditions.append("(ri.email LIKE %s OR ri.name LIKE %s)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term])
    
    if status_filter and status_filter in ['pending', 'used', 'expired']:
        conditions.append("ri.status = %s")
        params.append(status_filter)
    
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    count_query = f"SELECT COUNT(ri.id) AS total {query_base}{where_clause}"
    cursor.execute(count_query, tuple(params))
    total = cursor.fetchone()['total']
    total_pages = math.ceil(total / per_page)
    
    offset = (page - 1) * per_page
    data_query = f"""
        SELECT ri.id, ri.token, ri.email, ri.name, ri.role, ri.status,
               ri.created_at, ri.expires_at, ri.used_at,
               c.name as course_name, d.name as dept_name, u.username as created_by_username
        {query_base}{where_clause}
        ORDER BY ri.created_at DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(data_query, tuple(params) + (per_page, offset))
    invitations = cursor.fetchall()
    
    # Fetch dropdown data for creating new invitations
    cursor.execute("SELECT id, name FROM courses ORDER BY name")
    courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM classes ORDER BY name")
    classes = cursor.fetchall()
    cursor.execute("SELECT id, name FROM divisions ORDER BY name")
    divisions = cursor.fetchall()
    cursor.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cursor.fetchall()
    
    # Calculate statistics
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status = 'pending' AND expires_at > NOW() THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'used' THEN 1 ELSE 0 END) as used,
            SUM(CASE WHEN status = 'expired' OR (status = 'pending' AND expires_at <= NOW()) THEN 1 ELSE 0 END) as expired,
            COUNT(*) as total
        FROM registration_invitations
    """)
    stats_row = cursor.fetchone()
    stats = {
        'pending': stats_row['pending'] or 0,
        'used': stats_row['used'] or 0,
        'expired': stats_row['expired'] or 0,
        'total': stats_row['total'] or 0
    }
    
    cursor.close()
    
    return render_template('admin/manage_invitations.html',
                         form=form,
                         invitations=invitations,
                         courses=courses,
                         classes=classes,
                         divisions=divisions,
                         departments=departments,
                         stats=stats,
                         page=page,
                         total_pages=total_pages,
                         search=search,
                         status_filter=status_filter)


@invitations_bp.route('/create', methods=['POST'])
@has_permission('users_add_user')
def create_invitation():
    """Generate a new registration invitation"""
    email = request.form.get('email')
    name = request.form.get('name')
    role = request.form.get('role')
    days_valid = int(request.form.get('days_valid', 7))
    
    if not email or not name or not role:
        flash('Email, name, and role are required.', 'danger')
        return redirect(url_for('invitations.manage_invitations'))
    
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    
    # Check if email already has a pending invitation
    cursor.execute("""
        SELECT id FROM registration_invitations 
        WHERE email = %s AND status = 'pending' AND expires_at > NOW()
    """, (email,))
    if cursor.fetchone():
        flash('A pending invitation already exists for this email.', 'warning')
        cursor.close()
        return redirect(url_for('invitations.manage_invitations'))
    
    # Check if email already registered
    if role == 'Student':
        cursor.execute("SELECT id FROM students WHERE email = %s", (email,))
    else:
        cursor.execute("SELECT id FROM faculty WHERE email = %s", (email,))
    
    if cursor.fetchone():
        flash('This email is already registered in the system.', 'warning')
        cursor.close()
        return redirect(url_for('invitations.manage_invitations'))
    
    # Generate secure token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=days_valid)
    
    # Get role-specific data
    course_id = request.form.get('course_id') if role == 'Student' else None
    class_id = request.form.get('class_id') if role == 'Student' else None
    division_id = request.form.get('division_id') if role == 'Student' else None
    department_id = request.form.get('department_id') if role == 'Teacher' else None
    
    try:
        cursor.execute("""
            INSERT INTO registration_invitations 
            (token, email, name, role, course_id, class_id, division_id, department_id, created_by, expires_at, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
        """, (token, email, name, role, course_id, class_id, division_id, department_id, session['user_id'], expires_at))
        connection.commit()
        
        # Generate registration link
        registration_url = url_for('auth.register', token=token, _external=True)
        flash(f'Invitation created! Registration link: {registration_url}', 'success')
        
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error creating invitation: {str(e)}")
        flash('Error creating invitation. Please try again.', 'danger')
    
    cursor.close()
    return redirect(url_for('invitations.manage_invitations'))


@invitations_bp.route('/revoke/<int:invitation_id>', methods=['POST'])
@has_permission('users_change_user')
def revoke_invitation(invitation_id):
    """Revoke/expire an invitation"""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        UPDATE registration_invitations 
        SET status = 'expired' 
        WHERE id = %s AND status = 'pending'
    """, (invitation_id,))
    connection.commit()
    cursor.close()
    flash('Invitation revoked successfully.', 'success')
    return redirect(url_for('invitations.manage_invitations'))


@invitations_bp.route('/resend/<int:invitation_id>', methods=['POST'])
@has_permission('users_change_user')
def resend_invitation(invitation_id):
    """Regenerate token and extend expiry for an invitation"""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    
    # Get invitation details
    cursor.execute("SELECT email, status FROM registration_invitations WHERE id = %s", (invitation_id,))
    invitation = cursor.fetchone()
    
    if not invitation:
        flash('Invitation not found.', 'danger')
        cursor.close()
        return redirect(url_for('invitations.manage_invitations'))
    
    if invitation['status'] == 'used':
        flash('Cannot resend a used invitation.', 'warning')
        cursor.close()
        return redirect(url_for('invitations.manage_invitations'))
    
    # Generate new token and extend expiry
    new_token = secrets.token_urlsafe(32)
    new_expires_at = datetime.now() + timedelta(days=7)
    
    cursor.execute("""
        UPDATE registration_invitations 
        SET token = %s, expires_at = %s, status = 'pending' 
        WHERE id = %s
    """, (new_token, new_expires_at, invitation_id))
    connection.commit()
    
    registration_url = url_for('auth.register', token=new_token, _external=True)
    flash(f'Invitation regenerated! New link: {registration_url}', 'success')
    
    cursor.close()
    return redirect(url_for('invitations.manage_invitations'))


@invitations_bp.route('/copy_link/<int:invitation_id>')
@has_permission('users_change_user')
def copy_invitation_link(invitation_id):
    """Get invitation link for copying"""
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT token FROM registration_invitations WHERE id = %s", (invitation_id,))
    result = cursor.fetchone()
    cursor.close()
    
    if result:
        token = result['token']
        registration_url = url_for('auth.register', token=token, _external=True)
        return jsonify({'url': registration_url})
    
    return jsonify({'error': 'Invitation not found'}), 404


