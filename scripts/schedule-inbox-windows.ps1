<#
.SYNOPSIS
    Register or remove a Windows Scheduled Task that runs obsidian-agent process-inbox.

.DESCRIPTION
    Uses scripts/run-process-inbox.ps1 so quoting and logging stay reliable. Log file:
    VAULT\_AI_META\process-inbox-scheduler.log

.PARAMETER VaultRoot
    Absolute path to the Obsidian vault root (folder containing _AI_META).

.PARAMETER IntervalMinutes
    How often to run process-inbox (default: 15).

.PARAMETER TaskName
    Scheduled task name (default: ObsidianAgent-ProcessInbox).

.PARAMETER PythonExe
    Optional full path to python.exe for the scheduled task (stored in run-process-inbox.ps1 invocation).

.EXAMPLE
    .\schedule-inbox-windows.ps1 -VaultRoot "C:\Users\me\vault" -Install

.EXAMPLE
    .\schedule-inbox-windows.ps1 -VaultRoot "C:\Users\me\vault" -Uninstall
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $VaultRoot,

    [ValidateRange(1, 1439)]
    [int] $IntervalMinutes = 15,

    [string] $TaskName = "ObsidianAgent-ProcessInbox",

    [string] $PythonExe = "",

    [switch] $Install,
    [switch] $Uninstall,
    [switch] $RunOnce
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $here "run-process-inbox.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing runner script: $runner"
}

$vault = [System.IO.Path]::GetFullPath($VaultRoot)
$config = Join-Path $vault "_AI_META\agent-config.yaml"
if (-not (Test-Path -LiteralPath $config)) {
    throw "Config not found: $config (run obsidian-agent configure for this vault first)."
}

if ($RunOnce) {
    if ($PythonExe) {
        & $runner -ConfigPath $config -PythonExe $PythonExe
    } else {
        & $runner -ConfigPath $config
    }
    exit $LASTEXITCODE
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task: $TaskName"
    exit 0
}

if (-not $Install) {
    Write-Host "Specify -Install, -Uninstall, or -RunOnce. Get-Help .\schedule-inbox-windows.ps1 -Full"
    exit 1
}

$runnerFull = (Resolve-Path -LiteralPath $runner).Path
$configFull = (Resolve-Path -LiteralPath $config).Path

if ($PythonExe) {
    $pyFull = (Resolve-Path -LiteralPath $PythonExe).Path
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerFull`" -ConfigPath `"$configFull`" -PythonExe `"$pyFull`""
} else {
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerFull`" -ConfigPath `"$configFull`""
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
$start = (Get-Date).AddMinutes(1)
$repeat = New-TimeSpan -Minutes $IntervalMinutes
$duration = New-TimeSpan -Days 3650
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval $repeat -RepetitionDuration $duration
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "Registered task '$TaskName' every $IntervalMinutes min."
Write-Host "Log: $(Join-Path $vault '_AI_META\process-inbox-scheduler.log')"
