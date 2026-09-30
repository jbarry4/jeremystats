"""circuitrun.py -- running The Arc's Circuit: plan, cache, local, VACC, batch.

`circuit.py` says what a circuit IS: a pure function from a recording's cue
pair results to a payload. This says how one gets MADE -- which cue pairs,
which of them are already computed, where the rest are computed, and how the
answer is filed as a versioned artifact -- so that `app.py` only holds thin
routes (arc_contracts.md section 6).

THE UNIT OF WORK IS ONE CUE PAIR

A circuit is every cue pair of one cue type in one recording, and each pair
is exactly one `coupling.pair_connectivity` call. That call is the expensive
part (about four seconds cold, mostly reading 32 channels four times) and
it does not depend on the other pairs, so it is what is cached and what is
shipped to the cluster:

    GUI_logs/.cache/circuit/<gid>/<pair_id>__<kind>__<hash>__b<bank_version>.json

The file is the pair result, exactly as `pair_connectivity` returns it
(curves=False). `<hash>` covers every parameter that changes the numbers,
AND the recording's bad channels and the regions histology blocks: both
change a pair's numbers without the bank entry changing version, and a
cache keyed on the parameters alone would hand back a pair measured on a
wire somebody has since marked bad. `b<bank_version>` because the banked
event carries that pair's clipping exclusions.

A re-run at the same settings therefore computes nothing, builds the same
payload, and `Artifacts.put` stamps `confirmed` on the current version
instead of minting a new one -- the payload digest is the whole test.

LOCAL AND VACC GO THROUGH ONE `file_circuit`

The same shape Incisor uses: wherever the pairs were computed, they go into
the same cache under the same key and are built and filed by the same
function. The node never sees the bank or the artifact store; it gets the
pairs, the exclusions and the parameters, and returns pair results.

A HOST, NOT AN IMPORT OF APP

Everything that reads the bank, the registry, histology or the VACC status
lives in app.py already (`_coupling_entry`, `_coupling_pair`,
`_coupling_drop`, `_coupling_probe`, `_coupling_blocked`, `_vacc_run_for`,
`_vacc_run_array`, ...). They are handed in as a `host` object rather than
rewritten here, so there is one definition of "which wire" and one of "where
is it on the cluster". See `Host` below for what it has to carry.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import threading
import time

from . import cfc, circuit, coupling, spark, vacc, vaccrun

CACHE_SCHEMA = 1
#: The window lengths each kind actually reads. `pad_s` is kept for both:
#: a transition result still carries it, and `circuit.build` refuses pairs
#: whose carried parameters differ.
_HASHED = ("analysis_fs", "low", "high", "summary_hz", "max_lag_ms",
           "notch_hz", "pad_s")
_HASHED_TRANSITION = ("before_s", "after_s")
#: A band's own fields (arc_contracts.md 7.1). Hashed only when the params
#: are a band's, so every classic cache file keeps the name it has.
_HASHED_BAND = ("band", "coherence_mode", "raw_cc_filtered")

# BANDS AND REST (arc_contracts.md 7.1, 7.3)
#
# A band run is ONE read per cue pair and one artifact per band. The prep
# carries every band's parameters and cache hash (`band_params`,
# `band_phash`); `band_view(prep, band)` is that band as a classic prep, so
# the cache, the "already made" test and the filing are the same functions
# for a band as for a classic run. `prep["bands"]` is None for a classic
# run and every path below takes the classic branch then -- the same keys,
# the same payloads, the same files.
#
# A rest circuit is one DAY: its subject is the day's SPC recording (so it
# matches that day's cue circuits), its samples are ten-second epochs of
# FP1 and FP2 found through the registry (`find_fp`), placed by
# `spark.rest_epochs`, clipping-checked by `spark.clipping_windows` before
# anything is correlated, and each run through the same Coupling engine as
# a cue pair. Its "pairs" are the epochs, so the cache, the member rows and
# `circuit.build` need nothing new.

_ROOT = None
RUNLOG = None
_LOCK = threading.RLock()
# Circuit jobs this process is driving: {job_id: {...}}. For the panel to
# find a run it did not start (a re-attached one) and for `running` rows.
_ACTIVE = {}


class CircuitRunError(Exception):
    """Refused, with a sentence for a person and an HTTP code."""

    def __init__(self, message, code=400, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


class Host(object):
    """What app.py hands in. Every attribute is a callable except the two
    constants; all of them already exist in app.py under the names given.

      entry(gid)                -> the Spark bank entry, or None
      summary(gid)              -> REG.summary of the recording, or {}
      pair(ev, n)               -> _coupling_pair
      drop(ev, bad)             -> _coupling_drop
      probe(sm)                 -> _coupling_probe  (rat, probe records)
      blocked(probe)            -> _coupling_blocked
      measured_pad(entry)       -> _coupling_measured_pad
      measured_transition(e)    -> _coupling_measured_transition
      no_transition             str, _COUPLING_NO_TRANSITION
      artifacts                 the ARTIFACTS store
      recordings(wide)          -> the Arc's recordings in scope
      vacc_status()             -> vacc.status()
      vacc_states(gids, wait)   -> {gid: {"state", "remote", "why"}}
      vacc_run_for(sess, spec, plan, tool_steps) -> (VaccRun, where)
      vacc_run_array(job, tasks, failed, concurrency, tool, adopt,
                     runlog, record)            -> (done, failed)
      vacc_cfg()                -> vacc.load_config(LOGS_DIR)
      push_code()               -> vacc.push_code(cfg, APP_DIR)
      provenance()              -> STORE.provenance()
      activity(rows)            -> STORE.record_activity
    """

    def __init__(self, **kw):
        self.__dict__.update(kw)


def configure(logs_dir):
    """Where the cache and the run records live. Called once by app.py."""
    global _ROOT, RUNLOG
    _ROOT = os.path.join(os.path.abspath(logs_dir), ".cache", "circuit")
    RUNLOG = vaccrun.RunLog(logs_dir)


# ==========================================================================
# Plain values
# ==========================================================================
def _np_default(o):
    try:
        import numpy as np
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:                                    # noqa: BLE001
        pass
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError("%r is not JSON" % (o,))


def plain(x):
    """Through JSON and back, so a result computed now and one read from
    the cache (or off the cluster) are the SAME value, lists not tuples."""
    return json.loads(json.dumps(x, default=_np_default))


def say_s(s):
    """25 s, 3 min, 1.4 h."""
    if s is None:
        return None
    s = float(s)
    if s < 90:
        return "%d s" % max(1, int(round(s)))
    if s < 5400:
        return "%d min" % int(round(s / 60.0))
    return "%.1f h" % (s / 3600.0)


# ==========================================================================
# The per-pair cache
# ==========================================================================
def params_hash(params, bad=(), blocked=(), extra=None):
    """Everything that changes one pair's numbers, as 12 hex characters.

    A band's params hash their band fields too, and `extra` (a rest
    circuit's epochs and the FP recordings' bad channels) is hashed when
    given; neither touches a classic hash."""
    kind = params.get("kind") or "state"
    keep = {k: params.get(k) for k in _HASHED}
    if kind == "transition":
        keep.update({k: params.get(k) for k in _HASHED_TRANSITION})
    if params.get("band") is not None:
        keep.update({k: params.get(k) for k in _HASHED_BAND})
    body = {
        "schema": CACHE_SCHEMA, "kind": kind, "params": keep,
        "methods": list(coupling.METHODS),
        "bad": sorted(int(c) for c in (bad or [])),
        "blocked": sorted(str(b) for b in (blocked or [])),
    }
    if extra is not None:
        body["extra"] = extra
    blob = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _safe_gid(gid):
    g = str(gid or "")
    if not g or "/" in g or "\\" in g or ".." in g:
        raise CircuitRunError("%r is not a recording id." % (gid,))
    return g


def cache_path(gid, pair_id, kind, phash, bank_version):
    if _ROOT is None:
        raise RuntimeError("circuitrun.configure was never called")
    return os.path.join(_ROOT, _safe_gid(gid), "%s__%s__%s__b%s.json" % (
        int(pair_id), kind, phash, bank_version))


def cache_get(gid, pair_id, kind, phash, bank_version):
    """The cached pair result, or None. A file that does not say it is this
    pair and this kind is not trusted, and not deleted either."""
    path = cache_path(gid, pair_id, kind, phash, bank_version)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(got, dict) or got.get("pair_id") != int(pair_id):
        return None
    if ((got.get("params") or {}).get("kind") or "state") != kind:
        return None
    return got


def cache_has(gid, pair_id, kind, phash, bank_version):
    # By reading it, not by the file existing: the plan's "cached" has to
    # mean what the run will find, and a file `cache_get` refuses is a pair
    # the run will compute.
    return cache_get(gid, pair_id, kind, phash, bank_version) is not None


def cache_put(gid, pair_id, kind, phash, bank_version, result):
    path = cache_path(gid, pair_id, kind, phash, bank_version)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(result, fh, default=_np_default)
    os.replace(tmp, path)
    return path


def drop_tag(drop):
    """The wires one pair was computed without, as 8 hex characters.

    Part of the cache key beside the bank version, because the version
    alone does not move when they do: the bank files a new clipping
    measurement onto the same events without minting a version (a version
    records what a person decided), and Spark's transition re-bank of
    2026-09-30 did exactly that. Keyed on the version alone, a pair
    computed before it would have been reused with the wires it now
    excludes still in it."""
    body = json.dumps(plain(drop) if drop is not None else None,
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:8]


def _bank_key(bank_version, drop):
    return "%s-%s" % (bank_version, drop_tag(drop))


def _pair_key(prep, pid):
    if prep.get("kind") == "rest":
        # A rest epoch's wires come from its own clipping check of the FP
        # recordings, filled in at run time and cached under the epochs;
        # the bank never re-files them. Keyed as before.
        return (prep["gid"], pid, prep["kind"], prep["phash"],
                prep["bank_version"])
    drop = None
    for p in prep.get("pairs") or []:
        if int(p.get("pair_id")) == int(pid):
            drop = p.get("drop")
            break
    return (prep["gid"], pid, prep["kind"], prep["phash"],
            _bank_key(prep["bank_version"], drop))


# ==========================================================================
# One cue pair -- the same call here and on the node
# ==========================================================================
def _has_kind():
    try:
        return "kind" in inspect.signature(
            coupling.pair_connectivity).parameters
    except (TypeError, ValueError):
        return False


def _band_specs(band_params):
    """`coupling.band_spec` dicts from band parameter sets (read_params
    output with `band`), for `pair_connectivity(bands=...)`."""
    return [{"id": p["band"], "low": p["low"], "high": p["high"],
             "max_lag_ms": p["max_lag_ms"]} for p in band_params]


def compute_pair(folder, pair, drop, blocked, params, kind, progress=None,
                 bands=None):
    """`coupling.pair_connectivity` with the arguments Coupling's own run
    route gives it -- one place, called by a local run and by the node.

    `bands` is a list of band parameter sets (`read_params(..., band=)`
    output) or `band_spec` dicts: every band from one read, answered as
    `{"bands": {...}}` (see `coupling.pair_connectivity`)."""
    kw = dict(exclude_by_channel=drop,
              notch_hz=params["notch_hz"],
              low=params["low"], high=params["high"],
              max_lag_s=float(params["max_lag_ms"]) / 1000.0,
              pad_s=params["pad_s"],
              summary_hz=params["summary_hz"],
              blocked_regions=blocked or None,
              curves=False, progress=progress)
    if _has_kind():
        kw.update(kind=kind, before_s=params["before_s"],
                  after_s=params["after_s"])
    elif kind != "state":
        raise CircuitRunError("This copy of Coupling cannot measure "
                              "transition windows yet, so no transition "
                              "circuit can be computed with it.", 409)
    if bands:
        kw["bands"] = [b if "id" in b else _band_specs([b])[0]
                       for b in bands]
    return coupling.pair_connectivity(folder, pair, **kw)


def run_node(spec, job):
    """What `vacc_run.py` calls for `tool == "circuit"`.

    Each pair on its own: one that fails comes back as `{pair_id, error}`
    beside the ones that did not, rather than failing the task and throwing
    the rest away.
    """
    pairs = spec.get("pairs") or []
    drops = spec.get("drops") or {}
    params = spec["params"]
    kind = spec.get("kind") or "state"
    job.begin("circuit pairs", of=len(pairs), unit="pairs")
    out = []
    for n, pair in enumerate(pairs):
        pid = pair.get("pair_id")
        job.member(pid, status="running", step="computing on the node")
        try:
            res = compute_pair(spec["path"], pair, drops.get(str(pid)),
                               spec.get("blocked"), params, kind,
                               bands=spec.get("bands") or None)
            out.append(plain(res))
            job.member(pid, status="running", step="computed on the node")
        except Exception as exc:                         # noqa: BLE001
            out.append({"pair_id": pid,
                        "error": "%s: %s" % (type(exc).__name__, exc)})
            job.member(pid, status="failed", step=str(exc)[:120])
        job.tick("circuit pairs", n + 1)
    return {"schema": "arc.circuit.pairs/1", "pairs": out, "n": len(out)}


# ==========================================================================
# The plan
# ==========================================================================
def _types_of(host, entry):
    """[(pair_id, event, pair, cue_type)] for every banked pair."""
    out = []
    for i, ev in enumerate(entry.get("events") or [], start=1):
        pair = host.pair(ev, i)
        out.append((i, ev, pair, circuit.cue_type_of(pair)))
    return out


def cue_types_of(host, entry):
    """[{cue_type, cue_label, n_pairs}] in the order they first appear."""
    tally, order = {}, []
    for _i, _ev, _p, ct in _types_of(host, entry):
        if ct is None:
            continue
        if ct not in tally:
            order.append(ct)
            tally[ct] = 0
        tally[ct] += 1
    return [{"cue_type": ct, "cue_label": circuit.cue_label(ct),
             "n_pairs": tally[ct]} for ct in order]


def param_specs(kind, measured_pad, t_measured, t_before, t_after):
    """coupling.PARAMS for this kind with the limits the Coupling overview
    puts on them: no longer than what the clipping was measured over."""
    out = []
    for p in coupling.params_for(kind):
        q = dict(p)
        if q["id"] == "pad_s":
            q["max"] = min(float(q.get("max") or measured_pad), measured_pad)
        if q["id"] == "before_s" and t_measured:
            q["max"] = min(float(q["max"]), t_before)
        if q["id"] == "after_s" and t_measured:
            q["max"] = min(float(q["max"]), t_after)
        out.append(q)
    return out


def read_bands(bands):
    """The band ids a body asked for, checked (`coupling.band_ids`), or None
    for the classic run. Accepts a list of ids or band dicts, or "all"."""
    if bands in (None, "", []):
        return None
    if bands == "all":
        bands = list(coupling.BAND_ORDER)
    try:
        specs = coupling.band_ids(bands)
    except coupling.CouplingError as exc:
        raise CircuitRunError(str(exc), 400)
    return specs


def read_role(cue_role, role_source, kind):
    """(cue_role, role_source) from a body, checked (arc_contracts.md 7.2).
    Not part of the subject key: within a rat a role is a function of the
    cue type, so it labels a circuit rather than choosing one."""
    if cue_role in (None, ""):
        if role_source not in (None, "", {}):
            raise CircuitRunError("A role_source came without a cue_role; "
                                  "send both or neither.")
        return None, None
    if kind == "rest":
        raise CircuitRunError("A rest circuit has no cue, so it has no cue "
                              "role. Leave cue_role out for kind rest.")
    if cue_role not in circuit.CUE_ROLES:
        raise CircuitRunError("cue_role is %s, not %r." % (
            " or ".join(circuit.CUE_ROLES), cue_role))
    if role_source is not None and not isinstance(role_source, dict):
        raise CircuitRunError("role_source has to be the role table's "
                              "`source` (a dict), not %r." % (role_source,))
    return cue_role, plain(role_source) if role_source is not None else None


def prepare(host, gid, cue_type, kind, body_params=None, bands=None,
            cue_role=None, role_source=None):
    """Everything one circuit needs, worked out before anything runs.

    JSON-able throughout, because it is also the run record a restart picks
    a VACC run up from. Raises `CircuitRunError` with the sentence and the
    code a route should answer with.

    `bands` (ids, or None for the classic run) makes it a band run: one
    read per pair, one artifact per band. `cue_role`/`role_source` are
    filed into the subject and the payload. `kind="rest"` is a day's FP1 +
    FP2 (`prepare_rest`); its `cue_type` is ignored.
    """
    kind = (kind or "state").strip()
    if kind not in circuit.KINDS:
        raise CircuitRunError("The kind has to be state, transition or rest, "
                              "not %r." % kind)
    specs = read_bands(bands)
    cue_role, role_source = read_role(cue_role, role_source, kind)
    if kind == "rest":
        return prepare_rest(host, gid, body_params, specs)
    entry = host.entry(gid)
    if not entry:
        raise CircuitRunError("No cue pairs are banked for this recording. "
                              "Run Spark on it first.", 409)
    sm = host.summary(gid) or {}
    if not sm:
        raise CircuitRunError("There is no recording %s." % gid, 404)

    t_measured, t_before, t_after = host.measured_transition(entry)
    if kind == "transition" and not t_measured:
        raise CircuitRunError(host.no_transition, 409,
                              transition_measured=False)
    measured_pad = host.measured_pad(entry)
    try:
        params = coupling.read_params(
            body_params or {}, measured_pad_s=measured_pad, kind=kind,
            measured_transition=((t_before, t_after) if t_measured else None))
    except coupling.CouplingError as exc:
        raise CircuitRunError(str(exc), 400)

    all_pairs = _types_of(host, entry)
    types = cue_types_of(host, entry)
    if not cue_type:
        raise CircuitRunError(
            "Say which cue type: this recording's pairings are %s. A "
            "circuit is one cue type, never pooled."
            % ("; ".join("%s (%d pairs)" % (t["cue_label"], t["n_pairs"])
                         for t in types) or "none that are cue types"))
    if cue_type not in circuit.CUE_TYPES:
        raise CircuitRunError("%r is not a cue type." % cue_type)
    mine = [(i, ev, p) for i, ev, p, ct in all_pairs if ct == cue_type]
    if not mine:
        raise CircuitRunError(
            "This recording has no %s pairs. Its pairings are %s -- the "
            "cohort is counterbalanced, so each rat has its own."
            % (circuit.cue_label(cue_type),
               "; ".join("%s (%d)" % (t["cue_label"], t["n_pairs"])
                         for t in types) or "none"), 400)

    bad = sorted(int(c) for c in (sm.get("bad_channels") or []))
    rat, probe = host.probe(sm)
    blocked = host.blocked(probe) or {}
    phash = params_hash(params, bad, blocked)
    bank_version = entry.get("version")
    here = cued_folder(sm, entry)
    label = session_label(sm, here)
    reg_paths = list(sm.get("paths") or []) or ([here] if here else [])

    band_params, band_phash = _band_prep(
        specs, body_params, kind, measured_pad,
        (t_before, t_after) if t_measured else None,
        lambda p: params_hash(p, bad, blocked))
    if specs:
        params = band_params[specs[0]["id"]]
        phash = band_phash[specs[0]["id"]]

    pairs = []
    for i, ev, p in mine:
        row = {
            "pair_id": i, "label": p.get("label"),
            "opener_t": p.get("opener_t"),
            "pair": plain(p), "drop": plain(host.drop(ev, bad)),
        }
        _mark_cached(row, gid, kind, phash, bank_version, band_phash)
        pairs.append(row)

    subject = {
        "gid": gid, "project": sm.get("project"), "mouse": sm.get("mouse"),
        "session": sm.get("session"), "session_label": label,
        "phase": sm.get("phase"), "phase_n": sm.get("phase_n"),
        "run": sm.get("run"), "cue_type": cue_type,
        "cue_label": circuit.cue_label(cue_type), "window_kind": kind,
    }
    if cue_role is not None:
        subject["cue_role"] = cue_role
    return plain({
        "gid": gid, "label": label, "rat": rat,
        "cue_type": cue_type, "cue_label": circuit.cue_label(cue_type),
        "kind": kind, "params": params, "phash": phash,
        "bad": bad, "blocked": blocked, "probe": probe or [],
        "entry_id": entry.get("id"), "bank_version": bank_version,
        "path": here, "reg_path": here or (reg_paths[0] if reg_paths else None),
        "pairs": pairs, "n_pairs": len(pairs),
        "n_cached": sum(1 for p in pairs if p["cached"]),
        "measured_pad_s": measured_pad,
        "transition_measured": bool(t_measured),
        "measured_before_s": t_before, "measured_after_s": t_after,
        "subject": subject,
        "source": {"gid": gid, "session_label": label,
                   "bank_entry": entry.get("id"),
                   "bank_version": bank_version},
        "inputs": [{"kind": "bank", "entry": entry.get("id"),
                    "version": bank_version}],
        "cue_types": types,
        "band": None,
        "bands": [s["id"] for s in specs] if specs else None,
        "band_params": band_params, "band_phash": band_phash,
        "cue_role": cue_role, "role_source": role_source,
    })


def _band_prep(specs, body_params, kind, measured_pad, measured_transition,
               hasher):
    """({band: params}, {band: cache hash}) for a band run, ({}, {}) for a
    classic one. Every band's parameters are checked before anything runs:
    one refused band refuses the run."""
    if not specs:
        return {}, {}
    band_params, band_phash = {}, {}
    for s in specs:
        try:
            p = coupling.read_params(
                body_params or {}, measured_pad_s=measured_pad, kind=kind,
                measured_transition=measured_transition, band=s)
        except coupling.CouplingError as exc:
            raise CircuitRunError(str(exc), 400)
        band_params[s["id"]] = p
        band_phash[s["id"]] = hasher(p)
    return band_params, band_phash


def _mark_cached(row, gid, kind, phash, bank_version, band_phash):
    """`cached` on a pair row: every band's result is in the cache (for a
    band run, `cached_bands` says which are), or the classic one is.
    Keyed as `_pair_key` keys it: the version and this pair's wires."""
    if kind != "rest":
        bank_version = _bank_key(bank_version, row.get("drop"))
    if band_phash:
        row["cached_bands"] = [b for b, h in band_phash.items()
                               if cache_has(gid, row["pair_id"], kind, h,
                                            bank_version)]
        row["cached"] = len(row["cached_bands"]) == len(band_phash)
    else:
        row["cached"] = cache_has(gid, row["pair_id"], kind, phash,
                                  bank_version)


