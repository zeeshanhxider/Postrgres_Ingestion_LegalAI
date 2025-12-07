# Database Column Population Architecture

## Overview

This document maps how each column in the `cases` table is populated, showing which extraction method (metadata, regex, or AI) is responsible for each field.

---

## 🚀 HYBRID EXTRACTION MODE (Recommended)

**NEW:** The system now supports a `hybrid` extraction mode that combines all three methods for comprehensive data population:

```python
# Usage in batch_processor.py
result = ingestor.ingest_pdf_case(
    pdf_content=pdf_content,
    metadata=metadata,
    source_file_info=source_file_info,
    extraction_mode='hybrid'  # Recommended: combines metadata + regex + AI
)
```

### How Hybrid Mode Works

1. **Phase 1 - Metadata**: Always runs first, extracts CSV-provided fields (guaranteed accuracy)
2. **Phase 2 - Regex**: Fast pattern matching for structural data (judges, citations, statutes, outcomes)
3. **Phase 3 - AI**: LLM extraction for complex understanding (summary, issues, arguments, attorneys)
4. **Phase 4 - Merge**: Combines results, preferring higher-quality sources and deduplicating

### Hybrid Mode Benefits

| Aspect                | Hybrid          | Regex-Only    | AI-Only         |
| --------------------- | --------------- | ------------- | --------------- |
| **Columns Populated** | ALL             | ~50%          | ~80%            |
| **Speed**             | Medium (60-90s) | Fast (20-30s) | Slow (60-120s)  |
| **Cost**              | $0.01-0.05/case | $0            | $0.01-0.05/case |
| **Attorneys**         | ✅              | ❌            | ✅              |
| **Issues/Decisions**  | ✅              | ❌            | ✅              |
| **Arguments**         | ✅              | ❌            | ✅              |
| **Citations**         | ✅ (regex)      | ✅            | ✅              |
| **Summary**           | ✅ (AI)         | ❌            | ✅              |

### Command Line Usage

```bash
# Use hybrid mode (recommended, now default)
python batch_processor.py csv metadata.csv --extraction-mode hybrid

# Use regex-only mode (fast, but incomplete)
python batch_processor.py csv metadata.csv --extraction-mode regex

# Use AI-only mode (legacy, slower)
python batch_processor.py csv metadata.csv --extraction-mode ai
```

---

## CASES Table Column Population

### 🔵 METADATA-ONLY Fields (From CSV)

These fields are **ALWAYS** populated from the CSV metadata file and are **NEVER** extracted:

| Column                  | Source       | Method                       | Notes                                               |
| ----------------------- | ------------ | ---------------------------- | --------------------------------------------------- |
| `case_file_id`          | metadata.csv | `case_number`                | Raw case number (e.g., "102,586-6")                 |
| `title`                 | metadata.csv | `case_title`                 | Case title/name                                     |
| `opinion_type`          | metadata.csv | `opinion_type`               | "Supreme Court", "Court of Appeals", etc.           |
| `publication_status`    | metadata.csv | `publication_status`         | "Published", "Published in Part", etc.              |
| `decision_year`         | metadata.csv | `year`                       | Integer year (2025, 2024, etc.)                     |
| `decision_month`        | metadata.csv | `month`                      | Month name ("January", "February", etc.)            |
| `case_info_url`         | metadata.csv | `case_info_url`              | URL to case info page                               |
| `source_url`            | metadata.csv | `pdf_url`                    | URL to PDF file                                     |
| `appeal_published_date` | metadata.csv | `file_date` (parsed)         | File date from CSV                                  |
| `published`             | metadata.csv | Derived from `file_contains` | Boolean: TRUE if "unpublished" NOT in file_contains |

**Populated by:** `database_inserter._insert_case_from_regex()` lines 540-669

---

### 🟢 REGEX-EXTRACTED Fields

These fields are extracted from PDF text using regex patterns:

| Column                 | Extraction Mode | Method               | Regex Pattern                                | Notes                 |
| ---------------------- | --------------- | -------------------- | -------------------------------------------- | --------------------- |
| `county`               | regex only      | `regex_extractor.py` | County name extraction                       | From document text    |
| `overall_case_outcome` | regex only      | `regex_extractor.py` | Outcome mapping (affirmed/reversed/remanded) | From case disposition |
| `appeal_outcome`       | regex only      | `regex_extractor.py` | Same as overall_case_outcome                 | Duplicate field       |

