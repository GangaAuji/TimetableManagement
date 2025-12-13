"""Create faculty_availability table"""
import mysql.connector
from config import Config

conn = mysql.connector.connect(
    host=Config.MYSQL_HOST,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB
)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS faculty_availability (
        id INT AUTO_INCREMENT PRIMARY KEY,
        faculty_id INT NOT NULL,
        day_of_week ENUM('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday') NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        is_available BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (faculty_id) REFERENCES faculty(id) ON DELETE CASCADE,
        INDEX idx_faculty_day (faculty_id, day_of_week)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

conn.commit()
print('✅ faculty_availability table created')
cursor.close()
conn.close()
