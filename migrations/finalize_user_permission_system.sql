-- ====================================================================
-- FINALIZE USER PERMISSION SYSTEM
-- This migration ensures the complete permission system is in place
-- with department, course, and class-level access control
-- ====================================================================

-- 1. Ensure all necessary columns exist in users table
-- Check and add columns one by one (MySQL doesn't support IF NOT EXISTS for columns)

-- Add department_id if not exists
SET @dbname = DATABASE();
SET @tablename = "users";
SET @columnname = "department_id";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " INT DEFAULT NULL")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add is_hod if not exists
SET @columnname = "is_hod";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " BOOLEAN DEFAULT FALSE")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add default_course_id if not exists
SET @columnname = "default_course_id";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " INT DEFAULT NULL")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add default_class_id if not exists
SET @columnname = "default_class_id";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " INT DEFAULT NULL")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add foreign key if not exists
SET @constraintname = "fk_users_department";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (constraint_name = @constraintname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD CONSTRAINT ", @constraintname, 
         " FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- 2. Create comprehensive permissions list
INSERT IGNORE INTO permissions (name, description, module) VALUES
-- Academic Management
('view_students', 'View student information', 'academic'),
('manage_students', 'Create, edit, delete students', 'academic'),
('view_faculty', 'View faculty information', 'academic'),
('manage_faculty', 'Create, edit, delete faculty', 'academic'),
('view_courses', 'View courses', 'academic'),
('manage_courses', 'Create, edit, delete courses', 'academic'),
('view_departments', 'View departments', 'academic'),
('manage_departments', 'Create, edit, delete departments', 'academic'),
('view_subjects', 'View subjects', 'academic'),
('manage_subjects', 'Create, edit, delete subjects', 'academic'),
('view_classes', 'View classes', 'academic'),
('manage_classes', 'Create, edit, delete classes', 'academic'),

-- Timetable Management
('view_timetable', 'View timetables', 'timetable'),
('manage_timetable', 'Create, edit, delete timetables', 'timetable'),
('generate_timetable', 'Generate automatic timetables', 'timetable'),
('export_timetable', 'Export timetables', 'timetable'),

-- User Management
('view_users', 'View user information', 'users'),
('manage_users', 'Create, edit, delete users', 'users'),
('manage_roles', 'Manage user roles', 'users'),
('manage_permissions', 'Manage user permissions', 'users'),
('view_activity_log', 'View user activity logs', 'users'),

-- Proxy/Attendance Management
('view_proxy', 'View proxy logs', 'proxy'),
('manage_proxy', 'Create, edit proxy logs', 'proxy'),
('approve_proxy', 'Approve proxy requests', 'proxy'),

-- Reports
('view_reports', 'View reports', 'reports'),
('generate_reports', 'Generate reports', 'reports'),
('export_reports', 'Export reports', 'reports'),

-- System Management
('manage_invitations', 'Manage system invitations', 'system'),
('system_settings', 'Access system settings', 'system'),
('view_analytics', 'View system analytics', 'system');

-- 3. Ensure user_permissions table exists
CREATE TABLE IF NOT EXISTS user_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    permission_id INT NOT NULL,
    department_id INT DEFAULT NULL COMMENT 'NULL = all departments, specific ID = that department only',
    course_id INT DEFAULT NULL COMMENT 'NULL = all courses, specific ID = that course only',
    class_id INT DEFAULT NULL COMMENT 'NULL = all classes, specific ID = that class only',
    granted_by INT NOT NULL,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
    FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_permission (user_id, permission_id, department_id, course_id, class_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Create permission groups table (for bulk permission assignment)
CREATE TABLE IF NOT EXISTS permission_groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    module VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Create permission_group_permissions (many-to-many)
CREATE TABLE IF NOT EXISTS permission_group_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    group_id INT NOT NULL,
    permission_id INT NOT NULL,
    FOREIGN KEY (group_id) REFERENCES permission_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
    UNIQUE KEY unique_group_permission (group_id, permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Create user_permission_groups (assign groups to users)
CREATE TABLE IF NOT EXISTS user_permission_groups (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    group_id INT NOT NULL,
    department_id INT DEFAULT NULL,
    course_id INT DEFAULT NULL,
    class_id INT DEFAULT NULL,
    granted_by INT NOT NULL,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES permission_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
    FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_group (user_id, group_id, department_id, course_id, class_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6a. Add course_id and class_id columns to existing tables if they don't exist
SET @tablename = "user_permissions";
SET @columnname = "course_id";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = DATABASE())
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " INT DEFAULT NULL COMMENT 'NULL = all courses, specific ID = that course only'")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

SET @columnname = "class_id";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = DATABASE())
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " INT DEFAULT NULL COMMENT 'NULL = all classes, specific ID = that class only'")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

SET @tablename = "user_permission_groups";
SET @columnname = "course_id";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = DATABASE())
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " INT DEFAULT NULL")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

