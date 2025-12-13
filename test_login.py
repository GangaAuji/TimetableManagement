from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Create a new hashed password for testing
test_password = 'Info@1234'
hashed_password = generate_password_hash(test_password)
print(f"\nTest password: {test_password}")
print(f"Generated hash: {hashed_password}")

# Verify we can check the password correctly
verification = check_password_hash(hashed_password, test_password)
print(f"Local verification test: {verification}")

# Connect to database and check stored passwords
db = mysql.connector.connect(
    host=os.getenv('MYSQL_HOST'),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DB')
)

cursor = db.cursor(dictionary=True)
cursor.execute("SELECT id, username, password FROM users")
users = cursor.fetchall()

print("\nTesting stored passwords:")
for user in users:
    try:
        is_valid = check_password_hash(user['password'], test_password)
        print(f"User {user['username']}: Password valid = {is_valid}")
        print(f"Stored hash: {user['password'][:50]}...")
    except Exception as e:
        print(f"Error with user {user['username']}: {str(e)}")

cursor.close()
db.close()