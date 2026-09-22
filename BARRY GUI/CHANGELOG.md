# BARRY GUI — patch notes

Versions are dated, because BARRY ships continuously out of this repo: there
is no release to number, only the state everybody last pulled. The version in
the rail is the newest entry below, and the commit beside it is what this
machine is actually running — if those two disagree with a colleague's, one
of you has not pulled.

More than one goes out on most days, so the date carries a counter:
`2026.09.08.1`, then `.2`. Same day, next version. The counter starts at 1
rather than being left off the first one, so every version reads the same way
and "is that the first or the only one" is never a question.

This file is the only place the version is written. The app reads it.

---

## 2026.09.22.2 - Two stamps on one time is a flag, not a dead end

### Added

- **An `overlapping` pass in the review.** Two stamps sent to the same time
  are one event written twice rather than two events, and the bank has
  always refused to write it. What it said was "2 stamp(s) would land on a
  time another stamp already holds" — true, and useless: the times were the
  bank's, and what the person reading it had was a list of twelve hundred
  rows.

  It is now a flag like any other, except that it is worked out from the
  decisions rather than measured when the set is made — nothing can know it
  until somebody has moved something, and it stops being true the moment
  they move it back. So it is raised by a decision and cleared by one, and
  every route out of it works: move one of the pair off, leave one where it
  was, or decide one was never an event.

  It has a pill in the table, a colour of its own in the stamp list, and it
  is included in the bench's pass, so stepping through the flags walks onto
  it rather than past it. The bar names the stamp it collides with, which is
  the thing that cannot be seen on the trace — the pair are a tenth of a
  millisecond apart and drawn on top of each other. Banking a set that has
  one refuses as it always did, and now puts you on the first of them.

---

## 2026.09.22.1 - A hand-moved stamp can cross its neighbour

### Fixed

- **An alignment could not be banked if a reviewer had moved a stamp past
  its neighbour.** The last check before the write sorted the outgoing
  stamps, compared that against the order they were built in, and refused
  the whole write if the two disagreed: "The alignment reordered the
  events, which the no-crossing rule makes impossible -- so something
  upstream is wrong." Nothing upstream was wrong.

  The no-crossing rule holds over the peaks `braces.assign` hands out
  itself. It says nothing about the two things that come after it. A
  reviewer dragging a stamp onto the peak it plainly belongs on is bound by
  nothing but the window -- the bench allows the drag anywhere within
  ±100 ms of where the stamp sits -- and a stamp left where it was, by a
  `keep` or by having no peak in reach, does not move aside for a
  neighbour that does. Both are legitimate alignments, and both arrived at
  the bank as a refusal.

  Two of them in `M8s9feb8`, a set of 1213 stamps with an afternoon of
  review on it: one stamp hand-placed at 722.538 s, 10 ms ahead of the
  neighbour that aligned to 722.549 s, and another moved to 1780.893 s,
  14 ms past the one that landed on 1780.879 s. Everything else about the
  set was right, and none of it could be banked.

  The write now sorts by where each stamp ends up -- the order every other
  write to this bank keeps, and the order a version reads back in -- rather
  than refusing. Nothing is lost by the sort: `from_t` travels on the event,
  so a stamp that changed places still says where it came from. The report
  and the version record both carry `resorted`, the number of stamps that
  changed place, so a version whose set was reordered says so.

  Two stamps landing on ONE time is still refused. That is a duplicate
  rather than an alignment, and it is a different fact about the set.

---

## 2026.09.21.9 - Leaving the trace view cannot strand you in it

### Fixed

- **"Back to the proposal" did nothing, and the proposal could not be
  banked.** `exitView` set `view` to null and then read `view.list` four
  lines later. That throws, and everything after the throw never ran —
  including the line that brings the panel back. So the button appeared to
  do nothing, the trace view kept the keyboard, and the proposal, with the
  button that banks it, was unreachable. From a colleague's log:

      client.error  detail=exitView@...  message=TypeError: can't access
      braces.enter  set=br52367e4cc2 step=opening   (15:42)
      braces.enter  set=br52367e4cc2 step=opening   (15:45)
      braces.enter  set=br52367e4cc2 step=opening   (15:46)

  Somebody entering, failing to leave, reloading, entering again.

  It arrived when the list of stamps became a modal: the line used to
  remove a docked element by id, which is safe after `view` is gone, and
  became a read of `view`, which is not. The list is closed while `view`
  still exists now — and the parts that MUST happen, the key handler, the
  mode and the view, are in a `finally`, so a throw anywhere in the
  teardown can never again leave somebody in a mode with no way out. A
  half-tidied view is untidy; a panel nobody can get back to is somebody's
  afternoon.

- **A refused commit came back as "Request failed (200)".** The reason a
  write is refused — "this exact alignment is already version 4 of this
  set", "two stamps would land on a time another stamp already holds" —
  lives in the report, and the response carried `ok: false` with nothing at
  the top level. The client reads `data.error` and falls back to the status
  code, so a carefully written sentence arrived as a number. Both places
  now: the panel reads the report, the transport reads the top.

## 2026.09.21.8 - Braces can call one garbage, reluctantly

### Added

- **A garbage button, which asks twice and is not pleased about it.** `g`, or
  the red button beside "Leave it". A stamp marked this way is not moved and
  not written: an aligned version holds the spikes and nothing else, so a
  rejected one simply is not in it, and every earlier version still has it
  exactly as it was.

  Braces reads labels and does not write them — which candidates are real is
  curation's question, answered a step earlier, and a tool that quietly
  re-decides it makes the curation set stop being the record of what anybody
  decided. That reasoning is why this asks rather than just doing it. But
  somebody looking at a stamp on the recording, with the CSD under it, sees
  what they missed at a smaller size, and sending them back to Checkup for
  one obvious mistake is how obvious mistakes stay in.

  So it asks, by name, and then agrees to it grudgingly:

      "A curated set, Jeremy. Curated. By a person. Recently. And yet.
       Are you quite sure? Quite quite sure?"

      "I shall add it to the list of things that were definitely going to
       be handled in Checkup. It is out."

  Five openings and six replies, picked at random, because one fixed
  sentence read four hundred times stops being read at all — which is the
  failure mode of every confirmation dialog ever written.

  It is red on BOTH halves of the mark, because drawing its new position in
  the colour of an accepted move would be a lie: it is not going there. It
  has its own chip in the list of stamps, and pressing `g` again takes it
  back without arguing, since putting something back needs no persuading.

  Counted apart from the candidates curation had already rejected, in the
  preview and in the version's record.

### Fixed

- **Clearing a decision the obvious way answered "ok" and did nothing.**
  `{"row": 3, "call": null}` — which is what anybody would write, and what
  the route's own single-row shape invites — fell past the branch that
  builds a decision, because that branch only ran when the call was NOT
  null. Nothing was decided and the reply said it worked. The panel was
  unaffected: it has always sent the map form, `{"calls": {"3": null}}`,
  precisely because of this. Both work now, and the end-to-end check tries
  both spellings, because a route that reports success for a request it
  ignored is how a check of mine came to pass while testing nothing.

- **The end-to-end suite failed whenever a colleague banked something.** Its
  last check counted versions before and after and called any increase "the
  suite wrote to your bank". This lab syncs every twenty seconds: two
  versions banked on another machine arrived mid-run and were reported as
  this one writing. It compares WHICH versions exist now, fails only if one
  appeared stamped with this machine, and says plainly when the others
  arrived from elsewhere — which is the sync working, not a fault. "I threw this one out just now" and
  "this was thrown out last week" are different facts and the history should
  keep them that way.

## 2026.09.21.7 - A push no longer loses what changed while it was reading

### Fixed

- **The incremental push had a window in which an edit was lost for ever.**
  The cursor was stamped AFTER the read rather than before it:

      since   = last_push
      rows    = collect(...)      # half a minute on this store
      started = now()             # <- cursor taken here

  Anything edited while `collect` is running is then lost permanently. The
  row is not in the batch, because collect had already passed it; and the
  cursor moves past its timestamp, so no later push considers it either.
  Nothing knows it was missed, so nothing retries — the local side reports
  it as sent and the database keeps the old value indefinitely.

  Measured, not theorised. Renaming ten bank entries while a push was
  running sent five. The other five were written during the read and stayed
  behind the cursor through every cycle after it: days-old names in the
  database against local edits from a minute earlier.

      cloud  Incisor CSC61   updated 2026-09-17T14:52:23Z
      local  Incisor CSC61_PTEN m3 s7 2023-09-22   touched 2026-09-21T18:15:26Z

  The cursor is taken first now. A row edited during the read is merely
  re-sent next time, which the database drops as a no-op: sending something
  twice is free, sending it never is not. The five that were already
  stranded were recovered with a full push.

- **Every stamp already on its peak came back as an error.** "Nothing moved,
  so there is no new version to write" is what a set that is finished says,
  and it was shown as a red failure — which reads as something having gone
  wrong with a proposal that is simply right. It is an outcome now, said
  calmly, and the button says "Nothing to bank" and is disabled BEFORE it is
  pressed. A set where nothing moved but rejected candidates would be
  dropped still counts as a change, because the version then holds the
  spikes and nothing else.

- **Movement did not reach the support panels.** A drag publishes the moved
  marks every 120 ms, and the set is the same size while it happens — so
  the shortcut for "same set, new position" ran instead of the branch that
  adopts marks, applied the index and the focus, and kept the old positions.
  The other windows followed the stamp being decided and drew every line
  where it used to be. A pointer that brought its own marks is complete and
  current, so it is now adopted before any shortcut can decide nothing has
  changed.

### Changed

- **Neighbouring stamps are ticks again, in Checkup's proportions.** A
  neighbour rises 18% of the pane from the bottom, 38% where the pane is
  short enough that 18% would be a few pixels; the pair being decided runs
  the full height, wider and opaque; an answered neighbour is quieter and an
  untouched one quieter still and dashed. The same numbers curation uses, so
  stepping between the two is one picture in different colours.

  They were removed a few versions ago for a reason worth keeping straight:
  a mark's size depends on a flag that travels between windows, and while
  that flag was going astray every mark drew as a neighbour, which made a
  panel look EMPTY rather than slightly wrong. Size can carry the focus
  again because the focus now arrives — as a number on every pointer, and
  with marks adopted unconditionally.

- **Sets with nothing to align are no longer offered by Braces.** Nine of
  the forty-eight were fully curated sets in which every candidate had been
  rejected, one of them 738 of them. They were listed and greyed; the place
  to see "this one is finished and it is all garbage" is the Event Bank,
  which holds every entry. A list of things to align holds things to align.

- **Every `Incisor CSC##` entry now carries its session.** Incisor names a
  set after the channel it scanned, which is the one fact it is sure of and
  the one fact that identifies nothing: ten entries were named exactly that
  and six of the names were shared. Two different recordings both called
  "Incisor CSC42" are indistinguishable in any list that shows a name, which
  is every list.

      Incisor CSC42   ->   Incisor CSC42_PTEN m47 s1 2024-12-04

  `tools/name_incisor_sets.py`, which says what it would do and needs
  `--apply` to do it. Three of the ten turned out to be the same recording
  banked two or three times — same group id, same event count — which is
  not a naming collision and cannot be fixed by renaming. They get a short
  piece of their own id so they can be told apart, and the tool lists them
  for somebody to decide about: deleting a banked entry is not a thing a
  script should choose to do.

## 2026.09.21.6 - A set with nothing in it says so, and the batch keeps up

### Added

- **Every banked entry can say whether it has reached the database.**
  `/api/bank/sync`, and it is three questions rather than one flag, because
  an entry and its snapshots travel separately: an entry can be missing
  entirely, present but missing a version this machine has, or holding a
  version whose snapshot never went up — which is the case where somebody
  else can see the version in the history and cannot read the stamps back.

  Without asking the database it answers from the local push cursor, which
  is instant and works offline: anything changed since the last successful
  push is waiting. `?verify=1` asks what is actually up there, which is the
  only way to catch a push that reported success and did not land. First run
  on this bank: **90 synced, 10 missing a version, 1 absent, 1 local by
  design** — the demo recording, which never syncs and is named rather than
  flagged, because crying wolf about the one thing working as intended is
  how a status page gets ignored.

- **Bad contacts are visible and editable from the bulk table.** A bulk run
  uses whatever each recording has marked, and there was no way to see that
  from here, let alone change it. Each row says how many and which, and
  saves through the same route Incisor uses so a contact marked here and one
  marked in the trace view land on one record. They are interpolated rather
  than dropped — a second difference over an uneven grid is not a CSD — so
  the row says "not believed", not "missing".

- **A second button for the sets that have never been aligned.** "Everything
  ready" ticks a set that has been aligned as readily as one that has not,
  so a second pass over a bank re-reads the lot.

### Fixed

- **A set with no dentate spikes in it was offered, run, and filed empty.**
  `n` counts CANDIDATES. A set can be fully curated and hold no events at
  all — somebody went through it and rejected every one — and **nine of the
  forty-eight sets in this bank are exactly that**, one of them 738
  candidates every one of which is garbage. Running one read the recording
  for a minute and produced a proposal with no rows in it, which somebody
  then has to work out is empty on purpose.

  The run refuses it and says why. Both pickers grey it out, will not let it
  be ticked, and leave it out of the select-all buttons and the "can be read
  here" count. It is shown rather than hidden: "this one is finished and
  every candidate was rejected" is a real answer, and a row that silently is
  not there reads as a set that does not exist. Both views now show "N
  spikes of M" rather than the candidate count alone, which is the number
  that decides whether there is anything to do.

- **A finished batch row did not show it had finished.** A tick rewrote the
  status text and nothing else — right while a read is going, wrong the
  moment it lands, because the Open button is part of the row and only
  appeared at the next full render, which is when the whole queue ends. A
  set that landed four minutes ago looked exactly like one still being read.
  The finished row is rebuilt, and only that row, so the table keeps its
  scroll position.

- **The bulk table moved under the pointer while it worked.** Every tick
  replaced the whole card, four times a second, for the minute each read
  takes — throwing away the scroll position, the focus and any version list
  somebody had open, which is exactly when they are trying to read it. A
  tick writes one cell now.

- **The progress bar counted something and did not say what.** "Reading
  window 43 of 62" under a sentence that began "It is the whole recording".
  Braces has not read a whole recording since the windowed pass landed, and
  62 counts STRETCHES — stamps closer than a second are read as one, which
  is why this is minutes of an hour. Each stage says what it is doing, names
  its unit, and states the number it is not: how many stamps the set holds.

- **"Averaged over 16 channels, leaving out CSC59."** Neither half was true.
  The 16 are DEPTHS, not contacts: a CSD depth is a difference between
  contacts, so 18 contacts give 16 depths and there is no answer to "which
  16 channels" because they are not channels. And CSC59 was interpolated
  from its neighbours, not left out — dropping it would leave the rest
  unevenly spaced — and it is not even inside the band this was measured on.

- **The bank dialog said two different things in one sentence.** "This
  becomes version 4, branching off version 3": branching off v3 is v3.1, and
  v4 is what continuing it looks like. It also named the version by the ref
  it had been handed rather than by a name anybody would recognise, and
  still claimed "Nothing is deleted" after an aligned version started
  holding the spikes and not the rejected candidates. It says which version
  it is reading, whether that continues or branches, and what it is leaving
  out.

- **The bank dialog was laid out against the wrong box.** It built a modal
  and handed it to the thing that puts a dialog inside `#bigModalBox` —
  which is already a modal — so a 620px bordered panel sat at the left edge
  of a 1240px one. It uses the header/body/footer convention every other
  dialog in the app uses.

## 2026.09.21.5 - The bad contacts were always there; the table was reading an empty cache

### Fixed

- **"none bad", against the whole cohort.** The bulk table in Braces showed
  `none bad` on every row — all 46 sets whose recordings have contacts
  marked, including m33 s8 at CSC8/41/59 and M13_HF4s2aug1 at CSC55/59. The
  channels were in the store the whole time. The column was reading an empty
  list and drawing it as an answer.

  `registryRows` is a getter over ToolKit's sixty-second registry cache, not
  a read of the registry. Curation, StrataScope and Braid each warm that
  cache on their way in, so Braces worked whenever somebody had been through
  one of those first — and only then. Reached the way the bundle reaches it,
  ToolKit then step 3, nobody had, so the getter returned `[]` and every
  consumer of it answered from nothing.

  Two columns were wrong in the same direction, and both read as facts about
  the recordings rather than about the cache. The other one is the count on
  the bar: with no rows to judge against, `reachable` says yes to everything,
  so a list where 368 of 588 are mounted reported every set as readable.

  Braces now reads the registry itself when nobody has yet, and the columns
  that depend on it fill in when it lands. Not awaited — the read takes
  seconds on a network share and nothing on the first paint needs it, so the
  panel draws at once, as before.

- **A contact marked from the bulk table went on saying what it said
  before.** The save wrote to the store and then called ToolKit's `refresh`,
  which re-runs whichever tool is on screen — this one — so the table was
  repainted out of the same cache the edit had just made wrong, and the chip
  kept the old count for up to a minute. It forces a re-read now, which is
  what the cache's force flag is for.

- **Four rows of the bad-channel workbook had never landed correctly.** m5 s2
  and m5 s7 held each other's lists — s2 carried the CSC8 that belongs to s7.
  m21 s2 was missing CSC8. And m24 s4 listed CSC24, which is not a contact
  anybody marked: it is the mouse number, read out of the wrong column by
  whatever imported it. All four now match the sheet; the other 58 already
  did.

### Added

- **`tools/import_bad_channels.py`**, so the sheet can be applied again
  without anybody doing it by hand. Dry run by default, `--apply` to write,
  and it reports each change as a difference — `+CSC8`, `-CSC24` — rather
  than as two lists to compare by eye.

  It resolves a row to a recording rather than to a mouse and session pair.
  The numbering restarts per project here, so PTEN m13 s2 and KCNT1 m13 s2
  are two recordings with one loose key and nine of the 62 rows collide that
  way; matching on the pair alone writes a PTEN workbook into a KCNT1
  record. Retired records are not candidates, the PTEN cohort wins a tie, and
  anything still ambiguous is skipped and named.

  It writes nothing for a session the sheet does not mention. Sixty-two rows
  are not a statement about the other 526 recordings Jarvis knows, and
  reading them as one would clear every channel anybody has marked by hand in
  the trace view.

- **`web/_dev/bracesbad.html`**, which goes straight to Braces from a cold
  start — the route is the test, because entering through any other tool
  warms the cache and hides the bug. It computes what each chip should say
  from the registry and the bank rather than hardcoding counts, so it means
  something on a machine other than the one it was written on. Seven checks;
  three of them fail on the code as it was.

## 2026.09.21.4 - The read says what it is counting, and the list is the one you already know

### Fixed

- **The progress bar counted something, and did not say what.** "Reading
  window 43 of 62", under a sentence reading "Every ticked channel is read
  once — it is the whole recording, so it takes about as long as an Incisor
  scan."

  Both halves were wrong. The sentence was from the design before the
  windowed pass: Braces has not read a whole recording in weeks, it reads the
  stretches the stamps can reach, which is minutes of an hour. And 62 counts
  STRETCHES, not spikes — stamps closer together than a second are read as
  one, which is the whole reason this is fast — so somebody watching a set
  they know holds 1213 sees 62 and reasonably concludes the tool has lost
  most of them.

  The unit is named now, each stage says what it is doing rather than sharing
  one stale sentence, and the count it is NOT is written beside it: the
  number of stamps in the set. The depth pass says out loud that it works
  from a sample, because where the sink is is a fact about the probe rather
  than about any one spike. The bulk rows use the same words as the bar
  instead of the code's own stage names.

### Changed

- **The list of stamps is Checkup's list.** Same dialog, same bar, same
  chips, same rows — the classes are shared rather than copied, so the two
  look identical because they are the same markup, and a person who has been
  through a curation set already knows how to read this one. It replaces a
  panel of Braces' own with its own layout, which was one more thing to learn
  for no reason.

  What differs is only what a row can be sorted and filtered by, because an
  alignment's categories are not a curation's: not which label, but whether
  it moves, whether it was flagged, and whether anybody has answered. Sort by
  time or by how far a stamp moves — furthest first, which is the order a
  second look wants to happen in — and the same gap markers where the stamps
  thin out.

## 2026.09.21.3 - A version says which version it came from, and a restore puts every decision back

### Fixed

- **"I read v4, saved, and it says v7."** A version recorded where it came
  from in `from_v`, and what the panels send is a **ref** — a per-version id,
  because the number is not unique and a ref is the only thing that names one
  version and only one. The labeller then looked that ref up among the
  version *numbers*, found nothing, and treated the new version as a **root**.
  A root gets the next trunk number, so a version branched off v4 was named
  as though it had begun a fresh line. That is the jump.

  Versions now record `from_id` — the parent's id, exact — alongside the
  number, and the labeller prefers it. A history gains precision as new
  versions are written into it, with nothing rewritten. On an entry whose
  history runs v0 to v6:

      reading the newest  ->  writes v7
      reading v4          ->  writes v4.1, leaving v5 and v6 alone
      reading v6          ->  writes v7

  **And the name the panel promises is the name you get.** It was predicting
  the successor of the newest version whatever you had picked up, so reading
  an older one promised a number that branching would never produce. It now
  branches from what is actually being read.

  Two smaller things fell out of the same work. The default parent — what a
  run reads when nobody said otherwise — resolved by number, so on a history
  where two versions share one it could name a version in the middle as the
  thing it had continued from; it resolves by lineage now. And children were
  counted per parent *number* rather than per parent, so one parent's
  branches were counted against another's and a line branched where it should
  have continued.

- **A restored version put back fewer decisions than it held.** This is the
  "64 good spikes, and then the set says 63".

  Putting a banked version back onto the bench matches its stamps to the
  bench's candidates by time, rounded to a tenth of a millisecond, through a
  **dict** — which holds one value per key. Where two candidates share a
  rounded time the second replaced the first, one of them could never be
  matched, and its banked decision was dropped without a word. The comment
  beside it said a tenth of a millisecond is "tight enough that two real
  candidates are never confused". The data disagrees: one curation set on
  this machine holds **324 events across 167 distinct instants**, so a dict
  keyed on time could match at most 167 of them and 157 decisions had nowhere
  to land.

  Matched to a list per instant now, consumed in order, so N candidates at
  one instant take the N decisions banked at that instant. How many landed on
  a shared instant is reported rather than absorbed — a set with these in it
  is worth deduping, and the bank already has a `dedupe` for exactly that.

### Changed

- **A banked alignment holds the spikes and nothing else.** A curated set is
  a detector's candidate list plus a verdict on each one, and Braces only
  ever moves the ones somebody kept — moving a rejected stamp would assert a
  position for something that is not an event. So the rejected ones were
  being carried into the aligned version unchanged, which makes the version
  an analysis reads a mixture of events and things that were thrown out.

  They are left out now, counted by label, and named in the preview before
  anything is written. Nothing is lost: a version is a new row in a history
  and every earlier one still holds the whole candidate list with its
  verdicts, which is where "what did the detector find, and what did we
  reject" is answered.

  The preview's own arithmetic was wrong with them gone, and said so out
  loud: "28 move, 16 stay" counted the sixteen rejected stamps as staying
  where they are, in a version that will not contain them. It counts what it
  will write, and the end-to-end check now asserts that what is written plus
  what is dropped is what the set started with.

## 2026.09.21.2 - Jarvis opens in a second, and stops putting you where you did not ask to be

### Changed

- **Opening Jarvis no longer waits for the catalogue.** Measured on this
  machine, a boot spent four and a half seconds on `/api/sync/status` and
  another four and a half on `/api/vacc/knows`, both at once, before the
  interface could be used for anything. Both now answer in hundredths of a
  second, out of a small local cache of what they said last time, and the
  real answers are recomputed behind the page.

  Last boot's answer is almost always this boot's answer — the catalogue
  does not change while the computer is off — so the recompute usually
  finds nothing and the page does nothing. When it does find a difference
  the page is told, and only then does it re-read.

  The cache is per machine and local. It sits in `GUI_logs/.cache/warm`
  beside `index.json`, git ignores it, nothing uploads it, and deleting it
  costs exactly one slow boot. It cannot be anything else: two computers
  have different recordings on different drives, so one machine's answer is
  not merely useless on another, it is wrong there.

  **It is switched on by "Wake up Jarvis" and by nothing else**, and it
  stops answering the moment there is a real answer to give — or the moment
  somebody clicks anything, because a person who has started working is a
  person owed the truth. A server started by the harness suite, by
  `vacc_run`, or by a script reads the store live exactly as it always has.
  `tools/test_warmcache.py` checks each of those rules, and
  `web/_dev/warmboot.html` checks a real page load against a real store.

  **The first boot after a pull is slow again**, on purpose. The cache is
  stamped with the changelog version and the commit, and an update that
  changes the shape of a payload must never hand the new interface last
  week's shape. It costs exactly one boot.

  One thing it does not fix: `rebuild_index` holds the store's write lock
  for the whole of its eight seconds, so a write can still queue behind it.
  That was always true — it used to happen on the `/api/sync/status`
  request thread, where it was hidden behind the boot overlay. Now that the
  page is live while it runs, the recompute waits five seconds before
  starting so that the boot's own preference write is not caught by it;
  measured, that write went from 7.5 s to 0.02 s. Actually shortening the
  hold means changing how the store locks, which is a separate job.

- **Nothing loading at startup moves you any more.** Reopening the
  recording you last had open finished with `setView('xplore')`: a quarter
  of a second after the interface appeared, whatever you were looking at
  was replaced by a voltage trace that then took several seconds to draw —
  and a click you had already started landed there instead of where you
  aimed it.

  The recording still reopens. It reopens **underneath** whatever is on
  screen, which is what `?csc=` has done for months, and says so once,
  quietly, so finding it in XploreFinder later is not a surprise. If you
  have walked over to XploreFinder yourself in the meantime, it draws
  there, because then it is what you are waiting for.

  It also waits two seconds rather than 250 ms. Nothing is waiting on it,
  and reading a whole recording's headers into the middle of the page
  fetching its own catalogue made both slower.

- **Three views that read the catalogue once per row now read it once.**
  Found while measuring the first minute rather than the first paint,
  because "it takes a minute" is about walking into views and not about the
  splash screen. All three are the same mistake in three places: work that
  costs the same whether you do it once or seven hundred times, done inside
  the loop.

  | | before | after |
  |---|---|---|
  | `/api/layers` (ToolKit list) | 9.9 s | 0.5 s |
  | `/api/toolkit/bad-channels` | 6.8 s | 0.15 s |
  | `/api/toolkit/scopes` | 4.5 s | 0.15 s |
  | `/api/sessions` | 4.1 s | 0.1 s |

  `/api/layers` asked the registry for the recording behind each of
  seventy-two sheets, and `REG.by_gid` re-stats all 1510 session shards on
  every call to check nothing has moved — so it did that seventy-two times
  for one list. It builds the index once now, which is what `/api/registry`
  already does and says so in a comment.

  The other three went through `STORE.all_sessions()`, which re-reads and
  re-merges every shard on every call; `REG.all()` is the identical read
  cached against the shard directory's signature. Checked rather than
  assumed: both return the same 687 records byte for byte, and the three
  routes' output is identical either way.

  These were slow on **every** call, not only the first, so this is a fix
  rather than something the warm start was hiding.

- **A background refresh cannot scroll a list you are reading.** The rule
  for anything arriving after the interface is up: if the view is not on
  screen, mark it stale and let the next visit re-read it; if it is, redraw
  in place and put the scroll back. `BARRY.keepScroll` finds the element
  that is actually scrolling rather than being told which one it is — the
  Sessions list does not scroll, the pad two levels above it does, and code
  that saved `#sessTree.scrollTop` was saving a number that is always zero
  while reading exactly as though it worked.

## 2026.09.21.1 - The curve Braces measured, the whole set at a glance, and a version number that was not one

### Added

- **The curve the rule took its maximum from, drawn on the recording.** On
  by default, with a toggle in the Braces bar. Mean |CSD| over the band with
  the mains out — the actual trace the decision was made on — drawn into
  the bottom of every pane, behind the marks, scaled to its own peak. The
  green line is that curve's largest peak inside the window, so the answer
  and the working are on the same picture. It travels with the marks rather
  than being fetched per pane, which is what lets the pop-out aid windows
  draw it: they are separate pages with no proposal in them, and it is why
  it appears on the raster panels as well as the traces.

  **Remembered between sessions**, because it is a way of working rather
  than a property of a set: somebody who wants to see what the rule looked
  at wants it on every stamp of every alignment.

  **Read and drawn over the reach exactly.** A stamp may move within the
  window and nowhere else, so a sample outside it is not a candidate and
  cannot be the answer — three windows' worth of curve was two thirds of a
  picture no decision could be taken from, and read as though the rule had
  considered it and passed it over.

- **The window a stamp may move in is shaded on every pane.** It was drawn
  at five per cent, which over a CSD raster reads as a rendering artefact
  rather than as a region — and the raster panels are exactly where somebody
  is deciding whether the new line sits on the sink, so it is where knowing
  what was within reach matters most. A visible wash now, with both edges as
  solid rules and a bracket top and bottom, which is what makes it one region
  rather than two lines that happen to be there.

- **The whole set as a list, on the recording.** `l`, or the toggle in the
  bar. One row per stamp — where it was, how far it moves, why it was
  flagged, what you decided — docked to the right of the traces rather than
  over them, because the point is to read it while looking at the recording.
  Click a row to go to that stamp; the one you are on scrolls itself into
  view.

  Stepping is fine for going through a set once. It cannot answer "which are
  still flagged", "what did I decide forty stamps ago", or "take me back to
  the one that moved eighty milliseconds" — those are questions about the
  set, and a pair of arrow keys is the wrong instrument for all three.

- **Alignments on the overview strip, in their own scheme.** The strip was
  drawing them with the CURATION scheme: one mark per candidate, coloured by
  its label, and "the one you are on" found by position in the list. None of
  that is true of an alignment — there are two marks per stamp that mean
  different things, the colour comes from the decision, and the index is a
  row number, so the strip was lighting up whichever mark happened to sit at
  that position in a list twice as long. It hands the canvas to Braces now,
  the way the panes do. At forty pixels there is no room for a dash pattern,
  so the halves separate by height instead: where it goes on the top half,
  where it was on the bottom, and the one being decided full height.

- **Braces can align many sets in one go.** A switch at the top of the
  panel: one set at a time, or many at once. The many-at-once table lists
  every curated set with its recording, its stamp count and which version it
  would read from, and one button ticks every set whose recording can be
  read from this machine, each at its newest version. Any version can be
  changed before it starts.

  It runs them one after another and leaves a proposal for each. **Nothing
  is banked** — every set still has to be reviewed, which is the whole
  point of the flags; bulk is for the part a computer should do unattended.
  Sequential deliberately: each read is most of a minute of disk on a
  network share, and four at once on one spindle is slower than four in a
  row as well as being four times the memory. The queue says which one it is
  on, can be stopped between entries, and a failure is named on its row and
  kept rather than swallowed.

  **"Newest" means the newest version that can actually be read here**, and
  that is three different things from what it looks like. Not the largest
  stored number, which is not unique — a history running 0,1,2,3,4,3,4 has
  a largest of 4 and a newest of 6, and picking the largest is the "slightly
  earlier version for some reason" that started this. Not the last row in
  the list, because creation order is lineage order only until something
  branches. And not simply the newest, because a version can arrive as a row
  without its snapshot — a name, a count and no times — which is **14 of
  the 49 sets in this bank**, where the newest is v3 and the newest readable
  is v2. Those rows say so on the table rather than quietly running one
  version back.

- **The toolkit's session scope is typed, not scrolled.** The last
  `<select>` of recordings in the toolkit. It is the same control every
  other recording pick uses now — type a mouse, a session, a project or a
  date — and each row carries the dot that says whether the recording is on
  a drive this machine can reach, lit or dark. A dropdown of every session
  anybody has ever marked a channel on is a list you read three times to
  find the one you meant, and it could not say which of them you could
  actually open.

  The scope list and the registry are two different lists: one is "sessions
  something has been recorded about", the other is "sessions this machine
  has opened". They are joined on the session key, so a scope row the
  registry knows gains its date, its project and its reachability — and one
  it does not still appears, with a dark dot, because it is a real session
  with real marks against it and hiding it would hide the answer to the
  question being asked.

- **Braces asks which recording first, then which banked entry.** The same
  two questions the curation wizard asks, in the same order, with the same
  two controls — the recording picker and a radio list. It had a search box
  of its own that matched set names and session names at once, which works
  but asks somebody to hold both in their head and hands back a flat list of
  forty-six where the useful grouping is obvious.

  Only recordings something is curated against are offered. The registry
  holds every recording this machine has ever opened and Braces can do
  nothing with the ones that have no curated dentate spikes, so offering all
  of them means most picks land on "nothing here" — which reads as the tool
  being broken rather than as the recording being the wrong one. Picking a
  recording with nothing banked against it now gets a sentence saying what to
  run first, instead of an empty list.

### Fixed

