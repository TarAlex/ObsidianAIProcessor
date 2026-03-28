# Install obsidian-agent from GitHub and bootstrap the current folder as vault.
# Run: irm https://raw.githubusercontent.com/TarAlex/ObsidianAIProcessor/main/scripts/install.ps1 | iex
# Or:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 [-Vault path] [-Local]

param(
    [string] $Vault = (Get-Location).Path,
    [switch] $Local
)

$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:OBSIDIAN_AGENT_REPO_URL) { $env:OBSIDIAN_AGENT_REPO_URL } else { "https://github.com/TarAlex/ObsidianAIProcessor.git" }
$ChatModel = if ($env:OLLAMA_CHAT_MODEL) { $env:OLLAMA_CHAT_MODEL } else { "llama3.1:8b" }
$EmbedModel = if ($env:OLLAMA_EMBED_MODEL) { $env:OLLAMA_EMBED_MODEL } else { "nomic-embed-text" }
$OllamaUrl = if ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL } else { "http://127.0.0.1:11434" }

function Test-Python311 {
    param([string[]] $Prefix)
    $code = "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
    if ($Prefix.Count -lt 1) { return $false }
    if ($Prefix.Count -eq 1) {
        & $Prefix[0] -c $code 2>$null
    } else {
        & $Prefix[0] @($Prefix[1..($Prefix.Length - 1)] + @("-c", $code)) 2>$null
    }
    return ($LASTEXITCODE -eq 0)
}

$PyPrefix = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python311 @("py", "-3.11")) { $PyPrefix = @("py", "-3.11") }
}
if (-not $PyPrefix -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Python311 @("python")) { $PyPrefix = @("python") }
}
if (-not $PyPrefix) {
    Write-Error "Python 3.11+ not found. Install from https://www.python.org/downloads/"
}

function Invoke-Py {
    param([string[]] $Args)
    & $PyPrefix[0] @($PyPrefix[1..($PyPrefix.Length - 1)] + $Args)
}

if ($Local) {
    if (-not $PSScriptRoot) {
        Write-Error "-Local requires running this script from disk (not via piped iex)."
    }
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Write-Host "[install] pip install -e $Root"
    Invoke-Py @("-m", "pip", "install", "-e", $Root)
} else {
    $spec = "git+${RepoUrl}@main"
    Write-Host "[install] pip install $spec"
    Invoke-Py @("-m", "pip", "install", $spec)
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
Invoke-Py @(
    "-m", "agent", "configure", "--non-interactive",
    "--vault", $VaultAbs,
    "--config", $Cfg,
    "--provider", "ollama",
    "--ollama-url", $OllamaUrl,
    "--ollama-model", $ChatModel,
    "--embedding-model", $EmbedModel
)

Write-Host "[install] setup-vault"
Invoke-Py @("-m", "agent", "setup-vault", "--config", $Cfg)

Write-Host "[install] Done. Run: cd `"$VaultAbs`"; obsidian-agent run"
Write-Host "         or: $($PyPrefix -join ' ') -m agent run --config `"$Cfg`""
