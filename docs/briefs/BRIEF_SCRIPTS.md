# Brief Ingestion Scripts

## `clear_briefs.ps1`

Clears all brief data from the database.

```powershell
.\clear_briefs.ps1
```

Truncates the `briefs` table and all related tables (chunks, phrases, sentences, etc.) via CASCADE.

---

## `ingest_briefs.ps1`

Processes PDF briefs with **parallel processing** and generates Ollama embeddings.

### Usage

```powershell
# Process all briefs with 3 workers (default)
.\ingest_briefs.ps1

# Process with 5 parallel workers (faster!)
.\ingest_briefs.ps1 -Workers 5

# Process specific year with 4 workers
.\ingest_briefs.ps1 -Year 2024 -Workers 4

# Process single case folder
.\ingest_briefs.ps1 -CaseFolder "83895-4"

# Show help
.\ingest_briefs.ps1 -Help
```

### Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `-Year` | Process briefs from specific year only | `-Year 2024` |
| `-CaseFolder` | Process single case folder only | `-CaseFolder "83895-4"` |
| `-Workers` | Number of parallel workers (default: 3, max: 5) | `-Workers 5` |
| `-Help` | Display help message | `-Help` |

### Performance

- **Default (3 workers):** ~20-40 seconds per brief
- **5 workers:** ~15-30 seconds per brief
- **Sequential (1 worker):** ~1-2 minutes per brief

Higher worker counts increase throughput but require more Ollama server capacity.

### Features

- ⚡ **Parallel processing** - Multiple PDFs processed simultaneously
- 🔄 Uses Ollama embeddings (mxbai-embed-large, 1024 dims)
- 📝 Creates timestamped log files
- 📊 Shows progress and statistics
- ✅ Asks for confirmation before processing
- 🔒 Thread-safe database operations
