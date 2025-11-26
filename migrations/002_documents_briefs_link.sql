-- Migration: Link Documents to Briefs
-- Date: 2025-11-26
-- Purpose: Add brief_id to documents table and create document records for existing briefs
--          This makes documents the central file registry for ALL documents including briefs
--
-- NOTE: This migration ADDS data - it does NOT delete existing data

-- ============================================================================
-- STEP 1: Add brief_id column to documents table
-- ============================================================================

ALTER TABLE public.documents 
ADD COLUMN IF NOT EXISTS brief_id bigint;

COMMENT ON COLUMN public.documents.brief_id IS 
'FK to briefs table - populated when document is a brief (opening_brief, respondent_brief, reply_brief)';

-- Add foreign key constraint
ALTER TABLE public.documents
DROP CONSTRAINT IF EXISTS documents_brief_id_fkey;

ALTER TABLE public.documents
ADD CONSTRAINT documents_brief_id_fkey 
FOREIGN KEY (brief_id) REFERENCES public.briefs(brief_id) ON DELETE SET NULL;

-- Create index for brief_id lookups
CREATE INDEX IF NOT EXISTS idx_documents_brief_id 
ON public.documents(brief_id);

-- ============================================================================
-- STEP 2: Make case_id nullable (briefs may not have case_id initially)
-- ============================================================================

ALTER TABLE public.documents 
ALTER COLUMN case_id DROP NOT NULL;

-- ============================================================================
-- STEP 3: Make stage_type_id nullable (briefs don't need stage_type)
-- ============================================================================

ALTER TABLE public.documents 
ALTER COLUMN stage_type_id DROP NOT NULL;

-- ============================================================================
-- STEP 4: Create document records for existing briefs
-- Maps brief_type + filing_party -> document_type:
--   Opening + Appellant     -> opening_brief
--   Response + Respondent   -> respondent_brief  
--   Reply + Appellant       -> reply_brief
--   Reply + Respondent      -> reply_brief (respondent's reply)
--   Amended Brief           -> opening_brief (treated as opening)
-- ============================================================================

INSERT INTO public.documents (
    case_id,
    brief_id,
    stage_type_id,
    document_type_id,
    title,
    source_url,
    local_path,
    file_size,
    page_count,
    processing_status,
    created_at,
    updated_at
)
SELECT 
    b.case_id,
    b.brief_id,
    (SELECT stage_type_id FROM stage_types WHERE stage_type = 'Appeal' LIMIT 1),  -- Briefs are appeal stage
    CASE 
        -- Opening Brief: Appellant's initial brief
        WHEN b.brief_type = 'Opening' AND b.filing_party = 'Appellant' 
            THEN (SELECT document_type_id FROM document_types WHERE document_type = 'opening_brief')
        -- Respondent Brief: Respondent's response
        WHEN b.brief_type = 'Response' AND b.filing_party = 'Respondent' 
            THEN (SELECT document_type_id FROM document_types WHERE document_type = 'respondent_brief')
        -- Reply Brief: Either party's reply
        WHEN b.brief_type = 'Reply' 
            THEN (SELECT document_type_id FROM document_types WHERE document_type = 'reply_brief')
        -- Amended Brief: Treat as opening brief
        WHEN b.brief_type = 'Amended Brief' 
            THEN (SELECT document_type_id FROM document_types WHERE document_type = 'opening_brief')
        -- Default fallback to opening_brief
        ELSE (SELECT document_type_id FROM document_types WHERE document_type = 'opening_brief')
    END as document_type_id,
    -- Title: Combine brief_type and filing_party
    b.filing_party || '''s ' || b.brief_type || ' Brief - ' || b.case_file_id as title,
    NULL as source_url,  -- Briefs don't have URLs typically
    b.source_file_path as local_path,
    NULL as file_size,  -- Could be populated later
    b.page_count,
    b.processing_status,
    b.created_at,
    b.updated_at
FROM public.briefs b
WHERE NOT EXISTS (
    -- Don't insert if document already exists for this brief
    SELECT 1 FROM public.documents d WHERE d.brief_id = b.brief_id
);

-- ============================================================================
-- STEP 5: Update existing documents (Court Decisions) to use appellate_opinion type
-- ============================================================================

-- First, ensure we have the Appeal stage type
INSERT INTO public.stage_types (stage_type, description, level)
SELECT 'Appeal', 'Appellate court stage', 2
WHERE NOT EXISTS (SELECT 1 FROM stage_types WHERE stage_type = 'Appeal');

-- Update existing Court Decision documents to appellate_opinion
UPDATE public.documents d
SET document_type_id = (SELECT document_type_id FROM document_types WHERE document_type = 'appellate_opinion')
WHERE d.document_type_id = (SELECT document_type_id FROM document_types WHERE document_type = 'Court Decision')
  AND EXISTS (SELECT 1 FROM document_types WHERE document_type = 'appellate_opinion');

-- ============================================================================
-- STEP 6: Add unique constraint to prevent duplicate brief entries
-- ============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_brief_id 
ON public.documents(brief_id) 
WHERE brief_id IS NOT NULL;

-- ============================================================================
-- STEP 7: Update table comment
-- ============================================================================

COMMENT ON TABLE public.documents IS 
'Central file registry for ALL documents: court decisions (case_id set, brief_id NULL) and briefs (both case_id and brief_id set). Use document_type_id to determine processing strategy.';

-- ============================================================================
-- Verification queries
-- ============================================================================
-- Check document counts by type:
-- SELECT dt.document_type, dt.role, COUNT(d.document_id) as doc_count
-- FROM document_types dt
-- LEFT JOIN documents d ON dt.document_type_id = d.document_type_id
-- GROUP BY dt.document_type, dt.role
-- ORDER BY dt.display_order;

-- Check briefs linked to documents:
-- SELECT b.brief_id, b.brief_type, b.filing_party, d.document_id, dt.document_type
-- FROM briefs b
-- LEFT JOIN documents d ON d.brief_id = b.brief_id
-- LEFT JOIN document_types dt ON d.document_type_id = dt.document_type_id
-- LIMIT 20;
