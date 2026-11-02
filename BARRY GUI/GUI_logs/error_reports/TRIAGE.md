# Error report triage: where the last pass left off

The user hands these reports to an agent each day and asks for the bugs to be
patched. This file records what has been read and what was done about it, so
the next pass starts where the last one stopped. Add a section at the top for
your own pass. The Errors view lists only the `.txt` files here, so this file
does not show up in it.

## How to triage

- Since 2026-10-30 a pass runs by itself every morning at 08:47 on
  Bluebarry. The scheduled task "Jarvis daily error triage" runs
  `tools/daily_triage.ps1`, with the prompt in
  `tools/daily_triage_prompt.md`. Its run logs go to
  `%LOCALAPPDATA%\JarvisTriage`. It never commits.

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
- Before 2026-10-31, a harness run through `tools/harness_run.ps1`, or
  opened against the live app, filed what it provoked inside the app's
  frame as **real**: no `test` flag, and nothing in the message gives it
  away (e.g. "The border hb-other is not on this machine"). Since
  `2026.10.31.1` the runner sets `BARRY_HARNESS_SERVER`, and the frame
  sends `X-Barry-Test`. A fault with no activity lines around it, in the
  minutes a pass was running harnesses, is the usual sign.
- `ui/mode.bounce` is a tripwire, not a crash. Up to 10-23 every one of
  them came from a `web/_dev/*.html` harness calling `_exitView` or `enter`
  directly.
- To find what the person was doing, read the activity lines the report
  prints around a fault. The 10-20 Root Canal bug showed up there, not in
  the traceback.

## Pass 7: 2026-11-02 (morning, scheduled), 11-01 08:00 to 11-02 07:50

Nothing new. Bluebarry's 11-01 report: 0 faults, 0 actions, 4 left out
(pass 6's own `rootcanal/pool-fit` hb-1 / harness-none probes, all
`test: true`); no 11-02 shard yet. `git fetch` brought nothing
(`origin/master` still `137b5e73`). The cloud `errors` table, read-only,
has no row from any other machine after 10-30 21:58Z, and the cloud
`activity` table has only Strawbarry's 4 actions from 10-30 evening, so
nobody else has used Jarvis since: the weekend proves nothing. No code
changed. Open items B, C and the double-pool note stand as pass 6 left
them.

Builds: Bluebarry's Jarvis still ran `2026.10.28.2` on 11-01. **Passes
4, 5 and 6 (`2026.10.30.1`, `2026.10.31.1`, `2026.11.01.1`) all still
wait on a restart there**, and the last two are still uncommitted.

Next pass: Bluebarry's 11-02, then `git fetch`, then the cloud `errors`
table from `2026-10-30T22:00Z` (`machine=neq.Bluebarry`, no `detail`).

## Pass 6: 2026-11-01 (morning, scheduled), 10-30 afternoon to 11-01 08:00

Covered: Bluebarry's 10-31 report, shard and activity log, and its 11-01
shard so far. `git fetch` brought **nothing**: `origin/master` is still
`137b5e73` (Rain, 10-30 17:56), so no other machine has a 10-30 or 10-31
report here. Homebarry has never pushed a report by git. To fill the gap
I read the cloud, read-only, three queries: the `errors` table for every
machine but Bluebarry from 10-30 15:40Z to 11-01 13:00Z, and the
`activity` table around the two faults below. Clocks: the cloud is UTC,
and local time has been EST (-05:00) since 11-01.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 10-30 | Homebarry (Shahriar) | 1 | pass 5's open **A**: `rootcanal/event` on opening a pool saved on Strawbarry. **Fixed** (1) |
| 10-30 | Strawbarry (Rain) | 1 | `braces/decide` hold refusal at 17:58, in the cloud only. The old code: **fixed in `2026.10.30.3`** |
| 10-31 | Bluebarry | 0 (6 test) | all pass 5's harness runs, `test: true` |
| 10-31 | everyone else | 0 | nothing in the cloud, no reports |
| 11-01 | Bluebarry | 0 (4 test) | this pass's harness run, `test: true` |

