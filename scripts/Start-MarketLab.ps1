<#
.SYNOPSIS
  Start the MarketLab VN30 API + web UI on http://127.0.0.1:<port> (loopback only).
.DESCRIPTION
  Checks .venv, dependencies, .env, ODBC driver, SQL Server/schema/mode (cli check) and that the port is free,
  then starts uvicorn and prints the URLs. -Mode/-Database override .env for THIS process only.
  -Background starts a hidden process and writes var\marketlab_<port>.pid (stop with scripts\Stop-MarketLab.ps1).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1 -Mode REAL_PRIVATE -Database MarketLabVN30_Live -Port 8001
#>
[CmdletBinding()]
param(
    [ValidateSet('DEMO_OFFLINE','REAL_PRIVATE')][string]$Mode,
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]{0,99}$')][string]$Database,
    [ValidateRange(1024,65535)][int]$Port = 0,
    [switch]$NoBrowser,
    [switch]$Background
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$py = Join-Path $Root '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) { throw ".venv missing. Run first: powershell -ExecutionPolicy Bypass -File scripts\Setup-MarketLab.ps1" }
$ErrorActionPreference = 'Continue'
& $py -c "import fastapi, uvicorn, pyodbc, swagger_ui_bundle" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Dependencies missing in .venv. Run: uv sync --frozen" }
$ErrorActionPreference = 'Stop'
if (-not (Test-Path (Join-Path $Root '.env'))) { Write-Warning ".env not found: using defaults (DEMO_OFFLINE, MarketLabVN30_Demo on '.'). Run scripts\Setup-MarketLab.ps1 to create it." }

if ($Mode) { $env:MARKETLAB_MODE = $Mode }
if ($Database) { $env:MARKETLAB_SQL_DATABASE = $Database }
if ($Port -gt 0) { $env:MARKETLAB_PORT = "$Port" }
if ($Mode -eq 'REAL_PRIVATE' -and -not $Database -and -not $env:MARKETLAB_SQL_DATABASE) {
    $dotenvDb = (Get-Content (Join-Path $Root '.env') -ErrorAction SilentlyContinue | Where-Object { $_ -match '^MARKETLAB_SQL_DATABASE=' })
    if (-not $dotenvDb -or $dotenvDb -match 'MarketLabVN30_Demo$') { throw "REAL_PRIVATE needs -Database (e.g. MarketLabVN30_Live); no automatic choice." }
}

Write-Host "Checking configuration, ODBC driver, SQL Server, schema and mode..." -ForegroundColor Cyan
$check = & $py -X utf8 -m marketlab_app.cli check
$checkCode = $LASTEXITCODE
$check | Out-Host
if ($checkCode -ne 0) { throw "Pre-start check failed (exit $checkCode). Nothing started." }
$cfg = ($check -join "`n" | ConvertFrom-Json).config
$p = [int]$cfg.port

if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $p is already in use. Stop the other process or use -Port <n>."
}
$url = "http://127.0.0.1:$p"
Write-Host ""
Write-Host "MarketLab VN30 ($($cfg.mode), database $($cfg.sql_database))" -ForegroundColor Green
Write-Host "  Web UI : $url/"
Write-Host "  Swagger: $url/api/docs"
Write-Host "  Health : $url/api/health   Ready: $url/api/ready"
Write-Host "  Bound to 127.0.0.1 only (not reachable from the LAN)."

if ($Background) {
    New-Item -ItemType Directory -Force (Join-Path $Root 'var\logs') | Out-Null
    $log = Join-Path $Root ("var\logs\api_{0}.log" -f (Get-Date -Format yyyyMMdd))
    # No stream redirection: the child must not inherit this console's handles. The server logs to var\logs itself.
    $proc = Start-Process -FilePath $py -ArgumentList @('-X','utf8','-m','marketlab_app.cli','serve','--port',"$p") -WorkingDirectory $Root `
        -WindowStyle Hidden -PassThru
    Set-Content (Join-Path $Root "var\marketlab_$p.pid") $proc.Id
    $ok = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        try { if ((Invoke-RestMethod "$url/api/health" -TimeoutSec 2).status -eq 'ok') { $ok = $true; break } } catch { }
    }
    if (-not $ok) { throw "Server did not become healthy; see $log" }
    Write-Host "  Running in background, PID $($proc.Id). Stop: scripts\Stop-MarketLab.ps1 -Port $p"
    if (-not $NoBrowser) { Start-Process "$url/" }
    exit 0
}
if (-not $NoBrowser) {
    Start-Job -ScriptBlock { param($u) Start-Sleep 2; Start-Process $u } -ArgumentList "$url/" | Out-Null
}
Write-Host "  Press Ctrl+C to stop."
& $py -X utf8 -m marketlab_app.cli serve --port $p
exit $LASTEXITCODE
