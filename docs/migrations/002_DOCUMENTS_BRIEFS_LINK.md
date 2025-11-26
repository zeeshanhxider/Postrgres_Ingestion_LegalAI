# Schema Migration: Link Documents to Briefs

**Date:** November 26, 2025  
**Migration File:** `migrations/002_documents_briefs_link.sql`  
**Database:** `cases_llama3_3`

---

## Overview

Made the `documents` table the **central file registry** for ALL documents by adding a `brief_id` column and creating document records for existing briefs.

---

## Problem

Before this migration:

- `documents` table only contained court decisions (1,334 records)
- `briefs` table was separate with no link to `documents`
- No unified way to query "all files in a case"

---

## Solution

1. Added `brief_id` column to `documents` table
2. Created document records for all 179 existing briefs
3. Mapped `brief_type` + `filing_party` → `document_type`

---

## Schema Changes

### New Column Added to `documents`

| Column     | Type        | Description                                                |
| ---------- | ----------- | ---------------------------------------------------------- |
| `brief_id` | BIGINT (FK) | References `briefs.brief_id`, NULL for non-brief documents |

### Columns Made Nullable

| Column          | Reason                                                          |
| --------------- | --------------------------------------------------------------- |
| `case_id`       | Briefs may not have case_id initially (linked via case_file_id) |
| `stage_type_id` | Briefs don't require stage_type                                 |

### New Constraints

```sql
-- Foreign key to briefs
CONSTRAINT documents_brief_id_fkey
FOREIGN KEY (brief_id) REFERENCES briefs(brief_id) ON DELETE SET NULL

-- Unique constraint: one document per brief
UNIQUE INDEX uq_documents_brief_id ON documents(brief_id) WHERE brief_id IS NOT NULL
```

### New Index

```sql
CREATE INDEX idx_documents_brief_id ON documents(brief_id);
```

---

## Brief Type Mapping

The migration maps `briefs.brief_type` + `briefs.filing_party` to `document_types.document_type`:

| brief_type    | filing_party | → document_type    |
| ------------- | ------------ | ------------------ |
| Opening       | Appellant    | `opening_brief`    |
| Response      | Respondent   | `respondent_brief` |
| Reply         | Appellant    | `reply_brief`      |
| Reply         | Respondent   | `reply_brief`      |
| Amended Brief | Appellant    | `opening_brief`    |

---

## Data Changes

### Before Migration

| Table       | Count                       |
| ----------- | --------------------------- |
| `documents` | 1,334 (all Court Decisions) |
| `briefs`    | 179 (not in documents)      |

### After Migration

| document_type       | role  | count     |
| ------------------- | ----- | --------- |
| `appellate_opinion` | court | 1,334     |
| `opening_brief`     | party | 75        |
| `respondent_brief`  | party | 51        |
| `reply_brief`       | party | 53        |
| **Total**           |       | **1,513** |

---

## Document Table Structure (After Migration)

```
documents
├── document_id (PK)
├── case_id (FK → cases) -- NULL allowed for unlinked briefs
├── brief_id (FK → briefs) -- NULL for court decisions, set for briefs
├── document_type_id (FK → document_types)
├── stage_type_id (FK → stage_types) -- NULL allowed
├── title
├── source_url
├── local_path
├── file_size
├── page_count
├── processing_status
├── created_at
└── updated_at
```

---

## Relationship Diagram

```
                    ┌─────────────────┐
                    │  document_types │
                    │  (Traffic Cop)  │
                    └────────┬────────┘
                             │ document_type_id
                             ▼
┌──────────┐         ┌─────────────────┐         ┌──────────┐
│  cases   │◄────────│    documents    │────────►│  briefs  │
└──────────┘ case_id │ (Central File   │ brief_id└──────────┘
                     │    Registry)    │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        case_chunks    case_sentences    embeddings
```

---

## Query Examples

### Get all documents for a case (court decisions + briefs)

```sql
SELECT d.*, dt.document_type, dt.role
FROM documents d
JOIN document_types dt ON d.document_type_id = dt.document_type_id
WHERE d.case_id = 123
ORDER BY dt.display_order;
```

### Get briefs with their document info

```sql
SELECT
    b.brief_id,
    b.brief_type,
    b.filing_party,
    d.document_id,
    dt.document_type,
    dt.processing_strategy
FROM briefs b
JOIN documents d ON d.brief_id = b.brief_id
JOIN document_types dt ON d.document_type_id = dt.document_type_id;
```

### Count documents by role

```sql
SELECT dt.role, dt.category, COUNT(*) as doc_count
FROM documents d
JOIN document_types dt ON d.document_type_id = dt.document_type_id
GROUP BY dt.role, dt.category;
```

---

## How to Run Migration

```powershell
Get-Content "migrations/002_documents_briefs_link.sql" | docker exec -i legal_ai_postgres psql -U postgres -d cases_llama3_3
```

---

## Rollback (if needed)

```sql
-- Remove documents created for briefs
DELETE FROM documents WHERE brief_id IS NOT NULL;

-- Revert Court Decision documents back to original type
UPDATE documents
SET document_type_id = (SELECT document_type_id FROM document_types WHERE document_type = 'Court Decision')
WHERE document_type_id = (SELECT document_type_id FROM document_types WHERE document_type = 'appellate_opinion');

-- Remove brief_id column
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_brief_id_fkey;
DROP INDEX IF EXISTS idx_documents_brief_id;
DROP INDEX IF EXISTS uq_documents_brief_id;
ALTER TABLE documents DROP COLUMN IF EXISTS brief_id;

-- Restore NOT NULL constraints
ALTER TABLE documents ALTER COLUMN case_id SET NOT NULL;
ALTER TABLE documents ALTER COLUMN stage_type_id SET NOT NULL;
```

---

## Files Modified

| File                                           | Change                   |
| ---------------------------------------------- | ------------------------ |
| `migrations/002_documents_briefs_link.sql`     | Created migration script |
| `docs/migrations/002_DOCUMENTS_BRIEFS_LINK.md` | This documentation       |
