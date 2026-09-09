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
