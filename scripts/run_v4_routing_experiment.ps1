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
    [string]$ProviderEnv = "C:\Dev\src\github.com\msaeedmt\traj-eval\configs\qwen.remote.local.env",
    [string]$LeanProject = "C:\Dev\src\github.com\msaeedmt\traj-eval\dataset\Lean",
    [string]$Python = "C:\Users\Anwender\AppData\Local\anaconda3\envs\pytorch-gpu\python.exe",
    [string]$OutputBase = "data\batch\version_4_routing_ablation\shell_runs",

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

function Write-NewUtf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Lines
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
    if ($LASTEXITCODE -ne 0 -or $branch -ne "Han-experiment") {
        throw "Run only from Han-experiment; current branch is '$branch'."
    }

    if (-not $PlanOnly) {
        $trackedStatus = @(& git status --porcelain --untracked-files=no)
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to inspect tracked Git state."
        }
        if ($trackedStatus.Count -ne 0) {
            throw "Tracked files are dirty. Commit or restore them before a live run."
        }
    }

    $pythonPath = Resolve-ExistingFile -Path $Python -Label "Python interpreter"
    $providerPath = Resolve-ExistingFile -Path $ProviderEnv -Label "Provider env file"
    $leanPath = Resolve-ExistingDirectory -Path $LeanProject -Label "Lean project"
    if (-not (Test-Path -LiteralPath (Join-Path $leanPath ".lake") -PathType Container)) {
        throw "Lean project has no .lake artifacts: $leanPath"
    }

    $outputBasePath = $OutputBase
    if (-not [System.IO.Path]::IsPathRooted($outputBasePath)) {
        $outputBasePath = Join-Path $repoRoot $outputBasePath
    }
    $outputRoot = [System.IO.Path]::GetFullPath((Join-Path $outputBasePath $RunId))
    if (Test-Path -LiteralPath $outputRoot) {
        throw "Refusing to reuse existing run directory: $outputRoot"
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
    Write-Host ("Output: {0}" -f $outputRoot)
    Write-Host ("Conservative maximum model calls: {0}" -f $maximumCalls)
    Write-Host "Provider credentials will be read by Python from the env file and will not be copied into run documentation."

    if ($PlanOnly) {
        Write-Host "Plan-only check passed; no provider call or output write occurred."
        return
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
        "- Conservative maximum model calls: $maximumCalls",
        "- Lean project: $leanPath",
        "- Provider configuration file: $providerPath (credentials not copied)",
        "",
        "## Output layout",
        "",
        "- logs/: one console log per executed stage",
        "- smoke/controller_stuck/: planner and Engineer stuck-routing probes",
        "- smoke/arm_smoke/: one matched trial per task and arm",
        "- <arm>/: official JSONL traces, summary.json, and RESULTS.md",
        "- analysis/: paired statistics and COMPARISON.md",
        "- run_manifest.json: machine-readable official-run manifest",
        "- COMPLETED.md or FAILED.md: terminal launcher status",
        "",
        "## Claim boundary",
        "",
        "This two-task, one-model experiment can identify routing burden, safety defects, and a promising recovery effect. It cannot establish overall NLP-proposal improvement without broader repeated tasks and a single-agent control."
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
            "- Inspect the per-arm RESULTS.md files and analysis/COMPARISON.md before making research claims."
        )
        Write-Host ""
        Write-Host ("Run completed. Evidence: {0}" -f $outputRoot)
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
