# Brief Ingestion Guide

Complete guide for migrating briefs schema and ingesting brief PDFs into the database.

## Overview

This guide covers:

1. Running the migration to add briefs schema
2. Understanding the brief ingestion architecture
3. Batch processing briefs
4. Validating ingestion results
5. Troubleshooting common issues

---

## 1. Migration: Add Briefs Schema

### Step 1: Verify Database Connection

```bash
# Test connection to cases_llama3.3 database
psql -h localhost -U postgres -d cases_llama3.3 -c "\dt"
```

### Step 2: Run Migration Script

```bash
# From project root
psql -h localhost -U postgres -d cases_llama3.3 -f scripts/migrate_briefs_schema.sql
```

### Step 3: Verify Migration Success

```sql
-- Connect to database
psql -h localhost -U postgres -d cases_llama3.3

-- Check tables created
SELECT table_name
FROM information_schema.tables
WHERE table_name LIKE 'brief%';

-- Expected output:
-- briefs
-- brief_chunks
-- brief_arguments
-- brief_citations
-- brief_word_occurrence
-- brief_phrases
-- brief_sentences
```

### Step 4: Test Normalization Function

```sql
-- Test case_file_id normalization
SELECT normalize_case_file_id('69423-5');  -- Should return: 694235
SELECT normalize_case_file_id('83895-4-I');  -- Should return: 838954
```

---

## 2. Brief Ingestion Architecture

### Core Components

```
batch_process_briefs.py
    ↓
BriefBatchProcessor
    ↓
BriefIngestor
    ├── _parse_brief_filename()     # Extract metadata from filename
    ├── _insert_brief()             # Create brief record
    ├── _link_to_case()             # Multi-strategy case linking
    ├── _detect_brief_chaining()    # Find responds_to relationships
    ├── _insert_chunks()            # Create RAG chunks
    ├── _process_sentences()        # Sentence-level indexing
    ├── _process_words()            # Word-level indexing
    ├── _extract_phrases()          # N-gram phrases
    └── _extract_toa()              # Table of Authorities
```

### Multi-Strategy Case Linking

The ingestion process uses **two strategies** to link briefs to cases:

1. **Strategy 1: Folder case_file_id**
   - Extracts case_file_id from folder name (e.g., `83895-4`)
   - Normalizes and matches against `cases.case_file_id`
2. **Strategy 2: Filename case_id**
   - Extracts suffix from filename (e.g., `934` from `762508_appellants_reply_brief_934.pdf`)
   - Normalizes and matches against `cases.case_file_id`

If both strategies fail, the brief is still inserted but `case_id` is `NULL` (orphaned).

### Brief Chaining Logic

Briefs are automatically chained to reconstruct the "conversation of law":

- **Opening Brief** → `brief_sequence = 1`, `responds_to_brief_id = NULL`
- **Response Brief** → `brief_sequence = 2`, `responds_to_brief_id = <opening_brief_id>`
- **Reply Brief** → `brief_sequence = 3`, `responds_to_brief_id = <response_brief_id>`

---

## 3. Batch Processing Briefs

### Folder Structure Expected

```
downloaded-briefs/
    2024-briefs/
        83895-4/
            762508_appellants_reply_brief_934.pdf
            845012_respondents_brief.pdf
        69423-5/
            ...
    2023-briefs/
        ...
```

### Command Options

```bash
# Process all briefs (all years)
python batch_process_briefs.py --briefs-dir downloaded-briefs

# Process only 2024 briefs
python batch_process_briefs.py --briefs-dir downloaded-briefs --year 2024

# Process single case folder
python batch_process_briefs.py --briefs-dir downloaded-briefs --case-folder 83895-4

# Custom database URL
python batch_process_briefs.py \
    --briefs-dir downloaded-briefs \
    --db-url postgresql://postgres:password@localhost:5432/cases_llama3.3
```

### Example Output

```
🚀 Starting batch brief processing from: downloaded-briefs
Year filter: 2024

================================================================================
📅 Processing year: 2024
================================================================================

📂 Found 150 case folders in 2024-briefs

[1/150] Processing case folder: 83895-4
📄 Found 3 PDF files

────────────────────────────────────────────────────────────
📝 Processing: 762508_appellants_reply_brief_934.pdf
────────────────────────────────────────────────────────────
🚀 Starting brief ingestion for: downloaded-briefs/2024-briefs/83895-4/762508_appellants_reply_brief_934.pdf
📝 Parsing filename metadata...
✅ Extracted metadata: {'case_file_id': '83895-4', 'filename_case_id': '934', ...}
📄 Parsing PDF content...
✅ Parsed 25 pages, 45823 characters
💾 Creating brief record with case linking...
✅ Linked to case_id: 12345
🔗 Detecting brief chaining...
✅ Brief chain detected: brief 789 responds to brief 788
📄 Creating text chunks...
✅ Created 18 text chunks
📦 Inserting chunks with embeddings...
✅ Inserted 18 chunks
✂️ Processing sentences...
✅ Processed 342 sentences
📝 Processing words...
✅ Processed 8945 words
🔤 Extracting legal phrases...
✅ Extracted 234 phrases
🌟 Generating brief embedding...
✅ Generated brief embedding
📚 Extracting Table of Authorities...
✅ Extracted 15 citations from TOA

✅ Brief processed successfully!
   Brief ID: 789
   Case linked: True (case_id: 12345)
   Chunks created: 18
   Sentences: 342
   Words indexed: 8945
   Phrases: 234
   TOA citations: 15
```