**Populated by:** `database_inserter._insert_case_from_regex()` lines 540-669

---

### 🟡 HYBRID Fields (Metadata Priority + Regex Fallback)

These fields use metadata first, falling back to regex if metadata is unavailable:

| Column          | Primary Source            | Fallback Source  | Logic                                                                                                               |
| --------------- | ------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------- |
| `court_level`   | metadata (`opinion_type`) | regex extraction | Maps "Supreme Court" → "supreme_court", "Court of Appeals" → "court_of_appeals"                                     |
| `district`      | metadata (`division`)     | regex extraction | Maps I/II/III → "Division I/II/III"                                                                                 |
| `docket_number` | **COMPOSITE**             | -                | Built as `{case_number}-{division_suffix}` (e.g., "37230-8-III") for Appeals; plain `case_number` for Supreme Court |

**Division Mapping Logic:**

```python
metadata_division = "I" / "II" / "III"  # From CSV
↓
division = "Division I" / "Division II" / "Division III"  # For district column
division_suffix = "I" / "II" / "III"  # For docket_number composite
```

**Populated by:** `database_inserter._insert_case_from_regex()` lines 540-669

---

### 🔴 AI-ONLY Fields (LLM Extraction)

These fields are **ONLY** populated when using AI extraction mode (`extraction_mode='ai'`):

| Column                 | Extraction Mode | Method                                               | AI Model Field              | Notes                            |
| ---------------------- | --------------- | ---------------------------------------------------- | --------------------------- | -------------------------------- |
| `court`                | AI only         | `ai_extractor.py` → `CaseModel.court`                | Full court name             | e.g., "Washington Supreme Court" |
| `source_docket_number` | AI only         | `ai_extractor.py` → `CaseModel.source_docket_number` | Trial court docket          |                                  |
| `trial_judge`          | AI only         | `ai_extractor.py` → `CaseModel.trial_judge`          | Trial judge name            |                                  |
| `trial_start_date`     | AI only         | `ai_extractor.py` → `CaseModel.trial_start_date`     | Trial start date            | Date parsing                     |
| `trial_end_date`       | AI only         | `ai_extractor.py` → `CaseModel.trial_end_date`       | Trial end date              | Date parsing                     |
| `trial_published_date` | AI only         | `ai_extractor.py` → `CaseModel.trial_published_date` | Trial published date        | Date parsing                     |
| `appeal_start_date`    | AI only         | `ai_extractor.py` → `CaseModel.appeal_start_date`    | Appeal filing date          | Date parsing                     |
| `appeal_end_date`      | AI only         | `ai_extractor.py` → `CaseModel.appeal_end_date`      | Appeal decision date        | Date parsing                     |
| `oral_argument_date`   | AI only         | `ai_extractor.py` → `CaseModel.oral_argument_date`   | Oral argument date          | Date parsing                     |
| `summary`              | AI only         | `ai_extractor.py` → `CaseModel.summary`              | 2-3 sentence summary        | LLM-generated                    |
| `case_type`            | AI only         | `ai_extractor.py` → `CaseModel.case_type`            | "divorce", "criminal", etc. | Classification                   |
| `winner_legal_role`    | AI only         | `ai_extractor.py` → `CaseModel.winner_legal_role`    | Appellant/Respondent/etc.   | Overall winner                   |
| `winner_personal_role` | AI only         | `ai_extractor.py` → `CaseModel.winner_personal_role` | Husband/Wife/etc.           | Personal role                    |

**Populated by:** `database_inserter._insert_case()` lines 110-194

---

### ⚙️ SYSTEM/INTERNAL Fields

These fields are managed by the system, not extracted:

| Column                 | Populated By                    | Value                              |
| ---------------------- | ------------------------------- | ---------------------------------- |
| `case_id`              | PostgreSQL                      | Auto-increment primary key         |
| `source_file`          | `source_file_info['filename']`  | PDF filename                       |
| `source_file_path`     | `source_file_info['file_path']` | Full file path                     |
| `extraction_timestamp` | System                          | `datetime.now()` at insertion time |
| `created_at`           | System                          | `datetime.now()` at insertion time |
| `updated_at`           | System                          | `datetime.now()` at insertion time |
| `processing_status`    | System                          | Default: 'pending'                 |
| `ingestion_batch_id`   | System                          | UUID for batch tracking            |
| `case_type_id`         | Dimension resolver              | FK to case_types table             |
| `stage_type_id`        | Dimension resolver              | FK to stage_types table            |
| `court_id`             | Dimension resolver              | FK to courts_dim table             |
| `parent_case_id`       | Not used                        | NULL (future feature)              |

