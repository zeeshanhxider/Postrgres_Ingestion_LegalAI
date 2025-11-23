#!/usr/bin/env pwsh
# Ingest Briefs Script
# This script processes all PDF briefs from the downloaded-briefs folder
# with Ollama embeddings

param(
    [string]$Year = $null,
    [string]$CaseFolder = $null,
    [int]$Workers = 5,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Ingest Briefs Script
====================

Usage:
  .\ingest_briefs.ps1                           # Process all briefs (5 parallel workers)
  .\ingest_briefs.ps1 -Year 2024               # Process only 2024 briefs
  .\ingest_briefs.ps1 -CaseFolder "83895-4"    # Process single case folder
  .\ingest_briefs.ps1 -Workers 10              # Use 10 parallel workers (faster!)

Options:
  -Year <year>           Process briefs for a specific year only
  -CaseFolder <folder>   Process a single case folder only
  -Workers <number>      Number of parallel workers (default: 5, can go higher if Ollama can handle it)
  -Help                  Show this help message

Examples:
  .\ingest_briefs.ps1
  .\ingest_briefs.ps1 -Year 2024 -Workers 10
  .\ingest_briefs.ps1 -CaseFolder "83895-4" -Workers 15

Note: This uses Ollama embeddings from https://ollama.legaldb.ai
      Processing time: ~15-25 seconds per brief (with 5 workers), ~10-15 seconds (with 10+ workers)
      More workers = faster, but watch your Ollama server load
"@ -ForegroundColor Cyan
    exit 0
}

$DbUrl = "postgresql://postgres:postgres123@localhost:5433/cases_llama3_3"

Write-Host "🚀 Starting Brief Ingestion Pipeline" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""

# Show configuration
Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  Database: localhost:5433/cases_llama3_3"

# Read USE_OLLAMA from .env file
$UseOllama = "true"
if (Test-Path ".env") {
    $EnvContent = Get-Content ".env"
    foreach ($Line in $EnvContent) {
        if ($Line -match "^\s*USE_OLLAMA\s*=\s*(.+)") {
            $UseOllama = $Matches[1].Trim()
            break
        }
    }
}

if ($UseOllama -eq "false") {
    Write-Host "  Embeddings: OpenAI (text-embedding-3-large)" -ForegroundColor Green
    Write-Host "  Model: text-embedding-3-large (1024 dims)"
} else {
    Write-Host "  Embeddings: Ollama (https://ollama.legaldb.ai)"
    Write-Host "  Model: mxbai-embed-large (1024 dims)"
}

Write-Host "  Parallel Workers: $Workers" -ForegroundColor Green

if ($CaseFolder) {
    Write-Host "  Mode: Single case folder" -ForegroundColor Yellow
    Write-Host "  Case: $CaseFolder"
} elseif ($Year) {
    Write-Host "  Mode: Year filter" -ForegroundColor Yellow
    Write-Host "  Year: $Year"
} else {
    Write-Host "  Mode: All briefs (all years)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""

# Count PDFs
$TotalPdfs = (Get-ChildItem -Path "downloaded-briefs" -Recurse -Filter "*.pdf" | Measure-Object).Count
Write-Host "📄 Found $TotalPdfs PDF files in downloaded-briefs/" -ForegroundColor Cyan
Write-Host ""

# Confirm before proceeding
$Confirm = Read-Host "Proceed with ingestion? (y/N)"
if ($Confirm -ne "y" -and $Confirm -ne "Y") {
    Write-Host "❌ Cancelled" -ForegroundColor Red
    exit 0
}

Write-Host ""
Write-Host "Processing..." -ForegroundColor Green
Write-Host ""

# Build command
$Command = "python batch_process_briefs.py --db-url `"$DbUrl`" --workers $Workers"

if ($CaseFolder) {
    $Command += " --case-folder `"$CaseFolder`""
} elseif ($Year) {
    $Command += " --year $Year"
}

# Add logging
$LogFile = "batch_process_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
$Command += " 2>&1 | Tee-Object -FilePath `"$LogFile`""

Write-Host "Log file: $LogFile" -ForegroundColor Cyan
Write-Host ""

# Execute
Invoke-Expression $Command

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host "✅ Ingestion completed successfully!" -ForegroundColor Green
    Write-Host ""
    
    # Show summary
    Write-Host "Summary:" -ForegroundColor Cyan
    docker exec legal_ai_postgres psql -U postgres -d cases_llama3_3 -c "SELECT COUNT(*) as total_briefs, SUM(page_count) as total_pages, SUM(word_count) as total_words FROM briefs;"
    
    Write-Host ""
    Write-Host "Chunks with embeddings:" -ForegroundColor Cyan
    docker exec legal_ai_postgres psql -U postgres -d cases_llama3_3 -c "SELECT COUNT(*) as total_chunks, SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) as with_embedding, ROUND(100.0 * SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as coverage_pct FROM brief_chunks;"
    
} else {
    Write-Host ""
    Write-Host "❌ Ingestion failed! Check log: $LogFile" -ForegroundColor Red
    exit 1
}
