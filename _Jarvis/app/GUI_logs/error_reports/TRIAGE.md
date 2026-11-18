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

## Pass 22: 2026-11-17 (morning, scheduled), 11-16 08:50 to 11-17 08:50

Covered: Bluebarry's 11-16 report (build `2026.11.13.7 de71a7fc`, 0 faults,
3 actions; no Bluebarry 11-16 or 11-17 shard). `git fetch` brought
`8c391def` (Shahriar, 11-16 12:16): `origin/master` is `8c391def`, HEAD
still `de71a7fc`. It carries Blackbarry's 11-12 report and Strawbarry's
11-09 to 11-11 (all 0 faults; Strawbarry on `24e7b82f`, Blackbarry on
`03847324`). Strawbarry's 11-12/11-13 and Blackbarry's 11-13 still have not
come. A Blackbarry 11-16 shard is on disk here (`errors/2026-11-16@Blackbarry.jsonl`)
with one real fault. Cloud not read this pass.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 11-09 to 11-11 | Strawbarry (Angelina Woychosky) | 0 | Build `2026.11.06.4 24e7b82f` |
| 11-12 | Blackbarry (Isabella Piatek) | 0 | 114 actions, build `03847324` |
| 11-16 | Bluebarry (Shahriar) | 0 | 3 actions |
| 11-16 | Blackbarry (Isabella Piatek) | 1 | `dspca/fit` "That read is not on this machine any more" (1). Open |

1. **DS-PCA fit on a read this machine never made** (17:54:31Z, gid
   `sc74c98b2495d`, read `75398bb10d0c`). `dspca.load_read` refuses
   because the `.npz` is absent. The read cache is machine-local, but an
   X-ray bundle (an artifact, so it syncs) carries its read hash:
   `enter(b)` in `web/js/dspca.js` (~line 1676) sets `q.read` from
   `b.payload.read` and refits without asking whether that read is cached.
   On any machine but the one that made the read, the fit fails. The
   message says "read the set again", but in bundle mode `plan` is null, so
   `readCard()` draws nothing and there is no "Read again" button: the
   person has no way to do what it says. Not fixed: what a bundle opened on
   another machine should do (re-read automatically from the bundle's set
   and stamps, offer a Read button, or say the read lives on the making
   machine) is the user's call. Left open.

No code changed and there is no CHANGELOG entry.

Next pass: Bluebarry's 11-17 report and shard, any Blackbarry shard on
disk, then Strawbarry's 11-12/11-13 and Blackbarry's 11-13+ reports when
git brings them. Then `git fetch`, then the cloud from `2026-11-14T13:50Z`
(not read this pass). Item 1 above, pass 18's two watches and the Blackbarry
`POST /api/session/state` stalls (pass 19) are open.

## Pass 21: 2026-11-16 (morning, scheduled), 11-15 08:50 to 11-16 08:50

Nothing new. Bluebarry's 11-15 report (build `2026.11.13.7 de71a7fc`) has
0 faults and 0 actions, and there is no 11-14, 11-15 or 11-16 shard. 11-15
was a Sunday. `git fetch` brought nothing: `origin/master` is still
`67277475` and HEAD `de71a7fc`. The cloud, read only, from
`2026-11-14T13:50Z`: 0 `errors` rows and no `activity` rows from any
machine, so no `client.error` rows either. Its newest row is still
Strawbarry's at 22:24Z on 11-13. Floss: 0 open here. I could not see
Strawbarry's tickets this pass (nothing new came by git), so Rain's
`20261109-102332-eca9` counts as still open there.

No code changed and there is no CHANGELOG entry.

Next pass: Bluebarry's 11-16 report and shard (a Monday, the first working
day since 11-13). Then Strawbarry's 11-12 and 11-13 reports and
Blackbarry's 11-13 when git brings them. Then `git fetch`, then the cloud
from `2026-11-14T13:50Z` (nothing has arrived since, so the start does not
move). Pass 18's two watches and pass 19's count of the Blackbarry
`POST /api/session/state` stalls (thirteen since 11-09, with pooled
curation set opens over 30 s beside them) all still stand.

## Pass 20: 2026-11-15 (morning, scheduled), 11-14 08:50 to 11-15 08:50

Nothing new. Bluebarry's 11-14 report (build `2026.11.13.7 de71a7fc`) has
0 faults and 0 actions, and there is no 11-14 or 11-15 shard. 11-14 was a
Saturday. `git fetch` brought nothing: `origin/master` is still `67277475`
and HEAD `de71a7fc`. The cloud, read only, from `2026-11-14T13:50Z`: 0
`errors` rows, 0 `client.error` rows and no activity from any machine. Its
newest row is Strawbarry's at 22:24Z on 11-13. Floss: 0 open here, and
Rain's `20261109-102332-eca9` is still open on Strawbarry.

No code changed and there is no CHANGELOG entry.

Next pass: Bluebarry's 11-15 report and shard. Then Strawbarry's 11-12
and 11-13 reports and Blackbarry's 11-13 when git brings them. Then
`git fetch`, then the cloud from `2026-11-15T13:50Z`. Pass 18's two
watches and pass 19's count of the Blackbarry `POST /api/session/state`
stalls (thirteen since 11-09, with pooled curation set opens over 30 s
beside them) all still stand.

## Pass 19: 2026-11-14 (morning, scheduled), 11-13 09:10 to 11-14 08:50

Covered: Bluebarry's 11-13 report and shard. There is no 11-14 shard yet.
`git fetch` brought two more commits, Shahriar's `7a7f77c8`/`67277475`
(11-13 11:49). `origin/master` is `67277475`, and HEAD is still `de71a7fc`.
With them came Blackbarry's 11-11 and 11-12 reports. Strawbarry's 11-12 and
11-13 reports, and Blackbarry's 11-13, have not come yet. Floss: 0 open
here, and Rain's `20261109-102332-eca9` is still open on Strawbarry. I read
the cloud without writing to it, from `2026-11-13T13:45Z`: 6 `errors` rows,
all Bluebarry's and the same as the shard, and 14 `client.error` rows.

No real fault, so no code changed and there is no CHANGELOG entry.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 11-11 | Blackbarry (Isabella Piatek) | 0 | 0 actions. Build `2026.11.11.4 03847324` |
| 11-12 | Blackbarry (Isabella Piatek) | 0 | 114 actions, same build |
| 11-13 | Bluebarry (Shahriar) | 0 (6 test) | 256 actions. All six carry `test: true` (1) |
| 11-13 | Blackbarry, Strawbarry | 0 `errors` rows | 424 and 28 actions in the cloud. 14 "stuck" rows with Bluebarry's. Slow, not faults (2) |

1. **The six test faults** are the other session's probes of the
   Extraction Room while it built `2026.11.13.2` to `.7`. All are on the
   real folder `980b57eab496`, and all are flagged by the test client.
   - 11:48:19 `extraction/split`, "keywords must be strings": a
     `TypeError` from `dict(..., **{int(c): ...})` in `_er_direct_fit`.
     That line was written and replaced the same morning. On disk the
     function calls `extractionmod.rebuild_contacts` and no
     `**{int(` is left anywhere in `backend/`. It is the only one of the
     six that was a bug and not a refusal, and it is gone.
   - 13:14:04–05 `extraction/interp`, three in two seconds: "Contact 70
     is not on this shank (1-64)" and "Contact 63"/"Contact 1 needs two
     good contacts above it and two below". These are the refusals of
     `clean_interp`, asked for on purpose.
   - 15:30:37 `extraction/split`, the Contact 63 refusal again, through
     `_er_interp_look`.
   - 16:55:01 `extraction/split`, "Only 1 event between 0.2 and 0.2 min:
     a window keeps at least 8": the refusal of `subset_read` for a time
     window with too few events.
