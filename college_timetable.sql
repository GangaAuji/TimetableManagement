-- Create the database
CREATE DATABASE IF NOT EXISTS college_timetable_db;
USE college_timetable_db;

-- Table structure for users
CREATE TABLE `users` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `username` VARCHAR(50) NOT NULL UNIQUE,
  `password` VARCHAR(255) NOT NULL,
  `role` ENUM('Admin', 'Super Admin', 'Teacher', 'Student') NOT NULL
);

-- Table structure for departments
CREATE TABLE `departments` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(100) NOT NULL UNIQUE
);

-- Table structure for courses
CREATE TABLE `courses` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(100) NOT NULL,
  `program` ENUM('UG', 'PG') NOT NULL,
  `department_id` INT,
  FOREIGN KEY (`department_id`) REFERENCES `departments`(`id`) ON DELETE CASCADE
);

-- Table structure for classes
CREATE TABLE `classes` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(50) NOT NULL -- e.g., FY, SY, TY
);

-- Table structure for divisions
CREATE TABLE `divisions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(50) NOT NULL -- e.g., Div-A, Div-B
);

-- Table structure for subjects
CREATE TABLE `subjects` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(100) NOT NULL,
  `course_id` INT,
  `class_id` INT,
  FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`class_id`) REFERENCES `classes`(`id`) ON DELETE CASCADE
);

-- Table structure for faculty
CREATE TABLE `faculty` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `name` VARCHAR(100) NOT NULL,
  `email` VARCHAR(100) UNIQUE,
  `department_id` INT,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`department_id`) REFERENCES `departments`(`id`) ON DELETE SET NULL
);

-- Table structure for students
CREATE TABLE `students` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `name` VARCHAR(100) NOT NULL,
  `email` VARCHAR(100) UNIQUE,
  `course_id` INT,
  `class_id` INT,
  `division_id` INT,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`class_id`) REFERENCES `classes`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`division_id`) REFERENCES `divisions`(`id`) ON DELETE SET NULL
);

-- Junction table for faculty-subject-class-division allocation
CREATE TABLE `faculty_allocations` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `faculty_id` INT NOT NULL,
  `subject_id` INT NOT NULL,
  `class_id` INT NOT NULL,
  `division_id` INT NOT NULL,
  FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`subject_id`) REFERENCES `subjects`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`class_id`) REFERENCES `classes`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`division_id`) REFERENCES `divisions`(`id`) ON DELETE CASCADE
);

-- Table for faculty availability (can be used for future enhancements)
CREATE TABLE `faculty_availability` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `faculty_id` INT NOT NULL,
  `day_of_week` ENUM('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday') NOT NULL,
  `start_time` TIME NOT NULL,
  `end_time` TIME NOT NULL,
  `is_available` BOOLEAN DEFAULT TRUE,
  FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`id`) ON DELETE CASCADE
);

-- Table structure for timetable
CREATE TABLE `timetable` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `course_id` INT NOT NULL,
  `class_id` INT NOT NULL,
  `division_id` INT NOT NULL,
  `day_of_week` ENUM('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday') NOT NULL,
  `start_time` TIME NOT NULL,
  `end_time` TIME NOT NULL,
  `subject_id` INT NOT NULL,
  `faculty_id` INT NOT NULL,
  FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`class_id`) REFERENCES `classes`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`division_id`) REFERENCES `divisions`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`subject_id`) REFERENCES `subjects`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`id`) ON DELETE CASCADE
);

-- Table for faculty absences
CREATE TABLE `faculty_absences` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `faculty_id` INT NOT NULL,
  `absence_date` DATE NOT NULL,
  `reason` TEXT,
  `status` ENUM('PROCESSED', 'UNPROCESSED') DEFAULT 'UNPROCESSED',
  FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`id`) ON DELETE CASCADE
);

-- Table for proxy management log
CREATE TABLE `proxy_log` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `original_faculty_id` INT NOT NULL,
  `proxy_faculty_id` INT, -- Can be NULL if no proxy is found
  `timetable_id` INT NOT NULL,
  `absence_date` DATE NOT NULL,
  `status` ENUM('ASSIGNED', 'UNASSIGNED') NOT NULL,
  FOREIGN KEY (`original_faculty_id`) REFERENCES `faculty`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`proxy_faculty_id`) REFERENCES `faculty`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`timetable_id`) REFERENCES `timetable`(`id`) ON DELETE CASCADE
);

-- User Management Tables
CREATE TABLE `roles` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(50) NOT NULL UNIQUE,
  `description` TEXT,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE `permissions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(50) NOT NULL UNIQUE,
  `description` TEXT,
  `module` VARCHAR(50) NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE `role_permissions` (
  `role_id` INT NOT NULL,
  `permission_id` INT NOT NULL,
  PRIMARY KEY (`role_id`, `permission_id`),
  FOREIGN KEY (`role_id`) REFERENCES `roles`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`permission_id`) REFERENCES `permissions`(`id`) ON DELETE CASCADE
);

