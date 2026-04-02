from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from forms import LoginForm, RegistrationForm
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db
from security import log_activity, log_login_attempt
import secrets
import json
import os
import base64
import binascii
import math
from datetime import datetime, timedelta
from config import Config

auth_bp = Blueprint('auth', __name__)
EXPECTED_FACE_TEMPLATE_LENGTH = 192
DEFAULT_FACE_TEMPLATE_VERSION = 'mobilefacenet_192_l2_v1'


def _parse_face_template_json(raw_json):
    if not raw_json:
        return None

    try:
        parsed = json.loads(raw_json)
    except Exception:
        return None

    if not isinstance(parsed, list) or len(parsed) != EXPECTED_FACE_TEMPLATE_LENGTH:
        return None

    normalized = []
    sum_sq = 0.0
    for value in parsed:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        normalized.append(number)
        sum_sq += number * number

    norm = math.sqrt(sum_sq)
    if norm <= 0.0:
        return None

    return [value / norm for value in normalized]


def _parse_optional_float(raw_value):
    if raw_value in (None, ""):
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _decode_captured_face_data(data_url):
    if not data_url or not isinstance(data_url, str):
        return None

    if not data_url.startswith('data:image/'):
        return None

    parts = data_url.split(',', 1)
    if len(parts) != 2:
        return None

    header, encoded = parts
    if ';base64' not in header:
        return None

    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return None


def _generate_employee_id(user_id):
    return f"EMP{datetime.now().year}{user_id:06d}"

@auth_bp.route('/')
def home():
    if 'user_id' in session:
        role = session.get('role')
        if role in ('Admin', 'Super Admin'):
            return redirect(url_for('admin.dashboard'))
        elif role == 'Teacher':
            return redirect(url_for('teacher.dashboard'))
        elif role == 'Student':
            return redirect(url_for('student.dashboard'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        db, cursor = get_db()
        # Exclude Admin and Super Admin from regular login; they should use admin login
        cursor.execute("SELECT id, password, role, status FROM users WHERE username = %s AND role NOT IN ('Admin', 'Super Admin')", (username,))
        user = cursor.fetchone()

        if user is None:
            flash("User not found.", "danger")
            return render_template('login.html', form=form)
        
        # Check if user account is active
        if user['status'] == 'inactive':
            flash("Your account has been deactivated. Please contact the administrator for assistance.", "warning")
            return render_template('login.html', form=form)
        elif user['status'] == 'locked':
            flash("Your account has been locked due to security reasons. Please contact the administrator.", "danger")
            return render_template('login.html', form=form)

        # Compare passwords
        password_ok = check_password_hash(user['password'], password)

        if password_ok:
            session['user_id'] = user['id']
            session['username'] = username
            session['role'] = user['role']
            
            # Generate session ID
            import uuid
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            
            # Create session entry in user_sessions table
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(days=7)  # 7 days expiry
            cursor.execute("""
                INSERT INTO user_sessions 
                (session_id, user_id, ip_address, user_agent, expires_at, is_active) 
                VALUES (%s, %s, %s, %s, %s, 1)
            """, (session_id, user['id'], request.remote_addr, request.user_agent.string, expires_at))
            
            # Log successful login
            log_login_attempt(username, 'success')
            log_activity(user['id'], 'login', f'User {username} logged in as {user["role"]}')
            
            # Update last_login timestamp
            cursor.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user['id'],))
            db.commit()
            
            # Get additional user information including department and profile photo
            cursor.execute("SELECT department_id, is_hod, profile_photo FROM users WHERE id = %s", (user['id'],))
            user_details = cursor.fetchone()
            if user_details:
                session['department_id'] = user_details['department_id']
                session['is_hod'] = user_details['is_hod']
                session['profile_photo'] = user_details['profile_photo'] if user_details['profile_photo'] else 'default-avatar.svg'
            else:
                session['department_id'] = None
                session['is_hod'] = False
                session['profile_photo'] = 'default-avatar.svg'
            
            # Fetch details from role-specific tables
            # Note: Without user_id FK, we'll fetch the first matching record
            # This is a temporary solution until proper user_id linkage is added
            if user['role'] == 'Student':
                # Prefer user-scoped student mapping, but fall back gracefully if schema/data is missing
                student = None
                used_fallback = False
                try:
                    cursor.execute(
                        "SELECT id, name, email, course_id, class_id, division_id FROM students WHERE user_id = %s",
                        (user['id'],)
                    )
                    student = cursor.fetchone()
                except Exception as e:
                    current_app.logger.warning("Student mapping by user_id failed: %s", e)
                if not student:
                    used_fallback = True
                    cursor.execute(
                        "SELECT id, name, email, course_id, class_id, division_id FROM students LIMIT 1"
                    )
                    student = cursor.fetchone()
                if student:
                    session['student_id'] = student['id']
                    session['name'] = student['name']
                    session['email'] = student['email']
                    session['course_id'] = student['course_id']
                    session['class_id'] = student['class_id']
                    session['division_id'] = student['division_id']
                    if used_fallback:
                        flash("Your account isn't linked to a student profile yet. Showing default student data. Ask admin to link your user.", "warning")
                else:
                    # No student profile found at all
                    session['name'] = username
            elif user['role'] == 'Teacher':
                # Prefer user-scoped faculty mapping, but fall back gracefully if schema/data is missing
                faculty = None
                used_fallback = False
                try:
                    cursor.execute(
                        "SELECT id, name, email, department_id FROM faculty WHERE user_id = %s",
                        (user['id'],)
                    )
                    faculty = cursor.fetchone()
                except Exception as e:
                    current_app.logger.warning("Teacher mapping by user_id failed: %s", e)
                if not faculty:
                    used_fallback = True
                    cursor.execute(
                        "SELECT id, name, email, department_id FROM faculty LIMIT 1"
                    )
                    faculty = cursor.fetchone()
                if faculty:
                    session['faculty_id'] = faculty['id']
                    session['name'] = faculty['name']
                    session['email'] = faculty['email']
                    session['department_id'] = faculty['department_id']
                    if used_fallback:
                        flash("Your account isn't linked to a teacher profile yet. Showing default teacher data. Ask admin to link your user.", "warning")
                else:
                    # No faculty profile found at all
                    session['name'] = username
            
            return redirect(url_for('auth.home'))
        else:
            # Log failed login attempt
            log_login_attempt(username, 'failed', 'Invalid password')
            flash("Invalid credentials for Student/Teacher.", "danger")
    return render_template('login.html', form=form)

