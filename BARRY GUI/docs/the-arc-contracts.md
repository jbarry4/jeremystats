# The Arc — shared contracts for Circuit, Drift, Artifacts and Spark transitions

Every agent building part of this reads this file first and builds AGAINST it.
If you need to change a contract, do not — say so in your report instead, and
build to the contract as written. Four agents are building in parallel and the
contracts are the only thing keeping them compatible.

Repo: `C:\Users\Z390\Desktop\jeremystats\BARRY GUI` (Flask `backend/*.py`,
vanilla JS `web/js/*.js`, no build step). The house rules are
`web/GUI-CONSTITUTION.md` — binding. Read it.

---------------------------------------------------------------------------
## 0a. AMENDMENT (after wave 1): cue types are counterbalanced

Not one of the ~500 banked DEWEY cue pairs (J3–J11) is `Click → Noise` or
`High tone → Low Tone` — those were J1/J2's pairings on the VACC. The cohort
is counterbalanced and cross-modal per rat (Click → High tone, Noise → Low
Tone, High tone → Noise, Low Tone → Click, ...). `backend/circuit.py`
therefore defines a key for every ordered pairing of the four cues
(`Click_HighTone`, `HighTone_Noise`, `LowTone_Click`, ...), and a circuit is
split by the recording's ACTUAL ordered pairing.

Which pairings count as "the same cue type" across rats is a scientific
decision the user has not made. Until they do: Drift refuses to compare
circuits of different cue types, with a sentence naming both, and offers an
explicit, recorded "treat these as equivalent" choice that is written into
the drift payload (`cue_equivalence`) and shown on the result. Never guess
an equivalence.

## 0b. AMENDMENT: the artifact store as built

- File with `ARTIFACTS.put(kind, subject, payload, ...)` (find → add_version,
  else create). `create` refuses if a live artifact exists for the subject.
- Versions are addressed by number, "v3", or version id; numbers can clash
  across machines, so PIN BY `version_id` (Drift inputs carry `version`,
  `version_id` and `digest`).
- The digest ignores `made` (anywhere) and top-level `computed_on` /
  `computed_at`. Every timestamp or machine detail goes there and nowhere
  else, or re-runs never confirm.
- `supabase/18_artifacts.sql` must be run in the dashboard before artifacts
  sync; until then they are local and nothing errors.

## 0. Decisions the user made (do not re-litigate)

- **Circuit = one recording** × one cue type × one analysis kind (state or
  transition). Cue types are split: `Click_Noise` (Click → Noise) and
  `HighTone_LowTone` (High tone → Low Tone), never pooled.
- **State** = four 10 s chunks per cue pair: `pre`, `cue1`, `cue2`, `post`
  (exists today: `spark.CLIP_WINDOWS`, `spark.pair_windows`).
- **Transition** = three windows around the boundaries, default **1.0 s
  before to 2.0 s after**, adjustable, the lengths recorded on the bank entry.
- **Spark banks BOTH.** One read of the files, two answers (state clipping,
  transition clipping), shown to the user as two steps, banked separately.
  Transition clipping uses the same 50 ms-at-the-rail rule, in time.
- **In a circuit:** a probe histology marks `missed`, `relocated` or
  `unscored` is **grey and NOT computed at all** (stricter than Coupling,
  which computes relocated probes). Heavy event loss only **warns** — a
  region with a usable wire in even 1 cue pair is still used, and the count
  is shown ("usable in 1 of 8 pairs").
- **Each circuit cell stores every cue pair's value** plus n, mean, SD.
- **Drift** = a left group and a right group of circuit artifacts, each
  averaged, then a delta with statistics. **Nested weighting**: cue pairs are
  nested within recordings; recordings are the unit, weighted by precision.
  Never pool pairs across recordings as if independent.
- **No significance testing inside a single circuit.** Means with n. Stats
  live in Drift.
- **The network ring** draws edges by strength with a threshold slider, not
  all 66, no star chips.
- **Artifacts** get an automatic `name` from their metadata, an optional
  user `nickname`, and are identified by content digest. Re-running makes a
  **new version**; old versions are kept; **a version a Drift cites cannot
  be deleted**.
