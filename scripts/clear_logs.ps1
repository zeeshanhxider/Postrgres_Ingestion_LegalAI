# Clear Logs Script (PowerShell)
# Clears all log files from the logs directory and root directory

param(
    [switch]$Force
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $projectRoot "logs"

Write-Host "=" * 60
Write-Host "CLEAR LOGS SCRIPT"
Write-Host "=" * 60

# Find all log files
$logFiles = @()

# Logs in logs/ directory
if (Test-Path $logsDir) {
    $logFiles += Get-ChildItem -Path $logsDir -Filter "*.log" -File
}

# Logs in root directory
$logFiles += Get-ChildItem -Path $projectRoot -Filter "*.log" -File

if ($logFiles.Count -eq 0) {
    Write-Host "`n✅ No log files found to clear."
    exit 0
}

Write-Host "`n📋 Found $($logFiles.Count) log files:"
Write-Host ("-" * 60)

$totalSize = 0
foreach ($file in $logFiles | Sort-Object Name) {
    $sizeKB = [math]::Round($file.Length / 1KB, 1)
    $totalSize += $file.Length
    $relPath = $file.FullName.Replace($projectRoot, "").TrimStart("\")
    Write-Host "  $relPath ($sizeKB KB)"
}

Write-Host ("-" * 60)
$totalMB = [math]::Round($totalSize / 1MB, 2)
Write-Host "Total size: $totalMB MB`n"

if (-not $Force) {
    $response = Read-Host "🗑️  Delete all log files? [y/N]"
    if ($response.ToLower() -ne 'y') {
        Write-Host "❌ Cancelled."
        exit 0
    }
}

# Delete files
$deleted = 0
foreach ($file in $logFiles) {
    try {
        Remove-Item $file.FullName -Force
        $deleted++
        Write-Host "  ✅ Deleted: $($file.Name)"
    }
    catch {
        Write-Host "  ❌ Failed to delete $($file.Name): $_"
    }
}

Write-Host "`n✅ Deleted $deleted/$($logFiles.Count) log files."
