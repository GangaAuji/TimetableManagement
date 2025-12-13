-- Migration: Standardize proxy_log schema with approval workflow
-- Date: 2025-10-26
-- Purpose: Add approval_status, approval_date, approved_by to decouple approval from assignment

-- Add new columns
ALTER TABLE proxy_log
ADD COLUMN IF NOT EXISTS approval_status ENUM('PENDING', 'APPROVED', 'REJECTED') DEFAULT 'PENDING' AFTER status,
ADD COLUMN IF NOT EXISTS approval_date DATETIME NULL AFTER approval_status,
ADD COLUMN IF NOT EXISTS approved_by INT NULL AFTER approval_date,
ADD COLUMN IF NOT EXISTS approval_notes TEXT NULL AFTER approved_by,
ADD CONSTRAINT fk_proxy_log_approved_by FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL;

-- Migrate existing data:
-- Old 'ASSIGNED'/'UNASSIGNED' from auto-proxy should be APPROVED
-- Old 'PENDING' stays PENDING
-- Old 'APPROVED' stays APPROVED
-- Old 'REJECTED' stays REJECTED

-- Update approval_status based on old status column
UPDATE proxy_log 
SET approval_status = CASE 
    WHEN status IN ('ASSIGNED', 'UNASSIGNED') THEN 'APPROVED'
    WHEN status = 'PENDING' THEN 'PENDING'
    WHEN status = 'APPROVED' THEN 'APPROVED'
    WHEN status = 'REJECTED' THEN 'REJECTED'
    ELSE 'PENDING'
END
WHERE approval_status IS NULL OR approval_status = 'PENDING';

-- Now we keep status for assignment state: ASSIGNED or UNASSIGNED
-- Update status column to reflect assignment state
UPDATE proxy_log
SET status = CASE
    WHEN proxy_faculty_id IS NOT NULL THEN 'ASSIGNED'
    ELSE 'UNASSIGNED'
END
WHERE approval_status = 'APPROVED';

-- For PENDING and REJECTED, set status to NULL or keep as is
UPDATE proxy_log
SET status = 'PENDING'
WHERE approval_status = 'PENDING';

UPDATE proxy_log
SET status = 'REJECTED'
WHERE approval_status = 'REJECTED';

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_proxy_log_approval_status ON proxy_log(approval_status);
CREATE INDEX IF NOT EXISTS idx_proxy_log_approval_date ON proxy_log(approval_date);

-- Add comment
ALTER TABLE proxy_log 
COMMENT = 'Proxy request log with approval workflow. status=ASSIGNED|UNASSIGNED|PENDING|REJECTED for display; approval_status=PENDING|APPROVED|REJECTED for workflow';
