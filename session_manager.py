"""
Enhanced Session Management
Purpose: Secure session handling, timeout management, "remember me" functionality
Created: 2025-12-30
"""

from flask import session, request, current_app, g
from datetime import datetime, timedelta
from functools import wraps
import secrets
import hashlib
from database import get_db_connection

# Session configuration
SESSION_TIMEOUT_MINUTES = 30  # Regular session timeout
REMEMBER_ME_DAYS = 30  # "Remember me" duration
MAX_SESSIONS_PER_USER = 5  # Maximum concurrent sessions

class SessionManager:
    """Enhanced session management with security features"""
    
    @staticmethod
    def create_session(user_id, username, role, remember_me=False):
        """
        Create a new user session with tracking
        
        Args:
            user_id: User ID
            username: Username
            role: User role
            remember_me: Whether to create a persistent session
        """
        try:
            # Generate session ID
            session_id = secrets.token_urlsafe(32)
            
            # Set session data
            session['user_id'] = user_id
            session['username'] = username
            session['role'] = role
            session['_id'] = session_id
            session['created_at'] = datetime.now().isoformat()
            session['last_activity'] = datetime.now().isoformat()
            
            # Calculate expiration
            if remember_me:
                expires_at = datetime.now() + timedelta(days=REMEMBER_ME_DAYS)
                session.permanent = True
                session['remember_me'] = True
            else:
                expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
                session.permanent = False
            
            # Store session in database
            connection = get_db_connection()

            cursor = connection.cursor(dictionary=True)
            
            # Cleanup old sessions if user has too many
            SessionManager._cleanup_old_sessions(cursor, user_id)
            
            # Insert new session
            cursor.execute(
                """
                INSERT INTO user_sessions 
                (session_id, user_id, ip_address, user_agent, expires_at, 
                 is_active, remember_me, last_activity)
                VALUES (%s, %s, %s, %s, %s, 1, %s, NOW())
                """,
                (session_id, user_id, request.remote_addr,
                 request.headers.get('User-Agent', '')[:500],
                 expires_at, 1 if remember_me else 0)
            )
            
            # Update last_login in users table
            cursor.execute(
                "UPDATE users SET last_login = NOW(), last_activity = NOW() WHERE id = %s",
                (user_id,)
            )
            
            connection.commit()
            cursor.close()
            
            current_app.logger.info(f'Session created for user {username} (ID: {user_id})')
            
        except Exception as e:
            current_app.logger.error(f'Session creation failed: {str(e)}')
            raise
    
    @staticmethod
    def _cleanup_old_sessions(cursor, user_id):
        """Remove oldest sessions if user has too many active sessions"""
        # Get count of active sessions
        cursor.execute(
            """
            SELECT COUNT(*) FROM user_sessions 
            WHERE user_id = %s AND is_active = 1 
            AND (expires_at IS NULL OR expires_at > NOW())
            """,
            (user_id,)
        )
        count = cursor.fetchone()[0]
        
        if count >= MAX_SESSIONS_PER_USER:
            # Deactivate oldest sessions
            cursor.execute(
                """
                UPDATE user_sessions 
                SET is_active = 0 
                WHERE user_id = %s AND is_active = 1
                ORDER BY last_activity ASC 
                LIMIT %s
                """,
                (user_id, count - MAX_SESSIONS_PER_USER + 1)
            )
    
    @staticmethod
    def validate_session():
        """
        Validate current session and check for timeout
        
        Returns:
            bool: True if session is valid, False otherwise
        """
        if 'user_id' not in session:
            return False
        
        try:
            session_id = session.get('_id')
            if not session_id:
                return False
            
            connection = get_db_connection()

            
            cursor = connection.cursor(dictionary=True)
            
            # Check if session exists and is active
            cursor.execute(
                """
                SELECT user_id, expires_at, is_active, remember_me 
                FROM user_sessions 
                WHERE session_id = %s
                """,
                (session_id,)
            )
            
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                return False
            
            user_id, expires_at, is_active, remember_me = result
            
            # Check if session is active
            if not is_active:
                cursor.close()
                return False
            
            # Check if session has expired
            if expires_at and datetime.now() > expires_at:
                # Deactivate expired session
                cursor.execute(
                    "UPDATE user_sessions SET is_active = 0 WHERE session_id = %s",
                    (session_id,)
                )
                connection.commit()
                cursor.close()
                return False
            
            # Update last activity
            cursor.execute(
                """
                UPDATE user_sessions 
                SET last_activity = NOW() 
                WHERE session_id = %s
                """,
                (session_id,)
            )
            
            # Update user's last_activity
            cursor.execute(
                "UPDATE users SET last_activity = NOW() WHERE id = %s",
                (user_id,)
            )
            
            connection.commit()
            cursor.close()
            
            # Update session last_activity timestamp
            session['last_activity'] = datetime.now().isoformat()
            
            return True
            
        except Exception as e:
            current_app.logger.error(f'Session validation failed: {str(e)}')
            return False
    
    @staticmethod
    def destroy_session(session_id=None):
        """
        Destroy a session (logout)
        
        Args:
            session_id: Optional session ID to destroy. If None, uses current session.
        """
        try:
            target_session_id = session_id or session.get('_id')
            
            if target_session_id:
                connection = get_db_connection()

                cursor = connection.cursor(dictionary=True)
                cursor.execute(
                    "UPDATE user_sessions SET is_active = 0 WHERE session_id = %s",
                    (target_session_id,)
                )
                connection.commit()
                cursor.close()
            
            # Clear Flask session
            if not session_id:  # Only clear current session
                session.clear()
            
        except Exception as e:
            current_app.logger.error(f'Session destruction failed: {str(e)}')
    
    @staticmethod
    def get_active_sessions(user_id):
        """Get all active sessions for a user"""
        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)
        
        cursor.execute(
            """
            SELECT session_id, ip_address, user_agent, last_activity, 
                   created_at, expires_at, remember_me
            FROM user_sessions
            WHERE user_id = %s AND is_active = 1
            AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY last_activity DESC
            """,
            (user_id,)
        )
        
        sessions = cursor.fetchall()
        cursor.close()
        
        return sessions
    
    @staticmethod
    def revoke_all_sessions(user_id, except_current=True):
        """
        Revoke all sessions for a user (e.g., on password change)
        
        Args:
            user_id: User ID
            except_current: If True, keep current session active
        """
        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)
        
        if except_current and session.get('_id'):
            cursor.execute(
                """
                UPDATE user_sessions 
                SET is_active = 0 
                WHERE user_id = %s AND session_id != %s
                """,
                (user_id, session.get('_id'))
            )
        else:
            cursor.execute(
                "UPDATE user_sessions SET is_active = 0 WHERE user_id = %s",
                (user_id,)
            )
        
        connection.commit()
        cursor.close()
    
    @staticmethod
    def cleanup_expired_sessions():
        """
        Cleanup expired sessions (run periodically via cron job)
        """
        try:
            connection = get_db_connection()

            cursor = connection.cursor(dictionary=True)
            
            # Deactivate expired sessions
            cursor.execute(
                """
                UPDATE user_sessions 
                SET is_active = 0 
                WHERE is_active = 1 
                AND expires_at IS NOT NULL 
                AND expires_at < NOW()
                """
            )
            
            affected = cursor.rowcount
            
            # Delete very old inactive sessions (older than 90 days)
            cursor.execute(
                """
                DELETE FROM user_sessions 
                WHERE is_active = 0 
                AND last_activity < DATE_SUB(NOW(), INTERVAL 90 DAY)
                """
            )
            
            deleted = cursor.rowcount
            
            connection.commit()
            cursor.close()
            
            current_app.logger.info(
                f'Session cleanup: {affected} expired, {deleted} deleted'
            )
            
        except Exception as e:
            current_app.logger.error(f'Session cleanup failed: {str(e)}')


def require_valid_session(f):
    """
    Decorator to enforce session validation on routes
    
    Usage:
        @app.route('/protected')
        @require_valid_session
        def protected_route():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not SessionManager.validate_session():
            session.clear()
            from flask import redirect, url_for, flash
            flash('Your session has expired. Please login again.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def session_activity_tracker():
    """
    Middleware to track session activity on each request
    Add this to Flask's before_request
    """
    if 'user_id' in session:
        # Update last activity timestamp
        session['last_activity'] = datetime.now().isoformat()
        
        # Store in g for easy access
        g.user_id = session.get('user_id')
        g.username = session.get('username')
        g.role = session.get('role')
