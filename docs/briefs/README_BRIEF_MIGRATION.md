# Brief Migration & Ingestion Scripts

Quick reference guide for migrating briefs schema and ingesting brief PDFs.

## Quick Start

### 1. Run Migration (Add Briefs Tables)

**Windows (PowerShell):**

```powershell
cd d:\freelance\Dobbs_Data\Postgres_Ingestion_LegalAI
.\scripts\run_brief_migration.ps1
```

**Linux/Mac:**

```bash
cd /path/to/Postgres_Ingestion_LegalAI
bash scripts/run_brief_migration.sh
```

**Manual (if scripts fail):**

```bash
psql -h localhost -U postgres -d cases_llama3.3 -f scripts/migrate_briefs_schema.sql
```

### 2. Ingest Briefs

**Process all briefs:**

```bash
python batch_process_briefs.py --briefs-dir downloaded-briefs
```

**Process only 2024:**

```bash
python batch_process_briefs.py --briefs-dir downloaded-briefs --year 2024
```

**Process single case:**

```bash
python batch_process_briefs.py --case-folder 83895-4
```

---

## Files in This Directory

### Migration Scripts

| File                        | Purpose                                              | Usage                             |
| --------------------------- | ---------------------------------------------------- | --------------------------------- |
| `migrate_briefs_schema.sql` | SQL migration script that creates all 7 brief tables | Run via psql or migration scripts |
| `run_brief_migration.sh`    | Bash script for Linux/Mac                            | `bash run_brief_migration.sh`     |
| `run_brief_migration.ps1`   | PowerShell script for Windows                        | `.\run_brief_migration.ps1`       |

### Legacy Scripts (Cases)

| File                   | Purpose                         |
| ---------------------- | ------------------------------- |
| `init-postgres.sh`     | Initialize PostgreSQL for cases |
| `reset_database.py`    | Reset cases database            |
| `reset_database.sh`    | Reset database (bash)           |
| `startup.sh`           | Docker startup script           |
| `verify_database.py`   | Verify database structure       |
| `docker-entrypoint.sh` | Docker entrypoint               |

---

## Migration Details

### What Gets Created

The migration creates **7 new tables**:

1. **`briefs`** - Main brief metadata with multi-strategy case linking
2. **`brief_chunks`** - Text chunks with embeddings for RAG
3. **`brief_arguments`** - Hierarchical argument structure (I -> A -> 1)
4. **`brief_citations`** - Citations with TOA priority flagging
5. **`brief_word_occurrence`** - Word-level indexing (reuses `word_dictionary`)
6. **`brief_phrases`** - N-gram phrases for terminology search
7. **`brief_sentences`** - Sentence-level indexing with embeddings

### Key Features Added

✅ **Multi-Strategy Case Linking**

- Strategy 1: Match folder `case_file_id` (e.g., "83895-4")
- Strategy 2: Match filename `case_id` (e.g., "934")
- Both use normalization function for fuzzy matching

✅ **Brief Chaining**

- Opening → Response → Reply conversation tracking
- `responds_to_brief_id` links briefs together
- `brief_sequence` (1, 2, 3) tracks conversation order

✅ **Argument Hierarchy**

- Nested structure (parent_argument_id)
- Hierarchy path (e.g., "III.A.1")
- Hierarchy level (1, 2, 3)

✅ **Table of Authorities Priority**

- `from_toa` flag for high-confidence citations
- `toa_page_refs` array for page numbers
- Extracted separately from in-text citations

✅ **Normalization Function**

- `normalize_case_file_id()` removes non-digits
- "69423-5" → "694235"
- "83895-4-I" → "838954"

---

## Configuration

### Environment Variables

Set these before running migration scripts:

```bash
# Database connection
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=cases_llama3.3
export DB_USER=postgres
export DB_PASSWORD=your_password

# For batch processing
export DATABASE_URL=postgresql://postgres:password@localhost:5432/cases_llama3.3
export USE_OLLAMA=true  # Use Ollama for embeddings (faster)
```

### Database Requirements

- PostgreSQL 16+ with pgvector extension
- Existing `cases` table with data
- `word_dictionary` table for word indexing
- At least 10GB free space for embeddings

---

## Validation Queries

After migration, run these to validate:

### 1. Check Tables Created

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_name LIKE 'brief%'
ORDER BY table_name;
```

Expected: 7 tables

### 2. Check Normalization Function

```sql
SELECT
    normalize_case_file_id('69423-5') as test1,
    normalize_case_file_id('83895-4-I') as test2;
```

Expected: `694235`, `838954`

### 3. Check Indexes

```sql
SELECT indexname
FROM pg_indexes
WHERE tablename LIKE 'brief%'
ORDER BY tablename, indexname;
```

Expected: ~30+ indexes across all tables

### 4. Check Foreign Keys

```sql
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
AND tc.table_name LIKE 'brief%';
```

---

## Troubleshooting

### Migration Already Run

**Error:** `briefs table already exists`

**Solution:**

```sql
-- Check if tables exist
\dt brief*

-- To drop and re-run (⚠️ DELETES ALL BRIEF DATA):
DROP TABLE IF EXISTS brief_sentences CASCADE;
DROP TABLE IF EXISTS brief_phrases CASCADE;
DROP TABLE IF EXISTS brief_word_occurrence CASCADE;
DROP TABLE IF EXISTS brief_citations CASCADE;
DROP TABLE IF EXISTS brief_arguments CASCADE;
DROP TABLE IF EXISTS brief_chunks CASCADE;
DROP TABLE IF EXISTS briefs CASCADE;
```

### Connection Refused

**Error:** `could not connect to server`

**Solutions:**

1. Check PostgreSQL is running: `systemctl status postgresql` (Linux) or `Get-Service postgresql*` (Windows)
2. Check port: `netstat -an | grep 5432`
3. Check `pg_hba.conf` for authentication settings
4. Verify `DATABASE_URL` environment variable

### pgvector Extension Missing

**Error:** `type "vector" does not exist`

**Solution:**

```sql
-- Connect as superuser
psql -U postgres -d cases_llama3.3

-- Create extension
CREATE EXTENSION IF NOT EXISTS vector;
```

### set_updated_at() Function Missing

**Error:** `function set_updated_at() does not exist`

**This function should be in the original cases schema. If missing:**

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## Performance Tips

### During Migration

- Migration takes ~5-10 seconds
- Creates indexes automatically (may take longer with existing data)
- Safe to run multiple times (uses `IF NOT EXISTS`)

### During Ingestion

**Fast Mode (Ollama):**

```bash
export USE_OLLAMA=true
python batch_process_briefs.py --briefs-dir downloaded-briefs
```

- ~8-10 seconds per brief
- Uses local Ollama embeddings

**Slower Mode (OpenAI):**

```bash
export USE_OLLAMA=false
python batch_process_briefs.py --briefs-dir downloaded-briefs
```

- ~15-20 seconds per brief
- Uses OpenAI API (requires API key)

**Parallel Processing (Future):**

```bash
# Process multiple years in parallel
python batch_process_briefs.py --year 2024 &
python batch_process_briefs.py --year 2023 &
wait
```

---

## Next Steps

After successful migration and ingestion:

1. **Validate Data Quality**

   ```sql
   -- Check totals
   SELECT COUNT(*) as total_briefs FROM briefs;
   SELECT COUNT(*) as linked_briefs FROM briefs WHERE case_id IS NOT NULL;
   SELECT COUNT(*) as chained_briefs FROM briefs WHERE responds_to_brief_id IS NOT NULL;
   ```

2. **Test Search**

   ```sql
   -- Semantic search
   SELECT brief_id, case_file_id, brief_type
   FROM briefs
   WHERE full_embedding IS NOT NULL
   LIMIT 5;
   ```

3. **Review Documentation**

   - `docs/BRIEF_INGESTION_GUIDE.md` - Complete guide
   - `docs/BRIEFS_SCHEMA_EXTENSION.md` - Schema reference
   - `docs/BRIEFS_CRITICAL_IMPROVEMENTS.md` - Visual guide

4. **Build API Endpoints**
   - See `app/api/v1/endpoints/` for examples
   - Add `briefs.py` endpoint file

---

## Support

For questions or issues:

1. Check `docs/BRIEF_INGESTION_GUIDE.md` for detailed troubleshooting
2. Review migration logs
3. Check database logs: `tail -f /var/log/postgresql/postgresql-16-main.log`