- **The version chooser looked like it was defaulting two versions back.**
  Its first row — the selected one — read "v4 · 73 stamps, as they stand"
  above a list ending in v6.

  It was not choosing an old version: "as they stand" is the entry's current
  events, which is the newest state there is. The NUMBER on it was wrong.
  `current_version` was the maximum of the stored version numbers, and those
  are not unique — this entry's history is numbered 0, 1, 2, 3, 4, 3, 4,
  because two machines each minted a 3 and a 4 and the union kept both, which
  is correct and is what the per-version id exists for. The lineage walks
  them to 0…6, so the tip is 6 and the maximum is 4.

  Every mention of a version outside the list itself was showing that number:
  the chooser's first row, the search results, the "still on v4" line, the
  "Bank it as v5" button and the confirmation. All of them show the lineage
  name now, and the first row says which name a commit would write —
  checked against what a commit actually produces rather than assumed.

- **The support panels stopped keeping up after the first stamp.** The
  marks were drawn at tick size, the window a stamp may move in was not
  shaded, and the curve did not appear — until you moved something, at
  which point all three came good at once.

  One cause for all of it. `publishCuration` keeps only the latest pointer
  while one is in flight, because only the latest is the truth — so any
  burst, which is every step, arrives at the other window several revisions
  on. The receiving side treated a jump of more than one as "more changed
  than we were told about" and fell through to re-reading the set from
  `/api/curation/<gid>/braces`: not a curation set, no route that serves
  one, a request that fails and a catch that returns false. The pointer was
  dropped in silence. A drag changes the marks, so the publisher sends them,
  and a pointer carrying marks takes a different branch — which is exactly
  why moving something fixed it and nothing else did.

  A pointer for a set already held is now applied whatever the revision
  jump: everything it carries is absolute, so a jump loses nothing. An
  alignment never falls through to the fetch, because there is nothing there
  to fetch. And the marks are re-sent in full if they have not been for a
  second and a half, so a window opened between two of them fills within
  that rather than waiting for somebody to move a stamp.

- **The curve did not appear until it was toggled off and on.** It was
  asked for before the view moved to the stamp it was going to, so the
  samples that came back were the previous stamp's — and they are clipped
  to the reach around the new one, which they do not overlap, so nothing was
  drawn. Entering the view is the worst case: the curve is fetched at row 0
  and the view then lands on the first flagged row, which is rarely row 0.
  Toggling asked again from a settled position, which is why that was the
  one thing that worked.

- **The curve stopped appearing in the support panels after the first
  stamp.** It arrives on a pointer of its own: stepping publishes
  immediately — new focus, new index, no curve, because the read has not
  come back yet — and the curve follows a moment later on a pointer whose
  index, time and focus are all identical to the one before it. The guard
  that stops a window repainting when nothing has changed asked about those
  three fields and threw the curve away. Every early return there is now
  built from the same list of fields the code below it applies, which is the
  only arrangement where adding a field cannot quietly reintroduce this.

- **The overview strip was not repainted by a redraw at all.** It draws the
  whole set, so anything that changes which marks exist changes it —
  switching between "all of them" and "needing a decision" being the obvious
  one — and it kept showing the previous answer until something else
  happened to repaint it, which in practice meant moving to another stamp.
  Redrawing a pane without the strip under it is a half redraw with a name
  that does not say so.

- **The window and the curve were too faint to see on a CSD raster.** A wash
  at eleven per cent and a one-pixel line do not survive a red-and-blue
  image at full saturation — and the raster panels are exactly where
  somebody is deciding whether the new line sits on the sink, so they are
  the panels both of these exist for. The reach is close to twice as opaque
  with solid edges; the curve is a heavier bright line inside a wide dark
  outline, the same trick the marks and the gridlines use, because it has to
  read over white, over saturated blue and over saturated red in one panel.

- **No mark is drawn small any more.** Short ticks for the stamps not being
  decided made the focused pair easy to find and everything else easy to
  miss — and worse, they made a mark's visibility depend on a flag that
  travels between windows, so a pointer going astray left a panel that
  looked empty rather than one that looked slightly wrong. Every stamp is
  full height; the focused pair is twice the width, fully opaque and haloed,
  which tells them apart more clearly than height did. The window a stamp
  may move in also travels as a time of its own now, rather than being
  looked up from whichever mark claims the focus.

## 2026.09.18.4 - Braces takes the mains out, screens the probe, and aligns to the peak of the curve

### Changed

- **The mains comes out before anything else.** The dentate-spike band is
  5–100 Hz and sixty hertz is inside it. A current source density is a second
  spatial *difference*, which does nothing whatever to reject a signal common
  to every contact but not quite equal on them — so the mains was surviving
  into exactly the measure this tool aligns on. Measured on M1ptens2oct2 over
  a clean thirty seconds: the 60 Hz line in the CSD sits **5,950 times** above
  the power either side of it. The trace peaks were being picked from was, to
  a first approximation, a sine wave with a dentate spike riding on it.

  And one mains period is 16.7 ms while the candidate spacing was 12 — just
  under it — so the peak finder was resolving individual **mains cycles** as
  candidates and snapping stamps onto them. The corrections were quantised to
  the mains period and were not about the event.

  Notched at 60 Hz, two hertz wide, zero-phase — zero-phase because the whole
  output of this tool is a *time*, and a filter with phase would shift the
  thing being timed by an amount that varies with frequency, which is
  indistinguishable from the jitter it exists to remove. Taken out per
  channel, before the bandpass and long before the derivative: notching after
  the difference is too late, because by then a line that was everywhere has
  been turned into something that looks local.

- **The probe is screened, and a bad contact is interpolated rather than
  dropped.** A CSD does not merely include a dead wire, it *amplifies* it: a
  dead contact between two live ones is the largest deflection anywhere on the
  shank, and anything choosing a depth or a peak by magnitude chooses that.
  **CSC59 is dead in all three recordings tested** — M1ptens2oct2, m26s2jun28
  and M8s9feb8, three different mice — at around half a microvolt against
  medians of 43 to 68. It had never been screened, and the depth pass had duly
  been returning bands centred on it.

  Interpolated from its neighbours rather than removed, and the difference is
  not cosmetic: taking a contact out of the middle does not leave a shorter
  probe, it leaves an unevenly spaced one, and a second difference over an
  uneven grid has a step in it exactly where the missing wire was. That now
  applies to contacts *you* untick as well. Whatever was repaired is named on
  the panel and kept on the set.

- **The trace is the mean of |CSD| across the contacts, and a stamp goes to
  the largest peak of it in the window.** Not the nearest. With no floor a
  window holds every local maximum of the curve, so "nearest" means the
  nearest wiggle — measured on M1ptens2oct2, that moved nothing further than
  10 ms and scored 0.628 where the same candidates taken largest-first scored
  0.718. There is no height floor at all: a candidate is a local maximum
  whatever its size, so nothing is left unplaced for being small.

  **The assignment stays**, and only its objective changed: the same dynamic
  program over the same runs, minimising unmatched stamps first and then total
  *height given up* instead of total distance moved. Two stamps in a burst
  still cannot be handed the same instant. The edge case is untouched, because
  it comes from the first term — a stamp between two peaks and another after
  it that can only reach the later one means the first must take the earlier,
  or one of them goes unmatched and the count is worse.

- **How it scores.** The test is the event-triggered average of the signed CSD
  on the sink contact: the deflections add where the stamps agree and cancel
  where they do not, so the peak of the average over the mean single-trial
  peak is a direct read-out of alignment. On M1ptens2oct2's 64 curated spikes,
  one denominator and one contact for every condition:

      as curated                        0.599
      the reference implementation      0.712   (41 of 64 placed)
      this                              0.718   (64 of 64 placed)

  And on a second recording, m26s2jun28's 28 spikes, where the stamps were
  further out to begin with: **0.380 as curated, 0.690 after**. The median
  move there is −11.5 ms, which is large enough to be worth distrusting
  — the coherence is what says it is the rule finding the event rather
  than dragging the set off it.

  The average also narrows from 11.0 ms to 10.0 ms, and carries 0.4% of its
  power at 60 Hz — which is what says the number is an event getting sharper
  rather than the mains failure mode, where an ensemble slides between cycles
  and produces a beautiful 60 Hz average that measures nothing.

- **Both the mains frequency and the smoothing are settings.** Rectifying per
  contact and pooling after makes each half-cycle of a biphasic deflection its
  own positive lobe, so one event can arrive as two or three humps — |sin| has
  twice the frequency of sin, which is arithmetic rather than a property of
  the recording. A moving average about as long as one half-cycle merges them
  into a single hump whose maximum is a usable time. It is off by default,
  because broadening a peak makes it easier to find and harder to place.

### Fixed

- **The record said a floor applied when none does.** An alignment set carried
  `cand_height_sd: 4.5` whatever rule it was made under, and the parameters
  are the only record of how its numbers were made. Zero now means no floor,
  which is the rule — a set made with one and a set made without are not
  comparable, and nothing else on the set would show the difference.

- **The depth bars were labelled in microvolts** and have not been microvolts
  since they started being scored on the event-triggered template. Shown as a
  percentage of the strongest contact, which is what they are.

## 2026.09.21.3 - The cluster matcher was fed two different things

### Fixed

- **Incisor's VACC list showed `'str' object has no attribute 'get'` where
  the recordings should have been.** `_cluster_match` takes two lookups and
  decides which known recording a cluster folder is. It was built twice, in
  two places, and the two drifted: `/api/vacc/scan` filed the whole record in
  both maps, and `_vacc_staged` filed the record in `by_loose` and the bare
  **gid string** in `by_key`.

  So the moment a cluster folder matched a recording *exactly*, the matcher
  handed back a string and the caller's `rec.get("gid")` raised. Exact is 37
  of the 39 matches on the real cluster — it is what the feature is for —
  which is why this failed every time rather than occasionally.

  The irony is that `_cluster_match` exists to keep the matching rule in one
  place so the two callers cannot disagree, and it did that. What drifted was
  what they fed it. So `_match_index()` now builds the pair, once, and both
  maps hold the record: the loose branch needs the candidate's start date and
  project before it will accept a match, and every caller asks for a gid.

  `/api/incisor/batch/plan` answers again: 38 runnable, 1 blocked.

## 2026.09.21.2 - What kind of recording this is, on the row; and the sync stops shouting

### Fixed

- **A dual-array recording now opens IN the dual layout.** The control said
  "Dual array" from the moment it opened and the panes were a single array
  until somebody switched to something else and back. The label was right,
  the layout was wrong, and the two disagreed with no way to tell which one
  the CSD had actually used — which is the worst available failure, because
  everything still looks fine. The layout is applied on open, and again when
  the probe table arrives, since it is fetched after the page is and a
  recording reopened at startup can be on screen before it.

- **The cluster catalogue's count described the wrong thing.** It said "587
  registered" beside a tree of 109, which is the whole catalogue's number in
  a panel that only ever shows what VACC can read. It now says "109 on VACC,
  of 587", and says in the tooltip that the rest are not hidden by a filter
  you can turn off — they are not there.

### Added

- **A chip on every row saying what kind of recording it is** — H3, H10,
  HIP/M2 — on the drive scan, in Everything Jarvis knows and in Everything
  VACC knows. Three states that are not degrees of confidence, so they are
  not three shades of one colour:

  **confirmed** (green, filled) somebody said so. **detected** (hollow,
  warning-coloured) the channel count supports a guess and nobody has
  agreed — the guess is *used*, because a dual implant drawn as one array is
  worse than one drawn as two and marked unconfirmed, but it never draws as
  a fact. **unknown** (a question mark) no count, or a count that supports
  nothing.

  Seventy of the seventy-one dual implants here are currently detected and
  unconfirmed. Clicking a chip offers "Confirm — HIP/M2" as a single button,
  because agreeing is the common case by a wide margin and making somebody
  pick from a list seventy times is how a queue stops getting worked.

  Drawn from `probes.state_of` and nowhere else. Three surfaces working the
  state out themselves from `probe` and `n_channels` would eventually
  disagree about what green means.

- **Supabase carries the probe.** Migration 17 adds `probe`, `probe_source`
  and `channel_banks` to `sessions`, and they sync both ways — confirming a
  dual implant on the rig has to reach the desktop, or two machines compute
  different CSDs from the same recording and neither looks wrong.
  `probe_source` is only ever `manual` or absent: a guess is never written,
  because once filed it is indistinguishable from an answer.

### Changed

- **The sync was spending 6.5 GB of egress a month on the word "nothing".**
  Measured rather than guessed, with `tools/cloud_egress.py`: a pull asked
  each of twenty-one tables "anything newer than X", and on a quiet cycle
  every single answer was an empty list. The rows came to **7 KB** a cycle.
  The **requests** came to 21 a cycle, at a cycle every 20 seconds —
  **90,720 a day per machine**, and their HTTP overhead is essentially all
  of the 6.5 GB. The bytes were never the problem.

  Two changes, and either one helps on its own:

  *One question instead of twenty-one.* Migration 17 adds a
  `barry_watermarks` view — one row per table carrying its newest
  `updated_at` — so a quiet cycle is a single small request and a busy one
  fetches only the tables that actually moved. It falls back to asking
  everything when the view is not there, which is what every clone looks
  like until somebody runs the migration: a sync that refuses to work until
  a migration has been applied everywhere is a sync that stops working for
  whoever did not apply it.

  *Backing off while idle.* A pull every 20 seconds is right when two people
  are editing the same set. It is not right for the eight hours the rig sits
  on the Sessions view with nobody in the room, and it was doing it anyway.
  The interval now doubles each time a pull brings back nothing, up to about
  five minutes, and drops straight back to 20 seconds the moment anything
  arrives or anybody writes.

  Together, an idle machine goes from 90,720 requests a day to about 270.

## 2026.09.21.1 - Two probes in two places, the cluster gets the catalogue, and signing in

### Added

- **A dual-array probe template: hippocampus on CSC 1-64, M2 on 65-128.**
  The KCNT1 recordings are 128 channels because there are two implants in
  the animal, not one probe with twice as many contacts. That distinction
  is arithmetic, not bookkeeping: a CSD down the channel order steps across
  the gap at channel 64 and computes a second spatial derivative between
  two contacts that are millimetres and one brain region apart. It produces
  a number, the number is meaningless, and nothing about it looks wrong.

  So the dual implant is described the way the H10-D already is — as
  independent lines of contacts, one pane each, a CSD down each on its own.
  The split is the same 64/64 `sessreg.banks_for` writes down, and it has
  to stay that way: the banks are where a person records which region is
  which, and a template that disagreed with them would put the M2 label on
  the hippocampal trace.

- **Which probe a recording was made with is now a fact about the
  recording.** It lived in the Xplorefinder session's view state, so it
  lasted as long as that window and travelled to nobody — Incisor, a
  colleague's machine and the next open could each believe something
  different about the same animal. It is assigned in Housekeeping, beside
  the project, and everything reads it from one place.

  "Nobody has said" is kept distinct from "somebody said H3", and a
  128-channel recording is *read as* a dual implant without that being
  written down as a decision. A blank that is visibly blank can be filled
  in; a guess that looks like a fact cannot be found again — the same
  argument `banks_for` makes about leaving a region blank.

  Choosing a template with named regions fills in any blank channel bank,
  because picking "hippocampus + M2" **is** saying which bank is which, and
  making somebody enter the same fact twice is how the two come to
  disagree. It only ever fills a blank.

- **"Everything VACC knows" has the catalogue, not just the directories.**
  The same project → mouse → session tree as "Everything Jarvis knows",
  narrowed to the recordings the cluster can read — 109 of them here.
  Finding a recording by which animal it came from is how anybody thinks
  about it; recognising a folder name on a cluster is not.

  One renderer, not two, because a second copy of that tree is a second
  copy to keep in step. The directory walk is still there beside it, under
  its own tab, because it is how a recording gets connected to its copy on
  the cluster in the first place.

- **Filter by project, and by channel count.** In Everything Jarvis knows,
  where grouping by project already existed and is a different thing:
  grouping decides what the branches mean and every recording is still in
  the tree. Project is a set rather than one at a time — "PTEN and KCNT1
  but not the urethane work" is ordinary when the urethane project shares
  mouse numbers with KCNT1.

  Channels is a comparison rather than a value, because the question people
  have is "which of these are the dual implants", and that is **more than
  64**. Asking for exactly 128 gets the ordinary ones and misses the six
  whose `CSCn_0001.ncs` continuation files put the count at 190 or 192 —
  precisely the ones worth looking at. A recording nobody has read a header
  for has no channel count and is in **neither** side: 164 of them here,
  and a missing number landing in "fewer than 64" would be absence read as
  zero.

- **A guided VACC sign-in, from a NetID and one password.** The NetID is
  the whole question — `<netid>@login.vacc.uvm.edu` is the account and the
  home and scratch directories follow from it. Turn VACC Mode on with
  nothing set up and it offers to sign in.

  The password is needed exactly once, to install an SSH key, and then the
  key logs in. That is not only convenience: the status chip polls, and
  password login at UVM means Duo, so a second factor every ten seconds for
  six hours is not a thing anybody would leave on. Duo is answered with a
  push during the install; the person approves it on their phone.

  Somebody who already uses the cluster from a terminal has a key that
  works, and is offered it instead of being asked for a password to make a
  second one.

  **What happens to the password:** it goes over localhost into the
  environment of exactly one `ssh` process and is dropped when that process
  exits. It is never written to disk, never on a command line, never
  logged, and `_scrub` removes it from anything ssh echoes back. The
  askpass helper answers a password prompt with the password, a Duo prompt
  with a push, and **any prompt it does not recognise with nothing** —
  sending a credential to an unrecognised question is how a credential ends
  up somewhere it was not meant to go.

  The config is written only after the key has been proved by connecting
  again with the key **alone**. Writing it after the install would record
  "signed in" on the strength of a password that is now gone.

- **`start.py` asks for a NetID on a new machine**, beside the sync key and
  for the same reason. Deliberately no password there: a console that may
  be a double-clicked window is the wrong place for one, and the Duo push
  that follows needs somebody watching.

### Changed

- **A probe layout is however many columns the template has**, not six. An
  H10-D has six and a dual implant has two, and the reason for one pane
  each is identical in both cases.

- **The probe picker is built from the server.** It was two hand-written
  `<option>` tags, so adding a template gave every part of the app the new
  geometry except the one control anybody uses to pick it.

- **Each probe reports its own contact pitch** — 30 µm within an H10-D
  column, 50 µm on the linear arrays. The listing said 30 for all of them,
  which was right for exactly one. Nothing read it, so nothing was wrong;
  it would have been the moment anything did.

### Fixed

- **`tools/check_js.py` caught two shadowed `const` bindings** that would
  have shipped: one took the whole Sessions module down, the other made a
  harness page run none of its checks. There is no build step here, so
  neither produced an error anywhere.

- **The housekeeping harness restores `project_source`, not just the
  project.** Driving the picker and putting only the value back left a real
  recording reading "set by hand" with nobody having set it by hand — and a
  manual project is immune to the re-filer and raises no filing flag, so
  every run quietly immunised whichever recording was first in the tree.

## 2026.09.18.3 - A running scan says what it is finding

### Changed

- **The scan line was a spinner, two counters and a path.** The counters are
  the least informative part of it: "31 sessions · 75 folders" reads exactly
  the same whether the scan is walking the tree you meant or one directory
  too high, and a scan of a lab drive runs for minutes before anything else
  tells you. It now answers the three questions somebody watching it
  actually has.

  *Is it moving* — the rate, in folders a second, beside the elapsed time.

  *Is this the data I meant* — what it has found so far, broken down: the
  projects with counts, the number of distinct animals, and the channel
  counts. The channel count is the one that earns its place, because PTEN is
  64 and KCNT1 is 128, so the number alone says which drive is being walked.

  *Where has it got to* — the path, but relative to the folder you chose,
  because the first thirty characters of the absolute one are repeating your
  own answer back at you. Plus the last recording it found, so the line has
  something that visibly moves and is not a counter.

- **Two ways a channel count can be wrong are now told apart**, because they
  mean opposite things. Below a multiple of 32: files are missing, since the
  rig records in banks of 32. Above 128: files are *doubled* — a
  `CSCn_0001.ncs` beside every `CSCn.ncs`, which is what Cheetah writes when
  acquisition restarts mid-session, and the loader reads only the first of
  each pair. A real scan of `D:\KCNT1\urethane` finds 55 recordings at 128
  channels and then one at 53, three at 192, one at 190 and one at 256 —
  which is a sentence worth reading while the scan is still running.

- **A finished scan says how much of it was news.** The server already
  counted how many of the recordings it registered had never been seen on
  any machine; it was in the payload and only ever used to decide whether to
  re-render.

- **Progress is reported on the clock, not every 25 folders.** A folder
  count is a different interval on every drive — seconds apart on a network
  share, hundreds of times a second on a local one. A quarter of a second is
  the same interval everywhere, and finding a recording gets a shorter leash
  than walking past a folder, because it is the event somebody is watching
  for.

### Fixed

- **The path is no longer clipped.** It was one `nowrap` line with an
  ellipsis, which cut off the *end* — and the end is the recording folder,
  the only part of it worth reading. It wraps now.

- **`project_source` could be set to "manual" by a test.**
  `web/_dev/housekeeping.html` drives the project picker and put the value
  back afterwards but not the source, so a real recording was left reading
  "set by hand" with nobody having set it by hand. That is not cosmetic: a
  manual project is immune to the re-filer and raises no filing flag, so
  every run of that page quietly immunised whichever recording happened to
  be first in the tree. `set_project` takes a source now, and only a restore
  passes one.

- **Two scan harnesses were sharing one fixture.** Both register what they
  find and both forget it afterwards, and forgetting is permanent by design
  — so whichever ran first tombstoned the three recordings and the second
  could never register them. Each gets its own fixture, with its own animals
  as well as its own folder, since a recording is identified by mouse and
  start time rather than by the folder above it.

- **A harness whose own script does not parse is now a failure.** There is
  no build step here, so a syntax error is not a red line in a terminal — it
  is one module quietly never assigning itself, or one page running none of
  its checks and reporting "0 ok, 0 fail", which reads exactly like a page
  that has no checks by design. Both happened today. `tools/check_js.py`
  parses every module and every inline harness script in about a second, and
  the runner now fails a page whose title never moved off "running".

## 2026.09.18.2 - A path that disagrees with its project now says so

### Added

- **A recording whose own path names a different project raises a flag.**
  Not a re-file — a question, put where somebody can answer it.

  The word this exists for is "urethane", and it is worth writing down why
  it cannot be a rule. It appears in this lab's data in two different
  roles. In `D:\KCNT1\urethane\wt\...` it names a project: KCNT1 Urethane
  is a separate body of work from KCNT1, with its own mice and its own
  session numbers that happen to collide. In
  `...\CTL\rejects\M15_s3_baseline_urethane` it names the anaesthetic, and
  that recording is PTEN. A pass that reads the word and re-files on it
  moves the second pair out of the project they belong to, and does it
  silently.

  So the chip says what the path says and what the record says, and leaves
  the decision. Setting the project by hand is what clears it, because
  `project_source = manual` is already how this codebase records that
  somebody decided — including deciding to leave it exactly where it is.

  Eighteen of 571 recordings raise it today: sixteen filed KCNT1 whose
  paths read KCNT1 Urethane, and the two PTEN recordings where the word is
  the drug.

- **Clicking the chip opens the project picker on that recording.** The
  picker lives in Housekeeping and nowhere else, so a flag raised on a
  Sessions card now has somewhere to point; the flag is restated in full
  beside it. A `Project worth a look` filter finds them all at once.

### Fixed

- **`fromRegistry` was dropping the field on the way to the card**, which
  is precisely the failure its own comment warns about: a translation that
  quietly loses a field makes a filter that matches nothing, and that reads
  as "none of them qualify" rather than as a bug. The flag is also copied
  onto rows a scan already placed — otherwise the chip appeared on the
  recordings nobody had scanned and vanished from the ones somebody just
  had.

- **A fixture path glued onto a real recording is now detached, not
  ignored.** `scanreg.html` tidies up after itself by forgetting records
  whose paths are all under its temp folder, guarded additionally on the
  `m9xx` keys it mints. But a fixture whose timestamps collide with a real
  recording re-identifies to *that* recording, and the fake path is
  unioned onto it — so one sat in the registry as `m001_s002`, attached to
  a real PTEN recording with seven genuine paths, failing the tidy check
  every run. Forgetting the record would have taken the PTEN recording
  with it. It now detaches the fixture paths and leaves the recording.

- **`chan64.html` was picking a 128-channel recording.** Its filter said
  `>= 64`, which was the same thing until the KCNT1 recordings were
  scanned. Every assertion then measured 128 channels against a page whose
  whole subject is that sixty-four fit, and the failure read as a layout
  regression rather than as the wrong recording.

- **`toolicons.html` demanded an icon from a bundle step.** Steps inside
  The Dentist are numbered, not marked — the bundle carries the mark, and
  numbering them is the point because they are meant to be done in order.
  The page was widened to `.tk-tool, .tk-step` when Incisor and Checkup
  moved into the bundle; it now asks each shape for what that shape has.

- **The audit's verdicts are no longer assumed to be `empty`.**
  `scancheck.html` held that every flagged recording was an empty folder,
  which was true while the only flagged things were fixture leftovers. The
  128-channel KCNT1 recordings are flagged `suspect` — their channels are
  split across `CSCn.ncs` and `CSCn_0001.ncs` because acquisition
  restarted, and only the first part loads. That is a real recording with a
  real problem, and calling it empty would be the audit lying.

## 2026.09.18.1 - Braces aligns to the event's own peak, not the biggest one nearby

### Fixed

- **A stamp could be taken off its own spike by a bigger one beside it.** The
  candidate peaks were found with the detector's `dist_ms`, which is 100 ms,
  and the window a stamp may move in is also 100 ms. Two consequences, and
  the second is the one that showed on the screen. The list could hold only
  one peak per hundred milliseconds, so two events closer than that were one
  candidate between them. And with a single candidate in reach, "the nearest
  peak" and "the biggest deflection in the window" became the same choice —
  so a stamp whose neighbour was bigger was moved onto the neighbour, tens of
  milliseconds from the sink anybody could see under it.

  Measured on M8s9feb8's 1213 curated spikes: for 27% of stamps the biggest
  thing in the window is not that stamp's own peak. The old rule landed on
  the window maximum 97% of the time, and on the stamp's own peak 76%.

  **A candidate is now a local maximum that clears the detector's own
  floor** — the same 4.5 SD threshold that decided the stamp existed — with
  12 ms between candidates rather than 100. The floor is the substantive
  half. Finer spacing alone was measured first and is worse than what it
  replaced: with every wiggle in the list, "nearest" means the nearest
  wiggle, and a tenth of the stamps landed on something under half the height
  of the real deflection beside them. A floor with no spacing to speak of is
  a list of events; that is what the assignment was built to choose between.

  Lands within 5 ms of the stamp's own peak for 96% of stamps, against 76%.
  Largest move 97 ms against 89, which is the rule reaching further when it
  has a reason to rather than being forced. Flags fall from 99 to 56, and 39
  of those are `no peak in reach` — stamps with nothing over the floor within
  a hundred milliseconds, now left alone and asked about instead of moved
  somewhere confident and wrong.

  The reading needs one correction to the entry below this one. The CSD was
  recorded there as scattering wider than the voltage — a p95 of 27 ms
  against 17. That was the coarse candidate list, not the measure: with a
  proper one the two agree closely, and CSD stays the default on the
  rationale it was chosen for rather than on that number.

- **The marks stopped moving in the support panels.** Stepping from one stamp
  to the next redrew the main view and left the aid windows showing the set
  as it was when they opened. Which stamp is in focus lives on the marks
  themselves — the painter reads it off each one — and the signature deciding
  whether to send them again summed only the times, which do not change when
  the focus does. So the other windows kept the first copy they were given,
  in which nothing was focused: every mark there drew short and faint, for
  ever.

- **Short marks hung from the top of the panel.** On an image panel the top
  row is the shallowest channel, so a tick dangling from it read as belonging
  to that channel rather than to the time under it. They rise from the bottom
  axis now, and are a little taller.

- **The end-to-end check could not fail.** It gated everything it does on
  the plan naming a channel, which was right when somebody picked one by
  hand and has been dead since the sweep replaced that. With the gate
  permanently shut it skipped the run, the proposal, the flag review and the
  commit preview — four fifths of the suite — and printed "all checks
  passed" underneath. It runs the whole thing now, on the smallest curated
  set that holds at least twenty spikes: small enough to be worth running,
  real enough that the sections have something to check. It still never
  writes to the bank.

- **A voltage run was filed as a CSD one.** The measure was written into an
  alignment set's parameters as the literal `csd` rather than the one asked
  for, so a set made with the voltage said otherwise afterwards — and those
  parameters are the only record of how its numbers were made. It records
  what it was asked for now, along with both peak spacings and the candidate
  floor, which are what the numbers actually turn on.

## 2026.09.17.18 - Braces measures the CSD, and the overview can be dragged taller

### Changed

- **The magnitude is taken of the CSD, not of the voltage.** A voltage
  raster at any one site is mostly what is happening somewhere else: the
  field spreads, so a sink two hundred microns away shows up almost as
  strongly as one on the contact. The current source density is the second
  spatial derivative across depth, which is exactly the part that cannot be
  volume-conducted — a dentate spike is a current sink, and this is where the
  current actually went.

  Each channel is filtered 5–100 Hz first, then the derivative is taken
  across depth, then rectified, then averaged over the band. `csc.compute_csd`
  is the same function the CSD panel draws from: one derivative in this
  codebase, not two that could disagree about a sign.

  **Smoothed across depth before differencing**, which is not optional. A
  second difference amplifies whatever differs most between neighbours, and
  on a real probe that is usually one noisy contact rather than any current.
  Measured on M8s9feb8: the bare derivative put CSC27 at 46,000 between
  neighbours at 14,000 — a spike one contact wide, which no current sink can
  be, and which would have dragged the depth band onto a bad wire.

  **And it is a setting, because the data does not yet say it is better.** On
  M8s9feb8's 1213 curated spikes both measures find the same systematic
  offset — a median of −4.5 ms against the voltage's −5.9 — and the CSD
  scatters wider around it: a p95 of 27 ms against 17, a largest move of 89
  against 43, and 99 stamps unlike their neighbours against 1. Whether that
  spread is the CSD seeing variation the voltage smears over, or a derivative
  amplifying noise as derivatives do, is a question about this lab's
  recordings and not about the code. CSD is the default; the voltage is one
  button away, on the same set, so the comparison can be made rather than
  argued.

- **The overview strip can be dragged taller.** Forty pixels is enough to see
  where you are in a recording and not enough to read anything in it — which
  matters the moment something is drawing marks down there, because a whole
  recording of them in forty pixels is a smear. Drag the line above it,
  double-click to put it back. Remembered in the preferences, and it is the
  same strip in every pane of every view, so DS curation and StrataScope get
  it too.

- **Braces draws the window a stamp was allowed to move in.** The rule made
  visible. Two lines ninety milliseconds apart mean nothing without it —
  there is no way to tell whether the far one was even a candidate.

### Fixed

- **A `?csc=` in the address no longer takes over the view.** It sent the app
  straight to XploreFinder, so reopening a window that still carried one — a
  restored tab, a shortcut, yesterday's pop-out link — put somebody in a
  trace view they had not asked for while a recording they had not asked for
  loaded underneath them. The recording still opens; it opens in the
  background, and says so once. The view is whatever the address actually
  says: the hash where there is one, which is how the aid windows ask for the
  trace view, and the pipeline where there is not.

- **Two rows highlighted at once in the version chooser.** It matched the
  selected version by NUMBER, and the number is not unique — two machines
  curating one entry both mint the next one and the union keeps both, which
  is what the per-version id exists for. On an entry holding two v1s that is
  two rows lit and one radio filled, which reads as the dialog having lost
  track of what you picked. Matched on the version itself now, which needs no
  id to be present — and the histories that predate ids are exactly the ones
  most likely to collide.

## 2026.09.17.17 - The boot screen waits for the app to stop moving

### Fixed

- **Clicking during start-up got you taken somewhere you had not asked to
  go.** The overlay came down one frame after the first view was shown —
  while the recording open, the job list and the sync check were all still in
  flight. So the interface was live and clickable with three things still to
  land on it, and a click during that window was overruled a moment later by
  whichever of them finished. That is the "it keeps snapping me all over the
  place and back to XploreFinder after I have already clicked".

  It now waits for the things that MOVE THE PAGE — which on a normal start
  is the recording open — and comes down when they land.

  Capped at a second and a half, and the cap is the point. An overlay that
  waits on a slow drive is one somebody sits behind wondering whether the
  app has hung, and the thing being prevented is a click landing in the
  wrong place, which stops being likely the moment somebody has had time to
  read the screen. A registry read that fills a list behind a skeleton is
  not held for at all: that is a wait belonging to the view that wants it.

### Changed

