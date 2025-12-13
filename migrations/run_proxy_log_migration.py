"""
Migration: Standardize proxy_log schema with approval workflow
Run this script to add approval_status, approval_date, approved_by columns
and migrate existing data to the new schema.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mysql.connector
from config import Config

def run_migration():
    try:
        conn = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB
        )
        cursor = conn.cursor()
        print("✓ Connected to database")
        
        # Check if columns already exist
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'proxy_log' 
            AND COLUMN_NAME = 'approval_status'
        """, (Config.MYSQL_DB,))
        
        if cursor.fetchone()[0] > 0:
            print("⚠ Migration already applied (approval_status column exists)")
            cursor.close()
            conn.close()
            return
        
        print("Adding new columns to proxy_log...")
        
        # Add approval_status column
        cursor.execute("""
            ALTER TABLE proxy_log
            ADD COLUMN approval_status ENUM('PENDING', 'APPROVED', 'REJECTED') DEFAULT 'PENDING' AFTER status
        """)
        print("  ✓ Added approval_status column")
        
        # Add approval_date column
        cursor.execute("""
            ALTER TABLE proxy_log
            ADD COLUMN approval_date DATETIME NULL AFTER approval_status
        """)
        print("  ✓ Added approval_date column")
        
        # Add approved_by column
        cursor.execute("""
            ALTER TABLE proxy_log
            ADD COLUMN approved_by INT NULL AFTER approval_date
        """)
        print("  ✓ Added approved_by column")
        
        # Add approval_notes column
        cursor.execute("""
            ALTER TABLE proxy_log
            ADD COLUMN approval_notes TEXT NULL AFTER approved_by
        """)
        print("  ✓ Added approval_notes column")
        
        # Add foreign key constraint
        try:
            cursor.execute("""
                ALTER TABLE proxy_log
                ADD CONSTRAINT fk_proxy_log_approved_by 
                FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL
            """)
            print("  ✓ Added foreign key constraint")
        except mysql.connector.Error as e:
            if "Duplicate key" in str(e) or "already exists" in str(e):
                print("  ⚠ Foreign key constraint already exists, skipping")
            else:
                raise
        
        print("\nMigrating existing data...")
        
        # Migrate approval_status based on old status values
        cursor.execute("""
            UPDATE proxy_log 
            SET approval_status = CASE 
                WHEN status IN ('ASSIGNED', 'UNASSIGNED') THEN 'APPROVED'
                WHEN status = 'PENDING' THEN 'PENDING'
                WHEN status = 'APPROVED' THEN 'APPROVED'
                WHEN status = 'REJECTED' THEN 'REJECTED'
                ELSE 'PENDING'
            END
        """)
        print("  ✓ Set approval_status for existing records")
        
        # Standardize status column to reflect assignment state
        cursor.execute("""
            UPDATE proxy_log
            SET status = CASE
                WHEN proxy_faculty_id IS NOT NULL AND approval_status = 'APPROVED' THEN 'ASSIGNED'
                WHEN proxy_faculty_id IS NULL AND approval_status = 'APPROVED' THEN 'UNASSIGNED'
                WHEN approval_status = 'PENDING' THEN 'PENDING'
                WHEN approval_status = 'REJECTED' THEN 'REJECTED'
                ELSE status
            END
        """)
        print("  ✓ Standardized status column")
        
        # Add indexes
        print("\nAdding indexes...")
        try:
            cursor.execute("""
                CREATE INDEX idx_proxy_log_approval_status ON proxy_log(approval_status)
            """)
            print("  ✓ Created index on approval_status")
        except mysql.connector.Error as e:
            if "Duplicate key" in str(e):
                print("  ⚠ Index on approval_status already exists")
            else:
                raise
        
        try:
            cursor.execute("""
                CREATE INDEX idx_proxy_log_approval_date ON proxy_log(approval_date)
            """)
            print("  ✓ Created index on approval_date")
        except mysql.connector.Error as e:
            if "Duplicate key" in str(e):
                print("  ⚠ Index on approval_date already exists")
            else:
                raise
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        # Show summary
        cursor.execute("""
            SELECT approval_status, COUNT(*) as count 
            FROM proxy_log 
            GROUP BY approval_status
        """)
        print("\nProxy log status summary:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} records")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    print("=" * 60)
    print("Proxy Log Schema Standardization Migration")
    print("=" * 60)
    print()
    run_migration()