@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        db, cursor = get_db()
        # Allow users with admin roles (Admin, Super Admin, HOD) to use the admin login
        cursor.execute("SELECT id, password, role, status FROM users WHERE username = %s AND role IN ('Admin', 'Super Admin', 'HOD')", (username,))
        user = cursor.fetchone()

        # Debug logging
        current_app.logger.debug(f"Login attempt for username: {username}")
        current_app.logger.debug(f"User found in database: {user is not None}")
        if user:
            current_app.logger.debug(f"User data: id={user['id']}, role={user['role']}, status={user.get('status', 'active')}")

        if user is None:
            flash("Admin user not found or not authorized.", "danger")
            return render_template('admin_login.html', form=form)
        
        # Check if admin account is active
        if user.get('status') == 'inactive':
            flash("Your admin account has been deactivated. Please contact the system administrator.", "warning")
            return render_template('admin_login.html', form=form)
        elif user.get('status') == 'locked':
            flash("Your admin account has been locked due to security reasons. Please contact the system administrator.", "danger")
            return render_template('admin_login.html', form=form)

        try:
            # Compare passwords
            password_ok = check_password_hash(user['password'], password)
            current_app.logger.debug(f"Password verification result: {password_ok}")
        except Exception as e:
            current_app.logger.error(f"Error checking password: {str(e)}")
            flash("An error occurred during login.", "danger")
            return render_template('admin_login.html', form=form)

        if password_ok:
            session['user_id'] = user['id']
            session['username'] = username
            session['role'] = user['role']
            
            # Generate session ID
            import uuid
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            
            # Create session entry in user_sessions table
            from datetime import datetime, timedelta
            expires_at = datetime.now() + timedelta(days=7)  # 7 days expiry
            cursor.execute("""
                INSERT INTO user_sessions 
                (session_id, user_id, ip_address, user_agent, expires_at, is_active) 
                VALUES (%s, %s, %s, %s, %s, 1)
            """, (session_id, user['id'], request.remote_addr, request.user_agent.string, expires_at))
            
            # Log successful admin login
            log_login_attempt(username, 'success')
            log_activity(user['id'], 'admin_login', f'Admin {username} logged in with role {user["role"]}')
            
            # Update last_login timestamp
            cursor.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user['id'],))
            db.commit()
            
            # Get additional user information including department and profile photo
            cursor.execute("SELECT department_id, is_hod, profile_photo FROM users WHERE id = %s", (user['id'],))
            user_details = cursor.fetchone()
            if user_details:
                session['department_id'] = user_details['department_id']
                session['is_hod'] = user_details['is_hod']
                session['profile_photo'] = user_details['profile_photo'] if user_details['profile_photo'] else 'default-avatar.svg'
            else:
                session['department_id'] = None
                session['is_hod'] = False
                session['profile_photo'] = 'default-avatar.svg'
            
            # Admins can optionally have a name stored directly (for display purposes)
            # but they typically don't need role-specific table lookups like students/faculty
            session['name'] = username  # Default to username for admins
            
            return redirect(url_for('admin.dashboard'))
        else:
            # Log failed admin login attempt
            log_login_attempt(username, 'failed', 'Invalid admin password')
            flash("Invalid Admin credentials.", "danger")
    # Log request details on POST for debugging CSRF/missing token issues
    if request.method == 'POST':
        try:
            current_app.logger.debug('admin_login POST - form data: %s', request.form)
            current_app.logger.debug('admin_login POST - cookies: %s', request.cookies)
            current_app.logger.debug('admin_login POST - headers: %s', dict(request.headers))
        except Exception as e:
            current_app.logger.debug('Error logging request details: %s', e)
    return render_template('admin_login.html', form=form)

