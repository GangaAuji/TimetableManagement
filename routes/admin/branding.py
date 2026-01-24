from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename
import os
from functools import wraps
from database import get_db_connection

branding_bp = Blueprint('branding', __name__, url_prefix='/admin/branding')
mysql = MySQL()

def has_permission(permission_name):
    """Decorator to check if user has specific permission"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'danger')
                return redirect(url_for('auth.login'))
            
            user_role = session.get('role')
            if user_role == 'Super Admin':
                return f(*args, **kwargs)
            
            from security import check_user_permission
            user_id = session.get('user_id')
            has_perm, _, _ = check_user_permission(user_id, permission_name)
            
            if not has_perm:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('auth.dashboard'))
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_branding_settings():
    """Initialize branding settings table if not exists"""
    # Check if MySQL connection is available
    try:
        connection = get_db_connection()
    except:
        current_app.logger.warning("MySQL connection not available, skipping branding initialization")
        return
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS branding_settings (
                id INT PRIMARY KEY AUTO_INCREMENT,
                setting_key VARCHAR(100) UNIQUE NOT NULL,
                setting_value TEXT,
                setting_type VARCHAR(50) DEFAULT 'text',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        
        # Insert default values if not exist
        default_settings = [
            ('site_title', 'Timetable Management System', 'text'),
            ('login_title', 'Welcome Back', 'text'),
            ('admin_title', 'Admin Dashboard', 'text'),
            ('student_title', 'Student Portal', 'text'),
            ('teacher_title', 'Teacher Portal', 'text'),
            ('tagline', 'Efficient Scheduling Made Simple', 'text'),
            ('copyright_text', '© 2025 All rights reserved', 'text'),
            ('welcome_message', 'Welcome to our academic management system', 'text'),
            ('support_email', 'support@institution.edu', 'text'),
            ('support_phone', '+1 234 567 8900', 'text'),
            ('footer_text', 'Powered by Timetable Management System', 'text'),
            ('site_logo', '', 'image'),
            ('login_logo', '', 'image'),
            ('favicon', '', 'image'),
            ('primary_color', '#059669', 'color'),
            ('secondary_color', '#10b981', 'color'),
            ('accent_color', '#047857', 'color'),
            ('sidebar_bg', '#111827', 'color'),
            ('header_bg', '#ffffff', 'color'),
        ]
        
        for key, value, stype in default_settings:
            cursor.execute(
                "INSERT IGNORE INTO branding_settings (setting_key, setting_value, setting_type) VALUES (%s, %s, %s)",
                (key, value, stype)
            )
        
        connection.commit()
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error initializing branding settings: {str(e)}")
    finally:
        cursor.close()

@branding_bp.route('/')
@has_permission('admin_view_settings')
def manage_branding():
    """Display branding settings page"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT setting_key, setting_value, setting_type FROM branding_settings ORDER BY setting_key")
        settings_list = cursor.fetchall()
        
        # Convert to dictionary for easier template access
        settings = {}
        for key, value, stype in settings_list:
            settings[key] = {'value': value, 'type': stype}
        
    except Exception as e:
        current_app.logger.error(f"Error fetching branding settings: {str(e)}")
        settings = {}
    finally:
        cursor.close()
    
    return render_template('admin/manage_branding.html', settings=settings)

@branding_bp.route('/update', methods=['POST'])
@has_permission('admin_change_settings')
def update_branding():
    """Update branding settings"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Handle text settings
        text_settings = [
            'site_title', 'login_title', 'admin_title', 
            'student_title', 'teacher_title', 'tagline',
            'copyright_text', 'welcome_message', 'support_email',
            'support_phone', 'footer_text'
        ]
        
        for setting in text_settings:
            value = request.form.get(setting, '').strip()
            cursor.execute(
                "UPDATE branding_settings SET setting_value = %s WHERE setting_key = %s",
                (value, setting)
            )
        
        # Handle color settings
        color_settings = [
            'primary_color', 'secondary_color', 'accent_color',
            'sidebar_bg', 'header_bg'
        ]
        
        for setting in color_settings:
            value = request.form.get(setting, '').strip()
            cursor.execute(
                "UPDATE branding_settings SET setting_value = %s WHERE setting_key = %s",
                (value, setting)
            )
        
        # Handle file uploads
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'branding')
        os.makedirs(upload_folder, exist_ok=True)
        
        file_settings = ['site_logo', 'login_logo', 'favicon']
        
        for setting in file_settings:
            if setting in request.files:
                file = request.files[setting]
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Add timestamp to avoid conflicts
                    from datetime import datetime
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    filename = f"{setting}_{timestamp}_{filename}"
                    
                    filepath = os.path.join(upload_folder, filename)
                    file.save(filepath)
                    
                    # Store relative path in database
                    relative_path = f"uploads/branding/{filename}"
                    cursor.execute(
                        "UPDATE branding_settings SET setting_value = %s WHERE setting_key = %s",
                        (relative_path, setting)
                    )
        
        connection.commit()
        flash('Branding settings updated successfully!', 'success')
        
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error updating branding settings: {str(e)}")
        flash('Error updating branding settings. Please try again.', 'danger')
    finally:
        cursor.close()
    
    return redirect(url_for('branding.manage_branding'))

@branding_bp.route('/reset', methods=['POST'])
@has_permission('admin_change_settings')
def reset_branding():
    """Reset branding to default values"""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        default_values = {
            'site_title': 'Timetable Management System',
            'login_title': 'Welcome Back',
            'admin_title': 'Admin Dashboard',
            'student_title': 'Student Portal',
            'teacher_title': 'Teacher Portal',
            'tagline': 'Efficient Scheduling Made Simple',
            'copyright_text': '© 2025 All rights reserved',
            'welcome_message': 'Welcome to our academic management system',
            'support_email': 'support@institution.edu',
            'support_phone': '+1 234 567 8900',
            'footer_text': 'Powered by Timetable Management System',
            'primary_color': '#059669',
            'secondary_color': '#10b981',
            'accent_color': '#047857',
            'sidebar_bg': '#111827',
            'header_bg': '#ffffff',
        }
        
        for key, value in default_values.items():
            cursor.execute(
                "UPDATE branding_settings SET setting_value = %s WHERE setting_key = %s",
                (value, key)
            )
        
        connection.commit()
        flash('Branding settings reset to defaults!', 'success')
        
    except Exception as e:
        connection.rollback()
        current_app.logger.error(f"Error resetting branding: {str(e)}")
        flash('Error resetting branding settings.', 'danger')
    finally:
        cursor.close()
    
    return redirect(url_for('branding.manage_branding'))

# Initialize settings on module load
_initialized = False

def init_app(app):
    """Initialize branding module with app"""
    @app.before_request
    def ensure_branding_initialized():
        """Ensure branding settings are initialized on first request"""
        global _initialized
        if not _initialized:
            try:
                init_branding_settings()
                _initialized = True
            except Exception as e:
                app.logger.error(f"Error during branding initialization: {str(e)}")
                # Don't fail requests if branding init fails
