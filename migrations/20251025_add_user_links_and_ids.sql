
-- Migration: Add user_id links and identifiers per business rules
-- Date: 2025-10-25

-- Add user_id to students (nullable initially), admission_number unique, and FK
ALTER TABLE students ADD COLUMN user_id INT NULL;
ALTER TABLE students ADD COLUMN admission_number VARCHAR(50) NULL;
ALTER TABLE students ADD UNIQUE KEY uq_students_admission_number (admission_number);
ALTER TABLE students ADD UNIQUE KEY uq_students_user_id (user_id);
ALTER TABLE students ADD CONSTRAINT fk_students_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Backfill note: If existing students should be linked to users, run an update based on email or other mapping.

-- Add user_id to faculty (nullable initially), employee_id unique, and FK
ALTER TABLE faculty ADD COLUMN user_id INT NULL;
ALTER TABLE faculty ADD COLUMN employee_id VARCHAR(50) NULL;
ALTER TABLE faculty ADD UNIQUE KEY uq_faculty_employee_id (employee_id);
ALTER TABLE faculty ADD UNIQUE KEY uq_faculty_user_id (user_id);
ALTER TABLE faculty ADD CONSTRAINT fk_faculty_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Optional: If emails exist in users (not currently), you could backfill via email mapping.

-- Ensure NOT NULL constraints are respected for identifier fields
-- Optionally enforce NOT NULL later after backfilling existing records
-- ALTER TABLE students MODIFY admission_number VARCHAR(50) NOT NULL;
-- ALTER TABLE faculty MODIFY employee_id VARCHAR(50) NOT NULL;
