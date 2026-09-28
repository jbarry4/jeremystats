# Root Canal — build spec and API contract

Step 4 of The Dentist. X-ray moves to step 5.

    Incisor (find them) → Checkup (clean them) → Braces (line them up)
      → Root Canal (take the IEDs out) → X-ray (tell them apart)

## What it is for

Incisor's "dentate spikes" hide IEDs. Checkup and Braces don't take them out,
because nothing in those steps looks for them. Root Canal takes Braces' aligned
DS set for ONE recording and measures three things per event. It then runs a
2-class k-means in that 3D space and splits the set into dentate spikes and
hidden IEDs. X-ray then works on clean DSs.

Test recording: **PTEN m13 s2 2023-08-01**, bank entry `46fd29a77cc7`,
gid `s38b9e61c5684`, 296 aligned DS, readable on this machine
(`D:\PTEN\PTEN\M13_pten\HF4s2aug1\2023-08-01_12-11-26`). This is the recording
the lab's own scripts in `C:\Users\Z390\Desktop\jeremystats\FOOOF Playgroun\IED and such`
(`ied_ampwidth_gui_v5.py`, `ied_ds_features.py`, `ied_ds_lit.py`, `ied_ampwidth.py`)
were developed on. Their docstrings are the method source. Read them.

## The three axes (decided with the user; do not change)

1. **Max amplitude (µV)** — on the MAX-AMP CONTACT: per event, the contact
   with the largest `|x − baseline|` inside ±`win_ms` of the stamp, over the
   good contacts. This is v4's rule (`ied_ds_features.winning_contact`). The
   amplitude and its polarity are measured on that contact using v1's
   `measure_peak` logic (`ied_ampwidth.py`): the baseline is a real baseline,
   not zero, and the larger of the max/min polarities is taken.
2. **Half-width (ms)** — the full width at half amplitude, measured from the
   baseline on the SAME contact. Linear-interpolated crossings. If a crossing
   is never found, return `unresolved` (NaN) rather than silently using the
   window edge.
   - Filter for 1 and 2: **1–100 Hz zero-phase by default, ADJUSTABLE**
     (low and high corner). It's a FIT param, so changing it must NOT re-read
     the recording.
3. **HF power (dB)** — v5's measure exactly (`backend/dspcahf.py` already
   implements it): Welch PSD, band integrated by trapezoid, event window ±25 ms
   about the stamp, baseline ±20 ms centred 150 ms before, on the same contact,
   10·log10(event/baseline). Per event it's the **best contact's dB**: the
   nanmax across contacts, which is v5's `best_db` rule. **The band is ADJUSTABLE**
   (default 500–1000 Hz). This is a deliberate departure from v5's fixed band,
   because the user asked for it. So the band must be recorded with every
   result, and the axis label must show it. Max band edge = the read's Nyquist
   (2500 Hz at a 5 kHz read).

**Scaling:** each axis is z-scored per recording (mean 0, SD 1) before k-means.
NaN rows (unresolved half-width, missed HF) are left out of clustering and
shown as hollow "not measured" points. They are never silently imputed.

**Clustering:** k-means, k = 2, fixed `random_state`, `n_init` ≥ 10, on the 3
z-scored axes. **Naming rule:** the cluster whose centre has the higher mean
HF power (in dB, unscaled) is **IED**. Report the rule and both centres'
values, so the panel can say why.

**Overrides:**
- Flip one event's class by hand (DS ↔ IED).
- Drag either cluster centre (in any 2D projection). Every event is then
  re-assigned to the nearest centre in z-space, and the dragged centre sticks
  until reset.
Flips are stored as a list of event indices, centres as z-space coordinates.
Both are FIT params, so a result can be rebuilt from params alone.

## Read vs fit (the cache split every Jarvis tool uses)

READ (minutes, runs as a `cfc` job, cached, stoppable via `job.check`):
read the recording ONCE per event at **5 kHz** (`incisor.decimation_for`,
`incisor._decimate`, `csc._read_channel_window`, as `dspcahf.measure` does).
For every event and every contact, keep:
- a waveform snippet, decimated further to **2 kHz**, ±250 ms around the
  stamp (so any filter up to ~400 Hz lowpass can be applied at fit time).
  Store as float16 or int16 µV to keep it ~100 MB or less for 700 events × 64 ch.
