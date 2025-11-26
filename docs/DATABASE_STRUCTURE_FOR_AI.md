# Database Structure Guide for AI Query Generation

## Overview

This database stores Washington State family law appellate cases extracted from PDFs using AI (Ollama/OpenAI). The system uses Pydantic models to validate AI-extracted data before insertion into PostgreSQL. All data flows through the AI extraction pipeline → Pydantic validation → database insertion.

---

## Core Tables & Relationships

### 1. **CASES** (Primary Entity)

**Table:** `cases`
**Purpose:** Main case information extracted from legal documents

**Key Fields:**

- `case_id` (PK, BIGINT): Auto-generated unique identifier
- `case_file_id` (CITEXT): Court's internal file number extracted from document (e.g., "73404-1")
- `title` (CITEXT, NOT NULL): Case name (e.g., "In Re The Marriage Of Smith V. Jones")
- `docket_number` (CITEXT): Appeals court docket number (e.g., "50059-1-II")
- `source_docket_number` (CITEXT): Original trial court docket number
- `county` (CITEXT): County where case originated (extracted from PDF)
- `district` (CITEXT): Division - "Division I", "Division II", "Division III", or NULL
- `court_level` (CITEXT): "Appeals" or "Supreme"
- `court` (CITEXT): Full court name (e.g., "Washington State Court of Appeals Division Two")
- `court_id` (FK → courts_dim): Normalized court reference
- `case_type_id` (FK → case_types): References dimension table
- `case_type` (CITEXT): Legacy field - "divorce", "marriage", "criminal", "civil", "family", "business"

**Trial Judge Information:**

- `trial_judge` (CITEXT): Trial court judge name with title

**Dates (All Optional DATE fields):**

- `trial_start_date`: When trial proceedings began
- `trial_end_date`: When trial court made decision
- `trial_published_date`: When trial court decision was published
- `appeal_start_date`: When appeal was filed
- `appeal_end_date`: When appellate court made final decision
- `appeal_published_date`: When appellate court decision was published
- `oral_argument_date`: When oral arguments were presented

**Outcomes:**

- `published` (BOOLEAN): Publication status (TRUE/FALSE)
- `overall_case_outcome` (CITEXT): Overall result - "affirmed", "reversed", "remanded_full", "remanded_partial", "dismissed", "split", "partial", "other"
- `winner_legal_role` (CITEXT): Who won - "Appellant", "Respondent", "Petitioner", "Third Party", or NULL
- `winner_personal_role` (CITEXT): Personal role of winner - "Husband", "Wife", "Parent", "Other", "Estate", or NULL
- `appeal_outcome` (CITEXT): Overall appeal result - "reversed", "affirmed", "remanded", "dismissed", "partial", "split", "remanded_partial", "remanded_full", or NULL

**Full Text & Metadata:**

- `summary` (TEXT): 2-3 sentence case summary
- `full_text` (TEXT): Complete case text
- `full_embedding` (VECTOR(1024)): Document-level embedding for semantic search
- `source_file` (CITEXT): Original PDF filename
- `source_file_path` (TEXT): Full path to source PDF
- `source_url` (TEXT): Original URL or court website link
- `extraction_timestamp` (TIMESTAMP): When this case was extracted
- `created_at`, `updated_at` (TIMESTAMP): Record timestamps

---

### 2. **PARTIES**

**Table:** `parties`
**Purpose:** Track all parties involved in case (extracted from case heading and party sections)

**Key Fields:**

