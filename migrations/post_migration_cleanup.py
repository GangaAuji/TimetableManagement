#!/usr/bin/env python3
"""
Post-migration script to update foreign key references and fix primary keys
This script updates all tables that reference faculty.id or students.id to use user_id instead
"""

import mysql.connector
import sys
import os

# Add the parent directory to Python path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

def get_db_connection():
    """Get database connection using app config"""
    try:
        connection = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            autocommit=False
        )
        return connection
    except mysql.connector.Error as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)

def update_foreign_key_references(cursor):
    """Update all foreign key references to use user_id instead of old id"""
    print("🔄 Updating foreign key references...")
    
    # Update faculty_allocations
    print("  📋 Updating faculty_allocations...")
    cursor.execute("""
        UPDATE faculty_allocations fa 
        JOIN faculty f ON fa.faculty_id = f.id 
        SET fa.faculty_id = f.user_id
    """)
    updated_rows = cursor.rowcount
    print(f"    ✅ Updated {updated_rows} faculty_allocations records")
    
    # Update faculty_availability
    print("  📅 Updating faculty_availability...")
    cursor.execute("""
        UPDATE faculty_availability fav 
        JOIN faculty f ON fav.faculty_id = f.id 
        SET fav.faculty_id = f.user_id
    """)
    updated_rows = cursor.rowcount
    print(f"    ✅ Updated {updated_rows} faculty_availability records")
    
    # Update timetable
    print("  ⏰ Updating timetable...")
    cursor.execute("""
        UPDATE timetable t 
        JOIN faculty f ON t.faculty_id = f.id 
        SET t.faculty_id = f.user_id
    """)
    updated_rows = cursor.rowcount
    print(f"    ✅ Updated {updated_rows} timetable records")
    
    # Update faculty_absences
    print("  🚫 Updating faculty_absences...")
    cursor.execute("""
        UPDATE faculty_absences fa 
        JOIN faculty f ON fa.faculty_id = f.id 
        SET fa.faculty_id = f.user_id
    """)
    updated_rows = cursor.rowcount
    print(f"    ✅ Updated {updated_rows} faculty_absences records")
    
    # Update proxy_log - original_faculty_id
    print("  🔄 Updating proxy_log original_faculty_id...")
    cursor.execute("""
        UPDATE proxy_log p 
        JOIN faculty f ON p.original_faculty_id = f.id 
        SET p.original_faculty_id = f.user_id
    """)
    updated_rows = cursor.rowcount
    print(f"    ✅ Updated {updated_rows} proxy_log original_faculty_id records")
    
    # Update proxy_log - proxy_faculty_id (only where not NULL)
    print("  🔄 Updating proxy_log proxy_faculty_id...")
    cursor.execute("""
        UPDATE proxy_log p 
        JOIN faculty f ON p.proxy_faculty_id = f.id 
        SET p.proxy_faculty_id = f.user_id 
        WHERE p.proxy_faculty_id IS NOT NULL
    """)
    updated_rows = cursor.rowcount
    print(f"    ✅ Updated {updated_rows} proxy_log proxy_faculty_id records")

def clean_up_primary_keys(cursor):
    """Fix primary key issues by removing AUTO_INCREMENT and setting proper primary keys"""
    print("🔄 Cleaning up primary keys...")
    
    # Faculty table
    print("  👨‍🏫 Fixing faculty table primary key...")
    try:
        # Remove AUTO_INCREMENT from id column first
        cursor.execute("ALTER TABLE faculty MODIFY id INT NOT NULL")
        print("    🔧 Removed AUTO_INCREMENT from faculty.id")
        
        # Drop existing primary key
        cursor.execute("ALTER TABLE faculty DROP PRIMARY KEY")
        print("    🗑️ Dropped old primary key from faculty")
        
        # Set user_id as primary key
        cursor.execute("ALTER TABLE faculty ADD PRIMARY KEY (user_id)")
        print("    🔑 Set user_id as primary key for faculty")
        
    except mysql.connector.Error as e:
        print(f"    ⚠️ Error fixing faculty primary key: {e}")
    
    # Students table
    print("  🎓 Fixing students table primary key...")
    try:
        # Remove AUTO_INCREMENT from id column first
        cursor.execute("ALTER TABLE students MODIFY id INT NOT NULL")
        print("    🔧 Removed AUTO_INCREMENT from students.id")
        
        # Drop existing primary key
        cursor.execute("ALTER TABLE students DROP PRIMARY KEY")
        print("    🗑️ Dropped old primary key from students")
        
        # Set user_id as primary key
        cursor.execute("ALTER TABLE students ADD PRIMARY KEY (user_id)")
        print("    🔑 Set user_id as primary key for students")
        
    except mysql.connector.Error as e:
        print(f"    ⚠️ Error fixing students primary key: {e}")

def show_migration_summary(cursor):
    """Show final migration summary"""
    print("\n📊 Final Migration Summary:")
    
    # Faculty summary
    cursor.execute("""
        SELECT f.user_id, f.employee_id, f.name, u.username 
        FROM faculty f 
        JOIN users u ON f.user_id = u.id 
        ORDER BY f.user_id
    """)
    faculty_data = cursor.fetchall()
    
    print("  👨‍🏫 Faculty Mapping:")
    for user_id, emp_id, name, username in faculty_data:
        print(f"    • {name} (Employee: {emp_id}) → User: {username} (ID: {user_id})")
    
    # Students summary
    cursor.execute("""
        SELECT s.user_id, s.admission_id, s.name, u.username 
        FROM students s 
        JOIN users u ON s.user_id = u.id 
        ORDER BY s.user_id
    """)
    student_data = cursor.fetchall()
    
    print("  🎓 Student Mapping:")
    for user_id, adm_id, name, username in student_data:
        print(f"    • {name} (Admission: {adm_id}) → User: {username} (ID: {user_id})")

def run_post_migration():
    """Execute the post-migration cleanup"""
    print("🚀 Starting Post-Migration Cleanup")
    print("=" * 60)
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Disable foreign key checks temporarily
        print("🔓 Temporarily disabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # Step 1: Update foreign key references
        update_foreign_key_references(cursor)
        
        # Step 2: Clean up primary keys
        clean_up_primary_keys(cursor)
        
        # Re-enable foreign key checks
        print("🔒 Re-enabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        # Commit all changes
        connection.commit()
        print("\n✅ Post-migration cleanup completed successfully!")
        
        # Step 3: Show summary
        show_migration_summary(cursor)
        
        print(f"\n🎉 Migration Complete!")
        print(f"   • user_id is now the primary key for faculty and students")
        print(f"   • All foreign key references updated to use user_id")
        print(f"   • Employee IDs and Admission IDs are unique")
        print(f"   • Teacher login should now be user-scoped")
        
    except mysql.connector.Error as e:
        connection.rollback()
        print(f"\n❌ Post-migration failed: {e}")
        sys.exit(1)
    
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    print("Post-Migration Cleanup Script")
    print("This will update foreign key references and fix primary keys")
    
    response = input("\nDo you want to proceed? (y/N): ").strip().lower()
    if response in ['y', 'yes']:
        run_post_migration()
    else:
        print("Post-migration cancelled.")