- **Compute:** Circuit runs locally AND on the VACC, plus a VACC batch.
  Drift runs locally and can run on the VACC; no batch.

---------------------------------------------------------------------------
## 1. Window names (Spark ⇄ Coupling ⇄ Circuit)

```
STATE_WINDOWS      = ("pre", "cue1", "cue2", "post")        # exists: spark.CLIP_WINDOWS
TRANSITION_WINDOWS = ("onset", "switch", "offset")
WINDOW_SAY = {
  "pre": "baseline", "cue1": "cue 1", "cue2": "cue 2", "post": "after cue 2",
  "onset": "cue 1 onset", "switch": "cue 1 \u2192 cue 2", "offset": "cue 2 offset",
}
KINDS = ("state", "transition")
```

- `onset`  = [cue1_on − before, cue1_on + after]
- `switch` = [cue2_on − before, cue2_on + after]   (the cue1 → cue2 boundary)
- `offset` = [cue2_off − before, cue2_off + after]
- defaults `before = 1.0`, `after = 2.0` (seconds). Constants in spark.py:
  `TRANSITION_BEFORE_S = 1.0`, `TRANSITION_AFTER_S = 2.0`.
- New function: `spark.transition_windows(pair, before_s=1.0, after_s=2.0)`
  → `[(name, t0, t1), ...]` in TRANSITION_WINDOWS order, same shape as
  `spark.pair_windows`. Use the pair's MEASURED moments, exactly as
  `pair_windows` does (cue-2 offset from the rig's end mark).
- New helper: `spark.windows_for(pair, kind, pad_s=CLIP_PAD_S, before_s=..., after_s=...)`.

**Banked events** keep using the existing per-window dicts `clipped` and
`excluded` (see `backend/eventbank.py` — the whitelist already accepts a dict
keyed by any window name). Transition windows simply add keys `onset`,
`switch`, `offset` to the SAME dicts. No new event fields.

**Bank entry `source.parameters`** gain:
```
"state_measured": bool          # == the existing clip_measured
"transition_measured": bool
"transition_before_s": 1.0
"transition_after_s": 2.0
"clip_pad_s": 10.0              # exists already
```
An entry banked before this has no `transition_measured` → treat as False
(absent is not negative: "nobody looked", never "clean").

`coupling.pair_connectivity(...)` gains `kind="state"` (default, current
behaviour) and `before_s`, `after_s`; with `kind="transition"` it uses the
transition windows. Everything else (one wire per region per window, histology
blocking, `sanity_from_run`) is unchanged and must work for either kind.
`coupling.CLIP_WINDOW_NAMES` stays the state names; add
`coupling.windows_of(kind)`.

---------------------------------------------------------------------------
## 2. The artifact store (backend/artifacts.py)

Model: the Event Bank (`backend/eventbank.py`) — stable minted id, whitelist
schema, versions BYID with a stable version id and a digest, sharded per
machine with `backend/shards.py` `Book`, cloud mirrored add-only with
digest-mismatch = conflict. Differences from the bank: snapshots are NEVER
pruned (a cited version must stay restorable), and there is no retime/dedupe.

```python
class Artifacts:
    def __init__(self, logs_dir, store): ...
    # kind: "circuit" | "drift"   (registry of kinds is open; unknown kinds are refused)
    def create(self, kind, subject, payload, params=None, inputs=None,
               name=None, nickname=None, by=None, note=None) -> dict   # the record, version 1
    def add_version(self, artifact_id, payload, params=None, inputs=None,
                    by=None, note=None) -> dict
        # if the payload digest equals the current version's: no new version,
        # stamp `confirmed` on it instead and return the record unchanged
    def find(self, kind, subject_key) -> dict | None
        # the one artifact for this subject, so re-running a circuit on the same
        # recording+cue type+kind ADDS A VERSION rather than minting a new artifact
    def get(self, artifact_id) -> dict | None          # record, no payloads
    def payload(self, artifact_id, version=None) -> dict | None   # that version's payload
    def list(self, kind=None, gid=None) -> list[dict]  # summaries, no payloads
    def set_nickname(self, artifact_id, nickname, by=None) -> dict
    def cite(self, artifact_id, version, by_artifact_id, by_version) -> None
    def cited_by(self, artifact_id, version=None) -> list[dict]
    def delete(self, artifact_id, by=None) -> dict     # raises ArtifactError if any version is cited
class ArtifactError(Exception): ...
```

`subject_key` is a deterministic string built from the subject, e.g.
`circuit|<gid>|<cue_type>|<kind>` — so the same recording/cue type/kind always
finds the same artifact.

**Record fields** (the whitelist):
```
id                str, minted uuid4().hex[:12], never changes
kind              "circuit" | "drift"
schema            "arc.artifact/1"
subject           dict  (circuit: gid, project, mouse, session, session_label,
                         phase, phase_n, run, cue_type, window_kind)
                        (drift: {"left": [...refs], "right": [...refs]} summary)
subject_key       str
name              str   automatic, from metadata — see below
nickname          str | None   the user's own name for it
version           int   the current version number
versions          [ {v, id, digest, at, by, machine, app_version, commit,
                     params, params_hash, inputs, note, n_summary, confirmed?} ]
                  inputs = list of refs the payload was made from:
                    circuit: [{"kind":"bank", "entry": <id>, "version": <int>}]
                    drift:   [{"kind":"artifact", "id": ..., "version": ..., "digest": ..., "side": "left"|"right"}]
cited             [ {version, by_id, by_version, at} ]    UNION
added             {by, at, machine}   FIRST
deleted           None | {by, at}     (soft; only allowed when nothing cites it)
```

**Automatic name**: circuit →
`"<project> r<mouse> s<session> <phase><phase_n> <run> · <cue label> · <kind>"`,
e.g. `DEWEY r4 s1 Precon1 SPC · High tone → Low Tone · state`.
Drift → `"<left summary> vs <right summary> · <cue label> · <kind>"`.
Nickname is shown first where present, with the name under it.

**Digest**: sha1 over the canonical JSON of the payload (sorted keys, no
`made`/timestamps), first 12 hex chars. Same rule as the bank's `snap_sha`.

**Storage**: records in `GUI_logs/artifacts/<kind>/<id>@<machine>.json`
(sharded Book). Payload snapshots in
`GUI_logs/artifacts/snap/<id>/v<v>__<digest>.json` — written once, never
rewritten, never pruned.

**Routes** (in one clearly-commented block in `backend/app.py`):
```
GET  /api/artifacts?kind=&gid=            -> {ok, artifacts:[summary...]}
GET  /api/artifacts/<id>                  -> {ok, artifact: record}
GET  /api/artifacts/<id>/payload?v=       -> {ok, artifact_id, version, digest, payload}
POST /api/artifacts/<id>/nickname  {nickname}
POST /api/artifacts/<id>/delete           -> 409 with a sentence naming what cites it
```
Creating artifacts is done by the producing tool's own routes (Circuit, Drift)
calling `ARTIFACTS.create/add_version` — there is no generic create route.
Expose a module-level `ARTIFACTS = artifactsmod.Artifacts(LOGS_DIR, STORE)`
in app.py.

**Frontend registry** (in `web/js/results.js` or a new `web/js/artifacts.js`):
```js
BARRY.artifacts = {
  register(kind, { title, icon, summary(record) -> string,
                   render(host, record, payload, version) -> void }),
  action(kind, { id, label, title, run(record, version) }),   // e.g. Drift adds "Use in Drift"
  list(opts) -> Promise<summaries>,
  get(id) -> Promise<record>,
  payload(id, v) -> Promise<{payload, version, digest}>,
  open(id, v)          // opens it in Results' artifact viewer
}
```
Circuit's and Drift's own JS files call `BARRY.artifacts.register(...)` to
supply their viewers. Results owns listing, versions, nickname editing,
delete (with the "cited by" refusal), provenance, and downloading the payload
as JSON.

---------------------------------------------------------------------------
## 3. The circuit payload (backend/circuit.py produces, Drift consumes)

```
{
  "schema": "arc.circuit/1",
  "kind": "state" | "transition",
  "cue_type": "HighTone_LowTone" | "Click_Noise",
  "cue_label": "High tone \u2192 Low Tone",
  "windows": ["pre","cue1","cue2","post"]  |  ["onset","switch","offset"],
  "methods": ["coherence", "raw_cc", "amp_cc"],
  "region_order": [12 region display names, in probes.DEWEY_NETWORK_ORDER],
  "regions": [
    {"region": "Left PER", "slot": "L_PER", "label": "...",
     "histology": "intended|uncertain|relocated|missed|unscored",
     "status": "ok" | "grey",            # grey = relocated | missed | unscored
     "why": "sentence"}
  ],
  "pairs": [{"pair_id": 3, "label": "High tone \u2192 Low Tone", "opener_t": 123.4}],
  "n_pairs": 8,
  "cells": {
    "<window>": {
      "<method>": {
        "<regionA>|<regionB>": {           # regionA before regionB in region_order
          "n": 6, "mean": 0.31, "sd": 0.08,
          "values": [{"pair_id": 3, "v": 0.29}, ...],   # EVERY usable pair
          "of": 8,                          # cue pairs of this type in the recording
          "warn": "usable in 1 of 8 pairs" | null
        }
      }
    }
  },
  "region_usable": { "<window>": { "<region>": {"usable": 7, "of": 8} } },
  "grey": ["Left POR", ...],               # regions not computed, with regions[].why
  "params": { ...coupling.read_params output... , "kind": ..., "before_s":..., "after_s":... },
  "source": {"gid", "session_label", "bank_entry", "bank_version"},
  "computed_on": {"kind": "local" | "vacc", ...}
}
```
- A cell is ABSENT (not null, not zero) when either region is grey, or when
  no cue pair had both regions usable in that window.
- `sd` is the sample SD (ddof=1); `null` when n < 2.
- `warn` is set when `n < of / 2` (half the pairs) — warn, never drop.
- Values are the per-pair summary values `coupling.pair_connectivity`
  already produces (`summaryOf` shape: coherence value, raw_cc peak r,
  amp_cc peak r).

Pure functions in `backend/circuit.py` (no Flask, no file I/O except via
arguments):
```python
CUE_TYPES = {"Click_Noise": ("Click", "Noise"), "HighTone_LowTone": ("High tone", "Low Tone")}
def cue_type_of(pair) -> str | None
def build(pair_results, probe, kind, cue_type, params, source) -> dict   # the payload above
    # pair_results: list of pair_connectivity outputs (one per cue pair of this type)
    # probe: histo.probe_sanity(...) records
def summary(payload) -> dict      # n_summary for the artifact version
```

---------------------------------------------------------------------------
## 4. The drift payload (backend/drift.py)

Inputs: two lists of circuit payloads (left, right), each already pinned by
(artifact id, version, digest). Refuse to compare when kind, cue_type,
windows, methods, or the analysis params that change numbers (low, high,
summary_hz, max_lag_ms, notch_hz, pad_s/before_s/after_s, analysis_fs)
differ — within a side or across sides — and name the field and the
artifacts that disagree.

**Nested weighting, per cell, per side** (a random-effects / inverse-variance
meta-analysis of recordings):
- each recording r gives mean_r, sd_r, n_r (from its circuit cell)
- within-recording variance of its mean: se_r² = sd_r² / n_r
- a recording with n_r = 1 (no sd) uses the pooled within-recording SD
  of that cell across the other recordings on the same side; if no
  recording on that side has n ≥ 2, the cell's SE is undefined → report
  the mean, mark the test as not possible, say why.
- between-recording variance τ² by DerSimonian–Laird; weights
  w_r = 1 / (se_r² + τ²); pooled mean = Σ w_r mean_r / Σ w_r;
  SE = sqrt(1 / Σ w_r). With a single recording on a side, τ² = 0.
- delta = pooled_right − pooled_left; SE_delta = sqrt(SE_L² + SE_R²);
  z = delta / SE_delta; two-sided p; and Benjamini–Hochberg q across the
  cells of each (window, method) panel (66 at most). Report uncorrected p
  AND q; the display uses q.
- every cell reports: left {mean, se, tau2, k (recordings), n (pairs)},
  right {…}, delta, se, z, p, q, and a `warn` list (thin n, a side with
  k = 1, a recording that needed the pooled SD).
```
{
  "schema": "arc.drift/1",
  "kind", "cue_type", "cue_label", "windows", "methods", "region_order",
  "left":  {"label": "...", "members": [{"artifact_id","version","digest","name","gid","n_pairs"}]},
  "right": {...},
  "grey": [...regions grey in ANY member...],   # a region grey in any member is left out of that cell's pooling ONLY for that member; say so
  "cells": {"<window>": {"<method>": {"A|B": { ...as above... }}}},
  "params": {...the shared analysis params...},
  "method": "DerSimonian-Laird random effects; BH across each panel",
  "computed_on": {...}
}
```
Pure functions in `backend/drift.py`:
```python
def compatible(left, right) -> (bool, [sentences])
def pool(cells_by_recording) -> dict     # one side, one cell
def build(left_payloads, right_payloads, left_refs, right_refs, labels) -> dict
```

---------------------------------------------------------------------------
## 5. House rules that bite

- **Run every check from PowerShell**, never bash — under bash Edge's
  `--dump-dom` writes nothing and the whole harness suite passes vacuously.
  Harnesses: `python tools\harness_run.py <name>` (starts its own server).
- **Do not write Python or JS through a shell heredoc** if it contains a
  backslash — they get eaten here, even inside `<<'PY'`. Use the Write/Edit
  tools.
- **Never pipe a server's stdout** (deadlocks at ~40 requests).
- **Other agents are editing this tree right now.** Edit shared files
  (`backend/app.py`, `web/app.css`, `web/js/arc.js`) ONLY with small anchored
  Edit-tool replacements — never rewrite a whole shared file, never reformat,
  re-read just before each edit. Put new routes in ONE clearly-commented
  block. Never `git add -A`, never commit.
- **Harnesses restore, never clear.** A harness that creates bank entries or
  artifacts deletes exactly what it created, in a `finally`.
- **Absent is not negative.** Unmeasured ≠ clean; no histology ≠ intended.
- **Measure, don't guess.** Verify on real data (the Event Bank has 33 banked
  DEWEY recordings, J3–J11; E: holds the raw data) and run a negative control
  for every important check: break the thing, watch the check fail, restore.
