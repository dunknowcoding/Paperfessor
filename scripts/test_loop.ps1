<#
.SYNOPSIS
    Paperfessor 3-min test loop.

.DESCRIPTION
    The user spec (req.txt) says: "every 3 minutes check its
    performance, if any problem arises, fix it in time, repeatedly
    test until a paper that meets the requirements is produced."
    This script runs the end-to-end pipeline (3-agent society: PhD
    + MS + UG), then waits 3 minutes, then diffs the workspace
    against the previous run to surface any regressions. Repeats
    until the script is killed (Ctrl+C) or the run produces a
    paper.pdf that passes the visual inspector.

    The pipeline invokes:
      - PhD (PhDStudent): plan, dispatch, supervise, write, archive
      - MS  (MasterStudent): real search across arXiv / OpenAlex /
        Google Scholar / Semantic Scholar; read full text; extract
        evidence; write to research_log.md
      - UG  (Undergraduate): download + preprocess datasets; run
        Python experiments; write to code_log.md

    Both the MS and UG log every report to their respective
    ``shared/{research,code}_log.md`` files. The pipeline records
    the LLM token usage into the PhD's doc_memo and the visual
    inspect into article_memo. After the pipeline finishes, the
    loop inspects:
      - paper.pdf / paper.md / paper.tex (paper artifacts)
      - doc_memo.md / article_memo.md (PhD memory)
      - shared/research_log.md / shared/code_log.md (worker logs)
      - workspace/archived/<slug>/<run_id>/ (archive)
      - the Article 19 visual inspect.

.PARAMETER Direction
    Research direction. Default: anomaly detection in time series.

.PARAMETER MaxIterations
    Stop after this many iterations (default 0 = forever).

.PARAMETER VisualGate
    If set, exit 0 when visual inspect reports "overall: PASS".
#>

param(
    [string]$Direction = "anomaly detection in time series",
    [int]$MaxIterations = 0,
    [switch]$VisualGate
)

if (-not $PSBoundParameters.ContainsKey("VisualGate")) {
    $VisualGate = $true
}

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$Workspace   = Join-Path $ProjectRoot "workspace"
$LogsDir     = Join-Path $ProjectRoot "logs\test_loop"
$LatestDir   = Join-Path $LogsDir "latest"
$PrevDir     = Join-Path $LogsDir "prev"
$StdOutPath  = Join-Path $LogsDir "stdout.txt"
$StdErrPath  = Join-Path $LogsDir "stderr.txt"

