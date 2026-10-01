"""
monolith.py -- the Monolith: every coupling measure from 1 to 55 Hz,
Precon1 -> Precon4, computed on the VACC and pooled here.

The Drift panel's third tab drives it, one step at a time, one primary
button for whichever step comes next:

  1. Upload      the 48 folders (each rat-day's SPC, FP1 and FP2) to the
                 cluster -- Scratch (Jarvis Data) or Temp, asked every time,
                 Scratch first. Files already there at their size are
                 skipped, so pressing it again carries on where it stopped.
  2. Check       one listing of every folder in both places, compared file
                 by file with the copy here; and, once a run exists, where
                 each of its tasks is.
  3. Run         one slurm array, a task per rat-day x kind x band chunk,
                 at most 100 at once. Only rat-days whose recordings are
                 whole on the cluster go; it needs at least five rats.
  4. Fetch       only when pressed: the tasks' arrays come home in one
                 stream, and are pooled over rats here (`build`).
  5. View        the page (web/monolith.html), filed as a `monolith`
                 artifact in Results.

WHAT IS POOLED, AND HOW

Exactly the Precon drifts' rules (driftpool.py), applied to every entry --
window x band x method x region pair, plus each region's power and every
PAC cell. A rat-day is every cue pair of both pairings, blind to type; a
rat's change is Precon4 minus Precon1 of those means, its variance the two
squared standard errors; the changes are pooled DerSimonian-Laird and
tested Hartung-Knapp on k - 1 df; an entry with fewer than five rats is
shown and not tested; a rat with a single usable pair on a day leaves the
entry untested (there is no spread to put an error on), as it does there.
Minus FP is (cue - rest) per day, rest being the day's FP1+FP2 epochs. The
vectorised `pool` is checked against `drift.pool_rats` + `drift.hk_test`
in tools/check_monolith.py, and `entry_detail` recomputes any one entry
with those two functions and says if the two disagree.

p is uncorrected and every page that shows one says so. Points of interest
are single entries with p < .05, ranked by how many rats changed the same
way and then by p, at most three per region pair -- and an entry that is
the same finding as one already chosen (same window and method, within
2 Hz) is listed under it rather than taking a place.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tarfile
import threading
import time

import numpy as np

from . import circuit, circuitrun, coupling, drift, nlx, sweep, vacc, vaccupload

SCHEMA = "arc.monolith/1"
ANALYSIS = "precon1-4-sweep"
NAME = "Monolith · Precon1→4 · 1–55 Hz"
PROJECT = "DEWEY"
RATS = (3, 4, 6, 7, 8, 9, 10, 11)
EXCLUDED_RATS = {5: "no Precon4 recording, and no histology row"}
DAYS = ((1, "Precon1"), (4, "Precon4"))
DAY_NAMES = tuple(d for _n, d in DAYS)
MIN_RATS = 5
LAYERS = ("raw", "minus_fp")
LAYER_SAY = {
    "raw": "Each rat's own change, Precon4 − Precon1, of the cue-window value.",
    "minus_fp": "The same, after taking away that day's rest (FP1 + FP2) "
                "value: (cue − rest) on Precon4 minus (cue − rest) on "
                "Precon1.",
}
FOLDER_ROLES = ("SPC", "FP1", "FP2")

CONCURRENCY = 100
STATE_CHUNKS = 4
PARTITION = "short"
TASK_TIME = "02:00:00"
TASK_MEM = "6G"
TOOL_STAGES = ["sweep units"]

#: Measured on this desktop (2026-10-01, 12 regions, 66 pairs): seconds per
#: band per window, by window length; PAC per window. The cluster's cores
#: are of the same order; the estimate says so.
RATE_S = {"state": 15.6 / 58, "trans_slow": 4.45 / 13, "trans_fast": 3.3 / 45,
          "rest": 15.6 / 58, "pac": 2.2, "pac_rest": 2.2}

WINDOWS = list(sweep.STATE) + list(sweep.TRANSITION)
WINDOW_SAY = {"pre": "Baseline", "cue1": "Cue 1", "cue2": "Cue 2",
              "post": "After", "onset": "Onset", "switch": "Switch",
              "offset": "Offset"}
METHODS = list(sweep.ALL_METHODS)
METHOD_SAY = {
    "coherence": ("Coherence", "Magnitude-squared coherence, mean over the "
                  "band. Blind to delay; sees volume conduction."),
    "icoh": ("Imaginary coherence", "|imaginary part of coherency|, mean over "
             "the band. Zero for anything at zero lag."),
    "raw_cc": ("Raw cc", "Peak r of the band-passed traces within two cycles "
               "(signed)."),
    "env_cc": ("Envelope cc", "Peak r of the band's envelopes within two "
               "cycles (signed)."),
    "env_cc0": ("Amplitude r, zero lag", "Pearson r of the two envelopes at "
                "zero lag."),
    "orth_env": ("Orthogonalised envelope r", "Envelope r after removing "
                 "each signal's zero-lag share of the other (Hipp 2012)."),
    "plv": ("PLV", "Phase-locking value over the window."),
    "ppc": ("PPC", "Pairwise phase consistency: PLV without its "
            "sample-size bias."),
    "pli": ("PLI", "Phase-lag index: how consistently one leads."),
    "wpli": ("wPLI", "Weighted phase-lag index."),
    "dwpli": ("Debiased wPLI", "Debiased squared wPLI."),
    "gc_ab": ("Granger A→B", "Spectral Granger causality, first region to "
              "second (nats)."),
    "gc_ba": ("Granger B→A", "Spectral Granger causality, second region to "
              "first (nats)."),
    "gc_net": ("Granger net", "A→B minus B→A: positive means the first "
               "region drives the second more."),
}
QUANTITIES = ("est", "p", "k", "same", "se", "why")
WHY = {0: None, 1: "fewer than %d rats have it on both days" % MIN_RATS,
       2: "a rat had a single usable value on a day, so there is no spread "
          "to put an error on",
       3: "a rat gave the identical value in every cue pair",
       4: "every rat changed by exactly the same amount",
       5: "no rat has it on both days"}
TOP_N = 50
PER_PAIR = 3
SAME_HZ = 2
P_POINT = 0.05


#: The backend files a Monolith run depends on: what the node imports
#: (sweep, csc and theirs) and what plans and pools it here. A run is
#: refused while any of these has changed since Jarvis started -- the
#: cluster would be sent code this Jarvis has not loaded -- and not for an
#: edit to some other tool. tools/check_monolith.py imports the modules
#: afresh and fails if this list has fallen behind them.
CODE = ("cfc.py", "circuit.py", "circuitrun.py", "coupling.py", "csc.py",
        "demo.py", "drift.py", "lazyimp.py", "monolith.py", "nlx.py",
        "probes.py", "spark.py", "sweep.py", "sysinfo.py", "vacc.py",
        "vaccio.py", "vaccrun.py", "vaccupload.py")


class MonolithError(Exception):
    def __init__(self, message, code=400):
        Exception.__init__(self, message)
        self.code = code


# ==========================================================================
# Where things are kept
# ==========================================================================
_ROOT = None
_LOCK = threading.RLock()


def configure(logs_dir):
    global _ROOT
    _ROOT = os.path.join(os.path.abspath(logs_dir), ".cache", "monolith")
    os.makedirs(_ROOT, exist_ok=True)


def _path(*parts):
    if _ROOT is None:
        raise RuntimeError("monolith.configure was never called")
    return os.path.join(_ROOT, *parts)


def run_dir_local(rid):
    return _path("runs", vacc.check_rid(rid))


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, default=_np_default)
        fh.flush()
        os.fsync(fh.fileno())
    for i in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.15 * (i + 1))
    os.replace(tmp, path)


def _read_json(path, default=None):
    for i in range(5):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return default
        except (PermissionError, ValueError):
            time.sleep(0.1 * (i + 1))
    return default


def _np_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(repr(o))


def get_state():
    return _read_json(_path("state.json"), {}) or {}


def save_state(**patch):
    with _LOCK:
        st = get_state()
        for k, v in patch.items():
            if v is None:
                st.pop(k, None)
            else:
                st[k] = v
        _write_json(_path("state.json"), st)
        return st


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ==========================================================================
# The manifest: what goes, from where, to where
# ==========================================================================
def _manual(ev):
    """The event's hand exclusions, flat and per window, for the windows the
    node measures itself."""
    per, flat = coupling._csc_shape((ev or {}).get("excluded"))
    out = {"flat": sorted(flat)}
    for w, v in per.items():
        out[w] = sorted(v)
    return out


#: Which files of a recording go to the cluster: what Cheetah recorded, and
#: nothing processed into the folder afterwards (user, 2026-10-01).
#:
#:   every CSC* file   however it is named and wherever it sits -- some of
#:                     these recordings name their channels oddly, and a
#:                     channel left behind is a channel nobody can read there
#:   VT*.nvt/.mp4/.smi the video, continuations (VT1.0003.mp4) included
#:   Events*.nev       the TTLs
#:   CheetahLogFile*.txt, DataProcessingErrors*.nde, ConfigurationLog/*
#:                     Cheetah's own logs
#:
#: Anything else -- a .mat, a figure, a CSV, a folder of results -- stays
#: here. Recorded in the manifest, so a manifest made under another rule is
#: made again rather than trusted. (The node reads only the CSC channels it
#: recognises, by nlx's pattern; the rest travels for completeness.)
FILES_RULE = "cheetah-raw/2"
_RAW_TOP = re.compile(r"^(VT\d+[^/]*\.(nvt|mp4|smi)|Events[^/]*\.nev|"
                      r"CheetahLogFile[^/]*\.txt|DataProcessingErrors[^/]*\.nde)$",
                      re.IGNORECASE)


def is_sent(rel):
    """Whether a file (its path relative to the recording) goes."""
    parts = rel.split("/")
    name = parts[-1]
    if name.upper().startswith("CSC"):
        return True
    if len(parts) == 1:
        return bool(_RAW_TOP.match(name))
    return len(parts) == 2 and parts[0].lower() == "configurationlog"


def _files(local):
    """({rel: size} that go, {"n": files left here, "bytes": their size})."""
    sent, left_n, left_b = {}, 0, 0
    for rel, size, _full in vaccupload.local_files(local):
        if is_sent(rel):
            sent[rel] = size
        else:
            left_n += 1
            left_b += size
    return sent, {"n": left_n, "bytes": left_b}


def select_days(host):
    """{(rat, day name): gid} for the banked Precon1/Precon4 SPC
    recordings of the rats, and the sentences for what is not there."""
    rows = host.recordings(False) or []
    got, problems = {}, []
    for r in rows:
        if r.get("mouse") not in RATS or r.get("phase") != "Precon":
            continue
        day = dict(DAYS).get(r.get("phase_n"))
        if day is None or (r.get("run") or "SPC") != "SPC":
            continue
        gid = r.get("gid")
        if not gid or not host.entry(gid):
            continue
        key = (r["mouse"], day)
        if key in got and got[key] != gid:
            problems.append("r%d %s has two banked SPC recordings (%s, %s)"
                            % (key[0], day, got[key], gid))
            continue
        got[key] = gid
    for rat in RATS:
        for _n, day in DAYS:
            if (rat, day) not in got:
                problems.append("r%d %s: no banked SPC recording" % (rat, day))
    return got, problems


def build_manifest(host, cfg, progress=None):
    """Everything the run needs to know, worked out here, from the bank,
    the registry, histology and the cached rest clipping. Reads only (the
    rest clipping is measured if it was never cached)."""
    days, problems = select_days(host)
    roots = vacc.upload_roots(cfg)
    out_days, notes = [], list(problems)
    inputs = []
    gids = []
    for n, ((rat, day), gid) in enumerate(sorted(days.items())):
        if progress:
            progress(n, len(days), "r%d %s" % (rat, day))
        entry = host.entry(gid)
        sm = host.summary(gid) or {}
        spc = circuitrun.cued_folder(sm, entry)
        if not spc or not os.path.isdir(spc):
            notes.append("r%d %s: its SPC folder cannot be opened here" %
                         (rat, day))
            continue
        bad = sorted(int(c) for c in (sm.get("bad_channels") or []))
        _rat, probe = host.probe(sm)
        blocked = host.blocked(probe) or {}
        tm, tb, ta = host.measured_transition(entry)
        fast_banked = bool(tm) and abs(float(tb) - sweep.FAST_LEN[0]) < 1e-9 \
            and abs(float(ta) - sweep.FAST_LEN[1]) < 1e-9
        units = []
        for i, ev in enumerate(entry.get("events") or [], start=1):
            pair = host.pair(ev, i)
            ct = circuit.cue_type_of(pair)
            if ct is None:
                continue
            units.append({
                "id": "p%02d" % i, "pair_id": i, "cue_type": ct,
                "cue_label": circuit.cue_label(ct),
                "label": pair.get("label"),
                "pair": {k: pair.get(k) for k in ("pair_id", "opener_t",
                                                  "closer_t", "offset_t",
                                                  "label")},
                "drop": circuitrun.plain(host.drop(ev, bad)),
                "manual": _manual(ev)})
        rest_units, fps = [], []
        try:
            prep = circuitrun.prepare_rest(host, gid)
            clip = circuitrun.rest_clipping(prep)
            circuitrun.apply_rest_clipping(prep, clip)
            for p in prep["pairs"]:
                rest_units.append({
                    "id": "e%02d" % p["pair_id"], "pair_id": p["pair_id"],
                    "label": p["label"], "run": p["run"], "fp_gid": p["fp"],
                    "local": p["path"], "pair": p["pair"], "drop": p["drop"],
                    "why": p.get("unmeasured_why")})
            seen = set()
            for p in prep["pairs"]:
                if p["path"] in seen:
                    continue
                seen.add(p["path"])
                fps.append({"role": p["run"], "gid": p["fp"],
                            "local": p["path"]})
            notes.extend("r%d %s: %s" % (rat, day, x)
                         for x in prep.get("fp_notes") or [])
        except circuitrun.CircuitRunError as exc:
            notes.append("r%d %s: no rest epochs (%s); its minus-FP layer "
                         "leaves this rat out" % (rat, day, exc))
        folders = [{"role": "SPC", "gid": gid, "local": spc}] + fps
        for f in folders:
            files, left = _files(f["local"])
            f["files"] = files
            f["n_files"] = len(files)
            f["bytes"] = sum(files.values())
            f["left_here"] = left
            if not files:
                f.setdefault("why", "no CSC files in it")
            f["remote"] = {}
            for dest, r in roots.items():
                try:
                    f["remote"][dest] = vaccupload.destination(
                        cfg, {"project": sm.get("project") or PROJECT},
                        f["local"], r["root"])
                except vaccupload.UploadError as exc:
                    f.setdefault("why", str(exc))
        out_days.append({
            "rat": rat, "day": day, "gid": gid,
            "label": circuitrun.session_label(sm, spc),
            "bad": bad, "blocked": blocked,
            "grey": sorted(blocked),
            "fast_banked": fast_banked,
            "units": units, "rest": rest_units, "folders": folders,
            "bank": {"entry": entry.get("id"), "version": entry.get("version")},
        })
        inputs.append({"kind": "bank", "entry": entry.get("id"),
                       "version": entry.get("version")})
        gids.append(gid)
    man = {
        "schema": SCHEMA, "at": now_iso(), "rats": list(RATS),
        "excluded": {"r%d" % k: v for k, v in EXCLUDED_RATS.items()},
        "days": out_days, "notes": notes, "inputs": inputs, "gids": gids,
        "regions": sweep.regions(),
        "roots": roots, "files_rule": FILES_RULE,
    }
    man["digest"] = _digest(man)
    return man


def _digest(obj):
    blob = json.dumps({k: v for k, v in obj.items() if k not in ("at",
                                                                  "digest")},
                      sort_keys=True, default=_np_default)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def manifest():
    """The manifest, or None when there is none made under the current
    schema and file rule -- so every step works it out again rather than
    using one that would send what it should not."""
    man = _read_json(_path("manifest.json"))
    if not man or man.get("schema") != SCHEMA or \
            man.get("files_rule") != FILES_RULE:
        return None
    return man


def save_manifest(man):
    _write_json(_path("manifest.json"), man)


def folders_of(man):
    for d in man.get("days") or []:
        for f in d.get("folders") or []:
            yield d, f


def manifest_brief(man):
    if not man:
        return None
    days = man.get("days") or []
    n_bytes = sum(f["bytes"] for _d, f in folders_of(man))
    left = [f.get("left_here") or {} for _d, f in folders_of(man)]
    return {
        "at": man.get("at"), "digest": man.get("digest"),
        "n_days": len(days), "n_folders": sum(1 for _ in folders_of(man)),
        "bytes": n_bytes, "files_rule": man.get("files_rule"),
        "n_files": sum(f["n_files"] for _d, f in folders_of(man)),
        "left_here": {"n": sum(x.get("n") or 0 for x in left),
                      "bytes": sum(x.get("bytes") or 0 for x in left)},
        "n_units": sum(len(d["units"]) for d in days),
        "n_rest": sum(len(d["rest"]) for d in days),
        "notes": man.get("notes") or [],
        "excluded": man.get("excluded"),
        "rats": sorted({d["rat"] for d in days}),
        "days": [{"rat": d["rat"], "day": d["day"], "gid": d["gid"],
                  "label": d["label"], "n_units": len(d["units"]),
                  "n_rest": len(d["rest"]), "grey": d.get("grey") or [],
                  "folders": [{"role": f["role"], "local": f["local"],
                               "n_files": f["n_files"], "bytes": f["bytes"],
                               "remote": f.get("remote") or {},
                               "why": f.get("why")}
                              for f in d["folders"]]} for d in days],
        "roots": man.get("roots") or {},
    }


# ==========================================================================
# What is on the cluster
# ==========================================================================
def sizes_many(remote, dirs):
    """{dir: {rel: size}} -- one listing for many folders."""
    many = getattr(remote, "sizes_many", None)
    if many:
        return many(list(dirs))
    return {d: remote.sizes(d) for d in dirs}


def folder_state(local_files, there):
    """complete | partial | missing, and how much of it is there."""
    have = sum(1 for rel, size in local_files.items()
               if there.get(rel) == size)
    n = len(local_files)
    b = sum(size for rel, size in local_files.items()
            if there.get(rel) == size)
    state = ("complete" if n and have == n else
             "missing" if not there else "partial")
    return {"state": state, "have": have, "of": n, "bytes_have": b}


def check_data(man, listing, prefer=None):
    """Per folder, per place: is it whole there? And per rat-day, where each
    folder will be read from (the preferred place when whole there)."""
    order = [prefer] if prefer else []
    for d in ("scratch", "temp"):
        if d not in order:
            order.append(d)
    days = []
    for d in man.get("days") or []:
        rows = []
        for f in d["folders"]:
            per = {}
            for dest, rdir in (f.get("remote") or {}).items():
                per[dest] = folder_state(f["files"], listing.get(rdir) or {})
            use = next((x for x in order if (per.get(x) or {}).get("state")
                        == "complete"), None)
            rows.append({"role": f["role"], "gid": f["gid"], "at": per,
                         "use": use,
                         "remote": (f.get("remote") or {}).get(use)})
        spc = next((r for r in rows if r["role"] == "SPC"), None)
        fp_ok = [r for r in rows if r["role"] != "SPC"]
        days.append({"rat": d["rat"], "day": d["day"], "gid": d["gid"],
                     "folders": rows,
                     "spc_ready": bool(spc and spc["use"]),
                     "rest_ready": bool(fp_ok) and all(r["use"]
                                                       for r in fp_ok)})
    ready_rats = sorted({x["rat"] for x in days if x["spc_ready"]
                         and all(y["spc_ready"] for y in days
                                 if y["rat"] == x["rat"])
                         and sum(1 for y in days if y["rat"] == x["rat"])
                         == len(DAYS)})
    n_folders = sum(len(x["folders"]) for x in days)
    n_ready = sum(1 for x in days for r in x["folders"] if r["use"])
    return {"days": days, "ready_rats": ready_rats,
            "n_folders": n_folders, "n_ready": n_ready,
            "can_run": len(ready_rats) >= MIN_RATS}


# ==========================================================================
# The tasks
# ==========================================================================
def _chunks(seq, n):
    seq = list(seq)
    k = int(math.ceil(len(seq) / float(n)))
    return [seq[i:i + k] for i in range(0, len(seq), k)]


def plan_tasks(man, chk):
    """Every task of the run: [{key, rat, day, kind, chunk, spec, est_s}].

    A rat goes only when both its days' SPC are whole on the cluster; its
    rest goes when both FP folders are."""
    by = {(d["rat"], d["day"]): d for d in man.get("days") or []}
    ready = {(x["rat"], x["day"]): x for x in chk["days"]}
    rats = set(chk["ready_rats"])
    tasks = []
    names = sweep.regions()
    for (rat, day), d in sorted(by.items()):
        if rat not in rats:
            continue
        rd = ready[(rat, day)]
        where = {r["role"]: r["remote"] for r in rd["folders"]}
        spc = where.get("SPC")
        base = {"blocked": d["blocked"], "bad": d["bad"], "regions": names,
                "rat": rat, "day": day, "gid": d["gid"]}
        cue_units = [{"id": u["id"], "pair": u["pair"], "drop": u["drop"],
                      "manual": u["manual"]} for u in d["units"]]

        def add(kind, chunk, bands, units, folder=None):
            key = "r%d_%s_%s%s" % (rat, day, kind,
                                   "" if chunk is None else "_%d" % chunk)
            spec = dict(base, kind=kind, bands=bands, units=units,
                        folder=folder,
                        task={"rat": rat, "day": day, "kind": kind,
                              "chunk": chunk, "key": key})
            n_w = (4 if kind in ("state", "pac") else
                   3 if kind.startswith("trans") else 1)
            per = RATE_S[kind] * (1 if kind.startswith("pac")
                                  else len(bands or []))
            tasks.append({"key": key, "rat": rat, "day": day, "kind": kind,
                          "chunk": chunk, "n_units": len(units),
                          "est_s": round(len(units) * n_w * per, 1),
                          "spec": spec})

        if cue_units:
            for ci, bands in enumerate(_chunks(sweep.bands_for("state"),
                                               STATE_CHUNKS)):
                add("state", ci, bands, cue_units, spc)
            add("trans_slow", None, sweep.bands_for("trans_slow"), cue_units,
                spc)
            fast_units = cue_units if d.get("fast_banked") else [
                dict(u, drop=None, why="this recording's transition "
                     "windows were not banked at -1/+2 s") for u in cue_units]
            add("trans_fast", None, sweep.bands_for("trans_fast"), fast_units,
                spc)
            add("pac", None, [], cue_units, spc)
        if rd["rest_ready"] and d["rest"]:
            fp_where = {r["gid"]: r["remote"] for r in rd["folders"]
                        if r["role"] != "SPC"}
            rest_units = [{"id": u["id"], "pair": u["pair"], "drop": u["drop"],
                           "why": u.get("why"),
                           "folder": fp_where.get(u["fp_gid"])}
                          for u in d["rest"]]
            add("rest", None, sweep.bands_for("rest"), rest_units)
            add("pac_rest", None, [], rest_units)
    return tasks


def cost(tasks):
    cpu = sum(t["est_s"] for t in tasks)
    longest = max([t["est_s"] for t in tasks] or [0])
    waves = max(1, int(math.ceil(len(tasks) / float(CONCURRENCY))))
    wall = max(longest, cpu / float(min(CONCURRENCY, max(1, len(tasks)))))
    return {"n_tasks": len(tasks), "cpu_s": round(cpu), "longest_s":
            round(longest), "wall_s": round(wall), "waves": waves,
            "concurrency": CONCURRENCY, "partition": PARTITION,
            "time": TASK_TIME, "mem": TASK_MEM}


# ==========================================================================
# On the cluster
# ==========================================================================
def run_dir_remote(cfg, dest, rid):
    """Where a run's specs, code, logs and arrays live: beside the data."""
    vacc.check_rid(rid)
    if dest == "temp":
        root = (cfg.get("temp") or vacc._temp_of(cfg))["data_path"]
        return vacc._remote_path(root, "_monolith", rid)
    return vacc._remote_path(cfg.get("scratch") or
                             (cfg.get("shared") or {}).get("root") or ".",
                             "monolith", rid)


