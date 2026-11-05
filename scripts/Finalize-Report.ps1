<#
.SYNOPSIS
  Let Microsoft Word compute the table of contents, list of figures and list of tables of
  report\final\MarketLabVN30_FINAL.docx, save it, and export report\final\MarketLabVN30_FINAL.pdf.
.DESCRIPTION
  Run after: uv run --with python-docx --with pillow python scripts\build_final_report.py
  Requires Microsoft Word (COM). Two separate Word sessions:
    1. open, update the three TOC fields twice (page numbers shift after the lists fill), repaginate, save, quit;
    2. in a child powershell.exe, open the saved file read-only and SaveAs2 PDF to %TEMP%, then copy it in.
  Exporting in the same session that had just updated the fields re-laid out the document repeatedly and did not
  finish within 20 minutes on this machine; a fresh session exports in a few seconds. Steps go to var\logs\finalize_report.log.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$docx = Join-Path $Root 'report\final\MarketLabVN30_FINAL.docx'
$pdf = Join-Path $Root 'report\final\MarketLabVN30_FINAL.pdf'
New-Item -ItemType Directory -Force (Join-Path $Root 'var\logs') | Out-Null
$log = Join-Path $Root 'var\logs\finalize_report.log'
function Step($m) { $line = "{0} {1}" -f (Get-Date -Format 'HH:mm:ss'), $m; Add-Content $log $line -Encoding utf8; Write-Host $line }

function New-Word {
    $w = New-Object -ComObject Word.Application
    $w.Visible = $false
    $w.DisplayAlerts = 0
    $w.Options.CheckGrammarAsYouType = $false
    $w.Options.CheckSpellingAsYouType = $false
    $w.Options.UpdateFieldsAtPrint = $false
    $w.Options.UpdateLinksAtPrint = $false
    return $w
}

Step "start (session 1: update fields)"
$word = New-Word
try {
    $doc = $word.Documents.Open($docx, $false, $false, $false)
    for ($pass = 1; $pass -le 2; $pass++) {
        $i = 0
        foreach ($toc in $doc.TablesOfContents) { $i++; $toc.Update() }
        $doc.Repaginate()
        Step "pass $pass : $i TOC fields updated, repaginated"
    }
    $pages = $doc.ComputeStatistics(2)   # wdStatisticPages
    $doc.Save()
    Step "saved docx, pages=$pages"
    $doc.Close($false)
} finally {
    $word.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}

Step "session 2: export PDF (separate powershell.exe, local temp target, then copy)"
# Exporting from this process / straight onto the project drive hung on this machine; a child process that opens
# the saved file read-only and writes the PDF under %TEMP% finishes in about 6 s.
$tmpPdf = Join-Path $env:TEMP ('MarketLabVN30_FINAL_{0}.pdf' -f $PID)
$child = Join-Path $env:TEMP ('marketlab_export_{0}.ps1' -f $PID)
@"
`$w = New-Object -ComObject Word.Application; `$w.Visible = `$false; `$w.DisplayAlerts = 0
`$w.Options.UpdateFieldsAtPrint = `$false
try { `$d = `$w.Documents.Open('$docx', `$false, `$true); `$d.SaveAs2('$tmpPdf', 17); `$d.Close(`$false) } finally { `$w.Quit() }
"@ | Set-Content -Path $child -Encoding utf8
$p = Start-Process powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $child -PassThru -WindowStyle Hidden
if (-not $p.WaitForExit(180000)) { $p.Kill(); throw "PDF export did not finish within 180 s" }
if (-not (Test-Path $tmpPdf)) { throw "PDF export produced no file (exit $($p.ExitCode))" }
Copy-Item $tmpPdf $pdf -Force
Remove-Item $tmpPdf, $child -ErrorAction SilentlyContinue
Step "pdf exported -> $pdf"
Write-Host "OK pages=$pages docx=$docx pdf=$pdf"
