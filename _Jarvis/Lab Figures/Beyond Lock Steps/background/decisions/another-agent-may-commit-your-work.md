# another-agent-may-commit-your-work

_This repo is sometimes worked by two Claude sessions at once; the other one makes blanket commits that sweep in your work, and can restore a shared file from git and erase your uncommitted edits to it._

On 2026-09-17 a second Claude session was editing this tree at the same
time. It edited `web/js/xplore.js` while this session had the file open
(removing `LAYER_WASHES` and `drawLayerBands`), and it committed twice —
`12dc474 "."` and `f362d22 "Layers on any panel, and only where they mean
something"`. The second swept in this session's entire theta-CSD change and
its new harness under that message.

**Why:** nothing was lost, but three assumptions broke at once. `HEAD` moves
under you, so a worktree cut for "the baseline before my change" may already
contain someone else's. `git status` stops listing your files as modified
because they have been committed by someone else. And an edit tool will warn
that a file "changed on disk" for a reason that is not your own earlier
write.

**How to apply:** at the start of work in this repo, `git status --short`
and note `HEAD`; if files you never touched are modified, assume company.
Keep edits in regions of your own and re-check `node --check` / `ast.parse`
after their commits land. Cut a baseline worktree from the specific SHA you
measured against, not from `HEAD`, and verify it lacks your change before
trusting it. Do not "fix" their uncommitted work, and do not commit unless
asked — theirs will be in the diff. Say plainly in the handoff which commit
carried your work, since its message will not mention it.

On 2026-09-25 it went the other way. While this session was building The
Storm, the other session (building Root Canal, plus bundle folding in the
ToolKit) restored `web/js/toolkit.js` from git and re-applied only its own
52 lines. Every Storm registration in that file was gone. No error, and
`git status` still listed the file as modified. Every other file kept this
session's edits.

**How to apply, in addition:** after a long stretch in a shared file like
`toolkit.js`, `index.html` or `app.py`, grep for a marker of your own change
before assuming it is still there. Re-apply as targeted, idempotent inserts
(skip when the marker is present) on top of whatever is there now, never by
writing out a copy you hold. That copy is older than their change.

**Never `git stash` in this tree** (2026-10-23). This session stashed to
compare against old code, and the stash also took the other session's
uncommitted joefigs.py, check_joe.py and monolith_help.js, and the app's own
GUI_logs writes, back to HEAD on disk for a minute. The pop was clean, but
any write of theirs in that window would have conflicted or been lost. To
get a baseline, use a worktree at a SHA (`baseline-harnesses-in-a-head-worktree` (a note not copied here)),
or revert only your own hunks by Edit.