- **The boot screen is a recording.** It was a pulsing rounded square, which
  is the boot screen of anything. It is now a scope: a trace across the
  window with dentate spikes going past, a recording head sweeping left to
  right, and the line drawn bright behind it. The waveform is real path data
  in the same shape as the mark in the rail and on the favicon, not a spinner
  wearing a costume.

  Two things it does that the first attempt did not. The trace is already on
  the screen, dim, before the head reaches it — otherwise the scope is empty
  for the first third of every sweep, and on a boot that takes half a second
  that is all anybody ever sees. And the drawing uses `pathLength="1000"` on
  the path, so the dash lengths are thousandths of the path rather than user
  units somebody has to measure by hand and keep in step with the `d`.

  Still says which step it is on, still says so out loud when a step has
  genuinely been slow, and still holds completely still for anybody who has
  asked for less motion.

## 2026.09.17.16 - The set list is a list, and entering a mode is one movement

### Fixed

- **`wireTimeGrab is not defined`, on every pane.** The drag hook went in as
  two call sites and a function, in a script that checked its last assertion
  *after* replacing the text and *before* writing the file — so the assertion
  failed, the function was never written, and a follow-up added only the
  calls. `node --check` cannot see that: an undefined identifier is perfectly
  good syntax and only fails when the line runs, which for a handler wired
  inside a pane is minutes after the page loads.

  The function exists now. Its `mousemove` and `mouseup` are on the window
  rather than the pane, because a drag that leaves the plot is still the same
  drag and one that ends outside it still ends.

- **The set list was a stack of grey slabs with the names floating in the
  middle.** It borrowed `.bm-row`, which was written for a `<label>` wrapping
  a radio button. On a `<button>` that inherits the browser's own grey face
  and centred text, and neither is anything the class says. Its own row now:
  the name, the session under it, the size and version on the right, all left
  aligned, on a quiet ground that only lifts under the pointer.

### Changed

- **Entering a mode is one movement instead of five.** Opening Braces swaps
  the view, opens the recording, drops a banner in at the top, rebuilds the
  panes into a new layout and jumps the window to the first stamp — five
  reflows in a row, which reads as the interface being thrown at you.

  The workspace now dims and lifts a few pixels while all five happen and
  settles once, and the banner slides down rather than appearing. At the
  interface's own `--ease-dur`, which the rail, the log dock and the radio
  already move at: a mode arriving at a speed nothing else uses would be its
  own kind of jarring. StrataScope and Checkup get the banner and the settle
  too, being the same arrival.

  It undims on every way out of the arrival, including the two that fail —
  a workspace left invisible because the recording would not open is a worse
  bug than the one this fixes.

  Nothing moves for anybody who has asked for less motion.

## 2026.09.17.15 - Braces marks say which one you are on, and stamps can be dragged

### Changed

- **The marks are drawn by Braces, not by the curation painter.** That one
  draws every mark the same way, which is right for curation — one mark per
  candidate, coloured by the decision — and wrong here, where each stamp is
  TWO marks meaning different things and the pair being decided has to stand
  out from the forty others on screen.

  The rules, which are the whole of it:

  | | |
  |---|---|
  | the one in focus | full height |
  | everything else | a short tick from the top |
  | where it goes | solid, green |
  | where it was | dashed, and the colour says what was decided |

  A dashed line is faint while nobody has said anything, amber while it is
  flagged and waiting, and green once it has been confirmed. So a screen of
  them reads as a pass in progress rather than as a field of identical
  ticks.

  The focused pair also gets a hairline between the two ends with the
  distance on it. That number is the decision, and reading it off two lines
  and a time axis is arithmetic nobody should have to do.

  The same painter draws on the overview strip, so the one being decided is
  findable in the whole recording and not only in the window.

- **"Confirm" and "Keep it" now say what happens to the stamp.** They named
  what the button did rather than where the stamp ended up — and "keep it"
  reads as *keep the new one* at least as readily as *keep the old one*.
  They are **Move it → 27.800** and **Leave it · stays at 27.894**, with the
  first reading **It is right · already on the peak** where there is nothing
  to move.

### Added

- **Undo, on the row and on the pass.** A decision made by pressing one key
  has to be undoable by pressing one key, or people stop pressing the key.
  `u` forgets the one in view; *Undo every decision* clears the pass after
  asking. Both go through the same route as a decision — an explicit null on
  the row — so this window, the aid window and the server all learn about it
  the way they learned about the decision.

- **A stamp can be dragged onto its peak.** `xplore` gained a hook for a
  mode to claim pointer drags on a pane and be told the time under the
  pointer — wired on the same host, and torn down with the same list, as
  bookmark placement, because it is the same geometry question and a mode
  answering it itself would be a second copy of `timeAtPointer` to drift
  from the first.

  Three rules. The line follows the pointer immediately and locally, because
  a line that lags the mouse is worse than no line. The other windows follow
  on a throttle, because the marks are the payload and twelve hundred stamps
  is twenty-four hundred of them — at sixty moves a second that is a
  megabyte of publishing for a gesture lasting half of one. And nothing is
  decided until the button comes up: a drag still happening is not an
  answer.

  Only the stamp being decided can be grabbed, and only from within a window
  of it. Taking whichever mark is nearest the pointer would let a twitch
  move a stamp three screens away with nothing on screen to say which.

## 2026.09.17.14 - Braces stops shadowing the function that changes the view

### Fixed

- **The main window never left the ToolKit panel, because Braces had its own
  `setView`.** The function that draws the proposal was called `setView`, and
  a local function of that name shadows core's `setView(name)` for the whole
  module. So every `setView('xplore')` in this file called the proposal
  renderer, got a DOM node back, threw the argument away, and left the app
  exactly where it was.

  Everything downstream ran perfectly — the recording opened, the aid window
  popped out with its four panels, the marks were published and kept — all
  of it underneath a page that was still showing the summary. Which is
  precisely what "it opens the support panels but the main window does not
  change" looks like from the outside.

  Renamed to `proposalView`, for what it draws.

- **The reason column was drawn as ovals.** `.why` is already a class: the
  little round help button, fifteen pixels square with a 50% radius and
  italic text. A 50% radius on a wide table cell is an oval, and the italics
  came along with it. The column is `.br-why` now — renamed rather than
  fought, because the round one was there first and belongs to somebody
  else.

### Changed

- **The set is chosen by typing.** It was a dropdown of forty-six, whose
  names are "Incisor CSC42", "m33s8" and "DS candidates (ETS)" — a list you
  read three times to find the one you meant. The box matches on the set's
  name and on the session it belongs to, which are the two things somebody
  actually knows when they come looking, word by word and in any order: both
  `pten m22` and `m22 pten` find it.

- **Entering the view records every step.** This mode has now failed in five
  different places, and each time the report was that nothing happened —
  which is the one report nothing can be done with. Opening, opened, laid
  out, ready, and any failure with its reason, all go to the activity log,
  and a throw while drawing says so on screen and leaves the mode cleanly
  instead of half-open.

## 2026.09.17.13 - The Braces view keeps the marks it publishes

### Fixed

- **The trace view never changed, because the live sync deleted the marks a
  second after they were drawn.** `xplore` keeps every window in step by
  reading the curation channel and calling `adoptCuration` on each session —
  and `adoptCuration`, handed nothing, DELETES `curationMarks`. The window
  running a curation is skipped, and it is identified by `sess.curation`.

  Braces set the marks and never claimed them. So the marks went up, the
  next sync came round, found nothing on the channel for this recording, and
  took them straight back down. Everything about the mode was working except
  that it was arguing with the sync and losing.

  It claims the session now, the same way Checkup has since it was written,
  and hands it back on the way out.

- **The aid window had no way to receive them.** `adoptCuration` re-reads the
  set from `/api/curation/<gid>/<kind>` — right for curation, impossible for
  anything else, because Braces marks are not a curation set and no route
  would serve them.

  A pointer may now carry its own marks, and one that does is adopted as it
  stands. That costs the fetch nothing, and it means the overlay is usable
  by any mode with something to show rather than only by the one with a set
  behind it. So the before-and-after lines are on the CSD, the theta, the
  voltage and the spectrogram too, not only on the traces.

  The marks travel only when they have actually changed. Stepping through
  twelve hundred stamps would otherwise publish twenty-four hundred marks on
  every arrow key; the receiving side already knows how to follow a pointer
  without them so long as the count still matches, and a float sum of the
  times tells a stamp moving from a cursor moving.

## 2026.09.17.12 - The Braces view opens its aid panels

### Fixed

- **The Braces view opened the traces and nothing else.** Checkup puts the
  traces in the window and the CSD, theta, voltage and stacked spectrogram
  in a second one; this mode set the traces pane and stopped there, so the
  four panels that make an alignment decidable never appeared.

  They open now, and for a stronger reason than in Checkup: deciding whether
  a stamp is on the right deflection means seeing the CSD and the theta
  beside it, because a dentate spike has a shape across depth and one trace
  does not show it. The aid window reads the same `sess.curationMarks` this
  mode publishes, so the old and new positions are drawn on all four panels
  too.

  Its own window NAME, not Checkup's. `window.open` reuses a window by name,
  so two modes sharing one means entering either steals the other's panels.

- **A blocked pop-up left the mode looking like it had done nothing.** The
  traces opened, four panels did not, and there was no way to tell that from
  broken. The aids now fall back into the main window as a four-pane layout,
  with a line saying why and how to get the roomier one back. Cramped is
  something somebody can work with; absent is not.

## 2026.09.17.11 - The Braces view

### Added

- **Braces opens on the recording, as a mode.** The last version set some
  marks and appended a bar, which is why nothing about it behaved like the
  view it was meant to resemble. It is a mode now, the way Checkup and
  StrataScope are: `setMode` frames the workspace in the mode's colour,
  names it across the top, and gives the app one way out that runs the same
  teardown however somebody leaves — and a mode with no entry in that
  registry gets no banner and no Leave button, which is most of what was
  wrong.

  What it shows that Checkup does not is **every stamp twice**: where it
  was, muted, and where it is going, in the accent. A whole run of them
  reads at a glance, and the one being decided has its own colour rather
  than only being the one in the middle — panning away should not lose your
  place. Said in the banner too, because a viewer who does not know each
  stamp is drawn twice is looking at twice as many dentate spikes as the
  recording has.

  It publishes into `sess.curationMarks`, which every pane, the overview
  strip and the pop-out aid window already read, so the marks appear
  everywhere without a second drawing path.

- **Two passes, and the one that matters is the default.** *Needing a
  decision* shows only the stamps Braces would not vouch for; *All of them*
  shows the set. It opens on the first, because that is the pass with work
  in it, and falls back to the second when there is nothing waiting — the
  same rule Checkup uses for the same reason, that opening on an empty
  screen reads as broken.

- **Stamps can be moved from the trace.** `[` and `]` move the one you are
  on by a millisecond — one sample at the rate everything here is measured
  at — with five-millisecond steps on the bar beside them. The marks
  repaint as it goes, so the line being moved is the line being watched, and
  `0` puts it back to the proposal. Confirm with Enter, keep it where it was
  with `k`, and either sends you on to the next one still waiting.

### Fixed

- **Undoing a decision never reached the server.** The route reads `call`
  only when it is not null, so a null was dropped and the row kept whatever
  it had. Clearing one now goes through `calls`, where an explicit null is
  the documented way to drop a row — which `bracesset.decide` has honoured
  since it was written and nothing was using.

## 2026.09.17.10 - Braces reads where the spikes are, not the whole recording

### Changed

- **It reads the windows, not the hour.** Alignment asks, of each stamp,
  where the event is within a hundred milliseconds of it. Reading every
  channel end to end to answer that is reading an hour to use four minutes
  of it. The windows are worked out from the stamps, merged where they
  overlap so a burst is one read rather than five, and only those are read.

- **It reads the channels that can see the event.** A dentate spike is
  depth-specific: large across the hilus, small or absent at the top of the
  shank. Averaging all sixty-four buries it under channels that never saw
  it, and costs four times the reading to do so.

  So a short pass over a sample of the stamps measures the depth profile,
  and the average is then taken over the sixteen contiguous channels with
  the most signal. Contiguous on purpose — the channels a dentate spike is
  big on are the ones at that depth, and taking the top sixteen by score
  would be free to pick a scatter of electrodes from three depths that
  happened to be noisy, which is not a measurement of anything.

  On M8s9feb8 the profile runs from 134 µV at CSC1 up to 1481 µV at CSC41
  and back down to 112 µV at CSC62, and the band it picks is CSC33–48. That
  shape is now drawn in the panel, because it is the one picture that says
  whether the measurement is being made in the right place: a profile that
  does not rise to a peak and fall away means the set is not what it says it
  is, and no count in that panel says so.

  Together: **160 seconds to 70**, and the answer barely moves — median
  −5.9 ms against −5.6, p95 16.9 against 16.5. The largest move comes DOWN,
  59.7 ms to 42.9, which is what a cleaner measurement should do.

- **The progress says which pass and how far through.** Two stages now, both
  counted: *Finding the depth — channel 23 of 63*, then *Reading window 137
  of 206*, with an ETA that is right to a few seconds.

### Added

- **Browse them on the recording.** The bench is a magnifier on one
  alignment; this is the other thing somebody wants — the recording itself,
  with every stamp drawn where it was and where it is going, so a run of
  them can be read in context rather than one at a time through a keyhole.

  It publishes into `sess.curationMarks`, the shape every pane, the overview
  strip and the pop-out aid window already read, so the marks appear
  everywhere without a second drawing path. Each moved stamp goes in twice,
  muted where it was and in the accent where it goes. `n` and `p` step, `f`
  jumps to the next one needing a decision, and the two decisions can be
  made from the bar without leaving the trace.

### Fixed

- **Thirty-six stamps were flagged as weak peaks that were nothing of the
  kind.** The noise floor was `np.std` over the samples that had been read —
  and every one of those windows is there BECAUSE it contains an event, so
  the events were most of the variance and the floor came out high. The
  whole-recording read raised that flag on none of them.

  It is a median absolute deviation now, scaled the way
  `incisor.threshold_for(estimator="mad")` scales it: a statistic about the
  middle of a distribution rather than its tails, which is what a floor
  wants to be and is why that function offers the option at all.

## 2026.09.17.9 - Braces knows which channels are bad, and says how far along it is

### Fixed

- **Every channel came up ticked, on recordings with bad channels on
  record.** `csc.open_session` writes `"bad": False` on every channel it
  builds — which channels are bad is not in the `.ncs` files, it is a
  decision somebody made about the recording, and it lives in the session
  record keyed on identity. `_incisor_spec` has looked it up separately since
  it was written; Braces read the flag that is always false.

  So the list said 64 of 64 and the average quietly included the wire
  somebody had thrown away. One place now, called by the plan, the run and
  the bench, so the ticks on screen are the ticks the read honours. On this
  archive that is CSC59 on almost every recording, and 8, 41 and 59 on
  m33s8.

- **"Reading the channel…" for three minutes, with a bar that never moved.**
  Two faults on top of each other.

  A job's stages come from a fixed list in `cfc.STAGES`, and anything not on
  it is dropped silently — no stage, no progress, no error. The comment above
  that line warns about exactly this. `ds profile` was not on the list, so
  the job had no stage to be at. It is now, with its own name rather than
  Incisor's: it counts channels read whole where `ds read` counts seconds of
  recording, and `_learn` divides seconds by units without knowing which, so
  sharing a name would have rewritten Incisor's read rate by the length of
  the recording every time somebody aligned a set. It sits before the two
  Incisor stages because a job keeps its stages in that list's order, and
  listed the other way round the job reports its steps backwards.

  The panel then read `job.step` and `job.frac`, neither of which a job
  snapshot has. It carries `stages`, each with how many units it has and how
  many are done, plus an ETA. So the line now says **Reading channel 21 of
  63** and **about 2 minutes left**, and the bar moves.

### Changed

- **A proposal opens with what it would do, not with six panels of
  statistics.** The counts, the histogram and the table each answer a
  different question and all three are worth having, but none of them
  answers the first one: is this worth banking. There is now a sentence
  above them — *1055 stamps would move, by −5.6 ms typically, 59.7 ms at
  most. 4 need a decision first — look at those below, then bank it.* — and
  it says outright that nothing has been written and which version the set
  is still on.

  The button at the bottom names the version it would become rather than
  saying "Accept", so the order of the thing is legible without having
  pressed anything: see what it would do, look at the ones it is unsure of,
  then bank it.

## 2026.09.17.8 - Braces measures the probe, not a channel

### Changed

- **There is no channel setting, because the question was never about a
  channel.** A dentate spike is a population event: it appears across most of
  the shank at the same instant, largest near the hilus and smaller either
  side. Picking one electrode and finding its peak answers *when was it
  biggest here*, which is a question about that wire as much as about the
  event — and measured on M8s9feb8, the best and second-best channels scored
  within **0.3%** of each other. Another way of saying that the pick was
  close to arbitrary.

  Braces now averages the DS-band magnitude across every ticked channel into
  **one trace**, and each stamp goes to the highest point of that inside its
  window. One noisy wire cannot carry it and a dead one cannot sink it. The
  magnitude is what makes the average mean anything, incidentally: a signed
  sum across a probe cancels, because the deflection reverses across the
  layer.

  Accumulated channel by channel rather than stacked — sixty-four channels of
  an hour at 1 kHz is 230 million floats held at once, and one accumulator
  plus one channel is two arrays.

  It agrees with the old measurement where it should. On M8s9feb8's 1213
  spikes the single-channel run gave a median of −5.6 ms and a p95 of 16.4;
  the profile over all 64 gives −5.6 and 16.5. Two different measurements of
  the same offset landing on the same number is the best evidence either of
  them is right.

- **Bad channels are ticked off, not thrown out.** Every channel is listed
  before the run with the ones this recording has marked bad already
  unticked. Hiding them would make an average look like it was over the whole
  probe when it was over fifty-six of sixty-four; unticking says the same
  thing, is visible, and is one click to undo. Which channels went in, and
  which were left out, is recorded on the proposal and on the version.

- **The bench draws the profile.** It used to draw one channel's trace, which
  is a line that peaks a few milliseconds from where the decision was
  actually made — the exact disagreement this tool exists to remove, shown to
  the person being asked to adjudicate it. It now draws the summed profile
  over the same channels, read on the server, because six hundred
  milliseconds of sixty-four channels is a short read on that side and
  sixty-four requests on this one.

### Added

- **A move unlike the others is flagged.** The existing *near the edge* rule
  is about the window: it catches a stamp that went nearly as far as it was
  allowed to. That says nothing about a set whose jitter is small. On
  M8s9feb8 the median move is 5.6 ms and the largest is 59.7, and at a
  ±100 ms window not one of those trips an 80 ms edge — so the stamp that
  went sixty was confirmed silently along with the twelve hundred that went
  five.

  Unusual is now measured against the set's own spread, robustly: six median
  absolute deviations, scaled the way `incisor.threshold_for(estimator="mad")`
  does it, with a floor so that a set whose moves all agree to the
  millisecond does not find every one of them remarkable.

  On that recording it asks about four of 1213. Two of them are neighbours
  200 ms apart moving in opposite directions, +39.3 ms and −59.7 ms, which is
  a burst where the assignment had real work to do and a person should see
  it.

  It also matters more than it did. Averaging drops the noise floor without
  dropping the peaks, so nearly every peak in the profile clears the 4.5 SD
  that *weak peak* is measured against — which left the whole set arriving
  with no flags at all. A review pass that never asks anything is not a
  review pass.

## 2026.09.17.7 - Braces picks its own channel, and stops asking for a number two versions share

### Changed

- **Braces finds the channel itself.** It used to ask, and on this archive
  that meant asking every time: forty-one of the forty-five curated sets were
  banked before Incisor existed and record no channel anywhere. Falling back
  to the recording's hilus channel only moved the problem, because most of
  them have no hilus channel on record either.

  It now reads every channel, filters 5-100 Hz, takes the magnitude, and at
  each stamp looks at the largest value inside the window that stamp is
  allowed to move in. The channel with the highest median across the set
  wins.

  **Measured at the stamps, not over the recording.** A channel's overall
  magnitude is a fact about how noisy it is; what decides where a dentate
  spike should be measured is how big the dentate spikes are on it, and the
  set already says when those happened. Averaging over the whole trace would
  hand the answer to whichever wire hums loudest.

  **Ranked on the median, not the mean.** One artifact inside one stamp's
  window is enough to carry a mean on a set of eighty, and the question is
  where the typical event looks biggest. The margin travels with the answer
  the way Incisor's channel pick does — a win of thirty per cent and a win of
  two are different facts about a probe, and only the second is worth a
  second look.

  A channel can still be typed in, and then it is used and said so. Which of
  the two happened is recorded on the proposal and on the version, because a
  channel chosen by sweep and a channel chosen by hand must not be
  indistinguishable afterwards.

  On M8s9feb8's 1213 spikes it picks CSC40, with CSC41 and CSC39 a fraction
  behind — a smooth gradient down the shank, which is what a real answer
  looks like. The margin over the runner-up is **0.3%**, and the panel says
  so: adjacent sites see the same spikes at almost the same size, so the
  choice between those two is a coin toss. It is worth knowing rather than
  worth worrying about — the alignment lands in the same place either way,
  a median of −5.6 ms on both.

  **Swept once, not once per run.** Reading sixty-four channels is 208
  seconds, and which channel a recording's dentate spikes are biggest on
  does not change between two runs over the same band. Every proposal already
  records the sweep that produced it, so the cheapest store is the one
  already there: a previous proposal on the same recording, asked the same
  question. No new book, nothing to go stale against a recording, and it is
  visible to anybody who opens that proposal rather than hidden in a cache.

- **The alignment floor is gone.** It was a knob that could only be wrong.
  Peaks are found with a spacing rule, which already makes each one the
  largest thing within a hundred milliseconds of itself — so every peak found
  is a candidate a stamp could sensibly move to, and a height requirement on
  top of that could only remove the right answer for a real event whose peak
  on this channel happens to be small. Which is the case alignment exists to
  handle.

  The detector's own threshold is still computed, because "this peak is
  smaller than the detector would have called an event" is worth saying on a
  row and is what the *weak peak* flag means. It is a remark, not a gate, and
  the bench draws it as a line so it stops being an assertion.

### Fixed

- **The version chooser listed v3 twice and v4 twice, and picking one was a
  coin toss.** Both halves of that were real.

  The duplicates are real data and are correct: two machines curating one
  entry both mint the next number, the union keeps both, and the per-version
  id is what tells them apart — `versions.py` has said so since it was
  written, and this bank holds a history numbered 0,1,2,3,4,3,4. What was
  wrong is that Braces listed them by number, so two rows were the same
  sentence twice, and then sent that number back to be resolved by taking
  whichever came first in the file. Asking to read "v3" could read one
  person's pass while naming the other's.

  The list is now named through the lineage labeller the curation version
  chooser already uses, which walks `from_v` and gives the second line its
  own name — v3.1 rather than a second v3. And the id, not the number, is
  what travels back — except where there is no id to send. Versions minted
  before ids existed have none, and this archive still holds plenty: three
  of the eight on M8s9feb8. Those fall back to their number, which is the
  only handle they have -- except that the stored number is the one thing
  that is NOT unique, so that fallback reproduced the fault it was meant to
  cure: the chooser showed **v6**, sent back **4**, and the bank replied
  about a version numbered 4 that nobody had seen. The two halves of one row
  disagreed about which version it was.

  An id-less version is keyed on what it contains instead: its number, its
  time, who made it, its note and its size. Derived rather than minted, so
  nothing has to be written into the archive to make old versions
  addressable; content-based rather than positional, so a shard arriving
  between choosing and running cannot shift it. Checked against every
  version of M8s9feb8: all eight now resolve to the one the chooser names.

  Asking the bank for a version by a number only one version has still
  works; asking by a number two versions share is refused, and the refusal
  hands back the keys to choose between rather than being a dead end.

- **Picking which version to read is a list, not a dropbox.** A dropdown
  shows one line at a time, and the thing being chosen between is which pass
  of curation to work from -- which is a question about who did what, when,
  and what picking it would do, none of which fits on the one line a `select`
  gives you.

  It is drawn with the same parts the curation version chooser uses: the
  radio, the version chip, what is in it, what picking it would do, and who
  and when. Not the same function -- that one is built around a curation
  history with a bench to restore onto, and reshaping this into that contract
  would mean inventing fields to satisfy an adapter. The look is the part
  worth sharing, and it was already styled down to the disabled rows and the
  wrap at narrow widths.

  Versions that cannot be a starting point are listed rather than hidden,
  greyed, with the reason on them. Their counts and their notes are still
  worth reading, and a version that silently is not in the list reads as a
  version that does not exist.

- **The sweep reads every channel and says how each one scored.** It used to
  drop the ones marked bad before it started, which produces a ranking
  somebody reads as complete. They are listed now and arrive unticked, so
  leaving one out is visible and putting it back is one click -- and the
  result carries the whole table rather than only the winner, because the
  shape of that column is the answer: a gradient down the shank is a probe
  working, and a flat table is a set measured against the wrong thing. No
  single number says either.

- **Braces threw on every set with no channel on record.** `Cannot read
  properties of null (reading 'number')`, seven times in one sitting.
  Teaching the panel that a channel might be missing left one row still
  reading it as though it never could be. Moot now that the channel is swept,
  and fixed anyway: a value that can be absent has to be absent everywhere it
  is read.

## 2026.09.17.6 - The curation list stops asking the same question forty-eight times

### Fixed

- **Opening Event curation took four and a half seconds.** Measured, not
  guessed: `/api/curation` came back in 4537 ms on this archive, and it now
  takes about 400.

  `REG.by_gid` is not a scan — it keeps an index, and it has since the last
  time this was slow. What it does on every call is re-check the session
  shards' signature, to know the index it is holding is still good. That
  check is 77 ms here. The curation list called it once per set, which at
  forty-eight sets is forty-eight freshness checks of a list that cannot
  change halfway through being built.

  The index is now built once for the request, exactly as the bank
  summaries already were three lines above it and for the same reason. The
  freshness check is worth its cost once and nothing at all per row.

  Nothing else changed: the same forty-eight sets come back with the same
  session records and the same histories.

- **Braces threw on every set that does not record a channel.** Which is
  forty-one of the forty-five curated ones — `Cannot read properties of null
  (reading 'number')`, seven times in one sitting. Making a missing channel
  a question rather than a refusal left the panel still reading the answer
  as though it were always there. The row now says "not recorded — pick one
  below", the reason is printed under it, and **Line them up** stays
  disabled until there is a channel to aim at, rather than offering to start
  a read it cannot point anywhere.

- **Braces asked for its tool feed fifteen times in thirty seconds.** The
  panel rebuilt itself on every tick of the job poll — four times a second
  while a read was running — and rebuilding empties the panel host, which
  takes ToolKit's tool feed with it. The feed's own observer then mounted a
  fresh one, and a fresh mount is a request.

  Two halves, both fixed. The read now repaints only the progress bar, since
  nothing else on that panel changes while it runs. And ToolKit's observer
  coalesces: a panel that rebuilds does not fire once, and every firing that
  landed while the feed was absent used to mount another.

### Changed

- **A banked set can be named when it is banked, and renamed with the
  session already in it.** The names in this bank are "Incisor CSC61",
  "m33s8", "dupes seed" and "DS candidates (ETS)". Every one of them made
  sense to whoever typed it while they were looking at the recording, and
  none of them says which animal, which session or which day — so the Event
  Bank is a list of forty-five things you have to open to tell apart.

  Incisor now asks what to call a set at the moment of banking, with the
  session already filled in, rather than assembling "Incisor CSC61" silently.
  The Edit dialog — which could always rename an entry — gets the same
  suggestion on a button beside the field, and says so more loudly when the
  current name carries nothing about which recording it belongs to.

  Offered, never imposed. A name somebody chose on purpose is not a mistake
  to be corrected, so nothing is renamed without a press, and the rule lives
  in one place because two callers need it and a second copy would drift.

### Removed

- **The Dentist's step counts.** The rail was reporting how many DS sets are
  banked, how many decided and how many aligned. It was a number nobody
  asked of a rail, and the route behind it went with it rather than being
  left as something nothing calls.

## 2026.09.17.5 - Curation remembers where you were

### Added

- **Leaving a curation set and coming back lands you where you left off.**
  The decisions always survived; the place never did. Coming back to 430
  candidates with no idea whether you had reached 134 or 208 means
  re-reviewing the overlap to be safe, and that is the real cost of
  switching tabs to look something up — paid in minutes, every time.

  Kept per recording and per kind, in the same synced preferences file
  `span` already lives in, whose own header has said "where was I" since it
  was written. It is remembered **by candidate, not by index**: a set can
  gain or lose candidates between sittings — a re-import, a dedupe, a
  snapshot folder absorbed — and an index would then point at a different
  spike with perfect confidence. The candidate's id is what survives that,
  with its time as the fallback for a set rebuilt from a snapshot, which
  does not carry ids.

  The pass is restored before the position, because landing on candidate 208
  while the Undecided pass is showing would put you on a candidate that pass
  does not contain, and n/p would then walk away from it. A remembered pass
  with nothing left in it is dropped rather than restored — that is what
  happens when somebody finishes the undecided pass and comes back, and
  opening on an empty screen is the fault this sits next to.

  It says so on the way in: *Back where you left off: 208 of 430*. Landing
  in the middle of a set with no explanation reads as a bug, and the point
  is to be able to trust it. Where the candidate itself has gone, it says
  that too, and lands on the next one along rather than at the top.

  Written on the way out as well as on every jump. Preference writes are
  coalesced by a third of a second, and leaving is exactly the moment
  somebody is about to do something else.

### Changed

- **The loading line at the top of the window is twice as tall.** It was a
  two-pixel hairline, which was doing its job and being missed — nobody is
  watching the top of the window while they wait, so it is only ever seen
  out of the corner of an eye, and two pixels is not enough to catch one.
  Four now, over a faint track so the sweep reads as one object travelling
  rather than a glow appearing and vanishing at the edges, with a soft
  shadow that lifts it off the pale header on the light themes.

  Still fixed, still a fixed height. That was the constraint — it has to be
  able to appear during a mutation without shifting the list somebody is
  reading — and the thinness was never the point.

  It also now stays put rather than disappearing for anyone who has asked
  for less motion: it stops sweeping and holds. An indicator that vanishes
  under a motion preference is the one case where that setting costs
  information rather than saving annoyance.

## 2026.09.17.4 - The Dentist, and stamps that sit on their own peak

### Added

- **Bundles, and the first one.** The ToolKit rail was a flat list of nine
  tools with nothing to do with each other, three of which are one job done
  in three sittings. **The Dentist** groups them: Incisor finds the dentate
  spikes, **Checkup** says which ones are real, **Braces** puts every stamp
  on the peak it belongs to. The steps are numbered because the order is a
  real dependency rather than a suggestion — Checkup has nothing to show
  until Incisor has banked candidates, and Braces has nothing to move until
  Checkup has said which stamps are spikes.

  Grouping them is the small half. Each step reads its own state, so the rail
  says where the lab is — *56 DS sets banked, 45 of 56 decided, 0 of 45
  aligned* — rather than listing three tools that happen to be related.

  Checkup is a name on a door, not a second engine. `curation.py` is
  deliberately one engine with a vocabulary per kind, because deciding
  *dentate spike or garbage* and deciding *solid or sputter* are the same job
  once you stop looking at the biology; the flat tool list keeps **Event
  curation** for anyone arriving to do IEDs. One engine, one set of keys, one
  version history, two doors.

- **Braces.** A set's stamps are only as good as the trace they were measured
  against. A set detected on CSC38 and read back against CSC41 is a few
  milliseconds out, because adjacent sites on a shank see the same spike at
  slightly different times; one that came through Toothy was measured on a
  1 kHz grid over a nominal rate; one imported from a snapshot folder has
  whatever time was in the file name. None of that is wrong enough to notice
  one event at a time, and all of it is wrong enough to smear an average
  across a thousand.

  Braces reads one channel, band-passes it 5–100 Hz, takes the magnitude, and
  puts each stamp on its own peak within ±100 ms. Measured on M8s9feb8's 1213
  curated spikes against CSC41: 4161 peaks found in three seconds, a median
  shift of −5.6 ms, and nothing further out than 18.9 ms. The shift histogram
  is one tight lobe left of zero, which is what a systematic offset looks
  like and is the thing this tool exists to remove.

  **Magnitude, not the signed trace.** Incisor runs `find_peaks` on the
  signed trace, which is why polarity is a correctness question there and not
  a preference. A stamp that arrived from Toothy, from a snapshot folder, or
  from somebody's hand may sit on a trough. `|x|` finds the event under
  either convention, and is the one measure that does not care which tool
  produced the stamp.

  **A lower floor than detection.** Detection asks *is anything here*;
  alignment asks *where is the thing we already know is here*. Making each
  peak clear 4.5 SD a second time would strand the real events whose peak on
  this channel is a little smaller — and this channel is often not the one
  detection ran on. The floor is half the set's own detection threshold, so
  it travels with the parameters the set was made with rather than being a
  new number nobody chose.

