-- Migration: Enhanced User Permission System
-- Purpose: Add individual user permissions and department-based access control
-- Date: 2025-10-27

USE college_timetable_db;

-- Create user_permissions table for individual user permission assignments
CREATE TABLE IF NOT EXISTS `user_permissions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `permission_id` INT NOT NULL,
  `department_id` INT NULL, -- For department-specific permissions (HOD access)
  `granted_by` INT NOT NULL, -- Which admin granted this permission
  `granted_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `expires_at` TIMESTAMP NULL, -- Optional expiration
  `is_active` BOOLEAN DEFAULT TRUE,
  `notes` TEXT NULL,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`permission_id`) REFERENCES `permissions`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`department_id`) REFERENCES `departments`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`granted_by`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  UNIQUE KEY `unique_user_permission_dept` (`user_id`, `permission_id`, `department_id`)
);

-- Add department_id to users table for HOD assignments
ALTER TABLE `users` 
ADD COLUMN IF NOT EXISTS `department_id` INT NULL AFTER `role`,
ADD COLUMN IF NOT EXISTS `is_hod` BOOLEAN DEFAULT FALSE AFTER `department_id`;

-- Add foreign key for user department
ALTER TABLE `users` 
ADD CONSTRAINT `fk_users_department` 
FOREIGN KEY (`department_id`) REFERENCES `departments`(`id`) ON DELETE SET NULL;

-- Add additional columns to users table for better management
ALTER TABLE `users` 
ADD COLUMN IF NOT EXISTS `failed_attempts` INT DEFAULT 0 AFTER `last_login`,
ADD COLUMN IF NOT EXISTS `locked_until` TIMESTAMP NULL AFTER `failed_attempts`,
ADD COLUMN IF NOT EXISTS `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP AFTER `locked_until`,
ADD COLUMN IF NOT EXISTS `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`;

-- Create permission_groups table for easier management
CREATE TABLE IF NOT EXISTS `permission_groups` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(100) NOT NULL UNIQUE,
  `description` TEXT,
  `module` VARCHAR(50),
  `is_active` BOOLEAN DEFAULT TRUE,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create permission_group_permissions table (many-to-many)
CREATE TABLE IF NOT EXISTS `permission_group_permissions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `group_id` INT NOT NULL,
  `permission_id` INT NOT NULL,
  FOREIGN KEY (`group_id`) REFERENCES `permission_groups`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`permission_id`) REFERENCES `permissions`(`id`) ON DELETE CASCADE,
  UNIQUE KEY `unique_group_permission` (`group_id`, `permission_id`)
);

