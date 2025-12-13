-- ============================================================================
-- SCHEMA VERIFICATION SCRIPT
-- ============================================================================
-- Run this to verify your database schema before running migrations
-- ============================================================================

USE college_timetable_db;

-- Show courses table structure
SELECT 'COURSES TABLE COLUMNS:' AS info;
DESCRIBE courses;

-- Show subjects table structure  
SELECT 'SUBJECTS TABLE COLUMNS:' AS info;
DESCRIBE subjects;

-- Show timetable table structure
SELECT 'TIMETABLE TABLE COLUMNS:' AS info;
DESCRIBE timetable;

-- Show faculty_availability table structure
SELECT 'FACULTY_AVAILABILITY TABLE COLUMNS:' AS info;
DESCRIBE faculty_availability;

-- Check current subject data for MSc Data Analytics
SELECT '=== CURRENT SUBJECT CONFIGURATION ===' AS info;
SELECT 
    s.id,
    s.name AS subject_name,
    s.course_code AS subject_code,
    c.code AS course_code,
    c.name AS course_name,
    s.theory_practical,
    s.lectures_per_week,
    s.practical_hours_per_week,
    (s.lectures_per_week + CEIL(s.practical_hours_per_week / 2)) AS calculated_sessions
FROM subjects s
JOIN courses c ON c.id = s.course_id
WHERE c.id = 3  -- Adjust this to your MSc Data Analytics course ID
ORDER BY s.name;

-- Calculate total sessions needed
SELECT '=== TOTAL SESSIONS SUMMARY ===' AS info;
SELECT 
    c.code AS course_code,
    c.name AS course_name,
    COUNT(s.id) AS total_subjects,
    SUM(s.lectures_per_week) AS total_theory_lectures,
    SUM(CEIL(s.practical_hours_per_week / 2)) AS total_practical_sessions,
    SUM(s.lectures_per_week + CEIL(s.practical_hours_per_week / 2)) AS grand_total_sessions
FROM subjects s
JOIN courses c ON c.id = s.course_id
WHERE c.id = 3
GROUP BY c.code, c.name;

-- Check faculty allocations
SELECT '=== FACULTY ALLOCATIONS ===' AS info;
SELECT 
    s.name AS subject_name,
    f.name AS faculty_name,
    fa.is_primary,
    COALESCE(fa.max_hours_per_week, 0) AS max_hours_per_week
FROM faculty_allocations fa
JOIN subjects s ON s.id = fa.subject_id
JOIN faculty f ON f.user_id = fa.faculty_id
JOIN courses c ON c.id = s.course_id
WHERE c.id = 3
ORDER BY s.name, fa.is_primary DESC;

-- Check for any existing timetable entries
SELECT '=== CURRENT TIMETABLE COUNT ===' AS info;
SELECT 
    c.code AS course_code,
    c.name AS course_name,
    COUNT(*) AS total_timetable_entries
FROM timetable t
JOIN courses c ON c.id = t.course_id
WHERE c.id = 3
GROUP BY c.code, c.name;
