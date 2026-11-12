# The weekly email: the last 7 days' work, printed and sent to the lab.
#
#   powershell -File tools/weekly_email.ps1                   send it now (the lab list)
#   powershell -File tools/weekly_email.ps1 -Test             send it now (the test list)
#   powershell -File tools/weekly_email.ps1 -Register         every Friday at 15:00
#   powershell -File tools/weekly_email.ps1 -Register -Day Monday -At 08:30
#   Unregister-ScheduledTask -TaskName "Jarvis weekly email"   stop it
#
# What it does is tools/weekly_email.py. Who it goes to, and where the mailer
# is, are in %LOCALAPPDATA%\Jarvis\weekly\mail.json on this computer only.
# What happened is in %LOCALAPPDATA%\Jarvis\weekly\email.log. It never commits.
param([switch]$Register, [switch]$Test, [string]$Day = "Friday", [string]$At = "15:00")
$ErrorActionPreference = "Stop"
$name = "Jarvis weekly email"
$app = Split-Path -Parent $PSScriptRoot           # _Jarvis\app
$cfg = Join-Path $env:LOCALAPPDATA "Jarvis\weekly\mail.json"

if ($Register) {
  $act = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $PSCommandPath + '"')
  $when = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $At
  # A week the computer was off at the time sends when it is next on, not never.
  $how = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
  Register-ScheduledTask -TaskName $name -Action $act -Trigger $when -Settings $how `
    -Description "Prints Inside Jarvis's 'Last 7 days' work' and emails it to the lab from barrylabuvm@gmail.com (tools/weekly_email.py). Never commits." `
    -Force | Out-Null
  # Said on the printer in Jarvis, so people know it is coming.
  if (Test-Path $cfg) {
    $j = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
    $t = [datetime]::ParseExact($At, "HH:mm", $null).ToString("h:mm tt")
    $j | Add-Member -NotePropertyName schedule -NotePropertyValue ("$($Day)s at $t") -Force
    [System.IO.File]::WriteAllText($cfg, ($j | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding $false))
  }
  Get-ScheduledTask -TaskName $name | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
  exit 0
}

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
$args_ = @((Join-Path $PSScriptRoot "weekly_email.py"))
if ($Test) { $args_ += "--test" }
Set-Location $app
& $py @args_
exit $LASTEXITCODE
