# Folding the concat check into the BARRY GUI

Requirements and integration plan. **No code here** — this is the outline of
what to build, what it must not break, and why.

Context: [`README.md`](README.md) has the diagnosis and the numbers.

---

## 0. What is being proposed

Two features, in dependency order:

**A. A continuity check** inside the existing session health report — does this
recording have gaps, how many segments, how much data is missing, what is the
worst-case time error.

**B. A re-timing action** that, when a session has a concat issue *and* banked
dentate spikes, mints a **new version** of the DS event set with corrected
timestamps, leaving the old version intact and readable.

B is only safe once A exists, because B needs the gap map A produces and needs
to record which map it applied.

---

## 1. Where it fits — the seams that already exist

BARRY already has almost every hook this needs. Use them rather than adding
parallel machinery.

| seam | file | what it gives you |
|---|---|---|
| Session health report | [`backend/extras.py:28`](../BARRY%20GUI/backend/extras.py#L28) `session_health(path, deep=False)` | A list of `{level, name, message}` checks with `level ∈ ok\|warn\|bad`, rolled up by `_grade()`. Additive by design. |
| Health API | [`backend/app.py:4961`](../BARRY%20GUI/backend/app.py#L4961) `/api/session/health` | POST `{paths[], deep}`, returns `{ok, reports[]}`, already logs to activity. |
| Pipeline preflight | [`backend/app.py:4812`](../BARRY%20GUI/backend/app.py#L4812) | Already folds `session_health` checks into the run preflight — a continuity check lands there for free. |
| `.ncs` reader | [`backend/nlx.py`](../BARRY%20GUI/backend/nlx.py) | Correct 1044-byte record dtype, header parser, `read_ncs`, `read_ncs_range`. |
| Event bank versions | [`backend/eventbank.py:229`](../BARRY%20GUI/backend/eventbank.py#L229) `EventBank.add()` | Re-passing an entry `id` replaces in place and mints `v = max(v)+1`, keeping a snapshot. |
| Curation maintenance ops | [`backend/curation.py:716`](../BARRY%20GUI/backend/curation.py#L716) `restamp` / `backfill` / `dedupe` | The established shape for a corrective sweep: `dry_run=True` first, return a per-set report, write atomically, `store._stage()`. **Model the re-time on these.** |

**Do not** add a new top-level "Recording Health" page. The check belongs in the
report people already open before analysis; a second place to look is a second
place to forget.

---

## 2. What already exists that will conflict

Three things in BARRY today will disagree with the new check unless they are
reconciled in the same change. This is the main source of avoidable confusion.

### 2.1 `nlx.read_ncs` already reports a `gaps` count — with a different rule

[`nlx.py`](../BARRY%20GUI/backend/nlx.py) computes:

```
gaps = count(|Δt − nominal| > nominal × 0.5)        nominal = 512/fs × 1e6
```

On `M8s9feb8` that returns **9**. neo/spikeinterface — and therefore Toothy —
see **7** breaks and 8 segments. Two numbers, both called "gaps", visible in
the same app.

**Requirement:** one rule, one name.
- Keep `read_ncs`'s cheap counter but rename its meaning to something honest
  (`irregular_intervals`), *or* move it onto the neo-compatible rule.
- The health check must use the neo/spikeinterface rule:
  tolerance `round(0.25 × 512 × 1e6 / fs)` = 4267 µs at 30 kHz, compared
  against `Δt − int(nb_valid/fs × 1e6)`. That is the rule that decides whether
  Toothy sees one segment or eight, which is the only thing that matters
  downstream.
- Say "segments" in the UI, not "gaps". `8 segments` is the fact; the gap count
  is derived.

### 2.2 `session_health` reports a duration that is neither basis

[`extras.py`](../BARRY%20GUI/backend/extras.py) computes
`dur = n_rec × 512 / fs` — record-index time. On this recording that is
**2124.544 s**, against 2124.3445 s concatenated and 2124.4661 s true.

**Requirement:** report true duration (from the record timestamps) and, when
segments > 1, show the concatenated duration alongside it with a label. A
single unqualified number is what let this hide.

### 2.3 `read_ncs_range` seeks by record index, so the viewer is in a third basis

`r0 = floor(t0 / block)` treats record *i* as starting at `i × block`. With
short records and gaps that is neither concat nor true time — on this recording
the viewer's axis drifts to **+78 ms vs true, +200 ms vs concat** by the end.

**Requirement:** make `read_ncs_range` gap-aware — seek by the record timestamp
array rather than by arithmetic — before claiming any DS overlay is aligned.
Re-timing the events while the viewer's own axis is still wrong just moves the
error around.

> This is the change with the widest blast radius (every viewer, minimap and
> overlay call). It is also the one that makes the other two worth doing. Do it
> behind the segment count: when a file is single-segment the arithmetic path
> is exactly correct and can stay as the fast path.

---

## 3. The blocking constraint: curation identity **is** the timestamp

This is the single most important thing to get right, and it is the reason the
re-time cannot be a loop that adds 0.122 to every `start`.

[`curation.py:140`](../BARRY%20GUI/backend/curation.py#L140):

```python
MATCH_DP = 4
def _tkey(value):
    return round(float(value), MATCH_DP)
```

and [`create()`](../BARRY%20GUI/backend/curation.py#L350) carries this comment:

> *"A candidate's identity is its time in a recording, not the uuid that
> happened to be minted for it. […] events merge by id, so the two shards hold
> disjoint id sets for one set of times and the merge is the union. That is
> exactly what happened to m33 s8 on 2026-09-08: a set restarted from v0 on one
> machine while another held 416 decisions became 832 candidates, half of them
> undecided duplicates of the other half."*

Identity resolution is **0.1 ms**. The concat correction is **45–122 ms** —
roughly a thousand times larger.

**Therefore:** pushing re-timed events through `curation.create()` would give
every event a fresh id, orphan every decision already made, tombstone the old
ids, and — on the next shard merge from another machine — reproduce the m33 s8
doubling exactly.

### Requirements that follow

1. **The re-time must be an in-place edit keyed by event `id`**, never a
   re-create keyed by time. It changes `start` and nothing else about identity.
2. It must run over **both** the bank entry and the curation set. Both hold
   `start`; if only one moves they stop matching and the set comes back
   undecided.
3. It must bump the per-event merge stamp in `shard["_keys"]["events"][eid]`
   (the `["set", stamp]` pair `restamp` maintains). Without that, another
   machine's older copy of the same event id wins the merge and silently
   reverts the correction.
4. Event **count and order must be preserved**. A uniform positive shift is
   monotone, so sort order is stable — assert this rather than assume it.
5. Events that fall *inside* a gap (no true time exists) must be flagged, not
   silently mapped. There should be none, but the assertion is the point.

---

## 4. Part A — the continuity check

### Behaviour

Add one check to `session_health`, and populate structured fields alongside it
(the report already carries `channels`, `fs`, `duration_s`, `identity`).

| condition | level | message |
|---|---|---|
| 1 segment | `ok` | "Continuous — one segment." |
| >1 segment, total loss < ~10 ms | `warn` | "N segments, M ms missing. Timestamps after the first gap shift by up to X ms." |
| >1 segment, larger loss | `warn` | same, with the worst-case error |
| >1 segment **and** banked DS exist for this session | `warn`, with the re-time action offered | see Part B |
| channels disagree on segmentation | `bad` | "Channels disagree — the folder may be mixed or partly copied." |
| short records but 1 segment | `ok` with a note | data lost below the segment threshold |

Report these fields for the UI and for `--json` consumers:
`n_segments`, `gaps[]`, `samples_lost`, `seconds_lost`, `max_time_error_ms`,
`true_duration_s`, `concat_duration_s`, `segment_map[]`, `gap_rule`,
`gap_tolerance_us`.

### Performance

The check must be cheap enough to run on every session health call.

- Read **timestamp + nb_valid only**, via a memmap over the record dtype. Never
  materialise samples.
- One channel by default for the segmentation; **2–4 more as a cross-check**,
  chosen by stride (`session_health` already samples 8 headers this way). A
  full 64-channel parse is `deep=True` only.
- Touching one 130 MB `.ncs`'s timestamp column pulls the whole file through
  the page cache. Over a network share that is not free — cache the result.

### Caching

**Requirement:** a per-session cached gap map, keyed on
`(path, size, mtime)` of the reference `.ncs`, invalidated when any of those
change. `GUI_logs/.cache` already exists for this kind of thing.

The cached map is also the durable artifact Part B consumes, so it needs a
stable content hash (`gap_map_sha`) that can be recorded on a bank version.

### Correctness anchors

- Reproduce neo's **fast path** too: if `ts[-1] == round(ts[0] + (1e6/fs)×512×(n−1))`
  the file is one block with no parse. It is the common case and it is free.
- Report **gap loss** and **nominal-vs-actual clock drift** as separate numbers.
  The lab's clocks run ~29998.6 Hz, not 30000; inferring loss from
  `true_span − concat_span` reports −20 ms of "loss" on a perfectly clean file.
- Pin the rule in the output (`gap_rule: "spikeinterface-nonstrict"`,
  `gap_tolerance_us: 4267`) so a future spikeinterface default change is
  visible rather than mysterious.

---

## 5. Part B — re-timing DS events to a new version

### When it may be offered

All four must hold. Never infer any of them.

1. The session's continuity check found **> 1 segment**.
2. A bank entry of type `ds` exists for this session's `gid`.
3. That entry's `source.pipeline` identifies it as **Toothy concat-era output**
   — i.e. there is positive evidence its times are in concatenated time.
4. The entry is **not already re-timed** (see the idempotency stamp below).

Condition 3 is the one that will be tempting to skip. Do not: a DS set imported
from snapshot folders via [`dsimport.py`](../BARRY%20GUI/backend/dsimport.py),
or hand-curated in BARRY against the raw viewer, is **not** in concatenated
time, and "correcting" it would introduce exactly the error being fixed.
If the basis cannot be established from the record, say so and offer nothing.

### Which basis to correct *to*

This is a real decision and it should be made once, explicitly.

| | agrees with | disagrees with |
|---|---|---|
| keep **concatenated** | Toothy LFP arrays, `lfp_time`, `CSC_Raw.dat`, kilosort unit times | the raw `.ncs` files — i.e. BARRY's own viewer |
| convert to **true** | the raw `.ncs`, BARRY's viewer, `Events.nev`, video/tracking timestamps | Toothy's internal arrays and kilosort units |

**Recommendation: convert to true Neuralynx time**, because BARRY is a
raw-backed application — its viewer, its `.nvt` tracking, its `.nev` events and
its video all live on the Neuralynx clock. Making DS agree with the raw file
makes it agree with everything else BARRY shows.

The cost is explicit and must be stated in the UI: **kilosort unit times for
the same session are still in concatenated time** and need the same conversion
before unit/DS comparisons mean anything. Track that as follow-on work rather
than pretending it does not exist.

### The stamp that makes this safe

Every re-timed entry must carry a machine-readable record of what was done —
this is what prevents double-application, enables reversal, and lets another
machine understand a version it did not create:

```
time_basis: {
  kind:            "neuralynx_true" | "toothy_concat",
  converted_from:  "toothy_concat",
  gap_map_sha:     <hash of the segment map applied>,
  n_segments:      8,
  max_shift_ms:    121.924,
  tool:            "<name>@<version>",
  at:              <iso8601>,
  by:              <person>
}
```

**Requirements:**
- Absence of `time_basis` means *unknown*, not *true*. Never assume.
- A re-time refuses if `time_basis.kind` already equals the target.
- A re-time refuses if `gap_map_sha` does not match the current recording —
  the folder changed under the entry and a stale map must not be applied.

### Mechanics

- Mint the new version through `EventBank.add()` with the **same entry `id`**,
  so it replaces in place and everything pointing at it keeps pointing at it.
  `add()` requires `pipeline` and `added_by` — supply the tool identity and the
  operator, and put the human-readable summary in `version_note`
  ("re-timed from concatenated to true Neuralynx time; 8 segments, up to
  121.9 ms; 1027 of 3463 events moved").
- `add()` re-sorts by `start` and rounds to 6 dp — harmless for a monotone
  shift, but assert count-in == count-out.
- The old version stays in `versions[]` with its snapshot. **Reversal is
  "restore version n−1", not a second arithmetic pass**, and the UI should say
  so.
- Curation set: an in-place `retime(gid, kind, mapping, dry_run=False)` on
  `Curation`, following `restamp`'s shape exactly — read the shard, edit
  `start` per event `id`, bump `_keys.events[eid]`, `shards.write_json_atomic`,
  `store._stage(path)`, return a per-set report.
- **`dry_run=True` must be the first thing that runs and the thing the UI
  shows.** Every existing maintenance op works this way.

### Atomicity

The bank version and the curation set must move together. They are separate
files, so a true transaction is not available — the requirement is that a
partial application is **detectable and repairable**:

- Write the `time_basis` stamp **last**, after both have been written. An entry
  whose events moved but whose stamp is absent is then re-runnable rather than
  ambiguous.
- Make the re-time **idempotent per event id**: store the applied shift per
  event, so re-running compares and skips rather than adding again.
- Record it in activity (`STORE.record_activity`) as its own action, with the
  counts, so the history reads plainly.

---

## 6. Preventing conflicts across machines

Curation is sharded per machine and merged; this is the part where a
well-meant correction becomes a mess on somebody else's laptop.

1. **Never re-create, always edit by id** (§3). This is the whole ballgame.
2. **Bump the per-id merge stamp.** An edit without a newer stamp in
   `_keys.events[eid]` loses to any other machine's untouched copy. The
   correction would appear to work locally and silently revert after a sync.
3. **Deterministic version identity.** Bank versions merge `BYID`
   ([`eventbank.py:120`](../BARRY%20GUI/backend/eventbank.py#L120)). If two
   machines both re-time the same entry, two version ids appear and the history
   shows the same correction twice. Derive the version id from
   `(entry_id, gap_map_sha, target_basis)` so the same correction on two
   machines converges to one version instead of two.
4. **Re-time on one machine, then sync.** Simplest and most reliable: make the
   action refuse when the session's curation set is **open and owned by someone
   else**, and say who holds it. The workbench already tracks owners.
5. **Tombstones.** Since no event is removed, none should be created — assert
   that the tombstone set is unchanged as a post-condition. If it is not, the
   implementation fell back to a re-create path.
6. **The recording folder is per-machine.** A session's path differs across
   machines (and may be absent). The gap map must be stored **with the entry**,
   not recomputed on whichever machine happens to open it — otherwise a machine
   that cannot see `D:\PTEN\...` cannot understand the version.

---

## 7. User experience

### In the session health report

One row, consistent with the existing `{level, name, message}` rows:

```
⚠  continuity     8 segments — 0.122 s missing. Times after 1762.5 s
                  shift by up to 121.9 ms.               [ Details ]
```

`Details` expands to the gap table and segment map. Plain language in the row,
numbers in the expansion.

### When banked DS exist

A second row, and this is where the action lives:

```
⚠  DS timestamps  3463 dentate spikes are in concatenated time.
                  1027 of them are off by up to 121.9 ms.
                  [ Preview correction ]
```

### The correction flow

1. **Preview** (the `dry_run`) — a modal showing: how many events move, the
   shift per segment, the before/after for a handful of events, how many
   decisions are affected, and explicitly **"every labelled event keeps its
   label — nothing is re-detected."** The last line is what makes it
   approvable; fear of losing curation is the real barrier.
2. **Apply** — writes both files, mints `v(n+1)`, stamps the basis.
3. **Confirmation** naming the new version and how to get back:
   *"DS set is now v3 (true Neuralynx time). v2 is kept — restore it from the
   version history."*

### Non-negotiable UX requirements

- **Never auto-apply.** Not on scan, not on open, not on import. A timestamp
  rewrite is a decision with a person's name on it.
- **Never apply in bulk from a scan screen** without a per-session preview.
  The temptation is to offer "fix all 8 affected recordings"; the risk is one
  of them was not in concatenated time.
- **Show the basis wherever DS times are shown** once more than one basis
  exists in the database. A small `true` / `concat` chip on the set.
- **Say the units and the direction.** "121.9 ms earlier than the raw file" is
  understandable; "offset −0.1219" is not.
- **Flag the stitch-adjacent events** (§ README 3) in the same preview. 9
  events here were detected across a discontinuity and may be filter ringing —
  correcting their time does not make them real, and the preview is the honest
  place to say so.

---

## 8. Non-goals and explicit don'ts

- **Do not re-run detection.** This is arithmetic on existing events, not a new
  DS detection. Keeping that boundary is what makes the operation reversible.
- **Do not modify the raw `.ncs` files.** Ever. They are the ground truth the
  correction is derived from.
- **Do not rewrite `DATA.hdf5`.** Toothy's arrays are internally consistent in
  concatenated time; editing them would break `idx` alignment for no gain.
- **Do not "fix" the gaps by interpolation.** The samples were never recorded.
  A gap is missing data, not bad data.
- **Do not infer the time basis from the numbers.** A session with no gaps has
  identical bases and tells you nothing; a session with gaps needs positive
  evidence of provenance, not a guess.
- **Do not let the check block a pipeline run.** It is a `warn`, not a `bad` —
  the data is usable, it just needs its times understood.

---

## 9. Acceptance tests

Use the `HARNESS` project for fixtures. Two notes for whoever implements:
the harness runner shares the app server with `use_reloader=False`, so backend
edits need a restart and never mid-suite; and a harness that assumes its
starting state will report inverted results, so establish preconditions
explicitly.

| # | test | expectation |
|---|---|---|
| 1 | Clean single-segment recording | `ok`, 1 segment, 0 s lost, no action offered |
| 2 | `M8s9feb8` | 8 segments, 7 gaps, 0.1225 s, max 121.924 ms — matches spikeinterface exactly |
| 3 | Clean file, drift only | reports 0 s lost, **not** the negative drift figure |
| 4 | Re-time preview | event count unchanged, order unchanged, decision count unchanged |
| 5 | Re-time apply | every event id preserved; zero new ids; zero tombstones |
| 6 | Re-time twice | second run refuses on the `time_basis` stamp |
| 7 | Merge after re-time | shard from an un-retimed machine does **not** revert the times, and does **not** double the candidate list |
| 8 | Restore v(n−1) | original times return, decisions intact |
| 9 | Entry with no basis evidence | action not offered; reason stated |
| 10 | Folder changed since the map | refuses on `gap_map_sha` mismatch |

Test 7 is the one that matters. It is the m33 s8 failure, and it will only
appear after a sync — long after the change looked fine locally.

---

## 10. Suggested order of work

1. Move the segmentation into `nlx.py` as a cheap, cached, timestamp-only
   function. Reconcile the existing `gaps` counter (§2.1). *Ships alone, breaks
   nothing.*
2. Add the continuity check + structured fields to `session_health`, and fix
   the reported duration (§2.2). *Ships alone; makes the fleet legible.*
3. Run it across the archive and see the real scope before building anything
   that writes. (8 of 25 PTEN recordings, on the current count.)
4. Make `read_ncs_range` gap-aware (§2.3). *Largest blast radius; do it with
   the single-segment fast path retained.*
5. `Curation.retime()` + `time_basis` stamp, `dry_run` first, behind the
   four-condition gate (§5).
6. The UI flow (§7).
7. Only then: the same question for kilosort unit times.

Steps 1–3 are useful on their own even if 4–7 never happen, which is a good
property for a change that touches timestamps.
