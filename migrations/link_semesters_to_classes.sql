-- Add class_id to semesters table to link semesters with year levels
-- FY (class_id=1) -> Sem 1, 2
-- SY (class_id=2) -> Sem 3, 4
-- TY (class_id=3) -> Sem 5, 6
-- Fourth Year (class_id=4) -> Sem 7, 8

SET @dbname = DATABASE();
SET @tablename = "semesters";
SET @columnname = "class_id";

-- Add class_id column if it doesn't exist
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (column_name = @columnname)
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " INT DEFAULT NULL COMMENT 'Links semester to class/year level'")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add foreign key if column was just added
SET @constraintname = "fk_semesters_class";
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
         " FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Update existing semesters to link with classes based on semester_number
-- Semester 1-2 -> FY (assuming class id 1)
-- Semester 3-4 -> SY (assuming class id 2)
-- Semester 5-6 -> TY (assuming class id 3)
-- Semester 7-8 -> Fourth Year (assuming class id 4)

UPDATE semesters s
SET class_id = CASE 
    WHEN semester_number IN (1, 2) THEN (SELECT id FROM classes WHERE name = 'FY' LIMIT 1)
    WHEN semester_number IN (3, 4) THEN (SELECT id FROM classes WHERE name = 'SY' LIMIT 1)
    WHEN semester_number IN (5, 6) THEN (SELECT id FROM classes WHERE name = 'TY' LIMIT 1)
    WHEN semester_number IN (7, 8) THEN (SELECT id FROM classes WHERE name = 'Fourth Year' LIMIT 1)
    ELSE NULL
END
WHERE class_id IS NULL;

-- Create index for better performance (check if exists first)
SET @indexname = "idx_semesters_class";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE
      (table_name = @tablename)
      AND (table_schema = @dbname)
      AND (index_name = @indexname)
  ) > 0,
  "SELECT 1",
  CONCAT("CREATE INDEX ", @indexname, " ON ", @tablename, "(class_id)")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

SELECT 'Semester-class linking migration completed successfully' as status;