SET @columnname = "class_id";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = DATABASE())
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " INT DEFAULT NULL")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- 7. Set up default Super Admin permissions (all permissions)
-- First, ensure Super Admin role has all permissions
DELETE FROM role_permissions WHERE role_id = (SELECT id FROM roles WHERE name = 'Super Admin');

INSERT INTO role_permissions (role_id, permission_id)
SELECT 
    (SELECT id FROM roles WHERE name = 'Super Admin'),
    id
FROM permissions;

-- 8. Create predefined permission groups for common scenarios

-- Academic Admin Group (for department-specific academic management)
INSERT IGNORE INTO permission_groups (name, description, module) VALUES
('Academic Manager', 'Full academic management within assigned department', 'academic');

SET @academic_group_id = (SELECT id FROM permission_groups WHERE name = 'Academic Manager');

INSERT IGNORE INTO permission_group_permissions (group_id, permission_id)
SELECT @academic_group_id, id FROM permissions 
WHERE name IN (
    'view_students', 'manage_students',
    'view_faculty', 'manage_faculty',
    'view_courses', 'manage_courses',
    'view_subjects', 'manage_subjects',
    'view_classes', 'manage_classes',
    'view_reports', 'generate_reports'
);

-- Faculty Manager Group (for HOD/senior faculty)
INSERT IGNORE INTO permission_groups (name, description, module) VALUES
('Faculty Manager', 'Manage faculty and assignments', 'academic');

SET @faculty_group_id = (SELECT id FROM permission_groups WHERE name = 'Faculty Manager');

INSERT IGNORE INTO permission_group_permissions (group_id, permission_id)
SELECT @faculty_group_id, id FROM permissions 
WHERE name IN (
    'view_students', 'view_faculty', 'manage_faculty',
    'view_courses', 'view_subjects', 'view_classes',
    'view_timetable', 'manage_timetable',
    'view_proxy', 'manage_proxy', 'approve_proxy'
);

-- Timetable Manager Group
INSERT IGNORE INTO permission_groups (name, description, module) VALUES
('Timetable Manager', 'Full timetable management', 'timetable');

SET @timetable_group_id = (SELECT id FROM permission_groups WHERE name = 'Timetable Manager');

INSERT IGNORE INTO permission_group_permissions (group_id, permission_id)
SELECT @timetable_group_id, id FROM permissions 
WHERE name IN (
    'view_timetable', 'manage_timetable', 'generate_timetable', 'export_timetable',
    'view_courses', 'view_subjects', 'view_classes', 'view_faculty'
);

-- Student Viewer Group (for faculty who need student access)
INSERT IGNORE INTO permission_groups (name, description, module) VALUES
('Student Viewer', 'View student information', 'academic');

SET @student_viewer_id = (SELECT id FROM permission_groups WHERE name = 'Student Viewer');

INSERT IGNORE INTO permission_group_permissions (group_id, permission_id)
SELECT @student_viewer_id, id FROM permissions 
WHERE name IN ('view_students', 'view_courses', 'view_classes', 'view_timetable');

-- Department Admin Group (for department heads)
INSERT IGNORE INTO permission_groups (name, description, module) VALUES
('Department Admin', 'Full department management', 'academic');

SET @dept_admin_id = (SELECT id FROM permission_groups WHERE name = 'Department Admin');

INSERT IGNORE INTO permission_group_permissions (group_id, permission_id)
SELECT @dept_admin_id, id FROM permissions 
WHERE name IN (
    'view_students', 'manage_students',
    'view_faculty', 'manage_faculty',
    'view_courses', 'manage_courses',
    'view_departments', 'view_subjects', 'manage_subjects',
    'view_classes', 'manage_classes',
    'view_timetable', 'manage_timetable',
    'view_proxy', 'manage_proxy', 'approve_proxy',
    'view_reports', 'generate_reports', 'export_reports'
);

-- 9. Create indexes for better performance
-- MySQL doesn't support IF NOT EXISTS for indexes in older versions, so we'll check first

-- Helper to check if index exists
DELIMITER $$
CREATE PROCEDURE CreateIndexIfNotExists(
    IN tableName VARCHAR(128),
    IN indexName VARCHAR(128),
    IN indexColumns VARCHAR(256)
)
BEGIN
    DECLARE indexExists INT DEFAULT 0;
    
    SELECT COUNT(*) INTO indexExists 
    FROM INFORMATION_SCHEMA.STATISTICS 
    WHERE table_schema = DATABASE() 
      AND table_name = tableName 
      AND index_name = indexName;
    
    IF indexExists = 0 THEN
        SET @sql = CONCAT('CREATE INDEX ', indexName, ' ON ', tableName, '(', indexColumns, ')');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$
DELIMITER ;

-- Create indexes
CALL CreateIndexIfNotExists('user_permissions', 'idx_user_permissions_user', 'user_id');
CALL CreateIndexIfNotExists('user_permissions', 'idx_user_permissions_permission', 'permission_id');
CALL CreateIndexIfNotExists('user_permissions', 'idx_user_permissions_department', 'department_id');
CALL CreateIndexIfNotExists('user_permissions', 'idx_user_permissions_active', 'is_active');
CALL CreateIndexIfNotExists('user_permission_groups', 'idx_user_permission_groups_user', 'user_id');
CALL CreateIndexIfNotExists('user_permission_groups', 'idx_user_permission_groups_group', 'group_id');

