# 🗑️ Database Reset Scripts

Two convenient scripts for managing and resetting your law-helper database.

## 🚀 Quick Usage

### Shell Script (Recommended for Docker)
```bash
# Show database information
./scripts/reset_database.sh info

# Drop all tables (keep database structure)
./scripts/reset_database.sh drop

# Complete database reset with schema recreation
./scripts/reset_database.sh reset

# Restart database container
./scripts/reset_database.sh restart

# Show database logs
./scripts/reset_database.sh logs
```

### Python Script (More Advanced)
```bash
# Show database information
python scripts/reset_database.py --action info

# Drop all tables
python scripts/reset_database.py --action drop-tables --confirm

# Drop entire database
python scripts/reset_database.py --action drop-database --confirm

# Recreate database with fresh schema
python scripts/reset_database.py --action recreate --confirm
```

## 📋 Script Comparison

| Feature | Shell Script | Python Script |
|---------|-------------|---------------|
| **Best for** | Docker environments | Direct PostgreSQL connections |
| **Dependencies** | Docker, Docker Compose | Python, psycopg2 |
| **Safety** | Interactive confirmations | `--confirm` flag required |
| **Database info** | Basic stats | Detailed table counts |
| **Container management** | ✅ Can restart containers | ❌ Database connection only |

## 🔧 Shell Script Commands

### `info` - Database Information
Shows current database state, table count, and row counts.

```bash
./scripts/reset_database.sh info
```
**Output:**
```
📊 Database Information
========================
Database: law_helper
User: law_user
Container: law-helper-postgres-1

✅ Database exists
📋 Tables: 15

📊 Table row counts:
  cases: 245
  case_chunks: 1,234
  parties: 490
  ...
```

### `drop` - Drop All Tables
Removes all tables but keeps the database structure and extensions.

```bash
./scripts/reset_database.sh drop
```
**What it does:**
- Lists all tables to be dropped
- Asks for confirmation
- Drops tables with CASCADE to handle foreign keys
- Preserves database, extensions, and functions

### `reset` - Complete Reset
Full database reset with schema recreation.

```bash
./scripts/reset_database.sh reset
```
**What it does:**
1. Terminates all database connections
2. Drops the entire database
3. Creates a fresh database
4. Runs `init-db.sql` to recreate schema
5. Database is ready for fresh data

### `restart` - Restart Container
Restarts the PostgreSQL Docker container.

```bash
./scripts/reset_database.sh restart
```

### `logs` - Show Logs
Displays recent database container logs.

```bash
./scripts/reset_database.sh logs
```

## 🐍 Python Script Commands

### Database Information
```bash
python scripts/reset_database.py --action info
```

### Drop Tables Only
```bash
python scripts/reset_database.py --action drop-tables --confirm
```

### Drop Entire Database
```bash
python scripts/reset_database.py --action drop-database --confirm
```

### Recreate Database
```bash
python scripts/reset_database.py --action recreate --confirm
```

### Force Operations (No Prompts)
```bash
python scripts/reset_database.py --action drop-tables --force
```

## ⚠️ Safety Features

### Confirmation Required
Both scripts require explicit confirmation for destructive operations:

**Shell Script:**
```bash
Are you sure you want to drop all tables? (yes/no): yes
```

**Python Script:**
```bash
python scripts/reset_database.py --action drop-tables --confirm
```

### What Gets Preserved vs Deleted

| Operation | Tables | Database | Extensions | Schema | Data |
|-----------|--------|----------|------------|---------|------|
| `drop` | ❌ Deleted | ✅ Kept | ✅ Kept | ❌ Deleted | ❌ Deleted |
| `reset` | ❌ Deleted | 🔄 Recreated | 🔄 Recreated | 🔄 Recreated | ❌ Deleted |

## 🔄 Common Workflows

### 1. Development Reset
When you want to test with fresh data:
```bash
./scripts/reset_database.sh drop
python batch_processor.py ./case-pdfs/ --limit 5
```

### 2. Complete System Reset
When you need to start completely fresh:
```bash
./scripts/reset_database.sh reset
python batch_processor.py ./case-pdfs/
```

### 3. Check Current State
Before making any changes:
```bash
./scripts/reset_database.sh info
```

### 4. Troubleshooting
If database connections are stuck:
```bash
./scripts/reset_database.sh restart
./scripts/reset_database.sh logs
```

## 🚨 Emergency Recovery

If something goes wrong:

1. **Check container status:**
   ```bash
   docker ps | grep postgres
   ```

2. **Restart everything:**
   ```bash
   docker compose down
   docker compose up -d
   ```

3. **Complete reset:**
   ```bash
   ./scripts/reset_database.sh reset
   ```

4. **Restore from backup (if available):**
   ```bash
   docker exec -i law-helper-postgres-1 psql -U law_user -d law_helper < backup.sql
   ```

## 📝 Notes

- **Always backup important data** before running reset operations
- The shell script works with Docker Compose environments
- The Python script can work with any PostgreSQL connection
- Both scripts respect your database configuration in `.env` or `docker-compose.yml`
- Database extensions (pgvector, citext, etc.) are recreated automatically
- All foreign key constraints are handled properly during drops

## 🔧 Configuration

Scripts automatically detect your database configuration from:
1. Environment variables (`DATABASE_URL`, etc.)
2. Docker Compose configuration
3. Default values for law-helper project

Default configuration:
- **Database:** `law_helper`
- **User:** `law_user`
- **Password:** `law_password`
- **Host:** `localhost:5432`
