# Root Canal — k clusters, saved margins, pooled band, complete-only

Decided with the user on 2026-10-02. Don't change any decision here.
`ROOTCANAL-SPEC.md` and `ROOTCANAL-POOL-SPEC.md` still govern everything
not mentioned.

## Already built (backend, by me): don't redo it, but DO check it

1. **The pooled HF band.** `POST /api/rootcanal/pool/fit` and `/pool/save`
   accept `band: [lo, hi]`.
   - Every member is measured over it: unbanked members are refitted from
     their cached read with the band replaced.
   - A banked member fitted over a different band is refitted from its read
     (when the read is on this machine) and marked: `members[].rebanded_from
     = [old_lo, old_hi]`, `pin.rebanded_from`. Its `cls_single` is then the
     call at the pool's band, not the banked call.
   - A banked member whose read isn't here is refused (400, with a sentence
     naming it).
   - The band is validated like Single's (≤ 2000 Hz).
   - Code: `_rootcanal_pool_members(want, band=None)` and
     `_rootcanal_pool_fit` in app.py.
2. **Complete events only.** `complete_only: true` on pool fit/save drops
   every event missing an axis before scaling, clustering, the GMM, the
   switch tables and drawing.
   - Response: `counts.excluded`, `excluded: {n, complete_only, by_member:
     [{key, n}]}`, `params.complete_only`.
   - If nothing is left, it's refused with a sentence.
   - Code: `fit_pool(..., complete_only=False)` in rootcanalpool.py.
   - Measured on 6 real members: 919 events → 913, with 6 excluded.

## New: the number of clusters, k = 1..6 (Single AND Pooled)

- Fit body: `k` (int, 1–6, default 2). Validate it with a sentence.
- **Clusters are ranked by their centre's raw HF dB, ascending** (rank 0 =
  lowest HF), so a rank means the same thing from one refit to the next.
  Events carry `cluster` = rank.
- **Default calls:** at k ≥ 2 the highest-HF rank is IED and every other
  rank is DS. At k = 1 everything is DS (no split; there is nothing to call
  an IED against), and say so in the rule sentence.
- **Relabel any cluster:** body `cluster_calls: {"<rank>": "ds"|"ied"}`
  overrides the defaults. Hand flips of single events still apply on top,
  as today.
- `centres` (dragged) generalise to k × 3 in z; validate the length against
  k.
- **Response additions:**
  - `k`;
  - `clusters: [{rank, call, call_by: "rule"|"hand"|"margin", n,
    centre_raw: [amp, hw, hf], centre_z: [..]}]`;
  - `centres` stays, now length k.
  The rule sentence is generalised, e.g. "k = 3: the highest-HF cluster
  (+22.1 dB) is called IED; clusters at +9.8 and +14.2 dB are DS (cluster 2
  relabelled by hand)".
- Binary calls (DS/IED) drive everything downstream: banking, identity
  switches, the GMM-agreement metric and colours by call. These work for
  any k.
- **Split axis (Pooled):** the line from the mean z of DS-called events to
  the mean z of IED-called events (0 at their midpoint, DS negative). At
  k = 1, or when every cluster has one call, it's null, with a reason.
- The GMM 1-vs-2 test is unchanged and is independent of k.
- The commit record (Single bank) and saved pool payloads record `k`,
  `clusters` and `margin_used`.

## New: named margins

A **margin** is a set of k cluster centres plus their DS/IED calls, saved
under a name, so the same boundary can be applied to any other Single or
Pooled analysis.

- **Jarvis artifact kind `rootcanal_margin`** (`register_kind` in
  backend/artifacts.py, like `rootcanal_pool`). Its identity is a minted
  `margin_key` stored in the subject. Its `nickname` is the user's label
  and is REQUIRED to save. Re-saving with a changed result makes a new
  version; an identical re-save is a confirmation.
