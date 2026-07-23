<#
.SYNOPSIS
Run the Han V4 Lean routing experiment from one PowerShell command.

.DESCRIPTION
Creates a new timestamped, append-only run directory and invokes the existing
Python experiment harness. The launcher never reads credentials into the
PowerShell environment and never reuses an existing output directory.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_v4_routing_experiment.ps1 -Stage smoke -ConfirmExternalProviderRisk

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_v4_routing_experiment.ps1 -Stage all -ConfirmExternalProviderRisk -ConfirmOfficial160
#>

[CmdletBinding()]
param(
    [ValidateSet("smoke", "official", "all")]
    [string]$Stage = "smoke",

    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]*$")]
    [string]$RunId = ("v4_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss")),

    [string]$Model = "openai/Qwen3.5-27B-Q5_K_M.gguf",
    [string]$ProviderEnv = $env:TRAJ_EVAL_PROVIDER_ENV,
    [string]$LeanProject = "dataset\Lean",
    [string]$Python = "python",
    [string]$OutputBase = "data\batch\version_4_routing_ablation\shell_runs",
    [string]$AnalysisBase = "data\analysis\version_4_routing_ablation",
    [string]$DocsBase = "docs\experiments\version_4_routing_ablation",

    [ValidateRange(1, 3600)]
    [int]$WorkerTimeoutSeconds = 180,

    [switch]$ConfirmExternalProviderRisk,
    [switch]$ConfirmOfficial160,
    [switch]$PlanOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Trials = 20
$MaxWorkerTurns = 200
$MaxTotalModelCalls = 200

function Resolve-ExistingFile {
    param([Parameter(Mandatory = $true)][string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label does not exist: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Resolve-ExistingDirectory {
    param([Parameter(Mandatory = $true)][string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Label does not exist: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Resolve-Executable {
    param([Parameter(Mandatory = $true)][string]$Command, [string]$Label)
    if (Test-Path -LiteralPath $Command -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Command).Path
    }
    $resolved = Get-Command $Command -CommandType Application -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "$Label was not found as a file or command: $Command"
    }
    return $resolved.Source
}

function Resolve-RunRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$RunId
    )
    $basePath = $Base
    if (-not [System.IO.Path]::IsPathRooted($basePath)) {
        $basePath = Join-Path $RepoRoot $basePath
    }
    return [System.IO.Path]::GetFullPath((Join-Path $basePath $RunId))
}

function Write-NewUtf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [AllowEmptyString()]
        [string[]]$Lines
    )
    if (Test-Path -LiteralPath $Path) {
        throw "Refusing to overwrite existing artifact: $Path"
    }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, $Lines, $encoding)
}

