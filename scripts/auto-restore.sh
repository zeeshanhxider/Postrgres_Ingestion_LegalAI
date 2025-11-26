#!/bin/bash
set -e

# =============================================================================
# AUTO-RESTORE SCRIPT
# =============================================================================
# This script runs on first container startup and restores the database dump.
# It only runs if the database is empty (no tables exist).
# =============================================================================

DB_NAME="cases_llama3_3"
DB_USER="postgres"
DUMP_FILE="/docker-data/restore.dump"

echo "🔧 Auto-restore script starting..."

# Check if dump file exists
if [ ! -f "$DUMP_FILE" ]; then
    echo "⚠️  No dump file found at $DUMP_FILE"
    echo "📝 Running init-db.sql to create fresh schema..."
    exit 0
fi

# Check if database has tables (i.e., already restored)
TABLE_COUNT=$(psql -U $DB_USER -d $DB_NAME -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

if [ "$TABLE_COUNT" -gt "0" ]; then
    echo "✅ Database already has $TABLE_COUNT tables. Skipping restore."
    exit 0
fi

echo "📦 Database is empty. Restoring from dump..."
echo "   Dump file: $DUMP_FILE"
echo "   Database: $DB_NAME"

# Restore the dump
pg_restore -U $DB_USER -d $DB_NAME --no-owner --no-privileges --verbose "$DUMP_FILE" || {
    echo "⚠️  pg_restore completed with warnings (this is often normal)"
}

# Verify restoration
FINAL_COUNT=$(psql -U $DB_USER -d $DB_NAME -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
echo "✅ Restore complete! Database now has $FINAL_COUNT tables."

# List the tables
echo ""
echo "📋 Tables in database:"
psql -U $DB_USER -d $DB_NAME -c "\dt"