What changed (CHANGELOG `2026.11.01.1`):

1. **A saved Root Canal pool claimed every read was here.** Homebarry's
   activity in the cloud gave the lines pass 5 asked for:
   `rootcanal.pool_open` (artifact `789627824001` v2) at 14:19:18Z, and
   the refusal in the same second, before any click. Rain saved that
   pool on Strawbarry on 10-06, and its payload keeps Strawbarry's
   truth: all 9 members `here: true`, each with an `event_body` pinned
   to Strawbarry's read. `GET /api/rootcanal/pool/<id>` returned that
   payload unchanged. `memberHere` in `web/js/rootcanal.js` believed
   it, so `autoPick` asked for `adc84ab8c916`'s trace (read
   `b2c0380f768b`). Now `_rootcanal_saved_here` in `backend/app.py`
   recomputes `here`, `event_body` and `read_on` per member with the
   fit's own test (`ROOTCANAL.has_cached`), on copies. A member read
   elsewhere then takes the designed away path: it says where it was
   read and reads it here (`startEvRedo`). On Bluebarry the same pool
   has 2 of 9 members (`6a2ade1040d3`, `9b801cb6e235`) read only on
   Strawbarry, so the fault was waiting here too.
   `tools/check_rootcanal_saved_here.py`: 6 of 11 fail with the call
   taken out, 11 ok with it in. `rootcanalpool` (294) and
   `rootcanalswitch` (9) still pass. Both stub the saved-pool route, so
   neither one tests the fix itself.
2. **Strawbarry `braces/decide`** (set `br598faf68f9`, PTEN M2 s8, Lock):
   "This stamp is in a group this alignment holds where it is". The
   message ends "...not moved or relabelled here.", without the
   "unless the call is sent with `override`" that `81ac8c14`
   (`2026.10.30.3`, 15:16 that day) added along with the override. So
   Strawbarry's server was older than the fix; Rain had only pulled at
   17:56. Rain's commit 13 s later went through (2 moved, v3). No change.

Open:

- **B. Harness seeds in the shared bank.** Unchanged from pass 5, still
  the user's decision.
- **C. A harness's actions are logged as the person's.** The 10-31
  report's "84 actions" are all pass 5's harness run (08:56 to 09:02):
  56 `error.resolve` (`bounce.html` resolving its own faults), 20
  `mode.change` and 8 `link.scope`. They are credited to Shahriar Tafti
  with no test mark. `record_activity` in `backend/store.py` has no
  `test_origin` check, and `cloudsync` pushes the log to the cloud
  `activity` table, so they reach the lab's shared history, the tool
  feeds and Who. Dropping them at the door, or marking them and
  filtering in every reader, changes what the cloud holds. A harness may
  also assert on its own activity. So it is the user's call; the code
  is unchanged.
- The double-pool route (`/api/rootcanal/dpool/<id>`) also returns its
  payload as saved. No double pool has been saved on this machine, and
  its members are pools, not reads, so it was not checked.

Builds: Bluebarry's Jarvis still ran `2026.10.28.2` on 10-31. **Pass 4's
`2026.10.30.1`, pass 5's `2026.10.31.1` and today's `2026.11.01.1` all
need a restart there.** The last two are uncommitted, so no other
machine has them. Homebarry ran `2026.10.26.2`; Strawbarry ran something
older than `2026.10.30.3` at 17:58 on 10-30.

Next pass: Bluebarry's 11-01 (everything up to 08:00 is this pass's
harness run, all `test: true`). Then `git fetch`. If other machines still
have pushed no reports, read the cloud `errors` table, read-only, from
`2026-11-01T13:00Z` (`machine=neq.Bluebarry`, no `detail` column).

## Pass 5: 2026-10-31 (morning, scheduled), 10-30

