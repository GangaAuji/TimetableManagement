from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from forms import UserForm, EmptyForm, RoleForm, PermissionForm, UserFilterForm
from app import mysql
from security import has_permission, log_activity, get_user_permissions, check_user_permission, grant_user_permission, revoke_user_permission, get_accessible_departments
from werkzeug.security import generate_password_hash
from datetime import datetime
import csv
import io
import secrets
import string

user_mgmt_bp = Blueprint('user_mgmt_bp', __name__, url_prefix='/admin/users')

@user_mgmt_bp.before_request
def update_forms():
    """Update dynamic form choices before each request"""
    if 'role' in request.form:
        form = RoleForm()
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT id, name FROM permissions ORDER BY module, name')
        form.permissions.choices = [(p[0], p[1]) for p in cursor.fetchall()]
        cursor.close()

@user_mgmt_bp.route('/')
@has_permission('view_users')
def manage_users():
    form = UserForm()
    empty_form = EmptyForm()
    filter_form = UserFilterForm()
    
    # Get filters from request
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    
    # Build query conditions
    conditions = []
    params = []
    if role_filter:
        conditions.append("u.role = %s")
        params.append(role_filter)
    if status_filter:
        conditions.append("u.status = %s")
        params.append(status_filter)
    if search:
        # Without FK to students/faculty, search by username only for now
        conditions.append("(u.username LIKE %s)")
        search_term = f"%{search}%"
        params.extend([search_term])
    
    # Construct the final query
    query = """
        SELECT u.id, u.username, u.role, u.status, u.last_login,
               u.username as display_name
        FROM users u
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY u.username"
    
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT name FROM roles ORDER BY name')
    roles = cursor.fetchall()
    
    # Update filter form choices
    filter_form.role.choices = [('', 'All')] + [(r[0], r[0]) for r in roles]
    form.role.choices = [(r[0], r[0]) for r in roles]
    
    cursor.execute(query, params)
    users = cursor.fetchall()
    cursor.close()
    
    return render_template(
        'admin/manage_users.html',
        users=users,
        roles=roles,
        form=form,
        empty_form=empty_form,
        filter_form=filter_form,
        role_filter=role_filter,
        status_filter=status_filter,
        search=search
    )

@user_mgmt_bp.route('/add', methods=['POST'])
@has_permission('manage_users')
def add_user():
    form = UserForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        role = form.role.data
        status = form.status.data or 'active'
        email = form.email.data
        
        cursor = mysql.connection.cursor()
        try:
            # Check if username exists
            cursor.execute('SELECT id FROM users WHERE username = %s', [username])
            if cursor.fetchone():
                flash('Username already exists.', 'danger')
                return redirect(url_for('user_mgmt_bp.manage_users'))
            
            # Insert user
            hashed = generate_password_hash(password) if password else ''
            cursor.execute(
                'INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)',
                [username, hashed, role, status]
            )
            user_id = cursor.lastrowid
            
            # Log activity
            log_activity(
                session['user_id'],
                'create_user',
                f'Created new user: {username} with role {role}'
            )
            
            mysql.connection.commit()
            flash('User created successfully.', 'success')
            
        except Exception as e:
            mysql.connection.rollback()
            current_app.logger.error(f"Error creating user: {str(e)}")
            flash('Error creating user. Please try again.', 'danger')
        finally:
            cursor.close()
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    
    return redirect(url_for('user_mgmt_bp.manage_users'))

@user_mgmt_bp.route('/get/<int:user_id>')
@has_permission('view_users')
def get_user(user_id):
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "SELECT id, username, role, status, last_login FROM users WHERE id = %s",
            [user_id]
        )
        user = cursor.fetchone()

        if user:
            # Without profile linkage, display_name defaults to username; email unknown
            return jsonify({
                'id': user[0],
                'username': user[1],
                'role': user[2],
                'status': user[3],
                'display_name': user[1],
                'email': None
            })
        return jsonify({'error': 'User not found'}), 404
    finally:
        cursor.close()

@user_mgmt_bp.route('/edit/<int:user_id>', methods=['POST'])
@has_permission('manage_users')
def edit_user(user_id):
    form = UserForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        role = form.role.data
        status = form.status.data
        email = form.email.data
        
        cursor = mysql.connection.cursor()
        try:
            # Check if username exists for other users
            cursor.execute('SELECT id FROM users WHERE username = %s AND id != %s', 
                         [username, user_id])
            if cursor.fetchone():
                flash('Username already exists.', 'danger')
                return redirect(url_for('user_mgmt_bp.manage_users'))
            
            # Update user
            if password:
                hashed = generate_password_hash(password)
                cursor.execute('''
                    UPDATE users 
                    SET username=%s, password=%s, role=%s, status=%s 
                    WHERE id=%s
                ''', [username, hashed, role, status, user_id])
            else:
                cursor.execute('''
                    UPDATE users 
                    SET username=%s, role=%s, status=%s 
                    WHERE id=%s
                ''', [username, role, status, user_id])
            
            # Log activity
            log_activity(
                session['user_id'],
                'edit_user',
                f'Updated user {username} (ID: {user_id})'
            )
            
            mysql.connection.commit()
            flash('User updated successfully.', 'success')
            
        except Exception as e:
            mysql.connection.rollback()
            current_app.logger.error(f"Error updating user: {str(e)}")
            flash('Error updating user. Please try again.', 'danger')
        finally:
            cursor.close()
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    
    return redirect(url_for('user_mgmt_bp.manage_users'))

@user_mgmt_bp.route('/delete/<int:user_id>', methods=['POST'])
@has_permission('manage_users')
def delete_user(user_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'CSRF token missing or invalid'}), 400
    
    cursor = mysql.connection.cursor()
    try:
        # Get user info before deletion
        cursor.execute('SELECT username, role FROM users WHERE id = %s', [user_id])
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        username, role = user
        if role == 'Super Admin':
            return jsonify({'error': 'Cannot delete Super Admin users'}), 403
        
        # Delete user
        cursor.execute('DELETE FROM users WHERE id = %s', [user_id])
        
        # Log activity
        log_activity(
            session['user_id'],
            'delete_user',
            f'Deleted user {username} (ID: {user_id})'
        )
        
        mysql.connection.commit()
        return jsonify({'message': 'User deleted successfully'})
        
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error deleting user: {str(e)}")
        return jsonify({'error': 'Error deleting user'}), 500
    finally:
        cursor.close()

@user_mgmt_bp.route('/roles')
@has_permission('manage_roles')
def manage_roles():
    form = RoleForm()
    cursor = mysql.connection.cursor()
    
    # Get all permissions for form choices
    cursor.execute('SELECT id, name, module FROM permissions ORDER BY module, name')
    permissions = cursor.fetchall()
    form.permissions.choices = [(p[0], f"{p[2]} - {p[1]}") for p in permissions]
    
    # Get roles with their permissions
    cursor.execute("""
        SELECT r.id, r.name, r.description, r.created_at, r.updated_at,
               GROUP_CONCAT(p.name) as permissions
        FROM roles r
        LEFT JOIN role_permissions rp ON r.id = rp.role_id
        LEFT JOIN permissions p ON rp.permission_id = p.id
        GROUP BY r.id, r.name, r.description, r.created_at, r.updated_at
        ORDER BY r.name
    """)
    roles = cursor.fetchall()
    cursor.close()
    
    return render_template(
        'admin/manage_roles.html',
        roles=roles,
        form=form,
        permissions=permissions
    )

@user_mgmt_bp.route('/roles/add', methods=['POST'])
@has_permission('manage_roles')
def add_role():
    form = RoleForm()
    # Ensure permissions choices are populated so WTForms can coerce incoming values
    cursor = mysql.connection.cursor()
    try:
        cursor.execute('SELECT id, name, module FROM permissions ORDER BY module, name')
        perms = cursor.fetchall()
        form.permissions.choices = [(p[0], f"{p[2]} - {p[1]}") for p in perms]
    finally:
        cursor.close()

    if form.validate_on_submit():
        name = form.name.data.strip()
        description = form.description.data
        permissions = form.permissions.data or []
        
        cursor = mysql.connection.cursor()
        try:
            # Check if role exists
            cursor.execute('SELECT id FROM roles WHERE name = %s', [name])
            if cursor.fetchone():
                flash('Role already exists.', 'danger')
                return redirect(url_for('user_mgmt_bp.manage_roles'))
            
            # Insert role
            cursor.execute(
                'INSERT INTO roles (name, description) VALUES (%s, %s)',
                [name, description]
            )
            role_id = cursor.lastrowid
            
            # Add permissions
            for perm_id in permissions:
                try:
                    pid = int(perm_id)
                except (TypeError, ValueError):
                    continue
                cursor.execute(
                    'INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)',
                    [role_id, pid]
                )
            
            log_activity(
                session['user_id'],
                'create_role',
                f'Created new role: {name}'
            )
            
            mysql.connection.commit()
            flash('Role created successfully.', 'success')
            
        except Exception as e:
            mysql.connection.rollback()
            current_app.logger.error(f"Error creating role: {str(e)}")
            flash('Error creating role. Please try again.', 'danger')
        finally:
            cursor.close()
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')
    
    return redirect(url_for('user_mgmt_bp.manage_roles'))


@user_mgmt_bp.route('/roles/delete/<int:role_id>', methods=['POST'])
@has_permission('manage_roles')
def delete_role(role_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        flash('Invalid request (CSRF).', 'danger')
        return redirect(url_for('user_mgmt_bp.manage_roles'))

    cursor = mysql.connection.cursor()
    try:
        # Ensure role exists and is not Super Admin
        cursor.execute('SELECT name FROM roles WHERE id = %s', [role_id])
        row = cursor.fetchone()
        if not row:
            flash('Role not found.', 'danger')
            return redirect(url_for('user_mgmt_bp.manage_roles'))
        role_name = row[0]
        if role_name == 'Super Admin':
            flash('Cannot delete Super Admin role.', 'danger')
            return redirect(url_for('user_mgmt_bp.manage_roles'))

        # Remove role permissions first
        cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', [role_id])
        # Delete the role
        cursor.execute('DELETE FROM roles WHERE id = %s', [role_id])

        log_activity(
            session['user_id'],
            'delete_role',
            f'Deleted role {role_name} (ID: {role_id})'
        )

        mysql.connection.commit()
        flash('Role deleted successfully.', 'success')
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error deleting role: {str(e)}")
        flash('Error deleting role. Please try again.', 'danger')
    finally:
        cursor.close()

    return redirect(url_for('user_mgmt_bp.manage_roles'))


@user_mgmt_bp.route('/roles/edit/<int:role_id>', methods=['POST'])
@has_permission('manage_roles')
def edit_role(role_id):
    form = RoleForm()
    # populate permissions choices so form can validate
    cursor = mysql.connection.cursor()
    try:
        cursor.execute('SELECT id, name, module FROM permissions ORDER BY module, name')
        perms = cursor.fetchall()
        form.permissions.choices = [(p[0], f"{p[2]} - {p[1]}") for p in perms]
    finally:
        cursor.close()

    if form.validate_on_submit():
        name = form.name.data.strip()
        description = form.description.data
        permissions = form.permissions.data or []

        cursor = mysql.connection.cursor()
        try:
            # Prevent renaming to Super Admin if attempting to modify special role
            cursor.execute('SELECT name FROM roles WHERE id = %s', [role_id])
            row = cursor.fetchone()
            if not row:
                flash('Role not found.', 'danger')
                return redirect(url_for('user_mgmt_bp.manage_roles'))
            old_name = row[0]
            if old_name == 'Super Admin' and name != 'Super Admin':
                flash('Cannot rename Super Admin role.', 'danger')
                return redirect(url_for('user_mgmt_bp.manage_roles'))

            # Update role
            cursor.execute('UPDATE roles SET name=%s, description=%s WHERE id=%s', [name, description, role_id])
            # Reset permissions
            cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', [role_id])
            for perm_id in permissions:
                try:
                    pid = int(perm_id)
                except (TypeError, ValueError):
                    continue
                cursor.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)', [role_id, pid])

            log_activity(session['user_id'], 'edit_role', f'Edited role {name} (ID: {role_id})')
            mysql.connection.commit()
            flash('Role updated successfully.', 'success')
        except Exception as e:
            mysql.connection.rollback()
            current_app.logger.error(f"Error editing role: {str(e)}")
            flash('Error editing role. Please try again.', 'danger')
        finally:
            cursor.close()
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'danger')

    return redirect(url_for('user_mgmt_bp.manage_roles'))


@user_mgmt_bp.route('/roles/get/<int:role_id>')
@has_permission('manage_roles')
def get_role(role_id):
    cursor = mysql.connection.cursor()
    try:
        cursor.execute('SELECT id, name, description FROM roles WHERE id = %s', [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'error': 'Role not found'}), 404

        # fetch permission ids
        cursor.execute('SELECT permission_id FROM role_permissions WHERE role_id = %s', [role_id])
        perms = cursor.fetchall()
        perm_ids = [p[0] for p in perms]

        return jsonify({
            'id': role[0],
            'name': role[1],
            'description': role[2],
            'permissions': perm_ids
        })
    finally:
        cursor.close()

@user_mgmt_bp.route('/activity-log')
@has_permission('view_users')
def activity_log():
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            """
            SELECT l.id, l.user_id, l.activity_type, l.description,
                   l.ip_address, l.user_agent, l.created_at,
                   u.username,
                   u.username as display_name
            FROM user_activity_log l
            JOIN users u ON l.user_id = u.id
            ORDER BY l.created_at DESC
            LIMIT 1000
            """
        )
        logs = cursor.fetchall()
        return render_template('admin/activity_log.html', logs=logs)
    finally:
        cursor.close()


# -------- Enhancements: Bulk actions, status toggle, reset password, export --------

def _gen_temp_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

@user_mgmt_bp.route('/bulk', methods=['POST'])
@has_permission('manage_users')
def bulk_users_action():
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400

    action = request.form.get('action')
    ids = request.form.getlist('user_ids[]') or request.form.getlist('user_ids')
    if not ids:
        return jsonify({'error': 'No users selected.'}), 400

    # Prevent operating on Super Admin by ID
    cursor = mysql.connection.cursor()
    try:
        if action in ('activate', 'deactivate'):
            new_status = 'active' if action == 'activate' else 'inactive'
            format_str = ','.join(['%s'] * len(ids))
            cursor.execute(f"UPDATE users SET status = %s WHERE id IN ({format_str}) AND role != 'Super Admin'", [new_status, *ids])
            mysql.connection.commit()
            log_activity(session['user_id'], f'bulk_{action}_users', f"Affected IDs: {','.join(ids)}")
            return jsonify({'message': f"Users {action}d successfully."})
        elif action == 'delete':
            format_str = ','.join(['%s'] * len(ids))
            # Avoid deleting Super Admins
            cursor.execute(f"DELETE FROM users WHERE id IN ({format_str}) AND role != 'Super Admin'", ids)
            mysql.connection.commit()
            log_activity(session['user_id'], 'bulk_delete_users', f"Deleted IDs: {','.join(ids)}")
            return jsonify({'message': 'Users deleted successfully.'})
        elif action == 'reset_password':
            new_pwd = request.form.get('new_password')
            if new_pwd and len(new_pwd) < 8:
                return jsonify({'error': 'New password must be at least 8 characters.'}), 400
            # If not provided, generate a temporary password (returned in response)
            if not new_pwd:
                new_pwd = _gen_temp_password()
            hashed = generate_password_hash(new_pwd)
            format_str = ','.join(['%s'] * len(ids))
            cursor.execute(f"UPDATE users SET password = %s WHERE id IN ({format_str}) AND role != 'Super Admin'", [hashed, *ids])
            mysql.connection.commit()
            log_activity(session['user_id'], 'bulk_reset_password', f"Affected IDs: {','.join(ids)}")
            return jsonify({'message': 'Passwords reset successfully.', 'temp_password': new_pwd})
        else:
            return jsonify({'error': 'Unknown action.'}), 400
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Bulk users action error: {e}")
        return jsonify({'error': 'Operation failed.'}), 500
    finally:
        cursor.close()

@user_mgmt_bp.route('/reset_password/<int:user_id>', methods=['POST'])
@has_permission('manage_users')
def reset_password(user_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    new_pwd = request.form.get('new_password')
    if new_pwd and len(new_pwd) < 8:
        return jsonify({'error': 'Password must be at least 8 characters.'}), 400
    if not new_pwd:
        new_pwd = _gen_temp_password()
    hashed = generate_password_hash(new_pwd)
    cursor = mysql.connection.cursor()
    try:
        # Do not allow password reset for Super Admin via this endpoint
        cursor.execute("SELECT role FROM users WHERE id = %s", [user_id])
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'User not found.'}), 404
        if row[0] == 'Super Admin':
            return jsonify({'error': 'Cannot reset password for Super Admin.'}), 403
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", [hashed, user_id])
        mysql.connection.commit()
        log_activity(session['user_id'], 'reset_password', f'Reset password for user ID {user_id}')
        return jsonify({'message': 'Password reset successfully.', 'temp_password': new_pwd})
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Reset password error: {e}")
        return jsonify({'error': 'Operation failed.'}), 500
    finally:
        cursor.close()

@user_mgmt_bp.route('/toggle_status/<int:user_id>', methods=['POST'])
@has_permission('manage_users')
def toggle_status(user_id):
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("SELECT status, role FROM users WHERE id = %s", [user_id])
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'User not found.'}), 404
        if row[1] == 'Super Admin':
            return jsonify({'error': 'Cannot change status for Super Admin.'}), 403
        new_status = 'inactive' if row[0] == 'active' else 'active'
        cursor.execute("UPDATE users SET status = %s WHERE id = %s", [new_status, user_id])
        mysql.connection.commit()
        log_activity(session['user_id'], 'toggle_status', f'User ID {user_id} -> {new_status}')
        return jsonify({'message': 'Status updated.', 'status': new_status})
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Toggle status error: {e}")
        return jsonify({'error': 'Operation failed.'}), 500
    finally:
        cursor.close()

@user_mgmt_bp.route('/export')
@has_permission('view_users')
def export_users():
    # Reuse the same filters as manage_users
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')

    conditions = []
    params = []
    if role_filter:
        conditions.append("u.role = %s")
        params.append(role_filter)
    if status_filter:
        conditions.append("u.status = %s")
        params.append(status_filter)
    if search:
        conditions.append("(u.username LIKE %s)")
        params.append(f"%{search}%")

    query = """
        SELECT u.id, u.username, u.role, u.status, u.last_login
        FROM users u
    """
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY u.username"

    cursor = mysql.connection.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Username', 'Role', 'Status', 'Last Login'])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4]])
    csv_data = output.getvalue()
    output.close()

    from flask import Response
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=users_export.csv'}
    )

@user_mgmt_bp.route('/activity-log/export')
@has_permission('view_users')
def export_activity_log():
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            """
            SELECT l.created_at, u.username, l.activity_type, l.description, l.ip_address, l.user_agent
            FROM user_activity_log l
            JOIN users u ON l.user_id = u.id
            ORDER BY l.created_at DESC
            LIMIT 5000
            """
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Time', 'Username', 'Activity', 'Description', 'IP', 'User Agent'])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5]])
    csv_data = output.getvalue()
    output.close()

    from flask import Response
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=activity_log.csv'}
    )

@user_mgmt_bp.route('/roles/export')
@has_permission('manage_roles')
def export_roles():
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            """
            SELECT r.id, r.name, r.description,
                   GROUP_CONCAT(p.name ORDER BY p.module, p.name SEPARATOR '; ')
            FROM roles r
            LEFT JOIN role_permissions rp ON r.id = rp.role_id
            LEFT JOIN permissions p ON rp.permission_id = p.id
            GROUP BY r.id, r.name, r.description
            ORDER BY r.name
            """
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Role', 'Description', 'Permissions'])
    for r in rows:
        writer.writerow([r[0], r[1], r[2] or '', r[3] or ''])
    csv_data = output.getvalue()
    output.close()

    from flask import Response
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=roles.csv'}
    )


# -------- User Permissions Management --------

@user_mgmt_bp.route('/permissions/<int:user_id>')
@has_permission('manage_users')
def manage_user_permissions(user_id):
    """Manage individual permissions for a specific user"""
    cursor = mysql.connection.cursor()
    try:
        # Get user info
        cursor.execute("""
            SELECT id, username, role, department_id, is_hod 
            FROM users WHERE id = %s
        """, [user_id])
        user_tuple = cursor.fetchone()
        if not user_tuple:
            flash('User not found.', 'danger')
            return redirect(url_for('user_mgmt_bp.manage_users'))
        
        # Convert user tuple to dictionary for easier template handling
        user = {
            'id': user_tuple[0],
            'username': user_tuple[1],
            'role': user_tuple[2],
            'department_id': user_tuple[3],
            'is_hod': user_tuple[4]
        }
        
        # Get department name if user has one
        if user['department_id']:
            cursor.execute("SELECT name FROM departments WHERE id = %s", [user['department_id']])
            dept_result = cursor.fetchone()
            user['department_name'] = dept_result[0] if dept_result else None
        else:
            user['department_name'] = None
        
        # Get user's current permissions
        user_permissions_raw = get_user_permissions(user_id)
        
        # Convert permissions tuples to dictionaries for easier template handling
        user_permissions = []
        for perm in user_permissions_raw:
            user_permissions.append({
                'name': perm[0],
                'description': perm[1],
                'module': perm[2] or 'General',
                'source': perm[3],
                'department_id': perm[4],
                'expires_at': perm[5] if len(perm) > 5 else None
            })
        
        # Get all available permissions grouped by module
        cursor.execute("""
            SELECT id, name, description, module 
            FROM permissions 
            ORDER BY module, name
        """)
        all_permissions_raw = cursor.fetchall()
        
        # Convert permissions to dictionaries and group by module
        permissions_by_module = {}
        for perm_tuple in all_permissions_raw:
            perm = {
                'id': perm_tuple[0],
                'name': perm_tuple[1],
                'description': perm_tuple[2],
                'module': perm_tuple[3] or 'General'
            }
            module = perm['module']
            if module not in permissions_by_module:
                permissions_by_module[module] = []
            permissions_by_module[module].append(perm)
        
        # Get available departments for department-specific permissions
        cursor.execute("SELECT id, name FROM departments ORDER BY name")
        departments_raw = cursor.fetchall()
        departments = [{'id': dept[0], 'name': dept[1]} for dept in departments_raw]
        
        # Get available courses
        cursor.execute("SELECT id, name, department_id FROM courses ORDER BY name")
        courses_raw = cursor.fetchall()
        courses = [{'id': c[0], 'name': c[1], 'department_id': c[2]} for c in courses_raw]
        
        # Get available classes (year levels: FY, SY, TY, Fourth Year)
        cursor.execute("SELECT id, name FROM classes ORDER BY display_order, name")
        classes_raw = cursor.fetchall()
        classes = [{'id': c[0], 'name': c[1]} for c in classes_raw]
        
        # Get permission groups
        cursor.execute("""
            SELECT pg.id, pg.name, pg.description, pg.module,
                   GROUP_CONCAT(p.name ORDER BY p.name) as permissions
            FROM permission_groups pg
            LEFT JOIN permission_group_permissions pgp ON pg.id = pgp.group_id
            LEFT JOIN permissions p ON pgp.permission_id = p.id
            WHERE pg.is_active = TRUE
            GROUP BY pg.id, pg.name, pg.description, pg.module
            ORDER BY pg.module, pg.name
        """)
        permission_groups_raw = cursor.fetchall()
        permission_groups = []
        for group_tuple in permission_groups_raw:
            permission_groups.append({
                'id': group_tuple[0],
                'name': group_tuple[1],
                'description': group_tuple[2],
                'module': group_tuple[3],
                'permissions': group_tuple[4]
            })
        
        # Check which groups user is already assigned to
        cursor.execute("""
            SELECT upg.group_id, upg.department_id, pg.name
            FROM user_permission_groups upg
            JOIN permission_groups pg ON upg.group_id = pg.id
            WHERE upg.user_id = %s AND upg.is_active = TRUE
        """, [user_id])
        user_groups_raw = cursor.fetchall()
        user_groups = []
        for group_tuple in user_groups_raw:
            user_groups.append({
                'group_id': group_tuple[0],
                'department_id': group_tuple[1],
                'name': group_tuple[2]
            })
        
        return render_template(
            'admin/manage_user_permissions.html',
            user=user,
            user_permissions=user_permissions,
            permissions_by_module=permissions_by_module,
            departments=departments,
            courses=courses,
            classes=classes,
            permission_groups=permission_groups,
            user_groups=user_groups
        )
    finally:
        cursor.close()


@user_mgmt_bp.route('/permissions/<int:user_id>/grant', methods=['POST'])
@has_permission('manage_users')
def grant_permission(user_id):
    """Grant a permission to a user"""
    permission_name = request.form.get('permission_name')
    department_id = request.form.get('department_id')
    course_id = request.form.get('course_id')
    class_id = request.form.get('class_id')
    expires_at = request.form.get('expires_at')
    notes = request.form.get('notes')
    
    if not permission_name:
        return jsonify({'error': 'Permission name is required'}), 400
    
    # Convert empty strings to None
    department_id = int(department_id) if department_id else None
    course_id = int(course_id) if course_id else None
    class_id = int(class_id) if class_id else None
    expires_at = expires_at if expires_at else None
    
    success, message = grant_user_permission(
        user_id=user_id,
        permission_name=permission_name,
        department_id=department_id,
        course_id=course_id,
        class_id=class_id,
        granted_by=session.get('user_id'),
        expires_at=expires_at,
        notes=notes
    )
    
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 400


@user_mgmt_bp.route('/permissions/<int:user_id>/revoke', methods=['POST'])
@has_permission('manage_users')
def revoke_permission(user_id):
    """Revoke a permission from a user"""
    permission_name = request.form.get('permission_name')
    department_id = request.form.get('department_id')
    
    if not permission_name:
        return jsonify({'error': 'Permission name is required'}), 400
    
    department_id = int(department_id) if department_id else None
    
    success, message = revoke_user_permission(
        user_id=user_id,
        permission_name=permission_name,
        department_id=department_id,
        revoked_by=session.get('user_id')
    )
    
    if success:
        return jsonify({'message': message})
    else:
        return jsonify({'error': message}), 400


@user_mgmt_bp.route('/permissions/<int:user_id>/grant_group', methods=['POST'])
@has_permission('manage_users')
def grant_permission_group(user_id):
    """Grant a permission group to a user"""
    group_id = request.form.get('group_id')
    department_id = request.form.get('department_id')
    
    if not group_id:
        return jsonify({'error': 'Permission group is required'}), 400
    
    cursor = mysql.connection.cursor()
    try:
        # Convert empty strings to None
        department_id = int(department_id) if department_id else None
        group_id = int(group_id)
        
        # Check if already assigned
        cursor.execute("""
            SELECT id FROM user_permission_groups 
            WHERE user_id = %s AND group_id = %s 
            AND (department_id = %s OR (department_id IS NULL AND %s IS NULL))
            AND is_active = TRUE
        """, [user_id, group_id, department_id, department_id])
        
        if cursor.fetchone():
            return jsonify({'error': 'Permission group already assigned'}), 400
        
        # Insert new group assignment
        cursor.execute("""
            INSERT INTO user_permission_groups 
            (user_id, group_id, department_id, granted_by)
            VALUES (%s, %s, %s, %s)
        """, [user_id, group_id, department_id, session.get('user_id')])
        
        mysql.connection.commit()
        
        # Get group name for logging
        cursor.execute("SELECT name FROM permission_groups WHERE id = %s", [group_id])
        group_name = cursor.fetchone()[0]
        
        log_activity(
            session['user_id'],
            'grant_permission_group',
            f'Granted permission group {group_name} to user {user_id}' + 
            (f' for department {department_id}' if department_id else '')
        )
        
        return jsonify({'message': 'Permission group granted successfully'})
        
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error granting permission group: {str(e)}")
        return jsonify({'error': 'Failed to grant permission group'}), 500
    finally:
        cursor.close()


@user_mgmt_bp.route('/permissions/<int:user_id>/revoke_group', methods=['POST'])
@has_permission('manage_users')
def revoke_permission_group(user_id):
    """Revoke a permission group from a user"""
    group_id = request.form.get('group_id')
    department_id = request.form.get('department_id')
    
    if not group_id:
        return jsonify({'error': 'Permission group is required'}), 400
    
    cursor = mysql.connection.cursor()
    try:
        department_id = int(department_id) if department_id else None
        group_id = int(group_id)
        
        # Get group name for logging
        cursor.execute("SELECT name FROM permission_groups WHERE id = %s", [group_id])
        group_result = cursor.fetchone()
        if not group_result:
            return jsonify({'error': 'Permission group not found'}), 404
        
        group_name = group_result[0]
        
        # Delete the group assignment
        cursor.execute("""
            DELETE FROM user_permission_groups 
            WHERE user_id = %s AND group_id = %s 
            AND (department_id = %s OR (department_id IS NULL AND %s IS NULL))
        """, [user_id, group_id, department_id, department_id])
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Permission group assignment not found'}), 404
        
        mysql.connection.commit()
        
        log_activity(
            session['user_id'],
            'revoke_permission_group',
            f'Revoked permission group {group_name} from user {user_id}' + 
            (f' for department {department_id}' if department_id else '')
        )
        
        return jsonify({'message': 'Permission group revoked successfully'})
        
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error revoking permission group: {str(e)}")
        return jsonify({'error': 'Failed to revoke permission group'}), 500
    finally:
        cursor.close()


@user_mgmt_bp.route('/permissions/bulk_grant', methods=['POST'])
@has_permission('manage_users')
def bulk_grant_permissions():
    """Grant permissions to multiple users at once"""
    user_ids = request.form.getlist('user_ids[]') or request.form.getlist('user_ids')
    permission_names = request.form.getlist('permission_names[]') or request.form.getlist('permission_names')
    department_id = request.form.get('department_id')
    
    if not user_ids or not permission_names:
        return jsonify({'error': 'Users and permissions are required'}), 400
    
    department_id = int(department_id) if department_id else None
    granted_by = session.get('user_id')
    
    success_count = 0
    errors = []
    
    for user_id in user_ids:
        for permission_name in permission_names:
            success, message = grant_user_permission(
                user_id=int(user_id),
                permission_name=permission_name,
                department_id=department_id,
                granted_by=granted_by
            )
            if success:
                success_count += 1
            else:
                errors.append(f"User {user_id}, Permission {permission_name}: {message}")
    
    response = {'message': f'Successfully granted {success_count} permissions'}
    if errors:
        response['errors'] = errors
    
    return jsonify(response)


@user_mgmt_bp.route('/permissions/check', methods=['POST'])
@has_permission('view_users')
def check_permission():
    """Check if a user has a specific permission"""
    user_id = request.form.get('user_id')
    permission_name = request.form.get('permission_name')
    department_id = request.form.get('department_id')
    
    if not user_id or not permission_name:
        return jsonify({'error': 'User ID and permission name are required'}), 400
    
    department_id = int(department_id) if department_id else None
    
    has_perm, source, dept_restricted = check_user_permission(
        int(user_id), permission_name, department_id
    )
    
    return jsonify({
        'has_permission': has_perm,
        'source': source,
        'department_restricted': dept_restricted
    })


# -------- Role Management Enhancements --------

@user_mgmt_bp.route('/roles/clone/<int:role_id>', methods=['POST'])
@has_permission('manage_roles')
def clone_role(role_id):
    """Clone an existing role with all its permissions"""
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    
    cursor = mysql.connection.cursor()
    try:
        # Get source role
        cursor.execute('SELECT name, description FROM roles WHERE id = %s', [role_id])
        role = cursor.fetchone()
        if not role:
            return jsonify({'error': 'Role not found.'}), 404
        
        # Create new role name
        new_name = f"{role[0]} (Copy)"
        counter = 1
        while True:
            cursor.execute('SELECT id FROM roles WHERE name = %s', [new_name])
            if not cursor.fetchone():
                break
            counter += 1
            new_name = f"{role[0]} (Copy {counter})"
        
        # Insert new role
        cursor.execute(
            'INSERT INTO roles (name, description) VALUES (%s, %s)',
            [new_name, role[1]]
        )
        new_role_id = cursor.lastrowid
        
        # Copy permissions
        cursor.execute(
            'SELECT permission_id FROM role_permissions WHERE role_id = %s',
            [role_id]
        )
        perms = cursor.fetchall()
        for perm in perms:
            cursor.execute(
                'INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)',
                [new_role_id, perm[0]]
            )
        
        log_activity(
            session['user_id'],
            'clone_role',
            f'Cloned role "{role[0]}" to "{new_name}" (ID: {new_role_id})'
        )
        
        mysql.connection.commit()
        return jsonify({
            'message': 'Role cloned successfully.',
            'new_role_id': new_role_id,
            'new_role_name': new_name
        })
        
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Error cloning role: {str(e)}")
        return jsonify({'error': 'Failed to clone role.'}), 500
    finally:
        cursor.close()


@user_mgmt_bp.route('/roles/bulk_permissions', methods=['POST'])
@has_permission('manage_roles')
def bulk_permissions():
    """Add or remove permissions from multiple roles at once"""
    form = EmptyForm()
    if not form.validate_on_submit():
        return jsonify({'error': 'Invalid request (CSRF).'}), 400
    
    action = request.form.get('action')  # 'add' or 'remove'
    role_ids = request.form.getlist('role_ids[]') or request.form.getlist('role_ids')
    perm_ids = request.form.getlist('permission_ids[]') or request.form.getlist('permission_ids')
    
    if not role_ids or not perm_ids:
        return jsonify({'error': 'No roles or permissions selected.'}), 400
    
    cursor = mysql.connection.cursor()
    try:
        if action == 'add':
            for role_id in role_ids:
                # Skip Super Admin
                cursor.execute('SELECT name FROM roles WHERE id = %s', [role_id])
                role = cursor.fetchone()
                if role and role[0] == 'Super Admin':
                    continue
                    
                for perm_id in perm_ids:
                    # Check if already exists
                    cursor.execute(
                        'SELECT id FROM role_permissions WHERE role_id = %s AND permission_id = %s',
                        [role_id, perm_id]
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            'INSERT INTO role_permissions (role_id, permission_id) VALUES (%s, %s)',
                            [role_id, perm_id]
                        )
            
            mysql.connection.commit()
            log_activity(
                session['user_id'],
                'bulk_add_permissions',
                f'Added permissions to roles: {",".join(role_ids)}'
            )
            return jsonify({'message': 'Permissions added successfully.'})
            
        elif action == 'remove':
            for role_id in role_ids:
                # Skip Super Admin
                cursor.execute('SELECT name FROM roles WHERE id = %s', [role_id])
                role = cursor.fetchone()
                if role and role[0] == 'Super Admin':
                    continue
                    
                for perm_id in perm_ids:
                    cursor.execute(
                        'DELETE FROM role_permissions WHERE role_id = %s AND permission_id = %s',
                        [role_id, perm_id]
                    )
            
            mysql.connection.commit()
            log_activity(
                session['user_id'],
                'bulk_remove_permissions',
                f'Removed permissions from roles: {",".join(role_ids)}'
            )
            return jsonify({'message': 'Permissions removed successfully.'})
        else:
            return jsonify({'error': 'Invalid action.'}), 400
            
    except Exception as e:
        mysql.connection.rollback()
        current_app.logger.error(f"Bulk permissions error: {str(e)}")
        return jsonify({'error': 'Operation failed.'}), 500
    finally:
        cursor.close()


@user_mgmt_bp.route('/roles/stats')
@has_permission('manage_roles')
def role_stats():
    """Get statistics about roles and their usage"""
    cursor = mysql.connection.cursor()
    try:
        # Total roles
        cursor.execute('SELECT COUNT(*) FROM roles')
        total_roles = cursor.fetchone()[0]
        
        # Total permissions
        cursor.execute('SELECT COUNT(*) FROM permissions')
        total_permissions = cursor.fetchone()[0]
        
        # Roles by user count
        cursor.execute("""
            SELECT r.name, COUNT(u.id) as user_count
            FROM roles r
            LEFT JOIN users u ON u.role = r.name
            GROUP BY r.name
            ORDER BY user_count DESC
        """)
        role_usage = cursor.fetchall()
        
        # Permissions distribution
        cursor.execute("""
            SELECT p.module, COUNT(DISTINCT rp.role_id) as role_count
            FROM permissions p
            LEFT JOIN role_permissions rp ON p.id = rp.permission_id
            GROUP BY p.module
            ORDER BY role_count DESC
        """)
        perm_distribution = cursor.fetchall()
        
        # Most common permissions
        cursor.execute("""
            SELECT p.name, p.module, COUNT(rp.role_id) as role_count
            FROM permissions p
            LEFT JOIN role_permissions rp ON p.id = rp.permission_id
            GROUP BY p.id, p.name, p.module
            ORDER BY role_count DESC
            LIMIT 10
        """)
        common_perms = cursor.fetchall()
        
        return jsonify({
            'total_roles': total_roles,
            'total_permissions': total_permissions,
            'role_usage': [{'name': r[0], 'users': r[1]} for r in role_usage],
            'permission_distribution': [{'module': p[0], 'roles': p[1]} for p in perm_distribution],
            'common_permissions': [{'name': p[0], 'module': p[1], 'roles': p[2]} for p in common_perms]
        })
        
    except Exception as e:
        current_app.logger.error(f"Role stats error: {str(e)}")
        return jsonify({'error': 'Failed to fetch statistics.'}), 500
    finally:
        cursor.close()


@user_mgmt_bp.route('/roles/permissions_by_module')
@has_permission('manage_roles')
def permissions_by_module():
    """Get permissions grouped by module for better UI organization"""
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("""
            SELECT module, id, name, description
            FROM permissions
            ORDER BY module, name
        """)
        all_perms = cursor.fetchall()
        
        # Group by module
        by_module = {}
        for perm in all_perms:
            module = perm[0] or 'General'
            if module not in by_module:
                by_module[module] = []
            by_module[module].append({
                'id': perm[1],
                'name': perm[2],
                'description': perm[3]
            })
        
        return jsonify(by_module)
        
    except Exception as e:
        current_app.logger.error(f"Permissions by module error: {str(e)}")
        return jsonify({'error': 'Failed to fetch permissions.'}), 500
    finally:
        cursor.close()