#!/usr/bin/env pwsh
# Clear Briefs Database Script
# This script truncates all brief-related tables in the database

Write-Host "🗑️  Clearing briefs database..." -ForegroundColor Yellow
Write-Host ""

# Truncate briefs table (will cascade to all related tables)
docker exec legal_ai_postgres psql -U postgres -d cases_llama3_3 -c "TRUNCATE briefs CASCADE;"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Briefs database cleared successfully!" -ForegroundColor Green
    Write-Host ""
    
    # Show confirmation
    Write-Host "Verifying..." -ForegroundColor Cyan
    docker exec legal_ai_postgres psql -U postgres -d cases_llama3_3 -c "SELECT COUNT(*) as remaining_briefs FROM briefs;"
} else {
    Write-Host ""
    Write-Host "❌ Failed to clear database!" -ForegroundColor Red
    exit 1
}