Covered: Bluebarry's 10-30 report and its shard (last write 12:16), and
two raw shards that arrived by cloud sync at 11:46 on 10-30, as pass 4
was finishing: `10-29@Strawbarry` (pass 4's four `rootcanal/fit`,
nothing new) and `10-30@Homebarry`, a new machine: Shahriar at home,
`C:\Users\info\Desktop\JeremyStats`. `git fetch` brought `137b5e73`
(Rain, 10-30 17:56), which holds curation, bank and Root Canal data and
**no new reports**. No machine but Bluebarry has a 10-30 report yet.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 10-30 | Bluebarry | 0 (2 listed) | `rootcanal/pool-fit` "The border hb-other is not on this machine" ×2 at 11:46 is `rootcanalborder.html` checking a refusal on purpose, filed as real. **Fixed** (1) |
| 10-30 | Bluebarry | 4 test | `joeexport/file` WinError 32 / 2 from the test client at 12:16. A real race. **Fixed** (3) |
| 10-30 | Homebarry (Shahriar) | 2 | `rootcanal/event` "This member's read is not on this machine": **open** (A). `dspca/plan` on "harness dupes": a harness seed in the shared bank, **the user's call** (B) |
| 10-29 | Strawbarry | 4 | pass 4's, already fixed in `2026.10.30.1` |

What changed (CHANGELOG `2026.10.31.1`):

1. **Harness faults filed as real.** `tools/harness_run.ps1` (new on
   10-30, the runner these passes use) started its server without
   `BARRY_HARNESS_SERVER`. `harness_run.py` always set it. So nothing that
   server filed was marked as a test's. Its deletions would also have
   written tombstones, though none were written: Bluebarry's tombstone
   file is unchanged since 10-23. It also ran the day-report loop. The
   referrer fallback could not catch it either: the app in a harness's
   iframe sends the frame's address, not `/_dev/`. Now the `.ps1` sets
   the flag, and `api()` in `web/js/core.js` sends `X-Barry-Test` from
   any frame a `/_dev/` page holds, which `_request_is_test` counts.
   Checked: today's two hb-other refusals from the fixed runner are
   `test: true`.
2. **`-Names a,b` ran nothing.** Under `powershell -File` the list
   arrives as one string, and `run_harnesses.py` matched it as one
   substring: "0 harness(es) ... nothing failing". It splits on commas
   now, and it refuses with the names when one matches nothing.
   **Distrust any multi-name `harness_run.ps1` result from before
   today.** Single names were fine.
3. **Tab 10's files raced.** Every `joeexport/file` request runs
   `manifest()`, which makes stale Prism zips, previews and legend files
   again in place through fixed names. `manifest()` now holds a lock.
   `tools/check_joeexport_race.py` gave 28 × WinError 32 without it and
   none with it.

Each check fails with its fix taken out and passes with it in:
`tools/check_testorigin.py` (1 fail with the header check out, 3 with
the runner fixes out; 10 ok),
`web/_dev/testorigin.html` (2 fail / 3 ok) and
`tools/check_joeexport_race.py` (1 fail / 5 ok). `rootcanalborder` (103)
and `bounce` (10) still pass, and `check_js.py` parses everything.

Open:

- **A. Homebarry `rootcanal/event`** (10-30 14:19, entry `adc84ab8c916`,
  pten m60 s1, `i` 366). Homebarry's traceback line numbers match
  `7728a9ca` (`2026.10.26.2`). That code builds a pooled member's click
  request only when it finds the read in its cache at fit time, and the
  click checks the same cache. The entry's gid is `s8d7f397b9708` in
  every shard. So either the browser sent a read for a member with no
  `event_body` (`memberHere` in `web/js/rootcanal.js` says "here" when a
  member carries neither `event_body`, `here` nor a candidate), or the
  read left the cache between fit and click. **Read Homebarry's 10-30
  report for the activity lines** before changing anything.
