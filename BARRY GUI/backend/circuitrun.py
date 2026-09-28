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

from . import cfc, circuit, coupling, vacc, vaccrun

CACHE_SCHEMA = 1
#: The window lengths each kind actually reads. `pad_s` is kept for both:
#: a transition result still carries it, and `circuit.build` refuses pairs
#: whose carried parameters differ.
_HASHED = ("analysis_fs", "low", "high", "summary_hz", "max_lag_ms",
           "notch_hz", "pad_s")
_HASHED_TRANSITION = ("before_s", "after_s")

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
def params_hash(params, bad=(), blocked=()):
    """Everything that changes one pair's numbers, as 12 hex characters."""
    kind = params.get("kind") or "state"
    keep = {k: params.get(k) for k in _HASHED}
    if kind == "transition":
        keep.update({k: params.get(k) for k in _HASHED_TRANSITION})
    blob = json.dumps({
        "schema": CACHE_SCHEMA, "kind": kind, "params": keep,
        "methods": list(coupling.METHODS),
        "bad": sorted(int(c) for c in (bad or [])),
        "blocked": sorted(str(b) for b in (blocked or [])),
    }, sort_keys=True, default=str)
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


def _pair_key(prep, pid):
    return (prep["gid"], pid, prep["kind"], prep["phash"],
            prep["bank_version"])


# ==========================================================================
# One cue pair -- the same call here and on the node
# ==========================================================================
def _has_kind():
    try:
        return "kind" in inspect.signature(
            coupling.pair_connectivity).parameters
    except (TypeError, ValueError):
        return False


def compute_pair(folder, pair, drop, blocked, params, kind, progress=None):
    """`coupling.pair_connectivity` with the arguments Coupling's own run
    route gives it -- one place, called by a local run and by the node."""
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
                               spec.get("blocked"), params, kind)
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


def prepare(host, gid, cue_type, kind, body_params=None):
    """Everything one circuit needs, worked out before anything runs.

    JSON-able throughout, because it is also the run record a restart picks
    a VACC run up from. Raises `CircuitRunError` with the sentence and the
    code a route should answer with.
    """
    kind = (kind or "state").strip()
    if kind not in circuit.KINDS:
        raise CircuitRunError("The kind has to be state or transition, not "
                              "%r." % kind)
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
    here = (sm.get("here") or [None])[0]
    reg_paths = list(sm.get("paths") or []) or ([here] if here else [])

    pairs = []
    for i, ev, p in mine:
        pairs.append({
            "pair_id": i, "label": p.get("label"),
            "opener_t": p.get("opener_t"),
            "pair": plain(p), "drop": plain(host.drop(ev, bad)),
            "cached": cache_has(gid, i, kind, phash, bank_version),
        })

    subject = {
        "gid": gid, "project": sm.get("project"), "mouse": sm.get("mouse"),
        "session": sm.get("session"), "session_label": sm.get("label"),
        "phase": sm.get("phase"), "phase_n": sm.get("phase_n"),
        "run": sm.get("run"), "cue_type": cue_type,
        "cue_label": circuit.cue_label(cue_type), "window_kind": kind,
    }
    return plain({
        "gid": gid, "label": sm.get("label"), "rat": rat,
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
        "source": {"gid": gid, "session_label": sm.get("label"),
                   "bank_entry": entry.get("id"),
                   "bank_version": bank_version},
        "inputs": [{"kind": "bank", "entry": entry.get("id"),
                    "version": bank_version}],
        "cue_types": types,
    })


def artifact_params(prep):
    """What the artifact version records as its parameters: the analysis
    parameters verbatim, plus the hash that also covers bad channels and
    histology -- which is what "already made at these settings" compares."""
    return dict(prep["params"], inputs_hash=prep["phash"],
                bad_channels=prep["bad"],
                blocked_regions=sorted(prep["blocked"]))


def current_artifact(host, prep):
    rec = host.artifacts.find("circuit", circuit.subject_key(
        prep["gid"], prep["cue_type"], prep["kind"]))
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
            and plain(art.get("inputs") or []) == plain(prep["inputs"]))


def _rate(where):
    return cfc.rate_for("circuit pairs", where)


def local_seconds(prep):
    todo = prep["n_pairs"] - prep["n_cached"]
    if not prep.get("path"):
        return None
    return round(todo * _rate(cfc.volume_key(prep["path"])), 1)


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
    place = vacc_place(host, prep["gid"], wait)
    vacc_s = (round(todo * _rate(place["where"]), 1) if place["can"]
              else None)
    head = "%d cue pair%s" % (n, "" if n == 1 else "s")
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


