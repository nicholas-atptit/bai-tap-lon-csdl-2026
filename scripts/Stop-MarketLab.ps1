<#
.SYNOPSIS  Stop a MarketLab server started with Start-MarketLab.ps1 -Background.
#>
[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $Root "var\marketlab_$Port.pid"
if (-not (Test-Path $pidFile)) { Write-Host "No PID file for port $Port (nothing started in background)."; exit 0 }
$procId = [int](Get-Content $pidFile)
$p = Get-Process -Id $procId -ErrorAction SilentlyContinue
if ($p -and $p.Path -like (Join-Path $Root '.venv\*')) { Stop-Process -Id $procId; Write-Host "Stopped PID $procId" }
else { Write-Host "PID $procId is not a MarketLab server process; not touching it." }
Remove-Item $pidFile -ErrorAction SilentlyContinue
