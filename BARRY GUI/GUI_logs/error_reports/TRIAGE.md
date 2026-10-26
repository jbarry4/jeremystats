# Error report triage: where the last pass left off

The user hands these reports to an agent each day and asks for the bugs to be
patched. This file records what has been read and what was done about it, so
the next pass starts where the last one stopped. Add a section at the top for
your own pass. The Errors view lists only the `.txt` files here, so this file
does not show up in it.

## How to triage

- Each report is `<day>@<machine shard>.txt`, written by `backend/dayreport.py`
  (after 18:00 for today, on the first tick of a new day for yesterday). It
  covers **one computer only**. If a machine never ran Jarvis that day, it has
  no report.
- Read the raw shards as well: `GUI_logs/errors/<day>@<shard>.jsonl`. Older
  named shards (`@Strawbarry`, `@Blackbarry`, ...) come from other machines.
  Each record has `where`, `message`, `detail` (the traceback) and `context`.
- Test faults are left out of the reports by `_is_test_error` in
  `backend/app.py`: the `test: true` flag, `where == "selftest"`, or the
  `/_dev/`, `harness` and `127.0.0.1:879x-8830` patterns. The `test` flag has
  only existed since **2026-10-20 ~15:18**, so harness probes from before then
  (`hb-1`, `hb-other`, `harness-none`, `CSC9000`) look like real faults. They
  are not.
- `ui/mode.bounce` is a tripwire, not a crash. Up to 10-23 every one of
  them came from a `web/_dev/*.html` harness calling `_exitView` or `enter`
  directly.
- To find what the person was doing, read the activity lines the report
  prints around a fault. The 10-20 Root Canal bug showed up there, not in
  the traceback.

## Pass 1: 2026-10-23 (afternoon), everything since the reports began

The first pass since the reporter started (it first wrote 10-20's report on
10-21). Covered: every report in this folder, plus the raw shards for
10-20, 10-21, 10-22 and 10-23 on every machine.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 10-20 | Bluebarry | 10 listed | 9 are harness probes from before the `test` flag. **1 real**: Root Canal commit, fixed (below) |
| 10-21 | Bluebarry | 3 | joefigs scipy import deadlock x2, **fixed**. Supabase timeout x1, **made quiet** |
| 10-21 | Strawbarry | 1 | Supabase timeout in the same minute as Bluebarry's, **made quiet** |
| 10-22 | both | 0 | Bluebarry left out 64 test faults. Nothing real |
| 10-23 | Bluebarry | 0 so far | Shard read up to 12:12. All 26 faults are tests (Root Canal and Braces harnesses, mode.bounce). **No report for 10-23 yet**: it is written after 18:00 |

What changed (CHANGELOG `2026.10.23.7`):

1. **Root Canal commit refused with "read on file holds 431 ... this version
   has 243 ... Read it again"** (10-20 14:55, entry 46fd29a77cc7). The panel
   sends `read` = the read it opened, and after a commit the live set is the
   cleaned subset. `_rootcanal_setup` now falls back to the version's own
   read or a covering one. `api_rootcanal_commit` checks "already Root
   Canal's output" before setup, so the person gets the refusal that leads
   to the "Clean again anyway" dialog. Checks were added to
   `tools/check_rootcanal.py` (the old one never sent `read`, so it missed
   this). Result: 457 ok, 0 fail with `--no-real`.
2. **`_DeadlockError` on `scipy.spatial.distance`** (10-21 18:54 and
   18:56, `/api/arc/monolith/data/joefigs`). That route was already changed
   on 10-21 to read `figs.json` straight off the disk. The cause was still
   there, though: `backend/joe.py` was the only backend module importing
   scipy at module level. It now goes through `lazyimp`. `lazyimp` also
   does each library's first import under one lock, so two request threads
   can no longer race on it. Verified: importing `joe` no longer loads
   scipy, and 8 threads making a first call at once raise nothing.
3. **Supabase timeouts** (10-21 11:16, both machines in the same minute,
   and both recovered on the next pull). `cloud_sync_once` now logs a
   timeout or "cannot reach" only when the next attempt fails too. Other
   failures are still logged the first time. Checks were added to
   `tools/check_syncitems.py`, and all pass.

Not done, for the next pass:

- **Read 10-23's reports** once they exist (Bluebarry and Strawbarry,
  written after 18:00 on 10-23 or at the first start on 10-24). Today's
  shard was read only up to 12:12.
- `tools/check_joe.py` takes more than 10 minutes and was cut off at
  590 s. Before that it had one FAIL, "a copy whose size is not the
  recording tab 8 read". Run by hand on the same files with these changes,
  `python -m backend.joefigs pac` gave the right answer (15 rat-days, the
  right note). Another session was editing `joefigs.py` and `check_joe.py`
  at the same time, so the most likely cause is a half-written file. Run it
  again alone, in the background, before trusting it either way.
- Root Canal reached the same "not the same set" refusal on 10-23 with
  `from_version` set to a `br-`/`vk-` version. Those were harness runs
  flagged as tests, and fix 1 should cover them. If they come back without
  the test flag, look again.
