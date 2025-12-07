-- Migration: 008_schema_improvements.sql
-- Purpose: Fix schema issues for general legal case ingestion (not just divorce cases)
-- This migration is idempotent (safe to run multiple times)

-- ============================================================================
-- 1. FIX: Remove 'divorce' default from case_type - data is now general legal cases
-- ============================================================================

-- Remove the default constraint (cases should have NULL or explicit type)
ALTER TABLE cases ALTER COLUMN case_type DROP DEFAULT;

-- Add comment explaining the column
COMMENT ON COLUMN cases.case_type IS 'Case type classification: criminal, civil, family, administrative, etc. NULL if not yet classified.';


-- ============================================================================
-- 2. ADD: publication_status column for Published/Unpublished/Partially Published
-- ============================================================================

-- Add publication_status column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cases' AND column_name = 'publication_status'
    ) THEN
        ALTER TABLE cases ADD COLUMN publication_status CITEXT;
    END IF;
END $$;

-- Add check constraint for valid values
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints 
        WHERE constraint_name = 'chk_cases_publication_status'
    ) THEN
        ALTER TABLE cases ADD CONSTRAINT chk_cases_publication_status 
            CHECK (publication_status IS NULL OR publication_status IN (
                'Published', 
                'Unpublished', 
                'Partially Published',
                'Published in Part'
            ));
    END IF;
END $$;

-- Add comment explaining the column
COMMENT ON COLUMN cases.publication_status IS 'Publication status: Published, Unpublished, Partially Published, or Published in Part';

-- Create index for filtering by publication status
CREATE INDEX IF NOT EXISTS idx_cases_publication_status ON cases (publication_status);


-- ============================================================================
-- 3. ADD: court_type to courts_dim for Supreme Court vs Court of Appeals distinction
-- ============================================================================

-- Add court_type column to courts_dim if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'courts_dim' AND column_name = 'court_type'
    ) THEN
        ALTER TABLE courts_dim ADD COLUMN court_type CITEXT;
    END IF;
END $$;

-- Add check constraint for valid court types
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints 
        WHERE constraint_name = 'chk_courts_dim_court_type'
    ) THEN
        ALTER TABLE courts_dim ADD CONSTRAINT chk_courts_dim_court_type 
            CHECK (court_type IS NULL OR court_type IN (
                'Supreme Court',
                'Court of Appeals',
                'Superior Court',
                'District Court',
                'Municipal Court'
            ));
    END IF;
END $$;

-- Add comment explaining the column
COMMENT ON COLUMN courts_dim.court_type IS 'Court hierarchy type: Supreme Court, Court of Appeals, Superior Court, etc.';

-- Create index for filtering by court type
CREATE INDEX IF NOT EXISTS idx_courts_dim_court_type ON courts_dim (court_type);

-- Pre-populate Washington State courts if they don't exist
INSERT INTO courts_dim (court, level, jurisdiction, court_type)
VALUES 
    ('Washington Supreme Court', 'Supreme', 'Washington', 'Supreme Court'),
    ('Washington Court of Appeals Division I', 'Appeals', 'Washington', 'Court of Appeals'),
    ('Washington Court of Appeals Division II', 'Appeals', 'Washington', 'Court of Appeals'),
    ('Washington Court of Appeals Division III', 'Appeals', 'Washington', 'Court of Appeals')
ON CONFLICT (court) DO UPDATE SET 
    court_type = EXCLUDED.court_type,
    level = EXCLUDED.level;


-- ============================================================================
-- 4. ADD: processing_status for tracking ingestion pipeline progress
-- ============================================================================

-- Add processing_status column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cases' AND column_name = 'processing_status'
    ) THEN
        ALTER TABLE cases ADD COLUMN processing_status CITEXT DEFAULT 'pending';
    END IF;
END $$;

-- Add check constraint for valid processing statuses
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints 
        WHERE constraint_name = 'chk_cases_processing_status'
    ) THEN
        ALTER TABLE cases ADD CONSTRAINT chk_cases_processing_status 
            CHECK (processing_status IN (
                'pending',           -- Just created, no processing done
                'text_extracted',    -- PDF parsed, text stored, chunks created
                'ai_processed',      -- AI extraction completed (parties, issues, etc.)
                'embedded',          -- Embeddings generated
                'fully_processed',   -- All processing complete
                'failed'             -- Processing failed
            ));
    END IF;