### Summary Statistics

```
================================================================================
📊 BATCH PROCESSING SUMMARY
================================================================================
✅ Successfully processed: 450 briefs
❌ Failed: 5 briefs
⏭️ Skipped: 12 briefs
⏱️ Total duration: 3847.23 seconds
⏱️ Average time per brief: 8.55 seconds
================================================================================
```

---

## 4. Validating Ingestion Results

### Check Total Briefs Ingested

```sql
SELECT COUNT(*) as total_briefs FROM briefs;
```

### Check Case Linking Success Rate

```sql
SELECT
    COUNT(*) as total_briefs,
    COUNT(case_id) as linked_briefs,
    COUNT(*) - COUNT(case_id) as orphaned_briefs,
    ROUND(100.0 * COUNT(case_id) / COUNT(*), 2) as link_rate
FROM briefs;
```

### Check Brief Types Distribution

```sql
SELECT
    brief_type,
    COUNT(*) as count
FROM briefs
GROUP BY brief_type
ORDER BY count DESC;
```

### Check Brief Chaining Success

```sql
SELECT
    COUNT(*) as total_briefs,
    COUNT(responds_to_brief_id) as chained_briefs,
    ROUND(100.0 * COUNT(responds_to_brief_id) / COUNT(*), 2) as chain_rate
FROM briefs;
```

### Check Processing Status

```sql
SELECT
    processing_status,
    COUNT(*) as count
FROM briefs
GROUP BY processing_status;
```

### View Sample Brief Chain

```sql
-- View a complete brief conversation
WITH RECURSIVE brief_chain AS (
    -- Start with Opening brief
    SELECT
        brief_id,
        case_file_id,
        brief_type,
        filing_party,
        brief_sequence,
        responds_to_brief_id,
        0 as depth
    FROM briefs
    WHERE brief_type = 'Opening' AND case_file_id = '83895-4'

    UNION ALL

    -- Recursively find Response and Reply
    SELECT
        b.brief_id,
        b.case_file_id,
        b.brief_type,
        b.filing_party,
        b.brief_sequence,
        b.responds_to_brief_id,
        bc.depth + 1
    FROM briefs b
    INNER JOIN brief_chain bc ON b.responds_to_brief_id = bc.brief_id
)
SELECT * FROM brief_chain ORDER BY depth;
```

### Check RAG Components

```sql
-- Check chunks
SELECT
    COUNT(*) as total_chunks,
    AVG(word_count) as avg_words_per_chunk,
    COUNT(embedding) as chunks_with_embeddings
FROM brief_chunks;

-- Check word indexing
SELECT COUNT(*) as total_word_occurrences FROM brief_word_occurrence;

-- Check phrases
SELECT COUNT(*) as total_phrases FROM brief_phrases;

-- Check sentences
SELECT COUNT(*) as total_sentences FROM brief_sentences;
```

### Check Table of Authorities Extraction

```sql
SELECT
    COUNT(*) as total_citations,
    COUNT(*) FILTER (WHERE from_toa = TRUE) as toa_citations,
    ROUND(100.0 * COUNT(*) FILTER (WHERE from_toa = TRUE) / COUNT(*), 2) as toa_rate
FROM brief_citations;
```

---

## 5. Troubleshooting

### Issue: Migration Fails with "briefs table already exists"

**Solution:** The migration has already been run. To verify:

```sql
SELECT table_name FROM information_schema.tables WHERE table_name = 'briefs';
```

To re-run migration (CAUTION: deletes all brief data):

```sql
DROP TABLE IF EXISTS brief_sentences CASCADE;
DROP TABLE IF EXISTS brief_phrases CASCADE;
DROP TABLE IF EXISTS brief_word_occurrence CASCADE;
DROP TABLE IF EXISTS brief_citations CASCADE;
DROP TABLE IF EXISTS brief_arguments CASCADE;
DROP TABLE IF EXISTS brief_chunks CASCADE;
DROP TABLE IF EXISTS briefs CASCADE;
```

### Issue: Low Case Linking Rate (<80%)

**Diagnosis:**

```sql
-- Check orphaned briefs
SELECT
    case_file_id,
    filename_case_id,
    source_file
FROM briefs
WHERE case_id IS NULL
LIMIT 10;
```

**Common Causes:**