---

### 📄 POST-PROCESSING Fields

These fields are populated **AFTER** initial case insertion:

| Column           | Populated By         | When                    | Method                                   |
| ---------------- | -------------------- | ----------------------- | ---------------------------------------- |
| `full_text`      | Text chunking        | During chunk processing | `case_ingestor._insert_chunks()`         |
| `full_embedding` | Embedding generation | After chunking complete | `case_ingestor._update_case_embedding()` |

**Populated by:** `case_ingestor.ingest_pdf_case()` lines 158-230

---

## Related Tables Population

### PARTIES Table

**Regex Mode:**

- Extracted via: `regex_extractor.extract_parties()`
- Inserted via: `database_inserter._insert_party_from_regex()`
- Fields: `name`, `legal_role` (appellant/respondent)

**AI Mode:**

- Extracted via: `ai_extractor.py` → `PartyModel`
- Inserted via: `database_inserter._insert_party()`
- Fields: `name`, `legal_role`, `personal_role`, `party_type`

### CASE_JUDGES Table

**Regex Mode:**

- Extracted via: `regex_extractor.extract_judges()`
- Inserted via: `database_inserter._insert_judge_from_regex()`
- Fields: `judge_name`, `role` (author/concurring/dissenting)

**AI Mode:**

- Extracted via: `ai_extractor.py` → `JudgeModel`
- Inserted via: `database_inserter._insert_judge()`
- Fields: `judge_name`, `role`

### ATTORNEYS Table

**AI Mode Only:**

- Extracted via: `ai_extractor.py` → `AttorneyModel`
- Inserted via: `database_inserter._insert_attorney()`
- Fields: `name`, `firm_name`, `firm_address`, `representing`, `attorney_type`

**Regex Mode:** Attorneys are **NOT** extracted in regex mode.

### CITATION_EDGES Table

**Regex Mode:**

- Extracted via: `regex_extractor.extract_citations()`
- Inserted via: `database_inserter._insert_case_citation()`
- Pattern: `\d+\s+Wash\.\s*(2d|App\.?)\s*\d+` and variants

**AI Mode:**

- Extracted via: `ai_extractor.py` → `PrecedentModel`
- Inserted via: `database_inserter._insert_citation()`

### STATUTE_CITATIONS Table

**Regex Mode:**

- Extracted via: `regex_extractor.extract_statutes()`
- Inserted via: `database_inserter._insert_statute_citation()`
- Pattern: `RCW \d+\.\d+\.\d+` and variants

**AI Mode:** Currently not extracted by AI extractor (would need to be added)

### ISSUES_DECISIONS Table

**AI Mode Only:**

- Extracted via: `ai_extractor.py` → `IssueDecisionModel`
- Inserted via: `database_inserter._insert_issue()`
- Fields: `category`, `subcategory`, `issue_summary`, `decision_summary`, `outcome`, `reasoning`

**Regex Mode:** Issues are **NOT** extracted in regex mode.

### ARGUMENTS Table

**AI Mode Only:**

- Extracted via: `ai_extractor.py` → `ArgumentModel`
- Inserted via: `database_inserter._insert_argument()`
- Fields: `side`, `claim`, `support`, `weakness`

**Regex Mode:** Arguments are **NOT** extracted in regex mode.

---

## Extraction Mode Comparison

### REGEX Mode (Fast, Free)

**What it extracts:**

- ✅ Case metadata (from CSV)
- ✅ Court level (with metadata fallback)
- ✅ Division (with metadata fallback)
- ✅ County
- ✅ Outcome (affirmed/reversed/remanded)
- ✅ Parties (names + appellant/respondent roles)
- ✅ Judges (names + author/concurring/dissenting)
- ✅ Case citations (case law references)
- ✅ Statute citations (RCW references)

**What it DOES NOT extract:**

- ❌ Court full name
- ❌ Trial court information (docket, judge, dates)
- ❌ Appeal timeline dates
- ❌ Case summary
- ❌ Case type classification
- ❌ Winner information
- ❌ Attorneys
- ❌ Issues/decisions
- ❌ Arguments