-- Create user_permission_groups table for bulk assignment
CREATE TABLE IF NOT EXISTS `user_permission_groups` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `group_id` INT NOT NULL,
  `department_id` INT NULL, -- Department-specific group assignment
  `granted_by` INT NOT NULL,
  `granted_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `is_active` BOOLEAN DEFAULT TRUE,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`group_id`) REFERENCES `permission_groups`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`department_id`) REFERENCES `departments`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`granted_by`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  UNIQUE KEY `unique_user_group_dept` (`user_id`, `group_id`, `department_id`)
);

-- Insert default permission groups
INSERT INTO `permission_groups` (`name`, `description`, `module`) VALUES
('Academic Manager', 'Manage courses, departments, faculty, students, subjects', 'academic'),
('Faculty Manager', 'Manage faculty proxy assignments', 'faculty'),
('Timetable Manager', 'Manage and view timetables', 'timetable'),
('User Manager', 'Manage users and roles', 'user_management'),
('HOD Basic', 'Basic Head of Department permissions', 'academic'),
('HOD Advanced', 'Advanced Head of Department permissions', 'academic'),
('Teacher Basic', 'Basic teacher permissions', 'faculty'),
('Student Basic', 'Basic student permissions', 'student');

-- Assign permissions to groups
-- Academic Manager Group
INSERT INTO `permission_group_permissions` (`group_id`, `permission_id`)
SELECT pg.id, p.id 
FROM permission_groups pg, permissions p 
WHERE pg.name = 'Academic Manager' 
AND p.name IN ('manage_courses', 'manage_departments', 'manage_faculty', 'manage_students', 'manage_subjects');

-- Faculty Manager Group
INSERT INTO `permission_group_permissions` (`group_id`, `permission_id`)
SELECT pg.id, p.id 
FROM permission_groups pg, permissions p 
WHERE pg.name = 'Faculty Manager' 
AND p.name IN ('manage_proxy');

-- Timetable Manager Group
INSERT INTO `permission_group_permissions` (`group_id`, `permission_id`)
SELECT pg.id, p.id 
FROM permission_groups pg, permissions p 
WHERE pg.name = 'Timetable Manager' 
AND p.name IN ('manage_timetable', 'view_timetable');

-- User Manager Group
INSERT INTO `permission_group_permissions` (`group_id`, `permission_id`)
SELECT pg.id, p.id 
FROM permission_groups pg, permissions p 
WHERE pg.name = 'User Manager' 
AND p.name IN ('manage_roles', 'manage_users', 'view_users');

-- HOD Basic Group (view only)
INSERT INTO `permission_group_permissions` (`group_id`, `permission_id`)
SELECT pg.id, p.id 
FROM permission_groups pg, permissions p 
WHERE pg.name = 'HOD Basic' 
AND p.name IN ('view_users', 'view_timetable');

-- HOD Advanced Group (department management)
INSERT INTO `permission_group_permissions` (`group_id`, `permission_id`)
SELECT pg.id, p.id 
FROM permission_groups pg, permissions p 
WHERE pg.name = 'HOD Advanced' 
AND p.name IN ('manage_faculty', 'manage_subjects', 'manage_timetable', 'view_timetable', 'view_users');

-- Teacher Basic Group
INSERT INTO `permission_group_permissions` (`group_id`, `permission_id`)
SELECT pg.id, p.id 
FROM permission_groups pg, permissions p 
WHERE pg.name = 'Teacher Basic' 
AND p.name IN ('manage_proxy', 'view_timetable');

-- Create indexes for performance
CREATE INDEX `idx_user_permissions_user` ON `user_permissions`(`user_id`);
CREATE INDEX `idx_user_permissions_permission` ON `user_permissions`(`permission_id`);
CREATE INDEX `idx_user_permissions_department` ON `user_permissions`(`department_id`);
CREATE INDEX `idx_user_permissions_active` ON `user_permissions`(`is_active`);
CREATE INDEX `idx_users_department` ON `users`(`department_id`);
CREATE INDEX `idx_users_hod` ON `users`(`is_hod`);

-- Create view for easier permission checking
CREATE OR REPLACE VIEW `user_all_permissions` AS
SELECT DISTINCT
    u.id as user_id,
    u.username,
    u.role,
    u.department_id as user_department_id,
    u.is_hod,
    p.id as permission_id,
    p.name as permission_name,
    p.module as permission_module,
    COALESCE(up.department_id, upg.department_id) as permission_department_id,
    'individual' as source_type,
    up.granted_at,
    up.expires_at
FROM users u
JOIN user_permissions up ON u.id = up.user_id
JOIN permissions p ON up.permission_id = p.id
WHERE up.is_active = TRUE 
AND (up.expires_at IS NULL OR up.expires_at > NOW())

UNION ALL

SELECT DISTINCT
    u.id as user_id,
    u.username,
    u.role,
    u.department_id as user_department_id,
    u.is_hod,
    p.id as permission_id,
    p.name as permission_name,
    p.module as permission_module,
    upg.department_id as permission_department_id,
    'group' as source_type,
    upg.granted_at,
    NULL as expires_at
FROM users u
JOIN user_permission_groups upg ON u.id = upg.user_id
JOIN permission_group_permissions pgp ON upg.group_id = pgp.group_id
JOIN permissions p ON pgp.permission_id = p.id
WHERE upg.is_active = TRUE

UNION ALL

SELECT DISTINCT
    u.id as user_id,
    u.username,
    u.role,
    u.department_id as user_department_id,
    u.is_hod,
    p.id as permission_id,
    p.name as permission_name,
    p.module as permission_module,
    NULL as permission_department_id,
    'role' as source_type,
    NULL as granted_at,
    NULL as expires_at
FROM users u
JOIN roles r ON u.role = r.name
JOIN role_permissions rp ON r.id = rp.role_id
JOIN permissions p ON rp.permission_id = p.id;

-- Add some sample data for testing
-- Make Ganga Auji HOD of Computer Science (assuming they exist)
UPDATE users u 
JOIN departments d ON d.name = 'Computer Science'
SET u.department_id = d.id, u.is_hod = TRUE 
WHERE u.username = 'ganga.auji' OR u.username = 'ganga_auji';

-- Grant HOD Advanced permissions to HODs
INSERT INTO `user_permission_groups` (`user_id`, `group_id`, `department_id`, `granted_by`)
SELECT 
    u.id,
    pg.id,
    u.department_id,
    1 -- Assuming user ID 1 is a Super Admin
FROM users u
JOIN permission_groups pg ON pg.name = 'HOD Advanced'
WHERE u.is_hod = TRUE AND u.department_id IS NOT NULL;

-- Grant Teacher Basic permissions to all Teachers
INSERT INTO `user_permission_groups` (`user_id`, `group_id`, `granted_by`)
SELECT 
    u.id,
    pg.id,
    1 -- Assuming user ID 1 is a Super Admin
FROM users u
JOIN permission_groups pg ON pg.name = 'Teacher Basic'
WHERE u.role = 'Teacher';

COMMIT;