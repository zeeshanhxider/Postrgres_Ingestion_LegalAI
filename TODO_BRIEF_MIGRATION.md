# Brief Migration & Ingestion - TODO Checklist

Quick checklist for migrating briefs schema and ingesting briefs.

---

## Pre-Flight Checks

### Database

- [ ] PostgreSQL 16+ is running
- [ ] pgvector extension is installed
- [ ] cases_llama3.3 database exists
- [ ] Cases table has data (check: `SELECT COUNT(*) FROM cases;`)
- [ ] word_dictionary table exists

### Environment

- [ ] Python 3.11+ installed
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Environment variables set:
  ```bash
  export DATABASE_URL=postgresql://postgres:password@localhost:5432/cases_llama3.3
  export USE_OLLAMA=true
  ```

### Briefs Data

- [ ] `downloaded-briefs/` folder exists
- [ ] Contains year folders (e.g., `2024-briefs/`)
- [ ] Contains case folders (e.g., `83895-4/`)
- [ ] Contains PDF files

---

## Step 1: Run Migration

### Option A: Use Script (Recommended)

**Windows:**

```powershell
cd d:\freelance\Dobbs_Data\Postgres_Ingestion_LegalAI
.\scripts\run_brief_migration.ps1
```

**Linux/Mac:**

```bash
cd /path/to/Postgres_Ingestion_LegalAI
bash scripts/run_brief_migration.sh
```

### Option B: Manual

```bash
psql -h localhost -U postgres -d cases_llama3.3 -f scripts/migrate_briefs_schema.sql
```

### Validation

- [ ] 7 tables created (briefs, brief_chunks, brief_arguments, brief_citations, brief_word_occurrence, brief_phrases, brief_sentences)
- [ ] Normalization function works: `SELECT normalize_case_file_id('69423-5');` returns `694235`
- [ ] Indexes created (check: `\di brief*`)
- [ ] No errors in migration output

---

## Step 2: Test with Single Brief

### Run Test

```bash
python batch_process_briefs.py --case-folder 83895-4
```

### Validation

- [ ] Brief inserted (check: `SELECT COUNT(*) FROM briefs;`)
- [ ] Case linked (check: `SELECT case_id FROM briefs WHERE case_id IS NOT NULL LIMIT 1;`)
- [ ] Chunks created (check: `SELECT COUNT(*) FROM brief_chunks;`)
- [ ] Embeddings generated (check: `SELECT COUNT(*) FROM brief_chunks WHERE embedding IS NOT NULL;`)
- [ ] Words indexed (check: `SELECT COUNT(*) FROM brief_word_occurrence;`)
- [ ] Phrases extracted (check: `SELECT COUNT(*) FROM brief_phrases;`)
- [ ] TOA extracted (check: `SELECT COUNT(*) FROM brief_citations WHERE from_toa = TRUE;`)

---

## Step 3: Batch Process All Briefs

### Option A: Process All Years

```bash
python batch_process_briefs.py --briefs-dir downloaded-briefs
```

### Option B: Process Single Year

```bash
python batch_process_briefs.py --briefs-dir downloaded-briefs --year 2024
```

### Monitor Progress

- [ ] Watch console output for errors
- [ ] Check processed count increments
- [ ] Monitor database size (`SELECT pg_size_pretty(pg_database_size('cases_llama3.3'));`)
- [ ] Check Ollama/OpenAI service is responding

---

## Step 4: Validate Results

### Check Totals

```sql
-- Total briefs
SELECT COUNT(*) as total_briefs FROM briefs;

-- Linked briefs
SELECT
    COUNT(*) as total,
    COUNT(case_id) as linked,
    ROUND(100.0 * COUNT(case_id) / COUNT(*), 2) as link_rate
FROM briefs;

-- Chained briefs
SELECT
    COUNT(*) as total,
    COUNT(responds_to_brief_id) as chained,
    ROUND(100.0 * COUNT(responds_to_brief_id) / COUNT(*), 2) as chain_rate
FROM briefs;

-- TOA citations
SELECT
    COUNT(*) as total_citations,
    COUNT(*) FILTER (WHERE from_toa = TRUE) as toa_citations,
    ROUND(100.0 * COUNT(*) FILTER (WHERE from_toa = TRUE) / COUNT(*), 2) as toa_rate
FROM brief_citations;
```

### Check Components

```sql
-- Chunks
SELECT COUNT(*) as chunks FROM brief_chunks;

-- Words
SELECT COUNT(*) as words FROM brief_word_occurrence;

-- Phrases
SELECT COUNT(*) as phrases FROM brief_phrases;

-- Sentences
SELECT COUNT(*) as sentences FROM brief_sentences;
```

### Targets

- [ ] Linking rate > 80%
- [ ] Chaining rate > 60%
- [ ] TOA rate > 50%
- [ ] All embeddings generated (check: `SELECT COUNT(*) FROM briefs WHERE full_embedding IS NOT NULL;`)

---

## Step 5: Troubleshooting (If Needed)

### Low Linking Rate (<80%)

Check orphaned briefs:

```sql
SELECT case_file_id, filename_case_id, source_file
FROM briefs
WHERE case_id IS NULL
LIMIT 10;
```

**Actions:**

- [ ] Verify cases exist in `cases` table
- [ ] Check normalization matches
- [ ] Review filename patterns

### Low Chaining Rate (<60%)

Check unchained briefs:

```sql
SELECT brief_type, COUNT(*)
FROM briefs
WHERE brief_type IN ('Response', 'Reply')
AND responds_to_brief_id IS NULL
GROUP BY brief_type;
```

**Actions:**

- [ ] Check if Opening briefs exist for Responses
- [ ] Check if Response briefs exist for Replies
- [ ] Verify case_file_id matching

### Low TOA Rate (<50%)

Check briefs without TOA:

```sql
SELECT b.brief_id, b.source_file
FROM briefs b
LEFT JOIN brief_citations bc ON b.brief_id = bc.brief_id AND bc.from_toa = TRUE
WHERE bc.brief_citation_id IS NULL
LIMIT 10;
```

**Actions:**

- [ ] Check brief text for TOA section
- [ ] Review TOA extraction regex pattern
- [ ] Manual inspection of sample briefs

### Performance Issues

**Slow embeddings:**

- [ ] Verify Ollama is running: `curl http://localhost:11434/api/tags`
- [ ] Check OpenAI API key if using OpenAI
- [ ] Monitor network latency

**Database slow:**

- [ ] Check disk space
- [ ] Monitor CPU/memory
- [ ] Check connection pool size

---

## Step 6: Next Development

### API Endpoints

- [ ] Create `app/api/v1/endpoints/briefs.py`
- [ ] Implement GET `/api/v1/briefs/{brief_id}`
- [ ] Implement GET `/api/v1/briefs/case/{case_id}`
- [ ] Implement POST `/api/v1/briefs/search`
- [ ] Implement GET `/api/v1/briefs/{brief_id}/conversation`

### Testing

- [ ] Write unit tests for `brief_ingestor.py`
- [ ] Write integration tests for batch processor
- [ ] Test edge cases (orphaned briefs, missing TOA, etc.)

### Documentation

- [ ] Update API documentation
- [ ] Create Postman collection
- [ ] Add example queries to documentation

---

## Success Criteria

### Phase 1: Migration ✅

- [x] All tables created
- [x] All indexes created
- [x] Normalization function working
- [x] No migration errors

### Phase 2: Test Ingestion

- [ ] Single brief ingested successfully
- [ ] Case linking works
- [ ] All RAG components created
- [ ] No processing errors

### Phase 3: Batch Ingestion

- [ ] All briefs processed
- [ ] <5% failure rate
- [ ] Linking rate >80%
- [ ] Chaining rate >60%
- [ ] TOA rate >50%

### Phase 4: Validation

- [ ] All validation queries pass
- [ ] Database size as expected (~2-5GB for 1,000 briefs)
- [ ] Query performance acceptable (<500ms for simple queries)
- [ ] No duplicate briefs

---

## Rollback Plan (If Needed)

### Drop All Brief Tables

```sql
DROP TABLE IF EXISTS brief_sentences CASCADE;
DROP TABLE IF EXISTS brief_phrases CASCADE;
DROP TABLE IF EXISTS brief_word_occurrence CASCADE;
DROP TABLE IF EXISTS brief_citations CASCADE;
DROP TABLE IF EXISTS brief_arguments CASCADE;
DROP TABLE IF EXISTS brief_chunks CASCADE;
DROP TABLE IF EXISTS briefs CASCADE;
DROP FUNCTION IF EXISTS normalize_case_file_id(TEXT);
```

### Re-run Migration

```bash
psql -d cases_llama3.3 -f scripts/migrate_briefs_schema.sql
```

---

## Timeline Estimates

| Phase                                | Time Estimate |
| ------------------------------------ | ------------- |
| Pre-flight checks                    | 15 minutes    |
| Migration                            | 5 minutes     |
| Test single brief                    | 10 minutes    |
| Batch process (1,000 briefs, Ollama) | 2-3 hours     |
| Validation                           | 15 minutes    |
| Troubleshooting (if needed)          | 30-60 minutes |
| **Total**                            | **3-4 hours** |

---

## Notes

- **Backup First:** Always backup database before migration

  ```bash
  pg_dump cases_llama3.3 > cases_llama3.3_backup.sql
  ```

- **Monitor Resources:** Watch CPU, memory, disk during ingestion

  ```bash
  top -p $(pgrep postgres)
  ```

- **Check Logs:** Review logs for errors

  ```bash
  tail -f /var/log/postgresql/postgresql-16-main.log
  ```

- **Parallel Processing:** Can process multiple years in parallel if needed
  ```bash
  python batch_process_briefs.py --year 2024 &
  python batch_process_briefs.py --year 2023 &
  wait
  ```

---

## Contact

For questions, see:

- `docs/BRIEF_INGESTION_GUIDE.md` - Complete guide
- `scripts/README_BRIEF_MIGRATION.md` - Quick reference
- `docs/BRIEF_IMPLEMENTATION_SUMMARY.md` - Technical details
