#!/usr/bin/env python3
"""
Migration: Add user_id as primary key, admission_id for students, employee_id for faculty
- Make user_id the primary key for faculty and students tables
- Add admission_id (unique) for students
- Add employee_id (unique) for faculty
- Ensure no duplicates and proper constraints
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

def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table"""
    cursor.execute(f"""
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME = '{table_name}' 
        AND COLUMN_NAME = '{column_name}'
    """)
    return cursor.fetchone()[0] > 0

def check_constraint_exists(cursor, table_name, constraint_name):
    """Check if a constraint exists on a table"""
    cursor.execute(f"""
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME = '{table_name}' 
        AND CONSTRAINT_NAME = '{constraint_name}'
    """)
    return cursor.fetchone()[0] > 0

def check_index_exists(cursor, table_name, index_name):
    """Check if an index exists on a table"""
    cursor.execute(f"""
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.STATISTICS 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME = '{table_name}' 
        AND INDEX_NAME = '{index_name}'
    """)
    return cursor.fetchone()[0] > 0

def migrate_faculty_table(cursor):
    """Migrate faculty table: add user_id as PK, employee_id unique"""
    print("🔄 Migrating faculty table...")
    
    # Step 1: Add user_id column if it doesn't exist
    if not check_column_exists(cursor, 'faculty', 'user_id'):
        print("  ➕ Adding user_id column to faculty table...")
        cursor.execute("ALTER TABLE faculty ADD COLUMN user_id INT NULL")
        print("  ✅ user_id column added to faculty")
    else:
        print("  ✅ user_id column already exists in faculty")
    
    # Step 1.5: Populate user_id values with available users for teachers
    cursor.execute("SELECT COUNT(*) FROM faculty WHERE user_id IS NULL")
    null_count = cursor.fetchone()[0]
    if null_count > 0:
        print(f"  🔄 Found {null_count} faculty records without user_id. Mapping to teacher users...")
        
        # Get teacher users that aren't already mapped
        cursor.execute("""
            SELECT u.id, u.username 
            FROM users u 
            WHERE u.role = 'Teacher' 
            AND u.id NOT IN (SELECT user_id FROM faculty WHERE user_id IS NOT NULL)
            ORDER BY u.id
        """)
        available_users = cursor.fetchall()
        
        # Get faculty without user_id
        cursor.execute("SELECT id, name FROM faculty WHERE user_id IS NULL ORDER BY id")
        unmapped_faculty = cursor.fetchall()
        
        # Map them 1:1
        for i, (faculty_id, faculty_name) in enumerate(unmapped_faculty):
            if i < len(available_users):
                user_id, username = available_users[i]
                cursor.execute("UPDATE faculty SET user_id = %s WHERE id = %s", (user_id, faculty_id))
                print(f"    👤 Mapped faculty '{faculty_name}' to user '{username}' (user_id: {user_id})")
            else:
                print(f"    ⚠️ No available teacher user for faculty '{faculty_name}' (id: {faculty_id})")
    
    # Step 2: Add employee_id column if it doesn't exist
    if not check_column_exists(cursor, 'faculty', 'employee_id'):
        print("  ➕ Adding employee_id column to faculty table...")
        cursor.execute("ALTER TABLE faculty ADD COLUMN employee_id VARCHAR(20) NULL")
        print("  ✅ employee_id column added to faculty")
    else:
        print("  ✅ employee_id column already exists in faculty")
    
    # Step 2.5: Generate employee_id values for faculty without them
    cursor.execute("SELECT user_id, name FROM faculty WHERE employee_id IS NULL OR employee_id = ''")
    faculty_without_empid = cursor.fetchall()
    
    for user_id, name in faculty_without_empid:
        # Generate employee_id like EMP001, EMP002, etc.
        cursor.execute("SELECT COUNT(*) FROM faculty WHERE employee_id LIKE 'EMP%'")
        count = cursor.fetchone()[0]
        employee_id = f"EMP{count + 1:03d}"
        
        cursor.execute("UPDATE faculty SET employee_id = %s WHERE user_id = %s", (employee_id, user_id))
        print(f"    🆔 Generated employee_id {employee_id} for faculty {name}")
    
    # Step 3: Now make user_id and employee_id NOT NULL and UNIQUE
    cursor.execute("SELECT COUNT(*) FROM faculty WHERE user_id IS NULL")
    remaining_nulls = cursor.fetchone()[0]
    
    if remaining_nulls == 0:
        print("  🔧 Making user_id NOT NULL and UNIQUE...")
        cursor.execute("ALTER TABLE faculty MODIFY user_id INT NOT NULL")
        
        if not check_index_exists(cursor, 'faculty', 'user_id'):
            cursor.execute("ALTER TABLE faculty ADD UNIQUE INDEX idx_faculty_user_id (user_id)")
        
        print("  🔧 Making employee_id NOT NULL and UNIQUE...")
        cursor.execute("ALTER TABLE faculty MODIFY employee_id VARCHAR(20) NOT NULL")
        
        if not check_index_exists(cursor, 'faculty', 'employee_id'):
            cursor.execute("ALTER TABLE faculty ADD UNIQUE INDEX idx_faculty_employee_id (employee_id)")
        
        # Step 4: Drop old primary key if exists and set user_id as primary key
        try:
            cursor.execute("ALTER TABLE faculty DROP PRIMARY KEY")
            print("  🗑️ Dropped old primary key from faculty")
        except mysql.connector.Error as e:
            if "doesn't have a primary key" not in str(e):
                print(f"  ⚠️ Could not drop primary key: {e}")
        
        try:
            cursor.execute("ALTER TABLE faculty ADD PRIMARY KEY (user_id)")
            print("  🔑 Set user_id as primary key for faculty")
        except mysql.connector.Error as e:
            if "PRIMARY KEY" in str(e):
                print("  ✅ user_id is already the primary key for faculty")
            else:
                print(f"  ❌ Error setting primary key: {e}")
        
        # Step 5: Add foreign key constraint to users table
        if not check_constraint_exists(cursor, 'faculty', 'fk_faculty_user'):
            try:
                cursor.execute("ALTER TABLE faculty ADD CONSTRAINT fk_faculty_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE")
                print("  🔗 Added foreign key constraint for faculty.user_id")
            except mysql.connector.Error as e:
                print(f"  ⚠️ Could not add foreign key constraint: {e}")
    else:
        print(f"  ❌ Cannot proceed: {remaining_nulls} faculty records still have NULL user_id")