def plan(host, gid, cue_type, kind, body_params=None):
    """The `/plan` response (contract section 6), minus `ok`."""
    prep = prepare(host, gid, cue_type, kind, body_params)
    grey = [{"region": r, "why": why}
            for r, why in circuit.grey_regions(prep["probe"])]
    art = current_artifact(host, prep)
    if art:
        art = {k: art[k] for k in ("artifact_id", "version", "version_id",
                                   "digest", "name", "nickname")}
        art["current"] = is_current(current_artifact(host, prep), prep)
    return {
        "gid": gid, "label": prep["label"], "rat": prep["rat"],
        "cue_type": prep["cue_type"], "cue_label": prep["cue_label"],
        "kind": prep["kind"],
        "pairs": [{"pair_id": p["pair_id"], "label": p["label"],
                   "opener_t": p["opener_t"], "cached": p["cached"]}
                  for p in prep["pairs"]],
        "n_pairs": prep["n_pairs"], "n_cached": prep["n_cached"],
        "params": param_specs(prep["kind"], prep["measured_pad_s"],
                              prep["transition_measured"],
                              prep["measured_before_s"],
                              prep["measured_after_s"]),
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
    }


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
        report(pid, status="running", step="reading")
        try:
            res = plain(compute_pair(prep["path"], p["pair"], p["drop"],
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


def _results_from_cache(prep):
    out = {}
    for p in prep["pairs"]:
        hit = cache_get(*_pair_key(prep, p["pair_id"]))
        if hit is not None:
            out[p["pair_id"]] = hit
    return out


def file_circuit(host, prep, results, computed_on, nickname=None, by=None):
    """Build the payload and file it: a new artifact, a new version, or a
    confirmation of the current one. The job result (contract section 6)."""
    got = [results[p["pair_id"]] for p in prep["pairs"]
           if p["pair_id"] in results]
    missing = [p["pair_id"] for p in prep["pairs"]
               if p["pair_id"] not in results]
    if not got:
        raise CircuitRunError(
            "None of the %d %s pairs could be computed, so there is no "
            "circuit to file." % (prep["n_pairs"], prep["cue_label"]), 409)
    payload = circuit.build(got, prep["probe"], prep["kind"],
                            prep["cue_type"], prep["params"], prep["source"],
                            of=prep["n_pairs"], computed_on=computed_on)
    arts = host.artifacts
    key = circuit.subject_key(prep["gid"], prep["cue_type"], prep["kind"])
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
                       "where": (computed_on or {}).get("kind")},
        }])
    except Exception:                                    # noqa: BLE001
        pass
    return {"ok": True, "artifact_id": rec["id"], "version": cur.get("v"),
            "version_id": cur.get("id"), "digest": cur.get("digest"),
            "name": rec.get("name"), "nickname": rec.get("nickname"),
            "new_version": new, "confirmed": not new,
            "n_pairs": len(got), "of": prep["n_pairs"],
            "missing": missing,
            "payload": payload, "computed_on": payload.get("computed_on")}


def _here(host):
    prov = {}
    try:
        prov = dict(host.provenance() or {})
    except Exception:                                    # noqa: BLE001
        pass
    return {"kind": "local", "machine": prov.get("machine"),
            "at": prov.get("at")}


def _small_spec(prep, where):
    return {"tool": "circuit", "gid": prep["gid"], "path": prep.get("path"),
            "cue_type": prep["cue_type"], "kind": prep["kind"],
            "where": where}


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
        job.begin("circuit pairs", of=todo, unit="pairs")
        results = run_pairs(
            job, prep, report=lambda pid, **k: job.member(pid, **k),
            tick=lambda n: job.tick("circuit pairs", n))
        on = dict(_here(host), cached=prep["n_cached"],
                  computed=len(results) - prep["n_cached"])
        return file_circuit(host, prep, results, on, nickname)

    job = cfc.start(_small_spec(prep, "local"),
                    [("circuit pairs", todo)], work, 1.0)
    _track(job, prep, "local")
    return job


def _vacc_spec(prep, todo):
    return {"path": prep["reg_path"], "gid": prep["gid"],
            "kind": prep["kind"], "params": prep["params"],
            "blocked": prep["blocked"],
            "pairs": [p["pair"] for p in todo],
            "drops": {str(p["pair_id"]): p["drop"] for p in todo}}