**Speed:** ~20-30 seconds per case
**Cost:** $0

### AI Mode (Slow, Expensive)

**What it extracts:**

- ✅ Everything from Regex mode
- ✅ Court full name
- ✅ Trial court information (docket, judge, dates)
- ✅ Appeal timeline dates
- ✅ Case summary (LLM-generated)
- ✅ Case type classification
- ✅ Winner information (legal + personal roles)
- ✅ Attorneys (with firm info)
- ✅ Issues/decisions (detailed)
- ✅ Arguments (claim/support/weakness)
- ✅ Party personal roles (husband/wife/etc.)

**Speed:** ~60-120 seconds per case
**Cost:** ~$0.01-0.05 per case (depending on model)

---

## Current Processing Flow

### Regex Extraction Flow

```
1. batch_processor.py reads metadata.csv
2. For each row:
   a. Load metadata from CSV row
   b. Read PDF file
   c. Extract text from PDF
   d. Run regex_extractor.extract_case_data_regex(full_text, metadata)
   e. database_inserter.insert_regex_extraction(regex_result, metadata, source_file_info)
      - _insert_case_from_regex() → creates case record
      - _insert_party_from_regex() → creates party records
      - _insert_judge_from_regex() → creates judge records
      - _insert_statute_citation() → creates statute records
      - _insert_case_citation() → creates citation records
   f. case_ingestor.ingest_pdf_case() → chunking, embeddings, RAG features
      - Create chunks
      - Create sentences
      - Create word occurrences
      - Create phrases
      - Generate embeddings
```

### AI Extraction Flow

```
1. batch_processor.py reads metadata.csv
2. For each row:
   a. Load metadata from CSV row
   b. Read PDF file
   c. Extract text from PDF
   d. Run ai_extractor.extract_case_data(full_text, case_info)
   e. database_inserter.insert_complete_case(extracted_data, metadata, source_file_info)
      - _insert_case() → creates case record (full AI fields)
      - _insert_party() → creates party records (with personal roles)
      - _insert_attorney() → creates attorney records
      - _insert_judge() → creates judge records
      - _insert_issue() → creates issue records
      - _insert_argument() → creates argument records
      - _insert_citation() → creates citation records
   f. case_ingestor.ingest_pdf_case() → chunking, embeddings, RAG features
      - Same RAG processing as regex mode
```

---

## Hybrid Strategy Recommendation

For optimal cost/accuracy balance, consider:

### Tier 1: All Cases - Regex Extraction

- Fast, free baseline extraction
- Populates: parties, judges, citations, statutes, outcomes
- ~30 seconds per case, $0 cost

### Tier 2: Priority Cases - AI Enhancement

Run AI extraction on cases that meet criteria like:

- Published opinions (higher quality, more important)
- Supreme Court cases (precedential value)
- Cases with specific issues (divorce, custody, support)
- Recent cases (last 5 years)

AI enhancement adds:

- Detailed case summary
- Issue/decision analysis
- Attorney information
- Complete timeline
- Winner analysis

### Implementation:

```python
# In batch_processor.py
extraction_mode = 'regex'  # Default for all

# Upgrade to AI for priority cases
if (metadata['publication_status'] == 'Published' and
    metadata['opinion_type'] == 'Supreme Court'):
    extraction_mode = 'ai'
```

This gives you:

- 100% coverage with fast, free regex extraction
- Rich AI data on ~10-20% of cases (the most important ones)
- Estimated cost: $50-200 for 4,342 cases vs $200-1,000 for all AI

---

## Code References

### Key Files:

- **database_inserter.py** - All INSERT logic (lines 110-700)
- **regex_extractor.py** - Regex extraction patterns
- **ai_extractor.py** - LLM extraction (lines 1-138)
- **models.py** - Pydantic models for AI extraction (lines 1-629)
- **case_ingestor.py** - Main ingestion orchestration (lines 1-577)
- **batch_processor.py** - Batch processing logic (lines 1-469)

### Key Methods:

- `database_inserter._insert_case_from_regex()` - Regex case insertion (lines 519-679)
- `database_inserter._insert_case()` - AI case insertion (lines 110-194)
- `regex_extractor.extract_case_data_regex()` - Regex extraction
- `ai_extractor.extract_case_data()` - AI extraction (lines 115-138)
- `case_ingestor.ingest_pdf_case()` - Main ingestion (lines 52-250)
