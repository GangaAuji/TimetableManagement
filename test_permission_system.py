"""
Test script for the enhanced user permission system
Creates sample users with different permission levels
"""

import mysql.connector
from werkzeug.security import generate_password_hash

# Database configuration
config = {
    'user': 'Admin',
    'password': '',  # Will be prompted
    'host': 'localhost',
    'database': 'college_timetable_db'
}

def main():
    # Get password
    import getpass
    config['password'] = getpass.getpass("Enter MySQL password: ")
    
    # Connect to database
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True)
        
        print("🔗 Connected to database")
        
        # 1. Create a Computer Science HOD user
        print("\n📝 Creating Computer Science HOD...")
        
        # First, get Computer Science department ID
        cursor.execute("SELECT id FROM departments WHERE name = 'Computer Science'")
        cs_dept = cursor.fetchone()
        if not cs_dept:
            # Create CS department if it doesn't exist
            cursor.execute("INSERT INTO departments (name) VALUES ('Computer Science')")
            cs_dept_id = cursor.lastrowid
            print(f"   Created Computer Science department (ID: {cs_dept_id})")
        else:
            cs_dept_id = cs_dept['id']
            print(f"   Found Computer Science department (ID: {cs_dept_id})")
        
        # Create HOD user
        hod_username = "cs_hod"
        hod_password = generate_password_hash("password123")
        
        cursor.execute("""
            INSERT IGNORE INTO users (username, password, role, department_id, is_hod, status)
            VALUES (%s, %s, 'Admin', %s, TRUE, 'active')
        """, (hod_username, hod_password, cs_dept_id))
        
        if cursor.lastrowid:
            hod_user_id = cursor.lastrowid
            print(f"   Created HOD user: {hod_username} (ID: {hod_user_id})")
        else:
            # User already exists, get ID
            cursor.execute("SELECT id FROM users WHERE username = %s", (hod_username,))
            hod_user_id = cursor.fetchone()['id']
            print(f"   HOD user already exists: {hod_username} (ID: {hod_user_id})")
        
        # 2. Create a regular admin with limited permissions
        print("\n📝 Creating limited admin...")
        
        limited_admin_username = "admin_limited"
        limited_admin_password = generate_password_hash("password123")
        
        cursor.execute("""
            INSERT IGNORE INTO users (username, password, role, status)
            VALUES (%s, %s, 'Admin', 'active')
        """, (limited_admin_username, limited_admin_password))
        
        if cursor.lastrowid:
            limited_admin_id = cursor.lastrowid
            print(f"   Created limited admin: {limited_admin_username} (ID: {limited_admin_id})")
        else:
            cursor.execute("SELECT id FROM users WHERE username = %s", (limited_admin_username,))
            limited_admin_id = cursor.fetchone()['id']
            print(f"   Limited admin already exists: {limited_admin_username} (ID: {limited_admin_id})")
        
        # 3. Assign permission groups
        print("\n🔐 Assigning permission groups...")
        
        # Give HOD advanced permissions for their department
        cursor.execute("SELECT id FROM permission_groups WHERE name = 'HOD Advanced'")
        hod_advanced_group = cursor.fetchone()
        if hod_advanced_group:
            cursor.execute("""
                INSERT IGNORE INTO user_permission_groups 
                (user_id, group_id, department_id, granted_by)
                VALUES (%s, %s, %s, 1)
            """, (hod_user_id, hod_advanced_group['id'], cs_dept_id))
            print(f"   ✅ Assigned HOD Advanced group to CS HOD (department-specific)")
        
        # Give limited admin only user management permissions
        cursor.execute("SELECT id FROM permission_groups WHERE name = 'User Manager'")
        user_manager_group = cursor.fetchone()
        if user_manager_group:
            cursor.execute("""
                INSERT IGNORE INTO user_permission_groups 
                (user_id, group_id, granted_by)
                VALUES (%s, %s, 1)
            """, (limited_admin_id, user_manager_group['id']))
            print(f"   ✅ Assigned User Manager group to limited admin")
        
        # 4. Grant some individual permissions
        print("\n🎯 Granting individual permissions...")
        
        # Give HOD view permissions for timetables
        cursor.execute("SELECT id FROM permissions WHERE name = 'view_timetable'")
        view_timetable_perm = cursor.fetchone()
        if view_timetable_perm:
            cursor.execute("""
                INSERT IGNORE INTO user_permissions 
                (user_id, permission_id, department_id, granted_by, notes)
                VALUES (%s, %s, %s, 1, 'HOD can view department timetables')
            """, (hod_user_id, view_timetable_perm['id'], cs_dept_id))
            print(f"   ✅ Granted view_timetable permission to CS HOD (department-specific)")
        
        # 5. Create a Mathematics department and HOD for testing
        print("\n📚 Creating Mathematics department and HOD...")
        
        cursor.execute("INSERT IGNORE INTO departments (name) VALUES ('Mathematics')")
        cursor.execute("SELECT id FROM departments WHERE name = 'Mathematics'")
        math_dept_id = cursor.fetchone()['id']
        
        math_hod_username = "math_hod"
        math_hod_password = generate_password_hash("password123")
        
        cursor.execute("""
            INSERT IGNORE INTO users (username, password, role, department_id, is_hod, status)
            VALUES (%s, %s, 'Admin', %s, TRUE, 'active')
        """, (math_hod_username, math_hod_password, math_dept_id))
        
        cursor.execute("SELECT id FROM users WHERE username = %s", (math_hod_username,))
        math_hod_result = cursor.fetchone()
        if math_hod_result:
            math_hod_id = math_hod_result['id']
            print(f"   Created Math HOD: {math_hod_username} (ID: {math_hod_id})")
            
            # Assign HOD Basic group to Math HOD (more restricted)
            cursor.execute("SELECT id FROM permission_groups WHERE name = 'HOD Basic'")
            hod_basic_group = cursor.fetchone()
            if hod_basic_group:
                cursor.execute("""
                    INSERT IGNORE INTO user_permission_groups 
                    (user_id, group_id, department_id, granted_by)
                    VALUES (%s, %s, %s, 1)
                """, (math_hod_id, hod_basic_group['id'], math_dept_id))
                print(f"   ✅ Assigned HOD Basic group to Math HOD (department-specific)")
        
        # Commit all changes
        conn.commit()
        
        # 6. Test permission queries
        print("\n🧪 Testing permission system...")
        
        # Test CS HOD permissions
        cursor.execute("""
            SELECT DISTINCT p.name, p.module, 'individual' as source, up.department_id
            FROM user_permissions up
            JOIN permissions p ON up.permission_id = p.id
            WHERE up.user_id = %s AND up.is_active = TRUE
            
            UNION ALL
            
            SELECT DISTINCT p.name, p.module, 'group' as source, upg.department_id
            FROM user_permission_groups upg
            JOIN permission_group_permissions pgp ON upg.group_id = pgp.group_id
            JOIN permissions p ON pgp.permission_id = p.id
            WHERE upg.user_id = %s AND upg.is_active = TRUE
            
            ORDER BY module, name
        """, (hod_user_id, hod_user_id))
        
        cs_hod_permissions = cursor.fetchall()
        print(f"\n   CS HOD ({hod_username}) permissions:")
        for perm in cs_hod_permissions:
            dept_info = f" [Dept: {perm['department_id']}]" if perm['department_id'] else " [All Depts]"
            print(f"     • {perm['name']} ({perm['module']}) - {perm['source']}{dept_info}")
        
        # Test limited admin permissions
        cursor.execute("""
            SELECT DISTINCT p.name, p.module, 'group' as source
            FROM user_permission_groups upg
            JOIN permission_group_permissions pgp ON upg.group_id = pgp.group_id
            JOIN permissions p ON pgp.permission_id = p.id
            WHERE upg.user_id = %s AND upg.is_active = TRUE
            ORDER BY module, name
        """, (limited_admin_id,))
        
        limited_admin_permissions = cursor.fetchall()
        print(f"\n   Limited Admin ({limited_admin_username}) permissions:")
        for perm in limited_admin_permissions:
            print(f"     • {perm['name']} ({perm['module']}) - {perm['source']}")
        
        print(f"\n✅ Test setup completed successfully!")
        print(f"\n📋 Test Users Created:")
        print(f"   • {hod_username} / password123 (CS HOD with department-specific permissions)")
        print(f"   • {limited_admin_username} / password123 (Limited admin with only user management)")
        print(f"   • {math_hod_username} / password123 (Math HOD with basic permissions)")
        print(f"\n🔗 You can now test the permission system by:")
        print(f"   1. Logging in as these users at /admin/login")
        print(f"   2. Checking which menu items are visible")
        print(f"   3. Testing department-specific access")
        print(f"   4. Managing permissions at /admin/users/permissions/<user_id>")
        
    except mysql.connector.Error as err:
        print(f"❌ Database error: {err}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("\n🔌 Database connection closed")

if __name__ == "__main__":
    main()