# BARRY GUI

A local workbench for this repo. Runs every Python and MATLAB script in the
tree, drives the IED pipeline from a folder, browses every recording on a data
share, and includes **Xplorefinder 2.0** — a multi-session trace explorer in the
spirit of `xplorefinder.m`, with a figure builder on the end of it.

It is a small Flask server plus plain HTML/CSS/JS that opens in your browser.
No Electron, no Qt, no tkinter widgets, no build step, no `npm install`. The
browser does the drawing, which is why it stays fast. Nothing leaves the
machine — the server binds to `127.0.0.1` only.

Runs on **Windows and macOS**.

---

## First time on a machine

| | |
|---|---|
| **Windows** | double-click **`Setup Windows.bat`** |
| **macOS** | double-click **`Setup Mac.command`** |

Setup checks your Python, installs the packages BARRY needs, then looks for
MATLAB and ffmpeg and tells you exactly what to do if either is missing. It
never installs anything without asking.

> **macOS gatekeeper:** if double-clicking is refused ("unidentified
> developer"), right-click the file and choose **Open** once.

## Starting it

| | |
|---|---|
| **Windows** | double-click **`Start BARRY GUI.bat`** |
| **macOS** | double-click **`Start BARRY GUI.command`** |
| **Either** | `python start.py` |

It prints what it found and opens `http://127.0.0.1:8733/`. Stop with `Ctrl+C`.

### What's optional

- **MATLAB** — needed only for the MATLAB pipeline stages. Found automatically
  (newest release under `C:\Program Files\MATLAB` or `/Applications`). Without
  it the Python half works and MATLAB stages are grayed out.
- **ffmpeg** — needed only to play `VT1.mpg` session video. Neuralynx video is
  MPEG-1, which no browser can decode, so BARRY transcodes a few seconds at a
  time. Everything else works without it, and the video pane says plainly when
  it is missing rather than sitting on a spinner.

---

## Anywhere in the app

| | |
|---|---|
| **`ctrl`/`cmd` + `K`** | command palette — jump to a view, open a session, run any of the 420 scripts, export a CSV, start a deck |
| **`?`** | the full keyboard sheet |
| **`0`–`9`** | switch section |
| **`T`** | ToolKit — the eleventh section, and there are only ten digits |
| **Guide** | bottom of the rail: guided tours that point at the real thing |

The palette ranks by a subsequence score, so `cscconv` finds
`CSCconverter_LLready_pure.m`, and anything you have starred floats to the top.

## Show me around

Everything in BARRY is visible and almost none of it is obvious — which
is the usual problem with an instrument. **Guide**, at the bottom of the rail
(or `ctrl`+`K` and "tour"), runs a guided walkthrough: the screen dims except
for one thing, a box beside it says what that thing is for, and on the steps
worth doing rather than reading you click the thing itself and the tour
follows you.

| Module | |
|---|---|
| **Getting started** | the shape of the place — the rail, the palette, opening a recording, and where your work goes |
| **Reading a recording** | panels, the shared window, filters, bad channels, and what the scale is actually claiming |
| **Finding events** | importing marks, the threshold detector, and the Event Bank |
| **Making a figure** | the builder, the preview, and why every export can be rebuilt |
| **Telling the story** | Storyboard: drawing, arrows, and presenting with zoom |
| **Keeping track** | History, the debug trace, ToolKit, and how GUI_logs syncs |

Nothing is a mock-up: every step points at the live control, and where it
says to click, the real click happens. Escape leaves at any point. Progress is
remembered on that computer only — it is a fact about the person at the
desk, not about the project, so it does not travel through git.

## The eleven views

Press `0`–`9` (or `T` for ToolKit), or click the left rail.

### 1. Pipeline

The IED pipeline, driven by a folder. Two tracks:

**Session** — one recording folder. Each stage writes back into it, so one
stage's output is the next one's input:

| # | Stage | Runs | Needs | Leaves |
|---|-------|------|-------|--------|
| 1 | CSC Conversion | `CSC2LL_uV_mex_disk.m` | `CSC*.ncs` | `*.mat` (µV) |
| 2 | IED Detection | `vacc_ied_detect.m` | `*.mat` | `ets` / `LLspikes` |
| 3 | Event Curation *(optional)* | `TheVisionOverlay.m` | events or `.xlsx` | review images |
| 4 | Session Pipeline | `Pipeline_Main.m` | `*.mat` | `Pipeline Output/` |

**Cohort** — a parent of many processed sessions: grand averages (CSD and
voltage), IPP Take 4, anatomical labeling, stats tables.

Each stage shows **ready**, **needs input**, or **output present**, checked
against what is actually on disk. **Run all stages** walks the track and stops
if a stage fails rather than feeding garbage forward.

**Preflight** asks every question that could make a stage fail ten minutes in,
before it starts: is MATLAB actually there, are the Python imports installed,
is there disk space, is any channel file truncated or empty, do the channels
agree on a sample rate, is the session identifiable. Green, amber or red per
row, and it will not call a run blocked on a warning.

**Batch…** runs the chosen stages across many recordings, one at a time so
MATLAB is never asked to start twice at once. Point it at a parent folder and
it finds the sessions itself, or pull in whatever is ticked in **Sessions**.
Progress is per item, with a link to each one's log.

**Presets** name a set of stage options — "PTEN defaults", "40 µV threshold" —
and store them in `GUI_logs` like every other preset, so the numbers someone
actually used are recoverable instead of remembered. The chosen folder for each
track is remembered across restarts.

### 2. Explorer

All 420 scripts, grouped and searchable. Pick one to see its docstring, its
functions and imports, and its **settings**.

These scripts have no `argparse` — their top-level constants *are* the
interface. Explorer surfaces those as form fields. Change one and BARRY writes a
temporary copy **next to the original** with just that literal rewritten, runs
it, and deletes the copy. The sibling location matters:
`os.path.dirname(__file__)` and every relative path keep resolving exactly as
they do today. **Your source files are never modified.**

- **Favourites** — star the six scripts you actually use and they get their own
  section at the top of a 420-script tree. Kept in `GUI_logs`, so they follow
  you to the next machine rather than the browser.
- **Find in file** — the source viewer numbers its lines and highlights
  matches, for when you want the line number to quote.
- **Settings presets and Copy command** — name a set of overrides and reuse it;
  or copy the exact command line that reproduces the run outside BARRY
  entirely, with the constants to change spelled out.

### 3. Xplorefinder 2.0

Several sessions open at once as tabs, shown through **1, 2 or 4 panes**. View
state lives on the *session*, so two panes onto the same recording — traces
above, CSD below — share one time window for free. **Link time** extends that
across different sessions, for baseline-vs-CNO comparison. Any pane pops out
into its own window.

Each pane shows one of:

| Pane | What it is |
|---|---|
| Voltage traces | stacked waveforms, drawn as vectors in the browser |
| Voltage raster | channels × time heatmap, as `VoltageRaster.m` |
| CSD raster | current source density, as `myCSDPP2.m` (with `interp2` upsampling) |
| Theta raster | 4–12 Hz band |
| Spectrogram | single-channel STFT |
| Scalogram | single-channel Morlet CWT |
| Video | session video, synced to the cursor |
| Position tracking | `VT1.nvt` path, scrubbing with the cursor |

**The control strip.** What is on it is what you touch while looking at the
trace: the window, the move and zoom buttons, the amplitude scale, the gain.
Everything else sits behind a button that carries its own current value —
`Filter 1–70 Hz +60`, `Ch 30/32`, `Panel 20–1000`, `Marks 4` — so the strip
still states the setting without spending a strip's worth of width on it.
Click one to open it. Nothing is hidden: the settings are one click away and
the button says what they are.

`More` holds the things you set once per recording: the event actions
(classes, import, export), the threshold spike detector, the read options
(invert polarity, even channels only), jump-to-start and jump-to-end, and
Reveal / Figure builder.

| | |
|---|---|
| Pan | drag, arrow keys, jump buttons |
| Zoom time | wheel, `-`/`=`, zoom buttons |
| Zoom amplitude | shift+wheel, up/down arrows |
| Jump anywhere | click or drag the timeline strip |
| Mark an event | **alt-click** on the traces |
| Place a bookmark | **+ add**, then click the exact spot |
| Next / previous event | `n` / `p`, or the `‹ 2 ›` control in the pane header |
| Measure | `m`, then drag across a trace |
| Bookmark this window | `b` |
| Start / end of recording | `home` / `end` |
| Filters | high-pass, low-pass, notch (zero-phase Butterworth); `0` disables |
| Colormaps | jet (lab standard) plus 12 others, per pane |

Any window size stays responsive because the server sends a **min/max envelope**
sized to the canvas — two points per pixel column preserving the true extremes.
A spike is never lost to subsampling.

Three things make the long views usable:

- **Marks** puts bookmarks, imported events, committed spike sets and an
  uncommitted draft in one list, sorted by time, with per-kind filters and a
  search. Click any row to jump to it. They are three different things with
  one thing in common — a time in this recording worth going back to — and
  keeping them in separate panels meant knowing which kind you were after
  before you could look for it.
- **Bookmarks are placed, not assumed.** "+ add" arms placement; a faint rule
  then follows the pointer showing the time it would land on, and a click puts
  it there. Escape backs out.
- **The scale is the control.** The color scale and the trace amplitude are a
  log slider and a number box sitting in the strip with everything else —
  drag for the rough value, type for the exact one, and a button toggles
  between pinned and per-window. It used to be a button that opened a popover,
  with the value it set displayed somewhere else entirely.
- **The event navigator** steps through everything navigable in the session —
  imported events, committed spike sets, bookmarks — in time order, respecting
  the class filters, and centers the window on each. `n` and `p`, no mouse.
- **The measure tool** reports Δt in milliseconds, the equivalent rate in Hz,
  and the amplitude difference between the two endpoints on the channel under
  the cursor. The readout stays put after you let go, so the number can be
  written down.
- **The overview strip** carries the recording's own amplitude profile behind
  the event and bookmark marks — a min/max envelope plus an RMS line, built
  from one channel at a coarse stride. A seizure, a cable knock or a flat
  stretch is visible at a glance, so it is a map rather than a position
  indicator.

Every raster carries thin time and channel rules with the channel labels
written along them, on an overlay canvas so they stay crisp at any pane size
and never get baked into an export. (`web/_dev/grid.html` checks they are
actually drawn: 31 channel rules for 32 channels, on all three raster types.)

The channel rows are a CSS grid of equal fractions with the same top and bottom
insets the canvas draws with, so a row's center is the same fraction of the
plot area as its trace's midline — at any pane height, and without waiting for
a redraw. (`web/_dev/align.html` measures this: 0.00 px error on all 32 rows,
before and after a resize.)

### 4. Sessions

Point it at a data root (`D:\PTEN\PTEN`, a netfiles share) and it walks the tree
and lists every recording, grouped **cohort → mouse → session**, with channel
count, duration, and flags for video, tracking, converted `.mat` and remembered
bad channels. Click one to open it in Xplorefinder.

The scan is depth-limited and prunes at the first recognized recording, and
reads only one 16 KB header per session, so it stays usable over a share.

- **Health check** validates a recording the way a person would before
  analysing it: channel gaps, truncated or empty files, a byte count that ends
  mid-record, channels that disagree on sample rate, missing video / tracking /
  events, and whether the session is identifiable at all. The deep check reads
  a slice from every channel and flags flat, clipped and very noisy ones.
- **Quality flags and notes** — good / review / exclude, plus free text, keyed
  on session identity so they survive a re-mount or a rename exactly as bad
  channels do. Which recordings are in the analysis stops being a fact that
  lives only in someone's notebook.
- **Compare and export** — a side-by-side table of any selection with the
  differing rows highlighted, and a CSV of the lot. That is the table that goes
  into a methods section, built from what is on screen instead of retyped.

### 5. History

Every run BARRY has made, pooled from `GUI_logs` — what ran, with which
parameters, against which session, by whom, on which machine, how it ended, and
the tail of its output. Figure exports are recorded too, with their panel list.

The **Activity** tab is the other half: every filter change, colormap pick,
raster switch, channel change, event import, measurement, download and
bookmark, with the machine it happened on.

- **Timeline** — one stacked bar per day, colored by what kind of thing
  happened. Click a bar to filter the list to that day. Logging everything is
  only useful if you can see the shape of it.
- **Replay** — a history entry already holds the script, the language and every
  parameter. Replay puts them back: the pipeline pointed at the same folder,
  the Explorer loaded with the same script, or the viewer reopened at the same
  window and filters.
- **Export CSV** — runs or activity, as a table.

### 6. Errors

Everything that failed, with the command, the working directory, the context
and the full traceback. Written to `GUI_logs/errors/` as one JSONL file per
day. Front-end exceptions land here too, rather than failing silently.

- **Grouped** — the same failure logged forty times is one problem, not forty.
  Groups fold on a signature that ignores paths, timestamps and numbers, and
  show a count, the machines it happened on, and first/last seen.
- **Triage** — marking a group resolved clears every past repeat and any future
  one that matches, with a note on what fixed it. The rail badge counts what is
  still open, so it is a number that can go down.
- **Diagnostic bundle** — one block of text with the machine, the Python and
  MATLAB versions, ffmpeg, the user, and the last few tracebacks in full.
  Copy, paste into a message, done.

Nothing is ever deleted from the error log. It is append-only JSONL, one file
per day, and resolving a group marks it rather than removing it — resolved
entries stay on screen, dimmed, with a tick.

### The debug trace

Some bugs raise nothing at all: a panel comes back blank, a click does
nothing, a number is quietly wrong. There is no error to look at, but there is
a sequence of commands. The **Debug trace** tab records it:

| | |
|---|---|
| the server side | every API request, its parameters, its status and how long it took |
| the browser side | the same requests as the browser saw them, including any that never arrived |
| the console | warnings and errors, captured without replacing devtools' own output |
| the actions | which controls were used, from the activity log |

**Copy debug report** rolls all four together with the machine, the versions
and the recent errors into one block of text, asks what you were doing, and
files a copy under `Output/Debug/`. That is the thing to paste when something
goes wrong in a way that leaves no trace of itself.

### 0. Event Bank

A detector's output normally ends up as an `ets.mat` beside the recording, on
whichever drive it was run on. Six months later nobody can say which version of
which script produced it, or find it from another machine. The bank is the
answer to that.

Entries are filed by **project → mouse → session → type**, and an entry will
not be accepted unless it can say three things:

| | |
|---|---|
| **who** added it | taken from your git config, editable if you are banking for someone else |
| **when** | stamped automatically, with the machine |
| **what produced it** | the script, the detector or the file. There is no default and no guess — an entry that cannot say where it came from is not evidence |

Times are stored as seconds from the start of that recording, so they only
mean anything against it. Matching uses the same tiering as bad channels —
exact identity, then mouse+session, then mouse alone — so an entry banked on
one machine is found from another where the path is different.

**Getting events in and out** is one **import…** and one **export…** button in
Xplorefinder, each asking where:

- **import…** → from the Event Bank (what is already banked against *this*
  recording, tagged with how well each matches) or from a file.
- **export…** → to the Event Bank or to a CSV on this machine. Either way it
  shows you the events first, everything ticked, and you drop whatever should
  not go — with a **go** button on each row to jump there before deciding, and
  **Only this window** to keep just what is on screen.

From the bank itself, **Load onto a recording…** offers the sessions already
open, flags whether each is actually the one the entry was banked against, and
can open the banked path directly.

One JSON file per entry in `GUI_logs/event_bank/`, so two people banking at
once merge without conflict.

### T. ToolKit

The jobs that are about the whole pile rather than one recording. A tool list
on the left, the chosen tool on the right.

**Bad-channel export.** A bad channel matters twice: now, because it has to
come out of the average, and later, because the next person has to know it
came out. Pick the scope —

| Scope | |
|---|---|
| Everything | every session BARRY has a record of |
| One session | picked from a list that shows how many are marked on each |
| One mouse | every session for that animal |
| One project | every session in it |
| A date range | by recording date, bounded by the dates that actually exist |

— then choose the shape: **one row per channel** (long form, which a
spreadsheet can pivot and a script can filter) or **one row per session**
(channels listed in a cell, easier to read). *Include sessions with nothing
marked* adds the zero rows, which are the only way to tell a session that was
checked and found clean from one nobody has looked at.

The rows and the counts are shown before anything is downloaded, including
which channel numbers came up in **more than one session** — a recurring
number is usually a wire, not a recording, and that is worth checking at the
headstage rather than in the analysis.

The CSV opens with a comment line naming the scope, the row count and the
date it was taken, so a file found months later still says what it was a list
of. Every export is filed under `Results/ToolKit/` as well as downloaded, and
recorded in History with its scope and counts.

Nothing here reads data off disk — it reads the record of what was decided,
which lives in `GUI_logs/sessions/`.

### 7. Misc

Loose scripts, notebooks, archived scripts, and utilities: re-index, sweep
stray temp files, environment summary.

- **Search the repo** — grep every `.py`, `.m`, `.ipynb`, `.csv` and `.prb` in
  the tree, in-process so it behaves the same on macOS. Click a hit to open
  that file in the Explorer. "Where else do we compute the CSD?" has an answer.
- **Scratch runner** — the "just check one thing" script. Runs as a normal job,
  so its output goes to the log dock and its run is recorded like any other,
  with the repo and BARRY's own readers already importable and `numpy` bound.
  Snippets can be named and saved; the draft survives a reload.
- **Housekeeping** — finds `__pycache__` folders, stray `.pyc`, `.DS_Store`,
  `Thumbs.db`, zero-byte exports (an export that died mid-write) and the
  largest files in the repo. Deletion is deliberately narrow: only names that
  are unambiguously build clutter, only inside the repo, and only after the
  list has been shown.

### 8. Results

Everything BARRY saves, cataloged automatically. Nothing is filed by hand:
figures from the builder, single-window exports, deck exports, manifest CSVs,
and any image or table a pipeline stage drops into a session folder. The
catalog is rebuilt by scanning, so a colleague's committed figure appears
after a `git pull`.

Each result keeps its provenance — who made it, on which machine, from which
session, with which run id — and can be given a title, tags and notes, starred,
previewed full size, revealed on disk, or dropped onto a storyboard slide.

- **Compare** — two or more results side by side at full width, with their
  captions. The comparison people otherwise make by opening two image viewers.
- **Bulk actions** — tag, star, untag or delete many at once, and export a
  manifest CSV of the selection. Tagging thirty figures one dialog at a time is
  why nobody tags figures. Deletion only ever touches the `Output` folder.
- **Smart collections** — name a filter set. "Figure 3 candidates" is a search,
  not a folder, so a newly exported figure joins it on its own.

`ctrl`+`A` selects everything shown; `esc` clears.

### 9. Storyboard

A slide deck built from your results. Drag results into a sequence, draw on
them, add text boxes, highlight, and write the notes underneath. The slide rail
on the left reorders by drag and shows a live miniature of each slide.

| | |
|---|---|
| Tools | select, text, rectangle, ellipse, arrow, line, highlight, freehand |
| Tools stay selected | draw three arrows without picking the arrow three times; `esc` returns to Select |
| Add a result | from the Results view, or **Browse results** in the inspector |
| Add an image | `ctrl`+`V` pastes from the clipboard |
| Undo / redo | `ctrl`+`Z` and `ctrl`+`shift`+`Z` (or `ctrl`+`Y`), 60 deep, with buttons in the deck bar |
| Save | `ctrl`+`S`, and an autosave 2.5 s after any edit |
| Export | multi-page PDF, or one PNG per slide — filed into `Output/Storyboards/` and cataloged |

- **Lines and arrows go where you drew them.** A line runs from where the
  drag started to where it ended, in any of the eight directions, and an
  arrowhead lands on the end you finished at. Selecting one gives you its two
  **ends** to drag rather than the corners of a box it happens to fit inside;
  hold `shift` while dragging an end to snap the angle to 15°. **Swap ends**
  reverses it, **Flip across** mirrors it.
- **Everything else rotates.** A grip above the selection, where PowerPoint
  puts it; drag it to spin the shape about its own center, `shift` to snap to
  15°, or type an exact angle in the inspector. Rotation is honored in the
  PDF and PNG export, not just on screen.
- **Colors** — a row of swatches for the usual cases and a color picker
  beside it for matching one already in a figure. Same for the slide
  background.
- **Slide order** — drag a thumbnail in the rail, or use the ▲▼ buttons on it;
  the numbering follows.
- **Layouts** — title, section, 1 panel, 2 across, 2 stacked, 4 up, big + notes,
  quote. Drops exact frames and fills them from the selected results in order;
  empty frames stay as visible targets to drop something into later.
- **Presenter mode** — `F5`. Full screen, arrow keys, speaker notes below, and
  the same fractional geometry the export uses, so what is on screen is what
  lands in the PDF.
- **Zoom, mid-sentence.** Scroll to zoom about the pointer, drag to move
  around, double-click to jump in on what you double-clicked, `0` for the
  whole slide again — or `+` / `−` and the buttons in the bar. Once
  zoomed, the up and down arrows pan instead of changing slide. The point is
  to be able to point at one channel of a raster during a talk without having
  made a second zoomed slide in advance. Changing slide always comes up whole,
  so you never land on the next one showing a corner of itself.
- **Align, distribute, order and snap** — flush and center against the slide,
  match another item's width or height, space everything evenly, bring to
  front, `ctrl`+`D` to duplicate. Dragging snaps to the slide's own edges and
  centers and to any other item's, with a guide line, within a few pixels only,
  so it never fights your hand.

---

## Session identity — how bad channels follow a recording

A path is not an identity: the same session is `D:\PTEN\...` on one machine and
`\\netfiles03.uvm.edu\bigdata_jbarry\...` on another. What *is* stable is the
mouse and session number, which every one of your naming conventions carries,
though never the same way twice:

```
PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26              -> mouse 13, session 2
PTEN\M11_Pten\HF2_s10jul25\2023-07-25_14-40-32           -> mouse 11, session 10
CTL\m21_ptenblind\m21s2jul29\2024-07-29_13-05-17         -> mouse 21, session 2
PTEN_DKO\PTENKDOM48\m48s6cno90feb4\2025-02-04_12-48-12   -> mouse 48, session 6
KCNT1\KCNT1_m0591\KCNT1_m0591_s04_081026\2026-08-10_...  -> mouse 591, session 4
```

Validated against all 65 rows of `IED/01_Session_Inventory/batch_input.csv`:
**64 match**. (The one that doesn't is a data-entry error in that CSV —
`HF4s1aug1` is labeled mouse 2 but sits under `M13_pten`, and every other HF4
row is mouse 13.)

Mouse + session alone is **not unique** — `M5s2bnov16` and `M5s2cnov16` are both
mouse 5 session 2. So the full identity adds the **recording start time, read
from the Neuralynx header**, which lives inside the data file and survives
renaming, moving and re-mounting.

Matching is tiered: **exact** (mouse + session + start), **strong** (mouse +
session, unambiguous), **weak** (ambiguous — nearest start time wins). Mark a
channel bad on one machine and it is found on the next.

Bad channels are stored by **CSC channel number**, not row index, because an
index shifts the moment someone toggles even-only. In a CSD panel a bad channel
is interpolated from its neighbours rather than blanked — a second spatial
derivative would otherwise lose three rows to one bad channel.

---

## Event import

Opens anything your detectors produce, detects the format **and the units**, and
tells you why:

| Source | Detected as |
|---|---|
| `ets.mat` + `ech` | `[onset offset]` in **samples**, channel from the participation matrix |
| Toothy `DS_DF` / `SWR_DF` | `idx` in samples, `ch`, filtered on `is_valid` |
| Curated `.csv` / `.xlsx` | column-matched, units inferred |
| Anything else | pick the columns yourself |

The units question is the one that silently ruins a figure, so it is settled by
evidence: values are checked against the recording's length and sample count,
and non-integer values rule out sample indices. Any mapping can be **saved as a
named preset** and reused.

Filter presets work the same way — six ship built in (LFP, Theta, Spikes, IED,
Ripple, Dentate spike), and you can save your own.

---

## Figure builder

Preview **before** you download. Set the page size, drop panels into a grid,
retitle them, pick colormaps, fill in the metadata block, and see the real
rendered figure. The preview comes from the same matplotlib code that does the
export, so what you see is what you get.

Exports as PNG, PDF or SVG — PDF and SVG are true vectors. The provenance footer
carries who generated it, when, on which machine, from which session, with which
filters and time window, and the **GUI_logs run id** that ties the figure back to
the analysis that produced it.

### Rebuilding a figure

A figure in `Results/` is evidence, and six months later the question is
always the same: which recording, which seconds of it, which channels,
filtered how. Every export writes the **complete layout** onto its run record
— not a summary of it, because a summary is exactly what cannot be rebuilt
from — including the channel selection, the bad channels, the gain, the event
marks and how the session was opened (`invert`, `even_only`).

**Rebuild…** on a figure, in Results or in History, reads that back and checks
it against the machine as it is *now* before doing anything:

| Step | Checked |
|---|---|
| Locate the recording | does the folder still exist; if not, is the same mouse/session/start-time recording on disk somewhere else |
| Read the channel inventory | how many channels, at what rate, how long; are the ones the figure used still there |
| Restore the time window | is it inside the recording, or does it run past the end |
| Restore the filters and gain | — |
| Restore the channel selection | including the bad marks |
| Put the event marks back | — |
| Rebuild the panel grid | are those panel types and colormaps still known |
| Open the figure builder | — |

Every step arrives already marked ok / amber / red, so a drive that is not
mounted is a sentence in the dialog rather than a failure four steps in. Then
it performs them one at a time, each saying what it actually did — *"Opened
PTEN m7 s2 — 32 channels at 30000 Hz"*, *"6 of 32 channels selected; CSC 8
marked bad"* — and stops at a button that hands you the figure builder with
everything filled in. The account of what happened stays on screen; the
builder's notes field records what it was rebuilt from.

A figure exported before recipes were recorded still rebuilds, from the
recording, window and filters that *were* written down — and says plainly
that the channel selection and gain are coming from the session defaults
instead.

---

## GUI_logs — the sync store

Everything BARRY remembers lives in `BARRY GUI/GUI_logs/` as plain JSON:

```
GUI_logs/
  runs/YYYY-MM-DD/<id>.json      one file per run
  event_bank/<entry>.json        banked events, one file per entry
  sessions/<identity>.json       bad channels, quality flag, notes, event
                                 classes, bookmarks, spike sets, view state,
                                 every path this session has been seen at
  activity/YYYY-MM-DD.jsonl      every logged action, one per line
  presets/                       filter, import, layout, pipeline and script
                                 presets
  errors/YYYY-MM-DD.jsonl        one error per line
  errors/resolved.json           which failures are triaged, and by whom
  decks/<id>.json                storyboard decks
  results/curation.json          titles, tags, notes and stars on results
  preferences.json               favourites, smart collections, saved snippets,
                                 where you were last
  scratch/                       snippets the scratch runner has executed
  index.json                     pooled roll-up
```

One file per run and per session is deliberate: **git merges separate files
without conflict**, so two people can both work, both commit, and a pull brings
in both sets. A single shared log would conflict on almost every push.

Reading a few thousand small files for every request would be the one thing
that made this store feel slow with a year of work in it, so the run list is
cached in memory and invalidated by a fingerprint over every run file's own
mtime — which means a colleague's `git pull` is picked up without anyone having
to press anything, including a file that was *overwritten* rather than added.
At 3,000 runs that is a 20-second read once per change instead of once per
request.

BARRY never commits or pushes on its own. The rail chip shows how many files are
uncommitted; to share:

```
git add "BARRY GUI/GUI_logs"
git commit -m "session logs"
git push
```

---

## The Results folder

Everything BARRY exports is filed under `BARRY GUI/Output/`, grouped by
session, with `Storyboards/` and `Manifests/` of their own. It is inside the
repo on purpose: commit it and a figure is viewable on GitHub, next to the code
and the log entry that produced it. **Results** has a **View on GitHub** button
that builds the URL for the current remote and branch.

---

## Speed

The interface is plain canvas and DOM with no framework, so what determines
whether it feels fast is the server. Measured on a 64-channel, 30 kHz, 11-minute
recording on a local disk:

| request | before | after |
|---|---|---|
| 10 s window, 32 channels | 359 ms | **116 ms** |
| 10 s window, 1–70 Hz + 60 Hz notch | 1,088 ms | **182 ms** |
| 10-minute window, 32 channels | 16.2 s | **3.2 s** |
| 10-minute window, filtered | 37.1 s | **2.7 s** |
| whole recording, 32 channels | 16.5 s | **4.7 s** |
| history / errors, 3,000 runs on record | 20 s | **21 ms** |

What changed:

- Only CSD needs every channel in one array — it is a derivative *across*
  channels. Everything else is enveloped a channel at a time, so peak memory
  is one channel's worth rather than 2.3 GB, however far out the view is
  zoomed.
- The display scale came from a 99.5th percentile of every sample in the
  window. It now comes from a strided sample, which is the same estimator to
  well inside a pixel and four orders of magnitude cheaper.
- Filters with every stage at zero used to still promote the array to float64
  and scan it for NaNs before returning it unchanged.
- When a low-pass is set it states outright that nothing above it survives, so
  the filtering is done at a few hundred Hz instead of 30 kHz. A block-mean
  decimation is used rather than a polyphase FIR, whose anti-alias filter grows
  with the factor and convolves at the *input* rate.
- A 1 Hz high-pass and a 60 Hz notch are both subtractive — `x - baseline(x)`
  and `x - hum(x)` — so past a couple of million samples the part being removed
  is measured on a decimated copy and subtracted, leaving the full-rate detail
  untouched. Accurate to 0.05 % RMS for the high-pass and 0.8 % for the notch,
  both far below a pixel, and only used where the exact filter would be slow.
- Every pane's window listeners and its ResizeObserver are now torn down before
  the pane is rebuilt. They were not, and nearly every interaction rebuilds the
  panes, so they accumulated on detached nodes and kept firing on every mouse
  move. Sixty rebuilds leaked 240 listeners; it is now zero
  (`web/_dev/leak.html` measures it).
- The server runs threaded, so a slow window request never blocks the polls
  that keep the rest of the interface live.

---

## Deep links

Handy for a desktop shortcut per recording:

```
http://127.0.0.1:8733/?csc=<path>#xplore
http://127.0.0.1:8733/?csc=<path>&t0=1.94&span=0.16&panel=csd#xplore
http://127.0.0.1:8733/?root=D:\PTEN\PTEN#sessions
http://127.0.0.1:8733/?folder=<path>#pipeline
http://127.0.0.1:8733/?theme=light#explorer
```

---

## Layout

```
BARRY GUI/
  Setup Windows.bat / Setup Mac.command      one-time install
  Start BARRY GUI.bat / .command             launchers
  setup.py  start.py  requirements.txt
  backend/
    app.py          Flask routes (86 of them)
    sysinfo.py      Windows/macOS abstraction
    ids.py          session identity + cross-machine matching
    discovery.py    data-root scanning
    store.py        GUI_logs read/write, with an mtime-stamped run cache
    registry.py     repo script index + introspection
    runner.py       subprocess execution, live logs, AST param override
    nlx.py          pure-Python Neuralynx .ncs, .nvt and .nev readers
    csc.py          session loading, filters, CSD, envelope decimation
    events.py       event import with format + unit autodetection
    analysis.py     the six panel renderers
    compose.py      multi-panel figure composition
    export.py       single-window vector export
    video.py        VT1.mpg transcoding, .nvt tracking
    pipeline.py     the IED pipeline definition
    live.py         cross-window state sync
    eventbank.py    the shared record of detected events
    results.py      the results catalog and deck storage
    storyboard.py   deck rendering to PDF / PNG
    extras.py       session health, recording overview, error grouping,
                    repo grep, housekeeping, CSV
  web/
    index.html  app.css
    js/core.js         shared state, API, routing, log dock
    js/features.js     preferences, command palette, shared dialogs
    js/{pipeline,explorer,xplore,sessions,logs,misc}.js
    js/{eventimport,figure,results,storyboard,eventbank,activity}.js
    _dev/              four harnesses that drive the real UI in an iframe
  Output/                       everything exported, grouped by session
  GUI_logs/                     the sync store
```

### Tests

There is no framework and nothing to install. `web/_dev/` holds four pages
that drive the live interface in an iframe and report what they find — 66
assertions across all nine sections, plus a channel-alignment measurement and a
listener-leak count. See `web/_dev/README.md`.

## Notes

- Drag-and-drop: browsers deliberately hide real filesystem paths from dropped
  files, so a drop asks you to confirm the path. **Browse…** uses a native
  picker and avoids the step.
- Temp run copies are named `_barrygui_tmp_*.py` and deleted when the run ends.
  If a run is killed hard, **Misc → Clean temp run files** sweeps them.
- The repo index is built at startup; hit **Re-index** after adding files.
- `BARRY` is declared with `const` in `core.js`, so it is a lexical global and
  *not* a property of `window`. The devtools console can see it (the console
  evaluates in global scope); anything reaching in from another frame has to go
  through `eval`.
