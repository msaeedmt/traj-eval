param(
    [switch] $SkipRepoGuard,
    [string] $ProviderEnv = $env:TRAJ_EVAL_PROVIDER_ENV,
    [string] $CodexHome = $env:QWEN_CODEX_HOME,
    [string] $CodexBin = $env:QWEN_CODEX_BIN,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CodexArgs
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $CodexHome) {
    $userProfile = [Environment]::GetFolderPath(
        [Environment+SpecialFolder]::UserProfile
    )
    if (-not $userProfile) {
        throw "Unable to derive a user profile for Qwen CODEX_HOME."
    }
    $CodexHome = Join-Path $userProfile ".codex-qwen-agent-eval"
}
elseif (-not [System.IO.Path]::IsPathRooted($CodexHome)) {
    $CodexHome = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $CodexHome))
}

function Import-AgentEvalEnv {
    param([Parameter(Mandatory = $true)][string] $Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing Qwen provider env file: $Path"
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $text = $line.Trim()
        if (-not $text -or $text.StartsWith("#") -or -not $text.Contains("=")) {
            continue
        }

        $key, $value = $text.Split("=", 2)
        $key = $key.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($key) {
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}

function Resolve-CodexBinary {
    param([string] $Candidate)

    if ($Candidate) {
        if ($Candidate -like "wsl:*" -or $Candidate -like "/mnt/*") {
            throw "This Windows launcher requires a Windows Codex executable. WSL execution is intentionally unsupported because it cannot share the isolated Windows provider and CODEX_HOME contract safely."
        }
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            Write-Host "Using Codex binary: $Candidate"
            return (Resolve-Path -LiteralPath $Candidate).Path
        }
        $configured = Get-Command $Candidate -CommandType Application -ErrorAction SilentlyContinue
        if ($configured) {
            Write-Host "Using configured Codex command: $($configured.Source)"
            return $configured.Source
        }
        throw "Configured Codex binary was not found: $Candidate"
    }

    $cmd = Get-Command codex -CommandType Application -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "Using PATH Codex binary: $($cmd.Source)"
        return $cmd.Source
    }

    throw "No Codex binary found. Pass -CodexBin, set QWEN_CODEX_BIN, or add codex to PATH."
}

if (-not $SkipRepoGuard) {
    $branch = (& git -C $RepoRoot branch --show-current).Trim()
    if ($branch -ne "Han") {
        throw "traj-eval Qwen launcher expected branch Han, found '$branch'. Use -SkipRepoGuard only if intentional."
    }
}

if (-not $ProviderEnv) {
    throw "Pass -ProviderEnv or set TRAJ_EVAL_PROVIDER_ENV."
}
$providerPath = $ProviderEnv
if (-not [System.IO.Path]::IsPathRooted($providerPath)) {
    $providerPath = Join-Path $RepoRoot $providerPath
}
Import-AgentEvalEnv -Path $providerPath
$env:CODEX_HOME = $CodexHome
if ($env:CMBAGENT_EVAL_LOCAL_MODEL) {
    $env:TRAJ_EVAL_MODEL = $env:CMBAGENT_EVAL_LOCAL_MODEL
}
if (-not $env:TRAJ_EVAL_MODEL) {
    throw "Provider configuration must set TRAJ_EVAL_MODEL or CMBAGENT_EVAL_LOCAL_MODEL."
}

Set-Location -LiteralPath $RepoRoot

$codex = Resolve-CodexBinary -Candidate $CodexBin
& $codex @CodexArgs
exit $LASTEXITCODE