def band_view(prep, band):
    """One band of a band prep, shaped as a classic prep: its own params,
    cache hash, subject (with `band`) and per-pair `cached`. The cache, the
    "already made" test and the filing all take it as they take a classic
    prep."""
    pairs = [dict(p, cached=band in (p.get("cached_bands") or []))
             for p in prep["pairs"]]
    return dict(prep, params=prep["band_params"][band],
                phash=prep["band_phash"][band], band=band, bands=None,
                subject=dict(prep["subject"], band=band), pairs=pairs,
                n_cached=sum(1 for p in pairs if p["cached"]))


def views(prep):
    """[prep] for a classic run, one `band_view` per band for a band run."""
    if not prep.get("bands"):
        return [prep]
    return [band_view(prep, b) for b in prep["bands"]]


# ==========================================================================
# Rest: the day's FP1 and FP2 (arc_contracts.md 7.3)
# ==========================================================================
FP_RUNS = ("FP1", "FP2")


def cued_folder(sm, entry=None):
    """The folder of this recording that holds its cue pairs.

    Not `here[0]`. The registry files a DEWEY day's FP1, SPC and FP2 under
    one gid, all three folders in `paths`, in no reliable order -- r10
    Precon1's first reachable folder is FP2, r10 Precon4's is FP1 -- so the
    first folder read an FP recording at the SPC's cue times (Spark found
    no cue pairs there on 2026-09-30; Coupling and Circuit would have
    correlated the wrong recording without a word).

    In order: the folder the banked cue pairs were read from (the entry's
    `session_path`, if it is reachable); else the one reachable folder whose
    own name says it is the SPC run of this rat, phase and phase number
    (`ids.identify`, which reads the folder, not the row's label -- labels
    here name the wrong run); else, among several, the one the registry
    key names; else `here[0]`, as before."""
    from . import ids as _ids
    here = [f for f in (sm or {}).get("here") or [] if f]
    if not here:
        return None
    norm = lambda p: os.path.normcase(os.path.abspath(str(p)))  # noqa: E731
    sp = (entry or {}).get("session_path")
    if sp:
        for f in here:
            if norm(f) == norm(sp):
                return f
    want = ((sm or {}).get("mouse"), (sm or {}).get("phase"),
            (sm or {}).get("phase_n"))
    spc = []
    for f in here:
        ident = _ids.identify(f) or {}
        if ident.get("run") != "SPC":
            continue
        if want[1] is not None and (ident.get("mouse"), ident.get("phase"),
                                    ident.get("phase_n")) != want:
            continue
        spc.append((f, ident))
    if len(spc) == 1:
        return spc[0][0]
    if spc:
        key = (sm or {}).get("key")
        for f, ident in spc:
            if key and ident.get("key") == key:
                return f
        return spc[0][0]
    return here[0]