function Invoke-ExperimentStage {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$LogDirectory,
        [Parameter(Mandatory = $true)][string]$PythonPath
    )
    $logPath = Join-Path $LogDirectory ("{0}.log" -f $Name)
    if (Test-Path -LiteralPath $logPath) {
        throw "Refusing to overwrite existing stage log: $logPath"
    }
    Write-Host ""
    Write-Host ("=== {0} ===" -f $Name)
    Write-Host ("Log: {0}" -f $logPath)
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $PythonPath @Arguments *>&1 | Tee-Object -FilePath $logPath
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode. Evidence is preserved in $logPath"
    }
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne "Han") {
        throw "Run only from Han; current branch is '$branch'."
    }

    if (-not $PlanOnly) {
        $workingStatus = @(& git status --porcelain --untracked-files=all)
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to inspect complete Git working-tree state."
        }
        if ($workingStatus.Count -ne 0) {
            throw "Tracked or untracked files are present. Commit, archive, or restore them before a live run so HEAD fully identifies the inputs."
        }
    }

    $outputRoot = Resolve-RunRoot -Base $OutputBase -RepoRoot $repoRoot -RunId $RunId
    $analysisRoot = Resolve-RunRoot -Base $AnalysisBase -RepoRoot $repoRoot -RunId $RunId
    $docsRoot = Resolve-RunRoot -Base $DocsBase -RepoRoot $repoRoot -RunId $RunId
    $runRoots = @($outputRoot, $analysisRoot, $docsRoot)
    $rootSet = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($runRoot in $runRoots) {
        [void] $rootSet.Add(
            [System.IO.Path]::GetFullPath($runRoot).TrimEnd(
                [System.IO.Path]::DirectorySeparatorChar,
                [System.IO.Path]::AltDirectorySeparatorChar
            )
        )
    }
    if ($rootSet.Count -ne 3) {
        throw "Raw, analysis, and docs run roots must be distinct."
    }
    $existingRoots = @($runRoots | Where-Object { Test-Path -LiteralPath $_ })
    if ($existingRoots.Count -ne 0) {
        throw "Refusing to reuse existing run root(s): $($existingRoots -join ', ')"
    }

    $runsOfficial = $Stage -eq "official" -or $Stage -eq "all"
    if (-not $PlanOnly -and -not $ConfirmExternalProviderRisk) {
        throw "Live Qwen runs require -ConfirmExternalProviderRisk."
    }
    if (-not $PlanOnly -and $runsOfficial -and -not $ConfirmOfficial160) {
        throw "The official 160-slot study requires -ConfirmOfficial160."
    }

    $maximumCalls = switch ($Stage) {
        "smoke" { 4002 }
        "official" { 80000 }
        "all" { 84002 }
    }
    $head = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to resolve Git HEAD."
    }

    Write-Host "Han V4 routing experiment"
    Write-Host ("Stage: {0}" -f $Stage)
    Write-Host ("Run ID: {0}" -f $RunId)
    Write-Host ("Model: {0}" -f $Model)
    Write-Host ("Raw evidence: {0}" -f $outputRoot)
    Write-Host ("Derived analysis: {0}" -f $analysisRoot)
    Write-Host ("Human-readable docs: {0}" -f $docsRoot)
    Write-Host ("Conservative maximum model calls: {0}" -f $maximumCalls)
    Write-Host "Retrieval-only no-progress threshold: 8 completed Reasoner search_lemmas calls, evaluated after each tool-execution batch."

    if ($PlanOnly) {
        Write-Host "Plan-only check passed; no provider file was accessed and no output was written."
        return
    }

    if (-not $ProviderEnv) {
        throw "Live modes require -ProviderEnv or TRAJ_EVAL_PROVIDER_ENV."
    }
    $pythonPath = Resolve-Executable -Command $Python -Label "Python interpreter"
    $providerPath = Resolve-ExistingFile -Path $ProviderEnv -Label "Provider env file"
    $leanProjectPath = $LeanProject
    if (-not [System.IO.Path]::IsPathRooted($leanProjectPath)) {
        $leanProjectPath = Join-Path $repoRoot $leanProjectPath
    }
    $leanPath = Resolve-ExistingDirectory -Path $leanProjectPath -Label "Lean project"
    if (-not (Test-Path -LiteralPath (Join-Path $leanPath ".lake") -PathType Container)) {
        throw "Lean project has no .lake artifacts: $leanPath"
    }

    New-Item -ItemType Directory -Path $outputRoot | Out-Null
    $logDirectory = Join-Path $outputRoot "logs"
    New-Item -ItemType Directory -Path $logDirectory | Out-Null

    $runDocument = @(
        "# Han V4 Routing Ablation Run",
        "",
        "- Run ID: $RunId",
        "- Started: $((Get-Date).ToString('o'))",
        "- Git branch: $branch",
        "- Git commit: $head",
        "- Stage selection: $Stage",
        "- Model: $Model",
        "- Tasks: easy_fatem_019, easy_fatem_020",
        "- Arms: legacy_deterministic, upstream_free, central_worker_matched, central_total_call_matched",
        "- Official trials per task and arm: $Trials",
        "- Worker-turn cap: $MaxWorkerTurns",
        "- Total-call cap for the matched central arm: $MaxTotalModelCalls",
        "- Worker timeout seconds: $WorkerTimeoutSeconds",
        "- Provider-internal retries: 0",
        "- Recorded outer infrastructure retries: at most 1 per slot",
        "- Retrieval-only no-progress threshold: 8 completed Reasoner search_lemmas calls, evaluated after each tool-execution batch; a parallel batch may cross the threshold and is counted exactly",
        "- Conservative maximum model calls: $maximumCalls",
        "- Lean project: configured runtime validated against dataset/Lean (local path omitted)",
        "- Provider configuration: explicit env file (local path and credentials omitted)",
        "",
        "## Output layout",
        "",
        "- data/batch/.../$RunId/: raw JSONL traces, run manifest, logs, and terminal launcher status",
        "- data/batch/.../$RunId/smoke/controller_stuck/: Reasoner and Engineer stuck-routing probes",
        "- data/batch/.../$RunId/smoke/arm_smoke/: one matched raw trial per task and arm",
        "- data/analysis/.../$RunId/: reproducible JSON summaries and paired metrics",
        "- docs/experiments/.../$RunId/: human-readable RESULTS.md and COMPARISON.md",
        "",
        "## Claim boundary",
        "",
        "This pilot records descriptive routing, safety, and recovery observations for two selected tasks and one model. It does not establish an architecture-improvement claim."
    )
    Write-NewUtf8File -Path (Join-Path $outputRoot "RUN.md") -Lines $runDocument

    $env:PYTHONPATH = "src"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $common = @(
        "scripts\run_routing_ablation.py",
        "--model", $Model,
        "--provider-env", $providerPath,
        "--lean-project", $leanPath,
        "--output-dir", $outputRoot,
        "--analysis-dir", $analysisRoot,
        "--docs-dir", $docsRoot,
        "--worker-timeout-seconds", $WorkerTimeoutSeconds.ToString()
    )

    try {
        if ($Stage -eq "smoke" -or $Stage -eq "all") {
            Invoke-ExperimentStage -Name "01_controller_smoke" -PythonPath $pythonPath -LogDirectory $logDirectory -Arguments ($common + @("--mode", "controller-smoke"))
            Invoke-ExperimentStage -Name "02_arm_smoke" -PythonPath $pythonPath -LogDirectory $logDirectory -Arguments ($common + @(
                "--mode", "arm-smoke",
                "--max-worker-turns", $MaxWorkerTurns.ToString(),
                "--max-total-model-calls", $MaxTotalModelCalls.ToString()
            ))
        }
        if ($runsOfficial) {
            Invoke-ExperimentStage -Name "03_official_160" -PythonPath $pythonPath -LogDirectory $logDirectory -Arguments ($common + @(
                "--mode", "official",
                "--trials", $Trials.ToString(),
                "--max-worker-turns", $MaxWorkerTurns.ToString(),
                "--max-total-model-calls", $MaxTotalModelCalls.ToString()
            ))
        }

        Write-NewUtf8File -Path (Join-Path $outputRoot "COMPLETED.md") -Lines @(
            "# Run completed",
            "",
            "- Completed: $((Get-Date).ToString('o'))",
            "- Stage selection: $Stage",
            "- Inspect the matching docs/experiments routing bundle before making research claims."
        )
        Write-Host ""
        Write-Host ("Run completed. Raw evidence: {0}" -f $outputRoot)
        Write-Host ("Derived analysis: {0}" -f $analysisRoot)
        Write-Host ("Human-readable docs: {0}" -f $docsRoot)
    }
    catch {
        Write-NewUtf8File -Path (Join-Path $outputRoot "FAILED.md") -Lines @(
            "# Run failed",
            "",
            "- Failed: $((Get-Date).ToString('o'))",
            "- Stage selection: $Stage",
            "- Error: $($_.Exception.Message)",
            "- All partial traces and logs are intentionally preserved. Start a new run ID after diagnosing the failure."
        )
        throw
    }
}
finally {
    Pop-Location
}