- **One peak per stamp, and no crossing.** Nearest-peak-wins is wrong, and
  wrong in a way that quietly loses events. Take two stamps and two peaks
  where the first stamp sits between the peaks nearer the later one, and the
  second can only reach the later one: nearest-peak-wins gives that peak to
  the first stamp and the second — a real, curated dentate spike — is left
  with nothing. The right answer moves the first stamp *further*, onto the
  earlier peak, so the second can have the later one.

  So the objective is not "move as little as possible". It is, in order:
  match as many stamps as possible, then move them the least in total,
  subject to a stamp taking at most one peak, a peak being taken by at most
  one stamp, and the assignment never crossing. Solved per *run* — the
  contiguous group of stamps and peaks that can reach one another — which on
  real data is one stamp and one or two peaks and is settled by inspection.

  The two constraints are not decoration. Without **one peak per stamp**, two
  stamps snap onto the same peak and the set acquires two events at an
  identical time, which the bank's duplicate machinery would then make
  somebody resolve by hand at 0.1 ms. Without **no crossing**, two events
  swap places and their curation calls follow them — a Garbage and a Dentate
  Spike trading identities. Events in a recording do not reorder, so neither
  may this. Both are checked again immediately before the write.

- **Only the stamps somebody called a dentate spike.** A curated set is not a
  list of events; it is a list of candidates, most of which are events and
  some of which were looked at and rejected. Garbage and unsettled Flags are
  kept out of the run **entirely**, not filtered out of the answer
  afterwards: one peak per stamp means a Garbage stamp sitting nearer a peak
  would take it, and the real spike beside it would be stranded or pushed
  onto the wrong one. What was left alone is counted and named on the
  proposal rather than quietly dropped.

- **Most of them arrive confirmed.** Four situations Braces will not vouch
  for, each pre-flagged with its reason: *no peak in reach* (the stamp does
  not move), *near the edge* (further than 80% of the window, where the peak
  it found is about as likely to be the next spike as this one), *not the
  nearest peak* (the run overrode nearest-peak-wins so a neighbour could have
  one — the only flag that reports a decision the tool actually made), and
  *weak peak* (cleared the alignment floor but not the detection threshold).
  Everything else confirms on arrival, and anything can still be flagged by
  hand.

- **A proposal is not a version.** Running Braces writes nothing to the bank.
  What comes out is an alignment set — the measurement, plus every decision
  made about it — kept in `GUI_logs/braces/` so that reviewing twenty-six
  flags does not have to happen in one sitting. The decisions are a `MAPLWW`
  field, so two people reviewing different flags on one proposal merge row by
  row. Accepting it previews exactly what the write would do first, the way
  re-timing already does, because a timestamp rewrite that cannot be read
  before it happens should not be offered at all.

  **A flag nobody resolved does not move.** Not moved quietly on the grounds
  that the proposal was probably right — the flag exists because the tool
  would not vouch for it, and accepting it by default would make the flag
  decorative. The count of them sits beside the button.

### Changed

- **The event bank can tell a stamp that moved from one that was deleted.**
  A banked event's only identity was its time. That held until something
  moved one, and Braces does exactly that — so an aligned set would have
  arrived as every event vanishing and an unrelated one appearing, and the
  history would have read *1198 lost, 1198 gained* about a pass in which
  nothing was decided differently at all.

  A stamp Braces moved now carries `from_t`, the time it used to have, and
  the diff matches in two passes: every event still where it was claims its
  own slot first, and only the leftovers are matched on where they came from.
  The order is not a style choice — one pass, whichever key it preferred,
  could hand a moved event the slot belonging to an event that had not moved.
  Versions gained a `shifted` count, written only when something did.

  `from_t` also had to be added to the whitelist `add()` builds each event
  from. It was being dropped on the way in, which is the same fault seen from
  the other end: the field exists to make the next diff possible, and a diff
  that cannot see it is blind again.

### Fixed

- **A registry row has no `path`.** It has `here` — the folders *this*
  machine can actually reach, which is not the same list as `paths`, because
  a recording seen on the rig and on a laptop has two and only one of them
  opens here. Asking for `path` returns nothing for every recording in the
  archive, so the first version of Braces reported that not one of the 45
  curated sets could be aligned. `curate.js` has taken `here[0]` since the
  workbench was written; this now does too, and a recording that is known but
  not plugged in gets a different sentence from one that was never recorded
  against a session at all.

- **Forty-one of the forty-five curated sets say nothing about which channel
  they were detected on.** They were banked before Incisor existed. That was
  a hard refusal, so the tool worked on nothing anybody actually has; it now
  falls back to the recording's own hilus channel, and where there is not one
  either it *asks* rather than refusing — the panel has the box, so a missing
  channel is a prompt, not a failure. Which of the four ways the channel was
  arrived at is always said out loud beside it, because a channel chosen by
  rule and one chosen by hand must not be indistinguishable.

- **Older entries store `label` without `label_id`.** Their `by_label` reads
  `{"Dentate Spike": 10}` rather than `{"spike": 10}`, so matching the
  dentate-spike category by id alone silently skipped every real stamp in
  them — which would have looked like a set with nothing to align rather than
  like a bug. Matched by id *and* by display name, and by whatever the entry
  itself calls them.

## 2026.09.17.3 - The band line says which channel it came from, and can carry ten

### Added

- **Choose the channels the band line is read from - up to ten.** It read
  whichever channel happened to come first in the selection, which answers "is
  there theta in this recording" and not the question people actually bring to
  this strip: which channel has it, and how do they compare down the probe.
  The Strip panel now lists the channels it is reading as chips, each with the
  colour its line is drawn in, and offers the rest in a dropdown. A chip takes
  its channel off again; the last one stays, because an empty strip still
  labelled Band power is a blank picture with no way to tell why.

  Ten is the cap. They share one 40 px band, so past ten they are stacked
  hair-widths.

- **Every line on one scale.** The reason to put two channels on one strip is
  to compare them, so the scale is computed across all of them together. A
  per-line scale would draw a weak channel and a strong one at the same height
  - the picture saying they match while the numbers say one is ten times the
  other.

- **Name each line on the strip.** Optional, because names cost room on a strip
  this short, but five unlabelled coloured lines is a picture nobody can put in
  a figure. The channel is written at the end of its own line rather than in a
  legend box: on a 40 px strip a legend would be most of the picture, and a
  label sitting on its own line needs no key to read.

  Colours come from a fixed ten-step ramp rather than the theme's categorical
  one, which guarantees four and wraps after that - and two channels drawn the
  same colour on one axis is worse than drawing them in no colour at all,
  because you cannot tell there are two. A single line keeps the accent colour
  it has always had, so turning a second channel off puts the strip back
  exactly as it was.


## 2026.09.17.2 - The Strip panel answers the button you press

### Fixed

- **Band power looked like a dead button.** Pressing it on the overview
  strip's panel left the highlight sitting on Average magnitude, and the band
  boxes, the presets and the measure switch never appeared - so the one
  control the choice exists to reach was unreachable, and the panel read as
  broken. It was not: the strip redrew, the reading happened, and the menu
  button relabelled itself to "4-12 Hz power" the whole time. The only thing
  that did not change was the panel being looked at while pressing it.

  A segmented control paints its highlight from the value it was built with.
  The Marks switch gets away with that because it closes itself on the way
  out, so it is rebuilt on the next open; this panel deliberately stays open,
  because picking Band power is the step *before* choosing the band, and so
  nothing ever rebuilt it. Open panels can now rebuild in place from their own
  builder - not by rebuilding the control strip, which would detach the very
  button the panel belongs to. The same fault was in the band presets and the
  measure switch, and the "reading the recording" note that never cleared when
  the read landed; all four are the same fix.

  Typing is left alone: the band boxes commit on change, so a rebuild arriving
  mid-number would throw the number away, and a read finishing is exactly what
  would land there.

## 2026.09.17.1 - Layers on any panel, and only where they mean something

### Added

- **Which layer a panel is showing, on the panels that have no channel
  lanes.** The layer look reaches every pane through the More menu, but a
  single-channel spectrogram, scalogram or band-power map is one channel seen
  against frequency: there are no channel rows to band, so those panels
  answered the question with nothing at all, which reads as "layers do not
  work here". They now carry a chip naming the region that channel is in, in
  that region's own colour. It works from whichever sheet the window has - the
  read-only look's, or StrataScope's while the labelling mode is open - so the
  same panel says the same thing whichever door you came in by. A channel the
  sheet has no label for gets no chip, rather than a chip naming nothing.

### Fixed

- **The read-only layer look painted channel bands down a frequency axis.**
  It kept its own copy of the overlay, and the copy had its own fallback: when
  a panel reported no channel rows it laid the sheet's channels evenly down the
  plot anyway. On a band-power map and on a single-channel spectrogram that is
  64 layer bands across an axis measured in hertz - measured, not inferred. The
  labelling mode's own overlay had been taught this rule; the copy never was,
  which is how a copy nobody can see is a copy ends up.

### Changed

- **One layer painter instead of two.** The copy existed because three things
  were private to the labelling module: the wash vocabulary, the current
  strength, and any way to paint at a strength of your own. All three are now
  shared, so the read-only look calls the same painter the labelling mode does.
  Everything about which lane is which channel, and whether the lanes are
  channels at all, has one answer instead of two that could drift - and the
  four strengths are read from one list rather than copied into a second that
  had to be kept in step by hand.

- **The layer selection stays with the mode doing the selecting.** Leaving
  StrataScope does not empty the set of picked-out channels - it never had to,
  because nothing else could reach the overlay. Now that something can, a
  selection left behind on the way out would have come back as an accent wash
  in a view whose whole promise is that it changes nothing.

## 2026.09.16.5 - Band power on the strip, a version to work from, and layers you can just look at

### Added

- **Theta power across the whole recording, on the overview strip.** The strip
  has always drawn average magnitude, which answers "is there signal here" and
  not much else. It can now draw the power in a band you choose instead, with
  the edges settable and presets for the usual ones, as absolute power, as a
  fraction of the 1-100 Hz total, or against a delta reference. This is the
  line `theta_through_time.py` draws, on the true time axis, with the 60 Hz
  line bridged out of the total and a gap in the recording coming through as a
  hole rather than as zero power. What is cached is the spectrogram surface
  rather than the line, so moving a band edge is an integral over numbers
  already in memory, not another read of the disk.

- **Which banked version a curation sitting carries on from.** A set is one row
  per recording per kind, but the bank behind it keeps every pass anybody ever
  banked - seven of them on one real entry. Picking a set up said nothing about
  which of those the sitting continued, so banking always landed on top of
  whatever was newest, which silently buries the work that came after whenever
  somebody goes back to an earlier pass on purpose. Both doors now ask, and
  every row says what pressing it will do before it is pressed: `continues from
  v4 as v5`, or `branches off v1 as v1.1, leaving what came after it alone`.
  Switching while a set is on the bench puts the current version down and picks
  the chosen one up, says how many decisions that will change first, and clears
  the undo history - replaying a decision across a switch would put a call
  nobody made into a pass they did not make it in. Versions banked without a
  snapshot cannot be worked from, so they are shown greyed with the reason
  rather than offered and then refused.

- **Layer bands in XploreFinder, read-only.** The layers a recording has been
  given in StrataScope can now be shown in the ordinary viewer, from the
  per-pane More menu, at three strengths and with a colour key of the regions
  actually in the sheet. It is a look, not an edit: no rail, no keyboard, no
  mode, and the only request it makes is a GET. The bands are painted into the
  pane canvas underneath the marks and the traces, so they sit behind
  everything else rather than covering it, and nothing can swallow a click.

### Fixed

- **The layer overlay no longer paints channels onto a frequency axis.** The
  overlay was extended from the traces onto every image panel, which is right
  for the panels whose rows are channels - the CSD, a stacked time-frequency
  view - and wrong for the ones whose vertical axis is frequency. A
  single-channel spectrogram or scalogram has no channel rows to report, and
  the band-power map has none either, so the overlay fell through to its
  every-channel default and laid the layer colours evenly down a frequency
  axis: the hilus band sitting across 40-60 Hz as though it meant something.
  Sixty-one bands and four boundary rules, in the right place for a picture
  that was not there. It now draws only where a lane is genuinely a channel,
  which is worse-looking and correct.

- **A window that was handed the layers can now draw them.** `sess.strata` has
  carried the labels and the regions since it was written, put there for the
  reason the curation marks are published the same way: a pop-out page has its
  own session objects and none of the labelling module's private state. But the
  overlay checked for that private state before doing anything, so any window
  not doing the labelling stopped at the first line and the payload was never
  once drawn from. The comment beside it has described the intended behaviour
  all along; it is now true.

- **The DS span no longer freezes at one second.** Moving through detected
  events re-derived the window width from a preference that was not being
  written, so a span set by hand was thrown away at the next jump and every
  recording came back at 1.00 s. The manual zoom is now adopted and kept.

- **The bank import harness tested the wrong recording.** It typed the mouse
  rather than the whole session label, so the picker offered the first session
  that animal ever had instead of the one with the banked entry, and then
  clicked an option class the picker does not render - so nothing was selected
  at all and the wizard kept its default. The "already exists" check downstream
  then failed on a recording that genuinely has no set, reporting a fault in
  the interface that was really a fault in the harness. It now types the label,
  clicks what the picker actually draws, and asserts its own starting state
  first.

## 2026.09.16.4 - Incisor draws the channel it is choosing between

### Added

- **Toothy's three channel plots, in the Incisor panel.** DS count, DS
  amplitude and DS height above surround, drawn from the scan that is on
  screen - the same three `ephys.py:1144 plot_channel_events` puts beside
  Toothy's own channel picker, in the same cubehelix palette, so a plot
  people have been reading for years looks like itself here. The hilus
  estimate is an argmax over normalised count x normalised amplitude; these
  are the picture that argmax came out of, which is what says whether the
  pick was obvious or a coin toss.

- **Click a plot to put the hilus on that channel.** All three share one
  axis and any of them takes the click. The chosen channel is banded behind
  the data in all three at once, and hovering reads out that channel's
  count, mean amplitude and mean height.

- **"Most spikes" as its own answer.** The scan's pick weighs how big the
  events are as well as how many, which is usually the right trade and
  sometimes is not - a hilus site next to a quiet one can come second on
  amplitude while carrying nearly every spike in the recording. Measured on
  PTEN m1 s2: the scan picks CSC41 at 27 events and 601 microvolt mean,
  while CSC42 carries 79. The button names the channel and its count, and
  the panel says in words when the two part company. It is offered, never
  applied: "the most events are here" and "the hilus is here" are different
  claims and the second is the one being banked.

- **Channels that were not read are drawn as grey columns rather than left
  out.** A gap you can see is how "CSC59 is excluded" reads off the plot
  instead of off a sentence above it, and an absent channel and a channel
  with no events are different facts that a bar of height nothing conflates.

### Changed

- **The amplitude axis is scaled to the amplitudes.** Pinning it to zero
  spent the lower two thirds of the panel on the range below the detection
  threshold, which is empty by construction. The count axis still starts at
  zero, because a bar chart that does not lies about its ratios, and it
  labels whole numbers whole - there is no such thing as 73.0 dentate
  spikes.

- **The colour ramp is oriented to the background, not copied blind.**
  Seaborn's walk from light to dark puts the busiest channel at the darkest
  point, which is right on Toothy's white figure and invisible on a dark
  theme - measured on screen, the tall bars came out near-black on a
  near-black ground. "A lot" is now always the end that stands out. On the
  light themes it is Toothy's ramp exactly.

- **The plots are drawn synchronously as well as on the next frame.**
  `requestAnimationFrame` does not fire in a background tab, and a panel
  whose plots are blank until you look at it twice is worse than one that
  costs a layout flush. Found by a harness: after a repick the canvases were
  still at the HTML default 300x150 with nothing on them.

### Fixed

- **A scan carries the shape statistics the plots need.** Each channel now
  reports the mean half-prominence height with its standard error - Toothy's
  `width_height`, taken the same way its `.agg('sem')` takes it - and a
  sample of at most four hundred amplitudes, strided so it spans the
  recording rather than its first minutes. The sample exists because all of
  them is not affordable: sixty-four channels of every event is the payload
  that arrives as a 200 with a body that will not parse. The count beside it
  is exact and is never taken from the sample.

---

## 2026.09.16.3 - The cluster, and what it can already read

### Added

- **VACC Mode.** A switch in the rail foot that turns the interface up and
  turns the cluster on, because they are the same thing: the interface is
  fired up *because* the cluster is live. `data-vacc` is a second attribute
  on the root, orthogonal to `data-theme`, and it adds six `--fire-*` tokens
  and touches none of the thirty a theme defines.

  That restraint is not tidiness. `--accent-soft` and `--on-accent` are
  hand-written per theme rather than derived, and `--on-accent` is *measured
  ink* for one exact accent -- #14231b on the gold, #ffffff on the light
  themes. CSS has no contrast function, so mixing a hotter accent here would
  produce text nobody has checked can be read on it. `vaccskin.html` reads
  all thirty tokens in all ten themes with the mode off and on and asserts
  every one is byte-identical, so the claim is checked rather than promised.

  Ten themes, three blocks. Everything is mixed from the theme's own accent,
  so a theme added later is covered the day it is added -- and the light
  family gets weight and edge instead of glow, because a bloom on parchment's
  #faf6ef is a coffee stain and on jirai-shiro it is a greetings card.

  One thing pulses, and only while a job is actually being polled: `opacity`
  on one pseudo-element, never a shadow or a filter, because xplore repaints
  its canvases every pan frame and an animated shadow above them drags the
  whole stack with it. A permanently glowing workbench is one people quietly
  stop using, and it would also be a lie.

- **What VACC knows.** Every recording now says whether the cluster can
  already read it, and **357 of 582 can** -- 61%, with no transfer of any
  kind. The lab keeps most of its recordings on `bigdata_jbarry`, which VACC
  mounts at `/netfiles/bigdata_jbarry`, so what looked like a file-transfer
  problem is mostly a path-mapping one.

  Asked of the RECORDING, not of the path in front of you, and that is the
  whole design. 2544 recorded paths begin with `Y:`, and `net use` on this
  computer reports no mappings at all -- those paths were written by a
  different machine. But a recording carries every path it has ever been
  opened from on any machine, unioned, so the UNC spelling a colleague
  recorded answers for the drive letter this one cannot expand. Mapping by
  drive letter alone would have found 117 of the 582; going through the
  registry finds 357.

  Four states, and the fourth earns its place: `unknown` draws nothing.
  Exact ids are only minted when headers are read, so most of a fresh scan
  has no gid, and reading a missing answer as "the cluster cannot reach
  this" would have put an upload badge on four hundred recordings already
  sitting on the share. `canOpen` in sessions.js carries a comment about the
  identical mistake. A staged copy takes the warning colour rather than the
  green one, because scratch is purged without notice and green would read
  as a guarantee.

### Fixed

- **A run on the cluster would have corrupted every estimate on this
  computer.** `_learn` folded each measurement into the volume-blind key as
  well as the per-volume one -- right for a second disk, wrong for a second
  machine -- and `_PER_VOLUME` covers only the four reading stages, so
  `ds detect`, `panorama windows`, `panorama pool` and the rest collapsed to
  the bare name whatever ran them.

  Measured: one cluster run drags this machine's `ds detect` rate from 0.15
  to 0.108, a 28% shift, and at 0.7/0.3 it takes about ten local runs to wash
  back out. It runs both ways -- the cluster's ETA would have quoted the
  desktop. Nothing had happened yet, which is the only reason this is a note
  rather than a repair.

  Fixed in `_key`, deliberately not by adding stages to `_PER_VOLUME`:
  `_stage_stamp` hashes that set, so widening it would have dropped every
  affected rate on every machine in the lab at the next start.
  `tools/test_rates.py` asserts the membership so the wrong fix fails loudly.

- **Queue wait is not a rate.** It is seconds at three in the morning and
  hours before a deadline, and a running mean over the two describes
  neither -- while `eta` would have added it to the total from t=0, making
  the bar wrong from the first paint rather than settling. `vacc queue` is in
  a new `_NOLEARN`; slurm answers the question properly with `squeue --start`.

### Changed

- `applyTheme`'s three repaint calls are now `repaintThemedSurfaces()`. Which
  surfaces read a token once and keep the answer is not obvious, the list has
  been wrong before, and there are now two things that change tokens.

- **The cluster is not an empty machine waiting to be filled.**
  `/gpfs2/scratch/sakhava1` already holds 1.3 TB and **120 recordings** across
  four projects -- KCNT1 Urethane, IED, DEWEY/HOF and Wheel -- all 64-channel,
  all put there before any of this existed. Thirty-three of them are
  recordings the registry already knows, matched by `ids.identify` run on the
  remote path: the same code that identifies a local folder, from the path
  string alone, so nothing about identity is reimplemented for the cluster and
  the two cannot drift. Another eighty-four are real recordings Jarvis has
  never been shown, and they are reported rather than dropped.

  So while the netfiles share is unreadable, there are still thirty-three
  recordings that can be run on the cluster today with no transfer at all.
  A listing of scratch is never written down: it is a filesystem that gets
  purged without notice, and a durable record of it would be a claim with an
  expiry date. Asked, cached five minutes, and re-asked on a button.

- **Incisor now runs on the cluster, and gets the same answer.** Measured on
  `s0a9e96cf1739`, a recording that exists both on scratch and on this
  machine's D: drive: four channels, **691 dentate spikes, and not one of
  them stamped at a different microsecond**. The channel picks agree, the
  per-channel counts agree, and `abs_us` -- the one identity that does not
  depend on which tool made the number -- is identical throughout. Eleven
  seconds here, thirty-two on the cluster including the queue.

  It is the same arithmetic because it is the same code. `vacc_run.py`
  imports `backend.incisor` and calls the `run()` the desktop calls; the
  backend is tarred over ssh and unpacked into a workspace keyed by content
  hash, so an unchanged tree skips the upload. The continuity report travels
  with the spec rather than being recomputed, because it is inside the cache
  key and a segmentation that came out even slightly differently there would
  file the answer under a name no local run ever looks for.

  The environment was built to match: miniforge 26.7.2-py3.14 against this
  machine's 3.14.4, numpy 2.5.3 against 2.4.6, scipy 1.18.1 against 1.18.0,
  and fooof 1.1.1 against 1.1.1 -- exact where it matters most, since fooof
  is the fitter. `env_check` records all of it.

- **Incisor, over every recording the cluster can reach, as one job array.**
  `Scan all on VACC` in the ToolKit panel: one `sbatch --array`, every
  recording a task, `%N` capping how many run at once. Twenty-eight
  recordings, sixteen of them new, **nine and a half minutes at four at a
  time and nothing failed**. The other twelve were already answered and were
  skipped in milliseconds -- the vault is keyed on the recording and the
  settings, so a batch that dies halfway resumes and a colleague running the
  other half is not doing yours.

  The first version of this was serial: submit, wait, submit the next. It
  took forty minutes to do about ninety seconds of work at a time, on a
  machine with thousands of cores, and `poll_states` had taken a LIST of job
  ids since the day it was written. The lab's own `.sbat` files have used
  `#SBATCH --array` with a `dirs=()` for years.

- **A queue of finished scans, and nothing banked without being looked at.**
  Each row carries the pick, how far it beat the runner-up, and whether it
  has been banked. Opening one points the panel at that recording and
  re-runs it, which comes straight back out of the vault -- so the three
  plots, the hilus pick and the Bank button are the ordinary ones on the
  ordinary path, and behave the same whether the numbers were computed here
  or on a compute node.

  **Twenty-seven of thirty-one picks came back within ten percent of the
  runner-up.** The hilus estimate is an argmax over normalised count times
  normalised amplitude, and on this data it is very nearly a coin toss
  almost every time -- which is the whole argument for the plots being on
  screen beside it, and for a person pressing the button.

### Three wrong recordings, caught before anything was banked

All three would have analysed one recording's data under another's name,
and none of them would have looked wrong on screen.

- `m22 s3` exists in PTEN recorded 2024-07-15 and in KCNT1 recorded
  2023-06-02. The loose key -- mouse and session -- is
  character-for-character identical, and the first version took whichever
  came last out of the listing. It offered to run the PTEN scan against the
  KCNT1 data. Exact keys now beat loose ones outright.
- `m13 s3` and `m2 s2` had no exact match at all, so the loose one won by
  default: PTEN 2023-08-01 matched to KCNT1 2022-08-15, a year apart. A
  loose match must now agree on the day, which is the only thing left that
  distinguishes them.
- And one genuine duplicate -- the same recording sitting in two folders on
  the cluster -- is refused rather than guessed at, because nothing here can
  tell which was meant.

Twenty-eight matches remain and every one of them has a label date that
agrees with its folder date. `mouse+session is not an identity` was already
written down in this lab; numbering restarts per project.

### The parity check lied three times before it worked

Written down because each lie was a confident pass, and because the shape of
them is the same shape every time: a check that cannot say how much it
checked can quietly check nothing.

- Four channels were picked without looking and all four were silent. Zero
  events here, zero there, reported as agreement. It now scans for channels
  that have events and **fails** if none do.
- The local result keys `_rows` by int; the one off the cluster arrives
  through JSON, which has no integer keys. Indexing the remote with an int
  found nothing, `zip` yielded no pairs, and a loop that compared NOTHING
  reported a maximum difference of exactly zero.
- The event's time field is `start`, not `t`. Asking for `t` got `None` from
  both sides, and `None == None`.

`tools/check_vacc_parity.py` now prints how many events it compared and
asserts that the number equals how many there were.

### What the real cluster taught, once there was a key on it

Four things, and three of them would have been invisible from here.

- **The share is mounted and the account cannot read it.**
  `/netfiles/bigdata_jbarry` is exactly where the path map says, and 357
  recordings resolve onto it. It is also `drwxrws--- jbarry4 root`, and every
  lab member's primary group is `pi-jbarry4`. So the only account that can
  read the lab's own share is the PI's, and the group it is shared to is one
  nobody is in. Nothing in this feature can run until that is changed.

  Which is why "VACC mounts this" and "you can read it" are now two separate
  facts on the status payload rather than one. A path map is a lab-wide fact
  and stays one; whether the person sitting here can open what it points at
  has a different answer per account, and answering the first while being
  asked the second sends somebody to debug a job that was never going to be
  able to open its input.

- **`quota -s` never returns on the login node.** Measured: whoami 1 ms,
  squeue and sinfo 6 ms, quota a flat 5003 ms, which is the `timeout 5`
  expiring every single time for an answer that never arrives. It was in the
  probe, so the probe took 61 s. Moved behind a button; the probe is now
  0.4 s, which is 150x, from deleting one line.

- **sacct does not print the id you asked about.** `sbatch --parsable` hands
  back a raw numeric id; for anything in an array sacct prints the
  array-and-task form beside it -- measured, `sacct -j 999999` answers
  `999467_3|999999|COMPLETED`. Keying on what it prints loses the job, and
  the poller then fails a run that finished an hour and forty-nine minutes
  ago as vanished. Keyed on `JobIDRaw` now, with the printed form kept for
  anything shown to a person.

- **And one that was ours.** `subprocess.Popen(text=True)` translates
  newlines on Windows, so every script sent to the cluster arrived with CRLF.
  bash read the last line of a one-line script as `fi\r` and reported a
  syntax error, and a `$(whoami)` inside a `printf` picked the stray CR up and
  returned `sakhava1\r` -- which produced a malformed answer from a cluster
  that was replying perfectly, and read exactly like the login node doing
  something strange to command substitution. The pipes are binary now and the
  encoding is done by hand. A comment blaming the cluster has been corrected.

  Worth recording next to it: the first round-trip figure written into this
  feature was eleven seconds, and every poll interval was set from it. It came
  from a shell loop whose `date +%s` had one-second resolution and whose own
  `timeout` and subshells dominated the measurement. Six consecutive calls
  measured properly: 389, 395, 417, 417, 433, 441 ms. The harness was being
  measured, not the cluster.

### Checks

- `vaccskin.html` (53), `vaccmode.html` (21), `vaccquiet.html` (23) and
  `vaccknows.html` (18). `vaccskin` is two-sided on purpose: the unchanged
  side alone passes if the layer does nothing, which is exactly its state
  before the tokens land, so the changed side asserts the mode is real and
  that `color-mix` actually *resolved* -- a typo'd token stays a literal
  string and looks like it applied.
- `vaccquiet` walks every element for a running animation with the mode on
  and no job live, and measures body text and every `on-` pair against 7:1
  and 4.5:1 in all ten themes with the mode on.
- `tools/test_rates.py`, `tools/test_vaccpaths.py`, `tools/vacc_check.py` and
  `tools/test_vaccrun.py` -- the last two drive the whole cluster state
  machine against a stubbed login node, because every interesting thing about
  a remote job is a failure and none of them can be produced on demand
  against a real one. Timeout, out of memory, a dead node, a cancel arriving
  before the job id does, and the window where a finished job is in neither
  `squeue` nor `sacct` and a naive poller calls it vanished.

---

## 2026.09.16.2 - Rooms, and a result that says what it is of

### Added

- **The catalogue has rooms.** Four hundred results in one grid ordered by
  when they happened answers exactly one question -- "what did I just do" --
  and it is the only question that stops mattering. Group by animal, by tool,
  by day or by run. Headings are sticky and double as "select everything in
  here", because taking the eleven figures from one session is the thing you
  came to a room to do.

  Anything the grouping does not apply to goes in one room at the end rather
  than each getting a heading of its own. A lab-wide bad-channel export
  genuinely belongs to no animal, and forty headings reading "unknown mouse"
  is the pile again with chrome on it.

- **Search one field instead of any text anywhere.** `mouse:306` used to match
  a figure of m3060, a figure whose notes said "306 windows", and a file saved
  at 13:06.

      panorama m306            both, as text, as before
      tool:panorama mouse:306  the tool and the animal, exactly
      project:PTEN on:2023-08  every PTEN recording made that month

  Mouse and session are anchored, because `mouse:306` matching m3060 is a
  wrong answer that looks like a right one. Everything else stays a substring
  on purpose. An unrecognised prefix is searched as plain text, since a
  Windows path is full of colons and typing one should look for it.

- **A result knows which animal it is about.** Project, mouse, session and the
  recording's own id come off the run record, which knew all along; the
  catalogue was dropping them. A file with no run record -- a colleague's
  commit, or a tool that predates run records -- has them read off its name,
  because every naming convention the lab uses puts the animal in the name and
  those are exactly the files somebody is hunting for.

- **What a tool has already worked out is kept.** Incisor's scan lived in a
  dictionary in memory holding eight entries, which is why "those candidates
  are no longer cached, run the scan again" is a sentence this app has had to
  say -- a scan is minutes of reading, and being told to redo it because
  somebody restarted Jarvis is not a cache miss, it is lost work.

  It now keeps its answers the way Panorama keeps its: the numbers durably,
  keyed on the recording and on the settings that change them, and the bulky
  per-channel event lists as cache that regenerates. A colleague's scan
  answers your question without being re-run.

### Fixed

- **A figure rebuild could report success and leave the window wrong.** The
  verify step checks what the earlier steps restored and puts back whatever
  has moved since -- channels, bad channels, event marks. The window, the
  filters and the gain were only put back when the whole session object had
  been replaced, so anything that moved the window on the session *already on
  screen* left that check believing the three of them matched the recipe. It
  then said so, out loud, in the sentence that exists to be trusted.

  Which is the exact failure the step was written to catch, in the one shape
  it was not looking for. Intermittent, because it needs a late write to land
  inside the pause the step already takes -- so it appeared when something
  else had been using the recording first and never when a rebuild was run on
  its own.

- **A page of thirty figures was forty-five megabytes.** The grid used each
  figure as its own thumbnail, and the browser decoded every one at full
  resolution to draw it at 150 pixels. Measured here: 20.1 MB of originals
  against 0.25 MB of thumbnails, for the same grid.

- **The Run button on a result opens that run.** It used to go to History and
  reload it, landing you at the top of a list of every run the lab has ever
  done -- having just clicked something that displayed the id of the one you
  wanted.

- **A result's provenance is followable.** It was a list ending in a single
  unbroken line of JSON. The recording now opens, the animal is a search for
  the animal, the run opens the run, and the settings are a table -- which is
  what a rebuild reads back, and what tells two figures of the same recording
  apart.

## 2026.09.16.1 - Results is a folder of results again, and buttons answer

### Fixed

- **Results had 197 files in it and about a dozen were results.** The rest was
  what running the tests leaves behind: forty-five "rebuild harness" PNGs,
  forty-nine debug reports, thirty "arrow harness" exports of which
  twenty-three were byte-identical to each other. All of it committed, to a
  repository whose history is already 1.5 GB.

  Saving now takes a *lane*. **Exhibit** is a result -- somebody made it on
  purpose, it is evidence, and it is committed so a colleague sees it beside
  the log entry that produced it. **Scratch** is a by-product: still written,
  still findable under `Results/_scratch`, skipped by the catalogue and
  ignored by git. The backlog was swept the same way. **Eighty-one files where
  there were two hundred and five.**

  The lane is declared by whoever saves, never guessed from the filename. The
  harness pages drive the real interface from inside an iframe, so their
  requests carry the app's own Referer and are indistinguishable from a
  person's; saying so outright is the only honest signal there is. Debug
  reports are always scratch.

- **Clicking a button now registers.** Delete a banked entry, assign a set,
  flag a recording: the dialog shut, the list carried on showing what you had
  just changed, and a beat later it snapped. It was never the sync -- that
  runs on a background thread and blocks nothing. It was that the answer the
  server had already sent was thrown away in favour of re-reading the whole
  store, that the re-read was expensive, and that nothing was on screen while
  it happened.

  A confirmation dialog holds itself open until the work is actually done,
  rather than closing on the press and leaving the screen empty -- that alone
  covers twenty-three destructive actions. A list you caused to reload dims
  instead of silently lying. Anything slow raises a hairline at the top of the
  window, after a moment's grace so the usual fast case never flickers. And
  the writes people make most -- the session quality chips, archiving a
  curation set, banking a delete -- now move on the click and put themselves
  back if the save fails.

