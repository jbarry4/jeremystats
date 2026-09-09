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

## 2026.09.09.2 — one probe, one panel

### Fixed

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
