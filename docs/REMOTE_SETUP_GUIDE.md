# Remote System Setup Guide

Quick guide to run brief ingestion scripts on a remote system after cloning this repository.

---

## Prerequisites

- Docker and Docker Compose installed
- Python 3.8+ installed
- Git installed
- Brief PDFs available in `downloaded-briefs/` folder structure

---

## Setup Steps

### 1. Clone Repository

```bash
git clone https://github.com/zeeshanhxider/Postrgres_Ingestion_LegalAI.git
cd Postrgres_Ingestion_LegalAI
```

### 2. Start PostgreSQL Container

```bash
# Start Docker container with pgvector
docker-compose up -d

# Verify container is running
docker ps | grep legal_ai_postgres
```

### 3. Import Database

```bash
# Copy your dump file to the project directory
# Then restore the database
docker cp cases_llama3_3.dump legal_ai_postgres:/tmp/
docker exec legal_ai_postgres psql -U postgres -c "CREATE DATABASE cases_llama3_3;"
docker exec legal_ai_postgres psql -U postgres -d cases_llama3_3 -c "CREATE EXTENSION vector;"
docker exec legal_ai_postgres pg_restore -U postgres -d cases_llama3_3 /tmp/cases_llama3_3.dump
```

### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Environment

```bash
# Copy and edit .env file
cp .env.example .env

# Edit .env to set:
# - DATABASE_URL=postgresql://postgres:postgres123@localhost:5433/cases_llama3_3
# - OLLAMA_BASE_URL=https://ollama.legaldb.ai (or your Ollama server)
# - USE_OLLAMA=true
```

### 6. Verify Brief PDFs Structure

Ensure your briefs are in this structure:

```
downloaded-briefs/
├── 2010-briefs/
│   ├── case-folder-1/
│   │   ├── brief1.pdf
│   │   └── brief2.pdf
├── 2024-briefs/
│   ├── 83895-4/
│   │   ├── 857568_Appellant_'s.pdf
│   │   └── 849735_Respondent's.pdf
```

### 7. Run Brief Ingestion

```powershell
# Process all briefs with 10 workers
.\ingest_briefs.ps1 -Workers 10

# Or process specific year
.\ingest_briefs.ps1 -Year 2024 -Workers 10
```

---

## Quick Verification

```bash
# Check database connection
docker exec legal_ai_postgres psql -U postgres -d cases_llama3_3 -c "\dt"

# Check brief count
docker exec legal_ai_postgres psql -U postgres -d cases_llama3_3 -c "SELECT COUNT(*) FROM briefs;"
```

---

## Troubleshooting

**Container won't start:**

```bash
docker-compose down
docker-compose up -d
```

**Port 5433 already in use:**

```bash
# Edit docker-compose.yml to change port mapping
# Change "5433:5432" to "5434:5432" or another available port
```

**Ollama embeddings failing:**

- Check `OLLAMA_BASE_URL` in `.env`
- Verify Ollama server is accessible: `curl https://ollama.legaldb.ai/api/tags`

---

## Performance Tips

- Use **10-15 workers** for fastest processing (~10-15 seconds per brief)
- Ensure Ollama server has sufficient capacity
- Process in batches by year if needed: `-Year 2024`, `-Year 2023`, etc.