CREATE TABLE `user_activity_log` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `activity_type` VARCHAR(50) NOT NULL,
  `description` TEXT,
  `ip_address` VARCHAR(45),
  `user_agent` TEXT,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
);

CREATE TABLE `password_reset_requests` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `token` VARCHAR(100) NOT NULL,
  `expires_at` TIMESTAMP NOT NULL,
  `used` BOOLEAN DEFAULT FALSE,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
);

-- Alter users table to add more fields
ALTER TABLE `users` 
ADD COLUMN `status` ENUM('active', 'inactive', 'locked') DEFAULT 'active',
ADD COLUMN `last_login` TIMESTAMP NULL,
ADD COLUMN `failed_attempts` INT DEFAULT 0,
ADD COLUMN `password_changed_at` TIMESTAMP NULL,
ADD COLUMN `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Insert default roles and permissions
INSERT INTO `roles` (`name`, `description`) VALUES
('Super Admin', 'Has complete access to all system features'),
('Admin', 'Has access to administrative features'),
('Teacher', 'Has access to teaching-related features'),
('Student', 'Has access to student-related features');

INSERT INTO `permissions` (`name`, `description`, `module`) VALUES
('manage_users', 'Create, edit, and delete users', 'user_management'),
('view_users', 'View user list and details', 'user_management'),
('manage_roles', 'Create, edit, and delete roles', 'user_management'),
('manage_departments', 'Manage department information', 'academic'),
('manage_courses', 'Manage course information', 'academic'),
('manage_subjects', 'Manage subject information', 'academic'),
('manage_faculty', 'Manage faculty information', 'academic'),
('manage_students', 'Manage student information', 'academic'),
('manage_timetable', 'Manage timetable generation', 'timetable'),
('view_timetable', 'View timetable information', 'timetable'),
('manage_proxy', 'Manage proxy arrangements', 'faculty');

-- Assign permissions to roles
INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.name = 'Super Admin';

INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM roles r, permissions p 
WHERE r.name = 'Admin' 
AND p.name IN ('view_users', 'manage_departments', 'manage_courses', 'manage_subjects', 
               'manage_faculty', 'manage_students', 'manage_timetable', 'view_timetable', 'manage_proxy');

INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM roles r, permissions p 
WHERE r.name = 'Teacher' 
AND p.name IN ('view_timetable', 'manage_proxy');

INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM roles r, permissions p 
WHERE r.name = 'Student' 
AND p.name IN ('view_timetable');

-- Insert sample data
INSERT INTO `users` (`username`, `password`, `role`, `status`) VALUES
('Admin', 'Info@1234', 'Admin'),
('Ishaan', 'Info@1234', 'Teacher'),
('Omkar', 'Info@1234', 'Teacher'),
('Ganga', 'Info@1234', 'Student');

INSERT INTO `departments` (`name`) VALUES ('Computer Science'), ('Information Technology');
INSERT INTO `courses` (`name`, `program`, `department_id`) VALUES ('BSc Computer Science', 'UG', 1), ('MSc Data Science', 'PG', 1);
INSERT INTO `classes` (`name`) VALUES ('FY'), ('SY'), ('TY');
INSERT INTO `divisions` (`name`) VALUES ('Div-A'), ('Div-B');
INSERT INTO `subjects` (`name`, `course_id`, `class_id`) VALUES ('Introduction to Programming', 1, 1), ('Data Structures', 1, 1), ('Database Management', 1, 1);

INSERT INTO `faculty` (`user_id`, `name`, `email`, `department_id`) VALUES
(2, 'Dr. Alan Turing', 'alan.turing@gmail.com', 1),
(3, 'Prof. Grace Hopper', 'grace.hopper@gmail.com', 1);

INSERT INTO `students` (`user_id`, `name`, `email`, `course_id`, `class_id`, `division_id`) VALUES (4, 'Ada Lovelace', 'ada.lovelace@example.com', 1, 1, 1);

-- Allocate subjects to faculty
INSERT INTO `faculty_allocations` (`faculty_id`, `subject_id`, `class_id`, `division_id`) VALUES
(1, 1, 1, 1), -- Alan teaches Intro to Prog
(1, 2, 1, 1), -- Alan teaches Data Structures
(2, 3, 1, 1), -- Grace teaches DBMS
(2, 1, 1, 1); -- Grace can also teach Intro to Prog (for proxy)



-- Add these tables to your schema

-- User Roles and Permissions
CREATE TABLE `roles` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(50) NOT NULL UNIQUE,
  `description` TEXT,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Permissions table
CREATE TABLE `permissions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(50) NOT NULL UNIQUE,
  `description` TEXT,
  `module` VARCHAR(50) NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Role-Permission mapping
