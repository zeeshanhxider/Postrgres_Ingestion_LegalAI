-- Migration: Restructure document_types table per client requirements
-- Date: 2025-11-26
-- Purpose: Transform document_types into a "Traffic Cop" control center
--          that routes documents to appropriate processing pipelines
-- 
-- NOTE: This migration ADDS columns and INSERTS new rows - it does NOT truncate existing data

-- ============================================================================
-- STEP 1: Add new columns to document_types (IF NOT EXISTS)
-- ============================================================================

-- Role: Separates Authority (Court) from Argument (Party) from Fact (Evidence)
-- Values: 'court', 'party', 'evidence', 'administrative'
ALTER TABLE public.document_types 
ADD COLUMN IF NOT EXISTS role public.citext;

COMMENT ON COLUMN public.document_types.role IS 
'Document authority source: court (rulings), party (briefs), evidence (facts), administrative (procedural)';

-- Category: UI grouping for frontend display
-- Values: 'Court Decisions', 'Party Briefs', 'Evidence', 'Administrative'
ALTER TABLE public.document_types 
ADD COLUMN IF NOT EXISTS category public.citext;

COMMENT ON COLUMN public.document_types.category IS 
'UI grouping label for frontend display (e.g., Court Decisions, Party Briefs, Evidence)';

-- Is Adversarial: Indicates if document is biased/argumentative
-- True for briefs (biased arguments), False for transcripts/opinions (neutral/objective)
ALTER TABLE public.document_types 
ADD COLUMN IF NOT EXISTS is_adversarial boolean DEFAULT false;

COMMENT ON COLUMN public.document_types.is_adversarial IS 
'TRUE if document is biased/argumentative (briefs), FALSE if neutral/objective (opinions, transcripts)';

-- Processing Strategy: Tells backend which pipeline/table to use
-- Values: 'case_outcome', 'brief_extraction', 'evidence_indexing', 'text_only'
ALTER TABLE public.document_types 
ADD COLUMN IF NOT EXISTS processing_strategy public.citext;

COMMENT ON COLUMN public.document_types.processing_strategy IS 
'Backend routing: case_outcome (extract winners), brief_extraction (populate briefs table), evidence_indexing (chunk & embed), text_only (basic indexing)';

-- Display order for UI
ALTER TABLE public.document_types 
ADD COLUMN IF NOT EXISTS display_order integer DEFAULT 100;

COMMENT ON COLUMN public.document_types.display_order IS 
'Sort order for UI display within category';

-- ============================================================================
-- STEP 2: Update existing rows to have the new column values
-- ============================================================================

-- Update existing 'Opinion' type if it exists (map to appellate_opinion behavior)
UPDATE public.document_types 
SET role = 'court', 
    category = 'Court Decisions', 
    is_adversarial = false, 
    processing_strategy = 'case_outcome',
    display_order = 10
WHERE document_type ILIKE '%opinion%' AND role IS NULL;

-- Update existing 'Order' type if it exists
UPDATE public.document_types 
SET role = 'court', 
    category = 'Court Decisions', 
    is_adversarial = false, 
    processing_strategy = 'case_outcome',
    display_order = 20
WHERE document_type ILIKE '%order%' AND role IS NULL;

