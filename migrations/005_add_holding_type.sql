-- Migration 005: Add holding_type column to issues_decisions
-- This column stores the granular holding for each issue in mixed-outcome cases
-- 
-- Values: 'affirmed', 'reversed', 'remanded', 'vacated', 'harmless_error'
--
-- This migration is also run automatically by scripts/repair_holding_types.py

-- Add the column with check constraint
ALTER TABLE issues_decisions 
ADD COLUMN IF NOT EXISTS holding_type CITEXT 
CHECK (holding_type IN ('affirmed', 'reversed', 'remanded', 'vacated', 'harmless_error'));

-- Add index for filtering by holding type
CREATE INDEX IF NOT EXISTS idx_issues_decisions_holding_type 
ON issues_decisions(holding_type);

-- Verify
-- SELECT holding_type, COUNT(*) FROM issues_decisions GROUP BY holding_type;