def submit_script(cfg, rdir, rid, n, indices=None):
    arr = (",".join(str(i) for i in indices) if indices
           else "0-%d" % max(0, n - 1))
    return (
        "#!/bin/bash\n"
        "#SBATCH --job-name=%(rid)s\n"
        "#SBATCH --array=%(arr)s%%%(cap)d\n"
        "%(acct)s"
        "#SBATCH --partition=%(part)s\n"
        "#SBATCH --time=%(time)s\n"
        "#SBATCH --mem=%(mem)s\n"
        "#SBATCH --cpus-per-task=1\n"
        "#SBATCH --nodes=1\n"
        "#SBATCH --ntasks=1\n"
        "#SBATCH --output=%(rd)s/logs/%%A_%%a.out\n"
        "#SBATCH --mail-type=NONE\n"
        "%(pre)s\n"
        "export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1\n"
        "cd %(rd)s/code\n"
        "exec python vacc_run.py %(rd)s/spec_${SLURM_ARRAY_TASK_ID}.json\n"
    ) % {"rid": rid, "arr": arr, "cap": CONCURRENCY,
         "acct": vacc.sbatch_account(cfg), "part": PARTITION,
         "time": TASK_TIME, "mem": TASK_MEM, "rd": rdir,
         "pre": vacc.activate(cfg)}