-- ============================================================================
-- STEP 3: Insert new V1 document types (only if they don't exist)
-- ============================================================================

-- RULINGS (The Logic Source) - role: 'court'
INSERT INTO public.document_types (
    document_type, description, role, category, has_decision, is_adversarial, processing_strategy, display_order
) 
SELECT 'appellate_opinion', 'Appellate court opinion with legal reasoning and outcome determination',
       'court', 'Court Decisions', true, false, 'case_outcome', 10
WHERE NOT EXISTS (SELECT 1 FROM public.document_types WHERE document_type = 'appellate_opinion');

INSERT INTO public.document_types (
    document_type, description, role, category, has_decision, is_adversarial, processing_strategy, display_order
) 
SELECT 'trial_court_order', 'Order issued by trial court judge during proceedings',
       'court', 'Court Decisions', true, false, 'case_outcome', 20
WHERE NOT EXISTS (SELECT 1 FROM public.document_types WHERE document_type = 'trial_court_order');

INSERT INTO public.document_types (
    document_type, description, role, category, has_decision, is_adversarial, processing_strategy, display_order
) 
SELECT 'final_judgment', 'Final judgment or decree from trial or appellate court',
       'court', 'Court Decisions', true, false, 'case_outcome', 30
WHERE NOT EXISTS (SELECT 1 FROM public.document_types WHERE document_type = 'final_judgment');

-- BRIEFS (The Arguments) - role: 'party'
INSERT INTO public.document_types (
    document_type, description, role, category, has_decision, is_adversarial, processing_strategy, display_order
) 
SELECT 'opening_brief', 'Appellant''s initial brief presenting arguments for appeal',
       'party', 'Party Briefs', false, true, 'brief_extraction', 40
WHERE NOT EXISTS (SELECT 1 FROM public.document_types WHERE document_type = 'opening_brief');

INSERT INTO public.document_types (
    document_type, description, role, category, has_decision, is_adversarial, processing_strategy, display_order
) 
SELECT 'respondent_brief', 'Respondent''s brief answering appellant''s arguments',
       'party', 'Party Briefs', false, true, 'brief_extraction', 50
WHERE NOT EXISTS (SELECT 1 FROM public.document_types WHERE document_type = 'respondent_brief');

INSERT INTO public.document_types (
    document_type, description, role, category, has_decision, is_adversarial, processing_strategy, display_order
) 
SELECT 'reply_brief', 'Appellant''s reply brief responding to respondent''s arguments',
       'party', 'Party Briefs', false, true, 'brief_extraction', 60
WHERE NOT EXISTS (SELECT 1 FROM public.document_types WHERE document_type = 'reply_brief');

-- EVIDENCE (The Facts) - role: 'evidence'
INSERT INTO public.document_types (
    document_type, description, role, category, has_decision, is_adversarial, processing_strategy, display_order
) 
SELECT 'transcript', 'Court transcript of hearings, trial proceedings, or depositions',
       'evidence', 'Evidence', false, false, 'evidence_indexing', 70
WHERE NOT EXISTS (SELECT 1 FROM public.document_types WHERE document_type = 'transcript');

INSERT INTO public.document_types (
    document_type, description, role, category, has_decision, is_adversarial, processing_strategy, display_order
) 
SELECT 'exhibit', 'Documentary exhibit submitted as evidence',
       'evidence', 'Evidence', false, false, 'evidence_indexing', 80
WHERE NOT EXISTS (SELECT 1 FROM public.document_types WHERE document_type = 'exhibit');

-- ============================================================================
-- STEP 4: Add constraints (drop first if exist to avoid errors)
-- ============================================================================

ALTER TABLE public.document_types 
DROP CONSTRAINT IF EXISTS chk_document_types_role;

ALTER TABLE public.document_types 
ADD CONSTRAINT chk_document_types_role 
CHECK (role IN ('court', 'party', 'evidence', 'administrative'));

ALTER TABLE public.document_types 
DROP CONSTRAINT IF EXISTS chk_document_types_processing_strategy;

ALTER TABLE public.document_types 
ADD CONSTRAINT chk_document_types_processing_strategy 
CHECK (processing_strategy IN ('case_outcome', 'brief_extraction', 'evidence_indexing', 'text_only'));

-- ============================================================================
-- STEP 5: Create indexes for common lookups (IF NOT EXISTS)
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_document_types_role 
ON public.document_types(role);

CREATE INDEX IF NOT EXISTS idx_document_types_category 
ON public.document_types(category);

CREATE INDEX IF NOT EXISTS idx_document_types_processing_strategy 
ON public.document_types(processing_strategy);

-- ============================================================================
-- STEP 6: Update table comment
-- ============================================================================

COMMENT ON TABLE public.document_types IS 
'Traffic Cop control center: Routes incoming documents to appropriate processing pipelines based on type, role, and strategy. V1 supports: appellate_opinion, trial_court_order, final_judgment (Court); opening_brief, respondent_brief, reply_brief (Party); transcript, exhibit (Evidence).';

-- ============================================================================
-- Verification query
-- ============================================================================
-- Run this to verify the migration:
-- SELECT document_type, role, category, has_decision, is_adversarial, processing_strategy 
-- FROM document_types ORDER BY display_order;