- **Payload:**
  - `k`;
  - `clusters: [{rank, call, centre_raw[3], n}]`;
  - `scale: {mean[3], sd[3]}` (the SOURCE's z scale, raw units);
  - `measure: {filt, mains_out, lo_hz, hi_hz, order, win_ms, cross_ms,
    band_lo, band_hi}`;
  - `source: {kind: "single"|"pool"|"pool_group", entry_id?, read?,
    pool_artifact?, members?: [pins], focus?, n_events}`;
  - `calls_by_hand: [ranks]`.
- **Extracting** (decided: all three sources):
  - `single`: the Single fit's own clustering, dragged centres included,
    on that recording's own scale.
  - `pool`: the pooled clustering, on the pool's scale.
  - `pool_group`: a focused mouse / mouse type / recording in Pooled.
    k-means is RE-RUN on that group alone, z-scored on the group's own
    mean/SD (pooled raw units restricted to the group). Its scale is the
    group's.
- **Applying** (decided: read on the SOURCE's scale; Fixed or Refine,
  a toggle). Body `margin: {artifact_id, version|null, mode: "fixed"|
  "refine"}` on Single fit/commit and Pooled fit/save.
  - **Compatibility first.** The target's measurement settings (`measure`
    keys) must equal the margin's. Otherwise refuse with a 400 that names
    each difference ("the margin was measured on the DS filter and this on
    LFP; the band was 500–1000 Hz and this is 600–900 Hz"). Values on two
    filters are two measurements.
  - **fixed** (the default): z = (raw − margin.scale.mean) / margin.scale.sd
    for every target event; nearest margin centre; partial events on the
    axes they have. Nothing moves. Calls come from the margin, with
    `call_by: "margin"`.
  - **refine**: k-means on the target in the margin's scale, initialised at
    the margin's centres, `n_init = 1`. Each refined cluster keeps the call
    of the margin centre it started from.
  - `cluster_calls` relabels and event flips still apply on top.
  - The margin sets k; a body `k` that differs is ignored, and the
    response says so (`k_from_margin: true`).
  - Response: `margin_used: {artifact_id, version, nickname, mode, digest}`.
  - A saved pool or a banked Single result that used a margin CITES that
    margin version (`Artifacts.cite`), so it can't be deleted from under
    them.
- **Routes:**
  - `POST /api/rootcanal/margin/extract` body `{source: "single", ...single
    fit body}` | `{source: "pool", ...pool fit body}` | `{source:
    "pool_group", ...pool fit body with focus}` → `{ok, preview:
    <payload>}`. Refits server-side.
  - `POST /api/rootcanal/margin/save` body `{artifact_id|null, nickname,
    extract: <the extract body>, note}` → refits, then saves →
    `{ok, artifact_id, version, confirmed, name, nickname}`. Refuse an
    empty nickname.
  - `GET /api/rootcanal/margins` → `{ok, margins: [{artifact_id, nickname,
    name, version, k, calls, measure (the summary words), source (the
    summary words), updated}]}`.
  - `GET /api/rootcanal/margin/<id>?version=` → `{ok, artifact, payload}`.

## Frontend

Constitution binding (web/GUI-CONSTITUTION.md, §2, §6, §6e naming), tokens
only, nothing truncated, deferred Recompute.

- **k selector** (BARRY.ui.seg 1–6) in the Single controls and in Pooled.
  It's disabled, with a title saying why, while a margin is applied.
- **Cluster row** under the space: one chip per rank, showing its colour,
  n, its centre in raw units, its call, and a DS/IED toggle that relabels
  (`cluster_calls`). "by hand" / "from margin" marks.
- **Colour by cluster:** a new colour mode in Single and Pooled (k
  categorical colours, from the token palette), beside the existing modes.
  Calls still drive DS/IED colouring.
- **Dragging centres** works for k centres in the flat views (Single). It's
  off while a margin is applied in fixed mode.
- **Margins:**
  - "Save margins…": in Single (this recording) and in Pooled (the whole
    pool; and "this group" when a focus is set). Through
    BARRY.ui.bankDialog with a required label and no default.
  - "Use a saved margin": a picker over /margins with the version, showing
    each margin's k, calls, measurement and source, plus a Fixed | Refine
    seg. When applied, a chip says "margin ‘label’ v2 · fixed".
  - A 400 incompatibility sentence is shown in place; never a toast alone.
  - Clearing the margin returns to free k-means.
- **Pooled band** (feature 1): lo/hi fields in the Pooled controls, capped
  at 2000, applied with the explicit Pool button. Re-banded members are
  marked in the member list ("re-banded from 500–1000 Hz — its single call
  is at the pool's band"). A refusal sentence is shown beside the button.
- **Complete events only** (feature 2): a checkbox in Pooled, "only events
  measured on all 3 axes". When on, the why-line says how many were left
  out (and per member in the member list).
- Saved pools reopen with band, complete_only, k, cluster_calls and the
  margin restored.

## Checks

- **Backend** (agent A), in tools/check_rootcanal.py:
  - k = 1..6 on synthetic data with known structure: three blobs at k = 3
    → three clusters ranked by HF; at k = 1 all DS.
  - Relabels; centres length vs k refused.
  - The pooled band and complete-only (mine, above): numbers, refusals,
    re-banded marking.
  - Margins: extract from each source; save/reopen identical; v2 on change;
    an identical re-save confirms; a required label.
  - Apply fixed: the same margin on the source gives the source's own calls
    back exactly. On a target with a known shift, events cross exactly
    where the raw boundary says.
  - Apply refine: it moves, keeping calls.
  - An incompatible margin is refused, naming each difference; a margin
    sets k.
  - A cited margin version can't be deleted.
  - Temp logs dirs only. Never write to the real GUI_logs/artifacts or
    event_bank.
- **Frontend** (agent B): `rootcanal.html` and `rootcanalpool.html` gain
  checks for every item above, driven through the real controls. Intercept
  every save POST, as the existing harnesses do. Bites confirmed. End with
  `A.src = 'about:blank'`. Bank backup before runs; a " D" on a
  harness@test seed is a harness cleaning up after itself.
- Both: check_js.py, check_classes.py; PowerShell for harnesses; patch
  scripts via the Write tool; touch only your files; don't commit.
