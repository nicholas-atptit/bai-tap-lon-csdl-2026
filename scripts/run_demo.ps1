param([string]$Server='.')
$ErrorActionPreference='Stop'
$projectPath=Split-Path -Parent $PSScriptRoot
$evidencePath=Join-Path $projectPath ('tests\evidence\manual_live_'+(Get-Date -Format 'yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Path $evidencePath -ErrorAction Stop | Out-Null
foreach($item in @('all_in_one','10_preflight_live','09_live_demo','07_business_queries','08_validation_tests')) {
    $scriptPath=Join-Path $projectPath "sql\$item.sql"
    $logPath=Join-Path $evidencePath "manual_$item.log"
    & sqlcmd -S $Server -E -C -No -b -f 65001 -W -s '|' -i $scriptPath -o $logPath
    if($LASTEXITCODE -ne 0) { throw "SQL failed: $scriptPath. Read $logPath" }
}
Write-Output "PASS: deployment, preflight, five-part live demo, 16 business queries and 44 controlled tests. Evidence: $evidencePath"