- `party_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `name` (CITEXT, NOT NULL): Full party name
- `legal_role` (CITEXT): Role in case - "Appellant", "Respondent", "Petitioner", "Third Party", "Appellant/Cross Respondent", "Respondent/Cross Appellant", "Unknown"
- `personal_role` (CITEXT): Family relationship - "Husband", "Wife", "Parent", "Other", "Estate", or NULL (only for family law cases)
- `party_type` (CITEXT): "Individual" or "Organization"
- `created_at` (TIMESTAMP)

**AI Extraction Notes:**

- Personal roles are only extracted for family law cases (divorce, paternity, custody)
- For civil/criminal cases, `personal_role` is NULL
- Pydantic validator handles NULL personal roles gracefully

---

### 3. **ATTORNEYS**

**Table:** `attorneys`
**Purpose:** Track legal representation (extracted from attorney sections)

**Key Fields:**

- `attorney_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `name` (CITEXT, NOT NULL): Attorney full name
- `firm_name` (CITEXT): Law firm name (if mentioned)
- `firm_address` (TEXT): Complete firm address
- `representing` (CITEXT): Legal role they represent - "Appellant", "Respondent", "Petitioner", "Third Party", "Unknown"
- `attorney_type` (CITEXT): "Attorney", "Counsel", "Public Defender", "Unknown"
- `created_at` (TIMESTAMP)

**AI Extraction Notes:**

- Pydantic validator parses descriptive representations (e.g., "Guardian ad litem for J.H.") into standard legal roles
- Complex representations like "for the Appellant/Cross Respondent" are simplified to "Appellant"

---

### 4. **ISSUES & DECISIONS**

**Table:** `issues_decisions`
**Purpose:** Individual legal issues and their outcomes within a case (Washington State divorce appeals categorization)

**Key Fields:**

- `issue_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)

**Washington State Categorization:**

- `category` (CITEXT, NOT NULL): Top-level category
  - "Spousal Support / Maintenance"
  - "Child Support"
  - "Parenting Plan / Custody / Visitation"
  - "Property Division / Debt Allocation"
  - "Attorney Fees & Costs"
  - "Procedural & Evidentiary Issues"
  - "Jurisdiction & Venue"
  - "Enforcement & Contempt Orders"
  - "Modification Orders"
  - "Miscellaneous / Unclassified"
- `subcategory` (CITEXT, NOT NULL): Mid-level detail
  - Examples: "Duration (temp vs. permanent)", "Income determination / imputation", "Residential schedule", "Valuation of assets"
- `rcw_reference` (CITEXT): Washington RCW statute (e.g., "RCW 26.09.090")
- `keywords` (CITEXT[]): Array of keywords (e.g., ["rehabilitative maintenance", "indefinite award"])

**Issue Details:**

- `issue_summary` (TEXT, NOT NULL): Specific issue description from case

**Decision Details:**

- `decision_stage` (CITEXT): "trial", "appeal", or NULL
- `decision_summary` (TEXT): What the court decided on this issue
- `appeal_outcome` (CITEXT): Outcome for THIS specific issue - "reversed", "affirmed", "remanded", "dismissed", "partial", "split", "remanded_partial", "remanded_full", or NULL
- `winner_legal_role` (CITEXT): "appellant", "respondent", or NULL
- `winner_personal_role` (CITEXT): "husband", "wife", etc., or NULL

**AI Metadata:**

- `confidence_score` (REAL): AI extraction confidence (0.0 to 1.0)
- `created_at`, `updated_at` (TIMESTAMP)

**Important:** A single case can have multiple issues with different outcomes. Use DISTINCT when counting cases.

---

### 5. **ARGUMENTS**

**Table:** `arguments`
**Purpose:** Track legal arguments made by each side for specific issues

**Key Fields:**

- `argument_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `issue_id` (FK → issues_decisions, NOT NULL)
- `side` (CITEXT, NOT NULL): "Appellant", "Respondent", "Court"
- `argument_text` (TEXT, NOT NULL): The actual argument content
- `created_at`, `updated_at` (TIMESTAMP)

---

### 6. **CASE CITATIONS** (Precedents)

**Table:** `citation_edges`
**Purpose:** Track which cases cite which precedents (graph-like structure)

**Key Fields:**

- `citation_id` (PK, BIGINT)
- `source_case_id` (FK → cases, NOT NULL): The citing case
- `target_case_citation` (CITEXT, NOT NULL): Raw citation text (e.g., "490 U.S. 581")
- `target_case_id` (BIGINT): Resolved target case ID (if available)
- `relationship` (CITEXT): "cites", "distinguishes", "overrules", etc.
- `importance` (CITEXT): "key", "support", etc.
- `pin_cite` (CITEXT): Specific page reference (e.g., "at 589-590")
- `created_at` (TIMESTAMP)