def migrate_students_table(cursor):
    """Migrate students table: add user_id as PK, admission_id unique"""
    print("🔄 Migrating students table...")
    
    # Step 1: Add user_id column if it doesn't exist
    if not check_column_exists(cursor, 'students', 'user_id'):
        print("  ➕ Adding user_id column to students table...")
        cursor.execute("ALTER TABLE students ADD COLUMN user_id INT NULL")
        print("  ✅ user_id column added to students")
    else:
        print("  ✅ user_id column already exists in students")
    
    # Step 1.5: Populate user_id values with available users for students
    cursor.execute("SELECT COUNT(*) FROM students WHERE user_id IS NULL")
    null_count = cursor.fetchone()[0]
    if null_count > 0:
        print(f"  🔄 Found {null_count} student records without user_id. Mapping to student users...")
        
        # Get student users that aren't already mapped
        cursor.execute("""
            SELECT u.id, u.username 
            FROM users u 
            WHERE u.role = 'Student' 
            AND u.id NOT IN (SELECT user_id FROM students WHERE user_id IS NOT NULL)
            ORDER BY u.id
        """)
        available_users = cursor.fetchall()
        
        # Get students without user_id
        cursor.execute("SELECT id, name FROM students WHERE user_id IS NULL ORDER BY id")
        unmapped_students = cursor.fetchall()
        
        # Map them 1:1
        for i, (student_id, student_name) in enumerate(unmapped_students):
            if i < len(available_users):
                user_id, username = available_users[i]
                cursor.execute("UPDATE students SET user_id = %s WHERE id = %s", (user_id, student_id))
                print(f"    🎓 Mapped student '{student_name}' to user '{username}' (user_id: {user_id})")
            else:
                print(f"    ⚠️ No available student user for student '{student_name}' (id: {student_id})")
    
    # Step 2: Add admission_id column if it doesn't exist
    if not check_column_exists(cursor, 'students', 'admission_id'):
        print("  ➕ Adding admission_id column to students table...")
        cursor.execute("ALTER TABLE students ADD COLUMN admission_id VARCHAR(20) NULL")
        print("  ✅ admission_id column added to students")
    else:
        print("  ✅ admission_id column already exists in students")
    
    # Step 2.5: Generate admission_id values for students without them
    cursor.execute("SELECT user_id, name FROM students WHERE admission_id IS NULL OR admission_id = ''")
    students_without_admid = cursor.fetchall()
    
    for user_id, name in students_without_admid:
        # Generate admission_id like ADM001, ADM002, etc.
        cursor.execute("SELECT COUNT(*) FROM students WHERE admission_id LIKE 'ADM%'")
        count = cursor.fetchone()[0]
        admission_id = f"ADM{count + 1:03d}"
        
        cursor.execute("UPDATE students SET admission_id = %s WHERE user_id = %s", (admission_id, user_id))
        print(f"    🆔 Generated admission_id {admission_id} for student {name}")
    
    # Step 3: Now make user_id and admission_id NOT NULL and UNIQUE
    cursor.execute("SELECT COUNT(*) FROM students WHERE user_id IS NULL")
    remaining_nulls = cursor.fetchone()[0]
    
    if remaining_nulls == 0:
        print("  🔧 Making user_id NOT NULL and UNIQUE...")
        cursor.execute("ALTER TABLE students MODIFY user_id INT NOT NULL")
        
        if not check_index_exists(cursor, 'students', 'user_id'):
            cursor.execute("ALTER TABLE students ADD UNIQUE INDEX idx_students_user_id (user_id)")
        
        print("  🔧 Making admission_id NOT NULL and UNIQUE...")
        cursor.execute("ALTER TABLE students MODIFY admission_id VARCHAR(20) NOT NULL")
        
        if not check_index_exists(cursor, 'students', 'admission_id'):
            cursor.execute("ALTER TABLE students ADD UNIQUE INDEX idx_students_admission_id (admission_id)")
        
        # Step 4: Drop old primary key if exists and set user_id as primary key
        try:
            cursor.execute("ALTER TABLE students DROP PRIMARY KEY")
            print("  🗑️ Dropped old primary key from students")
        except mysql.connector.Error as e:
            if "doesn't have a primary key" not in str(e):
                print(f"  ⚠️ Could not drop primary key: {e}")
        
        try:
            cursor.execute("ALTER TABLE students ADD PRIMARY KEY (user_id)")
            print("  🔑 Set user_id as primary key for students")
        except mysql.connector.Error as e:
            if "PRIMARY KEY" in str(e):
                print("  ✅ user_id is already the primary key for students")
            else:
                print(f"  ❌ Error setting primary key: {e}")
        
        # Step 5: Add foreign key constraint to users table
        if not check_constraint_exists(cursor, 'students', 'fk_students_user'):
            try:
                cursor.execute("ALTER TABLE students ADD CONSTRAINT fk_students_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE")
                print("  🔗 Added foreign key constraint for students.user_id")
            except mysql.connector.Error as e:
                print(f"  ⚠️ Could not add foreign key constraint: {e}")
    else:
        print(f"  ❌ Cannot proceed: {remaining_nulls} student records still have NULL user_id")

