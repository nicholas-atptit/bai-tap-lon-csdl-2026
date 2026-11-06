<#
.SYNOPSIS
  Install / inspect / run / disable / remove the Windows Scheduled Task for the MarketLab EOD job.
.DESCRIPTION
  Nothing is scheduled unless you run this script. Default action installs (or updates) the task DISABLED.
  -Enable turns it on ONLY if a manual (non-dry-run) SUCCESS run already exists in the ops log (manual smoke first).
  Triggers: Monday-Friday at the given Vietnam times (default 16:10, 17:30, 19:30 = retries for late provider data;
  reruns are idempotent and -IfNeeded skips sessions that already succeeded). Times are converted to the machine's
  local timezone. The task runs as the current user, only while logged on (no stored password, no service, no network
  listener). Logs: var\logs\eod_task_<yyyyMMdd>.log.
.EXAMPLE
  .\scripts\Install-MarketLab-EODTask.ps1            # install disabled
  .\scripts\Install-MarketLab-EODTask.ps1 -Show
  .\scripts\Install-MarketLab-EODTask.ps1 -RunNow     # one on-demand run through Task Scheduler (task stays disabled if it was)
  .\scripts\Install-MarketLab-EODTask.ps1 -Enable
  .\scripts\Install-MarketLab-EODTask.ps1 -Disable
  .\scripts\Install-MarketLab-EODTask.ps1 -Uninstall