**Usage for Queries:**

- Find most cited cases overall
- Find most cited cases for specific issue categories
- Track precedent relationships

---

### 7. **STATUTE CITATIONS**

**Table:** `statute_citations`
**Purpose:** Track statutory references

**Key Fields:**

- `id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `statute_id` (FK → statutes_dim): Normalized statute reference
- `raw_text` (TEXT): Raw citation text as it appears
- `created_at` (TIMESTAMP)

**Related Dimension Table:** `statutes_dim`

- `statute_id`, `jurisdiction` (e.g., "WA", "US"), `code` (e.g., "RCW", "USC")
- `title`, `section`, `subsection`, `display_text`

---

### 8. **JUDGES**

**Tables:** `judges` (dimension), `case_judges` (mapping)

**judges:**

- `judge_id` (PK, BIGINT)
- `name` (CITEXT, UNIQUE, NOT NULL): Judge name

**case_judges:**

- `id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `judge_id` (FK → judges, NOT NULL)
- `role` (CITEXT): "Author", "Concurring", "Dissenting", "Panelist"
- `court` (CITEXT): Which court (trial vs. appellate)
- `created_at` (TIMESTAMP)

---

### 9. **FULL-TEXT SEARCH TABLES**

#### **A. Documents**

**Table:** `documents`

- `document_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `stage_type_id` (FK → stage_types)
- `document_type_id` (FK → document_types)
- `title`, `source_url`, `local_path`, `file_size`, `page_count`
- `processing_status` (CITEXT): "pending", "processing", "completed", "failed"

#### **B. Chunks**

**Table:** `case_chunks`
**Purpose:** Document broken into paragraph/section-level chunks for efficient retrieval

**Key Fields:**

- `chunk_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `document_id` (FK → documents)
- `chunk_order` (INT, NOT NULL): Sequential order (1..N)
- `section` (CITEXT): Section label (e.g., "FACTS", "ANALYSIS", "MAINTENANCE")
- `text` (TEXT, NOT NULL): Chunk content
- `sentence_count` (INTEGER): Number of sentences in chunk
- `tsv` (TSVECTOR): Full-text search vector (auto-generated)
- `created_at`, `updated_at` (TIMESTAMP)

**Indexes:**

- Unique: `(case_id, chunk_order)`
- GIN index on `tsv` for full-text search

#### **C. Sentences**

**Table:** `case_sentences`
**Purpose:** Sentence-level text for precise searching and phrase extraction

**Key Fields:**

- `sentence_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `chunk_id` (FK → case_chunks, NOT NULL)
- `document_id` (FK → documents)
- `sentence_order` (INTEGER): Order within chunk
- `global_sentence_order` (INTEGER): Order within entire case
- `text` (TEXT, NOT NULL): Sentence text
- `word_count` (INTEGER)
- `tsv` (TSVECTOR): Full-text search vector (auto-generated)
- `created_at`, `updated_at` (TIMESTAMP)

**Indexes:**

- Unique: `(case_id, chunk_id, sentence_order)`
- GIN index on `tsv` for full-text search

#### **D. Word Dictionary & Occurrences**

**Tables:** `word_dictionary`, `word_occurrence`

**word_dictionary:**

- `word_id` (PK, SERIAL)
- `word` (CITEXT, UNIQUE, NOT NULL): Lowercase word
- `lemma` (CITEXT): Lemmatized form
- `df` (INT): Document frequency (# of cases containing this word)

**word_occurrence:**

- `word_id` (FK → word_dictionary)
- `case_id` (FK → cases)
- `chunk_id` (FK → case_chunks)
- `sentence_id` (FK → case_sentences)
- `document_id` (FK → documents)
- `position` (INT, NOT NULL): Token index within sentence (0-based)
- **PK:** `(word_id, sentence_id, position)`

**Usage:**

- Find every occurrence of specific words across all cases
- Enables precise phrase matching by position

#### **E. Phrase Dictionary & Occurrences**

**Tables:** `case_phrases`

**case_phrases:**

- `phrase_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `document_id` (FK → documents)
- `phrase` (CITEXT, NOT NULL): N-gram phrase (e.g., "spousal support", "business valuation")
- `n` (SMALLINT): Phrase length (2, 3, or 4 words)
- `frequency` (INT): Occurrence count in this case
- `example_sentence` (FK → case_sentences): Reference to first occurrence
- `example_chunk` (FK → case_chunks)
- `created_at` (TIMESTAMP)

