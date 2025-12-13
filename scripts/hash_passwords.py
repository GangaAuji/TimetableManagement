"""One-off script to hash plaintext passwords in the users table.

Usage (from repository root):
    python -m scripts.hash_passwords

This script will:
 - load the Flask app using the factory
 - find users whose password doesn't look like a werkzeug hash (starts with 'pbkdf2:')
 - update those rows with generate_password_hash(password)

Make a backup of your DB before running.
"""
from app import create_app, mysql
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, username, password FROM users")
    users = cur.fetchall()

    updated = 0
    for u in users:
        user_id, username, pwd = u
        if pwd and not pwd.startswith('pbkdf2:'):
            new_hash = generate_password_hash(pwd)
            cur.execute("UPDATE users SET password = %s WHERE id = %s", (new_hash, user_id))
            updated += 1

    mysql.connection.commit()
    cur.close()

    print(f"Hashed {updated} user passwords.")