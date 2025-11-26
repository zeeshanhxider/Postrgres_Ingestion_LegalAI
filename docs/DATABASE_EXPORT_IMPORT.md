# Database Export and Import Guide

## 🚀 Quick Start (For Backend Devs)

**When you pull and there's a new dump file:**

```powershell
# 1. Pull latest code (gets the new dump file)
git pull

# 2. Wipe old database and restart (auto-restores new schema)
docker-compose down -v
docker-compose up -d

# Done! Database auto-restores with the new schema.
```

---

## 🔧 Schema Change Workflow (For DB Devs)

**When you make schema changes (migrations, new tables, ALTER TABLE, etc.):**

```powershell
# 1. Make your schema changes directly in the running database
#    (Run migrations, ALTER TABLE commands, CREATE TABLE, etc.)

# 2. Export the updated dump
docker exec legal_ai_postgres pg_dump -U postgres -d cases_llama3_3 -F c -f /tmp/cases_llama3_3.dump
docker cp legal_ai_postgres:/tmp/cases_llama3_3.dump ./cases_llama3_3.dump

# 3. Commit and push
git add cases_llama3_3.dump
git commit -m "Updated schema: added xyz table"
git push
```

### Workflow Summary

| DB Dev (Schema Changes)   | Backend Dev (Uses Schema) |
| ------------------------- | ------------------------- |
| Make schema changes in DB | `git pull`                |
| Export new dump file      | `docker-compose down -v`  |
| `git push`                | `docker-compose up -d`    |

The dump file is the **single source of truth** for the database schema and data.

---

## How Auto-Restore Works

The `docker-compose.yml` is configured to **automatically restore** the database from `cases_llama3_3.dump` on first startup:

1. Container starts → PostgreSQL creates empty database
2. `auto-restore.sh` runs → Restores the dump file (full schema + data)
3. Database is ready with all tables!

**Files involved:**

- `cases_llama3_3.dump` - The database dump (source of truth)
- `scripts/auto-restore.sh` - Auto-restore script

> **Note:** Init scripts only run when the volume is empty. That's why you need `docker-compose down -v` to wipe the volume before restarting.

---

## Export Database from Docker Container

```powershell
# 1. Create dump inside container
docker exec legal_ai_postgres pg_dump -U postgres -d cases_llama3_3 -F c -f /tmp/cases_llama3_3.dump

# 2. Copy dump to your machine
docker cp legal_ai_postgres:/tmp/cases_llama3_3.dump ./cases_llama3_3.dump
```

---

## Import to Another PostgreSQL

### Prerequisites

The target PostgreSQL **must have pgvector extension** installed:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Import Steps

```bash
# Create target database
psql -U your_user -h your_host -c "CREATE DATABASE your_database;"

# Install pgvector extension
psql -U your_user -h your_host -d your_database -c "CREATE EXTENSION vector;"

# Restore dump (provide full or relative path to dump file)
pg_restore -U your_user -h your_host -d your_database /path/to/cases_llama3_3.dump
```

**Examples:**

```bash
# Using absolute path (Windows)
pg_restore -U postgres -h localhost -d my_database D:\freelance\Dobbs_Data\Postgres_Ingestion_LegalAI\cases_llama3_3.dump

# Using relative path (from current directory)
pg_restore -U postgres -h localhost -d my_database ./cases_llama3_3.dump

# Remote database (dump file on local machine)
pg_restore -U user -h db.example.com -d my_database ./cases_llama3_3.dump
```

**Note:** The dump file can be located anywhere on your machine. You don't need to copy it to your production codebase folder - just provide the correct path to `pg_restore`.

---

## Connect from Another Codebase

### Python (SQLAlchemy)

```python
from sqlalchemy import create_engine

engine = create_engine("postgresql://user:password@host:5432/your_database")
```

### Python (psycopg2)

```python
import psycopg2

conn = psycopg2.connect(
    host="your_host",
    port=5432,
    database="your_database",
    user="your_user",
    password="your_password"
)
```

### Connection String Format

```
postgresql://user:password@host:port/database
```

**Example:**

```
postgresql://postgres:postgres123@db.example.com:5432/cases_llama3_3
```

---

## What Gets Exported

- ✅ All 22 case tables (cases, chunks, sentences, etc.)
- ✅ All 7 brief tables (briefs, brief_chunks, brief_phrases, etc.)
- ✅ All indexes and constraints
- ✅ pgvector extension schema
- ✅ All embeddings (VECTOR columns)
- ✅ Functions (normalize_case_file_id, etc.)

**Total:** 29 tables with all data and relationships intact