@auth_bp.route('/logout')
def logout():
    # Log logout and deactivate session before clearing
    if 'user_id' in session:
        log_activity(session['user_id'], 'logout', f"User {session.get('username', 'unknown')} logged out")
        
        # Mark session as inactive in database
        if 'session_id' in session:
            from database import get_db
            db, cursor = get_db()
            cursor.execute("""
                UPDATE user_sessions 
                SET is_active = 0 
                WHERE session_id = %s
            """, (session['session_id'],))
            db.commit()
            cursor.close()
    
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('auth.login'))

@auth_bp.route('/register/<token>', methods=['GET', 'POST'])
def register(token):
    """Invitation-based registration - requires valid token from admin"""
    db, cursor = get_db()
    
    # Validate token
    cursor.execute("""
        SELECT id, email, role, name, course_id, class_id, division_id, department_id, expires_at, status
        FROM registration_invitations 
        WHERE token = %s
    """, (token,))
    invitation = cursor.fetchone()
    
    if not invitation:
        flash("Invalid registration link. Please contact your administrator.", "danger")
        return redirect(url_for('auth.login'))
    
    # Check if already used
    if invitation['status'] == 'used':
        flash("This invitation has already been used.", "warning")
        return redirect(url_for('auth.login'))
    
    # Check if expired
    if datetime.now() > invitation['expires_at']:
        cursor.execute("UPDATE registration_invitations SET status = 'expired' WHERE id = %s", (invitation['id'],))
        db.commit()
        flash("This invitation has expired. Please request a new one.", "danger")
        return redirect(url_for('auth.login'))
    
    form = RegistrationForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            flash("Username already exists. Please choose a different one.", "danger")
            return render_template('register.html', form=form, invitation=invitation, token=token)
        
        # Check if email already registered
        if invitation['role'] == 'Student':
            cursor.execute("SELECT id FROM students WHERE email = %s", (invitation['email'],))
        else:
            cursor.execute("SELECT id FROM faculty WHERE email = %s", (invitation['email'],))
        
        if cursor.fetchone():
            flash("This email is already registered. Please contact your administrator.", "danger")
            return render_template('register.html', form=form, invitation=invitation, token=token)
        
        # Hash password
        hashed_password = generate_password_hash(password)
        
        try:
            # Optional face image from registration form
            face_image_path = None
            face_capture_data = (request.form.get('face_capture_data') or '').strip()
            captured_bytes = _decode_captured_face_data(face_capture_data)

            raw_face_template = (
                request.form.get('face_template_json')
                or request.form.get('face_template')
                or request.form.get('embedding')
                or request.form.get('face_embedding')
                or request.form.get('face_embeddings')
                or request.form.get('embedding_vector')
                or request.form.get('face_vector')
                or request.form.get('face_descriptor')
                or ''
            ).strip()

            face_template = _parse_face_template_json(raw_face_template)
            if raw_face_template and face_template is None:
                flash(
                    "Invalid face embedding format. Expected 192 numeric values from mobilefacenet.tflite.",
                    "danger"
                )
                return render_template('register.html', form=form, invitation=invitation, token=token)

            embedding_version = (
                request.form.get('face_template_version')
                or request.form.get('embedding_version')
                or request.form.get('face_embedding_version')
                or DEFAULT_FACE_TEMPLATE_VERSION
            ).strip()
            quality_score = _parse_optional_float(
                request.form.get('face_template_quality') or request.form.get('quality_score')
            )

            if not face_template and Config.MOBILE_FACE_EMBEDDING_ENABLED:
                try:
                    from ml.face_embedding import get_face_pipeline

                    pipeline = get_face_pipeline(
                        detector_model_path=Config.YOLO_FACE_DETECTOR_MODEL_PATH,
                        embedder_model_path=Config.MOBILEFACENET_MODEL_PATH,
                        detector_conf_threshold=Config.FACE_DETECT_CONF_THRESHOLD,
                        detector_iou_threshold=Config.FACE_DETECT_IOU_THRESHOLD,
                    )
                    generated = pipeline.generate(captured_bytes)
                    face_template = generated.embedding
                    quality_score = generated.quality_score
                    embedding_version = generated.embedding_version
                except Exception as generation_error:
                    current_app.logger.exception(
                        "Failed to generate face template during registration: %s",
                        str(generation_error)
                    )
                    if Config.MOBILE_FACE_EMBEDDING_REQUIRE_SUCCESS:
                        flash(
                            "Unable to generate face embedding. Ensure assets/mobilefacenet.tflite and assets/yolov8n_float32.tflite are available.",
                            "danger"
                        )
                        return render_template('register.html', form=form, invitation=invitation, token=token)

            if not face_template and Config.MOBILE_FACE_EMBEDDING_REQUIRE_SUCCESS:
                flash(
                    "Face template is required for recognition. Please retry capture.",
                    "danger"
                )
                return render_template('register.html', form=form, invitation=invitation, token=token)

            if not captured_bytes:
                flash("Face capture is required. Please open camera and capture your face image.", "danger")
                return render_template('register.html', form=form, invitation=invitation, token=token)

            # Create user account
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", 
                         (username, hashed_password, invitation['role']))
            user_id = cursor.lastrowid

            upload_root = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
            os.makedirs(upload_root, exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            final_name = f"{user_id}_{timestamp}_captured.jpg"
            target_path = os.path.join(upload_root, final_name)

            with open(target_path, 'wb') as out_file:
                out_file.write(captured_bytes)

            face_image_path = f"uploads/profiles/{final_name}"
            cursor.execute(
                "UPDATE users SET profile_photo = %s, updated_at = NOW() WHERE id = %s",
                (face_image_path, user_id)
            )
            
            # Create role-specific record
            if invitation['role'] == 'Student':
                # Generate unique admission ID
                admission_id = f"STU{datetime.now().strftime('%Y%m%d')}{user_id:04d}"
                
                cursor.execute("""
                    INSERT INTO students (id, user_id, admission_id, name, email, course_id, class_id, division_id) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, user_id, admission_id, invitation['name'], invitation['email'], 
                      invitation['course_id'], invitation['class_id'], invitation['division_id']))
            elif invitation['role'] in ('Teacher', 'Faculty'):
                employee_id = _generate_employee_id(user_id)
                cursor.execute("""
                    INSERT INTO faculty (id, user_id, name, email, department_id, employee_id) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    user_id,
                    invitation['name'],
                    invitation['email'],
                    invitation['department_id'],
                    employee_id,
                ))

            # Save face image reference to mobile template table when available
            if face_image_path and _table_exists(cursor, 'mobile_face_templates'):
                cursor.execute(
                    """
                    INSERT INTO mobile_face_templates (
                        user_id, embedding_json, image_path, quality_score, embedding_version, is_active, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 1, NOW(), NOW())
                    ON DUPLICATE KEY UPDATE
                        embedding_json = VALUES(embedding_json),
                        image_path = VALUES(image_path),
                        quality_score = VALUES(quality_score),
                        embedding_version = VALUES(embedding_version),
                        is_active = 1,
                        updated_at = NOW()
                    """,
                    (
                        user_id,
                        json.dumps(face_template) if face_template else None,
                        face_image_path,
                        quality_score,
                        embedding_version if face_template else None,
                    )
                )
            
            # Mark invitation as used
            cursor.execute("""
                UPDATE registration_invitations 
                SET status = 'used', used_at = NOW() 
                WHERE id = %s
            """, (invitation['id'],))
            
            db.commit()
            flash(f"Registration successful! You can now log in as {invitation['role']}.", "success")
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.rollback()
            current_app.logger.error(f"Registration error: {str(e)}")
            flash("An error occurred during registration. Please try again.", "danger")
            return render_template('register.html', form=form, invitation=invitation, token=token)
    
    # GET request - show registration form with pre-filled data
    return render_template('register.html', form=form, invitation=invitation, token=token)