- **The event bank was doing its work three times a request.** `/api/bank`
  returns the tree and the summaries, the tree builds the summaries again, and
  building them took every record apart and reassembled it. Cached: a warm
  read went from **206 ms to 0.18 ms**. Looking an entry up was a scan of the
  whole bank, called once per id inside loops that walk a selection; indexed,
  forty lookups went from **20.8 ms to 0.03 ms**.

- **Labelling a selection in StrataScope was one request per channel** --
  thirty-two channels, thirty-two round trips in series, each rewriting the
  whole sheet. The route had accepted the whole map all along. Painting also
  rebuilt all sixty-four rows every time one was coloured, which during a drag
  meant destroying the row under the cursor.

- **Incisor's "Bank them" and Panorama's "Make the set"** both did their first
  second of work before showing any sign of having been pressed.

### Changed

- **What a tool has already worked out is kept, and it is kept in one place.**
  `panoramaset.py` worked out the shape of this first: a record per
  *(recording, question)*, where the question is a short hash of the settings
  that change the numbers. Ask the same thing twice and the second time is
  free; a bulk run that dies halfway resumes; two people running halves of one
  set are not each doing the other's. The numbers are durable and committed;
  the picture is cache and regenerable.

  That is not a Panorama idea, so it now lives in `toolresults.py` where any
  tool can use it. Panorama passes the field list it always used, so every
  record already on disk keeps its name -- checked against the real records
  and four hundred generated parameter sets.

## 2026.09.15.6 - Incisor says what it read

### Added

- **Bad channels are removed from processing, and Incisor says so.** They
  used to be read like any other, which meant a dead channel could win the
  hilus, theta or ripple pick against the live ones. Now they are never read,
  and step 2 says which ones were left out and names them - or says outright
  that none are marked, because "nothing was removed" and "nothing was
  checked" look identical when a panel only speaks up about the first.

- **And says which probe configuration it was read as.** H3 or H10-D, every
  channel or even-only, inverted or not, with the measurement behind the
  even-only decision quoted. None of it changes when a dentate spike
  happened; all of it changes which channels there were to find one on.

- **Channels can be added and removed without leaving the panel.** A grid of
  every channel in step 2, ticked for read and unticked for bad. The tick
  writes through to the session record - the same one the trace view reads -
  so a channel marked in either place is marked in both. Changing it throws
  the scan away on purpose: every candidate time came out of reading a
  particular set of channels, and a result left sitting under a selection it
  no longer matches is the kind of thing that gets banked by mistake.

### Changed

- **The three landmarks are listed theta, ripple, hilus.** Down the probe -
  fissure, pyramidal layer, hilus - rather than in the order the code
  computes them, so reading the panel reads the same way as reading the
  traces beside it.

- **The traces window opens on a CSD of the even channels over five
  seconds.** A laminar landmark is a boundary, and a boundary reads off a CSD
  where it is a matter of opinion on sixty-four stacked traces. All three are
  starting points and all three can be changed in the window; a pick on a
  channel that view is not showing is marked at its own depth and labelled
  hidden. `?even=1` and `?even=0` now work on any deep link; leaving it off
  still lets the recording answer for itself.

- **Step 3 says what changing the channel does and does not do.** The hilus,
  theta and ripple picks are computed FROM the detection and never feed back
  into it: every channel was detected on separately and carries its own
  candidates, and every time is that candidate's own sample index put through
  the .ncs record timestamps. So switching a channel swaps which set you are
  looking at, instantly and with nothing read again, and moves no event by a
  microsecond. The answer is now in the panel, and `time_basis` carries
  `depends_on_channel: false` for anything reading the payload. What does
  move the picks is the selection in step 2, which is why that is where the
  channels are changed.

- **Channel lines repaint on the rasters, not only on the traces.** They were
  already drawn there - a landmark is easiest to read against the CSD bands -
  but only the traces panes were repainted when one moved, so a dragged line
  sat at its old position on a CSD until something else redrew it.

---

## 2026.09.15.5 - Panorama says what each control does

### Fixed

- **Clicking log or linear bins no longer takes the Holistic view with it.**
  Reported, and the cause was worse than the symptom: the bin scale and the
  bin count were part of the cache key, so changing either missed the cache,
  which meant the result on screen really had become invalid and getting it
  back meant another three-minute run of identical arithmetic. The control
  cleared the panel because there was nothing left to show.

  Neither is true now. A histogram is a count of the per-window dominant
  frequencies, and those are already computed - so re-binning is arithmetic
  on a few thousand floats. The spectrogram matrices are kept beside the
  cached result, so re-colouring is a re-render. The bin count, log or linear
  bins, the colormap and log power all change what is shown, leave the
  numbers alone, and start no job. A setting that really does change the
  measurement - the frequency range, the window lengths - still clears the
  result, because it should.

- **`/api/panorama/recolor` actually re-colours.** It returned the stored
  picture, so choosing a different colormap handed back the one already on
  screen.

### Added

- **Every control in Panorama explains itself.** A small `i` beside each one
  opens a note under it - what the window length and the FFT length are each
  doing, why the frequency range changes how sharp a question the dominant
  frequency is, what the two counting rules actually count, and why the bins
  are log-spaced by default. Under the control rather than as a tooltip, so
  it can be read without holding the mouse still.

- **How clearly the dominant peak won.** A window whose runner-up came within
  a fifth of the winner is a coin toss between two broad bumps, and the
  frequency that came out of it is not a finding. Measured at 84% of windows
  on a real recording over 2-100 Hz and 0% on a synthetic one with a single
  clean rhythm - so it is a property of asking a wide range of a 1/f
  spectrum, not a fault in any recording. Said in the convergence panel,
  where somebody is about to read a group difference off the curve.

## 2026.09.15.4 - Panorama converges

### Added

- **The convergence view.** Every recording in a set, pooled into one curve
  per group - PTEN against littermate, or by any attribute the colony sheet
  carries. The individual recordings are drawn faintly behind each mean,
  because a group mean over six recordings where one is bimodal looks exactly
  like six mildly broad ones and only the individual lines say which.

- **Two defaults that are arguments, not conveniences.** Each recording gets
  **one vote**, not one vote per window: the sampling unit is the recording,
  and windows inside one are not independent, so pooled counts have an
  apparent n of tens of thousands and a real n of however many animals there
  were. And the denominator is the windows that **have** a peak, not all of
  them: a genotype that abolishes a rhythm has to show up as an absence
  rather than as a slightly shorter curve. Both can be switched, and the
  panel says which it used.

- **The no-peak fraction is plotted in its own right**, beside a strip plot of
  one number per recording. The pooled curve is the exploratory object; the
  strip plot is the claim, and the thing a test can actually be run on. They
  are drawn together so nobody reads a group difference off a curve whose n
  is six without seeing the six.

- **Custom groupings**, seeded from what the colony sheet already says so
  nothing is retyped. A recording's whole membership is written at once, so
  moving one between arms on one machine cannot leave it in both after a
  merge - and a recording in two arms of the same axis is refused by name
  rather than counted twice.

- **Saving a convergence** writes the figure, one row per recording, and every
  histogram long-form, with the set id and the question's hash in the
  filename.

- **How clearly the dominant peak won is now recorded.** A window whose
  runner-up was within a fifth of the winner is a coin toss, and the
  frequency that came out of it is not a finding. Recordings where that
  happened often are flagged in the tree.

### Checks

- **`tools/check_panorama.py` compares the GUI with the command line.** On a
  real recording at matched settings, the aperiodic exponent agrees to a
  median of 0.002 and R-squared to 0.0002 - the two fit the same spectra.

  They disagree about the dominant frequency in 9.4% of windows, and the
  reason is now established rather than assumed: it is not the chunk size
  (31% of disagreements near a chunk edge against 23% of all windows) and not
  the recording's gap (1 of 160). In those windows the other's answer is a
  peak in this one's fit too, at a median 0.947 of the winner's power, and
  only 5 of the 160 are below 12 Hz. Theta - the rhythm anybody is asking
  about - is essentially never in dispute. The two agree about the spectrum
  and disagree about an argmax over numbers equal to three significant
  figures, so the check judges the dominant frequency where the winning peak
  actually won.

## 2026.09.15.3 - Panorama over a set

### Added

- **Panorama runs over many recordings at once.** A *set* is a question and
  the recordings to ask it of: pick them from the registry, say which channel
  by anatomy, and it works through them one at a time. The tree shows where
  each one got to while it runs - reading, fitting, done - with its
  dominant-frequency histogram drawn as a sparkline the moment it finishes, so
  the cohort takes shape while the run is still going. Click a row for that
  recording's spectrogram, histogram and spectrum.

- **The channel comes from the layer sheet, or from you.** CSC14 is a
  different depth in every animal, so a set names an anatomical region and
  each recording's channel is read from its StrataScope sheet. Any row can be
  overridden by hand, and overridden rows say so - a channel chosen by hand is
  evidence about that recording, a channel chosen by rule is evidence about
  the rule. A recording with no sheet is left needing one rather than analysed
  on whatever channel happened to be first, which would silently compare the
  hilus in one animal with stratum radiatum in the next.

- **Stopping costs nothing.** Every answer is filed the moment it lands, keyed
  on the recording and the question rather than on the set. So Stop is a
  pause, a restart mid-run loses only the recording that was in flight, and
  adding a recording to a second set that asks the same thing is free. Running
  a finished set again says there is nothing to do instead of spending an hour
  proving it.

- **Everything knowable before a run happens before it.** A recording with no
  channel chosen, or no folder this machine can read, is shown as blocked with
  the reason on its row - rather than waiting its turn behind thirty others
  and then failing. Found by the harness: the registry holds a second,
  pathless copy of each demo recording, and both took their turn before
  failing.

- **The question is frozen when the set is made.** Changing the frequency
  range makes a new set rather than quietly mixing two answers in one
  histogram. Two recordings measured over different ranges cannot be pooled
  and nothing in the file would have said so.

- **Sets survive a colleague.** Two people can run different halves of one set
  from different machines and both halves keep - the per-recording state
  merges key by key, the way layer sheets do. A recording whose job died with
  a restarted process reads as *interrupted*, not as still running.

### Changed

- **Bulk gets a job stage of its own, counted in seconds of recording.** It
  cannot reuse the single-recording stages: `Job.begin` closes whatever stage
  is running, so a stage opens once per run, and bulk has to read, fit and
  discard one recording before the next starts. Folding the fitting into
  `spectrum read` instead would have taught the Spectrum view that reading
  costs what fitting costs. Seconds rather than recordings so the estimate
  holds for a set mixing twenty- and forty-minute sessions.

- **The end of a spectrogram says why it is blank.** `open_session` reports a
  duration from the records and `segment_ncs` reports when acquisition
  actually stopped; on `M8s9feb8` they are 78 ms apart, so the last samples
  correctly have no data. The panel now says so instead of ending in an
  unexplained transparent sliver.

## 2026.09.15.2 - Panorama

### Added

- **Panorama, a new ToolKit tool: the whole recording at once.** The Spectrum
  view answers "how much power, at which frequency" with time collapsed, and
  XploreFinder's spectrogram panel answers "what changed, when" for a window
  you are looking at. Neither answers the question asked of a recording
  before any other: across the whole session, which frequency was in charge,
  and how often?

  Three steps, and they stay on screen together because the answer is the
  three of them side by side:

  1. **Holistic** - the spectrogram end to end, in Jet by default with every
     other colormap offered, beside a histogram of the dominant frequency by
     occurrence. 2-200 Hz and log-spaced bins by default; the range, the time
     range, the bin count and linear bins are all settable.
  2. **Power spectrum** - the whole-recording PSD over the same range, with
     the step size it achieved and how many segments it averaged stated on
     the card rather than left to be worked out.
  3. **Save** - a figure, the spectrum, the histogram and the per-window
     table as CSV, and a JSON of every setting that produced them, into
     `Results/Panorama`.

  This is the analysis that has been living in `FOOOF Playgroun/` as a
  command-line script. It worked, and it could only be run by somebody at a
  terminal, on one session at a time, into a matplotlib window that nothing
  kept.

- **Step 2 costs nothing.** Averaging the spectrogram's columns *is* the
  whole-recording Welch spectrum - same segments, same window, same average -
  so the power spectrum comes off the same read and arrives with step 1. The
  per-window fits come off the same columns again. One read, three answers,
  rather than reading a thirty-minute recording twice to get the same
  numbers.

- **A waiting screen worth watching.** Long runs show both stages with their
  counts and the learned estimate of what is left, and the spectrogram
  **builds up left to right as the recording is read** - the real data
  arriving, not an animation. A run that is obviously wrong can be stopped in
  the first ten seconds instead of at the end of four minutes. The picture
  rides on its own route rather than in the job poll, so it costs the tools
  that have no preview nothing.

- **Both definitions of "dominant frequency", switchable without re-running.**
  The tallest peak the fit actually found - which can be *none*, and a window
  with no rhythm is counted as such and reported rather than quietly dropped -
  and the highest bin left once the aperiodic slope is removed, which always
  returns a number and is labelled for what that means. Both come out of the
  one fit, so the toggle is free.

### Fixed

- **Acquisition gaps no longer shift the spectrogram's time axis.** Reading a
  long channel chunk by chunk and concatenating is right for a spectrum,
  which does not care what order its samples came in, and wrong for a
  spectrogram, whose x-axis *is* time: every column after a gap was drawn
  earlier than it happened, by as much as the gap. Eight of twenty-five PTEN
  recordings have gaps. Panorama lays the signal out on the recording's own
  clock with holes where nothing was written; windows overlapping one are
  drawn transparent and take no part in the spectrum, the fits or the
  histogram, and the panel says how many there were and how much time is
  missing.

- **Adding a job stage no longer costs every other tool its measured
  timings.** `.cfc_rates.json` was stamped with a hash of the whole stage
  table and the entire file was dropped when that changed - so a new tool's
  stages silently reset the comodulogram's, the spectrum's and Incisor's
  learned rates, and every estimate in the app was wrong for one run of each.
  Stamped per stage now: only a stage whose own meaning changed loses its
  number. Existing files are recognised and kept rather than discarded.

## 2026.09.15.1 — One event, written twice

### Added

- **Collapsing duplicate times in a banked set.** Some dentate spikes in the
  bank sit on exactly the same timestamp as another: `m34s8jun10` holds 185
  events on 162 distinct times. They arrive when a set is imported twice, or
  restarted on one machine while another still holds decisions on it, and
  nothing this lab records fires twice inside a tenth of a millisecond — so
  two rows that close are one event written twice.

  Open an entry and the panel says so before anybody asks: a chip at the top
  next to the event count, a strip above the events, and the rows themselves
  marked in the list. "Duplicate times…" opens the collapse.

  It is not housekeeping, which is why it does not run on its own. Fourteen
  of `m34s8jun10`'s twenty-three doubles carry two *different* calls — one
  copy says Dentate Spike and the other says Garbage — so collapsing them
  throws a real decision away. The dialog names every contested time with
  both calls, makes you pick which copy to keep, and will not run until you
  have: keeping the first leaves 52 dentate spikes and keeping the last
  leaves 42, and no sort order should be choosing between those. An
  undecided copy losing to a decided one is not a conflict and is not
  offered as one; nor is a double where both copies agree.

  The preview is the server's own dry run, so what it shows is what the
  write would do, produced by the code that would do it. It lands as a new
  version with the old one kept whole — including its snapshot, so deleting
  the new version puts every removed row back. No decision is changed by it;
  rows go, and the calls on the rows that stay are the ones that were
  already there. It also says when the curation set the entry was banked
  from still has doubles of its own, because re-banking from one that does
  would put them straight back.

---

## 2026.09.14.1 — Hello, and where the gaps actually are

### Added

- **The launcher says Jarvis.** Everything else was renamed months ago; the
  first thing the terminal printed was still BARRY GUI. It is now the name in
  block capitals, with a greeting that knows what time it is.

  Two things it has to survive. `Wake up Jarvis.bat` runs cmd.exe, which on an
  older machine is codepage 437 and cannot encode a single block character —
  so the wordmark is tested against the real console encoding first and a
  pure-ASCII one takes over when it will not fit. And ANSI colour works in
  Windows' console only once virtual-terminal processing is switched on, so it
  is switched on deliberately and dropped rather than printed as escape codes
  when that fails.

- **A bar showing where the gaps are.** Seven rows of record numbers said how
  much and how far and nothing about *where* — and where is the useful shape,
  because every gap on `M8s9feb8` falls inside 110 seconds of an otherwise
  clean 35-minute recording.

  Positions are to scale. Widths are not, and the panel says so: 122.5 ms in
  2124 s is a fifth of a pixel, so each marker has a floor width. Because four
  of the seven then share that pixel, a second bar draws just the stretch the
  gaps are in — and only when the gaps actually cluster, since on a recording
  where they are spread out it would be the same picture twice. Hovering a
  marker gives its size, its record, and the shift from there on.

- **The correction is explained, and offered.** The panel said correcting the
  times was "a separate, explicit step" and stopped, which reads like
  something nobody has built. It is built. The panel now says what it does —
  times move onto the recording's own clock, every label and id survives,
  nothing is re-detected, it lands as a new version with the old one kept, and
  kilosort units for the same session still need the same conversion — and
  offers a preview.

  The preview is the server's own dry run, so what it shows is what the write
  would do, produced by the code that would do it: how many events move, the
  shift per stretch, before and after for the first few, how many decisions
  are affected, and the events sitting within 125 ms of a stitch that may be
  filter ringing rather than real spikes. Applying is a second, deliberate
  button inside it, and nothing on the way there writes anything.

### Fixed

- **The gap heading could read "0 gap(s)" above a table of seven.** The count
  came from `n_gaps`, which the capped health summary carries and the full
  report does not — and the full report is exactly what `Check every channel`
  swaps in. It now counts whichever of the two actually arrived.

- **A check name was ellipsised** at 130 px, turning "mixed sample rates" into
  "mixed sample ra…". It wraps.

### Checks

- `web/_dev/continuity.html` — 45 checks now, including that the panel counts
  the gaps it was handed (fed the full report, which is the shape that was
  broken), that every gap is marked, that a marker sits where its timestamp
  says to within 0.05% of the bar's width, and that the correction box
  explains itself and offers a preview.
- `web/_dev/gapbar.html` — a shot-taker for the panel and the preview.

---

## 2026.09.11.1 — Gaps in the recording, and the scale on a dB panel

### Added

- **A re-timing action, behind a preview.** Once a recording is known to have
  gaps, the banked event set on it can be moved from Toothy's concatenated
  clock to the recording's own. Arithmetic on existing events: nothing is
  re-detected, the raw `.ncs` files are not touched, `DATA.hdf5` is not
  rewritten, and no gap is interpolated across — the samples were never
  recorded, and a gap is missing data rather than bad data.

  **Which way, and why.** To the Neuralynx clock, because Jarvis is a
  raw-backed application: its viewer, `.nvt` tracking, `.nev` marks and video
  are all on that clock. The cost is stated in the preview rather than left to
  be discovered — kilosort unit times for the same session are still in
  concatenated time and need the same conversion before unit/DS comparisons
  mean anything.

  **The basis is established, not assumed.** All seven affected sets say
  `pipeline: 'ETS dentate-spike export'`, and whether that is concat-era
  output is exactly the thing the plan says never to guess at. Measured
  instead: every one of the 1224 banked times for M8s9feb8 sits within 1.5 ms
  of a Toothy `ALL_DS` time, *including* the 314 after the first gap — which
  would be 96–122 ms away on any other clock. A set hand-curated against the
  raw viewer is recognised as already correct and refused; a pipeline nothing
  records is refused with a reason, because a correction applied on a guess
  introduces the error it is meant to remove.

  **Curation identity is the timestamp**, which is why this is not a loop
  adding 0.122 to every `start`. A candidate's identity in a set is its time
  at `MATCH_DP = 4` — 0.1 ms — and the correction is a thousand times that.
  Pushing re-timed events through `create()` would mint a fresh id for every
  one, orphan every decision, and on the next merge from a machine that had
  not re-timed produce two ids per time whose union is a set of twice the
  size, half of it undecided duplicates. That is what happened to m33 s8 on
  2026-09-08: 416 decisions became 832 candidates.

  So the edit is in place and keyed by event id; the per-event merge stamp is
  bumped, without which a colleague's untouched copy is newer and silently
  reverts the correction on the next sync; and every post-condition is
  asserted rather than assumed — ids preserved, count unchanged, order held,
  decisions intact, no tombstone written. `tools/test_retime.py` covers all of
  it, including a merge from an un-retimed machine, which is the failure that
  only appears after a sync.

  Never auto-applied. `/api/session/retime` previews by default and `apply`
  has to be asked for; running it twice refuses on the `time_basis` stamp,
  where absence means **unknown** rather than correct. Reversal is "restore the
  previous version", not a second arithmetic pass.

- **The session health report says whether a recording is continuous.**
  Cheetah closes a record early when acquisition hiccups, and the next
  record's timestamp jumps. neo and spikeinterface call that a segment break,
  so the file reaches Toothy as a multi-segment recording and Toothy
  concatenates it — which closes the gaps and relabels every sample after one
  with a time earlier than its true one, by the cumulative duration of all
  preceding gaps. The error is a step, constant inside each segment, and
  nothing downstream recorded that it happened.

  `M8_Pten\M8s9feb8` is 8 segments, 7 gaps, 0.1225 s never written, and
  121.9 ms of error by the end. A dentate spike is 10–20 ms wide, so seeking
  to a banked DS time in the raw file after 1762.5 s lands six to twelve event
  widths from the event. Before 1762.5 s the two agree exactly, which is why
  it passes a casual spot-check.

  The check is a faithful port of neo's `NcsSectionsFactory._buildNcsSections`
  — including spikeinterface's non-strict 4267 µs tolerance, so the
  segmentation reported is the one Toothy actually saw, not a stricter rule
  that would count clock jitter as a break and find thousands. Verified
  against spikeinterface's own answer on every affected recording in the PTEN
  archive: same segment counts, same gap tables, same figures to six decimal
  places.

  It runs on every health check rather than being a deep-check extra, because
  neo's fast path decides a continuous file from two records. Seventeen of
  the twenty-nine PTEN recordings take it and cost two seeks; the answer is
  cached against the reference file's size and mtime.

- **Details behind the continuity row** — the gap table, the segment map, and
  the three durations this recording can be said to have. Plain language in
  the row, numbers in the expansion, because "121.9 ms" is a claim and the gap
  table is the evidence for it. `Check every channel` parses all 64 rather
  than the four-channel spot-check, which is the answer to trust before acting
  on one.

- **`tools/scan_continuity.py`** — the same check across a whole tree, for
  "how much of the archive is affected" rather than "is this session all
  right". On D:\PTEN\PTEN: **7 of 29 recordings have gaps**, and the other
  22 are genuinely single-segment, which is the check discriminating rather
  than always firing.

- **`/api/session/continuity`** carries the full segment map. The health
  report holds a capped version — sixty segments and sixty gaps — so a
  sixty-session scan cannot return a hundred thousand rows.

### Fixed

- **Pinning the colour scale on a dB panel replaced the picture with a red
  rectangle.** Reported: "when you click on Auto to pin the theta power
  raster it breaks things, the colors look off."

  Three faults stacked. Only one of the five image panels ever reported
  `clim_auto`; the band-power raster, the spectrogram and the comodulogram
  never did, so the client fell back to the literal placeholder `[-1, 1]`.
  Band power in dB re 1 µV² runs about [-3, 27], so pinning clipped 30 dB of
  data into 2 dB and everything above 1 dB saturated at the top of jet.

  Underneath that, pinning rebuilt the range as `[-magnitude, +magnitude]`.
  Symmetry is right for voltage, CSD and theta — signed quantities where zero
  is the middle — and wrong for every one-sided scale: forcing [-3, 27] to
  [-27, 27] throws away most of the map whatever the placeholder does. Each
  panel now says what its auto limits are **and** whether its scale diverges,
  and pinning pins the picture that is on screen.

  And underneath *that*: the control strip is built when the pane appears and
  `fetchImagePanel` never rebuilt it, so the button closed over
  `auto === undefined` from before the first panel arrived and kept it for the
  life of the pane. It cannot simply rebuild on every fetch — that replaces
  the slider under a dragging pointer — so the button reads the live scale at
  the moment it is clicked, and the strip refreshes only when the text on it
  would change and no drag is settling.

  On a one-sided panel the slider now sets the dynamic range, anchored at the
  top, which is the only number on a dB axis anyone wants to move.

- **The event bank never reached Supabase.** The table existed with **0 rows**
  while this machine held 158 snapshots. Three faults, all from the morning
  the table was added:

  Each row's `updated_at` is the version's own creation time — deliberately,
  so a pushed snapshot is never re-sent — which also means every snapshot
  created before the feature shipped is older than `last_push` and was skipped
  permanently. The table is append-only and small, so it now asks the database
  which `(entry_id, v)` pairs exist and sends the difference. No clock
  involved, right on the first push and the thousandth.

  `collect()` never called the builder. It was written and wired into the push
  order and the conflict map, and the one line that gathers it was missing.

  And a foreign-key rejection aborted the **entire push**. `bank_snapshots`
  sits sixth in the order, so one snapshot whose entry had not landed yet
  returned `23503` and stopped `curation_sets`, `layer_sheets`, `results` and
  everything after it from being sent — which is why a v3 curated here never
  appeared anywhere else. The builder now sends only snapshots whose entry the
  database already has; the entry goes up from an earlier table in the same
  push and its snapshots follow a minute later. 130 snapshots up, and the
  later tables moving again.

- **The viewer was on a time basis of its own.** `read_ncs_range` seeked with
  `floor(t / block)`, which assumes every record is full and that no timestamp
  ever jumps. Measured on M8s9feb8: a window labelled t=2000 held data from
  1999.923 — **77 ms early** — and the axis was 70 ms wrong by the end of the
  file. Re-timing events while the viewer's own axis is wrong just moves the
  error around, so this went first.

  The seek is a binary search over the record timestamps now: seventeen
  twenty-byte reads find the right record in a file of any size, exactly, and
  on a continuous file it lands on precisely the record the arithmetic would
  have picked. A window that crosses a gap reports it rather than pretending
  to a uniform axis.

- **The reported duration was a third number again.** `session_health` gave
  `n_records × 512 / fs` — 2124.544 s on M8s9feb8, against 2124.3445 s
  concatenated and 2124.4661 s on the recording's own clock, and agreeing with
  neither the raw files nor anything Toothy produced. It is now the true
  duration, read from the first and last record, with the concatenated one
  beside it whenever the two differ. On a clean recording all three collapse
  to the same number, which is exactly why this went unnoticed.

- **Two counters were both called "gaps" and disagreed.** `read_ncs` counts
  inter-record intervals off by more than half a block — 9 on M8s9feb8, where
  neo sees 7 breaks. It also counts ordinary clock jitter, so it is now
  `irregular_intervals`, which is what it counts. "Gaps" means neo's rule,
  which is the one that decides whether Toothy sees one segment or eight.

- **"2309 samples went missing" was the wrong number and the wrong idea.** A
  synthetic test caught it: a record closed early at 200 of 512 samples, with
  the next timestamp following 200 samples later, lost nothing — and the check
  announced 312 missing samples. `n_records × 512 − samples` counts unused
  buffer slots, not loss.

  Nor is the obvious alternative any better: summing every sub-tolerance
  residual gives 290 ms on M8s9feb8 and 299 ms on a recording with **no gaps
  at all**, because `int(1e6 / fs × nvalid)` truncates and a microsecond per
  record over 124,485 records is 124 ms of pure arithmetic. Measured: the
  median residual on a full record is exactly 1 µs.

  What is measurable is the residual at the records Cheetah actually closed
  early. M8s9feb8 loses 7.6 ms that way; a clean recording with three short
  records loses 2.9 ms. Across the archive that is 2 of 22 clean recordings
  rather than all 22.

- **A check name was truncated.** `.check-name` ellipsised at 130 px, turning
  "mixed sample rates" into "mixed sample ra…" — hiding the word that matters.
  It wraps now.

### Checks

- `tools/test_continuity.py` — the segmentation against files it writes
  itself, so the right answer is known before the code runs: a continuous
  file, a 50 ms gap, a 2 ms hiccup below the tolerance, short records with and
  without lost time, a slow clock that must not read as loss, and a channel
  that disagrees with the others.
- `web/_dev/continuity.html` — 23 checks against the real recording, including
  that a clean session does **not** get the warning.
- `tools/test_retime.py` — 37 checks on the re-timing: a preview that
  writes nothing, an apply that keeps every id and decision, a second run
  that refuses, and a merge from an un-retimed machine that neither reverts
  the times nor doubles the candidate list.
- `web/_dev/climpin.html` — 11 checks that pinning a dB panel keeps the
  picture and that pinning a signed one is still symmetric. It reproduced the
  reported bug before the fix and fails again if either half is reverted.

---

## 2026.09.10.1 — Braid, and the name on the door

### Fixed

- **A profile set on one computer became everybody's.** Reported, and worse
  than it looked. `Profile` and `Device` both say they are per-machine, and
  both are half right: each machine WRITES its own shard, and both were
  READING `book.read()`, which merges every machine's shard field by field,
  last write wins. So the moment another computer typed a name, its name was
  newer than yours and won everywhere — and the computer's nickname went the
  same way.

  Attribution comes from that record, so this was not a display quirk: it
  credited work to whoever had most recently typed a name somewhere else.
  And because a save read the merged record before writing it back, the
  mixture got persisted — this machine's own file now holds one person's
  name with another's email, written two days apart.

  Both now read `read_mine`, which is this machine's shard and nothing else.
  A machine that has never set a profile reads as unset rather than as
  somebody else, which is the correct answer and the point: it will ask,
  once, instead of quietly crediting the wrong person.

- **The feed was not live, and the timestamps were fine.** Measured against
  the clock, the newest rows were genuinely 21 minutes old and correctly in
  UTC. Three delays were stacking: the client queues actions for four
  seconds, the push reaches Supabase on the sync cycle, and the feed polled
  every nine. Since it read only the shared table, your own work was
  invisible until a push happened.

  `activity.log` now notifies listeners the moment an action is logged —
  before the queue, before any request — so your own actions appear with no
  latency at all, marked "not shared yet" until the push carries them. The
  feed endpoint merges this machine's log with the shared table so a reload
  agrees with what the live append showed, and the poll is three seconds for
  everybody else's work.

- **A feed could go quiet while you were working.** It asked for rows newer
  than the newest one it held — and that stamp comes from whichever machine
  wrote it. The eleven machines in these logs do not share a clock, so one
  running a minute ahead put the watermark a minute into the future and
  every row this computer wrote until then was "older than since" and never
  arrived. The watermark is set back two minutes and duplicates are dropped
  by id.

- **Braid had no way out.** DS curation and StrataScope both end their bar
  with `Leave`; Braid had nothing, so a mode that takes over the panes, the
  keyboard and a second window gave no way to hand them back. Same button,
  same place, and `cfcbar.html` now checks for it.

- **"Draw at full rate" did nothing on a raster.** Reported, and the server
  proved it: at full rate a raster went from 1800 columns to 20000 and
  stayed averaged, so the picture was identical. A picture is as wide as the
  pane it is drawn in. That step is marked not-reversible now, the cap is no
  longer raised, and the panel states the limit — one column is 33 ms — with
  no switch offered, because a switch that cannot move is worse than none.

- **There was no way back from full rate.** The badge became a `<span>` once
  full rate was on, so the one thing it had to be able to say — "and here is
  how to undo me" — it could not. It is a button in both states.

- **A full-rate render now says what the wait is for.** "Every sample at
  30 kHz · exact filters, no shortcut · 64 channels", instead of "reading
  channels" whatever was being asked.

- **The rasters were downsampling without saying so.** Reported from the
  application: the badge showed on the voltage traces and not on the voltage
  raster or the CSD. True, and my omission — the recorder was wired into
  band power's call and not into the other two, so the panels people spend
  the most time in were the two that said nothing. A CSD of a 60 s window is
  1.8 M samples averaged into 1800 columns, which is **33 ms a column** when
  a dentate spike is a few milliseconds wide. It says that now, and offers
  to raise the cap.

- **The DOWNSAMPLED badge could not be clicked.** It lives in the caption
  strip over the plot, and that strip is `pointer-events: none` — so the
  answer to "how do I turn this off" was that you could not. Three faults in
  one small element, all mine: the strip swallowed the click, `nowrap` +
  `overflow: hidden` clipped the badge off the end of a long line, and the
  detail panel was appended *inside* that one-line strip, where it could
  never be seen. The text is now the part that ellipsises, the badge is the
  part that survives, and the panel opens in the caption's own frame.

