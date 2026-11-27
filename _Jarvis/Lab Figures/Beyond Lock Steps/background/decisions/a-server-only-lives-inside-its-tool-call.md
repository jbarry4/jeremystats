# a-server-only-lives-inside-its-tool-call

_A Flask server started with PowerShell Start-Process dies when that tool call returns, and Bash run_in_background reports exit 127 for it while it is actually running — so start the server and run the harness in ONE PowerShell call._

Two ways to put a second app server on its own port, both of which lie about
what happened:

- **PowerShell `Start-Process ... -WindowStyle Hidden`** starts it, and an
  `Invoke-WebRequest` later in the *same* call gets `200`. The process is
  gone by the next tool call. A harness run then dumps Edge's own
  "can't reach this page" and the runner reports **0 ok, 0 fail** — which is
  indistinguishable from a suite of shot-takers, not from a failure.
- **Bash `run_in_background`** keeps it alive across turns but reports
  `[exited with code 127]` in its task notification while the port is still
  listening and serving. The notification is wrong; believe the port.

**Why:** both failure shapes read as success. The PowerShell one costs a
whole harness run before you notice, and the Bash one invites you to restart
a server that was fine.

**How to apply:** do it in one PowerShell call — kill whatever holds the
port, `Start-Process -PassThru`, `Start-Sleep 5`, run the harness, then
`Stop-Process` the `-PassThru` id. Check the port with
`Get-NetTCPConnection -LocalPort <n> -State Listen` rather than trusting a
task status. A second server on its own port is the polite way to test
backend edits when something else owns 8791 — see
`harness-runner-shares-the-app-server` (a note not copied here) and
`harness-suite-needs-powershell` (a note not copied here).

The first run of a harness against a freshly started server often dumps
nothing at all (0 ok / 0 fail). Run every harness twice and take the second,
or a real 69-check pass reads as an empty page.
