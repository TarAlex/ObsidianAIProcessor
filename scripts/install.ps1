# Install obsidian-agent from GitHub and bootstrap the current folder as vault.
# Run: irm https://raw.githubusercontent.com/TarAlex/ObsidianAIProcessor/master/scripts/install.ps1 | iex
# Or:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 [-Vault path] [-Local]

param(
    [string] $Vault = (Get-Location).Path,
    [switch] $Local
)

$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:OBSIDIAN_AGENT_REPO_URL) { $env:OBSIDIAN_AGENT_REPO_URL } else { "https://github.com/TarAlex/ObsidianAIProcessor.git" }
$GitRef = if ($env:OBSIDIAN_AGENT_GIT_REF) { $env:OBSIDIAN_AGENT_GIT_REF } else { "master" }
$ChatModel = if ($env:OLLAMA_CHAT_MODEL) { $env:OLLAMA_CHAT_MODEL } else { "llama3.1:8b" }
$EmbedModel = if ($env:OLLAMA_EMBED_MODEL) { $env:OLLAMA_EMBED_MODEL } else { "nomic-embed-text" }
$OllamaUrl = if ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL } else { "http://127.0.0.1:11434" }

$VersionCheck = "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"

function Test-PythonExe {
    param([string] $ExePath)
    if (-not (Test-Path -LiteralPath $ExePath)) { return $false }
    $old = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $ExePath -c $VersionCheck 2>$null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $old
    }
}

function Test-PythonCommand {
    param([string[]] $Prefix)
    if ($Prefix.Count -lt 1) { return $false }
    $old = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        if ($Prefix.Count -eq 1) {
            & $Prefix[0] -c $VersionCheck 2>$null
        } else {
            & $Prefix[0] @($Prefix[1..($Prefix.Length - 1)] + @("-c", $VersionCheck)) 2>$null
        }
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $old
    }
}

# Resolve PyPrefix: string[] where [0] is exe path OR launcher name, rest are launcher args.
# Prefer real python.exe paths from "py -0p" so we never hit a broken default (e.g. PY_PYTHON=3.11).
$PyPrefix = $null

if (Get-Command py -ErrorAction SilentlyContinue) {
    $list = & py -0p 2>&1 | ForEach-Object { $_.ToString() }
    if ($LASTEXITCODE -eq 0 -and $list) {
        $best = $null
        foreach ($line in $list) {
            $t = $line.Trim()
            if ($t -notmatch '-V:(\d+)\.(\d+)(?:\s+\*)?\s+(.+)$') { continue }
            $maj = [int]$Matches[1]
            $min = [int]$Matches[2]
            $exe = $Matches[3].Trim()
            if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 11)) { continue }
            if ($exe -notmatch '\.exe$') { continue }
            if (Test-PythonExe $exe) {
                $tuple = ($maj * 1000) + $min
                if ($null -eq $best -or $tuple -gt $best.Tuple) {
                    $best = @{ Tuple = $tuple; Exe = $exe }
                }
            }
        }
        if ($null -ne $best) {
            $PyPrefix = @($best.Exe)
            Write-Host "[install] Using $($best.Exe) (Python 3.11+ via py -0p)"
        }
    }
}

if ($null -eq $PyPrefix) {
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        # Skip when `python` is the launcher binary (often tied to a missing 3.11 tag).
        if ($cmd.Name -ieq "py.exe" -or $cmd.Source -match '[\\/]py\.exe$') { continue }
        if (Test-PythonCommand @($name)) {
            $PyPrefix = @($name)
            Write-Host "[install] Using $name (Python 3.11+)"
            break
        }
    }
}

if ($null -eq $PyPrefix -and (Get-Command py -ErrorAction SilentlyContinue)) {
    if (Test-PythonCommand @("py", "-3")) {
        $PyPrefix = @("py", "-3")
        Write-Host "[install] Using py -3 (Python 3.11+)"
    }
}

if ($null -eq $PyPrefix) {
    Write-Error "Python 3.11 or newer not found. Install from https://www.python.org/downloads/ or run: py -0p"
}

function Invoke-Py {
    param([Parameter(Mandatory = $true)][string[]] $ArgumentList)
    if ($PyPrefix.Count -eq 1) {
        & $PyPrefix[0] @ArgumentList
    } else {
        & $PyPrefix[0] @($PyPrefix[1..($PyPrefix.Length - 1)] + $ArgumentList)
    }
}

if ($Local) {
    if (-not $PSScriptRoot) {
        Write-Error "-Local requires running this script from disk (not via piped iex)."
    }
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Write-Host "[install] pip install --upgrade -e $Root"
    Invoke-Py -ArgumentList @("-m", "pip", "install", "--upgrade", "-e", $Root)
} else {
    $spec = "git+${RepoUrl}@${GitRef}"
    Write-Host "[install] pip install --upgrade $spec"
    Invoke-Py -ArgumentList @("-m", "pip", "install", "--upgrade", $spec)
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Warning "ollama not on PATH. Install from https://ollama.com then: ollama pull $ChatModel; ollama pull $EmbedModel"
} else {
    Write-Host "[install] ollama pull $ChatModel"
    ollama pull $ChatModel
    Write-Host "[install] ollama pull $EmbedModel"
    ollama pull $EmbedModel
}

$VaultAbs = (Resolve-Path -LiteralPath $Vault).Path
$Cfg = Join-Path $VaultAbs "_AI_META\agent-config.yaml"

Write-Host "[install] configure $VaultAbs"
Invoke-Py -ArgumentList @(
    "-m", "agent", "configure", "--non-interactive",
    "--vault", $VaultAbs,
    "--config", $Cfg,
    "--provider", "ollama",
    "--ollama-url", $OllamaUrl,
    "--ollama-model", $ChatModel,
    "--embedding-model", $EmbedModel
)

Write-Host "[install] copy default templates to _AI_META/templates"
$prevWd = Get-Location
try {
    Set-Location ([System.IO.Path]::GetTempPath())
    Invoke-Py -ArgumentList @("-m", "agent", "seed-templates", $VaultAbs)
    if ($LASTEXITCODE -ne 0) {
        Write-Error "seed-templates failed (exit $LASTEXITCODE). Try: pip install --upgrade git+${RepoUrl}@${GitRef}"
        exit $LASTEXITCODE
    }
} finally {
    Set-Location $prevWd
}

Write-Host "[install] setup-vault"
Invoke-Py -ArgumentList @("-m", "agent", "setup-vault", "--config", $Cfg)

Write-Host "[install] Done. Run: cd `"$VaultAbs`"; obsidian-agent run"
if ($PyPrefix.Count -eq 1) {
    Write-Host "         or: `"$($PyPrefix[0])`" -m agent run --config `"$Cfg`""
} else {
    Write-Host "         or: $($PyPrefix -join ' ') -m agent run --config `"$Cfg`""
}
Write-Host "[install] Periodic inbox (Windows): scripts/schedule-inbox-windows.ps1 -Install -VaultRoot `"$VaultAbs`""
Write-Host "[install] Periodic inbox (Linux/macOS): see scripts/schedule-inbox-linux.example.sh"