def bundle_of(rid, i, task, rdir):
    spec = dict(task["spec"], out="%s/out/%s.npz" % (rdir, task["key"]))
    return {"rid": "%s_%d" % (rid, i), "tool": "sweep", "spec": spec,
            "plan": {}, "stages": TOOL_STAGES, "report": None}


def _tar_of(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for name, data in files:
            data = data.encode("utf-8") if isinstance(data, str) else data
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = int(time.time())
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def submit(cfg, tasks, dest, app_dir, ssh=None):
    """Push the code, write every spec, submit one array. Returns the run
    record (rid, array id, where, tasks)."""
    if not tasks:
        raise MonolithError("There is nothing to run: no rat has both days "
                            "whole on the cluster.", 409)
    run = vacc._runner(cfg, ssh)
    pushed = vacc.push_code(cfg, app_dir) if ssh is None else {"sha256": None}
    rid = vacc.new_rid()
    rdir = run_dir_remote(cfg, dest, rid)
    files = [("spec_%d.json" % i, json.dumps(bundle_of(rid, i, t, rdir)))
             for i, t in enumerate(tasks)]
    files.append(("submit.sh", submit_script(cfg, rdir, rid, len(tasks))))
    blob = _tar_of(files)
    code = vacc._remote_path(cfg.get("workspace") or ".", "code")
    script = ("set -e; mkdir -p %(rd)s; cd %(rd)s; tar -xf -; "
              "mkdir -p out logs; rm -rf code; cp -r %(code)s code; "
              "sbatch --parsable submit.sh"
              % {"rd": vacc.q(rdir), "code": vacc.q(code)})
    out = run("bash -c %s" % vacc.q(script), stdin=blob, timeout=300)
    array_id = None
    for line in reversed((out or "").strip().splitlines()):
        got = line.strip().split(";")[0].strip()
        if got.isdigit():
            array_id = got
            break
    if not array_id:
        raise MonolithError("The cluster did not return an array job id: %s"
                            % (out or "nothing")[:300], 502)
    return {
        "rid": rid, "dest": dest, "rdir": rdir,
        "arrays": [{"id": array_id, "indices": None, "at": now_iso()}],
        "submitted_at": now_iso(), "code": pushed.get("sha256"),
        "tasks": [{"i": i, "key": t["key"], "rat": t["rat"], "day": t["day"],
                   "kind": t["kind"], "chunk": t["chunk"],
                   "n_units": t["n_units"], "est_s": t["est_s"]}
                  for i, t in enumerate(tasks)],
        "cost": cost(tasks),
    }


def resubmit(cfg, run, indices, ssh=None):
    """Run the given tasks again, from the same specs and code."""
    if not indices:
        raise MonolithError("No task needs running again.", 409)
    r = vacc._runner(cfg, ssh)
    sh = submit_script(cfg, run["rdir"], run["rid"], len(run["tasks"]),
                       indices=sorted(indices))
    script = ("set -e; cd %(rd)s; cat > submit_again.sh; "
              "sbatch --parsable submit_again.sh" % {"rd": vacc.q(run["rdir"])})
    out = r("bash -c %s" % vacc.q(script), stdin=sh, timeout=120)
    array_id = None
    for line in reversed((out or "").strip().splitlines()):
        got = line.strip().split(";")[0].strip()
        if got.isdigit():
            array_id = got
            break
    if not array_id:
        raise MonolithError("The cluster did not return an array job id: %s"
                            % (out or "nothing")[:300], 502)
    run["arrays"].append({"id": array_id, "indices": sorted(indices),
                          "at": now_iso()})
    return run


def poll(cfg, run, ssh=None):
    """Where every task is, in one call: slurm's word for each, which have
    answered, and how big the arrays waiting to come home are."""
    r = vacc._runner(cfg, ssh)
    ids = ",".join(a["id"] for a in run["arrays"])
    script = (
        "sacct -n -X -j %(ids)s -o 'JobID,State' -P 2>/dev/null\n"
        "echo '--'\n"
        "ls -1 %(rd)s/ 2>/dev/null | grep '^result_' \n"
        "echo '--'\n"
        "du -sb %(rd)s/out 2>/dev/null | cut -f1\n"
        "echo '--'\n"
    ) % {"ids": vacc.q(ids), "rd": vacc.q(run["rdir"])}
    raw = r("bash -s", stdin=script, timeout=90)
    parts = (raw or "").split("--\n")
    sacct = parts[0] if parts else ""
    results = parts[1] if len(parts) > 1 else ""
    du = parts[2] if len(parts) > 2 else ""
    from . import vaccrun
    by_array = {}
    for line in sacct.splitlines():
        line = line.strip()
        if not line:
            continue
        bits = line.split("|")
        jid = bits[0].split(".")[0]
        st = vacc.read_state(bits[1] if len(bits) > 1 else "")
        aid = jid.split("_")[0]
        if "_[" in jid:
            for i in vaccrun._task_range(jid.split("_[", 1)[1]):
                by_array.setdefault(aid, {}).setdefault(i, st)
        elif "_" in jid:
            try:
                by_array.setdefault(aid, {})[int(jid.rsplit("_", 1)[1])] = st
            except ValueError:
                pass
    answered = set()
    for line in results.splitlines():
        line = line.strip()
        if line.startswith("result_") and line.endswith(".json"):
            try:
                answered.add(int(line[len("result_"):-len(".json")]))
            except ValueError:
                pass
    try:
        out_bytes = int(du.strip().splitlines()[0]) if du.strip() else 0
    except (ValueError, IndexError):
        out_bytes = 0
    states = {}
    for a in run["arrays"]:
        idx = a.get("indices") or range(len(run["tasks"]))
        for i in idx:
            st = (by_array.get(a["id"]) or {}).get(i)
            if st:
                states[i] = st
    return summarize(run, states, answered, out_bytes)


def summarize(run, states, answered, out_bytes=0):
    rows, tally = [], {"done": 0, "running": 0, "queued": 0, "failed": 0,
                       "unknown": 0}
    for t in run["tasks"]:
        i = t["i"]
        st = states.get(i)
        if i in answered:
            what, why = "done", None
        else:
            o = vacc.outcome_for(st) if st else None
            if not st:
                what, why = "unknown", None
            elif o is None:
                what = "running" if st == "RUNNING" else "queued"
                why = None
            elif o[0] == "done":
                what, why = "failed", ("finished without writing its answer; "
                                       "its log is logs/%s_%d.out"
                                       % (run["arrays"][-1]["id"], i))
            else:
                what, why = "failed", o[1] or o[0]
        tally[what] += 1
        rows.append({"i": i, "key": t["key"], "state": what,
                     "slurm": st, "why": why})
    n = len(run["tasks"])
    return {"tasks": rows, "tally": tally, "n": n,
            "answered": sorted(answered), "out_bytes": out_bytes,
            "finished": tally["done"] + tally["failed"] == n,
            "active": tally["running"] + tally["queued"] > 0,
            "at": now_iso()}


def log_tails(cfg, run, indices, lines=12, ssh=None):
    """The last lines of some tasks' logs -- what a failure said."""
    r = vacc._runner(cfg, ssh)
    bits = []
    for i in sorted(indices)[:10]:
        bits.append("echo '@@ %d'; tail -n %d %s/logs/*_%d.out 2>/dev/null "
                    "| tail -n %d" % (i, lines, vacc.q(run["rdir"]), i, lines))
    if not bits:
        return {}
    raw = r("bash -s", stdin="\n".join(bits) + "\n", timeout=60)
    out, cur = {}, None
    for line in (raw or "").splitlines():
        if line.startswith("@@ "):
            cur = int(line[3:])
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v)[-1500:] for k, v in out.items()}


