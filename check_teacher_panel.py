"""
Quick health check for Teacher Panel setup.
Verifies database tables and endpoints are ready.
"""
import mysql.connector
from config import Config
from flask import Flask
from app import create_app

def check_database():
    """Check if required tables exist"""
    try:
        conn = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB
        )
        cursor = conn.cursor()
        
        required_tables = [
            'faculty',
            'faculty_absences',
            'faculty_availability',
            'timetable',
            'proxy_log',
            'faculty_allocations'
        ]
        
        print("📊 Checking database tables...")
        all_good = True
        for table in required_tables:
            cursor.execute(f"SHOW TABLES LIKE '{table}'")
            exists = cursor.fetchone() is not None
            status = "✅" if exists else "❌"
            print(f"  {status} {table}")
            if not exists:
                all_good = False
        
        cursor.close()
        conn.close()
        return all_good
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def check_routes():
    """Check if Teacher Panel routes are registered"""
    try:
        app = create_app()
        print("\n🛤️  Checking routes...")
        
        required_routes = [
            'teacher.dashboard',
            'teacher.my_timetable',
            'teacher.timetable_data',
            'teacher.download_timetable',
            'teacher.availability',
            'teacher.absences',
            'teacher.delete_absence',
            'teacher.proxy_requests',
            'teacher.request_proxy'
        ]
        
        with app.app_context():
            all_good = True
            for route_name in required_routes:
                try:
                    from flask import url_for
                    # This will raise if route doesn't exist
                    url_for(route_name)
                    print(f"  ✅ {route_name}")
                except:
                    print(f"  ❌ {route_name}")
                    all_good = False
        
        return all_good
    except Exception as e:
        print(f"❌ Routes error: {e}")
        return False

def check_templates():
    """Check if required templates exist"""
    import os
    print("\n📄 Checking templates...")
    
    templates = [
        'templates/teacher/dashboard.html',
        'templates/teacher/timetable.html',
        'templates/teacher/availability.html',
        'templates/teacher/proxy_requests.html',
        'templates/teacher/request_proxy.html',
        'templates/teacher/_layout.html'
    ]
    
    all_good = True
    for template in templates:
        exists = os.path.exists(template)
        status = "✅" if exists else "❌"
        print(f"  {status} {template}")
        if not exists:
            all_good = False
    
    return all_good

def main():
    print("=" * 60)
    print("🔍 Teacher Panel Health Check")
    print("=" * 60)
    
    db_ok = check_database()
    routes_ok = check_routes()
    templates_ok = check_templates()
    
    print("\n" + "=" * 60)
    if db_ok and routes_ok and templates_ok:
        print("✅ ALL CHECKS PASSED - Teacher Panel is ready!")
        print("\n🚀 Next steps:")
        print("   1. Start Flask app: python app.py")
        print("   2. Login as a Teacher user")
        print("   3. Navigate to: http://localhost:5000/teacher/dashboard")
    else:
        print("❌ SOME CHECKS FAILED - Please review errors above")
        if not db_ok:
            print("   → Run: python run_migration.py")
        if not routes_ok:
            print("   → Check routes/teacher_routes.py")
        if not templates_ok:
            print("   → Verify templates/teacher/ directory")
    print("=" * 60)

if __name__ == "__main__":
    main()
