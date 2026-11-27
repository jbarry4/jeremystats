# no-js-through-shell-heredocs

_Never write JS/regex through a shell heredoc in this project — write the patch script with the Write tool instead._

Never author JavaScript, regex, or any backslash-bearing string by piping a
Python heredoc through Bash. Write the patch script to a file with the Write
tool and run it.

**Why:** it has silently corrupted files five times here. `\n` inside a JS
string literal arrives as a real newline (breaking the literal); `\b` in a
regex arrives as byte 0x08, so `/\b62\s*%/` became `/<BS>62\s*%/` and could
never match — which cost several harness runs chasing a product bug that did
not exist. The corruption is invisible in `grep` output and survives
`node --check`, because both are valid-but-wrong.

**How to apply:** patch scripts go through Write, then `python <path>`. When a
patch must assert its own success, end it with a scan for stray control bytes
(`ord(c) < 32 and c not in "\n\r\t"`) — that is what finally caught this one.
Applies to `sed -i` with escapes too. Plain-text edits with no backslashes are
still fine inline. See [measure-dont-guess](measure-dont-guess.md).

It is not only about writing files. A **throwaway analysis script** read
through a heredoc is corrupted the same way and lies quietly: a registry scan
using `re.compile(r"^J\d{1,3}")` had its `\d` eaten, matched nothing, and
reported "zero paths look like this" about 32 paths that did. A survey that
returns a clean empty answer is exactly the result you will not double-check,
so use Write for these too — even the ten-line ones, even when nothing is
being modified. The quoted delimiter (`<<'PY'`) does **not** prevent it.

Happened again 2026-10-09, three times in one session: a Python patch fed
through `cat > file <<'PYEOF'` (writing to a file first does not help) put
`'\\n'` into JS as a real line break, twice, and node's parse caught it only
because the literal broke. Check every patched JS with
`node -e "new Function(require('fs').readFileSync(f,'utf8'))"`.

Again 2026-10-23, three times: Python patches through heredocs broke a Python string ('\n' became a real newline in backend/figkit/render.py, which broke the app's import for every other session until fixed), joined a backslash line-continuation, and broke a JS split('\n'). Python files too: use Write or Edit, never a heredoc, for anything with a backslash.