- Tokens only in CSS (`--fs-*`, `--sp-*`, `--r-*`, colour tokens); never a
  literal colour; `prefers-reduced-motion`. One primary button per surface,
  last and right-aligned. `.empty-state` says what to do next.
- Every new harness gets a row in `web/_dev/README.md`.

---------------------------------------------------------------------------
## 6. Wave 2: Circuit integration — the route contract (backend ⇄ frontend)

Built by two agents at once: a BACKEND agent (routes, per-pair cache, local
job, VACC single + batch, reliability fixes) and a FRONTEND agent (panel,
matrix, ring, Results viewer). These shapes are the only thing they share.
`backend/circuit.py` (done) and `backend/artifacts.py` (done) are used as-is.

Cue types: split by the recording's ACTUAL ordered pairing (see 0a).

```
GET  /api/arc/circuit/recordings
  -> {ok, rows: [{gid, label, mouse, session, phase, phase_n, date,
                  banked: bool, reachable: bool, vacc: bool,   # vacc = the cluster holds it
                  n_pairs, cue_types: [{cue_type, cue_label, n_pairs}],
                  transition_measured: bool,
                  circuits: [{artifact_id, cue_type, kind, version, name, nickname}]}]}

GET  /api/arc/circuit/<gid>/plan?cue_type=&kind=state|transition
  -> {ok, gid, label, rat, cue_type, cue_label, kind,
      pairs: [{pair_id, label, opener_t, cached: bool}],
      n_pairs, n_cached,
      params: [...coupling.PARAMS with limits, as the Coupling overview gives them],
      defaults: {...}, measured_pad_s, transition_measured,
      probe: [...histo.probe_sanity], grey: [regions + why],
      cost: {local_s, vacc_s | null, vacc_can: bool, vacc_why: str|null,
             sentence: "8 cue pairs, 3 already computed; about 25 s here"},
      artifact: {artifact_id, version, digest, name, nickname} | null}
  # refused 409 with a sentence when kind=transition and transition_measured
  # is false ("run the transition check in Spark first").

POST /api/arc/circuit/<gid>/run
  body {cue_type, kind, params: {...}, where: "local"|"vacc", nickname?: str}
  -> {ok, job: <cfc job id>}             # progress through the existing
                                          # /api/cfc/job/<id>, /cancel, /api/cfc/result/<id>
  # the job result (via /api/cfc/result/<id>) is:
  -> {ok, artifact_id, version, digest, name, nickname, new_version: bool,
      payload: {...arc.circuit/1...}, computed_on: {...}}
  # job progress MUST expose each pair as it lands (a member row per cue
  # pair: pending | running | done | cached | failed + why), so the panel
  # can show pairs arriving before the whole circuit exists.

POST /api/arc/circuit/batch/plan
  body {gids: [...], cue_types: "all" | [...], kind, params}
  -> {ok, todo: [{gid, label, cue_type, n_pairs, n_cached, seconds}],
      already: [{gid, cue_type, artifact_id, version}],   # same params digest
      blocked: [{gid, why}],
      total_s, sentence}
POST /api/arc/circuit/batch/run
  body {gids, cue_types, kind, params, where: "vacc"|"local"}
  -> {ok, job}      # members = (gid, cue_type) rows; each files its artifact as it lands
```

