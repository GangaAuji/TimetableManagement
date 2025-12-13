#!/usr/bin/env python
"""Quick schema check for students and faculty tables"""
import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()

try:
    conn = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST', 'localhost'),
        user=os.getenv('MYSQL_USER', 'root'),
        password=os.getenv('MYSQL_PASSWORD', ''),
        database=os.getenv('MYSQL_DB', 'timetable_db')
    )
    cursor = conn.cursor()
    
    print("\n--- STUDENTS TABLE ---")
    cursor.execute("DESCRIBE students")
    for row in cursor.fetchall():
        print(f"  {row[0]:20s} {row[1]:20s} {row[2]:5s} {row[3]:5s} {row[4] if row[4] else '':20s}")
    
    cursor.execute("SELECT COUNT(*) FROM students")
    print(f"\nTotal students: {cursor.fetchone()[0]}")
    
    print("\n--- FACULTY TABLE ---")
    cursor.execute("DESCRIBE faculty")
    for row in cursor.fetchall():
        print(f"  {row[0]:20s} {row[1]:20s} {row[2]:5s} {row[3]:5s} {row[4] if row[4] else '':20s}")
    
    cursor.execute("SELECT COUNT(*) FROM faculty")
    print(f"\nTotal faculty: {cursor.fetchone()[0]}")
    
    print("\n--- USERS TABLE ---")
    cursor.execute("SELECT id, username, role FROM users")
    users = cursor.fetchall()
    print(f"Total users: {len(users)}")
    for u in users:
        print(f"  ID: {u[0]}, Username: {u[1]}, Role: {u[2]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