def _adopt_pairs(prep, out, report=None):
    """Put what the cluster computed into the cache, pair by pair."""
    report = report or (lambda pid, **k: None)
    for res in (out or {}).get("pairs") or []:
        pid = res.get("pair_id")
        if res.get("error"):
            report(pid, status="failed", step=None,
                   error=str(res["error"])[:200], why=str(res["error"])[:200])
            continue
        try:
            cache_put(*(_pair_key(prep, int(pid)) + (plain(res),)))
            report(pid, status="done", step=None)
        except Exception as exc:                         # noqa: BLE001
            report(pid, status="failed", step=None, error=str(exc)[:200],
                   why=str(exc)[:200])


def start_vacc(host, prep, nickname=None):
    """One circuit, its uncached pairs computed on the cluster."""
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
    got = file_circuit(host, prep, results, on, nickname)
    run.close_record("done")
    return got


def _start_filing_only(host, prep, nickname):
    def work(job):
        _init_pair_members(job, prep)
        results = _results_from_cache(prep)
        return file_circuit(host, prep, results,
                            dict(_here(host), cached=len(results),
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


def batch_plan(host, gids, cue_types="all", kind="state", body_params=None,
               where="vacc", keep_preps=False):
    """Which circuits a batch would make, which are already made at these
    settings, which cannot be made and why -- and what it costs, in total."""
    where = "local" if str(where or "").startswith("local") else "vacc"
    todo, already, blocked, preps = [], [], [], []
    gids = [g for g in (gids or []) if g]
    if not gids:
        raise CircuitRunError("Say which recordings: `gids` is empty.")
    # Parameters are checked once, up front: one set applies to a whole
    # batch, and a bad value is a refusal of the batch, not of each row.
    try:
        coupling.read_params(body_params or {}, kind=kind)
    except coupling.CouplingError as exc:
        raise CircuitRunError(str(exc), 400)
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
        want = _wanted_types(cue_types, have)
        if not want:
            blocked.append({"gid": gid, "why": (
                "It has no pairs of the cue types asked for; its pairings "
                "are %s." % ("; ".join(t["cue_label"] for t in have)
                             or "none"))})
            continue
        for ct in want:
            try:
                prep = prepare(host, gid, ct, kind, body_params)
            except CircuitRunError as exc:
                blocked.append({"gid": gid, "cue_type": ct, "why": str(exc)})
                continue
            art = current_artifact(host, prep)
            if is_current(art, prep):
                already.append({"gid": gid, "label": prep["label"],
                                "cue_type": ct,
                                "artifact_id": art["artifact_id"],
                                "version": art["version"],
                                "version_id": art["version_id"]})
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
            secs = round(n_todo * _rate(rate_where), 1)
            todo.append({"gid": gid, "label": prep["label"], "cue_type": ct,
                         "cue_label": prep["cue_label"],
                         "n_pairs": prep["n_pairs"],
                         "n_cached": prep["n_cached"], "seconds": secs})
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
                where="vacc", concurrency=None):
    """The batch: one job, one member row per (recording, cue type)."""
    got = batch_plan(host, gids, cue_types, kind, body_params, where,
                     keep_preps=True)
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
                   new_version=res["new_version"])
        return {"gid": prep["gid"], "cue_type": prep["cue_type"],
                "artifact_id": res["artifact_id"], "version": res["version"],
                "version_id": res["version_id"], "digest": res["digest"],
                "new_version": res["new_version"]}

    def summary(made, failed):
        return {"ok": True, "where": where, "n": len(rows),
                "made": made, "failed": failed,
                "already": got["already"], "blocked": got["blocked"],
                "sentence": got["sentence"]}

    if where == "local":
        def work(job):
            init(job)
            job.begin("circuit pairs", of=total_pairs, unit="pairs")
            count = [0]
            made, failed = [], []
            for prep in preps:
                job.check()
                mid = _member_id(prep)
                job.member(mid, status="running", step="reading")
                done_here = [0]

                def tick(n, mid=mid):
                    count[0] += 1
                    done_here[0] = n
                    job.member(mid, done=n)
                    job.tick("circuit pairs", count[0])
                try:
                    results = run_pairs(job, prep, tick=tick)
                    res = file_circuit(host, prep, results, dict(
                        _here(host), cached=prep["n_cached"],
                        computed=len(results) - prep["n_cached"]))
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
        job = cfc.start({"tool": "circuit", "batch": True, "where": "local",
                         "path": (preps[0].get("path") if preps else None)},
                        [("circuit pairs", total_pairs)], work, 1.0)
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
                    res = file_circuit(host, prep, _results_from_cache(prep),
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
            res = file_circuit(host, prep, _results_from_cache(prep),
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
        res = file_circuit(host, prep, _results_from_cache(prep),
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
            "nickname": a.get("nickname")})
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
