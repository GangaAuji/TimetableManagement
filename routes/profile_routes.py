from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from database import get_db_connection
from security import log_activity, login_required
import os
from datetime import datetime

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@profile_bp.route('/')
@login_required
def view_profile():
    """View current user's profile"""
    connection = get_db_connection()

    
    cursor = connection.cursor(dictionary=True)
    try:
        user_role = session.get('role')
        
        # Base user query - now includes email from users table
        cursor.execute("""
            SELECT u.id, u.username, u.role, u.email,
                   u.profile_photo, u.phone, u.address, 
                   u.bio, u.date_of_birth, u.status, u.last_login, 
                   u.created_at, u.department_id, u.is_hod
            FROM users u
            WHERE u.id = %s
        """, [session['user_id']])
        user_data = cursor.fetchone()
        
        if not user_data:
            flash('User not found', 'error')
            return redirect(url_for('auth.login'))
        
        # Initialize user dict with base data
        user = {
            'id': user_data['id'],
            'username': user_data['username'],
            'role': user_data['role'],
            'email': user_data['email'],
            'profile_photo': user_data['profile_photo'] if user_data['profile_photo'] else 'default-avatar.svg',
            'phone': user_data['phone'],
            'address': user_data['address'],
            'bio': user_data['bio'],
            'date_of_birth': user_data['date_of_birth'],
            'status': user_data['status'] or 'active',
            'last_login': user_data['last_login'],
            'created_at': user_data['created_at'],
            'department_id': user_data['department_id'],
            'is_hod': user_data['is_hod'] or False,
            'department_name': None
        }
        
        # Get department name if department_id exists
        if user['department_id']:
            cursor.execute("SELECT name FROM departments WHERE id = %s", [user['department_id']])
            dept_result = cursor.fetchone()
            if dept_result:
                user['department_name'] = dept_result['name']
        
        # Get role-specific data (for additional info if needed)
        if user_role == 'Teacher':
            cursor.execute("""
                SELECT f.email FROM faculty f WHERE f.user_id = %s
            """, [session['user_id']])
            faculty_data = cursor.fetchone()
            # Use faculty email if user email is not set
            if faculty_data and faculty_data['email'] and not user['email']:
                user['email'] = faculty_data['email']
                
        elif user_role == 'Student':
            cursor.execute("""
                SELECT s.email FROM students s WHERE s.user_id = %s
            """, [session['user_id']])
            student_data = cursor.fetchone()
            # Use student email if user email is not set
            if student_data and student_data['email'] and not user['email']:
                user['email'] = student_data['email']
        
        return render_template('profile/user_profile.html', user=user)
    finally:

        cursor.close()

        connection.close()

@profile_bp.route('/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit current user's profile"""
    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        bio = request.form.get('bio')
        date_of_birth = request.form.get('date_of_birth')
        user_role = session.get('role')
        
        connection = get_db_connection()

        
        cursor = connection.cursor(dictionary=True)
        try:
            # Handle profile photo upload
            profile_photo = None
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    if allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        # Add timestamp to filename to avoid conflicts
                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                        filename = f"{session['user_id']}_{timestamp}_{filename}"
                        
                        # Create uploads/profiles directory if it doesn't exist
                        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
                        os.makedirs(upload_folder, exist_ok=True)
                        
                        filepath = os.path.join(upload_folder, filename)
                        file.save(filepath)
                        profile_photo = f"uploads/profiles/{filename}"
                    else:
                        flash('Invalid file type. Only PNG, JPG, JPEG, and GIF images are allowed.', 'danger')
                        return redirect(url_for('profile.view_profile'))
            
            # Update users table (email, profile photo, phone, address, bio, date_of_birth)
            if profile_photo:
                cursor.execute("""
                    UPDATE users 
                    SET email = %s, phone = %s, address = %s, bio = %s, 
                        date_of_birth = %s, profile_photo = %s
                    WHERE id = %s
                """, [email, phone, address, bio, date_of_birth or None, profile_photo, session['user_id']])
            else:
                cursor.execute("""
                    UPDATE users 
                    SET email = %s, phone = %s, address = %s, bio = %s, date_of_birth = %s
                    WHERE id = %s
                """, [email, phone, address, bio, date_of_birth or None, session['user_id']])
            
            # Also update email in role-specific table for sync
            if user_role == 'Teacher':
                cursor.execute("""
                    UPDATE faculty 
                    SET email = %s
                    WHERE user_id = %s
                """, [email, session['user_id']])
            elif user_role == 'Student':
                cursor.execute("""
                    UPDATE students 
                    SET email = %s
                    WHERE user_id = %s
                """, [email, session['user_id']])
            
            connection.commit()
            
            # Update session with new profile photo if uploaded
            if profile_photo:
                session['profile_photo'] = profile_photo
            
            log_activity(session['user_id'], 'update_profile', 'Updated user profile')
            flash('Profile updated successfully', 'success')
            return redirect(url_for('profile.view_profile'))
        except Exception as e:
            connection.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
        finally:

            cursor.close()

            connection.close()
    
    # GET request - show edit form
    connection = get_db_connection()

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.role, u.phone, u.address, 
                   u.bio, u.date_of_birth, u.profile_photo,
                   d.name as department_name
            FROM users u
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE u.id = %s
        """, [session['user_id']])
        user_data = cursor.fetchone()
        
        if not user_data:
            flash('User not found', 'error')
            return redirect(url_for('auth.login'))
        
        user = {
            'id': user_data['id'],
            'username': user_data['username'],
            'email': user_data['email'],
            'role': user_data['role'],
            'phone': user_data['phone'],
            'address': user_data['address'],
            'bio': user_data['bio'],
            'date_of_birth': user_data['date_of_birth'],
            'profile_photo': user_data['profile_photo'] or 'default-avatar.png',
            'department_name': user_data['dept_name']
        }
        
        return render_template('profile/edit.html', user=user)
    finally:

        cursor.close()

        connection.close()

@profile_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('profile.change_password'))
        
        if len(new_password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return redirect(url_for('profile.change_password'))
        
        connection = get_db_connection()

        
        cursor = connection.cursor(dictionary=True)
        try:
            # Verify current password
            from werkzeug.security import check_password_hash
            cursor.execute("SELECT password FROM users WHERE id = %s", [session['user_id']])
            result = cursor.fetchone()
            
            if not result or not check_password_hash(result['password'], current_password):
                flash('Current password is incorrect', 'error')
                return redirect(url_for('profile.change_password'))
            
            # Update password
            hashed_password = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", 
                         [hashed_password, session['user_id']])
            connection.commit()
            
            log_activity(session['user_id'], 'change_password', 'Changed password')
            flash('Password changed successfully', 'success')
            return redirect(url_for('profile.view_profile'))
        except Exception as e:
            connection.rollback()
            flash(f'Error changing password: {str(e)}', 'error')
        finally:

            cursor.close()

            connection.close()
    
    return render_template('profile/change_password.html')