-- Drop the helper procedure
DROP PROCEDURE IF EXISTS CreateIndexIfNotExists;

-- 10. Create a view for easy permission checking
CREATE OR REPLACE VIEW v_user_all_permissions AS
SELECT DISTINCT
    u.id as user_id,
    u.username,
    u.role,
    p.id as permission_id,
    p.name as permission_name,
    p.module as permission_module,
    CASE
        WHEN rp.role_id IS NOT NULL THEN 'role'
        WHEN up.id IS NOT NULL THEN 'individual'
        WHEN upg.id IS NOT NULL THEN 'group'
    END as source,
    COALESCE(up.department_id, upg.department_id) as department_id,
    COALESCE(up.course_id, upg.course_id) as course_id,
    COALESCE(up.class_id, upg.class_id) as class_id,
    up.expires_at
FROM users u
CROSS JOIN permissions p
LEFT JOIN roles r ON u.role = r.name
LEFT JOIN role_permissions rp ON r.id = rp.role_id AND p.id = rp.permission_id
LEFT JOIN user_permissions up ON u.id = up.user_id AND p.id = up.permission_id 
    AND up.is_active = TRUE 
    AND (up.expires_at IS NULL OR up.expires_at > NOW())
LEFT JOIN user_permission_groups upg ON u.id = upg.user_id AND upg.is_active = TRUE
LEFT JOIN permission_group_permissions pgp ON upg.group_id = pgp.group_id AND p.id = pgp.permission_id
WHERE rp.role_id IS NOT NULL OR up.id IS NOT NULL OR upg.id IS NOT NULL;

-- ====================================================================
-- USAGE EXAMPLES
-- ====================================================================

-- Example 1: Grant "Computer Science" department admin access to a user
-- This gives user full academic management, but only for Computer Science department
/*
-- Get the user ID and department ID
SET @user_id = (SELECT id FROM users WHERE username = 'cs_admin');
SET @dept_id = (SELECT id FROM departments WHERE name = 'Computer Science');
SET @group_id = (SELECT id FROM permission_groups WHERE name = 'Department Admin');
SET @granted_by = (SELECT id FROM users WHERE role = 'Super Admin' LIMIT 1);

-- Assign the Department Admin group with department restriction
INSERT INTO user_permission_groups (user_id, group_id, department_id, granted_by)
VALUES (@user_id, @group_id, @dept_id, @granted_by);
*/

-- Example 2: Grant individual permission for specific course access
/*
SET @user_id = (SELECT id FROM users WHERE username = 'faculty_user');
SET @perm_id = (SELECT id FROM permissions WHERE name = 'manage_students');
SET @course_id = (SELECT id FROM courses WHERE name = 'BSc Computer Science');
SET @granted_by = (SELECT id FROM users WHERE role = 'Super Admin' LIMIT 1);

-- Grant permission only for specific course
INSERT INTO user_permissions (user_id, permission_id, course_id, granted_by)
VALUES (@user_id, @perm_id, @course_id, @granted_by);
*/

-- Example 3: Check what permissions a user has
/*
SELECT 
    username,
    permission_name,
    permission_module,
    source,
    CASE 
        WHEN department_id IS NULL THEN 'All Departments'
        ELSE (SELECT name FROM departments WHERE id = department_id)
    END as department_access
FROM v_user_all_permissions
WHERE user_id = @user_id
ORDER BY permission_module, permission_name;
*/

-- ====================================================================
-- VERIFICATION QUERIES
-- ====================================================================

-- Check permissions count
SELECT 'Total Permissions' as metric, COUNT(*) as count FROM permissions
UNION ALL
SELECT 'Permission Groups', COUNT(*) FROM permission_groups
UNION ALL
SELECT 'Super Admin Permissions', COUNT(*) 
FROM role_permissions 
WHERE role_id = (SELECT id FROM roles WHERE name = 'Super Admin');

-- Show permission groups and their permissions
SELECT 
    pg.name as group_name,
    GROUP_CONCAT(p.name ORDER BY p.name SEPARATOR ', ') as permissions
FROM permission_groups pg
LEFT JOIN permission_group_permissions pgp ON pg.id = pgp.group_id
LEFT JOIN permissions p ON pgp.permission_id = p.id
WHERE pg.is_active = TRUE
GROUP BY pg.id, pg.name;

-- Show users with individual permissions
SELECT 
    u.username,
    u.role,
    COUNT(DISTINCT up.permission_id) as individual_permissions,
    COUNT(DISTINCT upg.group_id) as permission_groups
FROM users u
LEFT JOIN user_permissions up ON u.id = up.user_id AND up.is_active = TRUE
LEFT JOIN user_permission_groups upg ON u.id = upg.user_id AND upg.is_active = TRUE
GROUP BY u.id, u.username, u.role;