function Save-WorkspaceSnapshot {
    # Copy the most recent run's artifacts to a stable location so
    # the next iteration can diff against it.
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
    if (Test-Path $LatestDir) {
        if (Test-Path $PrevDir) {
            & "$env:USERPROFILE\.mavis\bin\mavis-trash.cmd" $PrevDir 2>$null
        }
        Rename-Item -Path $LatestDir -NewName "prev" -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $LatestDir -Force | Out-Null
    if (Test-Path $Workspace) {
        Get-ChildItem -Path $Workspace -Recurse -Force |
            Where-Object { -not $_.PSIsContainer } |
            ForEach-Object {
                $rel = $_.FullName.Substring($Workspace.Length).TrimStart("\", "/")
                $dest = Join-Path $LatestDir $rel
                New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
                Copy-Item -Path $_.FullName -Destination $dest -Force
            }
    }
}

function Test-Pipeline {
    # Clear workspace except the memory DB (which is per-archive, not per-run).
    $keep = @("memory.sqlite3")
    if (Test-Path $Workspace) {
        Get-ChildItem -Path $Workspace -Force | Where-Object {
            $keep -notcontains $_.Name
        } | ForEach-Object {
            & "$env:USERPROFILE\.mavis\bin\mavis-trash.cmd" $_.FullName 2>$null
        }
    }
    # Run the pipeline. The conda env name is fixed (IronEngineWorld).
    # The 3-agent society: PhD plans, MS surveys, UG codes. The
    # PhD supervises both via the active-review thread.
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUTF8       = "1"
    $env:PAPERFESSOR_LLM_MIN_GAP_MS = "1500"
    $start = Get-Date
    # Use paperfessor entry-point (installed via pip install -e .) so
    # the 3-agent PhD / MasterStudent / Undergraduate classes are loaded
    # by the CLI app.
    & conda run -n IronEngineWorld paperfessor run "$Direction" -V `
        1>$StdOutPath `
        2>$StdErrPath
    $code = $LASTEXITCODE
    $elapsed = (Get-Date) - $start
    Write-Host "pipeline elapsed: $($elapsed.TotalSeconds.ToString('0.0'))s"
    return $code
}

function Test-Artifacts {
    $paper = Join-Path $Workspace "paper\body\paper.pdf"
    $md    = Join-Path $Workspace "paper\body\paper.md"
    $tex   = Join-Path $Workspace "paper\body\paper.tex"
    $docMemo = Join-Path $Workspace "doc_memo.md"
    $articleMemo = Join-Path $Workspace "article_memo.md"
    $surveyLog = Join-Path $Workspace "shared\research_log.md"
    $codeLog  = Join-Path $Workspace "shared\code_log.md"
    $ok = $true
    $report = @()
    foreach ($f in @($paper, $md, $tex, $docMemo, $articleMemo, $surveyLog, $codeLog)) {
        if (Test-Path $f) {
            $sz = (Get-Item $f).Length
            $report += "OK   $f  ($sz bytes)"
        } else {
            $ok = $false
            $report += "MISS $f"
        }
    }
    return @{ ok = $ok; report = $report }
}

function Test-VisualInspect {
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUTF8       = "1"
    $py = @"
import sys
sys.path.insert(0, r'$ProjectRoot\src')
from src.research.visual_inspect import inspect_pdf, overall_exit_code
from pathlib import Path
pdf = Path(r'$Workspace\paper\body\paper.pdf')
if not pdf.exists():
    print('overall: MISS')
    sys.exit(0)
checks = inspect_pdf(pdf)
ok = all(c.passed for c in checks)
print('overall: ' + ('PASS' if ok else 'FAIL') + '  pages: ' + str(len(checks)))
for c in checks:
    print('  page', c.page_num, 'font=(', round(c.font_min, 1), round(c.font_median, 1), round(c.font_max, 1), ')pt',
          'density=', round(c.text_density, 2), 'overlaps=', c.overlap_count, 'margins=', c.margin_violation_count)
"@
    $tmp = New-TemporaryFile
    $py | Out-File -FilePath $tmp.FullName -Encoding utf8
    $out = & conda run -n IronEngineWorld python -u $tmp.FullName 2>&1
    Remove-Item $tmp.FullName -Force -ErrorAction SilentlyContinue
    return ($out -join "`n")
}

function Compare-PreviousSnapshot {
    # If we have a previous snapshot, surface regressions.
    if (-not (Test-Path $PrevDir)) { return $null }
    $cmd = "Compare-Object -ReferenceObject " +
           "(Get-ChildItem -Recurse -File $PrevDir | Select-Object -ExpandProperty FullName) " +
           "-DifferenceObject (Get-ChildItem -Recurse -File $Workspace -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)"
    $diff = & PowerShell -NoProfile -Command $cmd 2>$null
    if ($diff) { return $diff }
    return $null
}

$iteration = 0
while ($true) {
    $iteration++
    Write-Host ""
    Write-Host "================ iteration $iteration ================"
    Write-Host (Get-Date -Format "yyyy-MM-dd HH:mm:ss") "  direction: $Direction"
    Write-Host "3-agent pipeline: PhD + MS (MasterStudent) + UG (Undergraduate)"
    Write-Host "Running paperfessor run..."
    $code = Test-Pipeline
    Write-Host "paperfessor run exit code: $code"
    $art = Test-Artifacts
    Write-Host "artifacts:"
    $art.report | ForEach-Object { Write-Host "  $_" }
    $visual = Test-VisualInspect
    Write-Host "visual inspect:"
    $visual.Split("`n") | ForEach-Object { if ($_ -ne "") { Write-Host "  $_" } }
    # Snapshot this run so the next iteration can diff against it.
    Save-WorkspaceSnapshot
    $diff = Compare-PreviousSnapshot
    if ($diff) {
        Write-Host "regressions vs previous run:"
        $diff | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
    }
    if ($VisualGate -and $visual -match "overall: PASS") {
        Write-Host ""
        Write-Host "================ visual inspect PASSED ================"
        Write-Host "stopping test loop"
        exit 0
    }
    if ($MaxIterations -gt 0 -and $iteration -ge $MaxIterations) {
        Write-Host "reached MaxIterations=$MaxIterations; stopping"
        exit 0
    }
    Write-Host "sleeping 3 min (Ctrl+C to stop)..."
    Start-Sleep -Seconds 180
}