def session_label(sm, folder):
    """What to call the recording a circuit is made from: the label its
    own folder name gives (`ids.identify`), when it gives one -- the
    registry's row label names the wrong run for five of the sixteen Precon
    recordings ("FP1" on an SPC, "m9" for r9), and every circuit's name
    and the report would have carried it. Else the row's label."""
    from . import ids as _ids
    if folder:
        got = (_ids.identify(folder) or {}).get("label")
        if got:
            return got
    return (sm or {}).get("label")


def find_fp(host, sm, entry=None):
    """The day's FP1 and FP2 recordings, as `[{gid, run, label, start,
    path, duration_s, bad_channels}]` (FP1 first), and a list of sentences
    about what was passed over.

    From the registry (`host.day_runs(sm)`: every non-retired row of the
    same project, rat, phase and phase number whose run is FP1 or FP2) --
    and then CHECKED, because the registry is not clean here: rows carry
    the other runs' folders in their paths, some name the wrong run in
    their label, and a few are aborted acquisitions with no records at
    all. So a folder is used only if its own name says it is that rat,
    phase, phase number and run (`ids.identify`), and it has records. If a
    run has more than one such folder, the one that started nearest the
    SPC recording is the day's. None of this is guessed silently: every
    folder passed over is said.
    """
    from . import ids as _ids
    rows = host.day_runs(sm) or []
    spc_here = cued_folder(sm, entry)
    spc_start = (_ids.identify(spc_here).get("start") if spc_here else None) \
        or sm.get("start")
    want = (sm.get("mouse"), sm.get("phase"), sm.get("phase_n"))
    found, notes = [], []
    for run in FP_RUNS:
        cands = {}
        for row in rows:
            if row.get("run") != run:
                continue
            for folder in row.get("here") or []:
                ident = _ids.identify(folder)
                if (ident.get("mouse"), ident.get("phase"),
                        ident.get("phase_n")) != want \
                        or ident.get("run") != run:
                    continue
                span = spark.recording_span_s(folder)
                if not span or span <= 0:
                    notes.append("%s %s has no records (an aborted "
                                 "acquisition), so it was passed over."
                                 % (run, os.path.basename(folder)))
                    continue
                key = os.path.normcase(os.path.abspath(folder))
                got = cands.setdefault(key, {
                    "run": run, "path": folder, "duration_s": span,
                    "start": ident.get("start"),
                    "label": ident.get("label") or row.get("label"),
                    "rows": []})
                got["rows"].append(row)
        if not cands:
            notes.append("No %s recording of this day is reachable here "
                         "with records in it." % run)
            continue
        pick = sorted(cands.values(), key=lambda c: (
            _secs_apart(c["start"], spc_start), c["path"]))
        chosen = pick[0]
        for other in pick[1:]:
            notes.append("%s %s was passed over for %s, which started "
                         "nearer the cued run." % (
                             run, os.path.basename(other["path"]),
                             os.path.basename(chosen["path"])))
        # The row the folder is filed under: the one whose own duration
        # agrees with the folder's, else the first by id.
        rows_ = sorted(chosen["rows"], key=lambda r: (
            abs(float(r.get("duration_s") or 1e9) - chosen["duration_s"])
            > 1.0, str(r.get("gid"))))
        row = rows_[0]
        found.append({
            "gid": row.get("gid"), "run": run, "label": chosen["label"],
            "start": chosen["start"], "path": chosen["path"],
            "duration_s": chosen["duration_s"],
            "bad_channels": sorted(int(c) for c in
                                   (row.get("bad_channels") or [])),
        })
    return found, notes


def _secs_apart(a, b):
    import datetime as _dt
    try:
        ta = _dt.datetime.fromisoformat(str(a)[:19])
        tb = _dt.datetime.fromisoformat(str(b)[:19])
        return abs((ta - tb).total_seconds())
    except (TypeError, ValueError):
        return float("inf")


def montage_channels(blocked):
    """The CSC numbers a rest epoch will read: the montage's, less the
    regions histology blocks. Clipping is measured on exactly these."""
    return sorted({int(c) for name, csc in coupling.region_map(None).items()
                   if name not in (blocked or {}) for c in csc})


