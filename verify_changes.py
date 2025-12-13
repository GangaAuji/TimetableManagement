"""
Quick verification script to check if all changes are in place
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("VERIFICATION: Proxy Approval Enhancement")
print("=" * 60)

# 1. Check database schema
print("\n1. Checking database schema...")
try:
    import mysql.connector
    from config import Config
    
    conn = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) 
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = %s 
        AND TABLE_NAME = 'proxy_log' 
        AND COLUMN_NAME = 'approval_status'
    """, (Config.MYSQL_DB,))
    
    if cursor.fetchone()[0] > 0:
        print("   ✅ proxy_log.approval_status column EXISTS")
    else:
        print("   ❌ proxy_log.approval_status column MISSING")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f"   ❌ Database check failed: {e}")

# 2. Check routes
print("\n2. Checking routes...")
try:
    from routes.admin_routes import admin_bp
    
    # Check if new endpoints exist
    endpoints = [rule.rule for rule in admin_bp.url_map.iter_rules() if rule.endpoint.startswith('admin.')]
    
    required_endpoints = [
        '/admin/faculty/<int:faculty_id>/absences/<int:absence_id>/approve',
        '/admin/faculty/<int:faculty_id>/absences/<int:absence_id>/reject',
        '/admin/faculty/<int:faculty_id>/proxy-log/<int:proxy_id>/approve',
        '/admin/faculty/<int:faculty_id>/proxy-log/<int:proxy_id>/reject',
        '/admin/api/faculty-by-subject'
    ]
    
    # Note: Can't check exact routes without Flask app context
    print("   ℹ️  Route check requires Flask app context")
    print("   ℹ️  Manual verification needed")
    
except Exception as e:
    print(f"   ⚠️  Route check skipped: {e}")

# 3. Check template files
print("\n3. Checking template files...")
try:
    with open('templates/admin/faculty_details.html', 'r', encoding='utf-8') as f:
        content = f.read()
        
    if 'approve-abs' in content:
        print("   ✅ Admin faculty_details.html has approval buttons")
    else:
        print("   ❌ Admin faculty_details.html MISSING approval buttons")
        
    if 'proxy-modal' in content:
        print("   ✅ Admin faculty_details.html has proxy modal")
    else:
        print("   ❌ Admin faculty_details.html MISSING proxy modal")
        
except Exception as e:
    print(f"   ❌ Template check failed: {e}")

# 4. Check teacher routes
print("\n4. Checking teacher routes...")
try:
    with open('routes/teacher_routes.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    if 'session.get(\'faculty_id\')' in content:
        print("   ✅ Teacher routes use session faculty_id")
    else:
        print("   ❌ Teacher routes NOT using session faculty_id")
        
    # Count occurrences
    count = content.count('session.get(\'faculty_id\')')
    print(f"   ℹ️  Found {count} uses of session.get('faculty_id')")
    
except Exception as e:
    print(f"   ❌ Teacher routes check failed: {e}")

# 5. Check teacher template
print("\n5. Checking teacher template...")
try:
    with open('templates/teacher/proxy_requests.html', 'r', encoding='utf-8') as f:
        content = f.read()
        
    if 'appr_st' in content or 'approval_status' in content:
        print("   ✅ Teacher proxy_requests.html shows approval_status")
    else:
        print("   ❌ Teacher proxy_requests.html NOT showing approval_status")
        
except Exception as e:
    print(f"   ❌ Teacher template check failed: {e}")

print("\n" + "=" * 60)
print("NEXT STEPS:")
print("=" * 60)
print("1. RESTART Flask server (Ctrl+C in Flask terminal, then restart)")
print("2. Clear browser cache (Ctrl+Shift+Delete)")
print("3. Login as teacher and verify dashboard shows only YOUR data")
print("4. Login as admin and verify approval buttons appear")
print("=" * 60)