- **Sixty-four channel labels sat on top of each other.** The lane is a
  fixed 18 px, or 12 px when compact. The grid slot it sits in is the plot
  height over the channel count — 7.8 px for 64 channels in a 500 px pane —
  so every lane overlapped its neighbours by two pixels top and bottom, and
  the gutter read as a grey smear. The height and font now follow the
  measured pitch, and below about 10 px the names thin out one row in `n`
  while every row keeps its controls, which is the stride a crowded axis
  already gets in `compose.py`.

  `chan64.html` checks that all sixty-four lanes have a hittable
  bad-channel button and never checked that two lanes were in the same
  place, which is why the suite was quiet about it. `downsampled.html` now
  measures it: no lane may overlap the next, and the caption may not
  intersect any of them. It reports 64 lanes at a 10 px pitch with 10 px
  height, and a caption starting 4 px clear of the widest label.

- **The caption ran into the channel labels.** It sat at `left: 0`, and so
  do the labels. The indent is measured now rather than guessed — the widest
  DOM lane on a trace pane, and the widest label the grid canvas actually
  drew on a raster, since those are painted rather than built. A pane
  showing `CSC28-CSC29` gets a wider indent than one showing `CSC2`. Its
  backdrop is opaque too: at 9 px over a trace, a translucent wash mixes the
  text with the signal and the line reads as neither.

- **The leftover-clearing added yesterday broke `bank.html`'s own count.**
  It clears the entries earlier runs left behind, and that clearing landed
  between the point where the harness counted the bank and the point where it
  compared — so every leftover deleted counted against the entry about to
  be banked, and the check read "77 -> 74". Counted from where banking
  actually starts now, and it passes three runs back to back, which is the
  case that broke it.

- **The comodulogram window snapped to a voltage trace a moment after it
  opened.** It is opened as `/?role=comod#comod` and names no recording,
  because it reads the window and the channel from its opener. The boot-time
  "reopen what was last open" guard says it skips a window "launched with its
  own target (a pop-out, or a deep link)" — but it tested only for
  `?csc=`, which pane pop-outs pass and this one cannot. So it fell through:
  the window drew its form, and 250 ms later `restoreLast()` reopened the
  last recording and finished with `setView('xplore')`. The three toasts were
  the only clue — "Reopening…", "view restored", "Loaded 2 events from
  Events.nev". The guard now excludes any window carrying a `role`, which is
  what "a pop-out" means here; every pop-out sets one.

- **The Comodulogram button spent its first seconds under a stack of
  toasts.** `cfcscope.js` removed the `--bottom-bar` variable on exit and
  never set it, so nothing reserved the height its bar occupies — and
  toasts are pinned bottom-right above exactly that spot, three of them on
  entering the mode. StrataScope sets the same variable and says why:
  "without this one covers Export CSV whenever anything is saved."

- **A typo in a band field asked the server for 60 GiB.** `0.05` typed where
  `5` was meant is a 180000-tap filter, and `firls` designs one by solving a
  least-squares system the size of the order — reported to the browser as
  numpy's complaint about an array shape. There is now a 1 GiB design budget
  in `cfc.eegfilt_taps`, so it covers the comodulogram as well as the panel,
  and it refuses in a sentence naming the number to change. A 4 Hz band
  (2250 taps) and 1 Hz delta (9000) design exactly as before.

- **`badsync` was measuring the opposite of what it says.** It assumed the
  channel it tests starts unmarked, so once a mark was left behind its first
  click cleared instead of marked and all five of its remaining checks
  reported backwards — which is how a harness passes five runs and then
  reports five failures pointing at the wrong thing. It now clears the
  channel first if it finds it marked, and says so. Its checks also asked
  whether the joined list "1,4,14" *contains* "4", which is true of 14 and
  40.

### Added

- **Archived computers stop filling the error feed.** Archiving a machine
  already existed and took it off the device pickers and nothing else, so
  eleven machines' faults — three of them retired — were still in the list.
  Matched on the id rather than the friendly name, because this lab has four
  names in its logs for three computers. Hidden, not dropped: the count is
  on screen with a way to show them, since "no errors from the rig" and "the
  rig is archived" read the same and mean opposite things.

- **Export open errors.** One text file of every unresolved fault with the
  activity either side of each occurrence, on one clock — because a
  traceback says what broke and the twelve actions before it say why. For
  working through a dozen at once, or for handing to somebody else. Bounded
  at sixty groups, three occurrences each, twelve actions either side: past
  that it stops being readable.

- **Every tool has a live activity feed, read from Supabase.** Each mode
  already wrote to the activity log and those rows already went up. What was
  missing was anybody being able to read them back **per tool**, so "is
  somebody else curating this?", "what did that import actually do?" and
  "why does this look different from yesterday?" were questions you answered
  by asking a person.

  It is for reproducibility first and debugging second. The feed is the
  record of what was done to a recording, by whom, on which machine, in what
  order — including the actions from the *other* machine that this one only
  learned about through the sync, which are exactly the ones nobody can
  reconstruct from memory.

  It is under all six tools: bad channels, event curation, StrataScope,
  Braid, Kilosort and Import sorted snapshots. **And under any tool added
  later, with no registration step**, twice over: a tool id the server has
  never heard of falls back to its own name as the action prefix, and the
  ToolKit mounts the feed by watching the panel host rather than by each
  tool remembering to ask. `toolfeed.TOOLS` exists only for the tools whose
  actions are not named after them — curation also writes `bank.*`, Kilosort
  writes `phy.*`, and bad channels were `channels.*` long before there was a
  page for them.

  The header says **which source it is reading**, because "nobody else is
  working on this" and "I could not reach the shared table" look identical
  on screen and are not the same fact. Polling asks only for what is newer
  than the newest row it holds, so a feed left open all afternoon costs
  twenty rows and then nothing.

- **Banked versions travel through Supabase, snapshots and all.** Migration
  11 sent the version history up without them and said why: 110 versions are
  44 kB of metadata and 0.5 MB with their snapshots. So a colleague's v7 was
  *visible* and not restorable — you could see who made it and how many
  events it held, and you needed a git pull to have it.

  `bank_snapshots` (migration **14**) closes that, and the shape is what
  makes it safe: keyed `(entry_id, v)`, append-only. A version's snapshot is
  written once and never changes, so two machines writing the same key write
  the same bytes — there is no last-writer, no clock to compare, and none of
  the timestamp-comparison class of bug that has been wrong in eleven places
  in this codebase. `updated_at` is the version's own creation time, so the
  incremental push sends each snapshot exactly once and then stops forever.

  Nothing replaces the JSON shard. It is still written and still travels
  with the repository, so a snapshot now has two independent copies instead
  of one. `absorb_snapshot` only ever FILLS one in: if this machine already
  has that version, the two are compared by a digest over a canonical form,
  and a disagreement is **reported rather than resolved** — there is no
  correct side to pick, and a version that disagrees with itself is a fault
  to look at. Conflicts ride out with the sync result.

  `tools/test_banksnap.py` proves it in seventeen checks, including that a
  machine's own work survives a pull, that a payload whose digest does not
  match its content is refused, and that float noise (315.275 against
  315.27500000000003) is one snapshot rather than two.

  **Run `supabase/14_bank_snapshots.sql` before expecting it to work.**

- **The comodulogram's parameters are editable again.** Tort's grid is still
  what it opens with and still says where it comes from; `Edit…` reveals the
  eight fields. Once the grid is no longer Tort's the form says so plainly,
  because the whole reason to default to the reference is that a map on it
  is comparable with a map from the paper. One click puts it back.

- **Every panel now says DOWNSAMPLED when it is, and offers not to be.** A
  panel that ran on every tenth sample cannot be told from one that ran on
  all of them by looking at it, and the difference decides what the picture
  is allowed to mean. So each one states what it did, in the line that
  already says what it ran on:

  ```
  ran on  01:40-02:40 (60 s) · 1 ch · >3 Hz +60Hz notch   [DOWNSAMPLED]
  ```

  Clicking it says exactly what happened — 30 kHz → 3 kHz, ÷10,
  anti-aliased, nothing above 1.5 kHz in the answer; or 1,800,000 samples
  drawn as 1,400 min/max columns, extremes exact and shape inside a column
  not — and offers **Draw at full rate**, per pane.

  The badge is red for a step that is **not** anti-aliased, which is a
  different claim and must not look like the same one. Only the scalogram
  does that: it takes a plain stride over 200 000 samples, so energy between
  1.5 and 15 kHz folds into the picture. It now says so in those words.

  Full rate is refused rather than attempted when it would be absurd, with
  the number and the window that would fit: "Every sample of 60 s at 30 kHz
  is 1,800,000 points per channel, past the 400,000 this will send without
  an envelope. About 13 s would fit." Which surfaced something worth
  knowing — **band power cannot run at full rate at 30 kHz at all**, because
  eegfilt's order scales with the sample rate and designing a 4 Hz filter
  there means a 22500-tap least-squares system. The decimation is not an
  optimisation; it is what makes the analysis possible.

  The spectrogram correctly wears no badge: it runs on every sample.

- **An explainer behind the bandwidth line, opened by the (i) beside it.**
  The band-power panel prints "Really 1.14–3.42 Hz wide, not 0.5. The bands
  overlap — this is a smooth read of where the rhythm sits, not 17
  separate measurements." The line is true and short, and short is what makes
  it repeatable — but it is a fact about filter length that takes a chapter
  to earn, and anyone meeting it for the first time had nowhere to go. There
  is now an (i) in that sentence, and it opens the chapter.

  Twelve chapters, from "a recording is a voltage over time" to "what not to
  claim": frequency, filtering, amplitude and phase, band-resolved theta, the
  bandwidth and what overlap costs, coupling, the modulation index, the
  comodulogram, surrogates, the controls mapped one by one, and the ways the
  arithmetic produces a number that means nothing.

  Nothing in it is a picture. One synthetic recording is built from sliders at
  the top and carried through every chapter — spectrum, filter, envelope,
  phase, band raster, comodulogram, surrogate histogram — so moving the
  coupling slider in chapter 7 changes chapter 9's map for the same reason it
  changes a real one. The comodulogram there is 195 live modulation indices,
  recomputed as you drag. A guide made of screenshots cannot be interrogated.

  Chapter 6 is where the (i) lands. It draws every row of the panel as the
  width it actually covers, and prints what the overlap costs: at three
  cycles the seventeen rows carry about 3.5 independent numbers. Drag the
  filter length to 24 and the bands narrow to 0.17–0.50 Hz and all seventeen
  rows become independent — and the filter now holds six seconds of
  recording, so chapter 5's drifting rhythm loses its slope. That trade is
  the whole reason the line exists.

- **CFCScope, in the Toolkit.** A third mode beside DS curation and
  StrataScope, and the first that decides nothing: it opens a recording in
  Xplorefinder, puts band-resolved theta power in a second window, and
  puts a comodulogram of the window on screen one keystroke away. No sets,
  no bench, no decisions — the banner says so and `web/_dev/cfc.html`
  checks it, by reading the activity log for writes after entering and
  leaving.

  The MATLAB beta run in `Reviving CFC/Revival Pipeline` answers "does this
  channel have phase–amplitude coupling", offline, in minutes. What it
  cannot answer is "does *this* window", which is the question somebody
  scrolling has. The arithmetic here is a copy of that pipeline's own
  Python port (`05_explainer/cfc_core.py`), and `tools/cfc_check.py`
  re-runs the explainer's assertions against the copy so it cannot drift:
  the modulation index matches `ModIndex_v2.m` to 1e-12.

- **A theta power panel that says which theta.** The existing `theta` panel
  bandpasses 4–12 Hz in one go, which answers how much and cannot answer
  which. This one is seventeen narrow bands in 0.5 Hz steps, each the mean
  squared envelope of its own analytic signal — the `ThetaPower.m`
  definition, from the same filter bank the coupling measure uses, so the
  two panels can never be quietly talking about different bands. A marginal
  curve down the right names the loudest band in the window.

  It also prints the thing a band axis never admits: `eegfilt` sets its
  order from the *lower* cutoff, so a band comes out about 0.30 × that
  wide however narrow you asked. The 0.5 Hz theta bands are really
  1.1–3.4 Hz and they overlap; a nominal 10 Hz band at 200 Hz is nearly
  60 Hz of spectrum. Measured from the filter's own frequency response and
  shown in the panel, because seventeen overlapping rows presented as
  seventeen measurements is the trap this panel was built to avoid.

- **A comodulogram you can afford to ask for.** Its own window, so two maps
  can be compared, which is most of what one is for. Measured on this
  machine, a 60 s window over the `params.m` grid: 3.3 s for the filter
  banks, 0.3 s for the 629 modulation indices, and 16 s or 32 s more for 50
  or 100 surrogates. So the null is off by default and the form says what
  turning it on will cost before you commit.

  It reports the permutation p, not z. The beta measured the surrogate null
  to be centred but over-dispersed — SD 1.4, and it does not shrink as
  surrogates are added — so a nominal |z| > 3 behaves like 2.2. The map
  outlines cells at p ≤ 0.05 and says how many chance alone would have
  given, because "31 cells significant" means nothing until you know that
  31 is what an empty map looks like.

- **A loading display that is not a spinner.** Seven named stages, each
  counting in its own unit — bands, cells, surrogates — with the overall
  bar weighted by what each stage actually costs rather than by stage
  count. On a 100-surrogate run the surrogates are seven eighths of the
  work, so seven equal steps would sit at 71% with nearly everything left
  to do. The estimate waits until it has three ticks to estimate from, and
  the per-stage rates are remembered per machine, so the second run's
  estimate is right on the rig as well as on a laptop. Cancel lands in
  0.11 s, measured.

### Changed

- **Jarvis, not Javits.** I misheard the name. Mechanical this time and
  safe in a way the last rename was not: "Javits" was nowhere an identifier,
  a folder, or a string written into anybody's data, so a straight
  replacement was correct everywhere it appeared — which is exactly what was
  not true of the name before it.

- **The rail badge wears the mark.** It was a gradient square with a `B` in
  it: the wrong initial, and a letter in a box is what an application uses
  when it has no mark. It has one, so it uses it — inline, taking its two
  colours from the live theme, so the badge in the rail and the icon in the
  tab are the same mark in the same light rather than one being a picture of
  the other.

- **The application is called Jarvis.** The launchers are **Wake up
  Jarvis** (`.bat` and `.command`), moved with `git mv` so their history
  follows them, and everything that names them was updated in the same pass
  — the README, `setup.py`'s closing line, `start.py`'s docstring, and the
  mac script's own chmod hint.

  Four things deliberately keep the old name, because they are not the
  product's name:

  - `const BARRY` and its 1713 references. That is an address, not a name.
  - `pipeline: 'BARRY threshold detector'`, which is **written into banked
    entries as provenance**. Renaming it would give one detector two names
    and make last week's entries disagree with today's about which tool made
    them. Provenance is history.
  - `"BARRY GUI"` in `registry.py`'s skip list — a **folder name**, and the
    string by which a drive scan knows not to descend into the application's
    own directory.
  - the folder itself, and every path containing it.

  Renaming the first of those was how I broke eighteen harnesses on the way
  here: they reach the global by name, as a string — `ev('BARRY')` — and a
  regex cannot tell a name from an address. The application booted fine
  throughout; the tests were asking for a global that no longer existed.

- **CFCScope is now Braid.** Phase-amplitude coupling is two rhythms
  plaited together, and "CFCScope" was an acronym wearing a telescope. The
  module, the file and the `BARRY.cfc` handle keep their names for the same
  reason as above.

- **A new mark.** The old favicon was a five-spike train in a rounded
  square, which said "oscilloscope" rather than anything about this
  application. The new one is a single continuous stroke: flat, a sharp
  spike up, down through the baseline, and the descent becomes the stem of a
  J. So it reads as a dentate spike at 256 px and as an initial at 16.

  `tools/make_icons.py` renders that same SVG in the browser and packs six
  sizes into `web/img/jarvis.ico`, so the tab, the shortcut and the dock
  cannot drift apart. A `.bat` cannot carry an icon, so there is a
  **`Wake up Jarvis.lnk`** beside it that can.

- **Samples are anti-aliased before the filter bank.** `read_csc.m`
  decimates with `Samples(1:10:end)` and no low-pass, so content above the
  new Nyquist folds into the 20–200 Hz amplitude axis — a caveat the beta's
  README flags as a real risk needing a decision. CFCScope uses
  `scipy.signal.decimate`, which filters first. Its numbers are therefore
  better than the legacy pipeline's and **not** bit-comparable with
  `newFCSE` output; every panel and every caption says which was used.

- **A sequential colormap, offered and defaulted to for coupling maps.**
  `jet` remains the default everywhere else, because it is what the
  existing figures use. It is the wrong choice for a comodulogram
  specifically: `fig11_colour_lies.py` in the explainer shows the same
  no-coupling recording three ways, and a rainbow autoscaled to its own
  range invents a story the numbers do not support. The map always prints
  its own maximum, and Lock scale holds the scale across every map in the
  window so two of them can actually be compared.

---

## 2026.09.09.2 — one probe, one panel

### Fixed

- **`conflict_check` called four conflict-proof files conflicts.** The tool
  that proves no file in `GUI_logs` can produce a git conflict flagged the
  feedback triage overlays — and the reason those exist is the very rule it
  enforces: triaging a report somebody else filed used to edit *their*
  shard, so it writes `<id>~<this machine>.json` instead. The machine name
  is in the name, just after `~` rather than `@`, because an overlay must
  not be read as a shard of the base report. The tool tested the spelling,
  not the rule. A feedback screenshot was flagged too; it is an attachment,
  written once by the machine that filed the report.

  `test_twomachines.py` had its own copy of the classification, which is
  exactly why the two drifted apart — it now asks `conflict_check.classify`,
  so there is one answer to “can this file conflict”. The sigil is a named
  constant in `feedback.py` instead of a `"~"` in two files that have to
  agree. All four `tools/test_*.py` pass, and the check reports 1259
  per-machine files and nothing shared.


- **A bad channel you had cleared came back by itself.** Bad channels travel
  between windows on their own “facts” channel, which is published whatever
  the link mode — a channel is broken or it is not, and that does not depend
  on whether the second window happens to be following the first. But the
  time/view channel carried the list as well, and that one is only published
  while the windows are linked:

  ```
  mark CSC4 bad while linked   ->  facts: [4]   time: [4]
  unlink, or close the other window
  clear CSC4                   ->  facts: []    time: [4]   <- stranded
  any window applies that view update -> CSC4 is bad again
  ```

  Measured on this machine, with the store and the facts channel both
  clear, the view channel still said `bad: [4]` — so every window that
  opened that recording came up with CSC4 marked, and the next save wrote
  it back to the store. That is how a mark somebody had deliberately
  cleared returns, and it is the reason `badsync` kept finding a leftover
  mark before every run however cleanly the previous one had finished.

  The view channel no longer carries a bad list or applies one. A view
  update can be minutes old and says nothing about whether a channel is
  broken. There is a harness for it (`badstale.html`) that marks a channel,
  clears it, then publishes exactly the stale view update the old code
  left behind — it fails on the old code and passes on the new.

- **`badsync` was measuring the opposite of what it says.** It assumed the
  channel it tests starts unmarked, so once a mark was left behind its first
  click cleared instead of marked and all five of its remaining checks
  reported backwards. It now clears the channel first if it finds it marked,
  and says so. Its checks also asked whether the joined list “1,4,14”
  *contains* “4”, which is true of 14 and 40 — a recording with CSC14
  marked would have passed the whole harness without CSC4 being touched.
  Membership is now asked of the set.


- **Five lists were ordered by comparing timestamps as text.** Having fixed
  six comparisons, I went through every remaining one in the application.
  What was left was ordering — the deck list and the report list “newest
  first”, the notes on a report oldest first, the curation shelf's “recent”
  order — plus one more decision, in the fold of the old shared sidecar
  file, which kept the older copy of a result's curation whenever the two
  stamps were written in different offsets.

  Every one of those lists holds both offsets at once, so “newest first”
  could put a row from 20:41 local below one from 00:37 UTC that is four
  minutes older. Eleven places in one day, from one habit.

  There is now a `tools/test_times.py` that covers the comparison, the sort
  key and the feedback merge — fifteen checks. Two of them fail if the
  string comparisons are put back, which is the only reason to trust the
  other thirteen.


- **Feedback could show the wrong state, and the wrong copy of a report.**
  Having found the same fault four times, I went looking for the rest of it.
  Six more comparisons of a timestamp as text: four in feedback and two in
  the activity fold.

  Feedback decided three things this way — which machine's copy of a report
  is the original, which overlay holds the newest state, and whether an
  incoming state is newer than the one held here. A report acknowledged on
  one machine this evening could lose to one marked on another this
  afternoon, because the second stamp read as larger. All three now compare
  moments.

- **“Last active” could name a time that was not the latest one.** The
  per-person, per-machine and per-session folds keep the most recent stamp
  by taking a maximum over text. Activity written here carries this
  machine's offset and activity pulled from the shared table is UTC, so the
  maximum was over two different scales and the answer could be an older
  row.


- **An error you had just resolved stayed red.** Whether an error counts as
  handled was a string comparison of when it happened against when somebody
  marked it:

  ```
  error at 2026-09-10T00:37:57+00:00    (UTC, from the shared table)
  mark  at 2026-09-09T20:40:45-04:00    (local, written here)
  ```

  The same afternoon — the mark is three minutes *after* the error — but as
  text “2026-09-10” sorts after “2026-09-09”, so the error read as newer
  than the mark that resolved it, and stayed unresolved however many times
  it was resolved. The “came back since” count beside it had the same test.

  This is the fourth place today the same fault has turned up: the
  incremental push dropping every edit made during a working day, the error
  triage letting an older remote mark overwrite a newer local one, the
  curation decisions, and this. Comparing two timestamps as text is only
  right while they share an offset, and in this application they do not —
  anything that came down from Supabase is UTC and anything written here
  carries this machine's.

- **The error-context panel could put the failure in the wrong place.** The
  panel lists what was happening either side of an error, and marks the
  error's own position in the sequence — decided by the same string test, so
  with a UTC row beside a local one the marker could land at the top of a
  list it belongs in the middle of. Showing which side of the failure each
  action is on is the only thing that list is for.


- **A channel could not be marked bad on any raster pane.** The side channel
  rail carried two things — which channels are drawn, and a bad/ok toggle on
  each — and when it was collapsed into the pane's `Ch` menu, only the first
  came across. On a traces pane the lanes on the plot still have their own
  toggle; on voltage, CSD and theta there are no lanes, so there was no way
  to mark a channel bad at all — and a raster is exactly where a dead
  channel is obvious. The toggle is back, in the menu the selection now
  lives in.

  Sixty lines of the removed rail were still in the file, unreachable, which
  is why a harness went on looking for its markup and reporting the absence
  as a fault.

- **Every figure rebuild was restoring into a session nobody was looking
  at.** `figrebuild` binds the session once, at its open step, and the
  recording can be re-opened after that — so every later step wrote to an
  object no longer in `XF.sessions`, and the “Check it matches the recipe”
  step confirmed a state that was not on screen. Which is worse than not
  checking: it reports success about the wrong thing.

  Measured: the steps reported “6 of 32 channels selected; CSC 8 marked
  bad” and “2 marks put back”, and the recording on screen had all 32
  channels, no bad channels and the file's own 12 marks. The check now takes
  the session that is actually active, repairs that one, and restores the
  window and the filters too when the two had diverged.


- **Two recordings with the same mouse and session numbers could become
  one, on a scan.** `ids.match` returned a “strong” match on `loose_key` —
  mouse plus session — whenever exactly one stored record had it, with no
  check on when either was recorded. `upsert_session` then patched *that*
  record and appended the new path to it.

  In this lab the numbering restarts per project, so PTEN m1 s1 and KCNT1
  m1 s1 are one loose key and two recordings. Found the hard way: a scan
  fixture with folders named m1s1, m1s2 and m2s1 — the most ordinary
  numbering there is — took over three real records within minutes,

  ```
  m001_s001_2026-01-02  ->  m001_s001_2023-10-02_16-49-04
  m001_s002_2026-01-02  ->  m001_s002_2023-10-02_16-58-03
  m002_s001_2026-01-03  ->  m002_s001_2024-01-23_14-48-16
  ```

  and rewrote their paths to the fixture's folders. (Those three records
  were restored from git, un-tombstoned and verified by key; the fixture
  now takes its mouse numbers and dates from the clock.)

  A loose match has to agree about *when* now, within six hours — enough
  slack for one side having read the start from a Neuralynx header and the
  other from a folder name, nowhere near enough for years. A folder whose
  name says mouse and session but not when still matches, because that is
  the case this tier exists for and refusing it would lose the match that
  makes bad channels follow a recording between machines.

- **Sixty lines of a channel rail that was removed on purpose.** The side
  column of channel rows down every raster pane went when the selection was
  consolidated into one control — it moved and changed shape depending on
  the panel. `paneChannels()` stayed behind, unreachable, for long enough
  that `chan64.html` went on looking for its markup and reporting the
  absence as a fault. Both are dealt with: the function is gone and the
  harness checks the `Ch` menu that replaced it.


- **A rebuilt figure quietly reverted to the recording's current state.**
  Every step of the rebuild reported success — “Restore the channel
  selection: 6 selected, 1 marked bad”, “Put the event marks back: 2 marks”
  — and the figure came back with the recording's channels, no bad channels
  and its own twelve marks. Watched half a second at a time:

  ```
  t+0.0s  sel 6,  bad [8], 2 marks,  src "figure rebuild"   <- the rebuild
  t+0.5s  sel 6,  bad [8], 12 marks, src "nev"              <- an import lands
  t+1.0s  no session                                        <- closed
  t+1.5s  sel 32, bad [],  12 marks, src "nev"              <- reopened
  ```

  Two stale writes, both landing after the work they overwrote.
  `autoImportNev` asked “does this recording have events yet” *before* its
  round trip and assigned when it came back, so anything that put events
  there while it waited was replaced — a rebuild's marks, an import, a
  detector's output. It asks again after the wait now, which is where the
  question had to be.

  And the session can be closed and reopened a second later, which resets
  the selection and the bad channels to the file's own. So the plan ends
  with a step that reads back what it restored, puts back whatever moved,
  and says which fields it had to put back. A rebuild is a provenance
  feature: “the figure you exported, drawn again” is either true or the
  feature is decoration, and the only way to know is to look.

- **Forgetting a recording is permanent, and two places promised otherwise.**
  The Forget dialog and the route's own docstring both said “opening or
  scanning it again starts a fresh record”. It does not: forget erases the
  record and writes a tombstone keyed on its permanent id, so a colleague's
  registry cannot push it back and the next scan does not re-register it.
  The scan finds the folder, reports it catalogued, and nothing appears.

  That behaviour is right — a scratch copy that creeps back on every scan
  has not been forgotten — so the words changed rather than the code.
  Bringing one back is a deliberate act, not something a scan does for you.


- **The ToolKit jumped between modules on its own.** Reported with a request
  log, which is what made it findable: `/api/registry` at 8.5-9.3 s four
  times in thirty seconds, `/api/layers` at 4.2-4.6 s, `/api/presence` every
  ten. Three causes.

  *A slow answer landing after you had clicked elsewhere.* The bad-channel
  loader has guarded against this all along and its comment says why —
  “rendering its answer then replaces the pane you just opened — which is
  the ‘it snaps back to another tool’” — but the guard was never applied
  to the two slow tools. Click StrataScope while Curation is still loading
  and Curation painted over it. The renders now refuse to paint a tool that
  is not the one on screen, in one place rather than at each call site.

  *The presence poll repainted Curation every ten seconds*, whatever you
  were looking at, for as long as the ToolKit was open. A jump to another
  module with nothing you did to explain it.

  *And the speed, which is what made the races easy to hit.* Profiled: the
  session records were read and merged three times per request — once
  directly, once inside `projects()`, once inside `tree()` — and the
  attachment counts read the figure catalogue and the deck list **once per
  recording**, five hundred times over, for 6,060 directory listings in one
  request. It was O(n²) in recordings, which is why it got worse as the lab
  collected data rather than being slow from the start.

  Records are cached against the shard directory's signature (a write, by
  this machine or by a pull, invalidates it — the index `by_gid` has used
  for the same reason), and the attachment counts are indexed once per view
  with the answers verified identical on every row. Measured: registry
  **8.5 s → 4.5 cold, 2.0 warm**, layers 4.6 → 2.5, curation 3.9 → 1.7, and
  four tool switches now cost at most one registry read instead of four.

  Two harnesses that had been crashing — `bankback` and `strip2` — pass
  again: they were timing out on those reads, not broken.

- **A spectrogram in a figure was one channel of the one on screen.** The
  builder offered a single `Channel` dropdown while the viewer has had
  multi-channel time-frequency panels for a while, and the seeding dropped
  the channel list, the mode, the analysed band, the display crop and the
  STFT variant. The filters and the window came through because they live
  on the layout, which is exactly why this looked half-right.

  It seeds from `panelSpec` now — the request the pane itself sends, which
  the prewarmer already mirrors so the server's cache key matches. Emulating
  what is on screen rather than re-deriving the same fields a second way is
  what stops a figure drifting from the screen it was made from.


- **A session record with no permanent id, and the hole that made it.** The
  housekeeping check said “every one has a gid: 1 without”, and it was:
  `Y:\ProcessedPtenData\PTEN_CFCs\VACC\CFC\Other`, created 2026-09-04 on
  BarryLab, no gid, no key, no channels.

  A record with no id cannot be reached by anything — every by-gid route
  answers 404, nothing can be attached to it, and it files itself under the
  shared `unknown` shard whose own comment records having eaten three real
  recordings. Two layers disagreed about whose job the id was:
  `Registry.ensure` and `_durable_patch` both mint one, but
  `Store.upsert_session` would *create* a record without one — and three
  routes write through the store directly (a note, a bad-channel list, a
  saved view state). Add a note to a folder that is not a recording and you
  get exactly this.

  The id is minted at the choke point now, which also makes the `unknown`
  filename unreachable. The existing row was repaired rather than deleted
  — given an id and a note saying where the id came from — so it can be
  corrected or forgotten like any other record. 515 records before and
  after, none without an id.

- **The built-in example offered four controls that could not work.** The
  demo project is in the tree so that a machine with nothing mounted is not
  an empty application, but a demo recording is deliberately not a registry
  record — so filing it under a project, annotating it, merging it and
  splitting it all answer “No session demo-ds-tutorial”. Housekeeping
  offered all four anyway, and a new user’s first click in Everything
  BARRY knows is quite likely to be the example. It now says what it is,
  and the writes are not offered. Everything that reads — the id, the
  paths, the links to what is attached — stays, because that is the point
  of having an example.

- **The figure footer ran off the page on the journal-column preset.** Two
  causes. `_ranges` collapsed only *consecutive* runs, so every-other-
  channel — which is what “even only” gives you — printed as thirty-two
  numbers and was cut by the paper edge; it says `CSC 1-63/2` now, the same
  rule the grid cells and the column heads use. And the packer laid whole
  phrases onto lines and never split one, so a phrase longer than the line
  overflowed; it wraps at its own separators instead. Nothing is cut,
  because a provenance strip that is approximate is worse than none.

  The layout also reserved three lines for it and a 3.5in page needs five,
  fitting only because the space under the tick labels happened to be free.
  The footer is measured before the grid is laid out now: letter 3 lines at
  5% of the page, slide 3 lines, 3.5in column 5 lines and the plot shrinks
  to make room.

- **`CSC59 (bad)` ran off the left edge.** The margin reserved a flat four
  characters’ worth whatever the labels said, and a bad channel is
  exactly the row somebody goes looking for. Measured from the labels that
  will actually be drawn, capped so one pathological name cannot eat the
  plot.

- **The last native browser dialog is gone.** `window.confirm` survived on
  “Forget this recording” — the one control that destroys a record’s
  history, and the one with no room to say so. It uses the application’s
  own dialog now, and says the part the old text left out: a fresh record
  gets a NEW permanent id, so anything still attached to the old one will
  not find its way back.



- **The incremental sync was comparing timestamps as text, across offsets.**
  Found while checking that picking up a layer sheet reached the shared
  table. It did not: the payload was right, the columns existed, nothing
  errored.

  ```
  batch = [r for r in batch if str(r["updated_at"]) > since]
  ```

  `since` is UTC — `2026-09-09T18:55:06+00:00`. A record written 45 seconds
  later carries `2026-09-09T14:55:51-04:00`, because `cloud.ts` validated the
  stamp and handed it back as BARRY wrote it. As text, `"14:55" < "18:55"`,
  so a row written *after* the last push looked older than it and was
  dropped.

  Vermont is UTC-4, so this hit **every record whose local hour was before
  20:00** — which is every record written during a working day. Those edits
  travelled only when something forced a full push. It is very likely the
  mechanism under "I made updates to Sylvia and Shahriar and Rain's profiles
  that are not showing up in a different computer"; the missing `role` and
  `initials` fields were real and this was underneath them.

  `ts()` normalises to UTC now — a timestamptz column stores an instant, so
  the offset was never information the database kept, only something the
  sender could get wrong — and the filter parses both sides. A stamp that
  cannot be parsed is sent rather than dropped: a needless upsert costs one
  round trip the database discards, and a dropped one loses somebody's work.

  The same fault was on the way IN, in the error triage: a signature you
  marked handled here carried a local stamp and the incoming row carried
  UTC, so as text your afternoon mark sorted before a colleague's morning
  one and the pull undid your triage. Both sides compare times now.