def prepare_rest(host, gid, body_params=None, specs=None):
    """A rest circuit's prep: the day of SPC recording `gid`, its FP1/FP2,
    the epochs, and everything `prepare` gives a cue circuit."""
    entry = host.entry(gid)
    if not entry:
        raise CircuitRunError(
            "No cue pairs are banked for this recording, so there is no count "
            "of cue pairs for the rest epochs to match. Run Spark on it "
            "first.", 409)
    sm = host.summary(gid) or {}
    if not sm:
        raise CircuitRunError("There is no recording %s." % gid, 404)
    types = cue_types_of(host, entry)
    if not types:
        raise CircuitRunError("None of this recording's banked cue pairs has "
                              "a pairing Circuit knows, so there is no count "
                              "for the rest epochs to match.", 409)
    n_epochs = max(t["n_pairs"] for t in types)
    fps, notes = find_fp(host, sm, entry)
    if not fps:
        raise CircuitRunError(
            "No FP1 or FP2 recording of this day (%s %s%s, r%s) is reachable "
            "here with records in it, so there is nothing to cut rest epochs "
            "from. %s" % (sm.get("project"), sm.get("phase"),
                          sm.get("phase_n"), sm.get("mouse"),
                          " ".join(notes)), 409, fp_notes=notes)
    try:
        epochs = spark.rest_epochs(
            [{"key": f["gid"], "run": f["run"],
              "duration_s": f["duration_s"]} for f in fps], n_epochs)
    except spark.SparkError as exc:
        raise CircuitRunError(str(exc), 409)
    try:
        params = coupling.read_params(body_params or {}, kind="rest")
    except coupling.CouplingError as exc:
        raise CircuitRunError(str(exc), 400)
    rat, probe = host.probe(sm)
    blocked = host.blocked(probe) or {}
    by_gid = {f["gid"]: f for f in fps}
    bad_by = {f["gid"]: f["bad_channels"] for f in fps}
    extra = {"rest": {
        "epochs": [[e["key"], e["t0"], e["t1"]] for e in epochs],
        "bad": bad_by, "epoch_s": spark.REST_EPOCH_S,
        "edge_s": spark.REST_EDGE_S}}
    phash = params_hash(params, (), blocked, extra)
    band_params, band_phash = _band_prep(
        specs, body_params, "rest", None, None,
        lambda p: params_hash(p, (), blocked, extra))
    if specs:
        params = band_params[specs[0]["id"]]
        phash = band_phash[specs[0]["id"]]
    bank_version = entry.get("version")
    pairs = []
    for e in epochs:
        f = by_gid[e["key"]]
        row = {
            "pair_id": e["pair_id"], "label": e["label"], "name": e["name"],
            "opener_t": None, "t0": e["t0"], "t1": e["t1"],
            "fp": f["gid"], "run": f["run"], "path": f["path"],
            "pair": {"pair_id": e["pair_id"], "label": e["label"],
                     "t0": e["t0"], "t1": e["t1"]},
            "drop": None,            # from the clipping check, at run time
        }
        _mark_cached(row, gid, "rest", phash, bank_version, band_phash)
        pairs.append(row)
    ct = circuit.REST_CUE_TYPE
    label = session_label(sm, cued_folder(sm, entry))
    subject = {
        "gid": gid, "project": sm.get("project"), "mouse": sm.get("mouse"),
        "session": sm.get("session"), "session_label": label,
        "phase": sm.get("phase"), "phase_n": sm.get("phase_n"),
        "run": sm.get("run"), "cue_type": ct,
        "cue_label": circuit.cue_label(ct), "window_kind": "rest",
    }
    only = montage_channels(blocked)
    clip_key = _rest_clip_hash(epochs, bad_by, only)
    reachable = all(os.path.isdir(f["path"]) for f in fps)
    return plain({
        "gid": gid, "label": label, "rat": rat,
        "cue_type": ct, "cue_label": circuit.cue_label(ct),
        "kind": "rest", "params": params, "phash": phash,
        "bad": [], "bad_by_fp": bad_by, "blocked": blocked,
        "probe": probe or [],
        "entry_id": entry.get("id"), "bank_version": bank_version,
        "path": fps[0]["path"] if reachable else None, "reg_path": None,
        "pairs": pairs, "n_pairs": len(pairs),
        "n_cached": sum(1 for p in pairs if p["cached"]),
        "measured_pad_s": None, "transition_measured": False,
        "measured_before_s": None, "measured_after_s": None,
        "subject": subject,
        "source": {"gid": gid, "session_label": label,
                   "bank_entry": entry.get("id"),
                   "bank_version": bank_version,
                   "fp": [{"gid": f["gid"], "run": f["run"],
                           "label": f["label"], "start": f["start"],
                           "duration_s": f["duration_s"],
                           "bad_channels": f["bad_channels"],
                           "n_epochs": sum(1 for e in epochs
                                           if e["key"] == f["gid"])}
                          for f in fps]},
        "inputs": [{"kind": "bank", "entry": entry.get("id"),
                    "version": bank_version}],
        "cue_types": types, "n_epochs": n_epochs,
        "fp_notes": notes, "only_channels": only, "clip_key": clip_key,
        "clip_cached": _rest_clip_get(gid, clip_key) is not None,
        "band": None,
        "bands": [s["id"] for s in specs] if specs else None,
        "band_params": band_params, "band_phash": band_phash,
        "cue_role": None, "role_source": None,
    })


def _rest_clip_hash(epochs, bad_by, only):
    blob = json.dumps({
        "schema": 1, "epochs": [[e["key"], e["t0"], e["t1"]] for e in epochs],
        "bad": bad_by, "only": list(only),
        "detector": [spark.CLIP_FRACTION, spark.CLIP_MIN_RUN,
                     spark.TRANSITION_LOST_MS],
    }, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _rest_clip_path(gid, key):
    if _ROOT is None:
        raise RuntimeError("circuitrun.configure was never called")
    return os.path.join(_ROOT, _safe_gid(gid), "rest_clip__%s.json" % key)


def _rest_clip_get(gid, key):
    try:
        with open(_rest_clip_path(gid, key), "r", encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) and got.get("key") == key else None


def rest_clipping(prep, tick=None, use_cache=True):
    """Measure every epoch of a rest prep for clipping, with the detector
    and the 50 ms rule every cue window has (`spark.clipping_windows`), on
    exactly the channels the epoch will be read on, each FP recording's
    bad channels skipped. Cached beside the pair results, because a re-run
    that computes nothing must still file the same `source.clipping`.

    Returns `{epoch name: {pair_id, gid, run, t0, t1, measured, why, lost,
    touched, unmeasured, skipped_bad, detail}}`.
    """
    gid, key = prep["gid"], prep["clip_key"]
    if use_cache:
        hit = _rest_clip_get(gid, key)
        if hit is not None:
            if tick:
                tick(len(prep["pairs"]))
            return hit["by_epoch"]
    by_fp = {}
    for p in prep["pairs"]:
        by_fp.setdefault((p["fp"], p["path"]), []).append(p)
    out, done = {}, 0
    for (fgid, path), eps in by_fp.items():
        skip = prep["bad_by_fp"].get(fgid) or []
        got = spark.clipping_windows(
            path, [{"pair_id": e["pair_id"], "windows": spark.rest_windows(e)}
                   for e in eps],
            skip=skip, only=prep["only_channels"])
        for e in eps:
            chans = (got.get("by_pair") or {}).get(e["pair_id"]) or {}
            unm = (got.get("unmeasured") or {}).get(e["pair_id"]) or {}
            out[e["name"]] = {
                "pair_id": e["pair_id"], "gid": fgid, "run": e["run"],
                "t0": e["t0"], "t1": e["t1"],
                "measured": bool(got.get("measured")), "why": got.get("why"),
                "lost": sorted(int(c) for c, r in chans.items()
                               if "rest" in (r.get("windows") or [])),
                "touched": sorted(int(c) for c, r in chans.items()
                                  if "rest" not in (r.get("windows") or [])),
                "unmeasured": {str(c): (w or {}).get("rest")
                               for c, w in sorted(unm.items())},
                "skipped_bad": sorted(int(c) for c in skip),
                "detail": {str(c): (r.get("detail") or {}).get("rest")
                           for c, r in sorted(chans.items())},
            }
            done += 1
            if tick:
                tick(done)
    out = plain(out)
    path = _rest_clip_path(gid, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"key": key, "by_epoch": out}, fh, default=_np_default)
    os.replace(tmp, path)
    return out


def apply_rest_clipping(prep, clip):
    """Each epoch's exclusion -- the channels lost in it, and its FP
    recording's bad channels -- into the prep's pairs, and the measurement
    into `source.clipping`. An epoch whose recording could not be measured
    is left without a `drop`, and is refused rather than read as clean."""
    for p in prep["pairs"]:
        c = clip.get(p["name"]) or {}
        if not c.get("measured"):
            p["drop"] = None
            p["unmeasured_why"] = (c.get("why") or "its clipping could not "
                                   "be measured")
            continue
        bad = prep["bad_by_fp"].get(p["fp"]) or []
        p["drop"] = {"rest": sorted(set(c.get("lost") or []) | set(bad))}
    prep["source"] = dict(prep["source"], clipping=clip)
    return prep


def artifact_params(prep):
    """What the artifact version records as its parameters: the analysis
    parameters verbatim, plus the hash that also covers bad channels and
    histology -- which is what "already made at these settings" compares."""
    out = dict(prep["params"], inputs_hash=prep["phash"],
               bad_channels=prep["bad"],
               blocked_regions=sorted(prep["blocked"]))
    # Section 7: what the digest alone would miss when deciding "already
    # made" -- a role filed onto a circuit, the FP recordings a rest one
    # read. Absent on a classic run, so its params are what they were.
    if prep.get("cue_role") is not None:
        out["cue_role"] = prep["cue_role"]
    if prep.get("kind") == "rest":
        out["bad_by_fp"] = prep.get("bad_by_fp") or {}
    return out


def current_artifact(host, prep):
    rec = host.artifacts.find("circuit", circuit.subject_key(
        prep["gid"], prep["cue_type"], prep["kind"], prep.get("band")))
    if not rec:
        return None
    cur = max(rec.get("versions") or [{}],
              key=lambda v: (v.get("v") or 0, v.get("at") or "",
                             v.get("id") or ""))
    return {"artifact_id": rec["id"], "version": rec.get("version"),
            "version_id": cur.get("id"), "digest": cur.get("digest"),
            "name": rec.get("name"), "nickname": rec.get("nickname"),
            "params": cur.get("params") or {},
            "inputs": cur.get("inputs") or []}


def is_current(art, prep):
    """The artifact already says what a run at these settings would say:
    same analysis parameters, bad channels and histology, same bank version."""
    if not art:
        return False
    p = art.get("params") or {}
    return (p.get("inputs_hash") == prep["phash"]
            and plain(art.get("inputs") or []) == plain(prep["inputs"])
            and p.get("cue_role") == prep.get("cue_role"))


def all_current(host, prep):
    """Every band's (or the one classic) artifact is already current."""
    return all(is_current(current_artifact(host, v), v) for v in views(prep))


def _rate(where):
    return cfc.rate_for("circuit pairs", where)


def local_seconds(prep):
    todo = prep["n_pairs"] - prep["n_cached"]
    if not prep.get("path"):
        return None
    vol = cfc.volume_key(prep["path"])
    if prep.get("kind") == "rest":
        clip = (0 if prep.get("clip_cached") else
                prep["n_pairs"] * cfc.rate_for("rest clipping", vol))
        return round(todo * cfc.rate_for("rest epochs", vol) + clip, 1)
    return round(todo * _rate(vol), 1)


def vacc_place(host, gid, wait=True):
    """{can, state, remote, where, why} for the cluster. Never raises."""
    out = {"can": False, "state": None, "remote": None, "where": None,
           "why": None}
    try:
        st = host.vacc_status() or {}
        if not st.get("configured"):
            out["why"] = "No VACC account is set up on this computer."
            return out
        if st.get("available") is False:
            out["why"] = st.get("why") or "The cluster is not reachable."
            return out
        got = (host.vacc_states([gid], wait) or {}).get(gid) or {}
        out["state"] = got.get("state")
        if got.get("state") in (vacc.NATIVE, vacc.STAGED) and got.get("remote"):
            out.update(can=True, remote=got["remote"],
                       where=("vacc:netfiles" if got["state"] == vacc.NATIVE
                              else "vacc:scratch"))
        else:
            out["why"] = ("The cluster holds no copy of this recording (%s). "
                          "Upload it to VACC first." % (
                              got.get("why") or "not found there"))
    except Exception as exc:                             # noqa: BLE001
        out["why"] = str(exc)[:200]
    return out


