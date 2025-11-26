# Backend Dev Setup Guide

## Quick Start

Clone this repo and run the database:

```powershell
git clone https://github.com/zeeshanhxider/Postrgres_Ingestion_LegalAI.git
cd Postrgres_Ingestion_LegalAI
docker-compose up -d
```

Your backend connects to: `postgresql://postgres:postgres123@localhost:5433/cases_llama3_3`

---

## When Schema Updates

When the DB dev pushes a new dump file:

```powershell
cd Postrgres_Ingestion_LegalAI
git pull
docker-compose down -v
docker-compose up -d
```

---

## Alternative: Add Database to Your Repo

If you prefer running the database from your own repo, copy these files:

### 1. Create `scripts/auto-restore.sh`

```bash
#!/bin/bash
set -e

DB_NAME="cases_llama3_3"
DB_USER="postgres"
DUMP_FILE="/docker-data/restore.dump"

echo "🔧 Auto-restore script starting..."

if [ ! -f "$DUMP_FILE" ]; then
    echo "⚠️  No dump file found at $DUMP_FILE"
    exit 0
fi

TABLE_COUNT=$(psql -U $DB_USER -d $DB_NAME -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

if [ "$TABLE_COUNT" -gt "0" ]; then
    echo "✅ Database already has $TABLE_COUNT tables. Skipping restore."
    exit 0
fi

echo "📦 Restoring from dump..."
pg_restore -U $DB_USER -d $DB_NAME --no-owner --no-privileges --verbose "$DUMP_FILE" || true

echo "✅ Restore complete!"
```

### 2. Copy `cases_llama3_3.dump`

Get the latest dump file from the DB dev.

### 3. Add to `docker-compose.yml`

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: legal_ai_postgres
    environment:
      POSTGRES_DB: cases_llama3_3
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres123
      POSTGRES_INITDB_ARGS: "--encoding=UTF-8"
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/auto-restore.sh:/docker-entrypoint-initdb.d/01-restore.sh:ro
      - ./cases_llama3_3.dump:/docker-data/restore.dump:ro
    command: >
      postgres -c shared_preload_libraries=vector
      -c max_connections=200
      -c listen_addresses='*'
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

### 4. Update Your Backend Connection

```python
DATABASE_URL = "postgresql://postgres:postgres123@localhost:5433/cases_llama3_3"
```

---

## Connection Details

| Setting  | Value            |
| -------- | ---------------- |
| Host     | `localhost`      |
| Port     | `5433`           |
| Database | `cases_llama3_3` |
| Username | `postgres`       |
| Password | `postgres123`    |