**Indexes:**

- Unique: `(case_id, phrase)`
- GIN trigram index on `phrase` for fuzzy matching

---

### 10. **EMBEDDINGS** (Semantic Search)

**Table:** `embeddings`
**Purpose:** Vector embeddings for semantic similarity search

**Key Fields:**

- `embedding_id` (PK, BIGINT)
- `case_id` (FK → cases, NOT NULL)
- `chunk_id` (FK → case_chunks, NOT NULL)
- `document_id` (FK → documents)
- `text` (TEXT, NOT NULL): Chunk text
- `embedding` (VECTOR(1024), NOT NULL): 1024-dimensional vector
- `chunk_order` (INTEGER): Order within case
- `section` (CITEXT): Section type
- `created_at`, `updated_at` (TIMESTAMP)

**Indexes:**

- HNSW index on `embedding` for fast cosine similarity search
- GIN index on `text` for full-text search

---

## Dimension Tables (Reference Data)

### **courts_dim**

- `court_id`, `court` (UNIQUE), `level` ("Supreme Court", "Court of Appeals")
- `jurisdiction` ("WA", "US"), `district`, `county`

### **case_types**

- `case_type_id`, `case_type` (UNIQUE, CITEXT)
- Values: "divorce", "paternity", "custody", "domestic_violence", "adoption", "other"
- `description`, `jurisdiction`, `created_at`

### **stage_types**

- `stage_type_id`, `stage_type` (UNIQUE, CITEXT)
- Values: "Trial", "Appeal", "Post-Appeal", "Other"
- `description`, `level` (INTEGER), `created_at`

### **document_types** (Traffic Cop Control Center)

**Purpose:** Routes incoming documents to appropriate processing pipelines based on type, role, and strategy.

**Key Fields:**

- `document_type_id` (PK, BIGINT)
- `document_type` (UNIQUE, CITEXT): Machine-readable slug

**Role Column** (Separates Authority from Argument from Fact):

- `role` (CITEXT): "court", "party", "evidence", "administrative"

**Category Column** (UI Grouping):

- `category` (CITEXT): "Court Decisions", "Party Briefs", "Evidence", "Administrative"

**Processing Flags:**

- `has_decision` (BOOLEAN): TRUE if document declares a winner
- `is_adversarial` (BOOLEAN): TRUE if biased/argumentative (briefs), FALSE if neutral (opinions, transcripts)

**Processing Strategy** (Backend Routing):

- `processing_strategy` (CITEXT): "case_outcome", "brief_extraction", "evidence_indexing", "text_only"

**V1 Supported Types:**
| Slug | Role | Category | has_decision | is_adversarial | Strategy |
|------|------|----------|--------------|----------------|----------|
| `appellate_opinion` | court | Court Decisions | TRUE | FALSE | case_outcome |
| `trial_court_order` | court | Court Decisions | TRUE | FALSE | case_outcome |
| `final_judgment` | court | Court Decisions | TRUE | FALSE | case_outcome |
| `opening_brief` | party | Party Briefs | FALSE | TRUE | brief_extraction |
| `respondent_brief` | party | Party Briefs | FALSE | TRUE | brief_extraction |
| `reply_brief` | party | Party Briefs | FALSE | TRUE | brief_extraction |
| `transcript` | evidence | Evidence | FALSE | FALSE | evidence_indexing |
| `exhibit` | evidence | Evidence | FALSE | FALSE | evidence_indexing |

**Routing Logic:**

- `processing_strategy = 'case_outcome'` → Extract winners, populate `cases` outcome fields
- `processing_strategy = 'brief_extraction'` → Populate `briefs` table with filing_party, responds_to
- `processing_strategy = 'evidence_indexing'` → Chunk and vector embed, skip briefs table
- `processing_strategy = 'text_only'` → Basic text indexing only

---