def cost(host, prep, wait=True):
    """Say the cost before it is spent (constitution 6d)."""
    n, c = prep["n_pairs"], prep["n_cached"]
    todo = n - c
    local_s = local_seconds(prep)
    if prep.get("kind") == "rest":
        # Rest is made here: the FP recordings are not what the cluster
        # was given, and nothing here has been run on it.
        place = {"can": False, "state": None, "where": None,
                 "why": "Rest circuits are made on this computer only."}
    else:
        place = vacc_place(host, prep["gid"], wait)
    vacc_s = (round(todo * _rate(place["where"]), 1) if place["can"]
              else None)
    if prep.get("kind") == "rest":
        head = "%d rest epoch%s of FP1 + FP2" % (n, "" if n == 1 else "s")
    else:
        head = "%d cue pair%s" % (n, "" if n == 1 else "s")
    if prep.get("bands"):
        head += " in %d band%s (%s), one read each" % (
            len(prep["bands"]), "" if len(prep["bands"]) == 1 else "s",
            ", ".join(circuit.band_label(b) for b in prep["bands"]))
    if todo == 0:
        sentence = head + (", all already computed; nothing to run, it "
                           "files at once")
    else:
        sentence = head + (", %d already computed" % c if c
                           else ", none computed yet")
        if local_s is not None:
            sentence += "; about %s here" % say_s(local_s)
        else:
            sentence += "; this computer cannot read the recording"
        if vacc_s is not None:
            sentence += ("; on the VACC about %s of compute plus the queue "
                         "wait" % say_s(vacc_s))
    return {"local_s": local_s, "local_can": bool(prep.get("path")),
            "local_why": None if prep.get("path") else
            "None of this recording's paths are reachable from this machine.",
            "vacc_s": vacc_s, "vacc_can": bool(place["can"]),
            "vacc_why": place["why"], "vacc_state": place["state"],
            "n_todo": todo, "sentence": sentence + "."}


def _art_brief(host, view):
    art = current_artifact(host, view)
    if not art:
        return None
    out = {k: art[k] for k in ("artifact_id", "version", "version_id",
                               "digest", "name", "nickname")}
    out["current"] = is_current(art, view)
    return out


def plan(host, gid, cue_type, kind, body_params=None, bands=None,
         cue_role=None, role_source=None):
    """The `/plan` response (contract section 6), minus `ok`.

    Section 7: with `bands`, `artifacts` is `{band: artifact brief}` and
    `artifact` is the first band's (the one the panel shows); `band_params`
    are each band's run parameters. For `kind="rest"`, `pairs` are the
    epochs (each with `t0`, `t1`, `run`), and `fp` names the FP1/FP2
    recordings found, `fp_notes` what was passed over and why."""
    prep = prepare(host, gid, cue_type, kind, body_params, bands, cue_role,
                   role_source)
    grey = [{"region": r, "why": why}
            for r, why in circuit.grey_regions(prep["probe"])]
    vs = views(prep)
    arts = {v.get("band"): _art_brief(host, v) for v in vs}
    art = arts.get(vs[0].get("band"))
    specs = param_specs(prep["kind"], prep["measured_pad_s"] or
                        spark.CLIP_PAD_S, prep["transition_measured"],
                        prep["measured_before_s"], prep["measured_after_s"])
    if prep.get("bands"):
        # The band owns these; said on the field rather than hidden, so
        # the panel can show what the band set them to.
        for q in specs:
            if q["id"] in coupling._BAND_OWNS:
                q["band_owned"] = True
    out = {
        "gid": gid, "label": prep["label"], "rat": prep["rat"],
        "cue_type": prep["cue_type"], "cue_label": prep["cue_label"],
        "kind": prep["kind"],
        "pairs": [dict({"pair_id": p["pair_id"], "label": p["label"],
                        "opener_t": p["opener_t"], "cached": p["cached"]},
                       **({"t0": p["t0"], "t1": p["t1"], "run": p["run"],
                           "name": p["name"]} if prep["kind"] == "rest"
                          else {}))
                  for p in prep["pairs"]],
        "n_pairs": prep["n_pairs"], "n_cached": prep["n_cached"],
        "params": specs,
        "defaults": coupling.default_params(),
        "run_params": prep["params"],
        "measured_pad_s": prep["measured_pad_s"],
        "transition_measured": prep["transition_measured"],
        "measured_before_s": prep["measured_before_s"],
        "measured_after_s": prep["measured_after_s"],
        "probe": prep["probe"], "grey": grey,
        "cost": cost(host, prep),
        "artifact": art,
        "cue_types": prep["cue_types"],
        "bank": {"entry": prep["entry_id"], "version": prep["bank_version"]},
        "bands": prep.get("bands"),
        "band_catalog": [dict(coupling.BANDS[b],
                              label=coupling.BAND_LABELS[b])
                         for b in coupling.BAND_ORDER],
        "cue_role": prep.get("cue_role"),
    }
    if prep.get("bands"):
        out["artifacts"] = arts
        out["band_params"] = prep["band_params"]
    if prep["kind"] == "rest":
        out["fp"] = prep["source"]["fp"]
        out["fp_notes"] = prep.get("fp_notes") or []
        out["n_epochs"] = prep["n_epochs"]
        out["clip_cached"] = prep.get("clip_cached")
    return out


# ==========================================================================
# Running the pairs here
# ==========================================================================
def run_pairs(job, prep, report=None, tick=None):
    """Every pair of `prep`, from the cache or computed here.

    `report(pair_id, **patch)` says what happened to each pair as it
    happens -- the single run points it at the job's member rows, a batch
    at one row's counters. `tick(n)` after each computed pair. Returns
    {pair_id: result} for every pair that has one; a failed pair is
    reported and left out.
    """
    report = report or (lambda pid, **k: None)
    if prep.get("bands"):
        return _run_pairs_bands(job, prep, report, tick)
    results, n_new = {}, 0
    for p in prep["pairs"]:
        job.check()
        pid = p["pair_id"]
        hit = cache_get(*_pair_key(prep, pid))
        if hit is not None:
            results[pid] = hit
            report(pid, status="cached", step="already computed",
                   cached=True)
            continue
        if prep["kind"] == "rest" and p.get("drop") is None:
            why = ("not computed: %s, and an epoch nobody could check is not "
                   "a clean one" % (p.get("unmeasured_why")
                                    or "its clipping was not measured"))
            report(pid, status="failed", step=None, error=why[:200],
                   why=why[:200])
            n_new += 1
            if tick:
                tick(n_new)
            continue
        report(pid, status="running", step="reading")
        try:
            res = plain(compute_pair(p.get("path") or prep["path"],
                                     p["pair"], p["drop"],
                                     prep["blocked"], prep["params"],
                                     prep["kind"]))
            cache_put(*(_pair_key(prep, pid) + (res,)))
            results[pid] = res
            report(pid, status="done", step=None)
        except cfc.Canceled:
            raise
        except Exception as exc:                         # noqa: BLE001
            why = "%s: %s" % (type(exc).__name__, exc)
            report(pid, status="failed", step=None, error=why[:200],
                   why=why[:200])
        n_new += 1
        if tick:
            tick(n_new)
    return results


def _run_pairs_bands(job, prep, report, tick):
    """`run_pairs` for a band run: {band: {pair_id: result}}.

    Per pair, the bands already in the cache are read back and the rest
    are computed from ONE read of the wires (`compute_pair(bands=...)`),
    then each band's result is cached under its own hash. A pair every
    band of which is cached is not read at all."""
    vs = {v["band"]: v for v in views(prep)}
    results = {b: {} for b in prep["bands"]}
    n_new = 0
    for p in prep["pairs"]:
        job.check()
        pid = p["pair_id"]
        need = []
        for b in prep["bands"]:
            hit = cache_get(*_pair_key(vs[b], pid))
            if hit is not None:
                results[b][pid] = hit
            else:
                need.append(b)
        if not need:
            report(pid, status="cached", step="already computed",
                   cached=True)
            continue
        if prep["kind"] == "rest" and p.get("drop") is None:
            why = ("not computed: %s, and an epoch nobody could check is not "
                   "a clean one" % (p.get("unmeasured_why")
                                    or "its clipping was not measured"))
            report(pid, status="failed", step=None, error=why[:200],
                   why=why[:200])
            n_new += 1
            if tick:
                tick(n_new)
            continue
        report(pid, status="running", step="reading")
        try:
            res = plain(compute_pair(
                p.get("path") or prep["path"], p["pair"], p["drop"],
                prep["blocked"], prep["params"], prep["kind"],
                bands=[prep["band_params"][b] for b in need]))
            for b, one in coupling.split_bands(res).items():
                cache_put(*(_pair_key(vs[b], pid) + (one,)))
                results[b][pid] = one
            report(pid, status="done", step=None)
        except cfc.Canceled:
            raise
        except Exception as exc:                         # noqa: BLE001
            why = "%s: %s" % (type(exc).__name__, exc)
            report(pid, status="failed", step=None, error=why[:200],
                   why=why[:200])
        n_new += 1
        if tick:
            tick(n_new)
    return results


def _results_from_cache(prep):
    """{pair_id: result} from the cache, or {band: {pair_id: result}} for
    a band run -- the shape `run_pairs` returns."""
    if prep.get("bands"):
        return {v["band"]: _results_from_cache(v) for v in views(prep)}
    out = {}
    for p in prep["pairs"]:
        hit = cache_get(*_pair_key(prep, p["pair_id"]))
        if hit is not None:
            out[p["pair_id"]] = hit
    return out


def file_all(host, prep, results, computed_on, nickname=None, by=None):
    """`file_circuit` for a classic run; for a band run, one artifact per
    band, filed in band order, answered as the first band's result plus
    `bands: {band: its result}` and `band_order`. With more than one band a
    nickname gets " · <band>" so the three artifacts can be told apart."""
    if not prep.get("bands"):
        return file_circuit(host, prep, results, computed_on, nickname, by)
    many = len(prep["bands"]) > 1
    out, first = {}, None
    for v in views(prep):
        b = v["band"]
        nick = nickname
        if nickname and str(nickname).strip() and many:
            nick = "%s · %s" % (str(nickname).strip(), circuit.band_label(b))
        got = file_circuit(host, v, results.get(b) or {}, computed_on, nick,
                           by)
        out[b] = got
        first = first or got
    return dict(first, bands=out, band_order=list(prep["bands"]))