def cancel(cfg, run, ssh=None):
    for a in run.get("arrays") or []:
        try:
            vacc.cancel(cfg, a["id"], run["rid"], ssh=ssh)
        except Exception:                                # noqa: BLE001
            pass


def fetch(cfg, run, into, progress=None, stop=None):
    """Every answer, home, in one stream: a tar of out/ and the result
    files, written straight to disk (never through a pipe held in memory),
    then unpacked into `into`."""
    os.makedirs(into, exist_ok=True)
    tar_path = os.path.join(into, "fetch.tar")
    script = ("cd %s && tar -cf - out $(ls result_*.json 2>/dev/null)"
              % vacc.q(run["rdir"]))
    cmd = vacc.ssh_cmd(cfg, script)
    err_path = tar_path + ".err"
    with open(tar_path, "wb") as fh, open(err_path, "wb") as eh:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=fh,
                                stderr=eh, **vacc.popen_kwargs())
        try:
            while proc.poll() is None:
                if stop and stop():
                    proc.kill()
                    raise MonolithError("Stopped.", 409)
                if progress:
                    try:
                        progress(os.path.getsize(tar_path))
                    except OSError:
                        pass
                time.sleep(0.5)
        except BaseException:
            try:
                proc.kill()
            except Exception:                            # noqa: BLE001
                pass
            raise
    if proc.returncode != 0:
        with open(err_path, "rb") as eh:
            err = eh.read().decode("utf-8", "replace")
        raise MonolithError("Bringing the answers home failed: %s"
                            % (err.strip() or "no reason given")[:300], 502)
    if progress:
        progress(os.path.getsize(tar_path))
    return unpack(tar_path, into)


def unpack(tar_path, into):
    n = 0
    with tarfile.open(tar_path, "r") as tar:
        for m in tar.getmembers():
            name = m.name.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                continue
            if not (m.isfile() or m.isdir()):
                continue
            tar.extract(m, into, filter="data")
            n += m.isfile()
    os.remove(tar_path)
    return n


# ==========================================================================
# Pooling: vectorised drift.pool_rats + drift.hk_test
# ==========================================================================
def day_stats(X):
    """Over the first axis, ignoring NaN: (mean, se2, n). se2 is NaN where
    n < 2 -- "no spread", which the pooling reads as untestable."""
    X = np.asarray(X, dtype=np.float64)
    ok = np.isfinite(X)
    n = ok.sum(axis=0)
    s = np.where(ok, X, 0.0).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(n > 0, s / np.maximum(n, 1), np.nan)
        dev = np.where(ok, X - mean, 0.0)
        var = np.where(n >= 2, (dev * dev).sum(axis=0) / np.maximum(n - 1, 1),
                       np.nan)
        se2 = np.where(n >= 2, var / np.maximum(n, 1), np.nan)
    return mean, se2, n


def stdtr_p(t, df):
    from scipy.special import stdtr
    return 2.0 * stdtr(df, -np.abs(t))


