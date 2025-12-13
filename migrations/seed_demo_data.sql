-- Seed demo data aligned with provided schema (users->faculty FK, non-null division_id in allocations)
START TRANSACTION;

-- Ensure department
INSERT INTO departments (name)
SELECT 'Computer Science' WHERE NOT EXISTS (
  SELECT 1 FROM departments WHERE name = 'Computer Science'
);

-- Ensure course (BSc Computer Science)
INSERT INTO courses (name, program, department_id)
SELECT 'BSc Computer Science', 'UG', (SELECT id FROM departments WHERE name = 'Computer Science')
WHERE NOT EXISTS (SELECT 1 FROM courses WHERE name = 'BSc Computer Science');

-- Ensure users for two teachers
INSERT INTO users (username, password, role)
SELECT 'alice', 'Teacher@123', 'Teacher' WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'alice');
INSERT INTO users (username, password, role)
SELECT 'bob', 'Teacher@123', 'Teacher' WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'bob');

-- Ensure faculty linked to users
-- Note: In this schema, faculty.id does NOT auto-increment and faculty.user_id is NOT NULL/UNIQUE.
-- We'll set faculty.id = users.id for simplicity and provide a unique employee_id.
INSERT INTO faculty (id, user_id, name, email, department_id, employee_id)
SELECT u.id, u.id, 'Alice Smith', 'alice@example.com', (SELECT id FROM departments WHERE name = 'Computer Science'), 'EMP-ALICE'
FROM users u WHERE u.username = 'alice'
  AND NOT EXISTS (SELECT 1 FROM faculty f WHERE f.user_id = u.id OR f.email = 'alice@example.com');

INSERT INTO faculty (id, user_id, name, email, department_id, employee_id)
SELECT u.id, u.id, 'Bob Johnson', 'bob@example.com', (SELECT id FROM departments WHERE name = 'Computer Science'), 'EMP-BOB'
FROM users u WHERE u.username = 'bob'
  AND NOT EXISTS (SELECT 1 FROM faculty f WHERE f.user_id = u.id OR f.email = 'bob@example.com');

-- Find canonical IDs from existing sample data
SET @course_id := (SELECT id FROM courses WHERE name = 'BSc Computer Science' LIMIT 1);
SET @class_id := (SELECT id FROM classes WHERE name IN ('FY','First Year') LIMIT 1);
SET @div_a := (SELECT id FROM divisions WHERE name IN ('Div-A','A') LIMIT 1);
SET @sub_intro := (SELECT id FROM subjects WHERE name IN ('Introduction to Programming') AND course_id = @course_id AND class_id = @class_id LIMIT 1);
SET @sub_ds := (SELECT id FROM subjects WHERE name IN ('Data Structures') AND course_id = @course_id AND class_id = @class_id LIMIT 1);
-- Use faculty.user_id (FK target) for related tables
SET @alice_uid := (SELECT user_id FROM faculty WHERE email = 'alice@example.com' LIMIT 1);
SET @bob_uid := (SELECT user_id FROM faculty WHERE email = 'bob@example.com' LIMIT 1);

-- Note: Subject creation skipped to avoid violating stricter NOT NULL constraints on subjects in this schema.
-- If the expected subjects don't exist, allocations for them will be skipped.

-- Faculty allocations (division_id must be NOT NULL)
INSERT INTO faculty_allocations (faculty_id, subject_id, class_id, division_id)
SELECT @alice_uid, @sub_intro, @class_id, @div_a
WHERE @sub_intro IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM faculty_allocations WHERE faculty_id = @alice_uid AND subject_id = @sub_intro AND class_id = @class_id AND division_id = @div_a
);

INSERT INTO faculty_allocations (faculty_id, subject_id, class_id, division_id)
SELECT @bob_uid, @sub_ds, @class_id, @div_a
WHERE @sub_ds IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM faculty_allocations WHERE faculty_id = @bob_uid AND subject_id = @sub_ds AND class_id = @class_id AND division_id = @div_a
);

-- Availability for both teachers Mon-Fri 09:00-15:00
DELETE FROM faculty_availability WHERE faculty_id IN (@alice_uid, @bob_uid);
INSERT INTO faculty_availability (faculty_id, day_of_week, start_time, end_time, is_available)
SELECT @alice_uid, d.day, '09:00', '15:00', 1 FROM (
  SELECT 'Monday' AS day UNION ALL SELECT 'Tuesday' UNION ALL SELECT 'Wednesday' UNION ALL SELECT 'Thursday' UNION ALL SELECT 'Friday'
) d;
INSERT INTO faculty_availability (faculty_id, day_of_week, start_time, end_time, is_available)
SELECT @bob_uid, d.day, '09:00', '15:00', 1 FROM (
  SELECT 'Monday' AS day UNION ALL SELECT 'Tuesday' UNION ALL SELECT 'Wednesday' UNION ALL SELECT 'Thursday' UNION ALL SELECT 'Friday'
) d;

-- Ensure weekly off on Sunday
-- Add weekly Sunday off if holidays table exists
INSERT INTO institution_holidays (holiday_date, day_of_week, name, applies_to_program, is_recurring)
SELECT NULL, 'Sunday', 'Weekly Off', 'Both', 1
FROM DUAL
WHERE EXISTS (
  SELECT 1 FROM information_schema.tables 
  WHERE table_schema = DATABASE() AND table_name = 'institution_holidays'
)
AND NOT EXISTS (
  SELECT 1 FROM institution_holidays WHERE is_recurring = 1 AND day_of_week = 'Sunday' AND applies_to_program = 'Both'
);

COMMIT;