2. **"Stuck" rows** (cloud `activity`): 14. None is `GET /api/link`, and
   none is a `rootcanal/meta` poll.
   - Blackbarry, start-up at 16:50:30Z: `registry` 35 s.
   - Blackbarry, `POST /api/session/state`: 41 s at 17:34:49Z, 33 s at
     17:49:19Z and 32 s at 18:35:11Z, all in Xplorefinder. That is pass
     17's open item, now thirteen times since 11-09.
   - Blackbarry, new this pass: opening a pooled curation set took 32 s
     at 17:54:40Z (`s655a06b22296`) and 31 s at 18:48:13Z
     (`se0c7b6ba6d5a`). `csc/window` took 31 s at 17:49:56Z, right after
     a `session/state` stall, and `csc/open` 31 s at 18:53:53Z. The
     activity lines beside them read "Working on syncs…" and "Checking
     which recordings…", so the server was busy with something else each
     time. I did not measure it. Left open with the item above.
   - Bluebarry at 18:39:32Z and Strawbarry at 20:37:47Z: the start-up
     clusters seen before (`registry` 35 s, `csc/open`, `prefs`,
     `arc/precon/status`).

Builds: Bluebarry's 11-13 report says `2026.11.13.7 de71a7fc`. HEAD is
still `de71a7fc`, and everything from `2026.11.11.5` to `2026.11.13.7`,
with pass 18's `2026.11.13.1`, is uncommitted here. Blackbarry ran
`03847324` on 11-11 and 11-12. That has `2026.11.07.2` (DS-PCA) and not
pass 18's fixes. Strawbarry's newest report is still 11-11, on `24e7b82f`.

Next pass: Bluebarry's 11-14 report and shard. Then Strawbarry's 11-12
and 11-13 reports and Blackbarry's 11-13 when git brings them. Both used
Jarvis on 11-13 and have no cloud `errors` rows. Then `git fetch`, then
the cloud from `2026-11-14T13:50Z`. Pass 18's two watches still stand
(the "every event on one side" cut, and Floss on Strawbarry after it
pulls). Count the `POST /api/session/state` stalls on Blackbarry, and the
pooled curation set opens over 30 s beside them. If they keep coming
together, the thing to find is what holds the server for 30 s while
"Working on syncs" shows.

## Pass 18: 2026-11-13 (morning, scheduled), 11-12 09:00 to 11-13 09:10

