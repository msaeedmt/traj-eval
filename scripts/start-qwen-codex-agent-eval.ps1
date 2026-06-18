param(
    [switch] $SkipRepoGuard,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CodexArgs
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ScienceRoot = "C:\Users\Anwender\Science-Work-Flow-"
$CodexHome = "C:\Users\Anwender\.codex-qwen-agent-eval"
$EnvFile = Join-Path $ScienceRoot "configs\cmbagent_eval\provider.local.env"
$ExpectedRemote = "git@github.com:msaeedmt/traj-eval.git"
$PreferredCodexBins = @(
    $env:QWEN_CODEX_BIN,
    "/mnt/c/Dev/src/github.com/openai/codex/codex-rs/target/release/codex",
    "/mnt/c/Dev/src/github.com/openai/codex/codex-rs/target/debug/codex",
    "C:\Dev\src\github.com\openai\codex\codex-rs\target\release\codex.exe",
    "C:\Dev\src\github.com\openai\codex\codex-rs\target\debug\codex.exe",
    "C:\Users\Anwender\.vscode\extensions\openai.chatgpt-26.609.30741-win32-x64\bin\windows-x86_64\codex.exe"
) | Where-Object { $_ }

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
    function Test-WslExecutable {
        param([Parameter(Mandatory = $true)][string] $Path)

        $safePath = $Path.Replace("'", "'\\''")
        $probe = wsl -e bash -lc "if [ -x '$safePath' ]; then echo found; else exit 1; fi"
        return ($LASTEXITCODE -eq 0 -and $probe.Trim() -eq "found")
    }

    foreach ($candidate in $PreferredCodexBins) {
        if ($candidate -like "/mnt/*") {
            if (Test-WslExecutable $candidate) {
                Write-Host "Using WSL Codex binary: $candidate"
                return "wsl:$candidate"
            }
            continue
        }
        if (Test-Path -LiteralPath $candidate) {
            Write-Host "Using Codex binary: $candidate"
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    $cmd = Get-Command codex -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "Using PATH Codex binary: $($cmd.Source)"
        return $cmd.Source
    }

    throw "No Codex binary found. Set QWEN_CODEX_BIN or build/install Codex first."
}

if (-not $SkipRepoGuard) {
    $branch = (& git -C $RepoRoot branch --show-current).Trim()
    if ($branch -ne "Han") {
        throw "traj-eval Qwen launcher expected branch Han, found '$branch'. Use -SkipRepoGuard only if intentional."
    }

    $origin = (& git -C $RepoRoot remote get-url origin).Trim()
    if ($origin -ne $ExpectedRemote) {
        throw "traj-eval Qwen launcher expected origin $ExpectedRemote, found '$origin'."
    }
}

Import-AgentEvalEnv -Path $EnvFile
$env:CODEX_HOME = $CodexHome
$env:OPENAI_BASE_URL = $env:OPENAI_BASE_URL
$env:OPENAI_API_BASE = $env:OPENAI_API_BASE
$env:TRAJ_EVAL_MODEL = $env:CMBAGENT_EVAL_LOCAL_MODEL

Set-Location -LiteralPath $RepoRoot

$codex = Resolve-CodexBinary
if ($codex -like "wsl:*") {
    $wslCodex = $codex.Substring(4)
    wsl -e $wslCodex @CodexArgs
    exit $LASTEXITCODE
}

& $codex @CodexArgs
exit $LASTEXITCODE