**Per-pair cache**: `GUI_logs/.cache/circuit/<gid>/<pair_id>__<kind>__<params_hash>__b<bank_version>.json`
(git-ignored — check `.gitignore` covers `GUI_logs/.cache/`). A pair result is
exactly `coupling.pair_connectivity` output (curves=False). A circuit re-run at
the same params recomputes nothing and `ARTIFACTS.add_version` returns
`confirmed` instead of a new version when the digest is unchanged.

**Artifact filing**: `ARTIFACTS.find("circuit", circuit.subject_key(gid, cue_type, kind))`
→ add_version, else create. `inputs = [{"kind":"bank","entry":<id>,"version":<v>}]`.
`subject` per §2. `name = circuit.name_for(subject)`. Nickname from the body.

**VACC**: add `tool == "circuit"` to `vacc_run.py` `run_tool` (open the
recording, run `coupling.pair_connectivity` for each requested pair, return
the list of pair results; the LOCAL side then builds the payload and files the
artifact, so the node never needs the bank or the artifact store). Use
`_vacc_run_for` for single runs and `_vacc_run_array` (with `tool=`, `adopt=`)
for the batch. Stage names in `cfc.STAGES` and seeds in `cfc._RATES`.
Frontend `VACC_TOOLS` gains 'circuit' only once a real VACC run has landed.

