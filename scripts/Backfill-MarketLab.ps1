<#
.SYNOPSIS
  Historical OHLCV backfill of the REAL_PRIVATE database (default MarketLabVN30_Live) from the configured provider (KBS via vnstock).
.DESCRIPTION
  Wraps: python -m marketlab_app.cli backfill run|backup|status|report.
  * -DryRun validates everything inside SQL Server and rolls back (nothing written to the business database; the job,
    staging and per-session results are kept in the ops database for review).
  * A real run first takes and verifies COPY_ONLY backups of the business and ops databases (BACKUP ... WITH CHECKSUM,
    RESTORE VERIFYONLY, test restore into a scratch database that is dropped afterwards), unless the job already has one.
  * -Resume continues the latest unfinished job (or -JobRef): staged provider data is reused, only failed chunks are
    refetched, only non-final sessions are re-applied.
  * Dates before 2023-01-01 are refused. -EndDate latest = latest completed session according to the provider calendar
    (after the 16:10 Asia/Ho_Chi_Minh cutoff for today's session).
  Exit codes: 0 COMPLETED / DRY_RUN_OK; 10 lock busy; 20 COMPLETED_WITH_GAPS; 30 FAILED / INTERRUPTED; 2 refused input.
  Output and progress go to the console and to var\logs\backfill_task_<yyyyMMdd>.log (no secrets).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -StartDate 2023-01-01 -EndDate latest -DryRun
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -StartDate 2023-01-01 -EndDate latest
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -Resume
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\Backfill-MarketLab.ps1 -Report
#>
[CmdletBinding()]
param(
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$StartDate = '2023-01-01',
    [ValidatePattern('^(latest|\d{4}-\d{2}-\d{2})$')][string]$EndDate = 'latest',
    [ValidatePattern('^[A-Za-z0-9,]{1,400}$')][string]$Tickers,
    [switch]$DryRun,
    [switch]$Resume,
    [ValidatePattern('^[0-9a-f-]{36}$')][string]$JobRef,
    [switch]$Status,
    [switch]$Report,
    [switch]$BackupOnly,
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]{0,99}$')][string]$Database
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { Write-Error ".venv missing; run scripts\Setup-MarketLab.ps1"; exit 2 }
New-Item -ItemType Directory -Force (Join-Path $Root 'var\logs') | Out-Null
$log = Join-Path $Root ("var\logs\backfill_task_{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
if (-not $Database) {
    $line = Get-Content (Join-Path $Root '.env') -ErrorAction SilentlyContinue | Where-Object { $_ -match '^MARKETLAB_EOD_DATABASE=\S+' } | Select-Object -First 1
    $Database = if ($line) { ($line -split '=', 2)[1].Trim() } else { 'MarketLabVN30_Live' }
}
if ($Database -eq 'MarketLabVN30_Demo' -or $Database -like 'MarketLabVN30_Research*') { Write-Error "Backfill never targets $Database"; exit 2 }
$env:MARKETLAB_MODE = 'REAL_PRIVATE'
$env:MARKETLAB_SQL_DATABASE = $Database

if ($Status) { $cliArgs = @('backfill', 'status'); if ($JobRef) { $cliArgs += @('--job-ref', $JobRef) } }
elseif ($Report) { $cliArgs = @('backfill', 'report'); if ($JobRef) { $cliArgs += @('--job-ref', $JobRef) } }
elseif ($BackupOnly) { $cliArgs = @('backfill', 'backup') }
else {
    $cliArgs = @('backfill', 'run')
    if ($Resume -or $JobRef) {
        $cliArgs += '--resume'
        if ($JobRef) { $cliArgs += @('--job-ref', $JobRef) }
    } else {
        $cliArgs += @('--start-date', $StartDate, '--end-date', $EndDate)
        if ($Tickers) { $cliArgs += @('--tickers', $Tickers) }
    }
    if ($DryRun) { $cliArgs += '--dry-run' }
}
$stamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
Write-Host "MarketLab backfill -> database $Database : $($cliArgs -join ' ')" -ForegroundColor Cyan
Add-Content $log "===== $stamp Backfill-MarketLab $($cliArgs -join ' ') (database $Database, user $env:USERNAME)" -Encoding utf8
$ErrorActionPreference = 'Continue'   # progress lines arrive on stderr
& $py -X utf8 -m marketlab_app.cli @cliArgs 2>&1 | ForEach-Object { $s = "$_"; Add-Content $log $s -Encoding utf8; $s }
$code = $LASTEXITCODE
Add-Content $log "===== exit $code" -Encoding utf8
Write-Host "Backfill exit code $code (log: $log)"
exit $code
