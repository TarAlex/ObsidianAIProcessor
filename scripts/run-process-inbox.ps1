<#
.SYNOPSIS
    Run obsidian-agent process-inbox once; append stdout/stderr to a vault log file.

.PARAMETER ConfigPath
    Full path to _AI_META/agent-config.yaml
.PARAMETER PythonExe
    Optional path to python.exe (default: python on PATH)
#>
param(
    [Parameter(Mandatory = $true)]
    [string] $ConfigPath,

    [string] $PythonExe = ""
)

$ErrorActionPreference = "Stop"
$cfg = (Resolve-Path -LiteralPath $ConfigPath).Path
$aiMeta = Split-Path $cfg
$log = Join-Path $aiMeta "process-inbox-scheduler.log"

if ($PythonExe) {
    $py = (Resolve-Path -LiteralPath $PythonExe).Path
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "python not on PATH; pass -PythonExe" }
    $py = $cmd.Source
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -LiteralPath $log -Value "`n===== $stamp =====`n"
& $py -m agent process-inbox --config $cfg *>> $log
exit $LASTEXITCODE