- **B. Harness seeds in the shared bank.** `GUI_logs/event_bank` holds
  229 `harness_*` files (about 80 sets) across 6 machine shards. `_note_deleted`
  deliberately writes no tombstone for project HARNESS. So a harness
  deleting its seed removes only that machine's copy, and the other
  machines' copies come back by git. Shahriar opened `bankdupes.html`'s
  "dupes seed" (`5360afb7c67c`, 10-22) in DS-PCA on Homebarry and got
  the "no registry id" refusal. Purging them, hiding HARNESS from the
  lists, or keeping seeds off git is the user's decision. Nothing was
  deleted.
- `GUI_logs/prefs/workbench@desktop-4h65ai7-d565.json` was rewritten at
  09:02:04 today, during the harness run. The live Jarvis (pid 3824) was
  also running and syncing. The write is the merged view of every
  machine's shard: no value newer than 10-30, only `updated`. It was
  left as it is. If it shows up again during a harness run, look at
  `bounce.html`, which does not stub `BARRY.prefs.set`.

Builds: Bluebarry's Jarvis has run since 10-28 16:59 on `2026.10.28.2`.
**Pass 4's `2026.10.30.1` and this pass need a restart there.**
`origin/master` now carries `2026.10.30.3`, so pass 4's fix has gone out;
today's is uncommitted. Homebarry ran `2026.10.26.2`.

Next pass: Bluebarry's 10-31 (everything in it up to 09:02 is this
pass's harness runs, all `test: true`), and 10-30 / 10-31 from
Strawbarry, Blackbarry, Avery and Homebarry off `origin/master`. Start
with Homebarry's 10-30 report, for A.

## Pass 4: 2026-10-30 (morning), 10-28 09:30 to 10-29

Covered: Bluebarry's 10-28 and 10-29 reports here, and from `origin/master`
(read with `git show`, not pulled) Strawbarry's 10-27, 10-28 and 10-29,
Avery's 10-26 and Blackbarry's (Isabella, `lcom549913-e62b`, new) 10-26,
10-27 and 10-28. No raw shards newer than 10-28 have synced here, so the
reports were all there was. **Reports from other machines arrive by git;
`git fetch` and read them off `origin/master`.**

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 10-27 | Strawbarry (Rain) | 4 | `braces/decide` "already accepted", pass 3's, **fixed** in `2026.10.28.1` |
| 10-28 | Bluebarry | 0 | 21 test faults |
| 10-28 | Strawbarry, Blackbarry | 0 | 1147 and 209 actions |
| 10-29 | Bluebarry | 0 | 0 actions |
| 10-29 | Strawbarry (Rain) | 4 | `rootcanal/fit` "has not been read at these settings", **fixed** |
| 10-26..28 | Avery, Blackbarry | 0 | |

1. **Root Canal: a finished read handed to the wrong set.** At 10:47:39 a
   read of entry `bfa98498290b` started; Rain then opened `41dd94702761`
   (pten m2 s3, its v3 `vk-b8455d7848f5`, 113 stamps, never read on
   Strawbarry). When the first read finished, `watch()` in
   `web/js/rootcanal.js` set `q.read` to its hash and fitted, so the fit
   asked for `41dd` over another recording's read: refused at 10:49:28
   and on each Recompute after. Rain pressed Read at 10:53:45 and it
   worked from there. `startRead` now records the set (`jobFor`), and a
   read that finishes under another set only refreshes the list and says
   so. The reading card names `jobFor`'s set. New
   `web/_dev/rootcanalswitch.html` fails 4 checks with the guard taken
   out and passes 9 with it in.

Builds: everyone else is on `2026.10.27.1`. **`origin/master` stops at
`2026.10.27.1`: 10.28.1 (Braces) and this pass's fix are not committed,
so no other machine has them yet.** A `braces/decide` "already accepted"
from a machine on `2026.10.27.1` is the old code.

Next pass: from 10-30. `git fetch` first and read the reports off origin.

## Pass 3: 2026-10-28 (morning), 10-26 to 10-28 09:30