def file_circuit(host, prep, results, computed_on, nickname=None, by=None):
    """Build the payload and file it: a new artifact, a new version, or a
    confirmation of the current one. The job result (contract section 6).

    `prep` is a classic prep or ONE band's view (`band_view`)."""
    got = [results[p["pair_id"]] for p in prep["pairs"]
           if p["pair_id"] in results]
    missing = [p["pair_id"] for p in prep["pairs"]
               if p["pair_id"] not in results]
    if not got:
        raise CircuitRunError(
            "None of the %d %s %s could be computed, so there is no "
            "circuit to file." % (prep["n_pairs"], prep["cue_label"],
                                  "epochs" if prep["kind"] == "rest"
                                  else "pairs"), 409)
    payload = circuit.build(got, prep["probe"], prep["kind"],
                            prep["cue_type"], prep["params"], prep["source"],
                            of=prep["n_pairs"], computed_on=computed_on,
                            cue_role=prep.get("cue_role"),
                            role_source=prep.get("role_source"))
    arts = host.artifacts
    key = circuit.subject_key(prep["gid"], prep["cue_type"], prep["kind"],
                              prep.get("band"))
    with _LOCK:
        before = arts.find("circuit", key)
        seen = {v.get("id") for v in ((before or {}).get("versions") or [])}
        note = None
        if missing:
            note = ("%d of %d pairs could not be computed (pair %s)"
                    % (len(missing), prep["n_pairs"],
                       ", ".join(str(m) for m in missing)))
        rec = arts.put("circuit", prep["subject"], payload,
                       params=artifact_params(prep), inputs=prep["inputs"],
                       name=circuit.name_for(prep["subject"]),
                       nickname=nickname, by=by, note=note)
        nick = (str(nickname).strip() if nickname else "") or None
        if before and nick and nick != rec.get("nickname"):
            rec = arts.set_nickname(rec["id"], nick, by=by)
    cur = max(rec.get("versions") or [{}],
              key=lambda v: (v.get("v") or 0, v.get("at") or "",
                             v.get("id") or ""))
    new = cur.get("id") not in seen
    try:
        host.activity([{
            "action": "arc.circuit.file",
            "detail": {"gid": prep["gid"], "cue_type": prep["cue_type"],
                       "kind": prep["kind"], "artifact": rec["id"],
                       "version": cur.get("v"), "new_version": new,
                       "pairs": len(got), "of": prep["n_pairs"],
                       "where": (computed_on or {}).get("kind"),
                       **({"band": prep["band"]} if prep.get("band")
                          else {})},
        }])
    except Exception:                                    # noqa: BLE001
        pass
    out = {"ok": True, "artifact_id": rec["id"], "version": cur.get("v"),
           "version_id": cur.get("id"), "digest": cur.get("digest"),
           "name": rec.get("name"), "nickname": rec.get("nickname"),
           "new_version": new, "confirmed": not new,
           "n_pairs": len(got), "of": prep["n_pairs"],
           "missing": missing,
           "payload": payload, "computed_on": payload.get("computed_on")}
    if prep.get("band"):
        out["band"] = prep["band"]
    return out


def _here(host):
    prov = {}
    try:
        prov = dict(host.provenance() or {})
    except Exception:                                    # noqa: BLE001
        pass
    return {"kind": "local", "machine": prov.get("machine"),
            "at": prov.get("at")}


def _small_spec(prep, where):
    out = {"tool": "circuit", "gid": prep["gid"], "path": prep.get("path"),
           "cue_type": prep["cue_type"], "kind": prep["kind"],
           "where": where}
    if prep.get("bands"):
        out["bands"] = list(prep["bands"])
    return out


def _n_results(prep, results):
    """How many pairs came back, from either shape `run_pairs` returns."""
    if prep.get("bands"):
        return len(set().union(*[set(r) for r in results.values()]) if
                   results else set())
    return len(results)


def _stages(prep, todo):
    """The job's stages: a rest circuit checks its epochs for clipping,
    then runs them; a cue circuit runs its pairs."""
    if prep.get("kind") == "rest":
        return [("rest clipping", prep["n_pairs"]), ("rest epochs", todo)]
    return [("circuit pairs", todo)]


def _pair_stage(prep):
    return "rest epochs" if prep.get("kind") == "rest" else "circuit pairs"


def compute_local(job, host, prep, report=None, tick=None):
    """The pairs of one circuit, here: for a rest circuit the clipping
    check first (its own stage), then the pairs. Returns what `run_pairs`
    returns."""
    if prep.get("kind") == "rest":
        job.begin("rest clipping", of=prep["n_pairs"], unit="epochs")
        clip = rest_clipping(prep, tick=lambda n: job.tick("rest clipping",
                                                           n))
        apply_rest_clipping(prep, clip)
    todo = prep["n_pairs"] - prep["n_cached"]
    stage = _pair_stage(prep)
    job.begin(stage, of=todo, unit="epochs" if stage == "rest epochs"
              else "pairs")
    return run_pairs(job, prep, report=report,
                     tick=tick or (lambda n: job.tick(stage, n)))


def _init_pair_members(job, prep):
    job.members_init([{"id": p["pair_id"], "label": p["label"]}
                      for p in prep["pairs"]])
    for p in prep["pairs"]:
        if p["cached"]:
            job.member(p["pair_id"], status="cached", cached=True,
                       step="already computed")
        else:
            job.member(p["pair_id"], status="pending", step=None)


def _track(job, prep, where, batch=False):
    with _LOCK:
        _ACTIVE[job.id] = {"job": job.id, "gid": prep.get("gid"),
                           "cue_type": prep.get("cue_type"),
                           "kind": prep.get("kind"), "where": where,
                           "batch": batch, "started": time.time()}


def running():
    """Circuit jobs this process is driving, still running."""
    out = []
    with _LOCK:
        rows = list(_ACTIVE.values())
    for r in rows:
        j = cfc.get(r["job"])
        if j is not None and j.status == "running":
            out.append(dict(r))
    return out


def start_local(host, prep, nickname=None):
    """One circuit, computed here. Returns the cfc job."""
    if not prep.get("path"):
        raise CircuitRunError("None of this recording's paths are reachable "
                              "from this machine, so there is nothing to "
                              "read here.", 409)
    todo = prep["n_pairs"] - prep["n_cached"]

    def work(job):
        _init_pair_members(job, prep)
        results = compute_local(
            job, host, prep, report=lambda pid, **k: job.member(pid, **k))
        on = dict(_here(host), cached=prep["n_cached"],
                  computed=_n_results(prep, results) - prep["n_cached"])
        return file_all(host, prep, results, on, nickname)

    job = cfc.start(_small_spec(prep, "local"), _stages(prep, todo), work,
                    1.0)
    _track(job, prep, "local")
    return job


def _vacc_spec(prep, todo):
    out = {"path": prep["reg_path"], "gid": prep["gid"],
           "kind": prep["kind"], "params": prep["params"],
           "blocked": prep["blocked"],
           "pairs": [p["pair"] for p in todo],
           "drops": {str(p["pair_id"]): p["drop"] for p in todo}}
    if prep.get("bands"):
        # Every band from one read on the node; the local side splits them.
        out["bands"] = _band_specs([prep["band_params"][b]
                                    for b in prep["bands"]])
    return out


def _adopt_pairs(prep, out, report=None):
    """Put what the cluster computed into the cache, pair by pair (and for
    a band run, band by band under each band's own hash)."""
    report = report or (lambda pid, **k: None)
    vs = {v.get("band"): v for v in views(prep)}
    for res in (out or {}).get("pairs") or []:
        pid = res.get("pair_id")
        if res.get("error"):
            report(pid, status="failed", step=None,
                   error=str(res["error"])[:200], why=str(res["error"])[:200])
            continue
        try:
            for b, one in coupling.split_bands(res).items():
                if b not in vs:
                    continue
                cache_put(*(_pair_key(vs[b], int(pid)) + (plain(one),)))
            report(pid, status="done", step=None)
        except Exception as exc:                         # noqa: BLE001
            report(pid, status="failed", step=None, error=str(exc)[:200],
                   why=str(exc)[:200])


def start_vacc(host, prep, nickname=None):
    """One circuit, its uncached pairs computed on the cluster."""
    if prep.get("kind") == "rest":
        raise CircuitRunError("Rest circuits are made on this computer only: "
                              "choose This computer.", 409)
    todo = [p for p in prep["pairs"] if not p["cached"]]
    if not todo:
        # Nothing to send. Filed here, at once, and said so.
        return start_local(host, prep, nickname) if prep.get("path") else \
            _start_filing_only(host, prep, nickname)
    place = vacc_place(host, prep["gid"], True)
    if not place["can"]:
        raise CircuitRunError(place["why"] or "The cluster cannot run this.",
                              409)
    steps = [("circuit pairs", len(todo))]
    est = len(todo) * _rate(place["where"])
    run, where = host.vacc_run_for({"path": prep["reg_path"],
                                    "gid": prep["gid"]},
                                   _vacc_spec(prep, todo),
                                   {"seconds": est, "megasamples": 1.0},
                                   steps)
    run.members = [p["pair_id"] for p in todo]
    run.runlog = RUNLOG
    run.record = {"prep": prep, "nickname": nickname}
    job = cfc.start(_small_spec(prep, where), vaccrun.steps() + steps,
                    lambda job: _vacc_work(host, prep, run, job, nickname),
                    1.0, where)
    _track(job, prep, where)
    return job


def _vacc_work(host, prep, run, job, nickname, init=True):
    if init:
        _init_pair_members(job, prep)
        for p in prep["pairs"]:
            if not p["cached"]:
                job.member(p["pair_id"], status="pending",
                           step="waiting for the cluster")
    out = run.work(job)
    _adopt_pairs(prep, out, report=lambda pid, **k: job.member(pid, **k))
    results = _results_from_cache(prep)
    on = dict(out.get("computed_on") or {"kind": "vacc"},
              cached=prep["n_cached"])
    got = file_all(host, prep, results, on, nickname)
    run.close_record("done")
    return got


def _start_filing_only(host, prep, nickname):
    def work(job):
        _init_pair_members(job, prep)
        results = _results_from_cache(prep)
        return file_all(host, prep, results,
                        dict(_here(host), cached=_n_results(prep, results),
                             computed=0), nickname)
    job = cfc.start(_small_spec(prep, "local"), [("circuit pairs", 0)],
                    work, 1.0)
    _track(job, prep, "local")
    return job


# ==========================================================================
# Batch
# ==========================================================================
def _wanted_types(cue_types, have):
    if cue_types in (None, "", "all"):
        return [t["cue_type"] for t in have]
    if isinstance(cue_types, str):
        cue_types = [cue_types]
    return [t["cue_type"] for t in have if t["cue_type"] in cue_types]


def _role_for(roles, gid, ct):
    """(cue_role, role_source) for one (recording, cue type) of a batch.
    `roles` is {"<gid>|<cue type>": {"cue_role", "role_source"}}: a role is
    a rat's, so a batch across rats cannot carry one role for all."""
    got = (roles or {}).get("%s|%s" % (gid, ct)) or {}
    return got.get("cue_role"), got.get("role_source")