1. Case doesn't exist in `cases` table
2. Case has different formatting (e.g., missing hyphens)
3. Filename case_id doesn't match any case

**Solution:**

- Verify cases exist: `SELECT case_file_id FROM cases WHERE case_file_id LIKE '%83895%';`
- Check normalization: `SELECT normalize_case_file_id('83895-4');`

### Issue: Brief Chaining Not Working

**Diagnosis:**

```sql
-- Check briefs without chaining
SELECT
    brief_id,
    case_file_id,
    brief_type,
    responds_to_brief_id,
    brief_sequence
FROM briefs
WHERE brief_type IN ('Response', 'Reply')
AND responds_to_brief_id IS NULL;
```

**Common Causes:**

1. Opening brief doesn't exist for Response
2. Response brief doesn't exist for Reply
3. Case_file_id mismatch between briefs

### Issue: TOA Extraction Finding Few Citations

**Diagnosis:**

```sql
-- Check briefs with TOA citations
SELECT
    b.brief_id,
    b.source_file,
    COUNT(bc.brief_citation_id) as toa_citations
FROM briefs b
LEFT JOIN brief_citations bc ON b.brief_id = bc.brief_id AND bc.from_toa = TRUE
GROUP BY b.brief_id, b.source_file
HAVING COUNT(bc.brief_citation_id) = 0
LIMIT 10;
```

**Common Causes:**

1. Brief doesn't have a Table of Authorities section
2. TOA has non-standard formatting
3. Pattern matching failed

**Solution:** Check brief text manually:

```sql
SELECT substring(full_text, 1, 2000) FROM briefs WHERE brief_id = 789;
```

### Issue: Slow Processing (<1 brief per 5 seconds)

**Diagnosis:**

- Check embedding service (Ollama or OpenAI)
- Check database connection latency
- Check vector index creation

**Solutions:**

- Use Ollama for faster embeddings: `export USE_OLLAMA=true`
- Increase batch size for embeddings
- Disable vector index during bulk insert, recreate after

---

## 6. Advanced Queries

### Find All Briefs for a Case

```sql
SELECT
    brief_id,
    brief_type,
    filing_party,
    brief_sequence,
    page_count,
    filing_date
FROM briefs
WHERE case_id = 12345
ORDER BY brief_sequence;
```

### Search Briefs by Semantic Similarity

```sql
-- Find briefs similar to a query
WITH query_embedding AS (
    SELECT full_embedding
    FROM briefs
    WHERE brief_id = 789
)
SELECT
    b.brief_id,
    b.case_file_id,
    b.brief_type,
    b.filing_party,
    1 - (b.full_embedding <=> qe.full_embedding) as similarity
FROM briefs b, query_embedding qe
WHERE b.brief_id != 789
ORDER BY similarity DESC
LIMIT 10;
```

### Find Citations Used in Multiple Briefs

```sql
SELECT
    citation_text,
    COUNT(DISTINCT brief_id) as brief_count,
    COUNT(*) as total_occurrences
FROM brief_citations
GROUP BY citation_text
HAVING COUNT(DISTINCT brief_id) > 1
ORDER BY brief_count DESC
LIMIT 20;
```

### Reconstruct Brief Conversation

```sql
-- View Opening → Response → Reply for a case
SELECT
    b1.brief_id as opening_id,
    b1.filing_party as opening_party,
    b2.brief_id as response_id,
    b2.filing_party as response_party,
    b3.brief_id as reply_id,
    b3.filing_party as reply_party
FROM briefs b1
LEFT JOIN briefs b2 ON b2.responds_to_brief_id = b1.brief_id
LEFT JOIN briefs b3 ON b3.responds_to_brief_id = b2.brief_id
WHERE b1.brief_type = 'Opening'
AND b1.case_file_id = '83895-4';
```

---

## 7. Next Steps

After successful ingestion:

1. **Validate Data Quality**

   - Check linking rates (target: >80%)
   - Check chaining rates (target: >60%)
   - Check TOA extraction (target: >50% of briefs have TOA)

2. **Build API Endpoints**

   - GET `/api/v1/briefs/{brief_id}`
   - GET `/api/v1/briefs/case/{case_id}`
   - POST `/api/v1/briefs/search` (semantic search)
   - GET `/api/v1/briefs/{brief_id}/conversation` (brief chain)

3. **Add AI Extraction** (Optional)

   - Extract hierarchical arguments (ARGUMENT sections)
   - Extract issue statements
   - Extract relief requested

4. **Performance Optimization**
   - Create materialized views for common queries
   - Optimize vector indexes
   - Implement caching layer

---

## Contact

For issues or questions, refer to:

- `BRIEFS_SCHEMA_EXTENSION.md` - Complete schema documentation
- `BRIEFS_CRITICAL_IMPROVEMENTS.md` - Quick reference for all fixes
- `MULTI_STRATEGY_LINKING.md` - Detailed linking logic
