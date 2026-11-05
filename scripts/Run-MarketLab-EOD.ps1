<#
.SYNOPSIS
  Run one EOD sync (or a bounded backfill) and exit with a status-specific code.
.DESCRIPTION
  Exit codes: 0 SUCCESS / DRY_RUN_OK / NO_SESSION / already succeeded (-IfNeeded); 10 SKIPPED; 20 PARTIAL; 30 FAILED;
  2 configuration/setup error. FAILED and PARTIAL are never exit 0.
  Uses .venv\Scripts\python.exe directly (no uv needed at schedule time). Output is appended to var\logs\eod_task_<yyyyMMdd>.log.
  Default session = today in Asia/Ho_Chi_Minh (decided by the Python job, not by UTC).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Run-MarketLab-EOD.ps1 -Date 2026-11-04 -DryRun
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Run-MarketLab-EOD.ps1 -Backfill -From 2026-10-01 -To 2026-10-31 -DryRun
#>
[CmdletBinding()]
param(
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$Date,
    [switch]$DryRun,
    [switch]$IfNeeded,
    [ValidateSet('CLI','SCHEDULER')][string]$Trigger = 'CLI',
    [switch]$Backfill,
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$From,
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$To,
    [ValidateRange(1,400)][int]$MaxSessions = 0,
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]{0,99}$')][string]$Database
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { Write-Error ".venv missing; run scripts\Setup-MarketLab.ps1"; exit 2 }
New-Item -ItemType Directory -Force (Join-Path $Root 'var\logs') | Out-Null
$log = Join-Path $Root ("var\logs\eod_task_{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
# EOD only writes REAL_PRIVATE data: target = -Database, else MARKETLAB_EOD_DATABASE from .env (the dashboard's
# MARKETLAB_MODE may stay DEMO_OFFLINE). Without either, .env is used as-is (DEMO_OFFLINE -> refused, exit 2).
if (-not $Database) {
    $line = Get-Content (Join-Path $Root '.env') -ErrorAction SilentlyContinue | Where-Object { $_ -match '^MARKETLAB_EOD_DATABASE=\S+' } | Select-Object -First 1
    if ($line) { $Database = ($line -split '=', 2)[1].Trim() }
}
if ($Database) { $env:MARKETLAB_MODE = 'REAL_PRIVATE'; $env:MARKETLAB_SQL_DATABASE = $Database }

if ($Backfill) {
    if (-not $From -or -not $To) { Write-Error "-Backfill needs -From and -To"; exit 2 }
    $cliArgs = @('eod','backfill','--from',$From,'--to',$To)
    if ($MaxSessions -gt 0) { $cliArgs += @('--max-sessions',"$MaxSessions") }
} else {
    $cliArgs = @('eod','sync','--trigger',$Trigger)
    if ($Date) { $cliArgs += @('--date',$Date) }
    if ($IfNeeded) { $cliArgs += '--if-needed' }
}
if ($DryRun) { $cliArgs += '--dry-run' }

$stamp = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
Add-Content $log "===== $stamp Run-MarketLab-EOD $($cliArgs -join ' ') (user $env:USERNAME, tz $((Get-TimeZone).Id))" -Encoding utf8
$ErrorActionPreference = 'Continue'   # native stderr must not abort (Windows PowerShell 5.1)
$out = & $py -X utf8 -m marketlab_app.cli @cliArgs 2>> $log
$code = $LASTEXITCODE
$out | Add-Content $log -Encoding utf8
$out | Out-Host
try {
    $j = ($out -join "`n") | ConvertFrom-Json
    $status = if ($j.status) { $j.status } else { ($j.status_counts | ConvertTo-Json -Compress) }
    Write-Host ("EOD result: {0} {1} (exit {2})" -f $status, $j.error_code, $code)
} catch { Write-Host "EOD finished with exit code $code (see $log)" }
Add-Content $log "===== exit $code" -Encoding utf8
exit $code
