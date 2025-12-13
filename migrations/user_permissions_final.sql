-- Migration: Enhanced User Permission System
-- Purpose: Add individual user permissions and department-based access control

USE college_timetable_db;

-- Create user_permissions table for individual user permission assignments
CREATE TABLE IF NOT EXISTS `user_permissions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `permission_id` INT NOT NULL,
  `department_id` INT NULL,
  `granted_by` INT NOT NULL,
  `granted_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `expires_at` TIMESTAMP NULL,
  `is_active` BOOLEAN DEFAULT TRUE,
  `notes` TEXT NULL,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`permission_id`) REFERENCES `permissions`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`department_id`) REFERENCES `departments`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`granted_by`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  UNIQUE KEY `unique_user_permission_dept` (`user_id`, `permission_id`, `department_id`)
);

-- Create permission_groups table for easier management
CREATE TABLE IF NOT EXISTS `permission_groups` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(100) NOT NULL UNIQUE,
  `description` TEXT,
  `module` VARCHAR(50),
  `is_active` BOOLEAN DEFAULT TRUE,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create permission_group_permissions table
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
  `department_id` INT NULL,
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
INSERT IGNORE INTO `permission_groups` (`name`, `description`, `module`) VALUES
('Academic Manager', 'Manage courses, departments, faculty, students, subjects', 'academic'),
('Faculty Manager', 'Manage faculty proxy assignments', 'faculty'),
('Timetable Manager', 'Manage and view timetables', 'timetable'),
('User Manager', 'Manage users and roles', 'user_management'),
('HOD Basic', 'Basic Head of Department permissions', 'academic'),
('HOD Advanced', 'Advanced Head of Department permissions', 'academic'),
('Teacher Basic', 'Basic teacher permissions', 'faculty'),
('Student Basic', 'Basic student permissions', 'student');