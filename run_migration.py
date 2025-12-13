"""
Run database migrations - Add email column to users table
"""
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
        
        print("Adding email column to users table...")
        
        # Check if email column exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE table_schema = %s 
            AND table_name = 'users' 
            AND column_name = 'email'
        """, (Config.MYSQL_DB,))
        
        exists = cursor.fetchone()[0]
        
        if exists > 0:
            print("✓ Email column already exists in users table!")
        else:
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN email VARCHAR(100) DEFAULT NULL
            """)
            conn.commit()
            print("✓ Email column added successfully!")
        
        # Verify
        cursor.execute("DESCRIBE users")
        print("\nUsers table structure:")
        for col in cursor.fetchall():
            print(f"  {col[0]:20} {col[1]}")
        
        cursor.close()
        conn.close()
        print("\n✓ Migration completed successfully!")
        
    except Exception as e:
        print(f"✗ Error running migration: {e}")
        raise

if __name__ == "__main__":
    run_migration()
