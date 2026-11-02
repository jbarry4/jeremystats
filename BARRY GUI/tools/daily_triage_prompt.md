This is the daily pass over Jarvis's end-of-day error reports. Find the real
faults since the last pass, fix the ones whose cause is clear, and write
down where you stopped. It runs unattended from Windows Task Scheduler
(`tools/daily_triage.ps1`), so nobody will answer a question. Where a
decision is the user's to make, write it up in TRIAGE.md and leave the code
as it is.

The app is in `BARRY GUI/`. All paths below are relative to it.

1. Read `GUI_logs/error_reports/TRIAGE.md` first. The how-to at the top says
   which faults are test faults. The newest pass at the top says what has
   been read and what to do next.
2. Run `git fetch origin`. Other machines' reports arrive by git, so read
   them with `git show "origin/master:BARRY GUI/GUI_logs/error_reports/<file>"`.
   List them with `git diff --name-only HEAD origin/master`. Read this
   machine's reports and the raw shards (`GUI_logs/errors/*.jsonl`) on disk.
   Check each report's `build` line, because a fault on a build older than
   its fix is the old code, not a failed fix. **Never** pull, merge, stash,
   reset, checkout, restore, commit or push. Other people and another
   Claude session work in this tree.
3. For each real fault, find the cause in the code. The activity lines
   around the fault usually show what the person was doing.
   - If the cause is clear and the fix is small, fix it. Then add or
     extend a check (`web/_dev/*.html` or `tools/check_*.py`) that fails
     with the fix taken out and passes with it in. Prove that, then put
     the fix back.
   - Run harnesses with
     `powershell -File tools/harness_run.ps1 -Names <name>,<name>`. It
     starts and stops its own server on port 8791.
   - Before editing a file, run `git diff` on it. If someone else has
     uncommitted work there, keep your change separate from theirs.
   - If the cause is unclear, or the fix is large, risky or a design
     choice, leave the code alone. Record it as open in TRIAGE.md with
     what you found.
4. For every code change, add a `CHANGELOG.md` entry above the newest one.
   Its version is `YYYY.MM.DD.N` for today. Say whether a page reload is
   enough or Jarvis must be restarted.
5. Add a `## Pass N` section at the top of TRIAGE.md, in the format of the
   ones below it: what was covered, a table by day and machine, what
   changed and why, builds, and where the next pass starts. If nothing is
   new, three lines are enough.
6. Do not use subagents or workflows. Do not touch the Supabase cloud, the
   VACC or anything outside this repo, except to read.
7. Finish with a short plain-English summary of what was found and what
   changed, for the run log.