#>
[CmdletBinding(DefaultParameterSetName = 'Install')]
param(
    [Parameter(ParameterSetName = 'Install')][string[]]$VietnamTimes = @('16:10', '17:30', '19:30'),
    [Parameter(ParameterSetName = 'Enable')][switch]$Enable,
    [Parameter(ParameterSetName = 'Show')][switch]$Show,
    [Parameter(ParameterSetName = 'Disable')][switch]$Disable,
    [Parameter(ParameterSetName = 'RunNow')][switch]$RunNow,
    [Parameter(ParameterSetName = 'Uninstall')][switch]$Uninstall,
    [string]$TaskName = 'MarketLab VN30 EOD'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$TaskPath = '\MarketLab\'
$runner = Join-Path $Root 'scripts\Run-MarketLab-EOD.ps1'
$py = Join-Path $Root '.venv\Scripts\python.exe'

function Get-MLTask { Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue }

function Show-MLTask {
    $t = Get-MLTask
    if (-not $t) { Write-Host "Task '$TaskPath$TaskName' is not installed."; return }
    $i = $t | Get-ScheduledTaskInfo
    [pscustomobject]@{
        Task = "$TaskPath$TaskName"; State = $t.State; Enabled = $t.Settings.Enabled
        Triggers = ($t.Triggers | ForEach-Object { $d = [int]$_.DaysOfWeek; $names = @('Sun','Mon','Tue','Wed','Thu','Fri','Sat') | Where-Object { $d -band (1 -shl [array]::IndexOf(@('Sun','Mon','Tue','Wed','Thu','Fri','Sat'), $_)) }; "{0} {1} (local)" -f ($names -join ','), ([datetime]$_.StartBoundary).ToString('HH:mm') }) -join '; '
        Action = "$($t.Actions[0].Execute) $($t.Actions[0].Arguments)"; WorkingDirectory = $t.Actions[0].WorkingDirectory
        RunAs = $t.Principal.UserId; LogonType = $t.Principal.LogonType
        LastRunTime = $i.LastRunTime; LastTaskResult = $i.LastTaskResult; NextRunTime = $i.NextRunTime
    } | Format-List
    Write-Host "LastTaskResult = process exit code: 0 ok/no-session, 10 skipped, 20 partial, 30 failed, 2 setup error."
}

switch ($PSCmdlet.ParameterSetName) {
    'Show' { Show-MLTask; exit 0 }
    'Disable' { if (Get-MLTask) { Disable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null; Write-Host "Disabled." }; Show-MLTask; exit 0 }
    'Uninstall' { if (Get-MLTask) { Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false; Write-Host "Removed '$TaskPath$TaskName'." } else { Write-Host "Not installed." }; exit 0 }
    'RunNow' {
        $t = Get-MLTask
        if (-not $t) { throw "Not installed. Run without switches first." }
        if (-not $t.Settings.Enabled) {
            Write-Host "Task is disabled; temporarily enabling it for one on-demand run, then disabling it again."
            Enable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null
            Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
            Start-Sleep -Seconds 2
            Disable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null
        } else { Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath }
        Write-Host "Started. Follow var\logs\eod_task_$(Get-Date -Format yyyyMMdd).log; check with -Show (LastTaskResult)."
        exit 0
    }
    'Enable' {
        if (-not (Get-MLTask)) { throw "Not installed. Run without switches first." }
        $line = Get-Content (Join-Path $Root '.env') -ErrorAction SilentlyContinue | Where-Object { $_ -match '^MARKETLAB_EOD_DATABASE=\S+' } | Select-Object -First 1
        if (-not $line) { throw "MARKETLAB_EOD_DATABASE is not set in .env (the REAL_PRIVATE database the task will sync)." }
        $env:MARKETLAB_MODE = 'REAL_PRIVATE'; $env:MARKETLAB_SQL_DATABASE = ($line -split '=', 2)[1].Trim()
        $ErrorActionPreference = 'Continue'
        $status = & $py -X utf8 -m marketlab_app.cli eod status --limit 200 2>$null | Out-String | ConvertFrom-Json
        $ErrorActionPreference = 'Stop'
        $manual = @($status.recent_runs | Where-Object { $_.Status -eq 'SUCCESS' -and -not $_.IsDryRun })
        if ($manual.Count -eq 0) { throw "Refusing to enable: no manual non-dry-run SUCCESS in the ops log yet. Run scripts\Run-MarketLab-EOD.ps1 -Date <closed session> first." }
        Enable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null
        Write-Host "Enabled (last manual SUCCESS: run #$($manual[0].EodRunId) session $($manual[0].SessionDate))."
        Show-MLTask; exit 0
    }
}

# ---- Install / update (DISABLED) --------------------------------------------------------------------------------
if (-not (Test-Path $py)) { throw ".venv missing; run scripts\Setup-MarketLab.ps1 first" }
$tz = Get-TimeZone
$offsetVN = [TimeSpan]::FromHours(7)
$triggers = foreach ($vt in $VietnamTimes) {
    if ($vt -notmatch '^([01]\d|2[0-3]):[0-5]\d$') { throw "Bad time '$vt' (HH:mm, Vietnam time)" }
    $vnTime = [datetime]::ParseExact($vt, 'HH:mm', $null)
    $local = $vnTime - $offsetVN + $tz.BaseUtcOffset
    if ($local.Date -ne $vnTime.Date) { throw "Vietnam time $vt falls on another local day in timezone $($tz.Id); choose times that map to the same day." }
    if ($tz.BaseUtcOffset -ne $offsetVN) { Write-Warning "Machine timezone $($tz.Id) is not UTC+7: $vt (VN) -> $($local.ToString('HH:mm')) local." }
    New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $local
}
$taskArgs = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$runner`" -IfNeeded -Trigger SCHEDULER"
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $taskArgs -WorkingDirectory $Root
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15) -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$desc = "MarketLab VN30 EOD sync (Run-MarketLab-EOD.ps1 -IfNeeded). Installed $(Get-Date -Format s) from $Root. Vietnam times: $($VietnamTimes -join ', ')."
$task = New-ScheduledTask -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description $desc
$task.Settings.Enabled = $false
Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -InputObject $task -Force | Out-Null
Disable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null
Write-Host "Installed '$TaskPath$TaskName' DISABLED. After a manual SUCCESS run, enable with -Enable." -ForegroundColor Yellow
Show-MLTask
