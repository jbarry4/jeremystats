# piped-server-log-deadlocks

_A test server started with stdout=PIPE stops answering after ~40 requests, and it reads as a slow route._

When starting the app server from a script to run a check against it, send
its output to a FILE, never `stdout=subprocess.PIPE` left undrained.

**Why:** Windows gives a subprocess pipe a 4 KB buffer. The Flask dev server
writes a line per request (~90 bytes), so at around forty requests the buffer
fills, the server blocks forever on its own `write`, and every request after
that times out. On 2026-09-18 this cost an hour: `check_braces_live.py` loops
over 48 candidate sets calling `/api/braces/plan` and prints nothing until the
loop ends, so the deadlock surfaced as a 300 s timeout with a traceback
pointing at one line — and it read as "that route hangs on an unreachable
recording". The route answers in 0.1 s; all 48 sets resolve in under 4.3 s.

**How to apply:** `logf = open(path, "wb")` then `Popen(..., stdout=logf,
stderr=subprocess.STDOUT)`, and read the file afterwards. Related:
[a-server-only-lives-inside-its-tool-call](a-server-only-lives-inside-its-tool-call.md) — the server and the check must
be in the same tool call, which is what makes a script the only way to do it.
Before believing a route is slow, time it in process AND over a socket: the
two disagreeing is the tell that the harness is what's broken, per
[measure-dont-guess](measure-dont-guess.md).