**Reliability fixes to the shared VACC layer** (they help Doppler/Incisor too;
run `tools\test_vaccrun.py` and `tools\check_vacc_parity.py` and their
harnesses after):
1. `VaccRun.wait`: an ssh error from a poll is retried (with backoff, bounded),
   never allowed to fail the run and cancel a healthy cluster job.
2. `_vacc_run_array`: an ssh error in `arr.poll()` is retried the same way; a
   batch that really fails cancels its array.
3. Batch loop: an overall deadline, and grace for a task that COMPLETED with
   no result file or never appears in sacct — then it is reported failed with
   a sentence, not waited on forever.
4. Survive a Jarvis restart: persist `{rid, slurm_id or array_id, workspace,
   tool, gid(s), cache keys, submitted_at}` at submit time under
   `GUI_logs/vacc_runs/`; on start-up (or on first open of the panel) re-attach
   via `cfc.Job(id=...)`/`cfc.adopt` and fetch what landed. Circuit uses it;
   make it generic so Doppler/Incisor can opt in, but do not change their
   behaviour beyond fixes 1–3.

**Frontend**: NEW `web/js/circuit.js` (`BARRY.circuit`), script tag in
`web/index.html` after arc.js. The Arc's Circuit step (`web/js/arc.js:68`,
`web/js/toolkit.js:310`) becomes built and delegates its paint to
`BARRY.circuit.paint(host)`. One commented CSS section in `web/app.css`.
Register the artifact viewer: `BARRY.artifacts.register('circuit', {title,
icon, summary, render(host, record, payload, version)})` using the SAME
renderer the panel uses, so Results and the panel draw a circuit one way.
