# The daily error-report pass, run by Claude Code with nobody watching.
#
#   powershell -File tools/daily_triage.ps1             run it now
#   powershell -File tools/daily_triage.ps1 -Register   run it every day at 08:47
#   Unregister-ScheduledTask -TaskName "Jarvis daily error triage"   stop it
#
# What it is asked to do is tools/daily_triage_prompt.md. What it did is in
# GUI_logs/error_reports/TRIAGE.md (the pass it adds), CHANGELOG.md, and the
# run log in %LOCALAPPDATA%\JarvisTriage. It never commits.
param([switch]$Register, [string]$At = "08:47")
$ErrorActionPreference = "Stop"
$name = "Jarvis daily error triage"

if ($Register) {
  $act = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $PSCommandPath + '"')
  $when = New-ScheduledTaskTrigger -Daily -At $At
  # A morning the computer was off runs when it is next on, not never.
  $how = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)
  Register-ScheduledTask -TaskName $name -Action $act -Trigger $when -Settings $how `
    -Description "Claude Code reads Jarvis's end-of-day error reports, fixes what it can and notes the rest in GUI_logs/error_reports/TRIAGE.md. Never commits." `
    -Force | Out-Null
  Get-ScheduledTask -TaskName $name | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
  exit 0
}

$app = Split-Path -Parent $PSScriptRoot           # BARRY GUI
$repo = Split-Path -Parent $app                   # jeremystats: where the memory is keyed
$logs = Join-Path $env:LOCALAPPDATA "JarvisTriage"
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs ((Get-Date -Format "yyyy-MM-dd_HHmm") + ".log")

# The CLI ships inside the VS Code extension, in a folder named for its
# version, so the newest is found each run rather than written down.
$exe = Get-ChildItem "$env:USERPROFILE\.vscode\extensions" -Directory -Filter "anthropic.claude-code-*" |
  Sort-Object { [version](($_.Name -replace '^anthropic\.claude-code-', '') -replace '-[a-z0-9]+-[a-z0-9]+$', '') } |
  ForEach-Object { Join-Path $_.FullName "resources\native-binary\claude.exe" } |
  Where-Object { Test-Path $_ } | Select-Object -Last 1
if (-not $exe) { "no claude.exe under the VS Code extensions" | Out-File $log -Encoding utf8; exit 1 }

$prompt = Get-Content (Join-Path $PSScriptRoot "daily_triage_prompt.md") -Raw -Encoding UTF8
Set-Location $repo
"started $(Get-Date -Format s) with $exe" | Out-File $log -Encoding utf8
$prompt | & $exe -p --permission-mode auto --disallowedTools "Agent" "Workflow" --output-format text 2>&1 |
  Out-File $log -Append -Encoding utf8
"finished $(Get-Date -Format s), exit $LASTEXITCODE" | Out-File $log -Append -Encoding utf8
