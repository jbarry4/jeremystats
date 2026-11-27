# python-open-truncates-before-it-raises

_io.open(path, "w", newline=<bad>) empties the file and THEN raises; a patch script with a bad argument destroyed spotter.js_

On 2026-10-14 a splice script ended with
`io.open(P, "w", encoding="utf-8", newline="\\n")`. That is an escaped
backslash, not "\n". Python opened the file for writing, which truncated it,
and only then rejected the newline value and raised. `spotter.js` was left at
0 bytes. It was restored from `git show HEAD:...` (as bytes, through
subprocess) and the session's edits were re-applied.

**Why:** with mode "w" the file is emptied the moment it is opened. An
exception after that point does not undo it, and the traceback looks like a
harmless argument error.

**How to apply:**
- In patch scripts, open for writing in binary (`"wb"`) and write
  `out.encode("utf-8")`, or write to a temp file and `os.replace` it.
- Never pass `newline=` through a string that has passed through escaping.
- After any script error, check the target file's size before doing anything
  else.

Related: [no-js-through-shell-heredocs](no-js-through-shell-heredocs.md),
[another-agent-may-commit-your-work](another-agent-may-commit-your-work.md).