## Critical Enum Values (From Pydantic Models)

### Court Level (`cases.court_level`)

```
"Appeals" | "Supreme"
```

### District (`cases.district`)

```
"Division I" | "Division II" | "Division III" | NULL
```

### Publication Status (`cases.published`)

```
BOOLEAN: TRUE | FALSE
```

**Note:** The Pydantic model accepts various text inputs ("Published", "Unpublished", etc.) but converts to boolean for database.

### Legal Roles (`parties.legal_role`, `attorneys.representing`)

```
"Appellant" | "Respondent" | "Petitioner" | "Third Party" |
"Appellant/Cross Respondent" | "Respondent/Cross Appellant" | "Unknown"
```

**Note:** Also accepts lowercase versions. Validators normalize variations.

### Personal Roles (`parties.personal_role`)

```
"Husband" | "Wife" | "Parent" | "Other" | "Estate" | NULL
```

**Critical:** Only populated for family law cases. NULL for civil/criminal cases.

### Appeal Outcomes (`cases.appeal_outcome`, `issues_decisions.appeal_outcome`)

```
"reversed" | "affirmed" | "remanded" | "dismissed" | "partial" |
"split" | "remanded_partial" | "remanded_full" | "Unknown" | NULL
```

### Overall Case Outcomes (`cases.overall_case_outcome`)

```
"affirmed" | "reversed" | "remanded_full" | "remanded_partial" |
"dismissed" | "split" | "partial" | "other"
```

### Issue Categories (`issues_decisions.category`)

```
"Spousal Support / Maintenance" | "Child Support" |
"Parenting Plan / Custody / Visitation" | "Property Division / Debt Allocation" |
"Attorney Fees & Costs" | "Procedural & Evidentiary Issues" |
"Jurisdiction & Venue" | "Enforcement & Contempt Orders" |
"Modification Orders" | "Miscellaneous / Unclassified"
```

### Decision Stage (`issues_decisions.decision_stage`)

```
"trial" | "appeal" | "Trial" | "Appeal" | "Unknown" | NULL
```

### Judge Roles (`case_judges.role`)

```
"Author" | "Concurring" | "Dissenting" | "Panelist" | "Authored by" | "Joining"
```

### Attorney Types (`attorneys.attorney_type`)

```
"Attorney" | "Counsel" | "Public Defender" | "Unknown"
```

### Argument Sides (`arguments.side`)

```
"Appellant" | "Respondent" | "Court"
```

---

## Common Query Patterns

### 1. **Count Cases by Type and Year**

```sql
-- "How many divorce appeal cases were there in 2020?"
SELECT COUNT(*)
FROM cases c
JOIN case_types ct ON c.case_type_id = ct.case_type_id
WHERE ct.case_type = 'divorce'
  AND EXTRACT(YEAR FROM c.appeal_published_date) = 2020;
```

### 2. **Find Cases by Topic (Full-Text Search)**

```sql
-- "How many cases involve business valuation?"
SELECT DISTINCT c.case_id, c.title, c.docket_number
FROM cases c
JOIN case_sentences s ON c.case_id = s.case_id
WHERE s.tsv @@ to_tsquery('english', 'business & valuation');

-- OR using phrase table:
SELECT DISTINCT c.case_id, c.title
FROM cases c
JOIN case_phrases p ON c.case_id = p.case_id
WHERE p.phrase ILIKE '%business valuation%';
```

### 3. **Find Why Cases Were Reversed/Remanded**

```sql
-- "For business valuation cases that were remanded or reversed, why were they?"
SELECT
  c.title,
  c.docket_number,
  id.issue_summary,
  id.decision_summary,
  id.appeal_outcome
FROM cases c
JOIN issues_decisions id ON c.case_id = id.case_id
WHERE id.appeal_outcome IN ('reversed', 'remanded', 'remanded_partial', 'remanded_full')
  AND (
    id.issue_summary ILIKE '%business valuation%'
    OR id.decision_summary ILIKE '%business valuation%'
    OR id.subcategory ILIKE '%valuation%'
  );
```

### 4. **Find Cases Mentioning Specific Circumstances**

