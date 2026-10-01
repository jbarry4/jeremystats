# Root Canal — Single | Pooled

Every decision here was made with the user on 2026-10-01. Don't change
any of them. `ROOTCANAL-SPEC.md` still governs the Single view.

## The question this answers

Do dentate spikes and IEDs form **two clear clusters**, or **one
ambiguous spectrum**? Asked across recordings, by mouse and by mouse type,
and with a focus on any single mouse.

## The bar

A bar at the top of Root Canal, under its stepHeader: **Single | Pooled**.
Use a `BARRY.ui.seg` (constitution §2: which control). Single is today's
view, unchanged. Pooled is new. The choice is remembered per viewer
(localStorage, wrapped in try/catch).

## What can join a pool (decided)

**Both kinds**, each marked:
- **Banked singles**: a Root Canal result in the results bank
  (`ROOTCANAL.put(... kind: "classification" ...)` in `api_rootcanal_commit`).
  It already holds every event's `[i, t, amp_uV, hw_ms, hf_db, cls,
  flipped, contact, axes, partial, wide]`, so pooling it reads NO recording.
  Pinned by entry id, `ds_version` and the record's `params_hash`.
- **Unbanked singles**: a Root Canal read cached on this machine, fitted at
  the settings the member is added with. Pinned by entry id, read hash and
  fit params, plus the digest of the rows it produced.
  A pool with any unbanked member says so: a chip on the pool, "N members
  not banked", with a title explaining that the pool can only be rebuilt
  while those reads are on this machine.

Only DS sets that have gone through Braces, i.e. the sets Root Canal already
offers. **Nothing from The Storm** (the IED bundle: Doppler and the rest),
and no hand-sort overlay.

## The arithmetic (decided)

- **Scale: pooled raw units only.** Pool every member's raw amp (µV), hw (ms)
  and hf (dB), then z-score ONCE across the whole pool. No per-recording
  z-score. The panel says why in one line: between-mouse differences in
  size stay visible, impedance and placement included.
- **Clustering: re-cluster AND keep each single's own label.** One k-means,
  k=2, on the pooled z-space. Same `random_state`, `n_init` and naming rule
  as Single: the cluster with the higher mean HF power (raw dB) is IED.
  Partial events (2 axes) are assigned on the axes they have, exactly as in
  Single. Each event keeps `cls_single` (its member's own call, including
  that member's hand flips) beside `cls_pool`.
- **Identity switch, visualised AND quantified.** `switched` = cls_single
  ≠ cls_pool. Report:
  - a 2×2 crosstab (single DS/IED × pooled DS/IED) and the overall switch rate;
  - switch counts and rates per member, per mouse and per mouse type;
  - in the views, a colour mode "switches" (DS→IED, IED→DS, unchanged) and a
    ring on switched dots in every colour mode.
- **Clear vs blur: GMM, 1 vs 2 components, by BIC.** `sklearn.mixture.
  GaussianMixture`, full covariance, fixed random_state, n_init ≥ 5, on the
  complete (3-axis) events in the pooled z-space. Report BIC for k=1 and
  k=2, ΔBIC = BIC1 − BIC2 (positive favours two groups), the 2-component
  weights and means (in raw units), and a one-sentence verdict, phrased on
  the conventional ΔBIC scale: < 2 "no support for two groups", 2–6
  "positive", 6–10 "strong", > 10 "very strong". Say plainly that BIC
  compares Gaussian shapes: a single skewed cloud can earn two components,
  so this is evidence, not proof. ALSO compute the same GMM test on the
  focused mouse alone when a focus is set (`focus` in the body), clearly
  labelled as that mouse's, beside the pool-wide one. The pool-wide one
  always stays on screen.

## Mouse and mouse type (decided: both)

- **Mouse identity = project + mouse number.** Never mouse number alone:
  numbering restarts per project, so m13 exists in PTEN and in KCNT1. Key:
  `"<PROJECT>|m<n>"`. A recording (gid) belongs to one mouse.
- **Mouse type** defaults to the registry's filing: `project` plus
  `cohort` (sessreg's `cohort_of` / the `cohort` field, e.g. PTEN_DKO;
  `wt` where the path says so). The user can override any mouse's type
  in the pool view, as free text with suggestions from the types already
  in use. The overrides are stored in the pool (`mouse_types`) and win
  over the registry.

## Views (decided)

The same 3D canvas and three flat views as Single, built from the SAME
renderer. Refactor `rootcanal.js` so both views call one drawing path;
don't copy it. Plus:
- **Colour by**: pooled call · single call · switches · recording · mouse ·
  mouse type. A legend for each, tokens only. For recording/mouse/type, use
  the categorical token palette, cycling with a shape change after it runs
  out, and say so in the legend.
- **Focus a mouse**: pick a mouse (or a mouse type). Its dots stay bright and
  everything else goes faint (dim the rest). The pool-wide statistics stay,
  and the focused mouse's own GMM line appears beside them.
- **The clear-vs-blur panel**: the GMM verdict sentence, BIC1, BIC2 and ΔBIC,
  the two components' weights and means, plus histograms of each axis and
  of the split axis (the line through the two k-means centres), split by
  pooled call. Histograms are the visual half of the question; draw them
  on canvas with labelled axes in every state.
- **The identity-switch panel**: the crosstab, the overall rate, and a table
  of switch rates per member / per mouse / per type, each row clickable to
  focus it.
- **Click a dot**: open that event the way Single does (/api/rootcanal/event
  with the member's entry, read and params). If that member's read isn't on
  this machine (a banked member read elsewhere), say so in a sentence; don't
  fail silently. Open in Xplorefinder works the same as in Single.

## The pool, labelled and saved as a Jarvis Artifact (decided)

- **Register a new artifact kind** `rootcanal_pool` in `backend/artifacts.py`
  with `register_kind`. Look at how `circuit`, `drift` and `monolith`
  register. A pool is its own subject, so its key is a minted `pool_key`
  (uuid) stored in the subject, not derived from the members, because the
  same members can be pooled twice on purpose. `name` is automatic from the
  contents (e.g. "Root Canal pool · PTEN + KCNT1 · 12 recordings, 9 mice");
  the user's **label is the artifact's `nickname`** and is REQUIRED to save
  (the bank dialog's no-empty-name rule, §6e).
- **Payload: pinned members + every dot.** Members with entry id,
  session_label, gid, project, mouse key, mouse type, banked flag, and their
  pin (ds_version + params_hash for banked; read hash + params + rows digest
  for unbanked); `mouse_types` overrides; the pool params (scale "pooled
  raw", k, random_state, tolerances); every event's raw values, z, cls_pool,
  cls_single, switched, partial, wide, member index; the centres and rule;
  the GMM result; the switch tables. A saved pool must reopen and explore
  with NO recording read.
- **Versions**: saving a pool that already exists, with changed members or
  overrides, adds a version via `Artifacts.add_version`. Byte-identical
  re-saves are confirmations, not versions; artifacts.py already does that.
  `inputs` = the member pins.
- **No write-back** to the Event Bank, ever, from Pooled. Banking stays per
  recording in Single.
- **Shelf**: the Pooled view lists saved pools (`Artifacts.list(kind=
  "rootcanal_pool")`) to reopen, and shows the open one's label, version and
  "unbanked members" chip. Opening one restores members, overrides and focus.
  "Save" names what it will do: "Save as new pool…" / "Save as v3 of
  ‘<label>’".

## Backend API (agent A builds; agent B codes against exactly this)

- `GET /api/rootcanal/pool/candidates` →
  `{"ok": true, "singles": [{"key": str (stable id for this candidate),
  "entry_id", "session_label", "gid", "project", "mouse", "mouse_key",
  "mouse_type" (registry default), "n", "banked": bool, "version": label|null,
  "params_hash"|null, "read"|null, "here": bool (read on this machine),
  "counts": {...}}]}`. Banked results and cached unbanked reads of Braces-
  aligned DS sets. A recording with both appears twice, as two candidates.
- `POST /api/rootcanal/pool/fit` body `{"members": [{"key", "params"?
  (unbanked only)}], "mouse_types": {mouse_key: type}, "focus":
  {"mouse_key"|"mouse_type": str}|null}` →
  ```
  {"ok": true, "n": int, "n_used": int,
   "axes": [...same as single...],
   "members": [{"key","entry_id","session_label","gid","mouse_key",
                "mouse_type","banked","n","pin":{...}}],
   "events": [{"m": member_index, "i", "t", "amp_uV", "hw_ms", "hf_db",
               "z": [a|null,b|null,c|null], "cls_pool", "cls_single",
               "switched": bool, "partial", "wide", "mouse_key",
               "mouse_type"}],
   "centres": [...], "rule": str, "scale": {"mean":[..],"sd":[..]},
   "gmm": {"n", "bic1", "bic2", "delta", "verdict", "weights":[..],
           "means_raw":[[..],[..]]},
   "gmm_focus": {...same...}|null,
   "switches": {"crosstab": {"ds":{"ds":n,"ied":n},"ied":{"ds":n,"ied":n}},
                "n", "switched", "rate",
                "by_member": [{"key","n","switched","rate","ds_to_ied","ied_to_ds"}],
                "by_mouse": [{"mouse_key", ...}], "by_type": [{"mouse_type", ...}]},
   "split_axis": {"centres_z":[[..],[..]], "values":[proj per event|null]},
   "counts": {"ds","ied","unmeasured","partial","wide"},
   "params": {...}}
  ```
- `POST /api/rootcanal/pool/save` body `{"artifact_id"|null, "nickname",
  "members", "mouse_types", "note"}` → refits server-side (never trusts a
  client payload), writes the artifact or a new version →
  `{"ok", "artifact_id", "version", "confirmed": bool, "name", "nickname"}`.
  Refuse an empty nickname with a sentence.
- `GET /api/rootcanal/pools` → `{"ok", "pools": [artifact rows of kind
  rootcanal_pool, with name, nickname, version, n members, n unbanked,
  updated]}`.
- `GET /api/rootcanal/pool/<artifact_id>` (optional `?version=`) →
  `{"ok", "artifact": row, "payload": the saved payload}`, which the panel
  renders directly with no refit.
- The click panel reuses `POST /api/rootcanal/event` with the member's
  entry/read/params. Add a pool helper that maps (member key, i) to that
  body, or document how the frontend builds it from `members[m].pin`.

## Checks

- agent A: extend `tools/check_rootcanal.py` with a POOL section. Cover:
  synthetic two-member pools with known structure (two well-separated blobs
  → ΔBIC large and positive; one blob → ΔBIC < 2); pooled-raw scaling (a
  member with doubled amplitudes moves in the pool, unlike per-recording z);
  identity-switch arithmetic against a hand count; mouse keys never merging
  PTEN m13 with KCNT1 m13; mouse_types overrides winning; the save refusing
  an empty nickname; save → reopen giving the identical payload; a changed
  member making v2 and an identical re-save a confirmation. Then a real pool
  of whatever banked/cached singles exist (46fd29a77cc7's read is cached),
  with the numbers reported. Never write into GUI_logs/artifacts or the
  event bank during checks: use a temp logs dir, as the commit checks do.
- agent B: `web/_dev/rootcanalpool.html`, driving the real panel: the bar,
  adding members, the colour modes and legends, focus dimming (via _geom
  alpha), the GMM and switch panels and their text, the histograms' axis
  labels (fillText spy), click-to-open, and Save. Intercept the save POST
  so no real artifact is written, as incisorunion.html does for the bank.
  The Single view's harness `rootcanal.html` must still pass. At the end,
  unload the app frame (`A.src = 'about:blank'`) before finishing; without
  it, headless Edge never dumps and the runner reports TIMED OUT.
- Both: `check_js.py`, `check_classes.py`; PowerShell for harnesses; back up
  GUI_logs/event_bank before a harness run and check for " D" afterwards.
  Note: a " D" on a `harness@test` seed record is a harness cleaning up
  after itself (check `added.by` in `git show HEAD:<path>` before
  restoring).
- Patch scripts via the Write tool, never shell heredocs for JS. Touch only
  your files. Don't commit.