def pool(Y, V):
    """Every entry at once. `Y` (rats, ...) each rat's change, NaN where the
    rat does not have the entry; `V` its variance, NaN where it has none.
    Returns {est, p, k, same, se, why} -- see QUANTITIES and WHY."""
    Y = np.asarray(Y, dtype=np.float64)
    V = np.asarray(V, dtype=np.float64)
    present = np.isfinite(Y)
    k = present.sum(axis=0)
    vnone = (present & ~np.isfinite(V)).any(axis=0)
    vzero = (present & np.isfinite(V) & (V == 0)).any(axis=0)
    y0 = np.where(present, Y, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        plain = np.where(k > 0, y0.sum(axis=0) / np.maximum(k, 1), np.nan)
        Vs = np.where(present & np.isfinite(V) & (V > 0), V, np.inf)
        w = np.where(present, 1.0 / Vs, 0.0)
        sw = w.sum(axis=0)
        yfe = (w * y0).sum(axis=0) / sw
        q = (w * (y0 - yfe) ** 2).sum(axis=0)
        c = sw - (w * w).sum(axis=0) / sw
        tau2 = np.where((k >= 2) & (c > 0),
                        np.maximum(0.0, (q - (k - 1)) / c), 0.0)
        wr = np.where(present, 1.0 / (Vs + tau2), 0.0)
        swr = wr.sum(axis=0)
        mean = (wr * y0).sum(axis=0) / swr
        dl_ok = ~vnone & ~vzero & (k > 0)
        est = np.where(dl_ok, mean, plain)
        ss = (wr * (y0 - est) ** 2).sum(axis=0)
        var = ss / ((k - 1) * swr)
        se = np.sqrt(var)
        t = est / se
    testable = dl_ok & (k >= MIN_RATS) & (k >= 2) & np.isfinite(var) & \
        (var > 0)
    p = np.full(est.shape, np.nan)
    if testable.any():
        p[testable] = stdtr_p(t[testable], (k - 1)[testable])
    why = np.zeros(est.shape, dtype=np.uint8)
    why[(k > 0) & ~testable] = 4
    why[(k > 0) & vzero] = 3
    why[(k > 0) & vnone] = 2
    why[(k > 0) & (k < MIN_RATS)] = 1
    why[k == 0] = 5
    sgn = np.sign(est)
    same = (present & (Y != 0) & (np.sign(np.where(present, Y, 0)) == sgn)
            & (sgn != 0)).sum(axis=0)
    return {"est": est, "p": p, "k": k.astype(np.float64),
            "same": same.astype(np.float64),
            "se": np.where(testable, se, np.nan), "why": why}


def layer_changes(cue, rest, layer):
    """Per rat (Y, V) from per rat-day statistics.

    `cue[(rat, day)]` = (mean, se2, n) with the entry axes; `rest[(rat,
    day)]` the same for rest, broadcastable to them, or None."""
    rats = sorted({r for r, _d in cue})
    shape = next(iter(cue.values()))[0].shape
    Y = np.full((len(rats),) + shape, np.nan)
    V = np.full((len(rats),) + shape, np.nan)
    for i, rat in enumerate(rats):
        xs, vs = [], []
        for day in DAY_NAMES:
            got = cue.get((rat, day))
            if got is None:
                xs = None
                break
            m, s2, n = got
            x, v = m, s2
            ok = n > 0
            if layer == "minus_fp":
                rs = rest.get((rat, day))
                if rs is None:
                    xs = None
                    break
                rm, rs2, rn = rs
                x = m - rm
                v = s2 + rs2
                ok = ok & (rn > 0)
            xs.append(np.where(ok, x, np.nan))
            vs.append(np.where(ok, v, np.nan))
        if xs is None:
            continue
        Y[i] = xs[1] - xs[0]
        V[i] = vs[0] + vs[1]
    return rats, Y, V


# ==========================================================================
# Building: the arrays, the pooled layers, the points, the artifact
# ==========================================================================
def _bi(bands):
    return [sweep.BAND_IDS.index(b) for b in bands]


def assemble(man, run, raw_dir, out_dir, progress=None):
    """Every task's arrays into one set per rat-day, saved as .npy:
    `<rat>_<day>_{edges,power,pac,wires_*}.npy` (cue pairs, in manifest
    order) and the same with `_rest`. Returns what was filled and what
    was not."""
    os.makedirs(os.path.join(out_dir, "days"), exist_ok=True)
    R = len(sweep.regions())
    P = len(sweep.pairs_of(list(range(R))))
    B = len(sweep.BAND_IDS)
    M = len(sweep.ALL_METHODS)
    C = len(sweep.PAC_CELLS)
    tasks = {t["key"]: t for t in run["tasks"]}
    by_day = {}
    for key, t in tasks.items():
        by_day.setdefault((t["rat"], t["day"]), []).append(t)
    filled, missing, refusals = [], [], []
    days = {(d["rat"], d["day"]): d for d in man["days"]}
    for n, ((rat, day), ts) in enumerate(sorted(by_day.items())):
        if progress:
            progress(n, len(by_day), "r%d %s" % (rat, day))
        d = days[(rat, day)]
        U = len(d["units"])
        Ur = len(d["rest"])
        uix = {u["id"]: i for i, u in enumerate(d["units"])}
        rix = {u["id"]: i for i, u in enumerate(d["rest"])}
        E = np.full((U, 7, B, M, P), np.nan, np.float32)
        Pw = np.full((U, 7, B, R), np.nan, np.float32)
        PAC = np.full((U, 4, C, R * R), np.nan, np.float32)
        Wst = np.full((U, 4, R), -1, np.int16)
        Wsl = np.full((U, 3, R), -1, np.int16)
        Wfa = np.full((U, 3, R), -1, np.int16)
        Er = np.full((Ur, 1, B, M, P), np.nan, np.float32)
        Pwr = np.full((Ur, 1, B, R), np.nan, np.float32)
        PACr = np.full((Ur, 1, C, R * R), np.nan, np.float32)
        Wr = np.full((Ur, 1, R), -1, np.int16)
        for t in ts:
            path = os.path.join(raw_dir, "out", t["key"] + ".npz")
            if not os.path.isfile(path):
                missing.append(t["key"])
                continue
            arrays, meta = sweep.load_task(path)
            refusals.extend(dict(x, task=t["key"]) for x in meta.get("why")
                            or [])
            kind = meta["kind"]
            rest = kind in ("rest", "pac_rest")
            index = rix if rest else uix
            rows = [index.get(u) for u in meta["units"]]
            if kind.startswith("pac"):
                for j, i in enumerate(rows):
                    if i is None:
                        continue
                    (PACr if rest else PAC)[i] = arrays["values"][j]
                    if rest:
                        Wr[i] = arrays["wires"][j]
                filled.append(t["key"])
                continue
            bi = _bi(meta["bands"])
            v = arrays["values"]                       # (U, W, b, 13, P)
            pw = arrays["power"]
            w0 = {"state": 0, "trans_slow": 4, "trans_fast": 4,
                  "rest": 0}[kind]
            nw = v.shape[1]
            tgtE, tgtP = (Er, Pwr) if rest else (E, Pw)
            for j, i in enumerate(rows):
                if i is None:
                    continue
                for wj in range(nw):
                    tgtE[i, w0 + wj, bi, :len(sweep.EDGE_METHODS)] = v[j, wj]
                    tgtP[i, w0 + wj, bi] = pw[j, wj]
                wt = {"state": Wst, "trans_slow": Wsl, "trans_fast": Wfa,
                      "rest": Wr}[kind]
                wt[i] = arrays["wires"][j]
            filled.append(t["key"])
        ga, gb = sweep.EDGE_METHODS.index("gc_ab"), \
            sweep.EDGE_METHODS.index("gc_ba")
        gn = sweep.ALL_METHODS.index("gc_net")
        E[:, :, :, gn] = E[:, :, :, ga] - E[:, :, :, gb]
        Er[:, :, :, gn] = Er[:, :, :, ga] - Er[:, :, :, gb]
        base = os.path.join(out_dir, "days", "r%d_%s" % (rat, day))
        for name, arr in (("edges", E), ("power", Pw), ("pac", PAC),
                          ("wires_state", Wst), ("wires_slow", Wsl),
                          ("wires_fast", Wfa), ("edges_rest", Er),
                          ("power_rest", Pwr), ("pac_rest", PACr),
                          ("wires_rest", Wr)):
            np.save(base + "_" + name + ".npy", arr)
    return {"filled": filled, "missing": missing, "refusals": refusals}


def _load_day(out_dir, rat, day, name, mmap=None):
    path = os.path.join(out_dir, "days", "r%d_%s_%s.npy" % (rat, day, name))
    if not os.path.isfile(path):
        return None
    return np.load(path, mmap_mode=mmap)


def pooled(out_dir, man, what):
    """{layer: {quantity: array}} for edges, power or pac."""
    cue_name, rest_name = {"edges": ("edges", "edges_rest"),
                           "power": ("power", "power_rest"),
                           "pac": ("pac", "pac_rest")}[what]
    cue, rest = {}, {}
    for d in man["days"]:
        key = (d["rat"], d["day"])
        X = _load_day(out_dir, d["rat"], d["day"], cue_name)
        if X is None or not X.shape[0]:
            continue
        cue[key] = day_stats(X)
        Xr = _load_day(out_dir, d["rat"], d["day"], rest_name)
        if Xr is not None and Xr.shape[0]:
            m, s2, n = day_stats(Xr)
            # Rest is one window; it stands against every cue window.
            rest[key] = (m, s2, n)
    out = {}
    for layer in LAYERS:
        if not cue:
            continue
        rats, Y, V = layer_changes(cue, rest, layer)
        got = pool(Y, V)
        got["rats"] = rats
        out[layer] = got
    return out


def write_layer(path, got, shape):
    """The page's binary: QUANTITIES stacked, float32, C order."""
    stack = np.stack([np.asarray(got[q], dtype=np.float32).reshape(shape)
                      for q in QUANTITIES])
    tmp = path + ".part"
    stack.tofile(tmp)
    os.replace(tmp, path)
    return stack.nbytes


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def points(got, layer, names, pairs, n=TOP_N, per_pair=PER_PAIR,
           p_cut=P_POINT):
    """The points of interest of one layer of edges.

    Every tested entry with p < p_cut, ranked by how many rats changed the
    same way and then by p. At most `per_pair` per region pair; an entry
    within SAME_HZ of one already chosen for the pair, in the same window
    and method, is the same finding and is listed under it (`more`)."""
    p = got["p"]
    ok = np.isfinite(p) & (p < p_cut)
    idx = np.nonzero(ok.ravel())[0]
    if not idx.size:
        return []
    same = got["same"].ravel()[idx]
    pv = p.ravel()[idx]
    order = idx[np.lexsort((pv, -same))]
    shape = p.shape                             # (W, B, M, P)
    chosen, by_pair = [], {}
    for flat in order:
        w, b, m, pi = np.unravel_index(int(flat), shape)
        rec = _point(got, (w, b, m, pi), layer, names, pairs)
        slot = by_pair.setdefault(int(pi), [])
        twin = None
        for c in slot:
            if c["w"] == rec["w"] and c["m"] == rec["m"] and \
                    _near(c["band"], rec["band"]):
                twin = c
                break
        if twin is not None:
            if len(twin["more"]) < 12:
                twin["more"].append(_brief(rec))
            twin["n_more"] += 1
            continue
        if len(slot) >= per_pair:
            host = slot[0]
            if len(host["more"]) < 12:
                host["more"].append(_brief(rec))
            host["n_more"] += 1
            continue
        if len(chosen) >= n:
            continue
        rec["more"], rec["n_more"] = [], 0
        slot.append(rec)
        chosen.append(rec)
    for i, c in enumerate(chosen):
        c["rank"] = i + 1
    return chosen


def _near(a, b):
    ba, bb = sweep.BAND_BY_ID[a], sweep.BAND_BY_ID[b]
    if ba["named"] or bb["named"]:
        return a == b
    return abs(ba["hz"] - bb["hz"]) <= SAME_HZ


def _point(got, at, layer, names, pairs):
    w, b, m, pi = (int(x) for x in at)
    a, bb = pairs[pi]
    est = float(got["est"][w, b, m, pi])
    return {"layer": layer, "w": WINDOWS[w], "wi": w,
            "kind": "state" if w < 4 else "transition",
            "band": sweep.BAND_IDS[b], "bi": b,
            "hz": sweep.BAND_BY_ID[sweep.BAND_IDS[b]]["hz"],
            "m": METHODS[m], "mi": m, "pair": pi,
            "a": names[a], "b": names[bb],
            "est": est, "se": _f(got["se"][w, b, m, pi]),
            "p": _f(got["p"][w, b, m, pi]),
            "k": int(got["k"][w, b, m, pi]),
            "same": int(got["same"][w, b, m, pi]),
            "up": est > 0}


def _brief(rec):
    return {k: rec[k] for k in ("w", "wi", "band", "bi", "hz", "m", "mi",
                                "est", "p", "k", "same")}


def _f(x):
    x = float(x)
    return x if math.isfinite(x) else None


def pac_points(got, layer, names, n=20):
    p = got["p"]
    ok = np.isfinite(p) & (p < P_POINT)
    idx = np.nonzero(ok.ravel())[0]
    if not idx.size:
        return []
    order = idx[np.lexsort((p.ravel()[idx], -got["same"].ravel()[idx]))]
    R = len(names)
    out = []
    for flat in order[:n]:
        w, c, op = (int(x) for x in np.unravel_index(int(flat), p.shape))
        fp, fa, _pb, ab = sweep.PAC_CELLS[c]
        out.append({"layer": layer, "w": WINDOWS[w], "wi": w, "cell": c,
                    "fp": fp, "fa": fa, "op": op,
                    "phase": names[op // R], "amp": names[op % R],
                    "est": _f(got["est"][w, c, op]), "p": _f(got["p"][w, c, op]),
                    "k": int(got["k"][w, c, op]),
                    "same": int(got["same"][w, c, op])})
    return out


def counts(got):
    p = got["p"]
    tested = np.isfinite(p)
    k = got["k"]
    same = got["same"]
    out = {"entries": int(p.size), "tested": int(tested.sum()),
           "p05": int((tested & (p < 0.05)).sum()),
           "p01": int((tested & (p < 0.01)).sum()),
           "p001": int((tested & (p < 0.001)).sum()),
           "chance_p05": round(0.05 * float(tested.sum())),
           "agree": {}}
    for kk in range(MIN_RATS, len(RATS) + 1):
        sel = tested & (k == kk)
        if not sel.any():
            continue
        out["agree"][str(kk)] = {
            "tested": int(sel.sum()),
            "all_same": int((sel & (same == kk)).sum()),
            # Each rat's direction a coin flip: all k the same way, 2 / 2^k.
            "chance_all_same": round(float(sel.sum()) * 2.0 / 2 ** kk)}
    return out


def build(man, run, raw_dir, out_dir, progress=None):
    """Assemble, pool, rank; write the page's files. Returns the summary
    (the artifact's payload, less the file digests)."""
    say = progress or (lambda *a: None)
    say("assemble", 0, 1, "")
    asm = assemble(man, run, raw_dir, out_dir,
                   progress=lambda i, n, w: say("assemble", i, n, w))
    names = sweep.regions()
    pairs = sweep.pairs_of(list(range(len(names))))
    shapes = {"edges": (len(WINDOWS), len(sweep.BAND_IDS), len(METHODS),
                        len(pairs)),
              "power": (len(WINDOWS), len(sweep.BAND_IDS), len(names)),
              "pac": (4, len(sweep.PAC_CELLS), len(names) ** 2)}
    files, top, pac_top, cnt, rats_by = {}, {}, {}, {}, {}
    for what in ("edges", "power", "pac"):
        say("pool", 0, 1, what)
        got = pooled(out_dir, man, what)
        for layer, g in got.items():
            fname = "%s_%s.f32" % (what, layer)
            path = os.path.join(out_dir, fname)
            nbytes = write_layer(path, g, shapes[what])
            files[fname] = {"bytes": nbytes, "sha256": _sha(path),
                            "shape": [len(QUANTITIES)] + list(shapes[what])}
            rats_by.setdefault(layer, g["rats"])
            if what == "edges":
                top[layer] = points(g, layer, names, pairs)
                cnt[layer] = counts(g)
            elif what == "pac":
                pac_top[layer] = pac_points(g, layer, names)
    summary = {
        "schema": SCHEMA, "analysis": ANALYSIS, "name": NAME,
        "built_at": now_iso(), "rid": run["rid"],
        "rats": sorted({d["rat"] for d in man["days"]}),
        "rats_by_layer": rats_by,
        "days": DAY_NAMES, "layers": list(LAYERS), "layer_say": LAYER_SAY,
        "min_rats": MIN_RATS, "quantities": list(QUANTITIES),
        "why": {str(k): v for k, v in WHY.items()},
        "windows": [{"id": w, "label": WINDOW_SAY[w],
                     "kind": "state" if w in sweep.STATE else "transition"}
                    for w in WINDOWS],
        "lengths": {"state": "10 s", "slow": "−3 s / +3 s (bands ≤ 12 Hz, "
                    "theta)", "fast": "−1 s / +2 s (bands ≥ 13 Hz, beta, "
                    "low gamma)"},
        "bands": sweep.BANDS,
        "methods": [{"id": m, "label": METHOD_SAY[m][0],
                     "say": METHOD_SAY[m][1],
                     "directed": m in ("gc_ab", "gc_ba", "gc_net")}
                    for m in METHODS],
        "regions": names, "pairs": [list(p) for p in pairs],
        "grey": sorted({g for d in man["days"] for g in d.get("grey") or []}),
        "pac_cells": [{"fp": c[0], "fa": c[1], "phase_band": list(c[2]),
                       "amp_band": list(c[3]) if c[3] else None}
                      for c in sweep.PAC_CELLS],
        "files": files, "top": top, "pac_top": pac_top, "counts": cnt,
        "correction": "none -- every p shown is uncorrected",
        "points_rule": ("p < %.2f (uncorrected), most rats the same way "
                        "first, then p; at most %d per region pair; within "
                        "%d Hz in the same window and method is the same "
                        "finding" % (P_POINT, PER_PAIR, SAME_HZ)),
        "missing_tasks": asm["missing"],
        "n_refusals": len(asm["refusals"]),
        "refusals": asm["refusals"][:200],
        "manifest": {"digest": man.get("digest"), "at": man.get("at"),
                     "notes": man.get("notes") or []},
        "run": {"rid": run["rid"], "dest": run.get("dest"),
                "arrays": [a["id"] for a in run.get("arrays") or []],
                "code": run.get("code"), "submitted_at":
                run.get("submitted_at"), "n_tasks": len(run["tasks"])},
        "units": {"r%d_%s" % (d["rat"], d["day"]): {
            "cue": [{"id": u["id"], "label": u["label"],
                     "cue": u["cue_label"]} for u in d["units"]],
            "rest": [{"id": u["id"], "label": u["label"], "run": u["run"]}
                     for u in d["rest"]]} for d in man["days"]},
    }
    _write_json(os.path.join(out_dir, "summary.json"), summary)
    return summary


def file_artifact(artifacts, summary, man, by=None):
    """The `monolith` artifact: the summary as its payload (small), its
    inputs the 16 bank entries."""
    subject = {"analysis": ANALYSIS, "name": NAME, "project": PROJECT,
               "rats": summary["rats"], "days": list(DAY_NAMES),
               "gids": man.get("gids") or []}
    params = {"bands": len(sweep.BANDS), "methods": METHODS,
              "min_rats": MIN_RATS, "concurrency": CONCURRENCY,
              "slow": list(sweep.SLOW_LEN), "fast": list(sweep.FAST_LEN),
              "half_frac": sweep.HALF_FRAC, "top_hz": sweep.TOP_HZ,
              "split_hz": sweep.SPLIT_HZ, "rid": summary["rid"]}
    payload = {k: v for k, v in summary.items() if k not in ("refusals",)}
    rec = artifacts.put("monolith", subject, payload, params=params,
                        inputs=man.get("inputs") or [], by=by,
                        name=NAME, nickname=NAME)
    return rec


# ==========================================================================
# One entry, all the way down
# ==========================================================================
def entry_detail(out_dir, man, summary, what, layer, at):
    """Everything behind one entry: each rat's change and weight, each day's
    mean, and every cue pair and rest epoch, recomputed here with
    drift.pool_rats + drift.hk_test (the scalar functions every drift uses)
    and compared with the pooled arrays."""
    names = summary["regions"]
    days = {(d["rat"], d["day"]): d for d in man["days"]}
    cue_name, rest_name = {"edges": ("edges", "edges_rest"),
                           "power": ("power", "power_rest"),
                           "pac": ("pac", "pac_rest")}[what]
    at = tuple(int(x) for x in at)
    rest_at = (0,) + at[1:]
    rows, per_rat = [], []
    for rat in summary["rats"]:
        per_day, gone = {}, None
        for day in DAY_NAMES:
            d = days.get((rat, day))
            X = _load_day(out_dir, rat, day, cue_name, mmap="r") if d else None
            if X is None or not X.shape[0]:
                gone = "%s: not computed" % day
                break
            vals = np.asarray(X[(slice(None),) + at], dtype=np.float64)
            units = [{"id": u["id"], "label": u["label"], "cue":
                      u["cue_label"], "v": _f(v)} for u, v in
                     zip(d["units"], vals)]
            if what == "edges":
                wkey = ("wires_state" if at[0] < 4 else
                        "wires_slow" if sweep.BAND_BY_ID[
                            sweep.BAND_IDS[at[1]]]["speed"] == "slow"
                        else "wires_fast")
                Wt = _load_day(out_dir, rat, day, wkey, mmap="r")
                a, b = summary["pairs"][at[3]]
                wi = at[0] if at[0] < 4 else at[0] - 4
                if Wt is not None:
                    for i, u in enumerate(units):
                        u["wires"] = [int(Wt[i, wi, a]), int(Wt[i, wi, b])]
            m, s2, n = day_stats(vals[:, None])
            slot = {"cue": _f(m[0]), "cue_se2": _f(s2[0]), "n": int(n[0]),
                    "units": units}
            if layer == "minus_fp":
                Xr = _load_day(out_dir, rat, day, rest_name, mmap="r")
                if Xr is None or not Xr.shape[0]:
                    gone = "%s: no rest epochs" % day
                    break
                rv = np.asarray(Xr[(slice(None),) + rest_at],
                                dtype=np.float64)
                rm, rs2, rn = day_stats(rv[:, None])
                slot.update(rest=_f(rm[0]), rest_se2=_f(rs2[0]),
                            n_rest=int(rn[0]),
                            rest_units=[{"id": u["id"], "label": u["label"],
                                         "run": u["run"], "v": _f(v)}
                                        for u, v in zip(d["rest"], rv)])
                if slot["n"] and slot["n_rest"]:
                    slot["x"] = slot["cue"] - slot["rest"]
                    slot["se2"] = (None if slot["cue_se2"] is None or
                                   slot["rest_se2"] is None else
                                   slot["cue_se2"] + slot["rest_se2"])
            elif slot["n"]:
                slot["x"], slot["se2"] = slot["cue"], slot["cue_se2"]
            if slot.get("x") is None:
                gone = "%s: no usable value" % day
            per_day[day] = slot
        rec = {"rat": rat, "days": per_day}
        if gone is None:
            a, b = per_day[DAY_NAMES[0]], per_day[DAY_NAMES[1]]
            v = (None if a["se2"] is None or b["se2"] is None
                 else a["se2"] + b["se2"])
            rec.update(delta=b["x"] - a["x"], v=v, left=a["x"], right=b["x"])
            rows.append({"rat": "r%d" % rat, "delta": rec["delta"], "v": v,
                         "n": a["n"] + b["n"]})
        else:
            rec["why"] = gone
        per_rat.append(rec)
    mp = drift.pool_rats(rows)
    t = drift.hk_test(None, None, pooled=mp)
    p = t.get("p") if mp["k"] >= MIN_RATS else None
    weights = {d["rat"]: d.get("weight") for d in mp.get("deltas") or []}
    for rec in per_rat:
        rec["weight"] = weights.get("r%d" % rec["rat"])
    pooled_says = None
    path = os.path.join(out_dir, "%s_%s.f32" % (what, layer))
    if os.path.isfile(path):
        shape = summary["files"]["%s_%s.f32" % (what, layer)]["shape"]
        arr = np.memmap(path, dtype=np.float32, mode="r",
                        shape=tuple(shape))
        pooled_says = {q: _f(arr[(i,) + at]) for i, q in
                       enumerate(QUANTITIES)}
    agree = None
    if pooled_says is not None:
        e1, e2 = pooled_says.get("est"), mp.get("mean")
        p1 = pooled_says.get("p")
        agree = ((e1 is None and e2 is None) or
                 (e1 is not None and e2 is not None and
                  abs(e1 - e2) <= 1e-4 * max(1.0, abs(e2)))) and \
            ((p1 is None) == (p is None)) and \
            (p is None or abs(p1 - p) <= 1e-4 * max(1e-3, p))
    return {"what": what, "layer": layer, "at": list(at),
            "rats": per_rat, "pooled": {
                "est": mp.get("mean"), "se": t.get("se") if p is not None
                else None, "p": p, "df": t.get("df"), "k": mp["k"],
                "tau2": mp.get("tau2"), "why": mp.get("why") or t.get("why")},
            "arrays": pooled_says, "agree": agree}


# ==========================================================================
# The work Jarvis does in the background: one thing at a time
# ==========================================================================
class Stopped(MonolithError):
    def __init__(self):
        MonolithError.__init__(self, "Stopped.", 409)


class Worker(object):
    """One piece of background work -- the upload, or fetching and building
    -- with what it is doing now, in words and numbers."""

    def __init__(self, what):
        self.what = what
        self.id = vacc.new_rid()
        self.started = now_iso()
        self.ended = None
        self.status = "running"
        self.error = None
        self.result = None
        self.progress = {}
        self._stop = False

    def stop(self):
        self._stop = True

    def check(self):
        if self._stop:
            raise Stopped()

    def stopping(self):
        return self._stop

    def note(self, **patch):
        self.progress = dict(self.progress, **patch)

    def snapshot(self):
        return {"what": self.what, "id": self.id, "started": self.started,
                "ended": self.ended, "status": self.status,
                "error": self.error, "progress": dict(self.progress),
                "stopping": self._stop and self.status == "running",
                "result": self.result}


_WORK = {"now": None}
_WORK_SAY = {"upload": "uploading", "fetch": "fetching and building the "
             "Monolith"}


def work_now():
    w = _WORK["now"]
    return w.snapshot() if w else None


def start_work(what, fn):
    """Run `fn(worker)` in a thread, unless something else is running."""
    with _LOCK:
        w = _WORK["now"]
        if w is not None and w.status == "running":
            raise MonolithError("Jarvis is already %s. Wait for it, or stop "
                                "it first." % _WORK_SAY.get(w.what, w.what),
                                409)
        w = Worker(what)
        _WORK["now"] = w
        save_state(work={"what": what, "id": w.id, "started": w.started,
                         "status": "running", "pid": os.getpid()})

    def go():
        try:
            w.result = fn(w)
            w.status = "done"
        except Stopped:
            w.status = "stopped"
        except Exception as exc:                         # noqa: BLE001
            w.status = "failed"
            w.error = ("%s" % (exc,) if isinstance(exc, MonolithError)
                       else "%s: %s" % (type(exc).__name__, exc))
        w.ended = now_iso()
        save_state(work={"what": what, "id": w.id, "started": w.started,
                         "ended": w.ended, "status": w.status,
                         "error": w.error, "pid": os.getpid()})

    threading.Thread(target=go, daemon=True,
                     name="monolith-" + what).start()
    return w


def stop_work():
    w = _WORK["now"]
    if w is None or w.status != "running":
        return False
    w.stop()
    return True


def interrupted(st):
    """The last work this machine was doing, if a restart cut it short."""
    rec = (st or {}).get("work") or {}
    if rec.get("status") != "running":
        return None
    w = _WORK["now"]
    if w is not None and w.id == rec.get("id"):
        return None
    return rec


# ==========================================================================
# The steps
# ==========================================================================
def ensure_manifest(host, cfg, rebuild=False):
    man = None if rebuild else manifest()
    if man:
        return man
    man = build_manifest(host, cfg)
    save_manifest(man)
    return man


def upload_plan(man, dest, remote):
    """What uploading to `dest` would send: per folder and in all."""
    rows, dirs = [], []
    for d, f in folders_of(man):
        rd = (f.get("remote") or {}).get(dest)
        if rd:
            dirs.append(rd)
    listing = sizes_many(remote, dirs)
    send_b = send_n = skip_n = 0
    for d, f in folders_of(man):
        rd = (f.get("remote") or {}).get(dest)
        if not rd:
            rows.append({"rat": d["rat"], "day": d["day"], "role": f["role"],
                         "why": f.get("why") or "no place for it there"})
            continue
        there = listing.get(rd) or {}
        send = [(rel, size) for rel, size in sorted(f["files"].items())
                if there.get(rel) != size]
        b = sum(s for _r, s in send)
        rows.append({"rat": d["rat"], "day": d["day"], "role": f["role"],
                     "local": f["local"], "remote": rd,
                     "n_files": f["n_files"], "n_send": len(send),
                     "n_skip": f["n_files"] - len(send), "bytes": b,
                     "total_bytes": f["bytes"]})
        send_b += b
        send_n += len(send)
        skip_n += f["n_files"] - len(send)
    return {"dest": dest, "rows": rows, "bytes": send_b, "files": send_n,
            "skipped": skip_n, "at": now_iso(),
            # Six streams measured at about 80 MB/s to the login node.
            "seconds": round(send_b / (80.0 * 1024 * 1024)) if send_b else 0}


def man_files(man, local):
    for _d, f in folders_of(man):
        if f["local"] == local:
            return f["files"]
    return {}


def upload_work(worker, man, dest, remote):
    """Send every folder's missing files, several at a time. A folder that
    fails is said and the rest carry on; pressing Upload again sends only
    what is still missing."""
    worker.note(phase="listing", dest=dest)
    plan = upload_plan(man, dest, remote)
    rows = [r for r in plan["rows"] if r.get("n_send")]
    worker.note(phase="sending", bytes_total=plan["bytes"], bytes_done=0,
                files_total=plan["files"], files_done=0,
                folders_total=len(rows), folders_done=0, folder=None,
                failed=[])
    save_state(upload={"dest": dest, "started": now_iso(),
                       "status": "running", "bytes_total": plan["bytes"],
                       "files_total": plan["files"]})
    lock = threading.Lock()
    done = {"b": 0, "f": 0}
    failed = []
    t0 = time.time()
    for n, r in enumerate(rows):
        worker.check()
        worker.note(folder="r%d %s %s" % (r["rat"], r["day"], r["role"]),
                    folders_done=n)
        local = r["local"]
        files = [(rel, size, os.path.join(local, rel.replace("/", os.sep)))
                 for rel, size in sorted(man_files(man, local).items())]
        there = sizes_many(remote, [r["remote"]]).get(r["remote"]) or {}
        send = [f for f in files if there.get(f[0]) != f[1]]

        def on_bytes(k):
            with lock:
                done["b"] += k
                el = max(1e-3, time.time() - t0)
                worker.note(bytes_done=done["b"],
                            rate=round(done["b"] / el))

        def on_file(i, rel):
            worker.note(file=rel)

        try:
            got = vaccupload.send(
                remote, local, r["remote"],
                plan={"send": send, "skip": len(files) - len(send),
                      "bytes": sum(f[1] for f in send)},
                on_bytes=on_bytes, check=worker.check, on_file=on_file,
                streams=vaccupload.STREAMS)
            done["f"] += got["sent"]
            worker.note(files_done=done["f"])
        except Stopped:
            save_state(upload=dict(get_state().get("upload") or {},
                                   status="stopped", ended=now_iso(),
                                   bytes_sent=done["b"]))
            raise
        except Exception as exc:                         # noqa: BLE001
            failed.append({"folder": "r%d %s %s" % (r["rat"], r["day"],
                                                    r["role"]),
                           "why": str(exc)[:300]})
            worker.note(failed=list(failed))
    worker.note(folders_done=len(rows), folder=None, file=None)
    res = {"dest": dest, "bytes_sent": done["b"], "files_sent": done["f"],
           "failed": failed, "ended": now_iso()}
    save_state(upload=dict(get_state().get("upload") or {},
                           status="done" if not failed
                           else "done with failures", **res))
    return res


def check(man, remote, cfg=None, ssh=None, prefer=None, run_only=False):
    """Both places listed in one call, compared file by file; and the run,
    if there is one, polled in a second. `run_only` asks about the run
    alone (what the tab does by itself every two minutes while the run
    goes) and keeps the last listing."""
    st = get_state()
    if run_only and st.get("check"):
        chk = st["check"]
    else:
        dirs = []
        for _d, f in folders_of(man):
            dirs.extend((f.get("remote") or {}).values())
        listing = sizes_many(remote, dirs)
        prefer = prefer or (st.get("upload") or {}).get("dest")
        chk = check_data(man, listing, prefer)
        tasks = plan_tasks(man, chk)
        chk["plan"] = cost(tasks)
        chk["plan"]["by_kind"] = {}
        for t in tasks:
            chk["plan"]["by_kind"][t["kind"]] = \
                chk["plan"]["by_kind"].get(t["kind"], 0) + 1
        chk["at"] = now_iso()
        chk["manifest"] = man.get("digest")
    out = {"data": chk}
    run = st.get("run")
    if run and cfg is not None:
        try:
            pl = poll(cfg, run, ssh=ssh)
            failed = [r["i"] for r in pl["tasks"] if r["state"] == "failed"]
            if failed:
                tails = log_tails(cfg, run, failed[:5], ssh=ssh)
                for r in pl["tasks"]:
                    if r["i"] in tails:
                        r["log"] = tails[r["i"]]
            out["poll"] = pl
        except Exception as exc:                         # noqa: BLE001
            out["poll"] = {"error": str(exc)[:300], "at": now_iso()}
    save_state(check=chk, poll=out.get("poll"))
    return out


def again_of(st):
    """The tasks a finished run would run again: failed, or never seen."""
    run = st.get("run")
    pl = st.get("poll") or {}
    if not run or pl.get("active") or not pl.get("tasks"):
        return []
    return [r["i"] for r in pl["tasks"] if r["state"] in ("failed",
                                                           "unknown")]


def run_now(man, cfg, app_dir, ssh=None):
    """Submit the run, or run again what did not finish."""
    st = get_state()
    chk = st.get("check")
    if not chk:
        raise MonolithError("Check the VACC first: the run goes only where "
                            "the recordings are whole on the cluster.", 409)
    run = st.get("run")
    pl = st.get("poll") or {}
    if run:
        if pl.get("active"):
            raise MonolithError("The run is still going on the cluster. "
                                "Check the VACC to see where it is.", 409)
        again = again_of(st)
        if again and len(again) < len(run["tasks"]):
            run = resubmit(cfg, run, again, ssh=ssh)
            save_state(run=run, poll=None)
            return run
    if chk.get("manifest") and chk["manifest"] != man.get("digest"):
        raise MonolithError("What goes has changed since the VACC was "
                            "checked. Check it again first.", 409)
    if not chk.get("can_run"):
        n = len(chk.get("ready_rats") or [])
        raise MonolithError(
            "Only %d rat%s ha%s both days whole on the cluster; at least %d "
            "are needed. Upload, then check again."
            % (n, "" if n == 1 else "s", "s" if n == 1 else "ve", MIN_RATS),
            409)
    tasks = plan_tasks(man, chk)
    dest = (st.get("upload") or {}).get("dest") or "scratch"
    run = submit(cfg, tasks, dest, app_dir, ssh=ssh)
    run["ready_rats"] = chk.get("ready_rats")
    run["manifest"] = man.get("digest")
    save_state(run=run, poll=None, fetch=None)
    return run


def fetch_and_build(worker, man, cfg, artifacts, by=None, fetcher=None):
    """Bring every answer home, pool, write the page's files, file the
    artifact."""
    st = get_state()
    run = st.get("run")
    if not run:
        raise MonolithError("There is no run to fetch.", 409)
    base = run_dir_local(run["rid"])
    raw = os.path.join(base, "raw")
    data = os.path.join(base, "data")
    worker.note(phase="fetching", bytes_done=0,
                bytes_total=(st.get("poll") or {}).get("out_bytes") or 0)
    if os.path.isdir(raw):
        shutil.rmtree(raw, ignore_errors=True)
    n = (fetcher or fetch)(cfg, run, raw,
                           progress=lambda b: worker.note(bytes_done=b),
                           stop=worker.stopping)
    worker.check()
    save_state(fetch={"rid": run["rid"], "at": now_iso(), "files": n})
    worker.note(phase="building", step=None)
    if os.path.isdir(data):
        shutil.rmtree(data, ignore_errors=True)
    summary = build(man, run, raw, data, progress=lambda what, i, of, w:
                    worker.note(phase="building", step=what, i=i, of=of,
                                item=w))
    worker.check()
    worker.note(phase="filing")
    rec = file_artifact(artifacts, summary, man, by=by)
    built = {"rid": run["rid"], "at": now_iso(),
             "artifact_id": rec.get("id"), "version": rec.get("version"),
             "counts": summary.get("counts"),
             "n_top": {k: len(v) for k, v in summary["top"].items()},
             "missing_tasks": summary.get("missing_tasks") or []}
    save_state(built=built)
    return built


def data_dir():
    b = (get_state().get("built") or {}).get("rid")
    return os.path.join(run_dir_local(b), "data") if b else None


def summary_now():
    d = data_dir()
    return _read_json(os.path.join(d, "summary.json")) if d else None


def status(cfg, vstatus=None):
    st = get_state()
    man = manifest()
    return {
        "ok": True, "schema": SCHEMA,
        "manifest": manifest_brief(man),
        "dests": list(vacc.upload_roots(cfg).values()) if cfg else [],
        "upload": st.get("upload"), "upload_plan": st.get("upload_plan"),
        "check": st.get("check"), "poll": st.get("poll"),
        "run": st.get("run"), "again": again_of(st),
        "fetch": st.get("fetch"), "built": st.get("built"),
        "work": work_now(), "interrupted": interrupted(st),
        "vacc": {k: (vstatus or {}).get(k) for k in
                 ("configured", "available", "why", "netid", "host")},
        "min_rats": MIN_RATS, "concurrency": CONCURRENCY,
    }