```sql
-- "Are there any cases where a person couldn't afford their spousal support?"
SELECT DISTINCT
  c.case_id,
  c.title,
  c.docket_number,
  s.text as relevant_sentence
FROM cases c
JOIN case_sentences s ON c.case_id = s.case_id
WHERE s.tsv @@ to_tsquery('english', '(afford | unable | cannot) & (spousal | maintenance)')
  AND (
    s.text ILIKE '%afford%'
    OR s.text ILIKE '%unable to pay%'
    OR s.text ILIKE '%cannot pay%'
  );
```

### 5. **Analyze Issue-Specific Reversal Reasons**

```sql
-- "What's the most common reason child support cases are reversed?"
SELECT
  id.subcategory,
  id.decision_summary,
  COUNT(*) as frequency
FROM issues_decisions id
WHERE id.category = 'Child Support'
  AND id.appeal_outcome IN ('reversed', 'remanded')
  AND id.decision_summary IS NOT NULL
GROUP BY id.subcategory, id.decision_summary
ORDER BY frequency DESC
LIMIT 10;
```

### 6. **Find Most Cited Cases for Specific Issues**

```sql
-- "What's the most commonly cited case in property distribution rulings?"
SELECT
  ce.target_case_citation,
  COUNT(*) as citation_count
FROM citation_edges ce
JOIN issues_decisions id ON ce.source_case_id = id.case_id
WHERE id.category = 'Property Division / Debt Allocation'
GROUP BY ce.target_case_citation
ORDER BY citation_count DESC
LIMIT 10;
```

### 7. **Compare District Reversal Rates**

```sql
-- "Is one district more likely to overturn a case than the others?"
SELECT
  c.district,
  COUNT(*) as total_cases,
  SUM(CASE WHEN c.appeal_outcome IN ('reversed', 'remanded', 'remanded_partial', 'remanded_full')
      THEN 1 ELSE 0 END) as overturned,
  ROUND(100.0 * SUM(CASE WHEN c.appeal_outcome IN ('reversed', 'remanded', 'remanded_partial', 'remanded_full')
      THEN 1 ELSE 0 END) / COUNT(*), 2) as overturn_percentage
FROM cases c
WHERE c.district IS NOT NULL AND c.appeal_outcome IS NOT NULL
GROUP BY c.district
ORDER BY overturn_percentage DESC;
```

### 8. **Find Most Successful Attorneys**

```sql
-- "What are the top 10 most successful lawyers on the appellant side?"
SELECT
  a.name as attorney_name,
  a.firm_name,
  COUNT(DISTINCT c.case_id) as total_cases,
  SUM(CASE WHEN c.winner_legal_role = 'Appellant' THEN 1 ELSE 0 END) as wins,
  ROUND(100.0 * SUM(CASE WHEN c.winner_legal_role = 'Appellant' THEN 1 ELSE 0 END) /
        COUNT(DISTINCT c.case_id), 2) as win_percentage
FROM attorneys a
JOIN cases c ON a.case_id = c.case_id
WHERE a.representing IN ('Appellant', 'appellant')
  AND c.winner_legal_role IS NOT NULL
  AND a.attorney_type IN ('Attorney', 'Counsel', 'Unknown')
GROUP BY a.name, a.firm_name
HAVING COUNT(DISTINCT c.case_id) >= 3  -- Minimum cases for statistical relevance
ORDER BY win_percentage DESC, total_cases DESC
LIMIT 10;
```

---

## AI Data Extraction Flow

### **1. PDF → Text Extraction**

- PDFs parsed using `pdf_parser.py`
- Text extracted and cleaned

### **2. AI Extraction (Ollama/OpenAI)**

- `app/services/ai_extractor.py` sends text to LLM
- `app/services/prompts.py` contains extraction prompts
- AI returns JSON matching Pydantic models

### **3. Pydantic Validation**

- `app/services/models.py` contains all Pydantic models
- Field validators normalize AI outputs:
  - Handle case variations ("appellant" → "Appellant")
  - Parse compound roles ("Appellant/Cross Respondent" → "Appellant")
  - Handle NULL values gracefully
  - Convert descriptive text to enums
- **Critical:** Validators prevent extraction failures by accepting variations

