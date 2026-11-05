<#
.SYNOPSIS
  First-time setup of the MarketLab VN30 local product (few steps, idempotent).
.DESCRIPTION
  1. checks uv + ODBC Driver 18; 2. creates .venv with pinned dependencies (uv sync, PyPI only);
  3. creates .env from .env.example if missing and fills a random MARKETLAB_OPS_TOKEN (never printed);
  4. optionally sets mode/database/provider interpreter in .env; 5. runs `cli check`.
  It never creates databases, scheduled tasks, firewall rules or services.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Setup-MarketLab.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Setup-MarketLab.ps1 -Mode REAL_PRIVATE -Database MarketLabVN30_Live -ProviderPython "C:\Users\me\AppData\Local\Programs\Python\Python312\python.exe"
#>
[CmdletBinding()]
param(
    [ValidateSet('DEMO_OFFLINE','REAL_PRIVATE')][string]$Mode,
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]{0,99}$')][string]$Database,
    [string]$ProviderPython,
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_]{0,99}$')][string]$EodDatabase,
    [switch]$SkipCheck
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Set-EnvValue([string]$Path, [string]$Key, [string]$Value) {
    $lines = [System.Collections.Generic.List[string]](Get-Content $Path -Encoding utf8)
    $idx = $lines.FindIndex([Predicate[string]]{ param($l) $l -match "^\s*$Key=" })
    if ($idx -ge 0) { $lines[$idx] = "$Key=$Value" } else { $lines.Add("$Key=$Value") }
    Set-Content -Path $Path -Value $lines -Encoding utf8
}

Write-Host "[1/5] Checking prerequisites" -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv not found. Install: https://docs.astral.sh/uv/ (winget install astral-sh.uv)" }
$drivers = (Get-OdbcDriver -Platform 64-bit | Where-Object Name -like '*SQL Server*').Name
if ($drivers -notcontains 'ODBC Driver 18 for SQL Server') {
    Write-Warning "ODBC Driver 18 for SQL Server not found (found: $($drivers -join ', ')). Install it or set MARKETLAB_SQL_DRIVER in .env."
}

Write-Host "[2/5] Creating .venv (uv sync, pinned versions from uv.lock)" -ForegroundColor Cyan
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }

Write-Host "[3/5] Preparing .env (not committed)" -ForegroundColor Cyan
$envPath = Join-Path $Root '.env'
if (-not (Test-Path $envPath)) { Copy-Item (Join-Path $Root '.env.example') $envPath; Write-Host "  created .env from .env.example" }
$current = Get-Content $envPath -Encoding utf8
if (-not ($current -match '^MARKETLAB_OPS_TOKEN=.{32,}$')) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    Set-EnvValue $envPath 'MARKETLAB_OPS_TOKEN' $token
    Write-Host "  generated MARKETLAB_OPS_TOKEN in .env (open .env to read it; it is never printed or logged)"
}

Write-Host "[4/5] Applying requested settings" -ForegroundColor Cyan
if ($Mode) { Set-EnvValue $envPath 'MARKETLAB_MODE' $Mode; Write-Host "  MARKETLAB_MODE=$Mode" }
if ($Database) { Set-EnvValue $envPath 'MARKETLAB_SQL_DATABASE' $Database; Write-Host "  MARKETLAB_SQL_DATABASE=$Database" }
if ($EodDatabase) { Set-EnvValue $envPath 'MARKETLAB_EOD_DATABASE' $EodDatabase; Write-Host "  MARKETLAB_EOD_DATABASE=$EodDatabase (target of Run-MarketLab-EOD.ps1 / scheduled task)" }
if ($ProviderPython) {
    if (-not (Test-Path $ProviderPython)) { throw "ProviderPython not found: $ProviderPython" }
    & $ProviderPython -I -c "import importlib.metadata as m; print('vnstock', m.version('vnstock'))"
    if ($LASTEXITCODE -ne 0) { Write-Warning "vnstock is not importable by $ProviderPython; real EOD will report PROVIDER_UNAVAILABLE." }
    Set-EnvValue $envPath 'MARKETLAB_PROVIDER_PYTHON' $ProviderPython
}

if (-not $SkipCheck) {
    Write-Host "[5/5] Checking configuration and database" -ForegroundColor Cyan
    & (Join-Path $Root '.venv\Scripts\python.exe') -X utf8 -m marketlab_app.cli check
    if ($LASTEXITCODE -ne 0) { Write-Warning "Check reported problems (see JSON above). Fix .env / SQL Server, then run scripts\Start-MarketLab.ps1." ; exit $LASTEXITCODE }
}
Write-Host "Setup done. Start: powershell -ExecutionPolicy Bypass -File scripts\Start-MarketLab.ps1" -ForegroundColor Green