- the event-window PSD and the baseline-window PSD (Welch at 5 kHz, v5
  windows), so any band ≤ 2500 Hz is instant at fit time.
Cache the read with the same machinery X-ray uses (`toolresults.ToolResults`,
`cfcmod.cache_get/put`, an npz next to `DSPCA`'s). Key it on the READ params
only: entry, source version, stamps hash, rate, window. **Measure** (don't
assume) that amp/hw from the ±250 ms snippet filtered 1–100 Hz agree with the
same measure on a longer continuous read for a handful of real events, and
write the numbers into the module docstring. A 1 Hz high-pass can't mean the
same thing on 500 ms as on continuous data. Say how big the difference is.

FIT (fast, no read): filter → max contact → amp/hw; band → HF dB; z-score;
k-means; naming; overrides. Returns every event's three raw values, three z
values, cluster, class, whether it's hand-flipped, and its max contact.

## Backend API (agent A builds; agent B codes against exactly this)

All JSON, all under `/api/rootcanal/`. Errors come back as
`{"ok": false, "error": "<sentence a person can act on>"}` with a 400, using
the existing `fail()` helper.

- `GET /api/rootcanal/candidates` →
  `{"ok": true, "sets": [{"entry_id", "session_label", "gid", "project",
  "mouse", "session", "n", "aligned": bool, "readable": bool, "why_not":
  str|null, "versions": [named version rows, via named_versions()],
  "rootcanal": {"done": bool, "ied_entry": id|null, "version": label|null}}]}`
  Offers DS sets that Braces has aligned (`aligned` truthy). Anything else
  gets `readable: false` and a `why_not` ("Braces hasn't aligned this set
  yet"), mirroring `/api/dspca/candidates`.
- `POST /api/rootcanal/read` body `{entry_id, from_version}` →
  `{"ok": true, "cached": bool, "job": snapshot|null, "read": hash, "n": int}`.
  Poll with the existing `GET /api/cfc/job/<id>`.
- `POST /api/rootcanal/fit` body `{entry_id, from_version, lo_hz, hi_hz,
  win_ms, band_lo, band_hi, flips: [idx], centres: [[z,z,z],[z,z,z]] | null}` →
  ```
  {"ok": true, "n": int, "n_used": int,
   "axes": [{"key":"amp_uV","label":"max amplitude","unit":"µV"},
            {"key":"hw_ms","label":"half-width","unit":"ms"},
            {"key":"hf_db","label":"<lo>–<hi> Hz power","unit":"dB re baseline"}],
   "events": [{"i", "t", "amp_uV", "hw_ms", "hf_db", "z": [a,b,c] | null,
               "cluster": 0|1|null, "cls": "ds"|"ied"|null, "flipped": bool,
               "contact": csc_number, "contact_row": row, "polarity": "max"|"min"}],
   "centres": [{"z":[..], "raw":[..], "cls":"ds"|"ied", "n": int}, x2],
   "rule": "<one sentence: which cluster was called IED and why, with both centres' HF dB>",
   "counts": {"ds": int, "ied": int, "unmeasured": int},
   "params": {...everything needed to rebuild...}}
  ```
- `POST /api/rootcanal/event` body `{...fit body..., "i": idx}` → the click panel:
  ```
  {"ok": true,
   "trace": {"t_ms":[..], "y":[..], "baseline": uV, "peak_ms", "peak_uV",
             "left_ms", "right_ms", "half_uV", "contact", "polarity"},
   "spectrum": {"f":[..], "event":[..], "baseline":[..], "band":[lo,hi]},
   "stack": {"t_ms":[..], "rows":[[..]...], "nums":[..], "bad":[..], "gain"},
   "csd": {"t_ms":[..], "rows":[[..]...], "clim":[lo,hi]}}
  ```
  Downsample for display (≤ 400 points in time). The CSD is a 1–100 Hz (the
  fit filter) CSD down the probe using `dspca.spacing_for`/`dspca.geometry`
  and `dspca.stack_csd` or `standard_csd`. Arrays only; **the backend never
  draws** (no matplotlib, the same rule as `dspca.py`).
- `POST /api/rootcanal/commit` body `{...fit body..., "note": str, "pngs":
  {"space": dataURL, "flat": dataURL}}` → banks:
  1. **DS set vN+1**: `EventBank.add` with the SAME entry id and the events of
     the DS class only, keeping each event's existing fields (`start`, `end`,
     `from_t`, `label`, `label_id`, `channel`, `amplitude`). `version_note`
     says how many were removed and the rule. `version_tag: "rootcanal"`.
     `aligned` is carried.
  2. **IED entry**: `type: "ied"`, `name: "Hidden IEDs (Root Canal)"`,
     `curated: False` (a classifier said this, not a person, so they
     arrive as candidates Checkup's `ied` kind can curate). Link back in
     `parameters`: `from_entry`, `from_version`, the fit params, which ones
     were hand-flipped. If this DS entry already has a Root Canal IED entry,
     bank a NEW VERSION of that one rather than a second entry.
  3. The numbers and the figures filed to the results bank the way X-ray's
     commit files them (`DSPCA.put`-style vault `ROOTCANAL`; PNGs gated by the
     `_png_bytes`/`PNG_MAGIC` check), and linked onto the version.
  Returns `{"ok": true, "ds_entry", "ds_version", "ied_entry", "ied_version",
  "removed": int, "kept": int}`.
- `GET|POST /api/rootcanal/batch/plan` and `POST /api/rootcanal/batch` — same
  shape and behaviour as X-ray's batch (`/api/dspca/batch*`). The batch runs
  the READ for every ready set in the background, per-member progress via
  `members_init`/`member`/`tick`. Each set becomes openable as soon as it's
  done. Stop lands mid-recording (pass `stop=job.check` into the read, and
  re-raise `Canceled`).

### eventbank.py change (agent A)
`EventBank.add` accepts an optional `version_tag` (short string) and stores
it on the new version row as `"tag"`. `named_versions()` must pass it through.

## Frontend (agent B builds)

`web/js/rootcanal.js`, registered like `dspca.js` (`BARRY.rootcanal.paint`,
wired in `toolkit.js` where `dspca` is: see lines ~140, ~247, ~280 and ~3011
of `web/js/toolkit.js`). Add the step to the Dentist list:

    ['incisor','Incisor','find them'], ['curate','Checkup','clean them'],
    ['braces','Braces','line them up'], ['rootcanal','Root Canal','take the IEDs out'],
    ['dspca','X-ray','tell them apart']

Everything moves along by one. Update any harness or check that counts Dentist
steps (it's four today and will be five).

Layout and behaviour follow X-ray, and `web/GUI-CONSTITUTION.md` is binding
(read ALL of it first). `BARRY.ui.*` builders, tokens only, no literal colours,
no `.btn.small`, no `.primary`, no bespoke spinners, right-aligned actions with
the primary last, never truncate text (shrink or reflow instead).

- **Set picker:** type-out + version radio, like X-ray's.
- **Controls, compact and horizontal:** filter lo/hi (Hz), amp window (ms),
  HF band lo/hi (Hz, capped at 2500), a "Recompute" that's deferred like
  X-ray's (no refit on every keystroke), and "reset centres" / "clear flips".
- **The 3D space:** hand-built on `<canvas>`, no library. Orthographic
  projection of the 3 z-scored axes; drag to rotate, wheel to zoom,
  double-click to reset the view. Draw the axes with their labels, the IED
  and DS colours from tokens, the two centres as larger marks, hand-flipped
  events ringed, and unmeasured events hollow. Click a dot to pick it: pick
  in screen space, nearest within ~6 px, with depth-sorted drawing so the
  front dot wins. Sharp on HiDPI (devicePixelRatio, the way X-ray's `sized()`
  does it).
- **Three flat views beside it:** amp×hw, amp×power, hw×power (raw units on
  the axes, with labels and units). Clicking is exact here. **Drag a centre**
  in any of them to move it (this is the override). Labels on every axis,
  every state — the HF axis always says `<lo>–<hi> Hz power · dB re baseline`.
- **Mode chips on titles**, as in X-ray, showing the band and filter the
  picture was computed with. A chip goes stale-looking when the controls have
  changed but Recompute hasn't been pressed.
- **The "why" line:** the naming rule sentence from `fit.rule`, with the
  counts.
- **Click panel** for the picked event (below or beside the space; no
  scrolling traps, nothing cut off):
  1. max-amp contact trace, with the baseline, the peak, the half-amplitude
     level and the half-width span drawn;
  2. spectrum: event PSD vs baseline PSD, log-power, with the band shaded;
  3. stacked traces + CSD, with the max contact highlighted;
  4. a **DS / IED toggle** for this event (the flip);
  5. **"Open in Xplorefinder"**: pops a NEW WINDOW, the way X-ray's does
     (`window.open` + `barryXplore` + `setChannelLines`; see how `dspca.js`
     does it, and note `BARRY` is a const, not a window property). It stays
     synced as you step through dots.
  Step through events with ←/→, and highlight the picked dot in all four views.
- **Bank:** a button that says what it will do ("Bank: 283 DS as v5, 13 IED
  as a new entry"), posts `/commit` with PNGs of the 3D and flat canvases,
  and reports back what landed.
- **Batch** like X-ray: 1-at-a-time vs batch seg control, a batch list whose
  items become clickable and bankable as they finish, a working Stop, and
  batch progress that doesn't freeze.
- **Loading:** the X-ray-style informative loading line during the read
  (minutes), with no Activity feed flicker (X-ray's feed-preserving render).

**X-ray change:** in X-ray's "Read from" version picker, default to the
newest version with `tag === "rootcanal"` when there is one. Otherwise keep
the current default. Older versions stay pickable.

## Checks (both agents)

Every one of these must pass before you report done. Run them with **PowerShell**;
under Bash, Edge dumps nothing and the whole suite reads clean.
- `python tools/check_js.py`, `python tools/check_classes.py`
- agent A: `tools/check_rootcanal.py` (new). Pure backend: synthetic events
  with known amp/hw/power (a known half-width Gaussian; a 700 Hz burst vs
  noise), k-means naming, flips and centres rebuilding from params, the PNG
  gate, commit producing DS vN+1 + IED entry, idempotent re-commit, and Stop
  landing. Then one real read of `46fd29a77cc7`, with the resulting counts
  reported.
- agent B: `web/_dev/rootcanal.html`, driving the real panel like
  `web/_dev/dspca.html` does (read that harness first; copy its `ev`, `ok`,
  `until`, `head` pattern). Canvas text is checked by spying on `fillText`,
  and point positions through a `_geom()` test export. **Harness pitfalls,
  all hit before:** a heading starting with BAD/FAIL/ERROR counts as a
  failure; a duplicate `const` breaks the whole suite silently; checks placed
  after the try/catch are silent; the virtual-time budget can cut the suite
  short. Run with `python tools/harness_run.py rootcanal` (and
  `python tools/harness_run.py dspca` for the X-ray change).
  **Before ANY harness run, copy `GUI_logs/event_bank` somewhere safe, and
  afterwards check that no bank file was deleted** (`git status --porcelain
  GUI_logs/event_bank`, with ` D` lines meaning deletions). Harness runs have
  deleted real bank records three times. Restore with `git checkout -- <path>`
  or from the copy.
- The harness runner shares the app server with `use_reloader=False`, so a
  backend edit needs a server restart. A server started with Start-Process
  dies when its tool call ends.
- Write patch scripts with the Write tool, never through a shell heredoc
  (backslashes get eaten). Anchors in the source contain real `—`, `…`, `×`,
  `–` characters, not `\u` escapes.
- Another Claude session edits this tree too. Touch only the files named for
  you. **Do not commit.**