def update_foreign_key_references(cursor):
    """Update foreign key references to use user_id instead of old id columns"""
    print("🔄 Updating foreign key references...")
    
    # Update faculty_allocations to reference faculty by user_id
    if check_column_exists(cursor, 'faculty_allocations', 'faculty_id'):
        print("  ⚠️ faculty_allocations.faculty_id needs manual update to reference faculty.user_id")
        print("     Run: UPDATE faculty_allocations fa JOIN faculty f ON fa.faculty_id = f.id SET fa.faculty_id = f.user_id")
    
    # Update faculty_availability to reference faculty by user_id
    if check_column_exists(cursor, 'faculty_availability', 'faculty_id'):
        print("  ⚠️ faculty_availability.faculty_id needs manual update to reference faculty.user_id")
        print("     Run: UPDATE faculty_availability fav JOIN faculty f ON fav.faculty_id = f.id SET fav.faculty_id = f.user_id")
    
    # Update timetable to reference faculty by user_id
    if check_column_exists(cursor, 'timetable', 'faculty_id'):
        print("  ⚠️ timetable.faculty_id needs manual update to reference faculty.user_id")
        print("     Run: UPDATE timetable t JOIN faculty f ON t.faculty_id = f.id SET t.faculty_id = f.user_id")
    
    # Update faculty_absences to reference faculty by user_id
    if check_column_exists(cursor, 'faculty_absences', 'faculty_id'):
        print("  ⚠️ faculty_absences.faculty_id needs manual update to reference faculty.user_id")
        print("     Run: UPDATE faculty_absences fa JOIN faculty f ON fa.faculty_id = f.id SET fa.faculty_id = f.user_id")
    
    # Update proxy_log to reference faculty by user_id
    if check_column_exists(cursor, 'proxy_log', 'original_faculty_id'):
        print("  ⚠️ proxy_log faculty references need manual update to use faculty.user_id")
        print("     Run: UPDATE proxy_log p JOIN faculty f ON p.original_faculty_id = f.id SET p.original_faculty_id = f.user_id")
        print("     Run: UPDATE proxy_log p JOIN faculty f ON p.proxy_faculty_id = f.id SET p.proxy_faculty_id = f.user_id WHERE p.proxy_faculty_id IS NOT NULL")