Covered: Bluebarry's 11-12 report and shard. There is no 11-13 shard yet.
`git fetch` brought six commits from 11-12: Rain's `f9792b6e` (10:57),
Shahriar's `8c652c84`/`03847324` (13:16) and Aggie's `e7d114ac`/`233b1502`/
`42e0a8e3` (13:53 to 15:17). `origin/master` is `42e0a8e3`, and HEAD is
still `de71a7fc`. With them came Strawbarry's 11-09, 11-10 and 11-11
reports and Blackbarry's 11-10. They also brought eleven reports from Aggie
Krempasky's Mac. It names itself `ip0af550d3.int.uvm.edu-f987` from 11-01
to 11-10 and `ip0af5523d.int.uvm.edu-f987` on 11-11: one Mac, whose network
name changes while the `-f987` stays. One Floss ticket came too. I read the
cloud without writing to it, from `2026-11-12T13:45Z`: 25 `errors` rows,
all Bluebarry's and the same as the shard, and 30 `client.error` rows.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 11-01 to 11-10 | Aggie's Mac (`ip0af550d3`) | 1 | 11-02 10:33 `cloud.sync` "not answering (no connection)", with nothing around it: the laptop was offline. Not a fault. 25 actions on 11-02, none on the other days. Build `2026.10.30.3 d972b0bd` |
| 11-11 | Aggie's Mac (`ip0af5523d`) | 0 | 0 actions. Build `2026.11.11.4 233b1502`, written 11-12 14:01 |
| 11-09 | Strawbarry (Angelina Woychosky) | 0 (1 test) | 348 actions. The one left out is pass 17's `harness dupes` (DS-PCA), dropped by the `harness` pattern |
| 11-09 | Strawbarry (Rain), Floss | 1 | Floss could not start. **Fixed** (4) |
| 11-10, 11-11 | Strawbarry | 0 | 0 actions |
| 11-10 | Blackbarry (Isabella Piatek) | 0 | 433 actions. Build `2026.11.06.4 06e48c9b` |
| 11-12 | Bluebarry (Shahriar) | 17 (3 distinct), 8 test | (1) **fixed**, (2) older code than was on disk, (3) **fixed**. The 8 test faults are the `hb-1`/`harness-none` pool-fit probes |
| 11-12 | Strawbarry, Blackbarry, DESKTOP-AH45FAE | 0 `errors` rows | 30 "stuck" rows (with Bluebarry's). Slow, not faults (5) |

1. **`extraction/split-preview`, "That cut leaves every event on one
   side."**, five times: 12:42:11 (twice), 13:16:28–29 (twice) and
   15:55:46. Shahriar was dragging the cut on an Extraction Room card:
   delta and PCA on `xm-f7e3cb9cee38-v2`, and at 15:55 the Bite line on
   `xm-500fa6c3c5`. The card's plot runs 4% past the events on each side
   (`drawSplit`). `dragCut` in `web/js/extraction.js` sent wherever the
   pointer was, so a drag to the edge asked for a cut with every event on
   one side. `split_types` in `backend/extraction.py` refused it, and
   `fail()` filed each refusal. The pairs are one preview while dragging
   (the page swallows it) and one at let-go (the page says "Not cut
   there"). Compare splits (`normCut` in `web/js/extraction_compare.js`)
   already keeps its line inside the events. Fixed in `2026.11.13.1`: the
   card's drag follows the same rule. `web/_dev/extraction.html` has a new
   check that drags past the last event. With the fix taken out it fails
   (148 ok, 2 fail). With the fix in, 150 ok.
2. **`extraction/split`, "its X-ray bundle is not on this machine"**, ten
   times from 14:56:50 to :56, on `980b57eab496`. Its v3 had been
   extracted 10 s before, in the new "fitted here" round. v3's records are
   `direct` and have no `bundle`. On disk, `_er_split_arrays` sends a direct
   record to `_er_direct_arrays` before it looks for a bundle, so v3 cannot
   give this message now. The traceback's line numbers (11123, 11044) do
   not match the file (about 11395 and 11179 now). The server was running
   older code than was on disk while the other session built that round.
   After the restart at about 15:51, Bite-line cuts on the same folder went
   through (15:55:48). Old code. I changed nothing.
3. **`rootcanal/workflow-save`, "There is no saved pool None to use as the
   target."**, at 12:01:36 and 12:01:47 (`kind: pspike`). The new P-spike
   workflow `4e5ce690d4b1` was saved at 12:02:05, with the target "PTEN
   Baseline v2 (Optimized parameters)". A new workflow's pools are found by
   name (`byNick` in `openBuilder`, `web/js/rcworkflow.js`): "PTEN Baseline",
   then "PTEN ALL PTEN Baseline Full Incisor". Both are archived in the
   shared prefs (`0fb7e710f1b9`, `f669e8c87dc9`). The one on show is named
   "… v2 (Optimized parameters)", and `byNick`'s "v2" rule allows nothing
   after the number. So the builder opened on "Select pool", Save sent
   `{artifact_id: null}`, and `_wf_pool` printed the null. Fixed in
   `2026.11.13.1`. Save and Preview now say which pool to pick, using the
   button's own words, and send nothing. The server's words never say
   "None". `web/_dev/rcworkflow.html` has a new section, "A POOL NOT YET
   PICKED" (3 checks). With the fix taken out, Save goes through and the
   section throws at its next step (127 ok, 3 fail). With it in, 186 ok.
   `tools/check_wf_pool_unpicked.py` gives 6 ok, and 3 fail with `--head`.
   **For the user:** whether a new workflow should start on the renamed
   pools. Which pools it starts on is your choice, so the defaults are
   left as they are.
4. **Floss on Strawbarry, ticket `20261109-102332-eca9`** (Rain, 11-09
   10:23, `2026.11.06.4`). The ask: "When selecting Panning from Toolkit,
   'Reading Panning's sets' shows up for a long time … This should be much
   faster to load." Floss failed at once with "[WinError 2] The system
   cannot find the file specified". The ticket has no `head` and no `run`,
   so it stopped in `_prepare`, while copying the code. The message names
   no file, so a program could not be started. The only one `_prepare`
   starts is git, and `floss._git` asked for plain "git". Every other git
   call in Jarvis goes through `store.git_exe()`, made on 10-07 for a
   computer that has only GitHub Desktop's git. That is how Strawbarry's
   reports get their commit. Fixed in `2026.11.13.1`: `_git` uses
   `store.git_exe()`. `tools/check_floss_git.py` hides git from PATH.
   Before the fix it gives the ticket's own error, and after it, 2 ok.
   `tools/check_floss.py` still gives 8 ok. Needs a restart, and Strawbarry
   gets it when it pulls. I cannot see Strawbarry's PATH, but nothing else
   in `_prepare` gives that message. `inside.py`, `notes.py`, `sanity.py`,
   `sysinfo.py` and `weekly.py` also call plain "git". No fault has come
   from them, so I left them alone. **For the user:** Rain's ask itself
   (Panning's sets are slow to load) is a speed request, not a fault, and I
   did not look into it. The ticket is still open in
   `tools/floss_inbox.py --remote`. I did not mark it, because it is
   Strawbarry's file.
5. **"Stuck" rows** (cloud `activity`): 30. None is `GET /api/link`.
   - Bluebarry: `GET /api/rootcanal/meta` took 32–35 s four times, ten
     minutes apart (15:48, 15:59, 16:09 and 16:19Z). That is the Meta
     Workflow page's own poll (`web/js/rcmeta.js`). The route reads the
     payload of every Root Canal workflow to find the Ambiguous ones, and
     those snapshots are 5–6 MB each. I did not measure it. Also
     `GET /api/rootcanal/workflows` took 51 s (20:51Z) and 31 s (21:44Z),
     and `rootcanal/candidates` 35 s (17:30Z). There was one 5.4 s
     longtask (17:02Z). The cluster of ten at 16:51Z is a restart. These
     are the other session's Root Canal pages, still being built. Slow, not
     broken; left open.
   - Strawbarry at 18:12:55Z and Blackbarry at 18:19:20Z: the start-up
     clusters seen before (`registry` 35 s, `csc/open`, `prefs`, `firstrun`
     and others).
   - Blackbarry: `POST /api/session/state` took 42 s at 18:27:24Z
     (Xplorefinder), then "Working on a curation set" took 31 s at
     18:31:43Z. That is pass 17's open item, ten times since 11-09.
   - DESKTOP-AH45FAE is Rain's: 17 actions since 10-15, the last at 21:56Z
     on 11-12. "Reading the recording list" took 34 s at 21:55:04Z, a
     first start.

What changed, all in `2026.11.13.1` and uncommitted:
- `web/js/extraction.js`, in `dragCut` (around lines 1093–1113): `u`,
  `inside`, and `inside(...)` around the pointer's place.
- `web/js/rcworkflow.js`: `missingPool` and `sayMissingPool` just above
  `previewBuilder` (around 4285–4311), and one line in `saveBuilder`
  (around 4336).
- `backend/app.py`: `WF_POOL_UNPICKED` and the `if not aid` at the top of
  `_wf_pool` (around 17033–17050).
- `backend/floss.py`, in `_git` (around 163). That file had no other
  uncommitted work.
- Checks: `web/_dev/extraction.html` ("PAST THE LAST EVENT", around 453),
  `web/_dev/rcworkflow.html` ("A POOL NOT YET PICKED", around 1144), and
  the new `tools/check_wf_pool_unpicked.py` and `tools/check_floss_git.py`.

Every other hunk in `app.py`, `extraction.js`, `rcworkflow.js` and the two
harnesses is the other session's uncommitted 11-11 and 11-12 work. With
everything on disk: `extraction.html` 150 ok, `rcworkflow.html` 186 ok,
`rcmeta.html` 31 ok, `tools/check_rcmeta_persist.py` 7 ok,
`tools/check_wf_border_lend.py` 7 ok. As in pass 17, each harness server's
start rewrote `GUI_logs/prefs/workbench@desktop-4h65ai7-d565.json` as it
merged prefs. Only its `updated` stamp is from today, and no value came
from a harness.

Builds: Bluebarry's 11-12 report says `2026.11.12.4 de71a7fc`. HEAD here is
still `de71a7fc`. The other session's `2026.11.11.5` to `2026.11.12.5`,
pass 17's `2026.11.12.1` and this pass's `2026.11.13.1` are all
uncommitted. Strawbarry ran `24e7b82f` from 11-09 to 11-11, and Blackbarry
`06e48c9b` on 11-10. Neither has pulled past `b896bd29` yet, so neither
has `2026.11.07.2` (DS-PCA). Aggie's Mac ran `d972b0bd` until 11-10, and
`233b1502` from 11-12, which has it.

Next pass: Bluebarry's 11-13 report and shard. Then Strawbarry's and
Blackbarry's 11-12 reports when git brings them. Both used Jarvis on 11-12
and have no cloud `errors` rows. Then `git fetch`, then the cloud from
`2026-11-13T13:45Z`. If "That cut leaves every event on one side" appears
on a Jarvis loaded after this change, find out which page sent it: the
card (`extraction.js`) or Compare. If Floss fails on Strawbarry after it
pulls past this change, run `tools/check_floss_git.py` there. Count the
`POST /api/session/state` stalls and the `rootcanal/meta` polls over
30 s.

## Pass 17: 2026-11-12 (morning, scheduled), 11-09 08:50 to 11-12 09:00

The scheduled passes of 11-10 and 11-11 did not run. Both stopped as they
started because of a usage limit ("weekly limit", then "5-hour limit"; see
`%LOCALAPPDATA%\JarvisTriage`). So this pass covers three days.

Covered: Bluebarry's 11-09, 11-10 and 11-11 reports and shards. The
reports that came by git in `de71a7fc` (11-11 15:52): Strawbarry's 11-06
to 11-08 and Blackbarry's 11-05 to 11-09. The shard `11-09@Strawbarry`.
`git fetch` brought nothing new: `origin/master` is `de71a7fc`, the same as
HEAD. Floss: 0 open. I also read the cloud, without writing to it, from
`2026-11-09T13:45Z`: 32 `errors` rows (the same records as the shards) and
53 `client.error` rows. Strawbarry has no activity after 11-09 21:29Z.
Blackbarry's last activity is at 11-10 20:55Z, and its 11-10 report has not
come by git yet.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 11-05 | Blackbarry (Isabella) | 1 | `cloud.sync` HTTP 520, already read in pass 12 from the shard. Not a fault |
| 11-06 | Strawbarry (Rain) | 0 | 243 actions, build `2026.11.06.1 47b7b5c1` |
| 11-06 to 11-08 | Blackbarry | 0 | 0 actions |
| 11-07, 11-08 | Strawbarry | 0 | 0 actions |
| 11-09 | Blackbarry (Isabella, Avery Sullenberger) | 0 | 353 actions, build `2026.11.06.4 a76eae4b` |
| 11-09 | Strawbarry (Angelina Woychosky) | 1 (shard and cloud; no report yet) | DS-PCA opened on a harness seed. This is pass 14's fault, on code without its fix (1) |
| 11-09 | Bluebarry (Shahriar) | 0 (16 test) | X-ray Many and DS-PCA harness probes |
| 11-10 | Bluebarry | 0 (10 test) | one is a real bug behind a test flag, already fixed by the other session (2) |
| 11-11 | Bluebarry | 0 (5 test) | one is a real race behind a test flag. **Fixed** (3) |
| 11-09 to 11-11 | all three | 52 "stuck" rows, 1 other | slow, not faults. One pattern is left open (4) |

1. **Strawbarry `dspca/plan`, "This set (harness dupes) is not attached
   to a recording"**, 11-09 at 21:54:02Z (16:54 local), Angelina Woychosky,
   with no `test` flag. It is the fault pass 14 fixed in `2026.11.07.2`.
   The traceback's line numbers (8532, 4998) match `24e7b82f`, Rain's merge
   on Strawbarry at 10:19 that day, and the commits after it up to
   `a76eae4b`. None of them has `firstReadable` in `web/js/dspca.js`. The fix was committed only on 11-11 at 15:52, in
   `b896bd29`. So this is the old code, not a failed fix. There is no
   activity row after 21:29Z, so nothing shows anybody picking the set: the
   panel opened on it by itself, as on 11-07.

   Why that set: the seed `5360afb7c67c` (HARNESS m99 s1, `harness dupes`,
   added by Debug_Bot on 10-22, no gid) is the **newest** dentate spike set
   in the bank, and DS-PCA's list is newest first. The seed is in git
   (`GUI_logs/event_bank/harness_m99_s1_5360afb7c67c@barrylab-d8e8.json`
   and `@desktop-4h65ai7-d565.json`, committed 11-03 in `6bb57fc1`), so
   every clone has it. It is one of **80 harness seeds in the bank in git**
   (229 files, all added by Debug_Bot between 09-21 and 10-22). 29 of the
   93 curated DS sets in the bank are such seeds, none of them on a
   recording. Braces opens on the first set that has a gid, and DS-PCA now
   opens on the first readable one, so neither opens on a seed by itself.
   The seeds are still listed in both. **For the user:** whether to take
   the 80 seeds out of the shared bank. It changes everybody's bank.
   Deleting the files here would only leave uncommitted deletions, and
   other clones keep their copies unless a tombstone removes them. So it
   belongs in the app's own delete, and it is your decision. I changed
   nothing.
2. **Bluebarry `extraction/round2`, "name 'np' is not defined"**, 11-10 at
   17:02:43, `test: true`. This was a real bug behind a test flag.
   `_er_round2_rows` in `backend/app.py` called `np.mean` without importing
   numpy, so Round II would have failed for anybody. That was the day the
   Extraction Room first shipped (`2026.11.10.1`). The other session has
   fixed it: the function now starts with `import numpy as np`, and that
   is committed (`b896bd29`). `web/_dev/extraction.html` drives Round II.
   No check added.
3. **Bluebarry `rootcanal.meta.state`, "[WinError 32] The process cannot
   access the file because it is being used by another process:
   ...rcmeta\runs.json.part -> ...rcmeta\runs.json"**, 11-11 at 15:29:16.
   It was `test: true`, from the harness server, with no request around
   it. It is a real race. When Run is pressed on a Meta Workflow, the
   request (`api_rootcanal_meta_run`) and the run's own thread
   (`_meta_loop`) each call `_meta_persist(force=True)` at the same moment.
   Both wrote through the one scratch name `runs.json.part`. On Windows,
   while one writer holds the scratch file, the other's rename fails. I
   measured it standalone: two writers at once collide in 186 of 200 tries.
   For a person, pressing Run would have filed this as a real fault. The
   run itself goes on.

   Fixed in `2026.11.12.1`. A lock (`_META_WRITE`) lets one writer in at a
   time. A copy of the runs is taken whole under it. The write goes through
   `shards.write_json_atomic`, which uses a private scratch name and retries
   the rename. `tools/check_rcmeta_persist.py` compiles app.py's own
   `_META_*` lines and `_meta_persist` against a temp folder, so nothing
   under GUI_logs is touched. On the code on disk: 7 ok, five runs in a
   row. With `--head`: 2 of 7 fail, with "being used by another process",
   and with "Access is denied" when something holds runs.json open.
   `rcmeta.html` still passes (31 ok), and so does
   `tools/check_wf_border_lend.py` (7 ok). Needs a restart. **My hunks in
   `backend/app.py` are the two at `_META_SAVED` / `_meta_persist` (around
   lines 17376 and 17410).** The other hunks there (`import collections`,
   and the Extraction Room's `_er_splits` and the rest) are the other
   session's uncommitted `2026.11.11.5`/`.6` work.
4. **"Stuck" rows** (cloud `activity`, `where: stuck`): 52 of them. There
   was also one `arc.spark.clipping` on Bluebarry at 11-10 21:17:43Z. It
   came from port 8791 (the harness server), which asked for a 7 s window
   on purpose. None of the rows is `GET /api/link`, so pass 11's fix holds.
   - Most are clusters of four to six routes passing 30 s at the same
     moment. Strawbarry, 11-09 15:21–15:24Z (Rain, just after start-up:
     `registry` took 35 s). Blackbarry, 11-09 and 11-10 (Isabella and
     Avery). Passes 12 and 13 saw the same.
   - **`POST /api/session/state` (saving how a recording is being viewed)
     took 30 to 57 s nine times.** Blackbarry on 11-09 at 15:50, 15:59
     (57 s), 16:32 and 17:07Z, and on 11-10 at 18:56, 20:16 and 20:41Z.
     Strawbarry on 11-09 at 15:24 and 18:42Z. Pass 12 saw it once and
     asked to watch for it. Each time, the feed lines show "Checking which
     records have reached the shared database" or "Working on syncstate"
     starting a few seconds before. Then comes "Working on this recording",
     and nothing more. At 20:16:49Z on 11-10 the save was the only slow
     request (36.5 s), so it is not only the browser queueing behind other
     slow requests. `STORE.upsert_session` holds the store's lock (`_LOCK`
     in `backend/store.py`) for the whole save, so something else holding
     that lock is a guess. I did not measure it, and the route behind that
     feed line (`api_cloud_items` in `backend/syncitems.py`) does not take
     the lock itself. Left open: it is slow, not broken, and finding what
     holds it up needs a measurement on Blackbarry.
   - Bluebarry: `dspca/raster` 34 s (11-09 22:24Z), and on 11-11
     `doppler/estimate` 31 s, `extraction/extract` 30 s and 35 s, and
     `rootcanal/candidates` 38 s. That is heavy work during the other
     session's development. Not faults.

A side effect of this pass: the harness server for `rcmeta.html` (08:59)
rewrote `GUI_logs/prefs/workbench@desktop-4h65ai7-d565.json`. As it started,
it merged in Blackbarry's prefs changes of 11-09, which had come by git:
`xf_simplify_panning`, `panning_at`, `gobble`, Blackbarry's theme and its
`jarvis` flag. Each carries its 11-09 time, and the merged values are the
ones every Jarvis already reads. No value came from the harness. Bluebarry's
own Jarvis does the same on its next start, so I left the file as it is.

Builds: Bluebarry's reports say `2026.11.09.4`, `2026.11.10.1` and
`2026.11.11.4`, each with `11fcd58a`. The commit is read once, when Jarvis
starts, and HEAD here stayed at `11fcd58a` until `b896bd29` at 15:52 on
11-11. So that commit is correct, not a sign of a stale build. Everything
up to `2026.11.11.4` is committed and on origin (`de71a7fc`).
`2026.11.11.5` and `.6` (the other session's) and `2026.11.12.1` (this
pass) are uncommitted. On 11-09 Strawbarry ran code from `24e7b82f` or a
little later, but before `b896bd29`. Blackbarry
ran `2026.11.06.4 a76eae4b`. Neither has `2026.11.07.2` (DS-PCA) until
it pulls past `b896bd29`.

Next pass: Bluebarry's 11-12 report and shard. Then Blackbarry's 11-10
report and Strawbarry's 11-09 report, when git brings them. Then `git
fetch`, then the cloud `errors` and `client.error` rows from
`2026-11-12T13:45Z`. If `rootcanal.meta.state` appears again on a Jarvis
started after this change, run `tools/check_rcmeta_persist.py` first. If
DS-PCA opens on "harness dupes" on a machine past `b896bd29`,
`firstReadable` has failed. Count the `POST /api/session/state` stalls
again.

## Pass 16: 2026-11-09 (morning, scheduled), 11-08 08:50 to 11-09 08:50

Nothing new. Bluebarry's 11-08 report (build `2026.11.06.4 11fcd58a`,
written 18:16): 0 faults, 0 actions. Jarvis was running but nobody used
it. There is no 11-08 or 11-09 shard. `git fetch` brought nothing:
`origin/master` is still `83b3c701` (`.DS_Store` only). Strawbarry's
11-06 and Blackbarry's 11-05 reports have still not come by git. Floss:
0 open. In the cloud, read only, from `2026-11-08T13:45Z`: 0 `errors`
rows, 0 `client.error` rows and 0 `activity` rows from any machine. As a
control, the same query from `2026-11-07T13:45Z` returns pass 15's 15
Bluebarry errors and 78 actions, so the query works and the silence is
real. `tools/check_wf_border_lend.py` still passes (7 ok). No code
changed. `2026.11.07.1` to `.3` are still uncommitted.

Next pass: Bluebarry's 11-09 report and shard. Then Strawbarry's 11-06
and Blackbarry's 11-05 reports when git brings them. Then `git fetch`,
then the cloud `errors` and `client.error` rows from `2026-11-09T13:45Z`.

## Pass 15: 2026-11-08 (morning, scheduled), 11-07 13:05 to 11-08 08:50

Nothing new. Bluebarry's 11-07 report (build `2026.11.06.4 11fcd58a`):
0 faults, 97 actions, 15 left out. Those are the shard's 15 records,
all read in pass 14 (the `harness dupes` row is left out by the
`harness` pattern). The shard has nothing after 13:06, and there is no
11-08 shard. `git fetch` brought nothing new: `origin/master` is still
`f26427e1`/`83b3c701` (`.DS_Store` only). Floss: 0 open. In the cloud,
read only, from `2026-11-07T13:45Z`: the same 15 Bluebarry `errors`
rows, 0 `client.error` rows, and activity only from Bluebarry (78
rows, 17:54Z to 18:27Z). No other machine ran Jarvis on 11-07.
`tools/check_wf_border_lend.py` still passes (7 ok). No code changed.
`2026.11.07.1` to `.3` are still uncommitted.

Next pass: Bluebarry's 11-08 report, if Jarvis runs today (a Sunday).
Then Strawbarry's 11-06 and Blackbarry's 11-05 reports when git brings
them. Then `git fetch`, then the cloud `errors` and `client.error` rows
from `2026-11-08T13:45Z`.

## Pass 14: 2026-11-07 (afternoon, by hand), 08:50 to 13:05

Covered: the raw shard `11-07@desktop-4h65ai7-d565` (no report yet), the
Floss inbox (`tools/floss_inbox.py --remote`: 0 open), `git fetch` (nothing
new), and the cloud `errors` and `client.error` rows from `13:50Z`, read
only. Nothing from other machines. Note for the next pass: the cloud
`errors` table has `where_`, not `where`, and neither table has `user`.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 11-07 | Bluebarry | 1 (9 test) | fixed in `2026.11.07.2` (1) |

1. **`dspca/plan` at 12:56:05, "This set (harness dupes) is not attached
   to a recording".** `harness dupes` is `web/_dev/bankdupes.html`'s seed,
   banked into the LIVE app's bank for a few seconds (the harness was run
   against the live app, not `tools/harness_run.ps1`). A top-level window
   on the live app, so no `X-Barry-Test`, opened DS-PCA in those seconds.
   `loadCandidates` in `web/js/dspca.js` auto-picked `cands[0]`, the newest
   set, although `/api/dspca/candidates` had marked it `readable: false`.
   Any real set with no gid would do the same. It now uses
   `firstReadable`, the recording picker's rule. `web/_dev/dspca.html` has
   three new checks (308 ok). The 9 test faults are Root Canal and
   `ui/mode.bounce` harness probes.

## Pass 13: 2026-11-07 (morning, scheduled), 11-06 08:50 to 11-07 08:50

Covered: Strawbarry's 11-05 report (on disk since 11-06 12:11),
Bluebarry's 11-06 report and the raw shard `11-06@desktop-4h65ai7-d565`.
There is no 11-07 shard yet. `git fetch` brought `f26427e1`/`83b3c701`
(Shahriar, 11-06 15:21), which changed only `.DS_Store`, with no report.
I also read the cloud, without writing to it: the `errors` table from
`2026-11-06T13:50Z`, and the `activity` table's `client.error` rows from
the same time. The column is `action`, not `kind`, and `errors` has no
`shard` column. The cloud's last activity row is Bluebarry's, at 22:22Z
on 11-06.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 11-05 | Strawbarry (Aggie Krempasky) | 0 | 297 actions, build `2026.11.05.5` |
| 11-06 | Bluebarry (Shahriar) | 0 (34 test) | all `test: true`, from the other session's Root Canal harness runs (1) |
| 11-06 | Strawbarry (Maddie Massad, Aggie, Rain) | 0 (cloud) | 241 actions, nothing in `errors`. Its report has not come by git yet |
| 11-06 | both | 20 `client.error` rows | 18 "stuck" (slow), 1 longtask, 1 from a script run in the page. None is a fault (2) |

1. **Bluebarry's 34 test faults** came in two runs, 13:11–13:14 and
   16:28–17:19 local: `rootcanal/fit` and `pool-fit` probes on
   `harness-none`, `harness-nope`, `hb-1` and `hb-other`. Three were
   different: **`rootcanal/pool-fit`, "PTEN m51 s1 2025-04-08 is in this
   pool twice: as the read cached here (not banked) and as the read
   cached here (not banked)"**, at 16:56:56, 17:07:23 and 17:08:30. That
   was `web/_dev/rootcanalpool.html` ticking m51 s1's DS set and its
   Panning set. Panning's sets became pool candidates on 11-06, in the
   other session's uncommitted work. That session has since made the
   harness pick recordings by gid, and made the picker swap one set for
   the other (`toggleMember` and "Select all" in `web/js/rootcanal.js`).
   The server refused correctly. I changed nothing. **For the other
   session:** when both members are reads cached here,
   `_rootcanal_member_kind` in `backend/app.py` describes them in the
   same words, so the refusal does not say which one to keep. The
   members already carry `set_type` ("ds" or "pooled"), so the wording
   could name "its DS set" and "its Panning set". A person would only
   see this with a pool saved holding both, before the picker's guard
   existed. That pool's two rows have different ids, so the row's "counted
   twice" warning would not show either. I left it alone because it is
   that session's feature and still in progress.
2. **`client.error` rows in `activity`:**
   - **First registry read after a start, 30–35 s, three times.**
     Strawbarry at 17:12–17:13Z (Aggie, right after "Ready"):
     `GET /api/registry` took 30 s, and `csc/window`, `vacc/signin/state`,
     `presets/support_panels` and `people` each waited about 30 s
     behind it ("arranging recordings 50 of 2,039"). Bluebarry at
     17:18Z: ten routes at 30–35 s just after the 12:17 local restart
     ("Loading the analysis libraries — done in 15.2 s"), on a page left
     open since the day before. Bluebarry at 19:39Z: `registry` 34.6 s
     and `csc/window` 30.4 s just after "Ready". Pass 12 saw the same on
     Strawbarry on 11-05. The small routes that wait are likely queued
     in the browser behind the slow ones, not held by the server. I did
     not measure that. It is slow, not broken. Whether to warm the
     registry at start-up is a performance choice and is left open.
   - Strawbarry at 18:02:34Z (Maddie Massad): ToolKit's curation pane
     spinner ("reading the curation sets", then "reading the recording
     registry", `web/js/toolkit.js` ~1620) ran 30 s after they left
     Panning. Its last request was `/api/vacc/knows` matching 2,039
     recordings, which reads the registry. It is the same slowness as
     above. They went on working a minute later.
   - Bluebarry at 18:00:26Z (13:00 local): "Uncaught TypeError: Cannot
     read properties of null (reading 'click')" at `<anonymous>:6:78`.
     The only thing around it is `link.scope` rows a minute apart in the
     Sessions view. That is a script run inside the live page (CDP or
     the console), most likely the other Claude session driving the app,
     not Jarvis's own code. It is not a fault.
   - Bluebarry at 22:19:11Z: a 1.0 s longtask during Root Canal pool
     work. Not a fault.
   - None of the `stuck` rows is `GET /api/link`, so pass 11's fix holds
     everywhere. There was no repeat of pass 12's 34 s
     `POST /api/session/state`.

`tools/check_wf_border_lend.py` still passes (7 ok) on the code on
disk. The other session went on editing `_wf_definition` on 11-06.
"No border to lend" did not appear anywhere.

Builds: Bluebarry's 11-06 report says `2026.11.06.4 11fcd58a`.
Everything up to `2026.11.06.4`, including passes 11 and 12, is now
committed and on `origin/master` (`git log origin/master..HEAD` is
empty). Strawbarry ran `2026.11.05.5` on 11-05, so it had pass 11's
fixes but not `2026.11.05.6`'s workflow fix. The other session's Panning
pool work is still uncommitted, so it is on Bluebarry only. No code
changed this pass, so there is no CHANGELOG entry.

Next pass: Bluebarry's 11-07 report, if Jarvis runs today (a Saturday).
Then Strawbarry's 11-06 report and Blackbarry's 11-05 report when git
brings them. Blackbarry used Jarvis on 11-05 but has written no report
since 11-04. Then `git fetch`, then the cloud `errors` table and
`activity` `client.error` rows (`action=eq.client.error`) from
`2026-11-07T13:45Z`.

## Pass 12: 2026-11-06 (morning, scheduled), 11-05 09:05 to 11-06 08:50

Covered: Bluebarry's 11-04 and 11-05 reports, Blackbarry's 11-02 and 11-04
reports (on disk since 11-05 13:53), and the raw shards
`11-05@desktop-4h65ai7-d565` and `11-05@Blackbarry`. `git fetch` brought
`a1e00da3` ("Lock", and two "Curation" commits), with no report in them.
I also read the cloud, without writing to it: the `errors` table from
`2026-11-05T14:05Z` (the column is `where_`, not `where`), and the
`activity` table's `client.error` rows from the same time. Strawbarry
has no 11-05 report here yet.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 11-04 | Bluebarry | 0 (58 test) | as pass 11 read from the shard |
| 11-02 | Blackbarry (Isabella) | 1 | "JWT issued at future": the one pass 9 fixed, arriving again by git |
| 11-04 | Blackbarry | 0 | 0 actions, build `2026.10.30.3` |
| 11-05 | Blackbarry | 1 (shard) | `cloud.sync` HTTP 520 at 18:36Z: Supabase was not answering. Jarvis backed off as it should. Not a fault |
| 11-05 | Bluebarry (Shahriar) | 3, 2 distinct (78 test) | both Root Canal Workflow. Already fixed by uncommitted `2026.11.05.6`. **Check added** (1) |
| 11-05 | all | 5 "stuck" rows | slow, not faults (2) |

1. **`rootcanal/workflow-save`, "'Verified P-Spike' has not been run yet,
   so it has no border to lend"**, kind `ambiguous`, at 17:06:50 and
   17:07:10. Here is what happened, from the artifact `abe99ac5d1b6`:
   - v1 was the definition, at 16:24:10;
   - v2 was the run, at 17:04:05, with 1381 kept;
   - v3 was the same definition saved again at 17:04:09 ("Definition
     changed"), with no run of its own.

   `_wf_definition` read only the newest version, so it found no run.
   The other Claude session's uncommitted `2026.11.05.6` fixes exactly
   this with `_wf_last_run` (`backend/app.py` changed at 17:08). The
   tracebacks are the code from before that change: their line numbers
   are older, and the message has no "Run it first". Nothing checked the
   fix, so I added `tools/check_wf_border_lend.py`. It builds that history
   in memory and touches nothing under GUI_logs. On the code on disk:
   7 ok. With `--head` it compiles HEAD's own `_wf_definition` and
   `_wf_current` into the process: 3 of 5 fail, with Shahriar's exact
   message. I did not edit the other session's files. My only changes
   are the new check and the CHANGELOG entry `2026.11.06.1`, which is a
   check only and needs no reload.

   **`rootcanal/workflow-run`, "5 of the hand-sorted set(s) could not be
   measured here … Read it first"** at 16:24:23 (build `2026.11.05.5`,
   the version stamped on v1). It was a refusal with instructions, not a
   crash. `2026.11.05.6` now makes the run prepare the sets itself. The
   real run at 17:04:05 then measured them (1381 kept). No check added:
   `web/_dev/rcworkflow.html` (65 checks in that session's entry) covers
   the new run path.
2. **"Stuck" rows** (cloud `activity`, `where: stuck`):
   - Strawbarry, 15:22Z and 15:27Z: the old record format, with the route
     after the feed lines. The second one is `GET /api/link` (37 s), so
     Strawbarry was on a build older than `2026.11.05.1` then, as pass 11
     said to expect.
   - Strawbarry, 17:32Z: the new format. `GET /api/registry` took 30 s
     just after start-up ("Ready", then "Reading the recording list"):
     the first registry read is slow.
   - Blackbarry, 19:04Z and 19:07Z: the new format, so Blackbarry had
     updated past `2026.10.30.3` by then. `POST /api/csc/window` and
     `POST /api/session/state` each took 34 s while a curation set was
     being worked on, 30 minutes after the 520. A save of session state
     taking 34 s is odd. Watch for it again. With one row there is
     nothing to go on.

Not changed: on 11-05 at 15:22 and 15:38, two `dspca/plan` "harness dupes"
rows had no `test` flag. The report already left them out by the
`harness` pattern, so a harness was running against the live app at
those times.

Builds: Bluebarry's 11-05 report says `2026.11.05.6 f85d2b51`. That is
the server that wrote it at 18:05, not the one that hit the faults.
`2026.11.05.6` and `2026.11.06.1` are uncommitted, so no other machine
has the fix yet. Bluebarry needs a restart after 17:08 on 11-05 to run
it.

Next pass: Bluebarry's 11-06 report, and Strawbarry's and Blackbarry's
11-05 reports when git brings them. Then `git fetch`, then the cloud
`errors` table (`where_`) and `activity` `client.error` rows from
`2026-11-06T13:50Z`. If "no border to lend" appears again on a build
with the fix committed, that is a real failure of `_wf_last_run`. Run
`tools/check_wf_border_lend.py` first.

## Pass 11: 2026-11-05 (morning, scheduled), 11-04 08:50 to 11-05 09:05

Covered: Strawbarry's 11-03 report (already at HEAD, `0aa728fe`), the raw
shards `11-04@Strawbarry` (synced) and `11-04@desktop-4h65ai7-d565`, and
the cloud, read-only: the `errors` table from `2026-11-04T13:50Z`
(`machine=neq.Bluebarry`; it has no `test` column either), Strawbarry's
`activity` around its fault, and every `client.error` row since 11-03.
`git fetch` brought `762235c0`/`ab65b008` (Rain, 11-04 16:05), with no
report in them. **Bluebarry has no 11-04 report:** its Jarvis stopped at
16:16 local, before 18:00, and nothing is listening now. The report gets
written on the first tick after it starts again.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 11-03 | Strawbarry (Rain) | 0 | 141 actions |
| 11-04 | Strawbarry (Rain) | 1 | `csc/window` WinError 3 after a folder rename. **Fixed** (1) |
| 11-04 | Bluebarry | 0 (58 test) | all `test: true`; 6 of them a real race behind a test flag. **Fixed** (2) |
| 11-03, 11-04 | both | 229 "stuck" rows | `client.error` / `where: stuck` in **activity**, not errors. 210 + 11 were false. **Fixed** (3) |

What changed (CHANGELOG `2026.11.05.1`):

1. **Strawbarry `csc/window`, "[WinError 3] The system cannot find the
   path specified: Y:\...\KCNT1_529_s1apr17\...\CSC1.ncs"** at 20:02:44Z.
   The cloud activity shows Rain opening 529 s1 at 19:45 and 19:51Z, then
   rescanning KCNT1_526, 529, 524 and 521 from 19:56Z: the folders were
   being renamed to the `m###` pattern (`KCNT1_m529_s1_apr17`, registry
   row `m529_s001_2026-04-17_12-55-27`, made 20:03Z). `_SESSIONS` kept the
   opening of the old folder, so the window read a file that was gone, and
   every later read of that path would have failed the same way. Now
   `_session_gone` in `backend/app.py` (only after a failed read, so no
   stat on Y: per window) lets go of the stale opening and says it plainly.
   `tools/check_csc_folder_gone.py`: 4 of 8 fail with it out, with exactly
   Rain's WinError 3; 8 ok with it in. Needs a restart.
2. **Joe export list, "cannot identify image file ...joepub\all\fig_P2_2.png"**
   (6 times, 14:31 and 15:14–15:15 local, each a different PNG, all whole
   now: 839 checked). `joefigs._save` writes PNGs in place, and
   `joeexport._preview` read one mid-write while the other session was
   redrawing tab 11–13's sets. They were `test: true` only because a
   harness asked; a person with tab 10 open during a redraw gets the same
   500. Now an unreadable PNG keeps its last preview (or none) and the
   next listing makes it. `tools/check_joeexport_preview.py`: 3 of 7 fail
   with it out, 7 ok with it in. Needs a restart. I did not make
   `joefigs._save` write atomically: the PDFs and SVGs it writes are
   published too, and that is the other session's code.
3. **"Stuck" reports (new since `2026.11.03.x`, `web/js/solid.js` §4).**
   They go to the `activity` log as `client.error`, `where: "stuck"`, so
   **the day reports and the error shards never show them: read them from
   activity**. Of 268 rows since 11-03, 209 on Bluebarry and 11 on
   Strawbarry were xplore's `GET /api/link`, the long poll the server
   holds for 25 s on purpose. It was counted as a foreground request; past
   30 s it was filed once per 10 minutes per window, 12 an hour all night
   with nobody there. Held polls are now skipped (they still count as
   movement, as before). Also, the record put its route after 20 feed
   lines and was cut at 4000 characters, so 27 rows lost what they were;
   the route and kind now come first. `solid.html` has a new section: a
   40 s plain request is filed (the control), a 40 s link poll is not.
   1 fail with the skip taken out, 78 ok with it in. A page reload is enough.

Not changed, for the record:

- The other "stuck" rows are real but slow, not faults: Strawbarry's
  `csc/open`, `csc/window`, `registry`, `incisor/estimate`,
  `incisor/batch/plan`, `prefs`, `pick` and `prospector/accept` each went
  past 30 s on 11-04 while Rain worked off Y:. Worth watching if they grow.
- 4 registry records still point at the old 529 s1 folder (`sb63dd2b3ae81`,
  `sbc0daa6c7ae5`, `s480a3e4d88d9`, `sb1b95b460487`), all four the same
  folder under different gids, and 2 at the old 529 s2 folder
  (`s6435991bf573`, `s83c30a8c2649`). I checked only 529; 521, 524 and 526
  were rescanned the same afternoon and likely look the same. Which to
  retire after a rename is a registry decision; I did not touch them.
- `tools/check_joeexport_race.py` failed once right after
  `check_joeexport.py`: "[WinError 5] Access is denied" renaming a Prism
  zip's `.part` over the zip, most likely a scanner holding the fresh zip.
  It passes alone (5 ok). The Prism zip path does not retry the
  `os.replace`; nobody has hit it in the app yet.
- This pass's harness run touched `prefs/workbench@desktop-4h65ai7-d565.json`
  at 09:00:01: only its `updated` stamps moved, no values.

Open items B and C and the double-pool note stand as pass 6 left them.

Builds: Strawbarry ran `2026.11.03.2` (`0aa9ad6d`) on 11-04, older than
everything today. `2026.11.05.1` is uncommitted, so no other machine has it.

Next pass: Bluebarry's 11-04 report (written when its Jarvis next starts)
and 11-05. Then `git fetch`, then the cloud `errors` table from
`2026-11-05T14:05Z`, then the `activity` table's `client.error` rows with
`where: stuck` from the same time. If `/api/link` still appears there, it
is a machine on a build older than `2026.11.05.1`.

## Pass 10: 2026-11-04 (morning, scheduled), 11-03 07:50 to 11-04 08:50

Nothing new. Bluebarry's 11-03 report: 0 faults, 639 actions, 18 left
out, all `test: true` in the shard: 12 Errors-panel "Test error"
(`selftest`), 2 `dspca/plan` on "harness dupes" and 4 `ui/mode.bounce`,
all from `_dev/stratacheck.html` on port 8791. No 11-04 shard yet.
`git fetch` brought `0aa32f2a` (11-03 13:48) with Strawbarry's 11-02
report: 0 faults, 6 actions. The cloud `errors` table, read-only, has no
row from any other machine since `2026-11-03T12:50Z`. Strawbarry did 132
actions on 11-03 (last at 21:41Z) and filed nothing.

One note for open item **C**: the cloud `activity` table holds two
`device.rename` rows at 17:11:05Z on 11-03, by "zz probe person", one
under the machine name "zz test machine". They are `_dev/devicename.html`
renaming this computer and putting it back. It did put it back:
`prefs/device@desktop-4h65ai7-d565.json` says "Bluebarry" (its `by` field
says "zz probe person"). The rows reached the lab's shared history for
the reason C describes. No code changed. B, C and the double-pool note
stand as pass 6 left them.

Builds: Bluebarry ran `2026.11.03.2` (`5acf4b4f`), so it has restarted
since pass 9 and runs passes 4–8's fixes. `2026.11.03.1` is committed and on
`origin/master`, so the other machines get them on their next pull.
Strawbarry still ran `2026.11.02.1` (`b6232acc`) on 11-02.

Next pass: Bluebarry's 11-04, then `git fetch` (Strawbarry's 11-03), then
the cloud `errors` table from `2026-11-04T13:50Z`.

## Pass 9: 2026-11-03 (morning, scheduled), 11-02 16:40 to 11-03 07:50

Nothing new. Bluebarry's 11-02 report: 0 faults, 83 actions, 2 left out
(the Errors panel's own "Test error" at 17:03 and 17:06, `selftest`,
`test: true`). It has no 11-03 shard yet. `git fetch` brought nothing new
(`origin/master` is still `b6232acc`, Rain, 11-02 15:02, whose Strawbarry
reports pass 8 read). The cloud `errors` table, read-only, has no row from
any other machine after Blackbarry's JWT fault at 16:54Z on 11-02, which
pass 8 fixed. The cloud `activity` table has nothing from any other
machine after 20:11Z, so nobody else has used Jarvis since. A new person
did use it earlier on 11-02: `akrempas@uvm.edu`, on a machine that calls
itself `ip0af550d3.int.uvm.edu` (a Mac's network name, so it may change).
Their first action in the cloud is at 15:08Z, with the welcome opening by
itself at boot. They did 25 actions and hit no faults. Jeremy's MacBook (13 actions) had no faults either. No code
changed. Open items B and C and the double-pool note stand as pass 6 left
them.

Builds: Bluebarry ran `2026.11.02.2` (`c134d1ed`) on 11-02, so **pass 8's
sync fix (`2026.11.02.3`) and `2026.11.02.4` still need a restart
there**. `.2`, `.3` and `.4` are all uncommitted, so no other machine has
them.

Next pass: Bluebarry's 11-03, then `git fetch`, then the cloud `errors`
table from `2026-11-03T12:50Z` (`machine=neq.Bluebarry`, no `detail`;
the column is `where_`, not `where`, and there is no `user`).

## Pass 8: 2026-11-02 (afternoon, by hand), 11-02 07:50 to 16:40

Covered: what had arrived since pass 7. From `origin/master` (fetched, not
pulled): Strawbarry's 10-30, 10-31 and 11-01 reports. On disk: Blackbarry's
10-29 to 11-01 reports (Isabella, `lcom549913-e62b`), and two raw shards
synced today, `10-30@Strawbarry` and `11-02@Blackbarry`.

| Day | Machine | Real faults | Verdict |
|---|---|---|---|
| 10-30 | Strawbarry (Rain) | 1 | `braces/decide` hold refusal, the one pass 6 traced to old code. Nothing new |
| 10-31, 11-01 | Strawbarry | 0 | 0 actions |
| 10-29 to 11-01 | Blackbarry | 0 | 259 actions on 10-29, none after |
| 11-02 | Blackbarry (Isabella) | 1 | `cloud.sync` "JWT issued at future". **Fixed**, below |

1. **"JWT issued at future" was blamed on the computer's clock.** The
   message told Isabella to set her clock, and `cloud_sync_once` paused
   automatic sync for ten minutes. But the key is an `sb_secret_` key:
   Jarvis signs nothing, and Supabase's gateway mints the JWT on its own
   clock. So PGRST303 is skew between Supabase's servers. Bluebarry, whose
   clock Windows keeps, had it five times (09-03, 09-04 twice, 09-05,
   10-07), always alone. Now `_cloud_skew` in `backend/app.py` makes it a
   brief failure: no `blocked`, the short backoff, and logged only if the
   next attempt fails too. The hint in `backend/cloud.py` `_explain` says
   what it is. 5 new checks in `tools/check_syncitems.py`, all pass.
   Needs a restart.

Builds: every other machine is still on `2026.10.27.1`. Nothing from
passes 4–8 has reached them, because none of it is committed.

Next pass: from 11-02 16:40. `git fetch`, then the cloud `errors` table
from `2026-11-02T21:40Z`. Also new this pass: the Thanksgiving theme
(`2026.11.02.3`, `web/js/thanksgiving.js`) switches every machine once in
November. A fault whose `where` or stack names `thanksgiving.js`, or a
"button did nothing" report, may be Sir Gobbles sitting on the button. That
is by design: he takes the click and shoos.

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
