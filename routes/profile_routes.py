from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from app import mysql
from security import log_activity
import os
from datetime import datetime

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@profile_bp.route('/')
def view_profile():
    """View current user's profile"""
    if 'user_id' not in session:
        flash('Please login to view your profile', 'error')
        return redirect(url_for('auth.login'))
    
    cursor = mysql.connection.cursor()
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
            'id': user_data[0],
            'username': user_data[1],
            'role': user_data[2],
            'email': user_data[3],
            'profile_photo': user_data[4] if user_data[4] else 'default-avatar.svg',
            'phone': user_data[5],
            'address': user_data[6],
            'bio': user_data[7],
            'date_of_birth': user_data[8],
            'status': user_data[9] or 'active',
            'last_login': user_data[10],
            'created_at': user_data[11],
            'department_id': user_data[12],
            'is_hod': user_data[13] or False,
            'department_name': None
        }
        
        # Get department name if department_id exists
        if user['department_id']:
            cursor.execute("SELECT name FROM departments WHERE id = %s", [user['department_id']])
            dept_result = cursor.fetchone()
            if dept_result:
                user['department_name'] = dept_result[0]
        
        # Get role-specific data (for additional info if needed)
        if user_role == 'Teacher':
            cursor.execute("""
                SELECT f.email FROM faculty f WHERE f.user_id = %s
            """, [session['user_id']])
            faculty_data = cursor.fetchone()
            # Use faculty email if user email is not set
            if faculty_data and faculty_data[0] and not user['email']:
                user['email'] = faculty_data[0]
                
        elif user_role == 'Student':
            cursor.execute("""
                SELECT s.email FROM students s WHERE s.user_id = %s
            """, [session['user_id']])
            student_data = cursor.fetchone()
            # Use student email if user email is not set
            if student_data and student_data[0] and not user['email']:
                user['email'] = student_data[0]
        
        return render_template('profile/user_profile.html', user=user)
    finally:
        cursor.close()

@profile_bp.route('/edit', methods=['GET', 'POST'])
def edit_profile():
    """Edit current user's profile"""
    if 'user_id' not in session:
        flash('Please login to edit your profile', 'error')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        bio = request.form.get('bio')
        date_of_birth = request.form.get('date_of_birth')
        user_role = session.get('role')
        
        cursor = mysql.connection.cursor()
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
            
            mysql.connection.commit()
            
            # Update session with new profile photo if uploaded
            if profile_photo:
                session['profile_photo'] = profile_photo
            
            log_activity(session['user_id'], 'update_profile', 'Updated user profile')
            flash('Profile updated successfully', 'success')
            return redirect(url_for('profile.view_profile'))
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
        finally:
            cursor.close()
    
    # GET request - show edit form
    cursor = mysql.connection.cursor()
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
            'id': user_data[0],
            'username': user_data[1],
            'email': user_data[2],
            'role': user_data[3],
            'phone': user_data[4],
            'address': user_data[5],
            'bio': user_data[6],
            'date_of_birth': user_data[7],
            'profile_photo': user_data[8] or 'default-avatar.png',
            'department_name': user_data[9]
        }
        
        return render_template('profile/edit.html', user=user)
    finally:
        cursor.close()

@profile_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    """Change user password"""
    if 'user_id' not in session:
        flash('Please login to change your password', 'error')
        return redirect(url_for('auth.login'))
    
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
        
        cursor = mysql.connection.cursor()
        try:
            # Verify current password
            from werkzeug.security import check_password_hash
            cursor.execute("SELECT password FROM users WHERE id = %s", [session['user_id']])
            result = cursor.fetchone()
            
            if not result or not check_password_hash(result[0], current_password):
                flash('Current password is incorrect', 'error')
                return redirect(url_for('profile.change_password'))
            
            # Update password
            hashed_password = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", 
                         [hashed_password, session['user_id']])
            mysql.connection.commit()
            
            log_activity(session['user_id'], 'change_password', 'Changed password')
            flash('Password changed successfully', 'success')
            return redirect(url_for('profile.view_profile'))
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Error changing password: {str(e)}', 'error')
        finally:
            cursor.close()
    
    return render_template('profile/change_password.html')