- **A sync could replace real curation decisions with "undecided", and the
  progress bar would not have noticed.** Found because `curate.html` failed on
  `left`, and the server's own numbers were impossible:

  ```
  {"by_label": {"garbage":1,"solid":1,"sputter":1,"unspecified":7},
   "left": 0, "percent": 100, "specified": 10, "total": 10}
  ```

  Ten specified, seven of them unspecified. Three faults in a line:

  * `curation_events.label` is `NOT NULL`, so the shared table has no way to
    write "nobody has decided" and the push sends the word `unspecified`
    instead. That is the schema's encoding and it is fine.
  * `_apply_curation` then wrote that word back as a *local* label, because
    "different from what we have" was the whole test.
  * `progress` counts any non-empty label as a decision, so those became
    decisions: `left` 0, `percent` 100, on a set nobody had finished.

  Measured on a real set afterwards: 162 cloud rows carrying the word against
  162 locally decided events. The old applier would have overwritten **every
  one of those decisions with "unspecified"** — and `specified` would still
  have read 162, so nothing on screen would have shown that a day of
  judgements had been replaced by a placeholder.

  Now: the word is normalised to "no decision" on the way in, `progress`
  refuses to count it, and an incoming decision only wins if it is newer
  (below). Applying all 324 rows for that set changes nothing.

- **A pull could undo today's curation with a decision from last January.**
  `_apply_curation` compared no timestamps at all — last pull won — so two
  people working one set undid each other silently. Measured before the fix:

  ```
  event e99e3dd4290 | local: spike, decided 2026-09-09T11:27:37-0400
  applied: 1        | label now: garbage, at 2025-01-01T00:00:00+00:00
  ```

  The rule now: a decision beats no decision, and past that the newer one
  wins, compared as times. An incoming row with no stamp cannot overturn a
  decision that has one — on the push side an unreadable stamp means "send it
  and let the database sort it out", which is cheap, and on the pull side it
  would mean "overwrite somebody's judgement on no evidence", which is not.

- **A repair to the shared table needs a stamp or it is silently discarded.**
  Worth writing down: `barry_keep_newest` returns the OLD row for any update
  whose `updated_at` is not newer, so a `PATCH` that fixes a value and leaves
  the stamp alone comes back HTTP 204 and changes nothing.

- **A full push died on duplicate keys, which is the push you reach for when
  things are not travelling.** `ON CONFLICT DO UPDATE command cannot affect
  row a second time` from `errors`: two shards holding the same failure
  produce two rows with one id, and Postgres will not guess which you meant.
  Batches are collapsed to one row per conflict key — the later one, because
  the builders read in order — including the implicit primary key, which is
  where it bit: `errors` is keyed on `id` and is not in the `ON_CONFLICT`
  map.

  With both fixed, a full push is 44,316 rows across 19 tables in 69 s, and
  an incremental one carries a sheet picked up a minute ago in 79 rows.

- **The two session views were two doors to one answer.** "Scan a drive" and
  "Everything BARRY knows" were both seeded from the whole registry, so both
  showed all 476 recordings. Three separate faults:

  * sightings were keyed on `provenance().machine` — the *typed* label — so
    this computer's were filed under `Bluebarry`, `DESKTOP-4H65AI7` and
    `Strawbarrry`, and asking "has this machine met it" by id matched **none
    of 476**. New sightings are keyed on the machine id, which is derived;
    the label rides along for reading; and "have I met this" matches the id
    or any name this computer has answered to, because rewriting years of
    other machines' sightings is how two people's computers got merged the
    last time.
  * `setMode` toggled the two panels *under* the list and never re-drew the
    list, so both modes rendered the same 188 cards.
  * `#sessSub` had two authors — prose from the mode switch, counts from the
    tree — so it read `188 of 185` in one mode and prose in the other. One
    author now, and the count and the filter share a predicate so they
    cannot disagree again.

  Scan a drive: **185 on this computer, read from the registry on this
  disk**. Everything BARRY knows: the shared catalogue, kept in step through
  Supabase.

- **The figure builder printed six copies of one H3 where an H10 was
  wanted.** `buildInitialLayout` copied each pane into a panel and dropped
  `channels` — the per-pane override that *is* the column — so six panels
  each fell back to the whole selection.

  It is one panel now. The cell subdivides itself: the back shank's three
  columns in physical order, a gap, the front shank's three, each headed
  with its window and channel run (`W1 centre / CSC 1-31/3 +32`), sharing
  one depth axis and **one colour scale computed across all six before any
  is drawn**. Six independently auto-scaled CSDs is the bug already fixed
  once in the viewer, and a figure is where that mistake gets printed.

- **My own harness runner was under-reporting.** It counted one spelling of
  a passing check, so `figgrid.html` — 54 checks, every one passing — came
  back as a single check, indistinguishable from a screenshot-taker. Part of
  why the suite looked dead in places.

### Changed

- **The housekeeping view opens in about a second.** It was nine, then two,
  now 1.3. What was left after the figure index was three more stores read
  once per recording — measured over the real 526:

  ```
  the event bank      950 ms   (66 entries, rescanned 526 times)
  curation sets       585 ms
  layer sets          153 ms
  ```

  Read in bulk instead they are 330 ms for all three, once. The bank count
  survives the change exactly because the matching is an elif-chain: every
  entry lands in one tier, so the count is the size of a union rather than
  a sum. Checked by running both paths over all 526 recordings and
  comparing field for field — 502 banked entries, 4075 layer labels and
  9222 curated events, and every recording agrees.

  Opening a single recording still reads the three stores directly, because
  reading every store to answer about one is slower than the thing it
  replaces. That route is 83 ms.


- **The suite went from 1,746 checks with 60 failures to 1,935 with none**,
  and almost all of the movement was the suite learning to tell a fault from
  this machine. What the seventeen failing harnesses were really saying:

  * **Three crashed on each other.** `bankback` and `strip2` both opened a
    menu whose popover was already open — left by the harness before them —
    so the click closed it instead, and the next line dereferenced null:
    “Cannot read properties of undefined (reading 'click')”. A menu that
    toggles is correct; a test that assumes it starts closed is not. They
    dismiss anything open first, wait for their own popover rather than
    sleeping at it, and check each control before clicking it — so a missing
    one is a named failure instead of a crash forty lines later.

  * **Five asked for data this machine does not have**: a defective
    recording to audit, an external drive of sorted snapshots, a missing
    pip-installable package, a recording with event marks, a collection with
    something in it. Each now says what is missing and keeps every assertion
    for when it is there.

  * **Four measured the built-in example** — organising it, checking its
    path shape, exporting a figure from it — and it is deliberately not a
    registry record and not a folder.

  * **Three asserted behaviour that was deliberately removed**: nine filter
    pills, a side channel rail, and switching probe forcing CSD.

  * **`cloudkey`** wanted a button reading “Sync now” and found “Syncing…”,
    because a sync another harness started was still in flight.

  * **`scanreg` had never once been able to pass** — it reads its root from
    `?root=` and the runner never passed one, so for its whole life it
    scanned a folder named “null”.

  Two of the seventeen were real faults in the application, and both are
  above: a channel could not be marked bad on any raster pane, and every
  figure rebuild restored into a session nobody was looking at.


- **The harness suite tells the truth about this machine.** Seventeen
  harnesses were failing at the last full run and most were not reporting
  faults at all:

  * `check` asserted a frequency band set on the *pane*, when the band is
    locked to the recording by default — 43/6 to 49/0.
  * `housekeeping` and `pathprobe` organised and measured the built-in
    example, which is deliberately not a registry record — 29/10 to 42/0
    and 10/2 to 13/0.
  * `probehz` asserted that switching probe *forces* CSD, which was removed
    on purpose because it silently turned a voltage raster into a CSD. It
    now picks CSD and checks it survives the switch — and so proves six
    CSDs of one H10 really render.
  * `lineage` assigned “garbage” to a candidate that was already garbage,
    so nothing moved and the bank correctly wrote no version.
  * `scanreg` had never once been able to pass: it reads its root from
    `?root=` and the runner never passed one, so it scanned a folder called
    “null”. It gets a fixture now — three folders with Neuralynx-shaped
    headers, a fresh identity per run, because forgetting is permanent and a
    reused fixture can never be registered again — 16/8 to 26/0.
  * `scancheck`, `snapimport` and `kilosort` required this machine to have
    a defective recording, an external drive attached, and a missing
    pip-installable package. All three now say what is missing and keep
    every assertion for when it is there.

  And the runner itself was under-reporting: it counted one spelling of a
  passing check, so `figgrid` — 54 checks, every one passing — came back as
  a single check, and it printed counts without names for a third of the
  suite, which is why triage needed a re-run per harness.


- **StrataScope has event curation's workbench.** It had a flat list of
  every sheet that exists, in one order, with a Delete on each that fired on
  the first click and erased every label on that recording without a word.

  Now: the open sheets are the bench, everything else is the shelf, and
  picking one up claims it if nobody has. Opening a recording in StrataScope
  puts it on the bench, the way curating does. **Close** is the only removal
  — it takes the work set off the bench and changes no label, no version and
  no snapshot — with **File away** for "I am done thinking about this at
  all". Picking up an archived sheet is refused unless you say you mean to
  un-archive it, so filing something away cannot be undone by accident. A
  work set can be named by clicking its title, because a second pass after a
  probe map was corrected is not the same work as the first.

  The bench travels: `assignee`, `is_open` and `archived` sync, so it can
  answer "is anybody already labelling this recording" rather than only
  "what am I working on". Migration 13.

  Delete is gone from the cards. It had grown a three-paragraph confirmation
  explaining everything it would *not* destroy, which is the tell that the
  button should not be there.

- **The figure footer says what the figure is of, and stops cutting itself
  off.** It was two fixed lines at a fixed size with everything past a
  character count replaced by an ellipsis — so the answer to "which
  channels" would have been the first half of the answer. It packs now: the
  facts are laid into as many lines as they need at a size that fits the
  page, and nothing is dropped. On a letter page that is three lines in the
  height the old two occupied.

  What was missing and is now there: the probe, the hemisphere, the filter,
  which channels (as runs — `CSC 1-10/3` — not sixty-four numbers), which
  are marked bad, the contact spacing, the gain, and whether the scale was
  pinned or worked out from the data. That last one matters more than it
  looks: a printed CSD with an auto scale cannot be compared with another
  printed CSD, and nothing on the page used to say which it was.

- **The scan's own two settings are behind one button**, like the filters
  beside them. "Read headers" and "Depth" were a checkbox and a number box
  sharing a line with the recent-roots list. The button names what is not
  standard rather than counting it — `depth 3` explains a scan that found
  nothing, where a badge reading `1` does not.

### Added

- **A channel list for time-frequency panels**, with **Stack** (a band per
  channel) or **Mean** (one averaged map) once more than one is picked, and
  a **Match the viewer** button that takes the channels, the mode, the band
  and the display crop back from the pane on screen.


- **A panel spans by having its edge dragged.** Grips on a panel's right
  edge, bottom edge and corner; the cells it would take light up as you go.
  An edge owns one axis, so dragging the bottom edge sideways cannot
  secretly widen the panel. Shift-click still works.

  Measured while checking it: dragging the bottom edge did nothing at all,
  because the row below was scrolled past the bottom of the dialog and the
  pointer resolved to the backdrop. A drag now resolves to the nearest cell,
  which also covers the gaps between cells and overshooting the grid.

- **A panel comes out by being dragged out.** Moving, adding and spanning
  were all drags; removal was a small x in a list. There is a bin under the
  grid now.

- **Which window is which, in channel numbers.** Every grid cell and panel
  row carries the channels its panel draws — `CSC 1-10/3` — so six columns
  of one probe are told apart at a glance instead of by index.

- **Which columns of the probe, and in what order.** Collapsing the six
  panes into one panel answered “make it a single 1x1 for the entire 6
  pane view” and took the other half of the request with it —
  “remove certain windows and arrange certain windows in certain
  order”. The panel editor now shows a chip per column in the order they
  will be drawn, each with its channel run: click one to drop it, drag one
  onto another to reorder, click a faint one to bring it back. The last
  column cannot be dropped, because a panel drawing nothing is not a
  picture of anything.

  Not cosmetic. A shank that broke mid-experiment is three columns of noise
  beside three of data sharing one colour scale, so dropping it makes the
  other three readable and not merely tidier. One column left draws as a
  single full-width raster with its head suppressed, since the panel title
  already says which column it is.

---

## 2026.09.09.1 — the computer is not the person

### Changed

- **What a computer is called is now the computer's own record.** It used to
  be a field in the profile, next to your name and your email, and that was
  wrong in a way that took measuring to see: every path that saved a profile
  could rename the machine, and that name is stamped on every error, action
  and run.

  Measured across 216 errors before the fix: **one computer had filed under
  five different labels** — Bluebarry, DESKTOP-4H65AI7, StrawBarry,
  Strawbarrry and "Rig 2 (Barry lab)" — while **two different computers had
  both been set to "Strawbarrry"**. So one machine looked like five and two
  machines looked like one.

  It lives in `device.py` now, in its own shard, and switching who this
  machine credits work to cannot touch it. The old value is adopted once at
  start-up, because a machine that has already been named should not revert
  to its hostname and fork its own history.

- **Errors group by the computer, not by what somebody typed.** `shard` —
  the hostname slug plus a hash of the MAC — has been on every error record
  all along and is unique by construction. Grouping on it collects this
  machine's 188 errors into one row instead of five. The label is still what
  is shown, with the real hostname in brackets: **Bluebarry
  (DESKTOP-4H65AI7)**, **StrawBarry (LCOM549913)**, **Strawbarry
  (BARRYLAB)** — the last two being different computers whose friendly names
  differ by the case of one letter.

- **DEVICE is a button.** It opens a panel that names this computer, archives
  the ones that have gone, lists the names in the log that no machine answers
  to, and warns when two computers answer to the same label. The rename box
  lives there and only there.

- **Editing a profile cannot go wrong the way it did.** Save used to decide
  what to do by comparing the name in the form with the name being edited, so
  changing a name at all fell through to the branch that set THIS COMPUTER's
  identity to the person being edited and then added their new name to the
  roster beside the old row. Proven by putting the old line back: editing a
  probe person set the machine's profile from "Shahriar Tafti" to "zz edit
  probe renamed".

  The mode is explicit now and on screen. A rename is refused with the
  reason — the name is stamped on every decision, banked set and layer sheet
  — and offers the two real options. **Add somebody…** is its own button, so
  creating is never a side effect of editing.

- **Three jirai kei themes**: Jirai Kei (black, baby pink), Jirai Shiro
  (off-white, deep rose) and Jirai Yami (plum, lavender, sick mint). The
  first pass had errors 1.04:1 and 1.32:1 from their own accents — a failed
  run rendered as decoration — so the error colours were pushed apart to
  1.62:1 and 1.97:1 and `--ok` is mint in all three.

### Fixed

- **Event versions travel through Supabase instead of waiting for a git
  pull.** Three separate reasons they did not:

  * the version history was never sent — no `versions` column, nothing in
    the payload
  * `updated_at` was `added.at`, the moment the entry was *created*, so an
    edited entry never looked new to the incremental push and stopped
    travelling the moment it existed
  * `_apply_bank` skipped any row whose id it already had, so a version that
    did come down was thrown away on arrival

  The snapshots stay behind, and that is measured rather than preferred: the
  110 versions here are 44 KB of metadata and 0.5 MB of snapshots. The
  metadata is what makes a version *appear*; the snapshot is what lets one be
  *restored*. So metadata goes live over Supabase and snapshots stay in the
  JSON, which is the redundancy copy.

- **A merged-away name stays away.** Merging Rain into Rain Younger would not
  stick: deleting the row locally worked, deleting it from the shared table
  worked for a few seconds, and then the other machine — running, and still
  holding the old direction — pushed its copy back.

  Two things were wrong. There was no way to say "this name is retired", so
  `forget` now writes a tombstone, which is the mechanism this codebase
  already uses to make a deletion travel. And the two records had aliases
  pointing at *each other*, so whichever the roster compiled first won.

  Getting the tombstone rule right took three attempts, and the two failures
  are worth recording: "retire whenever asked" and "retire whenever a row was
  removed" both retired a live colleague, because `forget` is called on names
  the data carries and such a name can still have a hand-added row. The rule
  is now: recompile the roster and retire the name only if it has actually
  gone. Verified stable across a minute of live pulls with the other machine
  pushing: one entry, Rain Younger, 3,028 records, active.

### Added

- **A sync button you can reach.** There was one, three clicks in. The rail
  chip now syncs on click and reports the phase while it runs.

- **The JSON shards, viewable.** Supabase is the primary route; the JSON in
  GUI_logs is the redundancy — what survives an unreachable database, what
  holds the snapshots too large to send, and what a fresh clone arrives with.
  A backup nobody can inspect is a backup nobody trusts, so it has a section
  beside the error log: 1,084 files across 12 folders, whose each is, when it
  was written, and the contents of any one of them. Read-only.

- **Archiving, for people and for computers.** Removal is refused for
  anything the data carries, correctly, which left nowhere to put somebody
  who has left the lab. Archiving takes them off the pickers and changes no
  count anywhere.

- **One camera is one pane.** An H10-D is six probe columns, so H10 mode
  gives each one a pane — right for traces, voltage, CSD and theta, nonsense
  for video, which produced six panes of which one played. Both the way in
  and the panel switch now collapse to one.

- **One colour scale across an H10.** The master strip's tooltip said it set
  every pane at once and the scale did not: six shanks of one recording came
  up at [-2.71e+4], [-2.04e+4] and [-2.16e+4] while the control read
  "pinned", and a CSD is read by colour.

---

## 2026.09.08.17 — numbers you can quote

Six things, and one thread running through all of them: every one of these
produces a number somebody would say out loud — "587 in twenty-nine
minutes", "213 actions since I last looked", "five qualify" — and a number
you quote is a number that has to be right.

### Added

- **A session receipt.** What a sitting came to, in a card: how many
  decided, over how long, at what pace, split by label. On the way out of a
  set when there was a sitting worth reporting, and from the **Receipt**
  button on the workbench whenever the question arrives later.

  It exists for two unrelated reasons. It is pleasant to see the afternoon
  add up. And the pace is the only thing anywhere in BARRY that says
  something about the *deciding* rather than about the data — a set decided
  at twenty a minute and a set decided at four are not the same evidence,
  and nothing in the interface used to show which one you had.

- **A hall of garbage** — the candidates nobody had to think about:
  rejected, decided in under two and a half seconds, never flagged, never
  revisited. It is a teaching set, because the fastest way to explain what
  garbage looks like is forty examples that nobody hesitated over, and it is
  a sanity check on the detector, since a detector producing mostly obvious
  garbage is saying something about its threshold. **look** opens the
  recording at that moment rather than entering curation: looking at an
  example is not deciding it, and entering the set would take it off
  whoever has it.

- **"Since you last looked."** A card at the top of History: how many
  actions, by whom, on which recordings, and how many errors — since the
  last time you pressed **Mark as seen** on this machine. It leaves your own
  actions out, because a digest of what you did yourself is a diary, and the
  question is what everybody else has been doing.

  Reading it does not clear it. The first read is usually the one where you
  get interrupted, and a digest that clears itself on render cannot be read
  twice.

- **The dataset, and the slot a model would write into.**
  `/api/curation/dataset?format=csv` is all 9,265 human decisions as rows —
  which recording, when in it, what it was called, by whom, how long they
  took and whether anybody revisited it. The last two columns are the
  interesting ones: hesitation is the signal.

  And `POST /api/curation/<gid>/<kind>/order` sets the order candidates are
  visited in — `hardest` puts the ones somebody hesitated over first, which
  is worth having on its own for a review pass.

  This is deliberately where it stops. No classifier. The moment a model
  exists somebody will be tempted to let it decide, and the whole value of
  this store is that a person did: every decision in it has a name and a
  time against it. The useful thing a model can do here is change the
  *order*, so the hard cases get looked at while people are still fresh.

### Changed

- **A fault on two machines is now two rows.** The same traceback on the rig
  and on the desktop used to arrive as one group with a count of two — and
  "happened twice" is a different fact from "happens on both machines", the
  second of which tells you it is not something about one computer.
  Resolving is scoped the same way: **Resolved** on the rig now says fixed
  on the rig. `?fold=fault` folds them back to one row per fault, because
  "is this the same bug in both places" is also a real question.

  The fault's own signature is unchanged. Twenty-two triage marks were
  keyed on it before this, and they all still apply.

- **Errors and the Debug trace have a device picker.** Errors filters to one
  machine's groups. Debug swaps this machine's request trail for the chosen
  machine's feed — its actions and its errors, interleaved, because the
  useful shape is "these four things happened and then it broke". The
  request trail itself stays local and should: nobody debugs by reading
  somebody else's HTTP log.

- **The Sync button says where it has got to.** It used to read "Syncing…"
  for three or four seconds, which is indistinguishable from hung. Both
  halves now name the table they are on and how far through they are — the
  pull especially, which is the slow half at fifteen round trips and used to
  report the single word "pulling" for all of them.

  The bar's denominator is an estimate, and it stretches rather than
  overrunning: counting exactly would mean walking every table first, which
  is most of the work the bar is meant to be reporting on.

- **Four names became two.** `theexaminedexistence@gmail.com`, `Shahriar`
  and `Shahriar Tafti` were one person; `Rain` and `Rain Younger` were
  another. 423 decisions, 430 reviews, 38 assignments and 118 bank fields
  now carry the name their author actually goes by.

  Seven bank entries were left alone on purpose. `added.by` is immutable
  across the shard merge — provenance is not an editable field — so those
  fold at read time instead, through aliases stored on the roster. The
  activity and error logs were not touched at all: they record what each
  machine believed at the time, which is the point of a log.

### Fixed

- **The StrataScope layer buttons got their colours back.** A
  `border-color:` shorthand on the armed-brush style was overriding the
  `border-left: 3px solid var(--cat)` that carries each layer's colour, so
  all fifteen went grey the moment anything was selected. It is a
  `box-shadow` ring now, which cannot touch the border.

### The sync was quietly broken, and this is what it took to find out

All four of these were found by checking whether the two SQL files from
earlier had been run. 06 had; 07 had not; and the consequences went a long
way past "one field does not sync".

- **One un-run migration was stopping the whole lab's sync.** `sessions`
  carries six columns that `supabase/07_reference_channels.sql` adds, so
  every upsert of a changed recording came back

  ```
  HTTP 400 PGRST204  Could not find the 'extraction_note' column
                     of 'sessions' in the schema cache
  ```

  and because `sessions` is first in the push order, that exception aborted
  the push before it reached any other table. Curation, layers, the bank,
  the error triage: none of it went up, from the moment a recording changed.

  It hid because it was intermittent in the worst possible way. A push with
  no session changes in it skips the table and succeeds, so the sync looked
  fine most of the time. The repair push sent **26,327 rows**.

  A column the database has not got is now dropped on the way up and the
  rest of the push carries on — and because that means nothing visibly
  breaks, the sync panel says which file to run, and
  `GET /api/sync/pending-migrations` asks the schema directly rather than
  waiting to be refused. It distinguishes a column some migration accounts
  for from one nothing does; the second is the more worrying case, since it
  means a machine is sending a field no migration explains.

- **The roster merge was being undone on every pull.** Rain Younger folded
  into Rain and Shahriar's three spellings into one — on this machine, until
  the next sync. `aliases` was a local-only field: the shared `people` table
  has no such column, so the cloud still held the old names and
  `_apply_people` wrote them back every cycle. The merge looked like it had
  failed when what had happened is that it had been reverted.

  Aliases travel now (`supabase/08_people_aliases.sql`), unioned rather than
  last-write-wins, because two people merging different spellings on
  different machines are both right and neither should erase the other. And
  a pull no longer re-creates a name this machine has been told is somebody
  else.

- **The guard against the push/pull write loop had never once fired.**
  `_apply_people` skips a row that says nothing new, because writing an
  unchanged record restamps it and a restamped record is pushed back up as
  an edit — which is how the same eleven people came down and went up again
  forever, between every pair of machines. The skip read
  `for p in (self.people.roster() or [])`, and `roster()` returns a *dict*:
  the loop walked its keys, `"people".get(...)` raised, the bare `except`
  below set `have = {}`, and it moved on. Measured before the fix: 11 of 11
  unchanged rows written. After: 0, twice in a row.

  This is the fourth time this loop has been found in this file, and the
  first time the fix for it was itself broken.

- **The digest was reporting 8 where the answer was 2,018.** It asked for
  the newest 2,000 rows and *then* discarded this machine's — and PostgREST
  caps a response at 1,000, so on a busy machine the entire budget went on
  rows that were thrown away. The exclusion is in the query now and the
  headline comes from a counted request rather than from `len(rows)`.

  Where the breakdown cannot cover the whole total, the card says so rather
  than printing two numbers that do not add up. `/api/activity/who` had the
  same shape of problem and now reports what it counted.

  Worth noting for anyone reading the code: `provenance().machine` is
  `"Bluebarry"` where `machines.hostname` is `"desktop-4h65ai7-d565"` — the
  same computer under two names. A check comparing the wrong one passes
  vacuously, which one of the new harness checks was doing.

- **"Is there anything from the rig at all" could not be answered by the
  route that exists to answer it.** `/api/activity/who` tallied the two
  thousand newest rows -- capped to a thousand -- so on an evening when this
  machine had written the last thousand, it reported **one person and one
  machine**. The true answer was five of each.

  Both sets are small and known, so they are counted over the whole log now:
  the machines from every source that knows a machine name, the people from
  the roster with each of their aliases counted alongside their surviving
  name. That last part matters — `ilike`, not `eq`, because aliases are
  stored lower-cased and the log holds the name as it was typed, so a
  case-sensitive match counted nothing and reported "Rain" and "Rain
  Younger" as two people all over again.

  The machine list came from the `machines` table alone, which holds the
  three computers that have registered a heartbeat — while the log also
  carries `DESKTOP-4H65AI7` (6,847 rows), `BarryLab` (305) and `Blackbarry`
  (1). It attributed 3,802 of 10,955 rows and said nothing about the rest.
  Now: 10,954 of 10,955, with the remainder reported rather than buried, and
  `Rain` at 2,103 — which is 2,095 plus the 8 that were filed under the
  other spelling.

  The action-kind breakdown is still read off the recent page, because there
  is no bounded list of action names to iterate and "the shape of the recent
  work" is a fair thing to read off recent work. The route says which of its
  numbers are which.

**Still needs somebody with the SQL editor open:** run
`supabase/07_reference_channels.sql` and `supabase/08_people_aliases.sql`.
Until then the fissure, ripple and hilus channels for 62 recordings, and the
roster merge, exist on this machine only. The sync panel will stop mentioning
them once they are in.

### The test suite could not be run, which is why so much of this was found late

There are 92 harnesses in `web/_dev` and no way to run them together, so they
were run by hand, a few at a time, whenever something specific was being
changed. `tools/run_harnesses.py` runs all of them and tallies the result.

Writing it took three attempts, and each failure is worth knowing about
because each one made the suite look healthier than it was:

- The harnesses report in three different shapes — a `#out` div of plain
  lines, a `#log` `<pre>` of `<span class="good">ok …`, and a couple that put
  the verdict in the document title. The first runner understood one of them
  and reported **"0 ok, 0 fail"** for two thirds of the suite, which reads
  exactly like a clean run.

- Fifteen harnesses take `?session=<path>` and call `xplore.open()` on it
  without checking. Run without one, `open(null)` renders nothing and every
  geometry assertion fails against an empty pane — so thirteen harnesses
  looked broken and the cause was one missing argument. `master.html` went
  from five failures and a crash to **12 ok, 0 fail** once it had one.

  This is worth saying plainly: those failures were read as a possible
  regression in the xplore control strip, and the strip is fine. It renders
  `Filter`, `Ch 64/64`, `Marks` and `More` exactly as it should.

- But not to all of them. `bank.html` is 47 ok / 0 fail bare and *crashes*
  with a session; `strata.html` skips cleanly bare and throws on the demo
  recording, which has no layer sheet. So the argument is passed per
  harness, and the runner names the two exceptions and why.

- And it never set `--window-size`, so every layout harness was measuring
  an 800x600 window. `stratacheck.html` reported six failures — rows 1px
  tall, 0 of 64 rows clickable, 22 buttons off screen — and passes at
  1600x1000. `typing.html` reported 47 clipped entry names and passes.
  `chrome.html` went from two failed divider drags to 26 ok. A layout
  harness run in a 423px window is measuring the window.

One more of the same kind, in a harness rather than the runner:
`chrome2.html` measured the rail mid-transition. Under
`--virtual-time-budget` the timer clock fast-forwards and the animation
clock does not, so a transition sits at its start value for ever — the rail
animates its width through `@property --rail`, and every reading came back
190px however many times the burger was clicked. Settled with
`Animation.finish()`, as `motion.html` already knew to do: **190 → 54
(`rail-icons`) → 0 (`rail-away`)**, with `#main` growing 787 → 923 → 977 to
fill the window. The collapse works exactly as specified.

The suite now runs 936 checks passing against 763 before, with 12 harnesses
still failing rather than 22 — and almost all of that movement was fixing
the instrument, not the app. It is worth being blunt about that: for most of
this the harness output was read as evidence about BARRY when it was
evidence about the runner, and two alarming conclusions drawn from it — that
this machine's log was stranded from the cloud, and that the xplore control
strip had stopped rendering — were both wrong.

What is left is concentrated in the session scanner (`scanreg`,
`housekeeping`), a set of harnesses that need a specific recording rather
than the demo (`chan64` wants 64 channels, `kilosort` a sortable recording,
`lineage` an entry with versions, `spancentre` live candidates), and
`bankback`/`strip2`, which crash on a pane control before their first check.
`pathprobe` is the interesting one: it asserts every registry path is a
complete path, and the demo sessions carry pseudo-paths like
`demo:ds-tutorial` that are not. None of these are in anything this release
touched, and none of them has been confirmed as a defect rather than as
drift — that is the next session's work, and it starts from a runner that
can be trusted.

`uiprobe.html` is fixed too, and had never worked: it read `win().BARRY`, and
`BARRY` is a top-level `const` in core.js — a binding in that script's scope,
never a property of `window` — so it printed "MISSING" on a perfectly healthy
frame and then threw calling a method off undefined. `win().eval(...)` runs
inside the scope that can see it.

### A note on honesty

The receipt's first version reported **421.7 decisions a minute** for a set
that had been filled down fourteen at a time. It was not wrong about the
arithmetic — 738 decisions across 105 seconds really does divide out at
seven a second — it was wrong about what a timestamp means.

7,655 of the 9,265 decisions in this store were stamped in bulk: a snapshot
import stamped 1,224 of them at one instant, and fill-down stamps a
column at a time. So a decision now counts towards a pace only if it has a
timestamp to itself, and the rest are counted and named as what they are.
The receipt says "1,224 of them share a single timestamp — an import or a
fill-down stamped the set all at once, so nobody sat and decided them one by
one", and quotes no rate. The hall of garbage leads with the same caveat
before its list, because somebody who reads "5 qualify" and stops has been
misled about nine thousand decisions.

A card that says nothing is fine. A card that says seven a second is not.

Sixty-one checks in `web/_dev/digest.html` cover this, most of them
refusals — that the pace is absent where it cannot be known, and that the
bulk share is said out loud rather than averaged in. The phase sequence a
sync reports moved out to `tools/check_sync_progress.py`, on the real clock:
the browser harnesses run under `--virtual-time-budget`, where the page's
timers fast-forward while the server carries on at the real clock, and every
attempt to watch a real sync from in there either outran it or lost the lock
to the background pass.

---

## 2026.09.08.16 — the history the lab shares

### Changed

- **History can show the whole lab, not just this machine.** The log was
  never the problem — ninety-five distinct actions, and `session.open`
  already carried the path, the channel count, the sample rate and what was
  restored. What could not be answered was "who loaded that recording last,
  and what did they do to it", because the view read this machine's own day
  files and nothing else, so the answer was available only if it happened to
  be you.

  A switch between **This machine** and **Everyone**, a filter by kind of
  work (session, curation, bank, layers, figure, run…), and the rows now
  carry who did it and what it was done to — the recording's label, or the
  file, rather than making you open each one to find out.

  The kind filter matches a prefix, so "curation" reaches
  `curation.enter`, `curation.bank` and `curation.collision` alike. The
  useful question is about a kind of work, not one verb.

- **`/api/activity/who`** answers the shape rather than the list: who has
  done how much, from which machine, last seen when. Currently 756 actions
  from Shahriar Tafti on Bluebarry, 236 from Rain on StrawBarry, 8 from Rain
  Younger — which is the sort of thing a list of a thousand rows makes you
  work out for yourself.

- **The activity log is out of git.** Eight tracked files, several thousand
  lines a week, one per machine per day — and committing them was the only
  way one person's history reached another, so the repository carried a
  growing pile of keystroke records and "who loaded this last" was *still*
  unanswerable until somebody remembered to push. It goes through Supabase
  now. The files stay on disk as the offline buffer: BARRY records what
  happened whether or not there is a network, which is exactly when it
  matters. They are cache, not transport.

