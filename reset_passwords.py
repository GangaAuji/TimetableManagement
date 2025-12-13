from werkzeug.security import generate_password_hash
import mysql.connector
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Connect to database
db = mysql.connector.connect(
    host=os.getenv('MYSQL_HOST'),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DB')
)

cursor = db.cursor()

# Create new hash
hashed_password = generate_password_hash('Info@1234', method='pbkdf2:sha256')

# Update all users
cursor.execute("UPDATE users SET password = %s", (hashed_password,))
db.commit()

print("Passwords updated successfully")

# Verify update
cursor.execute("SELECT id, username, LEFT(password, 50) as password_prefix FROM users")
users = cursor.fetchall()
for user in users:
    print(f"User {user[1]}: {user[2]}...")

cursor.close()
db.close()