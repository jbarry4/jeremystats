# Hater of AI (Floss)

Hater of AI is the bug fixer anyone in the lab can ask from inside Jarvis
(the **Hater of AI** chip in the rail, or **Ask Hater of AI** on a fault in
History > Errors; it opens as a small pop-up beside the rail). The user
named him on 2026-11-06. Inside the code, routes, files and tickets he is
still "Floss".
It is Claude Code, run headless on the lab's Claude account, in a private
copy of this machine's code. It makes small fixes only and leaves everything
else for the main Claude Code session, "the mother AI", to review and
integrate.

Code: `backend/floss.py` (runs and tickets), `backend/floss_key.py` (the
key), `web/js/floss.js` (the dialog), `tools/floss_setup.py`,
`tools/floss_inbox.py`, `tools/check_floss.py`.

## Set up once, for the whole lab

1. Get the key from the lab account (Rain.Younger@uvm.edu), either kind:
   - a subscription token: on any machine, run `claude setup-token`, sign
     in as the lab account in the browser it opens, copy the
     `sk-ant-oat...` it prints; or
   - an API key: console.anthropic.com, signed in as the lab account,
     Settings > API keys > Create key (`sk-ant-api...`). Set a monthly
     spend limit there too.
2. From a machine with the cloud sync:
   `python tools/floss_setup.py --pin <lab PIN> --test`
   and paste the key at the hidden prompt. It is sealed with the PIN and
   put in Supabase storage (`results/jarvis-secrets/floss-key.txt`), never
   in git: the repo is public.

## On each machine, the first time

The dialog says what is missing and fixes it in one click each:

- **Install Claude Code**, if it is not on PATH, in `~/.local/bin`, or in
  the VS Code extension (the official installer, about a minute).
- **Unlock** with the lab PIN, once. The key is then kept sealed by Windows
  for this user (`%LOCALAPPDATA%\Jarvis\floss\key.bin`).

## What a run may do

- Its working copy is `%LOCALAPPDATA%\Jarvis\floss\wt\<id>`: `backend/`,
  `web/`, `tools/` as they are on this machine (uncommitted work included),
  made into a throwaway git repo and deleted after the run. The live tree,
  the real repo's index, branches and config are not touched by a run.
- Claude Code runs `--restricted` with Read, Glob, Grep, Edit and a Bash
  that may only run `py_compile`, `node --check`, `git diff`, `git status`.
  No Write (no new files), no web, no agents, no MCP. Its own config home,
  so it never sees this machine's personal settings, memory or sign-in.
- Model `sonnet` (`JARVIS_FLOSS_MODEL` overrides), 60 turns, 20 minutes,
  and $2 a run on an API key.
- Bugs, and small asked-for changes (wording, layout, a broken control,
  a default); no new tools, views or modules. Up to 6 screenshots per ask
  (pasted, dropped or attached), kept on that machine only
  (`%LOCALAPPDATA%\Jarvis\floss\img\<id>`, never git: the repo is public);
  the ticket lists their names.
- After the run, a hard check: at most 8 files and 250 changed lines,
  existing `.py .js .css .html` files under `backend/ web/ tools/`, none of
  the fenced files (Floss itself, cloud, shards, sign-ins, paths,
  launchers). Past that, the change is **held**: kept for review, never
  offered to apply here.

## Tickets

Every ask is `GUI_logs/floss/<id>@<shard>.json`. It travels by git with
that machine's next commit. It holds the ask, the context (view, the error
pointed at, recent errors), the machine's commit and uncommitted files,
Floss's report (`summary`, `cause`, `fix`, `confidence`, `tested`, `needs`,
and its plain `words`), the `patch`, `files`, `lines`, `held_because`, and
`run` (model, turns, cost). The run's raw transcript stays on the machine:
`%LOCALAPPDATA%\Jarvis\floss\runs\<id>.jsonl`.

| status | meaning |
|---|---|
| `working` | running now |
| `ready` | a small fix, waiting for the person to choose |
| `applied` | the person used it: it is in that machine's working tree |
| `undone` | used, then taken out again |
| `dismissed` | "Leave it for review": not used here |
| `held` | too big or fenced; never offered here |
| `nothing` | Floss made no change (see `needs`) |
| `failed`, `stopped` | as said; `error` says why |

## The weekly printout

Inside Jarvis's printer ("Last 7 days' work", `backend/weekly.py`) asks the
same engine, with the same key and config home, for something else: a calm
progress note for the PI. That run is read-only (`--tools Read,Glob,Grep`,
no Edit, no Bash), runs in the live app folder because it changes nothing,
and is given the week as its brief: the commits, every patch note of the
week, what was banked and called, and the Lab Operations sheet's dated
procedures. It answers with one json block (headline, summary, progress,
bench, data, next, watch). It shares the lab account's limits with the bug
fixer; when he cannot be asked, Jarvis writes the note from the numbers and
the printout says so. Its transcript stays on the machine
(`%LOCALAPPDATA%\Jarvis\floss\weekly\<id>.jsonl`); the printout itself is
`GUI_logs/weekly/<id>@<shard>.json`.

The same printout is emailed to the lab every Friday at 3:00 PM by the
scheduled task "Jarvis weekly email" on Bluebarry (`tools/weekly_email.ps1`,
`tools/weekly_email.py`), sent from barrylabuvm@gmail.com through Jarvis
Mailer (`_Jarvis/app/mailer/`, a standalone Apps Script; the secret and the
recipient lists are in `%LOCALAPPDATA%\Jarvis\weekly\mail.json` on that
computer only).

## For the mother AI

1. `python tools/floss_inbox.py --remote` lists open tickets (no `mother`
   field yet) on disk and on origin/master. It fetches; it never pulls.
   `show ID` prints one whole; `patch ID` prints its diff.
2. Settle each one:
   - **`applied`**: the fix is already live on that machine and arrives in
     its next commit. Review it as code you did not write. If it is right,
     add a check that fails without it and a CHANGELOG entry, then mark
     `integrated` with the commit that carried it. If it is wrong or
     partial, make the proper fix on master and mark `changed`; if that
     machine has not committed theirs, ask its person to press **Take it
     out** in Floss before they pull, or GitHub Desktop stops on the local
     change.
   - **`ready` / `dismissed`**: not live anywhere. If right,
     `floss_inbox.py patch ID > x.diff`, `git apply --3way x.diff` (it was
     cut against that machine's code, which can differ from yours), check,
     CHANGELOG, mark `integrated`.
   - **`held`**: a lead, not a fix. Do the real fix, or note why not.
   - **`nothing` / `failed`** with `needs`: do it, or mark `noted`.
3. `python tools/floss_inbox.py mark ID integrated|changed|rejected|noted
   --commit SHA --note "..."` writes the verdict into the ticket, so the
   asking machine's dialog shows "Reviewed". It travels with the next
   commit. The mother AI does not commit unless asked.