The log itself stays push-only, and the reason is unchanged: it is an
append-only record of what happened on one machine, and pulling somebody
else's into this machine's day file would be writing their actions into a
file that says it is mine. The combined history is a query, and now there is
one.

### A note on honesty

When the shared log is asked for and cannot be read, the answer says so —
`scope` reports what was actually served and `wanted` echoes what was asked,
and the view prints the reason above the list. An unlabelled list of your own
actions is indistinguishable from "nobody else did anything", and somebody
would believe it.

---

## 2026.09.08.15 — the reference channels

### Added

- **Ripple, fissure and hilus channels on 62 recordings**, from the Toothy
  workbook (`tools/import_toothy.py`). These are the landmarks every CSD is
  read against — which channel sits at the fissure is a fact about where the
  probe ended up — and BARRY had nowhere to put them, so the answer lived in
  a spreadsheet and was true for whoever had it open.

  Corroborated rather than trusted: the hilus channel the workbook names is
  labelled HIL in the StrataScope sheet in **57 of 57** cases, and those
  sheets came from a different spreadsheet imported separately. Two
  independent sources agreeing is the best evidence either could have.

- **The extraction note, where it was not clean.** 53 read "Success: Clean
  extraction" and are not shown; the nine that do not are on the card —
  five bad-channel hits on the ripple, three with no CA1 SP channel at all,
  one bad channel at the hilus. That last group changes how the recording
  should be read, and it was only ever visible in a spreadsheet. Three
  sessions are flagged as still needing processing.

Needs `supabase/07_reference_channels.sql`.

### Not imported, and why

Four of the workbook's six sheets are deliberately left alone. The reasoning
is in the tool's docstring, and `--reconcile` reports the differences without
writing anything.

- **DS#, Garbage#, Flag#, Deep Rev.** BARRY holds the decisions these count,
  one per candidate, with who made each and when. Of the 40 sessions where
  both exist, 22 agree exactly and 18 do not — and m24 s4 reads spike 4 /
  garbage 734 in the workbook against spike 738 / garbage 0 here, which looks
  like two columns swapped in that row. Importing a count that disagrees with
  the decisions it summarises would give the lab two answers to "how many
  dentate spikes", one of which cannot be shown event by event.
- **Channel side and location.** Already imported from the feeder sheet.
  3,898 of 3,948 agree; the 50 that do not are in four sessions and are
  systematic rather than scattered — for m11 s10 the workbook says CA1 for
  channels 8–17 where the sheet says CA1 SP. Two spreadsheets disagreeing
  about a layer boundary is a question for whoever drew it, not something to
  settle by picking the file read last.
- **Manual Vs Auto** and **Data Summary** are results — a comparison of the
  detector against manual picks, and per-mouse counts with percent change.
  Putting either in the session record would file a conclusion where
  measurements go.

### Fixed while surveying

The first pass compared the workbook's DS# against a curation label id of
`ds` and reported BARRY holding zero dentate spikes everywhere. The label is
`spike`. A survey that reports a false conflict is worse than one that
reports nothing, because somebody acts on it — so the comparison now names
the label ids explicitly, and the channel parse reads the digits out of
`CSC12.ncs` rather than failing silently and finding nothing to compare.

---

## 2026.09.08.14 — what was happening, and which devices

### Added

- **Click an error to see the five minutes before it.** The card carried a
  message, a traceback and a timestamp — everything except the part that
  makes a bug fixable. BARRY already writes every filter change, colormap
  pick and raster switch into the activity log; the two were simply never
  lined up, so an error was a message and the answer to "what were you
  doing" was a message to whoever hit it.

  Five minutes before, and one after — before is where the cause is, and
  that minute after is how you tell "and then it recovered" from "and then
  everything broke". The error is drawn **in** the sequence rather than
  beside it, because a list of actions with no indication which side of the
  failure each one is on is not much of a list. Other errors in the same
  window are listed too: one fault often arrives as six and the first is the
  one worth reading.

  It reads another machine's activity from the cloud, which is the case the
  shared copy exists for — the log itself stays push-only, because copying
  somebody else's actions into this machine's day file would be writing
  their history into a file that says it is mine. If the cloud cannot be
  reached it says so, because "nothing was happening" and "I could not find
  out what was happening" look identical in an empty list.

- **A devices table**, in the debug view: every machine that syncs here,
  whether it still is, and what it has been sending. `machines.last_seen`
  has been a heartbeat all along and nothing read it, so "is the rig still
  sending its logs" was a question you answered by walking down the
  corridor.

  Online and sending are separate columns on purpose. A machine can be
  reachable and have stopped logging, and that is the more interesting
  failure of the two — one of the three here is online with three errors and
  no actions at all.

The debug trace itself stays per-process and in memory. It is what *this*
browser and *this* server did, and shipping raw request trails between
machines would be a great deal of volume for very little: nobody debugs by
reading somebody else's HTTP log. What is worth knowing across machines is
whether each one is still reporting, which is what the table answers.

### Fixed

- The context window compared ISO strings, and the local log writes local
  time with its offset while the cloud copy writes UTC — so lexicographic
  comparison silently dropped every cloud row, which read as "the other
  machine logged nothing" rather than as a bug. Everything compares moments
  now, including the harness that caught it.

---

## 2026.09.08.13 — layer sheets in the Event Bank

### Added

- **StrataScope sheets are in the Event Bank**, on a switch beside Events.
  They are the other output somebody cites in a paper, and they were only
  reachable through the ToolKit — so "where is the recorded output for m11
  s10" had two answers depending which output you meant.

  Not as bank entries, though. A bank entry is a set of event *times*, and
  every invariant in the bank is about times: the snapshots are
  `[[start, label], …]`, the counts are event counts, the import path expects
  a time column. A layer sheet is channel → region and has no times at all.
  Forcing it in would mean either lying in the times field or making all of
  those invariants optional, and an entry that is only half an entry is worse
  than a second list. One view, two shapes, neither pretending to be the
  other.

- **The same version workflow as a banked DS set.** Snapshot a pass and it is
  frozen as the next version, with a note about what the pass was; every
  version exports as CSV, read from its snapshot so it cannot disagree with
  the history panel. A row per channel including the unlabelled ones — a CSV
  that silently omits them cannot be told from one where they were never
  offered.

- A sheet is shown as **runs** rather than one row per channel: a probe passes
  through a layer for a stretch, so where the boundaries fall is the fact
  worth reading and "CA1" eight times over is not.

### Fixed

- **62 of the 67 layer sheets had no channel list**, so they displayed and
  exported as empty despite holding sixty-odd labels each — every reader
  walks that list, and my feeder import never wrote one. The importer now
  does, the readers fall back to the labelled channels when it is missing,
  and the existing sheets have been backfilled. A sheet is never invisible
  just because nobody said how wide it was.

---

## 2026.09.08.12 — labelling layers by pointing at them

### Changed

- **StrataScope: click a channel, then name it.** The rail put a dropdown on
  every row, and at 64 channels a row is six pixels tall — so labelling asked
  the mouse to be right twice, once to hit the row and once to work a menu
  covering the thing being labelled. Reported as "I can't click on individual
  channels to select anything", which is what a six-pixel target feels like.

  Click selects, shift-click takes a range, drag extends, ctrl-click adds
  one. Then a layer button — or its number — names everything selected, and
  `0` unlabels. Precision is needed once, and the second half can be a
  keystroke. The selection survives being labelled, because finding one
  channel wrong in a run of twelve is the common case and re-picking the run
  to fix it is not an answer. Escape drops the selection before it drops the
  mode.

  The brush stays for anyone used to it: with a layer armed and nothing
  selected, dragging still paints.

### Fixed

- **The layer overlay drew on nothing but the traces**, which is the one view
  people do not label against — the CSD is where a boundary is visible, and
  the four-way view showed no layers at all. It draws on image panels now,
  aligned to the rows the panel reports rather than to the sheet's own
  channel order: CSD drops the first and last channel, and laying the sheet
  over those rows would put every band one off, which is worse than nothing
  because it looks right.
- **And it could stop drawing entirely.** The overlay was gated on a flag set
  on the session object — but entering StrataScope reopens the recording, and
  a reopen can hand back a different object from the one the flag was set on.
  It now also accepts "this is the recording under the sheet", which the
  module already knows.

### Added

- **An overlay strength control** beside Fill down and Clear: Off, Faint,
  Clear, Solid. The bands show where a boundary fell, and past a point they
  are in the way of the data that decides where it should have fallen. The
  selection is drawn whatever the setting — turning the layers down is not a
  reason to stop showing what you are pointing at.
- **Session filters: Layers labelled, Layers to do, On this machine.** 387
  recordings here, 64 labelled, 323 to do, 188 reachable.

  Both filters were wrong on the first pass and the harness caught both: the
  registry rows are translated into cards, and the translation dropped `has`
  and `here` — so the layers filter matched nothing at all, and "on this
  machine" fell back to "has a path", which matched 382 of 387. A filter that
  matches everything is as broken as one that matches nothing and much harder
  to notice.

---

## 2026.09.08.11 — removing a name, and the colony sheet

### Added

- **A profile can be removed.** The button was missing; the backend and its
  route had been there all along. Only names nothing else carries can go —
  the roster is compiled from the profiles, the decisions, the bank and the
  assignments, so a name with work behind it is there because the data says
  so, and a button that appeared to delete it would be lying about what
  BARRY holds. Those are marked and say how many records hold them.

  The trap, which the harness now guards: the roster counts the hand-added
  entry itself, so testing that count directly refuses **every** hand-added
  name — precisely the set that can go, and precisely what a leftover test
  entry is. Three are removable here; four are held.

- **Mouse details from the colony Google Sheet** (`tools/import_colony.py`).
  Cage, sex, genotype across all three loci, date of birth, role, alive or
  perfused, and what was implanted where and when — for the 19 mice BARRY
  has recordings for. The mouse book has had slots for these all along and
  nothing to put in them, so every one of those questions was answered by
  opening the spreadsheet.

  Mouse facts only, deliberately: the sheet also carries session numbers,
  and recordings are the one thing BARRY should learn from the recordings
  themselves. A session that exists because a spreadsheet says so is a
  session nobody can open.

  Read-only, one direction, via the published CSV — no key to store and
  nothing that stops working when a token expires. It writes only what
  differs, so a re-run is a clean no-op: the property the roster sync and
  the layer sync both turned out to lack. Of the sheet's 241 mice the 199
  with no recordings here are skipped unless `--all` is passed.

  The implant column is the useful surprise — which probe, which hemisphere,
  what date — and is the only independent check on the hemisphere a
  recording claims.

---

## 2026.09.08.10 — "keep, greyed out" is gone

### Removed

**The greyed-out channel mode.** It sounded like a display option and was
really two features in one coat: to draw an unchecked channel the request has
to ask for it, and once that data is in the response every derived number is
computed over channels somebody explicitly excluded. It produced a CSD colour
scale twice as wide as it should have been and a trace amplitude that moved
when you unchecked something — both invisible unless you went looking, both
the kind of thing that reaches a figure.

Each was fixable and each was fixed. The trouble is the list did not
obviously end: every future panel and every future statistic would have had
to remember that some of its rows were not really selected. A feature that
adds a caveat to everything downstream costs more than it gives — and what it
gave, seeing what you are leaving out, is already in the channel list beside
the plot.

Unchecking means what it always meant: not read, not drawn, not in any sum.
`rows[].dim` stays in the panel response, always false, so a stale tab that
still sends `dim_channels` is ignored rather than answered with a traceback.

Marks visibility (show / faded / hidden) stays. A bookmark has never been in
anybody's arithmetic.

### Fixed

- **Collapsing the menu made the rail taller and gave it a scrollbar**, worst
  on exactly the screens with least room. Two causes, both mine: labels
  collapsed with `max-width: 0` kept their full height — the environment
  block stayed three lines tall while being zero pixels wide — and the icons
  rule's `padding` shorthand silently overrode the compaction in
  `@media (max-height: 700px)`, adding six pixels to each of eleven items.
  Collapsing now never costs more room than it saves, checked at four window
  heights.

---

## 2026.09.08.9 — what the spreadsheets knew

Three facts lived in two Excel files and nowhere else, which meant they were
true only for whoever had the file open. `tools/import_feeder.py` brings them
in; it reports and writes nothing unless given `--apply`, because the first
version of any importer is wrong in a way you only see in the diff.

### Added

- **Hemisphere, on 64 recordings** — 36 left, 28 right, from the feeder
  sheet's `side` column. Shown on the session card, because pooling a left
  and a right CA1 recording without noticing is a mistake that survives into
  a figure. Two-way through Supabase, and it records where the value came
  from so a wrong one can be traced rather than argued about.
- **Layer sheets for 64 recordings, with a v0/v1 history** — 4,076 channels
  labelled from the sheet's `location` column. v0 is the empty sheet and v1
  is the import, mirroring the event bank: a layer sheet is evidence, and
  evidence with no history cannot be cited. v0 looks pointless until you need
  to answer "was this channel ever unlabelled", which is exactly the question
  that comes up when a migration turns out to have been wrong.
- Two layer regions the vocabulary lacked: **THAL** (twelve deep channels of
  m2s3 — thalamus, and emphatically not "out of brain", which was the only
  other place it could have gone) and **DG2** (m30's lower blade with no
  sublayer given). Appended, so every id already written keeps its meaning.

### Not applied, on purpose

**The bad-channel column would only have removed things.** Against what BARRY
already holds from the Toothy workbook it adds nothing: all eleven differences
are channels BARRY calls bad and the sheet does not — 13 flags in total,
including m24 s4 dropping 24 and 25.

Un-flagging is not a neutral edit. A channel marked bad is left out of what
people look at and of what they compute, so clearing the mark puts whatever
was wrong with it back into the analysis, quietly, in recordings somebody may
already have drawn conclusions from. The importer reports it and writes
nothing; `--bad-mode union` adds without ever removing, and `--bad-mode
replace` treats the sheet as authoritative. Which of those is right is a
judgement about the data, not about the code.

### Fixed while there

- The layer applier rewrote every label on every pull, restamping sheets that
  had not changed and pushing them straight back up — the same write loop the
  roster was stuck in. It now writes only what differs.

Needs `supabase/06_hemisphere.sql`.

---

## 2026.09.08.8 — a greyed channel is not in the equation

### Fixed

- **"Keep, greyed out" was letting the greyed channels set the colour
  scale.** Measured on m11 s10 with sixteen channels checked: the CSD came
  back at ±73,833 with the rest removed and ±143,792 with them greyed — the
  same sixteen channels, drawn through a colour map twice as wide, because a
  display setting had been changed. A setting that alters the picture you are
  reading is not a display setting; it is a second analysis wearing a
  disguise. The scale now comes from the channels you actually chose, and so
  does the value the "auto" button resets to.
- **The traces had it too, by the same route.** Every trace is scaled by
  `robust_max`, which the server computes over every channel the request
  asked for — and in this mode that is all of them, so unchecking a quiet
  channel while a loud one stayed greyed rescaled everything on screen. The
  greyed ones no longer get a say in the axis.

The rule, now asserted: **an unchecked channel in "keep, greyed out" is a
reference image and influences no number.** The testable form is exact — the
rows you kept come out identical whether the unchecked ones are removed or
greyed — and the harness checks the colour scale, the reset value, and the
row identities against each other rather than against a remembered constant.

Also checked, because they were asked about and neither was obvious: the
spectrogram is unaffected either way (it has one channel and frequency down
the rows, so `dim_channels` means nothing to it — the risk was that it
failed on a field it did not understand, and it does not), and the mode
remains a fact about the recording rather than the pane, so every pane
showing it agrees.

---

## 2026.09.08.7 — who is curating what, right now

### Added

- **The curation workbench shows who is in a set at this moment**, on which
  machine, and how far they have got — updating every ten seconds while you
  are looking at it. This is a different fact from the name already on the
  card: "assigned to Rain" is still true next week, "Rain has it open" will
  not be true after lunch, and only the second one should stop you starting.
- **Opening a set somebody is actively in asks first**, and says what they
  have done so far. Advisory, with the override in the dialog: the ask was to
  prevent doing it *accidentally*, and a hard block would also stop the
  deliberate case — somebody left a set open on a rig and went home — which
  is common enough that blocking it would just teach people to ignore the
  warning.
- Taking a set **marks the other session rather than deleting it**, so their
  window finds out on its next heartbeat and says so. The alternative is
  silently carrying on writing decisions into a set you no longer hold, which
  is the quiet version of the collision this exists to prevent.
- The curation window announces a colleague arriving in the set you are in,
  once per machine rather than every twenty seconds.

Presence lives only in Supabase — no local shard, nothing in `GUI_logs`.
A presence row that survives a restart is a lie, and a file claiming somebody
is curating a set three days after they stopped is worse than no file. If the
cloud is unreachable the answer is "nobody is reported present", which is
exactly the truth available, and nothing about curating stops working.

It **expires rather than unlocks**: a session is present while it keeps saying
so, and a set is held while somebody is present in it. A lock you have to give
back is one that strands the set when a machine crashes, and the only thing
worse than two people in a set is nobody able to get into it.

Needs `supabase/05_presence.sql`.

---

## 2026.09.08.6 — syncing, and three things I broke

### Fixed

- **Sync was slow in a way that looked like broken.** Pull and push ran as
  one round trip every two minutes, and on failure backed off by doubling to
  a thirty-minute ceiling — so a single gateway timeout, which the code
  itself calls brief, took syncing offline for half an hour. They run on
  their own clocks now: a pull every 20 seconds, and a push within a few
  seconds of any local write rather than on a timer, which is what makes
  your work appear on someone else's screen while they are looking at it.
  The backoff asks what kind of failure it was — a timeout is worth retrying
  in half a minute, a missing table is not — and a clock that is ahead no
  longer stands sync down until BARRY is restarted.
- **Every pull re-applied the whole roster, and pushed it straight back.**
  `_apply_people` rewrote each incoming row unconditionally; rewriting
  restamps, and a restamped row looks like an edit. Two machines passed the
  same seven people back and forth forever. It writes only when something
  actually differs.
- **Hiding the menu hid the entire interface.** `#main` never declared a grid
  column — it landed in column 2 by elimination, because the rail held
  column 1. The moment the rail's hidden state stopped using `display: none`,
  the workspace auto-placed into the column the rail had vacated, which in
  that state is 0px wide. Both are placed explicitly now.
- **The collapsed rail's icons sat off-centre**, because the labels collapse
  to zero width rather than `display: none` so they can animate — and a
  zero-width flex item still gets its gap.
- **"Keep, greyed out" never reached the traces.** The dimming was built into
  the raster path, where the server draws the rows; the traces come back as
  an envelope and are drawn by the canvas, which had not been told about the
  mode. So it did the first half of its job — ask for all 64 channels — and
  none of the second, which is exactly "it puts in all 64 channels and
  prevents me from graying out anything". The harness missed it because it
  checked the server's PNG, and the traces never go near it.

### Added

- **Export CSV, per version, in the event bank.** The entry-level export gives
  the events as they stand now; a version is what they were at that pass,
  which is the thing a result should cite. Read straight from the version's
  snapshot, so it cannot disagree with the history panel.
- Mode changes are recorded with the stack that caused them, for the
  "curation snaps to StrataScope and back" glitch — nothing in the code
  accounts for it, so the next occurrence will name whatever called it
  instead of leaving nothing behind.

---

## 2026.09.08.5 — waiting, and moving

### Added

- **A connecting overlay, instead of a black screen.** The page loads
  twenty-eight scripts and then fetches the catalogue, your preferences and
  the registry before the first view has anything to draw — and until all of
  that landed there was a dark rectangle, correctly themed and
  indistinguishable from a crash. The overlay is in the markup above the
  stylesheet, so it paints on the browser's first pass rather than after
  `app.css` arrives, and it names the step it is on. If a step outlasts four
  seconds it says which request it is waiting for, because "connecting" with
  no subject is also what a hung program says. Three separate things remove
  it, including a hard timeout: an overlay that can outlive a failure is
  worse than the black screen it replaced.
- **Skeleton loaders**, in the sessions tree, the event bank and Results.
  Placed by the measured request times rather than sprinkled about — a
  skeleton in front of an 80ms fetch is a flicker. Reading the catalogue
  takes about five seconds here, and for all of it that view was an empty
  box, which reads as "no sessions": a wrong answer rather than a slow one.
  They only appear when there is nothing on screen yet, so refreshing a list
  never blanks it, and they are cleared in a `finally` so a failed read
  cannot leave the bones behind.
- **The Menu button shows which of its three positions it is in.** It cycles
  full → icons → hidden, and the only thing that ever said so was a tooltip
  that changed after you had already clicked, so the second click — the one
  that hides the bar completely — was a surprise every time. Three pips on
  the button, a tooltip naming the whole cycle rather than the next step, and
  a one-line hint that retires itself once you have been round once.
- **The collapses move.** The rail, the log dock, the radio, tree sections,
  modals and popovers, all on one duration so they read as the same
  interface. Motion is dropped entirely for anyone whose system asks for
  less of it — but the skeletons keep their shape, because asking for less
  motion is not asking for less information.

### Changed

- The radio's third station is no longer Asian lofi. It is now ten hours of
  a mouse eating M&Ms, which in a program whose every other window is a
  mouse seems only right.

### Notes for later

Three ways of animating a collapse were tried before one worked, and the
failures are worth remembering, because each looked correct:

- Transitioning **`grid-template-columns`** seemed ideal — one property
  governing the rail and the workspace together. Measured, it did something
  far worse than jumping: the rail stayed at 190px in *every* state. The
  transition was not decorating the collapse, it was preventing it. It now
  animates `--rail`, registered with `@property` so a length is being
  interpolated; if that animation cannot run the value still changes, so the
  worst case is an instant collapse rather than none.
- Dropping `display: none` from the hidden state was necessary, and left an
  invisible 838px rail auto-placed into the workspace column. Pinning it to
  `grid-column: 1` got that to 20px, and no combination of `min-width: 0` and
  `width: 0` got it below: a grid item will not shrink past its own content.
  It slides out and *then* leaves the layout.
- The same 15px floor caught the radio dock, where `display: none` is not
  available — it holds the player, and nothing that risks detaching a
  playing iframe is acceptable. That one measures its own height instead.

---

## 2026.09.08.4 — the Marks list, and marks really meaning all of them

### Fixed

- **Deleting a bookmark stacked another Marks dialog on the open one.** The
  close X then peeled them off one at a time, each revealing a list that
  still held the bookmark just deleted — so closing the list looked like it
  was undoing the delete. The dialog already knew how to redraw its list in
  place; deleting was reopening the whole thing instead. Third place this
  same fault has turned up, after the figure builder and the event import,
  so the guard that stops a redraw ever stacking is on this one too.
- **A delete took three seconds to show anything, so it got pressed four
  times.** Four requests went out for one bookmark, each queued behind the
  last and slower than it — 2.7s, then 3.5s, 4.8s, 6.6s. The row now goes at
  the click and comes back if the server refuses, and a repeat while one is
  already in flight sends nothing.
- **Fading and hiding marks now reaches the dentate-spike marks.** They were
  deliberately exempt, on the reasoning that while you are deciding
  candidates the candidates are the job rather than an annotation over it.
  That was the wrong call: a setting that quietly spares the one kind you
  were looking at is worse than one that does nothing. The pane header still
  says the marks are faded or hidden, so it is never a mystery.
- **The radio would not play — "Error 153".** It was carrying
  `referrerpolicy="no-referrer"`, a `sandbox`, and an `origin` parameter, all
  added as privacy hardening. YouTube's embed validates the page it is
  embedded in from the referrer, so suppressing the referrer suppressed the
  thing it checks. None of the three bought anything real: a cross-origin
  iframe cannot touch the page whatever the sandbox says, and the referrer it
  sends is `127.0.0.1`. The dock also now has a way out to YouTube, because
  an embed failure is a bare number and "153" is not something anybody
  should have to look up.
- Two of the four radio stations were the same stream under different names,
  and one labelled Jazz was playing lofi. Three stations now, each named
  after what it actually plays.

---

## 2026.09.08.3 — display options, sync, and a radio

### The More tab

- **Unchecked channels: remove, or keep them greyed out.** Unchecking used
  to drop a channel from the request, so it was never read and never drawn —
  right when you want it gone, wrong when you want to see what you are
  leaving out. The greyed-out option reaches the rasters as well as the
  traces, because the row is really in the image: the client asks for every
  channel and names the unselected ones, and the renderer draws those at
  reduced alpha, the same mechanism a bad channel already used.
- **Marks — bookmarks, events, spikes — can be faded or hidden.** With a
  standing notice in the pane header while they are, because a mark you
  cannot see is indistinguishable from a mark that is not there, and that is
  how somebody concludes a recording has no events in it. Nothing is deleted
  and the counts do not change.

Both are facts about the recording rather than the pane, so both ride the
same broadcast as invert and even-only — every pane and every window showing
it agrees — and both are saved with the session.

### Syncing

- **Errors travel by Supabase, not by git.** They were append-only JSONL per
  machine per day, committed to the repo, and that commit was the only way
  one machine's errors reached another — so a colleague's crash was invisible
  until somebody remembered to commit and somebody else remembered to pull.
  The files stay on disk as the offline buffer; they are cache now, not
  transport, and the directory is gitignored.
- **Feedback, the roster and error triage come back down.** They were pushed
  and never pulled, which is half a sync and the half that looks like it is
  working. A report filed on the rig reached Supabase and stopped there.
- A pulled error is filed under the machine that had it, so nothing claims
  somebody else's crash happened here. The raw log stays push-only in the
  other direction for the same reason.

### Added

- **A radio.** Docked bottom-right, collapsible to a bar, and it keeps
  playing while you work — which is the whole point, so minimising hides the
  player rather than removing it. Four stations.

  It is the only part of BARRY that reaches the internet. It is off until
  you turn it on, it asks once per machine and says exactly what will be
  loaded and what will not be sent, and nothing is fetched until you agree —
  a closed radio is not a connection.
- Ctrl+Z in curation, alongside `u`. "Even up the panes" is now labelled a
  reset rather than an undo, which is why Ctrl+Z was expected to reach it.

---

## 2026.09.08.2 — undo in the figure builder

### One control strip for many panes

A six-pane probe layout carried six copies of the control strip, each
squeezed into a third of the width — and every one of them set the same
things. The window, the filter, the gain, the colour limits and the channel
set all belong to the recording, not to the pane.

So when every occupied pane is a view of the same recording in the same kind
of panel, there is now one strip above the grid, full width, and each pane
keeps only what is its own: which recording, which probe column, and its own
window read-out.

Two panes showing two different recordings still get a strip each — `t0`
means a different thing in each of them, so one strip could not speak for
both.

### Fixed

- **The figure builder's close button behaved like a back button.** Its
  redraw went through the modal stack, so every panel change and every grid
  click pushed another copy of the builder behind it — closing needed one
  press per change you had made. A redraw now replaces rather than stacks.
  `eventimport` had the same fault and is fixed with it.
- The column `+` sat in the header row, which put it above the row handles —
  floating in the top corner beside nothing. It is a full-height button on
  the right edge now, where another column would go.
- The builder sized its grid to the pane count rather than to the panels it
  actually had, so a four-pane layout with one pane filled opened as a 1×2
  grid holding one panel.

### Added

- **Undo in the figure builder**, on a button and on Ctrl+Z, with redo on
  Ctrl+Shift+Z. Hooked in one place — the layout is compared to the last
  snapshot whenever it is redrawn — so dragging a panel, adding a column,
  removing a row and editing a title are all undoable without any of them
  having to know about it. Ctrl+Z inside a text box still means the text.

---

## 2026.09.08.1 — the curation workbench

### Event curation is a workbench, not a table

The list of forty-two sets read as a database: everything at equal weight,
controls that were all query controls, and every row carrying the same five
buttons down to Delete. Nothing said whose work any of it was.

- **The bench** holds the sets you have open, with an owner and when it was
  last picked up. Two verbs on the face of a card — carry on, or put it down
  — and everything administrative folded behind **More**.
- **The shelf** is everything put down, behind a fold. That is the only part
  that is a lookup, and the only part with a search field.
- **Putting a set down costs nothing and requires nothing.** Every decision
  was written the moment it was made; banking is publishing a result, not
  saving work.
- Every set has a **person** on it, taken from whoever actually made the
  decisions.

### New curation set

Importing candidate times into Event curation is gone. Candidates live in the
Event Bank — with the detector that found them and their version history —
and curation now reads a version out of it: pick a recording, pick its banked
entry, pick which version to work from.

Version 0 is the detector's list with nothing decided. A later version
carries the decisions as they stood then, so you can carry on from where
somebody left off or go back to it.

The old importer implied a recording could have several named sets. It cannot
— one per kind — so a second import of the same times added nothing and threw
away the name that had been typed, silently.

### Fixed — things that were losing work

- **A banked set came back undecided.** The bank stores a category as its
  display name ("Garbage") and the set only recognised ids ("garbage"), so
  every decision was dropped on the way back in. One session's 416 decisions
  were lost this way and have been restored from the bank.
- **Re-banking erased the detector.** `source` was rebuilt from the caller on
  every bank after the first, so "ETS dentate-spike export" became "BARRY
  curation". Repaired on the entries it had already hit.
- **Restarting a set doubled it.** Replacing the candidate list minted fresh
  ids for the same times, which reads as a replacement on one machine and as
  new candidates on every other — the merge was their union. A candidate now
  keeps the id its time already has, and a set that had doubled has been
  collapsed with every decision intact.
- **Clearing a field did not stay cleared.** Removing one wrote a tombstone
  that the next unrelated write to the same record dropped, so another
  machine's older value came back. Un-archiving was the visible case; it
  affected any field cleared by removal.
- **8,845 decisions had no author or timestamp**, which meant they lost every
  disagreement on a handoff merge automatically. All of them now say who and
  when, and carry a review row.
- **Bulk labelling kept no review trail**, so a sweep or a restore overwrote
  a colleague's call leaving no trace they had made one.
- **Banking a half-curated set** deleted the candidates nobody had reached
  yet. Version zero now keeps the detector's full list.
- **Feedback never left the machine it was filed on**, and triaging a report
  filed elsewhere wrote into that machine's file — a guaranteed conflict.
  Triage is now an overlay of your own and merges.

### Versions

An import is **v0**, always: it is the thing curation gets done *to*, not a
round of curation. The first real pass is v1. A set whose sorting happened
before BARRY existed gets a blank v0 and its decisions as v1.

### Archiving

Archiving files a set away and touches nothing else — every candidate and
every decision stays exactly as it is. **Delete is gone** from the view; it
erased every machine's copy of a set and sat at the same weight as Export
CSV. Opening an archived set asks first, so archiving cannot be undone as a
side effect of looking at something.

### Fixed — the interface

- **Curating fast no longer outruns the server.** Each keystroke was firing
  two window-sync posts and a fresh render of all four aid panels; the queue
  reached twenty-five seconds and the decision writes looked broken when they
  were only behind it. The aids now wait for you to stop moving, and a
  superseded panel request is cancelled rather than merely ignored.
- **Banking survives leaving the mode.** Reading the previous versions is a
  round trip, and leaving curation while it was in flight threw an error into
  the console and banked nothing.
- The bank dialog shows the real history and the version it is actually about
  to write.
- Switching probe keeps the panel you were looking at instead of forcing a
  CSD, and changing a panel type in a six-column layout changes all six.
- The Event Bank list keeps its place when you pick an entry.
- The Errors count updates without opening Errors, and sits beside the word
  rather than after the shortcut key.
- The workbench is current when you come back to it.
- Picking up and putting down happen on the click, not after the round trip.

### The figure builder

Rows, columns and the page size were number boxes beside a picture of the
grid. The picture is the thing worth manipulating.

- **The grid is built on the grid.** A `+` on an edge adds a row or a
  column; an `x` on each one removes it. Rows, Cols, Width and Height are
  shown rather than typed — the page size follows the preset, and a second
  way to set it is a second thing that can disagree.
- **Panels are dragged in.** A palette of kinds below the grid, dropped into
  the cell they should occupy. Dragging a filled cell moves that panel. The
  dropdown put a panel in the first free cell, so you found out where it had
  gone afterwards and moved it.
- **It opens on what is actually in view.** It claimed to seed from the panes
  on screen and then discarded the arrangement: four at most, the first alone
  on the top row and the rest beneath it. A six-pane probe view arrived as
  four panels in the wrong places.
- Removing a column takes the panels that were only in it, shrinks the ones
  that spanned it and shifts the rest left, rather than decrementing a number
  and letting a clamp sort it out.
- **The rebuild dialog docks into a corner** while it works, and stops
  swallowing clicks. It narrates a recording opening and a window moving,
  behind a backdrop that covered exactly that.

### Added

- **Bookmarks carry a colour**, chosen when the bookmark is placed and
  changeable from the Marks list. Eight bookmarks in one accent were eight
  identical flags.
- **Profiles** offer the people already on record: click a name to credit
  this machine's work to them, or the pencil to fill in their details without
  becoming them.
- Assigning a curation set picks from that same roster instead of a text box,
  which is how one person becomes three.
- These patch notes, and the version in the rail.
