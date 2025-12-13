#!/usr/bin/env python3
"""
Fix foreign key constraints to reference user_id instead of id
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

def fix_foreign_keys():
    """Fix foreign key constraints"""
    print("🔧 Fixing Foreign Key Constraints")
    print("=" * 40)
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # Drop existing foreign key constraints
        print("🗑️ Dropping existing foreign key constraints...")
        
        # Get existing constraints
        cursor.execute("""
            SELECT CONSTRAINT_NAME, TABLE_NAME 
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
            WHERE REFERENCED_TABLE_NAME IN ('faculty', 'students') 
            AND TABLE_SCHEMA = DATABASE()
        """)
        constraints = cursor.fetchall()
        
        for constraint_name, table_name in constraints:
            try:
                cursor.execute(f"ALTER TABLE {table_name} DROP FOREIGN KEY {constraint_name}")
                print(f"   ✅ Dropped constraint {constraint_name} from {table_name}")
            except mysql.connector.Error as e:
                print(f"   ⚠️ Could not drop {constraint_name}: {e}")
        
        # Add new foreign key constraints that reference user_id
        print("\n🔗 Adding new foreign key constraints...")
        
        # For tables that reference faculty
        faculty_tables = [
            ('faculty_allocations', 'faculty_id'),
            ('faculty_availability', 'faculty_id'),
            ('timetable', 'faculty_id'),
            ('faculty_absences', 'faculty_id'),
            ('proxy_log', 'original_faculty_id'),
            ('proxy_log', 'proxy_faculty_id')
        ]
        
        for table_name, column_name in faculty_tables:
            try:
                constraint_name = f"fk_{table_name}_{column_name}"
                if column_name == 'proxy_faculty_id':
                    # Proxy faculty can be NULL
                    cursor.execute(f"""
                        ALTER TABLE {table_name} 
                        ADD CONSTRAINT {constraint_name} 
                        FOREIGN KEY ({column_name}) REFERENCES faculty(user_id) 
                        ON DELETE SET NULL
                    """)
                else:
                    cursor.execute(f"""
                        ALTER TABLE {table_name} 
                        ADD CONSTRAINT {constraint_name} 
                        FOREIGN KEY ({column_name}) REFERENCES faculty(user_id) 
                        ON DELETE CASCADE
                    """)
                print(f"   ✅ Added constraint {constraint_name} to {table_name}")
            except mysql.connector.Error as e:
                print(f"   ⚠️ Could not add constraint to {table_name}.{column_name}: {e}")
        
        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        connection.commit()
        print("\n✅ Foreign key constraints fixed!")
        
    except mysql.connector.Error as e:
        connection.rollback()
        print(f"❌ Foreign key fix failed: {e}")
    
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    fix_foreign_keys()