def batch_plan(host, gids, cue_types="all", kind="state", body_params=None,
               where="vacc", keep_preps=False, bands=None, roles=None):
    """Which circuits a batch would make, which are already made at these
    settings, which cannot be made and why -- and what it costs, in total.

    `bands` makes every row a band run (one read, one artifact per band;
    a row is "already" only when every band is). `kind="rest"` makes one
    row per recording (its day's FP1 + FP2), whatever `cue_types` says.
    `roles` files a cue role per row (see `_role_for`)."""
    where = "local" if str(where or "").startswith("local") else "vacc"
    todo, already, blocked, preps = [], [], [], []
    gids = [g for g in (gids or []) if g]
    if not gids:
        raise CircuitRunError("Say which recordings: `gids` is empty.")
    kind = (kind or "state").strip()
    if kind not in circuit.KINDS:
        raise CircuitRunError("The kind has to be state, transition or rest, "
                              "not %r." % kind)
    # Parameters are checked once, up front: one set applies to a whole
    # batch, and a bad value is a refusal of the batch, not of each row.
    try:
        coupling.read_params(body_params or {}, kind=kind)
    except coupling.CouplingError as exc:
        raise CircuitRunError(str(exc), 400)
    read_bands(bands)
    if kind == "rest" and where == "vacc":
        raise CircuitRunError("Rest circuits are made on this computer only: "
                              "run the batch here.", 409)
    states = {}
    if where == "vacc":
        try:
            states = host.vacc_states(gids, True) or {}
        except Exception:                                # noqa: BLE001
            states = {}
        st = host.vacc_status() or {}
        if not st.get("configured"):
            raise CircuitRunError("No VACC account is set up on this "
                                  "computer, so a VACC batch cannot run.",
                                  409)
    for gid in gids:
        entry = host.entry(gid)
        if not entry:
            blocked.append({"gid": gid, "why": "Spark has not filed this "
                            "recording’s cue pairs yet."})
            continue
        have = cue_types_of(host, entry)
        want = ([circuit.REST_CUE_TYPE] if kind == "rest"
                else _wanted_types(cue_types, have))
        if not want:
            blocked.append({"gid": gid, "why": (
                "It has no pairs of the cue types asked for; its pairings "
                "are %s." % ("; ".join(t["cue_label"] for t in have)
                             or "none"))})
            continue
        for ct in want:
            try:
                role, source = _role_for(roles, gid, ct)
                prep = prepare(host, gid, ct, kind, body_params, bands,
                               role, source)
            except CircuitRunError as exc:
                blocked.append({"gid": gid, "cue_type": ct, "why": str(exc)})
                continue
            if all_current(host, prep):
                arts = {v.get("band"): current_artifact(host, v)
                        for v in views(prep)}
                art = arts[views(prep)[0].get("band")]
                row = {"gid": gid, "label": prep["label"], "cue_type": ct,
                       "artifact_id": art["artifact_id"],
                       "version": art["version"],
                       "version_id": art["version_id"]}
                if prep.get("bands"):
                    row["bands"] = {b: {"artifact_id": a["artifact_id"],
                                        "version": a["version"],
                                        "version_id": a["version_id"]}
                                    for b, a in arts.items()}
                already.append(row)
                continue
            n_todo = prep["n_pairs"] - prep["n_cached"]
            if n_todo and where == "local" and not prep.get("path"):
                blocked.append({"gid": gid, "cue_type": ct, "why":
                                "This computer cannot read the recording."})
                continue
            if n_todo and where == "vacc":
                got = states.get(gid) or {}
                if not (got.get("state") in (vacc.NATIVE, vacc.STAGED)
                        and got.get("remote")):
                    blocked.append({"gid": gid, "cue_type": ct, "why": (
                        "The cluster holds no copy of this recording (%s). "
                        "Upload it to VACC first." % (
                            got.get("why") or "not found there"))})
                    continue
                prep["remote"] = got["remote"]
                prep["vacc_where"] = ("vacc:netfiles"
                                      if got["state"] == vacc.NATIVE
                                      else "vacc:scratch")
            rate_where = (prep.get("vacc_where") if where == "vacc"
                          else cfc.volume_key(prep.get("path")))
            secs = (local_seconds(prep) or 0.0) if kind == "rest" else \
                round(n_todo * _rate(rate_where), 1)
            row = {"gid": gid, "label": prep["label"], "cue_type": ct,
                   "cue_label": prep["cue_label"],
                   "n_pairs": prep["n_pairs"],
                   "n_cached": prep["n_cached"], "seconds": secs}
            if prep.get("bands"):
                row["bands"] = list(prep["bands"])
            if kind == "rest":
                row["fp"] = [f["run"] for f in prep["source"]["fp"]]
            todo.append(row)
            preps.append(prep)
    n_pairs = sum(t["n_pairs"] - t["n_cached"] for t in todo)
    if where == "vacc":
        # One array: the tasks run side by side, so the wall time is the
        # slowest task, not the sum. Both are said.
        total_s = round(sum(t["seconds"] for t in todo), 1)
        worst = max([t["seconds"] for t in todo] or [0])
        req = vacc.slurm_request(worst, 1.0,
                                 (host.vacc_cfg() or {}).get("partition"))
        sentence = ("%d circuit%s to make from %d cue pairs not yet "
                    "computed: about %s of cluster compute in one job array "
                    "on the %s partition, the longest task about %s, plus "
                    "the queue wait" % (
                        len(todo), "" if len(todo) == 1 else "s", n_pairs,
                        say_s(total_s), req["partition"], say_s(worst)))
    else:
        total_s = round(sum(t["seconds"] for t in todo), 1)
        req = None
        sentence = ("%d circuit%s to make from %d cue pairs not yet "
                    "computed: about %s here, one after another" % (
                        len(todo), "" if len(todo) == 1 else "s", n_pairs,
                        say_s(total_s)))
    if todo and not n_pairs:
        sentence = ("%d circuit%s to file from pairs already computed; "
                    "nothing needs computing, so nothing goes %s" % (
                        len(todo), "" if len(todo) == 1 else "s",
                        "to the cluster" if where == "vacc" else "to read"))
    if not todo:
        sentence = "Nothing to make"
    if already:
        sentence += "; %d already made at these settings" % len(already)
    if blocked:
        sentence += "; %d cannot be made (said why)" % len(blocked)
    nb = len(read_bands(bands) or [])
    if nb and todo:
        sentence += ("; each is %d band%s from one read, one artifact per "
                     "band" % (nb, "" if nb == 1 else "s"))
    if kind == "rest":
        sentence = sentence.replace("cue pairs", "rest epochs")
    out = {"todo": todo, "already": already, "blocked": blocked,
           "total_s": total_s, "sentence": sentence + ".", "where": where,
           "n_pairs": n_pairs,
           "partition": req["partition"] if req else None,
           "walltime": req["time"] if req else None}
    if keep_preps:
        out["_preps"] = preps
    return out


def _member_id(prep):
    return "%s|%s" % (prep["gid"], prep["cue_type"])