CREATE TABLE `role_permissions` (
  `role_id` INT NOT NULL,
  `permission_id` INT NOT NULL,
  PRIMARY KEY (`role_id`, `permission_id`),
  FOREIGN KEY (`role_id`) REFERENCES `roles`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`permission_id`) REFERENCES `permissions`(`id`) ON DELETE CASCADE
);

-- User Profile Extension
ALTER TABLE `users` 
ADD COLUMN `status` ENUM('active', 'inactive', 'locked') DEFAULT 'active',
ADD COLUMN `last_login` TIMESTAMP NULL,
ADD COLUMN `failed_attempts` INT DEFAULT 0,
ADD COLUMN `password_changed_at` TIMESTAMP NULL,
ADD COLUMN `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- User Activity Log
CREATE TABLE `user_activity_log` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `activity_type` VARCHAR(50) NOT NULL,
  `description` TEXT,
  `ip_address` VARCHAR(45),
  `user_agent` TEXT,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
);

-- Password Reset Requests
CREATE TABLE `password_reset_requests` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `token` VARCHAR(100) NOT NULL,
  `expires_at` TIMESTAMP NOT NULL,
  `used` BOOLEAN DEFAULT FALSE,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
);

-- Registration Invitations (for invitation-based registration system)
CREATE TABLE `registration_invitations` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `token` VARCHAR(64) NOT NULL UNIQUE,
  `email` VARCHAR(100) NOT NULL,
  `role` ENUM('Teacher', 'Student') NOT NULL,
  `name` VARCHAR(100),
  `course_id` INT DEFAULT NULL,
  `class_id` INT DEFAULT NULL,
  `division_id` INT DEFAULT NULL,
  `department_id` INT DEFAULT NULL,
  `created_by` INT NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `expires_at` TIMESTAMP NOT NULL,
  `used_at` TIMESTAMP NULL DEFAULT NULL,
  `status` ENUM('pending', 'used', 'expired') DEFAULT 'pending',
  FOREIGN KEY (`created_by`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`course_id`) REFERENCES `courses`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`class_id`) REFERENCES `classes`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`division_id`) REFERENCES `divisions`(`id`) ON DELETE SET NULL,
  FOREIGN KEY (`department_id`) REFERENCES `departments`(`id`) ON DELETE SET NULL,
  INDEX idx_token (`token`),
  INDEX idx_email (`email`),
  INDEX idx_status (`status`),
  INDEX idx_expires (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `faculty_absences` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `faculty_id` INT NOT NULL,
  `absence_date` DATE NOT NULL,
  `reason` TEXT,
  `status` ENUM('PROCESSED', 'UNPROCESSED') DEFAULT 'UNPROCESSED',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`id`) ON DELETE CASCADE,
  INDEX idx_faculty_date (`faculty_id`, `absence_date`),
  INDEX idx_status (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;