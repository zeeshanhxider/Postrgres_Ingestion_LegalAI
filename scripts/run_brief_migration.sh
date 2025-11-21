#!/bin/bash

# Quick Migration Script for Briefs Schema
# Adds briefs tables to existing cases_llama3.3 database

set -e  # Exit on error

echo "======================================================================"
echo "Brief Schema Migration Script"
echo "======================================================================"
echo ""

# Configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-cases_llama3.3}"
DB_USER="${DB_USER:-postgres}"

echo "Database Configuration:"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo ""

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "❌ Error: psql not found. Please install PostgreSQL client."
    exit 1
fi

# Test connection
echo "🔍 Testing database connection..."
if ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "\q" 2>/dev/null; then
    echo "❌ Error: Cannot connect to database."
    echo "Please check your connection settings and password."
    exit 1
fi
echo "✅ Database connection successful"
echo ""

# Check if migration already run
echo "🔍 Checking if briefs table already exists..."
TABLE_EXISTS=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'briefs');")

if [ "$TABLE_EXISTS" = "t" ]; then
    echo "⚠️ WARNING: briefs table already exists!"
    echo "Migration may have already been run."
    echo ""
    read -p "Do you want to continue anyway? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Migration cancelled."
        exit 0
    fi
fi

# Run migration
echo "🚀 Running migration script..."
echo ""

if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f scripts/migrate_briefs_schema.sql; then
    echo ""
    echo "======================================================================"
    echo "✅ Migration completed successfully!"
    echo "======================================================================"
    echo ""
    
    # Validate migration
    echo "🔍 Validating migration..."
    
    TABLE_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_name LIKE 'brief%';")
    
    echo "✅ Created $TABLE_COUNT brief tables"
    echo ""
    echo "Tables created:"
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'brief%' ORDER BY table_name;"
    echo ""
    
    # Test normalization function
    echo "🔍 Testing normalization function..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT normalize_case_file_id('69423-5') as normalized_id;"
    echo ""
    
    echo "======================================================================"
    echo "🎉 All done! Next steps:"
    echo "======================================================================"
    echo "1. Run batch processing:"
    echo "   python batch_process_briefs.py --briefs-dir downloaded-briefs"
    echo ""
    echo "2. Check results:"
    echo "   psql -d $DB_NAME -c 'SELECT COUNT(*) FROM briefs;'"
    echo ""
    echo "3. See full guide:"
    echo "   docs/BRIEF_INGESTION_GUIDE.md"
    echo "======================================================================"
else
    echo ""
    echo "======================================================================"
    echo "❌ Migration failed!"
    echo "======================================================================"
    echo "Check the error messages above for details."
    exit 1
fi