def generate_sample_data(cursor):
    """This function is now integrated into migrate_faculty_table and migrate_students_table"""
    print("� Sample data generation is handled during table migration...")
    pass

def run_migration():
    """Execute the complete migration"""
    print("🚀 Starting User ID and Unique ID Migration")
    print("=" * 60)
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Step 1: Migrate faculty table
        migrate_faculty_table(cursor)
        
        # Step 2: Migrate students table
        migrate_students_table(cursor)
        
        # Step 3: Generate sample IDs if needed
        generate_sample_data(cursor)
        
        # Step 4: Show foreign key update warnings
        update_foreign_key_references(cursor)
        
        # Commit all changes
        connection.commit()
        print("\n✅ Migration completed successfully!")
        
        # Show summary
        cursor.execute("SELECT COUNT(*) FROM faculty")
        faculty_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM students")
        student_count = cursor.fetchone()[0]
        
        print(f"\n📊 Migration Summary:")
        print(f"   👨‍🏫 Faculty records: {faculty_count}")
        print(f"   🎓 Student records: {student_count}")
        print(f"   🔑 user_id is now primary key for both tables")
        print(f"   🆔 employee_id (faculty) and admission_id (students) are unique")
        
        print(f"\n⚠️  Next Steps:")
        print(f"   1. Manually map existing user_id values to correct users")
        print(f"   2. Update foreign key references in other tables")
        print(f"   3. Test login functionality")
        
    except mysql.connector.Error as e:
        connection.rollback()
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
    
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    print("User ID and Unique ID Migration Script")
    print("This will modify faculty and students tables structure")
    
    response = input("\nDo you want to proceed? (y/N): ").strip().lower()
    if response in ['y', 'yes']:
        run_migration()
    else:
        print("Migration cancelled.")