Covered: the 10-26 reports from both machines and 10-27's from Bluebarry,
plus every raw shard. Strawbarry and DESKTOP-NR2H5O7 (Avery) had no 10-27
report yet; their raw shards arrived by sync on 10-28 09:24.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 10-26 | Bluebarry | 0 | 8 test faults (harness mode.bounce and braces/plan) |
| 10-26 | Strawbarry | 0 | 224 actions |
| 10-27 | Bluebarry | 0 | 19 test faults |
| 10-27 | Strawbarry (Rain) | 4 | `braces/decide` "already accepted as version 3", 4× in 20 s. **Fixed** |
| 10-27 | DESKTOP-NR2H5O7 (Avery) | 3 | the same `braces/decide` 2×, **fixed**. `ui/mode.bounce` none→panning in 5.5 s, a false alarm, **watcher fixed** |

1. **Braces/Lock keys after autobank.** `autoBank` commits once the last
   flagged stamp has its call, and the review stayed open with its answer
   buttons and keys live. Every key then hit `BracesSet.decide`, which
   refuses a committed set, and came back as a red toast. Now
   `accepted()` in `web/js/braces.js` stops `decide`, `vSay`, `vEnter`,
   `vGarbage`, `vDrop` and `vUndoAll`, and says so once per set. `vBar`
   shows "Banked as version N" in place of the answers. A section was
   added to `web/_dev/bracesenter.html`. The server's refusal is unchanged
   and still logs, so a `braces/decide` "already accepted" from a build at
   or after `2026.10.28.1` means some other path is still sending.
2. **mode.bounce false alarm.** Panning's `enter()` calls `exit()` (mode
   none), then `setMode('panning')` once the recording is open, 5.5 s
   later over the VACC. The click was on the first change, not the
   second. `noticeBounce` in `web/js/core.js` now records `byHand` on each
   change and skips X → none → X when the leaving was by hand. The real
   fault shape (into a mode, then out unasked) is still reported, and a
   check was added for it in `web/_dev/bounce.html`.
3. **`web/_dev/bounce.html` was broken in two ways.** Its counts read
   `/api/errors` without `tests=all`. Since 10-20 its own bounces are
   marked as tests and hidden, so "the bounce filed an error" could never
   pass. Its clean-up also resolved every bounce signature it could see,
   which, being hidden from its own, were only the real ones. (None was
   ever stored as resolved, so nothing was lost.) It now counts with
   `tests=all` and resolves only `test` records.

Pass 1's fixes are live on Bluebarry since build `2026.10.26.2` (10-27's
report). No Root Canal "Read it again", no scipy deadlock, and no sync
timeout since then, though there was little Root Canal use. Strawbarry
was still on `2026.10.23.6` on 10-26.

Next pass: Strawbarry's and Avery's 10-27 reports, then 10-28.

## Pass 2: 2026-10-26 (morning), 10-23 evening to 10-26 09:30

Nothing new. Covered: the 10-23, 10-24 and 10-25 reports on both machines,
and every raw shard in `GUI_logs/errors/`. The newest is still
10-23@desktop-4h65ai7-d565, last written 12:12.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 10-23 | Bluebarry | 0 | 26 test faults, the same ones pass 1 read. None after 12:12 |
| 10-23 | Strawbarry | 0 | 1091 actions, no faults |
| 10-24, 10-25 | both | 0 | **0 actions**: Jarvis was open but unused (weekend), so this proves nothing |
| 10-26 | both | 0 so far | No shard yet at 09:30 |

Builds the reports name: Bluebarry was still running `2026.10.23.6`
through 10-25, and Strawbarry `2026.10.23.5`. **Neither was running pass
1's fixes (`2026.10.23.7`) yet.** They reached master in `f2af2ca1`
(10-26 09:24). The first report that tests them is the first one whose
`build` line reads `2026.10.23.7` or later. Until then, a Root Canal "Read it
again", a scipy `_DeadlockError` or a lone sync timeout is the old code,
not a failed fix.

Next pass: start from 10-26's reports. Check their build lines first.

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