### **4. Database Insertion**

- `app/services/database_inserter.py` inserts validated data
- Handles FK relationships (parties, attorneys, issues, etc.)
- Creates word/phrase occurrences for full-text search
- Generates embeddings for semantic search

---

## Important Data Characteristics

### **NULL Handling**

- **Many fields can be NULL** - AI may not find certain information in PDFs
- Always use `IS NULL` or `IS NOT NULL` in WHERE clauses
- Use `COALESCE()` for default values

### **Case Sensitivity**

- CITEXT columns are case-insensitive
- Use `ILIKE` for case-insensitive pattern matching on TEXT columns
- Enum values are normalized by Pydantic validators

### **Multiple Records Per Case**

- Cases have multiple: parties, attorneys, issues, arguments, citations
- **Always use DISTINCT** when counting cases after joining to these tables
- Example: `SELECT COUNT(DISTINCT c.case_id) FROM cases c JOIN issues_decisions id ...`

### **Date Filtering**

- Use `EXTRACT(YEAR FROM date_field)` for year-based queries
- Many dates can be NULL if not found in documents
- Primary date fields: `appeal_published_date`, `appeal_end_date`

### **Full-Text Search**

- Use `@@` operator with `to_tsquery()` for PostgreSQL FTS
- Use `ILIKE '%pattern%'` for simple substring matching
- Use `tsv` columns (TSVECTOR) for indexed full-text search
- Phrase table is fastest for multi-word exact phrases

### **Array Fields**

- `keywords` in `issues_decisions` is CITEXT[]
- Use `ANY()` or array functions: `WHERE 'value' = ANY(keywords)`

---

## Key Relationships Summary

```
cases (1) ←→ (N) parties
cases (1) ←→ (N) attorneys
cases (1) ←→ (N) issues_decisions
cases (1) ←→ (N) citation_edges
cases (1) ←→ (N) statute_citations
cases (1) ←→ (N) case_judges
cases (1) ←→ (N) documents
cases (1) ←→ (N) case_chunks
cases (1) ←→ (N) case_sentences
cases (1) ←→ (N) word_occurrence
cases (1) ←→ (N) case_phrases
cases (1) ←→ (N) embeddings

issues_decisions (1) ←→ (N) arguments
issues_decisions (1) ←→ (N) issue_chunks (explainability anchors)

case_chunks (1) ←→ (N) case_sentences
case_chunks (1) ←→ (N) embeddings

cases (N) ←→ (1) courts_dim [court_id]
cases (N) ←→ (1) case_types [case_type_id]
cases (N) ←→ (1) stage_types [stage_type_id]

word_occurrence (N) ←→ (1) word_dictionary
statute_citations (N) ←→ (1) statutes_dim
case_judges (N) ←→ (1) judges
```

---

## Tips for AI SQL Query Generation

1. **Qualify all column names** with table aliases to avoid ambiguity
2. **Use DISTINCT when counting cases** after joining to multi-valued tables
3. **Check for NULL** - add `AND field IS NOT NULL` when filtering
4. **Use ILIKE** for case-insensitive text matching
5. **Date queries** - use `EXTRACT(YEAR FROM ...)` for year filtering
6. **Full-text search** - use `tsv @@ to_tsquery()` for indexed searches
7. **Enum matching** - use exact values from enum lists (case matters for non-CITEXT)
8. **Join carefully** - understand 1:N relationships to avoid duplicate counts
9. **Array fields** - use `ANY()` for array matching
10. **Performance** - add `case_id` filters early when using word/phrase tables
11. **Statistical queries** - use `HAVING` for post-aggregation filtering
12. **Issue-level queries** - join to `issues_decisions` for granular analysis

---

## Database Connection

**PostgreSQL Database:**

- Default DB: `cases_llama3.3`
- User: `legal_user`
- Password: `legal_pass`
- Port: 5433
- All tables in `public` schema

**Extensions:**

- `citext` - Case-insensitive text
- `vector` - pgvector for embeddings
- `pg_trgm` - Trigram matching for fuzzy search
- `unaccent` - Remove accents
- `pgcrypto` - UUID generation