END $$;

-- Add comment explaining the column
COMMENT ON COLUMN cases.processing_status IS 'Ingestion pipeline status: pending → text_extracted → ai_processed → embedded → fully_processed';

-- Create index for filtering by processing status (for batch operations)
CREATE INDEX IF NOT EXISTS idx_cases_processing_status ON cases (processing_status);


-- ============================================================================
-- 5. ADD: ingestion_batch_id for tracking batch runs
-- ============================================================================

-- Add ingestion_batch_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'cases' AND column_name = 'ingestion_batch_id'
    ) THEN
        ALTER TABLE cases ADD COLUMN ingestion_batch_id UUID;
    END IF;
END $$;

-- Add comment explaining the column
COMMENT ON COLUMN cases.ingestion_batch_id IS 'UUID of the batch that ingested this case, for tracking and rollback';

-- Create index for batch queries
CREATE INDEX IF NOT EXISTS idx_cases_ingestion_batch_id ON cases (ingestion_batch_id);


-- ============================================================================
-- 6. CREATE: ingestion_batches table for tracking batch processing runs
-- ============================================================================

CREATE TABLE IF NOT EXISTS ingestion_batches (
    batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_name TEXT NOT NULL,
    source_type CITEXT NOT NULL,  -- 'supreme_court', 'court_of_appeals', 'briefs', 'mixed'
    source_path TEXT,             -- Path to source directory or CSV
    started_at TIMESTAMP DEFAULT now(),
    completed_at TIMESTAMP,
    total_files INT DEFAULT 0,
    processed_files INT DEFAULT 0,
    failed_files INT DEFAULT 0,
    skipped_files INT DEFAULT 0,
    status CITEXT DEFAULT 'running',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT now() NOT NULL,
    
    CONSTRAINT chk_ingestion_batches_status CHECK (status IN (
        'running', 'completed', 'failed', 'cancelled', 'paused'
    )),
    CONSTRAINT chk_ingestion_batches_source_type CHECK (source_type IN (
        'supreme_court', 'court_of_appeals', 'court_of_appeals_partial', 'briefs', 'mixed', 'csv'
    ))
);

-- Add comments
COMMENT ON TABLE ingestion_batches IS 'Tracks batch ingestion runs for progress monitoring and rollback capability';
COMMENT ON COLUMN ingestion_batches.source_type IS 'Type of documents: supreme_court, court_of_appeals, court_of_appeals_partial, briefs, mixed, csv';


-- ============================================================================
-- 7. ADD: Unique constraint to prevent duplicate case ingestion
-- ============================================================================

-- Create unique index on case_file_id + court_level (allows multiple records only if case_file_id is NULL)
CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_unique_case_file 
    ON cases (case_file_id, court_level) 
    WHERE case_file_id IS NOT NULL;

-- Add comment
COMMENT ON INDEX idx_cases_unique_case_file IS 'Prevents duplicate cases with same case_file_id and court_level';


-- ============================================================================
-- 8. UPDATE: Existing cases to have proper defaults
-- ============================================================================

-- Set processing_status for existing cases that have full_text
UPDATE cases 
SET processing_status = 'text_extracted' 
WHERE processing_status IS NULL AND full_text IS NOT NULL;

-- Set processing_status for existing cases that have embeddings
UPDATE cases 
SET processing_status = 'embedded' 
WHERE processing_status = 'text_extracted' AND full_embedding IS NOT NULL;

-- Set publication_status to 'Published' for existing cases (they were from published opinions)
UPDATE cases 
SET publication_status = 'Published' 
WHERE publication_status IS NULL;


-- ============================================================================
-- Summary of changes:
-- ============================================================================
-- 1. Removed 'divorce' default from case_type column
-- 2. Added publication_status column with check constraint
-- 3. Added court_type column to courts_dim with pre-populated WA courts
-- 4. Added processing_status column for pipeline tracking
-- 5. Added ingestion_batch_id column for batch tracking
-- 6. Created ingestion_batches table
-- 7. Added unique constraint on (case_file_id, court_level)
-- 8. Updated existing records with sensible defaults
