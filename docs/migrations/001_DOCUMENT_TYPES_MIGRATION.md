# Schema Migration: Document Types Restructure

**Date:** November 26, 2025  
**Migration File:** `migrations/001_document_types_restructure.sql`  
**Database:** `cases_llama3_3`

---

## Overview

Transformed the `document_types` table from a simple lookup table into a **"Traffic Cop" control center** that routes incoming documents to appropriate processing pipelines based on type, role, and strategy.

---

## Client Requirements

### Requirement A: The "Role" Column

> "In your documents table... role: 'court', 'party', 'evidence', 'administrative'"

**Purpose:** Separate Authority (Court) from Argument (Party) from Fact (Evidence).

### Requirement B: The "Doc Type" Column

> "doc_type: one of the above tags"

**V1 Scope - Minimal Set:**

- `appellate_opinion`
- `opening_brief`
- `respondent_brief`
- `reply_brief`
- `trial_court_order`
- `final_judgment`
- `transcript`
- `exhibit`

---

## Schema Changes

### New Columns Added

| Column                | Type    | Description                                                                           |
| --------------------- | ------- | ------------------------------------------------------------------------------------- |
| `role`                | CITEXT  | Document authority source: `court`, `party`, `evidence`, `administrative`             |
| `category`            | CITEXT  | UI grouping label: `Court Decisions`, `Party Briefs`, `Evidence`, `Administrative`    |
| `is_adversarial`      | BOOLEAN | `TRUE` if biased/argumentative (briefs), `FALSE` if neutral (opinions, transcripts)   |
| `processing_strategy` | CITEXT  | Backend routing: `case_outcome`, `brief_extraction`, `evidence_indexing`, `text_only` |
| `display_order`       | INTEGER | Sort order for UI display within category                                             |

### Constraints Added

```sql
CONSTRAINT chk_document_types_role
CHECK (role IN ('court', 'party', 'evidence', 'administrative'))

CONSTRAINT chk_document_types_processing_strategy
CHECK (processing_strategy IN ('case_outcome', 'brief_extraction', 'evidence_indexing', 'text_only'))
```

### Indexes Added

```sql
CREATE INDEX idx_document_types_role ON document_types(role);
CREATE INDEX idx_document_types_category ON document_types(category);
CREATE INDEX idx_document_types_processing_strategy ON document_types(processing_strategy);
```

---

## New Document Types (V1)

### Before Migration

| document_type  | has_decision |
| -------------- | ------------ |
| Court Decision | true         |

### After Migration

| document_type     | role     | category        | has_decision | is_adversarial | processing_strategy |
| ----------------- | -------- | --------------- | ------------ | -------------- | ------------------- |
| Court Decision    | court    | Court Decisions | true         | false          | case_outcome        |
| appellate_opinion | court    | Court Decisions | true         | false          | case_outcome        |
| trial_court_order | court    | Court Decisions | true         | false          | case_outcome        |
| final_judgment    | court    | Court Decisions | true         | false          | case_outcome        |
| opening_brief     | party    | Party Briefs    | false        | true           | brief_extraction    |
| respondent_brief  | party    | Party Briefs    | false        | true           | brief_extraction    |
| reply_brief       | party    | Party Briefs    | false        | true           | brief_extraction    |
| transcript        | evidence | Evidence        | false        | false          | evidence_indexing   |
| exhibit           | evidence | Evidence        | false        | false          | evidence_indexing   |

---

## Processing Strategy Routing Logic

| Strategy            | Trigger Action                                                      |
| ------------------- | ------------------------------------------------------------------- |
| `case_outcome`      | Extract winners, populate `cases` outcome fields                    |
| `brief_extraction`  | Populate `briefs` table with `filing_party`, `responds_to_brief_id` |
| `evidence_indexing` | Chunk and vector embed only, skip briefs table                      |
| `text_only`         | Basic text indexing only                                            |

### Document Type → Strategy Mapping

```
PDF Upload → documents table → Check document_type
    │
    ├── appellate_opinion/trial_court_order/final_judgment
    │   └── processing_strategy = 'case_outcome'
    │       └── Run Outcome Extractor → Update cases table
    │
    ├── opening_brief/respondent_brief/reply_brief
    │   └── processing_strategy = 'brief_extraction'
    │       └── Run Argument Extractor → Populate briefs table
    │
    └── transcript/exhibit
        └── processing_strategy = 'evidence_indexing'
            └── Chunk & Embed → Skip briefs table
```

---

## Files Modified

| File                                            | Change                                                |
| ----------------------------------------------- | ----------------------------------------------------- |
| `migrations/001_document_types_restructure.sql` | Created migration script                              |
| `app/models/document_types.py`                  | Updated Pydantic models with enums & helper functions |
| `docs/CURRENT_SCHEMA.sql`                       | Updated schema documentation                          |
| `docs/DATABASE_STRUCTURE_FOR_AI.md`             | Updated AI-friendly documentation                     |

---

## How to Run Migration

```powershell
# From project root
Get-Content "migrations/001_document_types_restructure.sql" | docker exec -i legal_ai_postgres psql -U postgres -d cases_llama3_3
```

---

## Rollback (if needed)

```sql
-- Remove new columns
ALTER TABLE document_types DROP COLUMN IF EXISTS role;
ALTER TABLE document_types DROP COLUMN IF EXISTS category;
ALTER TABLE document_types DROP COLUMN IF EXISTS is_adversarial;
ALTER TABLE document_types DROP COLUMN IF EXISTS processing_strategy;
ALTER TABLE document_types DROP COLUMN IF EXISTS display_order;

-- Remove new rows
DELETE FROM document_types WHERE document_type IN (
    'appellate_opinion', 'trial_court_order', 'final_judgment',
    'opening_brief', 'respondent_brief', 'reply_brief',
    'transcript', 'exhibit'
);

-- Remove constraints
ALTER TABLE document_types DROP CONSTRAINT IF EXISTS chk_document_types_role;
ALTER TABLE document_types DROP CONSTRAINT IF EXISTS chk_document_types_processing_strategy;

-- Remove indexes
DROP INDEX IF EXISTS idx_document_types_role;
DROP INDEX IF EXISTS idx_document_types_category;
DROP INDEX IF EXISTS idx_document_types_processing_strategy;
```

---

## Data Verification

After migration, all existing data remained intact:

| Table              | Count   | Status       |
| ------------------ | ------- | ------------ |
| `documents`        | 1,334   | ✅ Preserved |
| `case_chunks`      | 4,919   | ✅ Preserved |
| `case_sentences`   | 207,544 | ✅ Preserved |
| `cases`            | 1,334   | ✅ Preserved |
| `briefs`           | 179     | ✅ Preserved |
| `parties`          | 2,659   | ✅ Preserved |
| `attorneys`        | 3,525   | ✅ Preserved |
| `issues_decisions` | 2,273   | ✅ Preserved |
