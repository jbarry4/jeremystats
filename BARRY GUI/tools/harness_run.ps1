# Run web/_dev harnesses against a server this script starts and stops.
#
#   powershell -File tools/harness_run.ps1 -Names rootcanalswitch,bounce
#
# The server has to live inside the same call: one started by Start-Process
# in an earlier tool call dies at the call boundary. Run from PowerShell, not
# Bash; under Bash, Edge dumps nothing and every harness reads as clean.
param([string[]]$Names)
$app = Split-Path -Parent $PSScriptRoot
Set-Location $app
$held = Get-NetTCPConnection -LocalPort 8791 -State Listen -ErrorAction SilentlyContinue
if ($held) { "port 8791 already held by pid $($held.OwningProcess); not starting another"; exit 1 }
$env:JARVIS_WARM = "0"
$log = Join-Path $env:TEMP "jarvis_harness_server.log"
$p = Start-Process python -ArgumentList '-c', '"from backend.app import app; app.run(host=''127.0.0.1'', port=8791, debug=False, threaded=True, use_reloader=False)"' -PassThru -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError "$log.err"
try {
  $up = $false
  for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:8791/ | Out-Null; $up = $true; break } catch {}
  }
  if (-not $up) { "server never came up"; Get-Content "$log.err" -Tail 20; exit 1 }
  Start-Sleep -Seconds 20
  # The first run against a fresh server often dumps nothing; take the second.
  python tools/run_harnesses.py @Names | Out-Null
  python tools/run_harnesses.py @Names
} finally {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