def start_batch(host, gids, cue_types="all", kind="state", body_params=None,
                where="vacc", concurrency=None, bands=None, roles=None):
    """The batch: one job, one member row per (recording, cue type) -- per
    recording for rest. A band batch files every band of a row when the
    row lands; the job result's `made` rows carry `bands`."""
    got = batch_plan(host, gids, cue_types, kind, body_params, where,
                     keep_preps=True, bands=bands, roles=roles)
    preps = got.pop("_preps")
    where = got["where"]
    if not preps and not got["already"]:
        raise CircuitRunError("Nothing in this batch can be made: " +
                              "; ".join(b["why"] for b in got["blocked"])[:600],
                              409)
    if where == "vacc" and any(p["n_pairs"] > p["n_cached"] for p in preps):
        host.push_code()
    rows = ([{"id": _member_id(p), "label": "%s · %s" % (
                p["label"], p["cue_label"])} for p in preps]
            + [{"id": "%s|%s" % (a["gid"], a["cue_type"]),
                "label": "%s · %s" % (a.get("label") or a["gid"],
                                            circuit.cue_label(a["cue_type"]))}
               for a in got["already"]]
            + [{"id": "%s|%s" % (b["gid"], b.get("cue_type") or "*"),
                "label": b["gid"]} for b in got["blocked"]])
    total_pairs = sum(p["n_pairs"] - p["n_cached"] for p in preps)

    def init(job):
        job.members_init(rows)
        for a in got["already"]:
            job.member("%s|%s" % (a["gid"], a["cue_type"]), status="done",
                       cached=True, step="already made at these settings",
                       artifact_id=a["artifact_id"], version=a["version"])
        for b in got["blocked"]:
            job.member("%s|%s" % (b["gid"], b.get("cue_type") or "*"),
                       status="skipped", step=None, error=b["why"][:200],
                       why=b["why"][:200])
        for p in preps:
            job.member(_member_id(p), status="pending", done=0,
                       of=p["n_pairs"] - p["n_cached"])

    def filed(job, prep, res):
        job.member(_member_id(prep), status="done", step=None,
                   artifact_id=res["artifact_id"], version=res["version"],
                   new_version=res["new_version"],
                   **({"n_bands": len(res["bands"])} if res.get("bands")
                      else {}))
        out = {"gid": prep["gid"], "cue_type": prep["cue_type"],
               "artifact_id": res["artifact_id"], "version": res["version"],
               "version_id": res["version_id"], "digest": res["digest"],
               "new_version": res["new_version"]}
        if res.get("bands"):
            out["bands"] = {b: {k: r.get(k) for k in (
                "artifact_id", "version", "version_id", "digest",
                "new_version")} for b, r in res["bands"].items()}
        return out

    def summary(made, failed):
        return {"ok": True, "where": where, "n": len(rows),
                "made": made, "failed": failed,
                "already": got["already"], "blocked": got["blocked"],
                "sentence": got["sentence"]}

    if where == "local":
        stage = "rest epochs" if kind == "rest" else "circuit pairs"
        n_clip = sum(p["n_pairs"] for p in preps) if kind == "rest" else 0

        def work(job):
            init(job)
            made, failed = [], []
            clip_failed = set()
            if kind == "rest":
                # Every row's epochs are checked first, as one stage: a
                # stage is opened once per run (cfc.Job.begin).
                job.begin("rest clipping", of=n_clip, unit="epochs")
                seen = [0]
                for prep in preps:
                    job.check()
                    mid = _member_id(prep)
                    job.member(mid, status="running",
                               step="checking the epochs for clipping")
                    base = seen[0]
                    try:
                        clip = rest_clipping(prep, tick=lambda n, b=base:
                                             job.tick("rest clipping", b + n))
                        apply_rest_clipping(prep, clip)
                    except cfc.Canceled:
                        raise
                    except Exception as exc:             # noqa: BLE001
                        why = str(exc)[:200]
                        clip_failed.add(mid)
                        job.member(mid, status="failed", step=None,
                                   error=why, why=why)
                        failed.append({"gid": prep["gid"],
                                       "cue_type": prep["cue_type"],
                                       "why": why})
                    seen[0] = base + prep["n_pairs"]
            job.begin(stage, of=total_pairs,
                      unit="epochs" if kind == "rest" else "pairs")
            count = [0]
            for prep in preps:
                job.check()
                mid = _member_id(prep)
                if mid in clip_failed:
                    continue
                job.member(mid, status="running", step="reading")
                done_here = [0]

                def tick(n, mid=mid):
                    count[0] += 1
                    done_here[0] = n
                    job.member(mid, done=n)
                    job.tick(stage, count[0])
                try:
                    results = run_pairs(job, prep, tick=tick)
                    res = file_all(host, prep, results, dict(
                        _here(host), cached=prep["n_cached"],
                        computed=_n_results(prep, results)
                        - prep["n_cached"]))
                    made.append(filed(job, prep, res))
                except cfc.Canceled:
                    raise
                except Exception as exc:                 # noqa: BLE001
                    why = str(exc)[:200]
                    job.member(mid, status="failed", step=None, error=why,
                               why=why)
                    failed.append({"gid": prep["gid"],
                                   "cue_type": prep["cue_type"], "why": why})
            return summary(made, failed)
        plan_ = ([("rest clipping", n_clip)] if kind == "rest" else []) \
            + [(stage, total_pairs)]
        job = cfc.start({"tool": "circuit", "batch": True, "where": "local",
                         "path": (preps[0].get("path") if preps else None)},
                        plan_, work, 1.0)
        _track(job, {"gid": None, "kind": kind}, "local", batch=True)
        return job, got

    def work(job):
        init(job)
        job.begin("circuit batch", of=len(preps), unit="circuits")
        made, failed = [], []
        tasks = []
        for prep in preps:
            todo = [p for p in prep["pairs"] if not p["cached"]]
            if not todo:
                try:
                    res = file_all(host, prep, _results_from_cache(prep),
                                   dict(_here(host), cached=prep["n_pairs"],
                                        computed=0))
                    made.append(filed(job, prep, res))
                except Exception as exc:                 # noqa: BLE001
                    failed.append({"gid": prep["gid"],
                                   "cue_type": prep["cue_type"],
                                   "why": str(exc)[:200]})
                    job.member(_member_id(prep), status="failed",
                               error=str(exc)[:200], why=str(exc)[:200])
                continue
            spec = _vacc_spec(prep, todo)
            tasks.append({
                "gid": prep["gid"], "member": _member_id(prep),
                "label": prep["label"],
                "spec_local": spec,
                "spec_remote": dict(spec, path=prep["remote"]),
                "tool_steps": [("circuit pairs", len(todo))],
                "seconds": len(todo) * _rate(prep.get("vacc_where")),
                "megasamples": 1.0,
                "resume": prep,
            })
            job.member(_member_id(prep), status="queued",
                       step="waiting for the cluster")
        landed = [len(made)]

        def adopt(t, out):
            prep = t["resume"]
            _adopt_pairs(prep, out)
            res = file_all(host, prep, _results_from_cache(prep),
                           dict(out.get("computed_on") or {"kind": "vacc"},
                                cached=prep["n_cached"]))
            made.append(filed(job, prep, res))
            landed[0] += 1
            job.tick("circuit batch", landed[0])

        if tasks:
            _done, _failed = host.vacc_run_array(
                job, tasks, 0, concurrency, "circuit", adopt, RUNLOG,
                {"job_id": job.id, "kind": kind, "batch": True})
            for t in tasks:
                m = next((x for x in (job.snapshot().get("members") or [])
                          if x.get("id") == t["member"]), {})
                if m.get("status") == "failed":
                    failed.append({"gid": t["gid"],
                                   "cue_type": t["resume"]["cue_type"],
                                   "why": m.get("why") or m.get("error")})
        return summary(made, failed)

    first = next((p for p in preps if p.get("vacc_where")), None)
    job = cfc.start({"tool": "circuit", "batch": True, "where": "vacc",
                     "path": None},
                    [("circuit batch", len(preps))], work, 1.0,
                    (first or {}).get("vacc_where") or "vacc:scratch")
    _track(job, {"gid": None, "kind": kind}, "vacc", batch=True)
    return job, got


# ==========================================================================
# Surviving a restart (fix 4)
# ==========================================================================
_RESUMED = {"done": False}


def resume_once(host, background=True):
    """Re-attach, once per process, to every circuit run a previous process
    submitted and never finished filing. Returns the jobs it adopted (or []
    straight away when it runs in the background)."""
    with _LOCK:
        if _RESUMED["done"]:
            return []
        _RESUMED["done"] = True
    if RUNLOG is None:
        return []
    if background:
        threading.Thread(target=lambda: resume(host), daemon=True,
                         name="barry-circuit-resume").start()
        return []
    return resume(host)


def resume(host, ssh=None):
    """Adopt every open circuit run record. Returns the jobs."""
    out = []
    for rec in RUNLOG.open_runs(tool="circuit"):
        if rec.get("job_id") and cfc.exists(rec["job_id"]):
            continue                   # this process is driving it already
        try:
            out.append(_resume_one(host, rec, ssh))
        except Exception as exc:                         # noqa: BLE001
            try:
                RUNLOG.close(rec["rid"], "failed",
                             "could not be picked up again: %s" % exc)
            except Exception:                            # noqa: BLE001
                pass
    return out


def _resume_one(host, rec, ssh=None):
    cfg = host.vacc_cfg()
    if rec.get("kind") == "single":
        run = vaccrun.VaccRun.reattach(cfg, rec, ssh=ssh)
        run.runlog = RUNLOG
        prep = run.record["prep"]
        nickname = run.record.get("nickname")
        where = (vacc_place(host, prep["gid"], True).get("where")
                 or "vacc:scratch")
        steps = [tuple(s) for s in (rec.get("tool_steps") or [])]
        job = cfc.adopt(cfc.Job(_small_spec(prep, where),
                                vaccrun.steps() + steps, 1.0, where,
                                id=rec.get("job_id")))
        job.log.append("picked up again after a restart: slurm job %s"
                       % run.slurm_id)
        _track(job, prep, where)

        def go():
            try:
                job.finish(_vacc_work(host, prep, run, job, nickname))
            except Exception as exc:                     # noqa: BLE001
                job.fail(exc)
        threading.Thread(target=go, daemon=True,
                         name="barry-circuit-" + job.id).start()
        return job

    arr = vaccrun.VaccArray.reattach(cfg, rec, ssh=ssh)
    arr.runlog = RUNLOG
    tasks = [dict(j) for j in (rec.get("jobs") or [])]
    job = cfc.adopt(cfc.Job({"tool": "circuit", "batch": True,
                             "where": "vacc", "path": None},
                            [("circuit batch", len(tasks))], 1.0,
                            "vacc:scratch", id=rec.get("job_id")))
    job.log.append("picked up again after a restart: array %s"
                   % arr.array_id)
    job.members_init([{"id": t.get("member") or t.get("gid"),
                       "label": t.get("label")} for t in tasks])
    taken = set(rec.get("taken") or [])
    _track(job, {"gid": None, "kind": (rec.get("record") or {}).get("kind")},
           "vacc", batch=True)
    made, landed = [], [len(taken)]

    def on_result(i, t, out):
        prep = t["resume"]
        _adopt_pairs(prep, out)
        res = file_all(host, prep, _results_from_cache(prep),
                       dict(out.get("computed_on") or {"kind": "vacc"},
                            cached=prep["n_cached"]))
        made.append({"gid": prep["gid"], "cue_type": prep["cue_type"],
                     "artifact_id": res["artifact_id"],
                     "version": res["version"]})
        landed[0] += 1
        job.tick("circuit batch", landed[0])

    def go():
        try:
            job.begin("circuit batch", of=len(tasks), unit="circuits")
            done, failed = vaccrun.collect(job, arr, tasks, on_result,
                                           taken=taken)
            job.finish({"ok": True, "where": "vacc", "resumed": True,
                        "made": made, "failed": failed})
        except Exception as exc:                         # noqa: BLE001
            job.fail(exc)
    threading.Thread(target=go, daemon=True,
                     name="barry-circuit-" + job.id).start()
    return job


# ==========================================================================
# The recordings list
# ==========================================================================
def recordings(host, wide=False):
    """The `/recordings` rows (contract section 6)."""
    rows = host.recordings(wide) or []
    circuits = {}
    for a in (host.artifacts.list(kind="circuit") or []):
        subj = a.get("subject") or {}
        cur = a.get("current") or {}
        circuits.setdefault(subj.get("gid"), []).append({
            "artifact_id": a.get("id"), "cue_type": subj.get("cue_type"),
            "kind": subj.get("window_kind"), "version": a.get("version"),
            "version_id": cur.get("id"), "name": a.get("name"),
            "nickname": a.get("nickname"),
            # Section 7: None on a classic circuit, the band id on a band
            # one; the cue role when one was filed.
            "band": subj.get("band"), "cue_role": subj.get("cue_role")})
    gids = [r.get("gid") for r in rows if r.get("gid")]
    try:
        states = host.vacc_states(gids, False) or {}
    except Exception:                                    # noqa: BLE001
        states = {}
    out = []
    for r in rows:
        gid = r.get("gid")
        entry = host.entry(gid) if gid else None
        tm = host.measured_transition(entry)[0] if entry else False
        st = states.get(gid) or {}
        types = cue_types_of(host, entry) if entry else []
        out.append({
            "gid": gid, "label": r.get("label"), "mouse": r.get("mouse"),
            "session": r.get("session"), "phase": r.get("phase"),
            "phase_n": r.get("phase_n"), "run": r.get("run"),
            "date": r.get("date"),
            "banked": bool(entry), "reachable": bool(r.get("reachable")),
            "vacc": st.get("state") in (vacc.NATIVE, vacc.STAGED),
            # Absent is not negative: "unknown" while the cluster's listing
            # has not been read yet, never a quiet False.
            "vacc_state": st.get("state") or "unknown",
            "n_pairs": len(entry.get("events") or []) if entry else None,
            "cue_types": types,
            "transition_measured": bool(tm),
            "bank": ({"entry": entry.get("id"),
                      "version": entry.get("version")} if entry else None),
            "circuits": circuits.get(gid, []),
            "why": None if entry else
            "Spark has not filed this recording’s cue pairs yet.",
        })
    return out
