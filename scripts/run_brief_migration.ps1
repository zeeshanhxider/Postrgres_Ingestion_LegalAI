# Quick Migration Script for Briefs Schema (PowerShell)
# Adds briefs tables to existing cases_llama3.3 database

$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Brief Schema Migration Script" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$DB_HOST = if ($env:DB_HOST) { $env:DB_HOST } else { "localhost" }
$DB_PORT = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$DB_NAME = if ($env:DB_NAME) { $env:DB_NAME } else { "cases_llama3.3" }
$DB_USER = if ($env:DB_USER) { $env:DB_USER } else { "postgres" }
$DB_PASSWORD = if ($env:DB_PASSWORD) { $env:DB_PASSWORD } else { Read-Host "Enter database password" -AsSecureString | ConvertFrom-SecureString -AsPlainText }

Write-Host "Database Configuration:"
Write-Host "  Host: $DB_HOST"
Write-Host "  Port: $DB_PORT"
Write-Host "  Database: $DB_NAME"
Write-Host "  User: $DB_USER"
Write-Host ""

# Check if psql is available
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Error: psql not found. Please install PostgreSQL client." -ForegroundColor Red
    exit 1
}

# Test connection
Write-Host "🔍 Testing database connection..."
$env:PGPASSWORD = $DB_PASSWORD
try {
    $null = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "\q" 2>&1
    Write-Host "✅ Database connection successful" -ForegroundColor Green
}
catch {
    Write-Host "❌ Error: Cannot connect to database." -ForegroundColor Red
    Write-Host "Please check your connection settings and password." -ForegroundColor Red
    exit 1
}
Write-Host ""

# Check if migration already run
Write-Host "🔍 Checking if briefs table already exists..."
$TABLE_EXISTS = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -tAc "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'briefs');"

if ($TABLE_EXISTS -eq "t") {
    Write-Host "⚠️ WARNING: briefs table already exists!" -ForegroundColor Yellow
    Write-Host "Migration may have already been run."
    Write-Host ""
    $response = Read-Host "Do you want to continue anyway? (y/N)"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-Host "Migration cancelled."
        exit 0
    }
}

# Run migration
Write-Host "🚀 Running migration script..." -ForegroundColor Cyan
Write-Host ""

$migrationPath = "scripts\migrate_briefs_schema.sql"

if (-not (Test-Path $migrationPath)) {
    Write-Host "❌ Error: Migration script not found at: $migrationPath" -ForegroundColor Red
    exit 1
}

try {
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $migrationPath
    
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host "✅ Migration completed successfully!" -ForegroundColor Green
    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host ""
    
    # Validate migration
    Write-Host "🔍 Validating migration..."
    
    $TABLE_COUNT = psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_name LIKE 'brief%';"
    
    Write-Host "✅ Created $TABLE_COUNT brief tables" -ForegroundColor Green
    Write-Host ""
    Write-Host "Tables created:"
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'brief%' ORDER BY table_name;"
    Write-Host ""
    
    # Test normalization function
    Write-Host "🔍 Testing normalization function..."
    psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT normalize_case_file_id('69423-5') as normalized_id;"
    Write-Host ""
    
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "🎉 All done! Next steps:" -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "1. Run batch processing:"
    Write-Host "   python batch_process_briefs.py --briefs-dir downloaded-briefs"
    Write-Host ""
    Write-Host "2. Check results:"
    Write-Host "   psql -d $DB_NAME -c 'SELECT COUNT(*) FROM briefs;'"
    Write-Host ""
    Write-Host "3. See full guide:"
    Write-Host "   docs\BRIEF_INGESTION_GUIDE.md"
    Write-Host "======================================================================" -ForegroundColor Cyan
    
}
catch {
    Write-Host ""
    Write-Host "======================================================================" -ForegroundColor Red
    Write-Host "❌ Migration failed!" -ForegroundColor Red
    Write-Host "======================================================================" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
