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
                 whole on the cluster go; it needs at least four rats.
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
tested Hartung-Knapp on k - 1 df; an entry with fewer than four rats is
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

from . import (circuit, circuitrun, coupling, drift, histo, nlx, probes,
               ratidentity, sweep, vacc, vaccupload)

SCHEMA = "arc.monolith/1"
ANALYSIS = "precon1-4-sweep"
NAME = "Monolith · Precon1→4 · 1–55 Hz"
PROJECT = "DEWEY"
RATS = (3, 4, 6, 7, 8, 9, 10, 11)
EXCLUDED_RATS = {5: "no Precon4 recording, and no histology row"}
DAYS = ((1, "Precon1"), (4, "Precon4"))
DAY_NAMES = tuple(d for _n, d in DAYS)
#: The two sessions between, for the trajectory only (the lab meeting,
#: 2026-10-02): measured exactly as Precon1 and Precon4 are, read across
#: the four sessions, never pooled into the change and never tested.
TRAJ_DAYS = ((2, "Precon2"), (3, "Precon3"))
TRAJ_NAMES = tuple(d for _n, d in TRAJ_DAYS)
ALL_DAY_ORDER = ("Precon1", "Precon2", "Precon3", "Precon4")


def core_view(man):
    """The manifest as the change sees it: Precon1 and Precon4 only."""
    return dict(man, days=[d for d in man.get("days") or []
                           if d["day"] in DAY_NAMES])
#: Four, not five, since 2026-10-05 (the user's choice): under histology
#: v2 with only "y" kept, Left POR-SUB has four rats, and at five its pairs
#: would be drawn and never tested. Every test with four rats is weaker,
#: and the page says how many rats each entry rests on.
MIN_RATS = 4

#: Which probes the Monolith uses (the user, 2026-10-05): only those
#: histology v2 scored "y" -- where they were aimed, with confidence. A
#: "maybe" and a probe found somewhere else are left out here (Coupling,
#: elsewhere in Jarvis, keeps them under their true names).
#:
#: One exception makes a region of its own. No probe aimed at POR is in
#: POR, and the LEFT ones are consistently in subiculum, so that channel
#: group -- the POR channel mapping -- is used as "Left POR-SUB" in every
#: rat whose left POR cell says subiculum. "Right POR-SUB" is excluded.
REGION_LABEL = {"Left POR": "Left POR-SUB", "Right POR": "Right POR-SUB"}
POR_SUB = ("Left POR",)
POR_SUB_EXCLUDED = ("Right POR",)
HISTO_RULE = "v%d: y only, Left POR-SUB, no Right POR-SUB" % \
    histo.HISTO_VERSION
HISTO_SAY = ("%s. Only probes scored “y” are used; “maybe”s and probes "
             "found somewhere else are left out. The left POR probes, which "
             "are in subiculum, are Left POR-SUB; Right POR-SUB is left out."
             % histo.version_say())


def label(name):
    """The Monolith's name for a channel group."""
    return REGION_LABEL.get(name, name)


def histology_blocked(rat):
    """{channel group: sentence} for every group the Monolith leaves out
    of this rat, under the rule above."""
    rat = int(rat)
    if rat not in _HISTO_BLOCKED:
        _HISTO_BLOCKED[rat] = _histology_blocked(rat)
    return dict(_HISTO_BLOCKED[rat])


_HISTO_BLOCKED = {}


def _histology_blocked(rat):
    regions = probes.regions_for("dewey32",
                                 [{"number": n} for n in range(1, 33)])
    out = {}
    for r in histo.probe_sanity(rat, regions):
        name = r["intended"]
        raw = " ".join(str(r.get("raw") or "").split())
        said = "“%s”" % raw if raw else "nothing (the rat is not scored)"
        if name in POR_SUB_EXCLUDED:
            out[name] = ("%s is left out of the Monolith (the lab, "
                         "2026-10-05); histology v%d scored this probe %s."
                         % (label(name), histo.HISTO_VERSION, said))
        elif name in POR_SUB:
            if raw.lower() != "subiculum":
                out[name] = ("Histology v%d scored this POR probe %s, not "
                             "subiculum, so it is not %s in this rat."
                             % (histo.HISTO_VERSION, said, label(name)))
        elif r["verdict"] != histo.INTENDED:
            out[name] = ("Histology v%d scored this probe %s, not “y”; the "
                         "Monolith uses only probes scored “y”."
                         % (histo.HISTO_VERSION, said))
    return out


def histology_now(man):
    """Bring a manifest's histology up to the rule in force. True when
    anything changed (its digest is then new)."""
    changed = man.get("histology") != HISTO_RULE
    for d in man.get("days") or []:
        want = histology_blocked(d["rat"])
        if d.get("blocked") != want:
            d["blocked"] = want
            d["grey"] = sorted(want)
            changed = True
    if changed:
        man["histology"] = HISTO_RULE
        man["digest"] = _digest(man)
    return changed

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
          "rest": 15.6 / 58, "pac": 2.2, "pac_rest": 2.2, "pac_trans": 2.2,
          # The whole pair is one 20 s window: twice a state window's work.
          "pair": 2 * 15.6 / 58, "rest_pair": 2 * 15.6 / 58,
          "pac_pair": 4.4, "pac_rest_pair": 4.4}
#: Band chunks of the whole-pair task (one window, so fewer than a state's).
PAIR_CHUNKS = 2

#: PAC windows: the four state windows, then the three transitions (the
#: slow -3/+3 s ones; user, 2026-10-02). A Monolith built before the
#: transitions were added has the first four only.
#: ...and the whole pair (cue 1 + cue 2, 20 s; the lab, 2026-10-06), last.
PAC_WINDOWS = list(sweep.STATE) + list(sweep.TRANSITION) + list(sweep.PAIR)

#: What a small run can add to a Monolith already built, without running
#: the rest again: named bands it lacks, and PAC at the transitions.
ADDITIONS_SAY = {"delta": "the delta band (2–4 Hz)",
                 "pac_trans": "phase–amplitude coupling at the transitions",
                 "pair": "the whole pair (cue 1 + cue 2, 20 s)",
                 "fast": "the fast transitions (13–55 Hz, −1/+2 s)"}

WINDOWS = list(sweep.STATE) + list(sweep.TRANSITION) + list(sweep.PAIR)
WINDOW_SAY = {"pre": "Pre-baseline", "cue1": "Cue 1", "cue2": "Cue 2",
              "post": "Post-baseline", "onset": "Onset", "switch": "Switch",
              "offset": "Offset", "pair": "Cue 1 + Cue 2"}
#: Where the whole pair sits in the windows.
PAIR_W = WINDOWS.index("pair")

#: The agreed comparison (the lab, 2026-10-06): within each presentation,
#: Cue 2 minus Cue 1 -- the second cue against the first, B - A in AB and
#: D - C in CD -- then Precon4 against Precon1, pooled as everything else.
#: It is carried as one more window, after the real ones, in every pooled
#: array (the day arrays are not changed: it is worked out from them). It
#: is RAW ONLY: the rest a day's minus FP takes away is the same for both
#: cue windows, so it cancels exactly, and the minus-FP layer holds the raw
#: numbers there.
CONTRAST = "c21"
CONTRAST_SAY = "Cue 2 − Cue 1"
WINDOW_SAY[CONTRAST] = CONTRAST_SAY


def window_ids(pac=False):
    """Every window of a pooled array, in its order: the measured ones,
    then the contrast."""
    return list(PAC_WINDOWS if pac else WINDOWS) + [CONTRAST]


def window_kind(w):
    return ("contrast" if w == CONTRAST else "state" if w in sweep.STATE
            else "pair" if w == "pair" else "transition")


def with_contrast(X, pac=False):
    """A day's array (presentations first, then windows) with one more
    window: each presentation's Cue 2 minus its Cue 1."""
    names = PAC_WINDOWS if pac else WINDOWS
    i1, i2 = names.index("cue1"), names.index("cue2")
    X = np.asarray(X)
    return np.concatenate([X, (X[:, i2] - X[:, i1])[:, None]], axis=1)


def at_values(X, at, pac=False):
    """Each presentation's value at `at` (window first) in a day's array:
    the contrast worked out from its Cue 2 and Cue 1."""
    names = PAC_WINDOWS if pac else WINDOWS
    at = tuple(int(x) for x in at)
    if at[0] == len(names):
        i1, i2 = names.index("cue1"), names.index("cue2")
        return (np.asarray(X[(slice(None), i2) + at[1:]], dtype=np.float64)
                - np.asarray(X[(slice(None), i1) + at[1:]],
                             dtype=np.float64))
    return np.asarray(X[(slice(None),) + at], dtype=np.float64)


def _rest_for(out_dir, d, rest_name, Xr, n_windows, pac=False):
    """A day's rest, one per window: the 10 s epochs stand against every
    window but the whole pair, which takes its own 20 s ones (NaN where it
    has none, so its minus-FP layer leaves the day out)."""
    m, s2, n = day_stats(Xr)
    full = [np.repeat(a, n_windows, axis=0) for a in (m, s2, n)]
    pw = (PAC_WINDOWS if pac else WINDOWS).index("pair")
    Xp = _load_day(out_dir, d["rat"], d["day"], rest_name + "_pair")
    if Xp is not None and Xp.shape[0]:
        mp, s2p, np_ = day_stats(Xp)
        full[0][pw], full[1][pw], full[2][pw] = mp[0], s2p[0], np_[0]
    else:
        full[0][pw], full[1][pw], full[2][pw] = np.nan, np.nan, 0
    return tuple(full)


def _slice(got, sl):
    """A pooled result cut along its window axis."""
    return {k: (v[sl] if isinstance(v, np.ndarray) and v.ndim else v)
            for k, v in got.items()}


def _tops(got, layer, names, pairs, pac=False):
    """Points and counts of the measured windows, and of the contrast,
    apart: the contrast is a different question and never mixes into the
    page's counts or its overall list."""
    ci = len(PAC_WINDOWS if pac else WINDOWS)
    main, con = _slice(got, slice(0, ci)), _slice(got, slice(ci, ci + 1))
    if pac:
        return (pac_points(main, layer, names), None,
                pac_points(con, layer, names, w0=ci), None)
    return (points(main, layer, names, pairs), counts(main),
            points(con, layer, names, pairs, w0=ci), counts(con))
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
        "demo.py", "drift.py", "histo.py", "lazyimp.py", "monolith.py",
        "nlx.py", "probes.py", "ratidentity.py", "spark.py", "sweep.py",
        "sysinfo.py", "vacc.py",
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


def select_days(host, days=DAYS):
    """{(rat, day name): gid} for the banked Precon SPC recordings of the
    rats (Precon1 and Precon4 unless `days` says), and the sentences for
    what is not there."""
    rows = host.recordings(False) or []
    got, problems = {}, []
    for r in rows:
        if r.get("mouse") not in RATS or r.get("phase") != "Precon":
            continue
        day = dict(days).get(r.get("phase_n"))
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
        for _n, day in days:
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
        rec = _day_record(host, cfg, roots, rat, day, gid, notes)
        if rec is None:
            continue
        out_days.append(rec)
        inputs.append({"kind": "bank", "entry": rec["bank"]["entry"],
                       "version": rec["bank"]["version"]})
        gids.append(gid)
    man = {
        "schema": SCHEMA, "at": now_iso(), "rats": list(RATS),
        "excluded": {"r%d" % k: v for k, v in EXCLUDED_RATS.items()},
        "days": out_days, "notes": notes, "inputs": inputs, "gids": gids,
        "regions": sweep.regions(),
        "roots": roots, "files_rule": FILES_RULE,
        "histology": HISTO_RULE,
    }
    man["digest"] = _digest(man)
    return man


def extend_manifest(host, cfg, progress=None):
    """The manifest with Precon2 and Precon3 added, for the trajectory:
    each worked out exactly as Precon1 and Precon4 were; the days already
    in it are left as they are."""
    man = manifest()
    if not man:
        raise MonolithError("Ask for the upload plan first: there is no "
                            "manifest to add to.", 409)
    days, problems = select_days(host, TRAJ_DAYS)
    have = {(int(d["rat"]), d["day"]) for d in man["days"]}
    roots = vacc.upload_roots(cfg)
    notes = list(man.get("notes") or [])
    for x in problems:
        if x not in notes:
            notes.append(x)
    todo = sorted(k for k in days if k not in have)
    added = []
    # The whole-pair window's 20 s rest, on every day that lacks it.
    for d in man["days"]:
        if d.get("rest_pair") is None:
            if progress:
                progress(0, 1, "r%d %s · 20 s rest" % (d["rat"], d["day"]))
            d["rest_pair"] = _rest_pair_units(host, d["gid"], int(d["rat"]),
                                              d["day"], notes) or []
            added.append("r%d %s 20 s rest" % (d["rat"], d["day"]))
    for n, (rat, day) in enumerate(todo):
        if progress:
            progress(n, len(todo), "r%d %s" % (rat, day))
        rec = _day_record(host, cfg, roots, rat, day, days[(rat, day)], notes)
        if rec is None:
            continue
        man["days"].append(rec)
        man["inputs"].append({"kind": "bank", "entry": rec["bank"]["entry"],
                              "version": rec["bank"]["version"]})
        man["gids"].append(rec["gid"])
        added.append("r%d %s" % (rat, day))
    order = {d: i for i, d in enumerate(ALL_DAY_ORDER)}
    man["days"].sort(key=lambda d: (int(d["rat"]), order.get(d["day"], 9)))
    man["notes"] = notes
    man["trajectory_days"] = list(TRAJ_NAMES)
    man["at"] = now_iso()
    man["digest"] = _digest(man)
    return man, added


def _rest_pair_units(host, gid, rat, day, notes):
    """The 20 s rest epochs for the whole-pair window: cut from FP1 and FP2
    exactly as the 10 s ones are, as many, and checked for clipping the same
    way. None (with a note) when there are none."""
    try:
        prep = circuitrun.prepare_rest(host, gid, epoch_s=sweep.PAIR_REST_S)
        clip = circuitrun.rest_clipping(prep)
        circuitrun.apply_rest_clipping(prep, clip)
    except circuitrun.CircuitRunError as exc:
        notes.append("r%d %s: no 20 s rest epochs (%s); the whole-pair "
                     "window's minus-FP layer leaves this rat out"
                     % (rat, day, exc))
        return None
    return [{"id": "f%02d" % p["pair_id"], "pair_id": p["pair_id"],
             "label": p["label"], "run": p["run"], "fp_gid": p["fp"],
             "local": p["path"], "pair": p["pair"], "drop": p["drop"],
             "why": p.get("unmeasured_why")} for p in prep["pairs"]]


def _day_record(host, cfg, roots, rat, day, gid, notes):
    """Everything one rat-day needs to be run: its cue pairs, rest epochs,
    folders and where each goes. None (with a note) when its SPC folder
    cannot be opened here."""
    entry = host.entry(gid)
    sm = host.summary(gid) or {}
    spc = circuitrun.cued_folder(sm, entry)
    if not spc or not os.path.isdir(spc):
        notes.append("r%d %s: its SPC folder cannot be opened here" %
                     (rat, day))
        return None
    bad = sorted(int(c) for c in (sm.get("bad_channels") or []))
    blocked = histology_blocked(rat)
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
    rest_pair = _rest_pair_units(host, gid, rat, day, notes)
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
    return {
        "rat": rat, "day": day, "gid": gid,
        "label": circuitrun.session_label(sm, spc),
        "bad": bad, "blocked": blocked,
        "grey": sorted(blocked),
        "fast_banked": fast_banked,
        "units": units, "rest": rest_units, "rest_pair": rest_pair,
        "folders": folders,
        "bank": {"entry": entry.get("id"), "version": entry.get("version")},
    }


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
    # The histology in force, whenever it was made: what goes to the
    # cluster, what is pooled and what the page says all follow it.
    if histology_now(man):
        save_manifest(man)
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
    core = [x for x in days if x["day"] in DAY_NAMES]
    ready_rats = sorted({x["rat"] for x in core if x["spc_ready"]
                         and all(y["spc_ready"] for y in core
                                 if y["rat"] == x["rat"])
                         and sum(1 for y in core if y["rat"] == x["rat"])
                         == len(DAYS)})
    n_folders = sum(len(x["folders"]) for x in days)
    n_ready = sum(1 for x in days for r in x["folders"] if r["use"])
    # The sessions between: each on its own, for a rat in the change.
    traj = [[x["rat"], x["day"]] for x in days if x["day"] in TRAJ_NAMES
            and x["spc_ready"] and x["rat"] in ready_rats]
    return {"days": days, "ready_rats": ready_rats,
            "n_folders": n_folders, "n_ready": n_ready,
            "traj_ready": traj,
            "can_run": len(ready_rats) >= MIN_RATS}


# ==========================================================================
# The tasks
# ==========================================================================
def _chunks(seq, n):
    seq = list(seq)
    k = int(math.ceil(len(seq) / float(n)))
    return [seq[i:i + k] for i in range(0, len(seq), k)]


def plan_tasks(man, chk, extra=None):
    """Every task of the run: [{key, rat, day, kind, chunk, spec, est_s}].

    A rat goes only when both its days' SPC are whole on the cluster; its
    rest goes when both FP folders are.

    `extra` plans an ADDITION to a Monolith already built instead: on the
    days the Monolith has (`on_days`, Precon1 and Precon4 unless said),
    only `{"bands": [...]}` (in the state, transition and rest tasks that
    measure them), `{"pac_trans": True}` and/or `{"pair": True}` (the whole
    pair, its PAC and its 20 s rest); and, with `{"days": ["Precon2",
    "Precon3"]}`, every task of those days, for the trajectory. Its tasks
    are keyed apart ("..._x") so they never overwrite the run they add
    to."""
    by = {(d["rat"], d["day"]): d for d in man.get("days") or []}
    ready = {(x["rat"], x["day"]): x for x in chk["days"]}
    rats = set(chk["ready_rats"])
    tasks = []
    names = sweep.regions()
    full_days = set((extra or {}).get("days") or []) if extra is not None \
        else None
    on_days = set((extra or {}).get("on_days") or DAY_NAMES)
    fast_keys = {(int(r), str(d)) for r, d in (extra or {}).get("fast") or []}
    for (rat, day), d in sorted(by.items()):
        if rat not in rats or (rat, day) not in ready:
            continue
        rd = ready[(rat, day)]
        whole_day = extra is None or (full_days and day in full_days)
        if whole_day and extra is not None and not rd["spc_ready"]:
            continue                # the sessions between: whole, or not
        if not whole_day and day not in on_days:
            continue
        where = {r["role"]: r["remote"] for r in rd["folders"]}
        spc = where.get("SPC")
        base = {"blocked": d["blocked"], "bad": d["bad"], "regions": names,
                "rat": rat, "day": day, "gid": d["gid"]}
        cue_units = [{"id": u["id"], "pair": u["pair"], "drop": u["drop"],
                      "manual": u["manual"]} for u in d["units"]]
        # The whole pair: a wire only where it was clean in both cues.
        pair_units = [{"id": u["id"], "pair": u["pair"],
                       "drop": None if u["drop"] is None else {"pair": sorted(
                           set(_drop_for(u["drop"], "cue1") or [])
                           | set(_drop_for(u["drop"], "cue2") or []))},
                       "why": None if u["drop"] is not None else
                       "no clipping measurement; not computed"}
                      for u in d["units"]]

        def add(kind, chunk, bands, units, folder=None):
            key = "r%d_%s_%s%s%s" % (rat, day, kind,
                                     "" if chunk is None else "_%d" % chunk,
                                     "_x" if extra else "")
            spec = dict(base, kind=kind, bands=bands, units=units,
                        folder=folder,
                        task={"rat": rat, "day": day, "kind": kind,
                              "chunk": chunk, "key": key})
            n_w = (4 if kind in ("state", "pac") else
                   3 if kind.startswith("trans") or kind == "pac_trans"
                   else 1)              # rest, and the whole pair
            per = RATE_S[kind] * (1 if kind.startswith("pac")
                                  else len(bands or []))
            tasks.append({"key": key, "rat": rat, "day": day, "kind": kind,
                          "chunk": chunk, "n_units": len(units),
                          "est_s": round(len(units) * n_w * per, 1),
                          "spec": spec})

        fp_where = {r["gid"]: r["remote"] for r in rd["folders"]
                    if r["role"] != "SPC"}

        def add_pair():
            """The whole pair: its edges and power, its PAC, its rest."""
            if pair_units:
                for ci, bands in enumerate(_chunks(sweep.bands_for("pair"),
                                                   PAIR_CHUNKS)):
                    add("pair", ci, bands, pair_units, spc)
                add("pac_pair", None, [], pair_units, spc)
            if rd["rest_ready"] and d.get("rest_pair"):
                rp = [{"id": u["id"], "pair": u["pair"], "drop": u["drop"],
                       "why": u.get("why"),
                       "folder": fp_where.get(u["fp_gid"])}
                      for u in d["rest_pair"]]
                add("rest_pair", None, sweep.bands_for("rest_pair"), rp)
                add("pac_rest_pair", None, [], rp)

        if not whole_day:
            xb = list((extra or {}).get("bands") or [])
            sl = [b for b in sweep.bands_for("trans_slow") if b in xb]
            fa = [b for b in sweep.bands_for("trans_fast") if b in xb]
            if cue_units:
                if xb:
                    add("state", None, xb, cue_units, spc)
                if sl:
                    add("trans_slow", None, sl, cue_units, spc)
                if fa and d.get("fast_banked"):
                    add("trans_fast", None, fa, cue_units, spc)
                # The fast transitions of a day whose transitions were not
                # banked at -1/+2 s when it ran, and are now (Spark).
                if (rat, day) in fast_keys and d.get("fast_banked") and \
                        "trans_fast" not in {t["kind"] for t in tasks
                                             if t["rat"] == rat
                                             and t["day"] == day}:
                    add("trans_fast", None, sweep.bands_for("trans_fast"),
                        cue_units, spc)
                if (extra or {}).get("pac_trans"):
                    add("pac_trans", None, [], cue_units, spc)
            if (extra or {}).get("pair"):
                add_pair()
            elif xb and (extra or {}).get("pair_built"):
                # A band added to a Monolith that has the whole pair: in
                # the whole pair too, and its 20 s rest.
                if pair_units:
                    add("pair", None, xb, pair_units, spc)
                if rd["rest_ready"] and d.get("rest_pair"):
                    add("rest_pair", None, xb, [
                        {"id": u["id"], "pair": u["pair"], "drop": u["drop"],
                         "why": u.get("why"),
                         "folder": fp_where.get(u["fp_gid"])}
                        for u in d["rest_pair"]])
            if xb and rd["rest_ready"] and d["rest"]:
                fp_where = {r["gid"]: r["remote"] for r in rd["folders"]
                            if r["role"] != "SPC"}
                add("rest", None, xb, [
                    {"id": u["id"], "pair": u["pair"], "drop": u["drop"],
                     "why": u.get("why"), "folder": fp_where.get(u["fp_gid"])}
                    for u in d["rest"]])
            continue
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
            add("pac_trans", None, [], cue_units, spc)
        add_pair()
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
    # A run that ADDS to an earlier one is assembled with it: every part's
    # answers from its own folder, the later part's over the earlier's.
    srcs = []
    for part in run.get("parts") or []:
        srcs.append((part["tasks"], os.path.join(run_dir_local(part["rid"]),
                                                  "raw")))
    srcs.append((run["tasks"], raw_dir))
    tasks, where = {}, {}
    for ts, rdir in srcs:
        for t in ts:
            tasks[t["key"]] = t
            where[t["key"]] = rdir
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
        Up = len(d.get("rest_pair") or [])
        uix = {u["id"]: i for i, u in enumerate(d["units"])}
        rix = {u["id"]: i for i, u in enumerate(d["rest"])}
        pix = {u["id"]: i for i, u in enumerate(d.get("rest_pair") or [])}
        NW = len(WINDOWS)
        E = np.full((U, NW, B, M, P), np.nan, np.float32)
        Pw = np.full((U, NW, B, R), np.nan, np.float32)
        PAC = np.full((U, len(PAC_WINDOWS), C, R * R), np.nan, np.float32)
        Wst = np.full((U, 4, R), -1, np.int16)
        Wsl = np.full((U, 3, R), -1, np.int16)
        Wfa = np.full((U, 3, R), -1, np.int16)
        Er = np.full((Ur, 1, B, M, P), np.nan, np.float32)
        Pwr = np.full((Ur, 1, B, R), np.nan, np.float32)
        PACr = np.full((Ur, 1, C, R * R), np.nan, np.float32)
        Wr = np.full((Ur, 1, R), -1, np.int16)
        Wpr = np.full((U, 1, R), -1, np.int16)
        Erp = np.full((Up, 1, B, M, P), np.nan, np.float32)
        Pwrp = np.full((Up, 1, B, R), np.nan, np.float32)
        PACrp = np.full((Up, 1, C, R * R), np.nan, np.float32)
        Wrp = np.full((Up, 1, R), -1, np.int16)
        for t in ts:
            path = os.path.join(where[t["key"]], "out", t["key"] + ".npz")
            if not os.path.isfile(path):
                missing.append(t["key"])
                continue
            arrays, meta = sweep.load_task(path)
            refusals.extend(dict(x, task=t["key"]) for x in meta.get("why")
                            or [])
            kind = meta["kind"]
            rest = kind in ("rest", "pac_rest")
            rest_p = kind in ("rest_pair", "pac_rest_pair")
            index = rix if rest else pix if rest_p else uix
            rows = [index.get(u) for u in meta["units"]]
            if kind.startswith("pac"):
                p0 = {"pac_trans": 4, "pac_pair": PAIR_W}.get(kind, 0)
                for j, i in enumerate(rows):
                    if i is None:
                        continue
                    if rest:
                        PACr[i] = arrays["values"][j]
                        Wr[i] = arrays["wires"][j]
                    elif rest_p:
                        PACrp[i] = arrays["values"][j]
                        Wrp[i] = arrays["wires"][j]
                    else:
                        v = arrays["values"][j]
                        PAC[i, p0:p0 + v.shape[0]] = v
                filled.append(t["key"])
                continue
            bi = _bi(meta["bands"])
            v = arrays["values"]                       # (U, W, b, 13, P)
            pw = arrays["power"]
            w0 = {"state": 0, "trans_slow": 4, "trans_fast": 4,
                  "rest": 0, "pair": PAIR_W, "rest_pair": 0}[kind]
            nw = v.shape[1]
            tgtE, tgtP = (Er, Pwr) if rest else (Erp, Pwrp) if rest_p \
                else (E, Pw)
            for j, i in enumerate(rows):
                if i is None:
                    continue
                for wj in range(nw):
                    tgtE[i, w0 + wj, bi, :len(sweep.EDGE_METHODS)] = v[j, wj]
                    tgtP[i, w0 + wj, bi] = pw[j, wj]
                wt = {"state": Wst, "trans_slow": Wsl, "trans_fast": Wfa,
                      "rest": Wr, "pair": Wpr, "rest_pair": Wrp}[kind]
                wt[i] = arrays["wires"][j]
            filled.append(t["key"])
        ga, gb = sweep.EDGE_METHODS.index("gc_ab"), \
            sweep.EDGE_METHODS.index("gc_ba")
        gn = sweep.ALL_METHODS.index("gc_net")
        E[:, :, :, gn] = E[:, :, :, ga] - E[:, :, :, gb]
        Er[:, :, :, gn] = Er[:, :, :, ga] - Er[:, :, :, gb]
        Erp[:, :, :, gn] = Erp[:, :, :, ga] - Erp[:, :, :, gb]
        # The histology in force: a channel group it leaves out of this rat
        # is out of every array, whatever the node measured (a run made
        # under an older scoring measured more, and nothing else differs:
        # each region is read on its own wire).
        gone = [ri for ri, n in enumerate(sweep.regions())
                if n in (d.get("blocked") or {})]
        if gone:
            pis = [pi for pi, (a, b) in enumerate(
                sweep.pairs_of(list(range(R)))) if a in gone or b in gone]
            ops = [ph * R + am for ph in range(R) for am in range(R)
                   if ph in gone or am in gone]
            for A in (E, Er, Erp):
                A[..., pis] = np.nan
            for A in (Pw, Pwr, Pwrp):
                A[..., gone] = np.nan
            for A in (PAC, PACr, PACrp):
                A[..., ops] = np.nan
            for A in (Wst, Wsl, Wfa, Wr, Wpr, Wrp):
                A[..., gone] = -1
        base = os.path.join(out_dir, "days", "r%d_%s" % (rat, day))
        for name, arr in (("edges", E), ("power", Pw), ("pac", PAC),
                          ("wires_state", Wst), ("wires_slow", Wsl),
                          ("wires_fast", Wfa), ("edges_rest", Er),
                          ("power_rest", Pwr), ("pac_rest", PACr),
                          ("wires_pair", Wpr), ("edges_rest_pair", Erp),
                          ("power_rest_pair", Pwrp), ("pac_rest_pair", PACrp),
                          ("wires_rest_pair", Wrp),
                          ("wires_rest", Wr)):
            np.save(base + "_" + name + ".npy", arr)
    return {"filled": filled, "missing": missing, "refusals": refusals}


def _load_day(out_dir, rat, day, name, mmap=None):
    path = os.path.join(out_dir, "days", "r%d_%s_%s.npy" % (rat, day, name))
    if not os.path.isfile(path):
        return None
    return np.load(path, mmap_mode=mmap)


def pooled(out_dir, man, what, keep=None):
    """{layer: {quantity: array}} for edges, power or pac.

    `keep(day, unit) -> bool`, when given, pools only those cue pairs (a
    split by cue pair, `SPLITS`); a rat-day with none of them leaves that
    rat out. Rest epochs are never split: they have no cue."""
    cue_name, rest_name = {"edges": ("edges", "edges_rest"),
                           "power": ("power", "power_rest"),
                           "pac": ("pac", "pac_rest")}[what]
    cue, rest = {}, {}
    for d in core_view(man)["days"]:
        key = (d["rat"], d["day"])
        X = _load_day(out_dir, d["rat"], d["day"], cue_name,
                      mmap="r" if keep else None)
        if X is None or not X.shape[0]:
            continue
        if keep is not None:
            idx = [i for i, u in enumerate(d["units"]) if keep(d, u)]
            if not idx:
                continue
            X = np.asarray(X[idx])
        cue[key] = day_stats(with_contrast(X, pac=(what == "pac")))
        Xr = _load_day(out_dir, d["rat"], d["day"], rest_name)
        if Xr is not None and Xr.shape[0]:
            rest[key] = _rest_for(out_dir, d, rest_name, Xr,
                                  cue[key][0].shape[0], what == "pac")
    out = {}
    for layer in LAYERS:
        if not cue:
            continue
        rats, Y, V = layer_changes(cue, rest, layer)
        got = pool(Y, V)
        got["rats"] = rats
        out[layer] = got
    # The contrast is raw only: rest cancels from Cue 2 - Cue 1 exactly.
    if "raw" in out and "minus_fp" in out:
        for k, v in out["raw"].items():
            if isinstance(v, np.ndarray) and v.ndim and \
                    isinstance(out["minus_fp"].get(k), np.ndarray):
                out["minus_fp"][k][-1] = v[-1]
    return out


#: The Monolith split by cue pair: each rat's AB and its CD, by the seats
#: on the lab's identity sheet (ratidentity.py, the lab, 2026-10-06). Every
#: rat has both, so each half has all eight rats and is pooled exactly as
#: the whole is. Which physical sounds those are is counterbalanced, so a
#: half averages the sounds out. (The earlier Click/Noise, High/Low and
#: later-role halves are gone: the first two cut across AB/CD, because
#: every pair crosses modality, and the third read the Con sessions, which
#: this analysis does not go into.)
SPLITS = (
    ("ab", "AB pair (A → B)", "pair"),
    ("cd", "CD pair (C → D)", "pair"),
)
SPLIT_IDS = tuple(g for g, _l, _f in SPLITS)
SPLIT_FAMILY_SAY = {
    "pair": "by each rat's own seats, from the lab's identity sheet: AB is "
            "the pair heard A → B, CD the pair heard C → D; which sounds "
            "those are is counterbalanced across rats",
}


def split_member(group, cue_type, role=None):
    """Whether a presentation belongs to a split: `role` is its pair in
    its rat, "AB" or "CD" (roles_of)."""
    return {"ab": role == "AB", "cd": role == "CD"}.get(group, False)


def split_keep(group, roles):
    """keep(day, unit) for pooled(): `roles` is {rat: {cue_type: "AB" |
    "CD"}}."""
    def keep(d, u):
        r = (roles.get(int(d["rat"])) or {}).get(u.get("cue_type"))
        return split_member(group, u.get("cue_type"), r)
    return keep


def split_build(man, summary, out_dir, roles, role_notes=None,
                progress=None, check=None):
    """Every split pooled exactly as the whole is: the page's files
    `<edges|power|pac>_<layer>__<group>.f32`, each split's points of
    interest and counts, written into the summary under `splits`."""
    say = progress or (lambda *a: None)
    names = summary["regions"]
    pairs = [tuple(p) for p in summary["pairs"]]
    # The shapes this build has (a Monolith built before a band or the
    # PAC transitions were added has fewer), not the code's.
    shapes = {w: tuple(summary["files"]["%s_raw.f32" % w]["shape"][1:])
              for w in ("edges", "power", "pac")}
    files, top, cnt, groups = {}, {}, {}, []
    ctop, ccnt = {}, {}
    core = core_view(man)["days"]
    for n_, (g, label, fam) in enumerate(SPLITS):
        keep = split_keep(g, roles)
        rats = sorted({int(d["rat"]) for d in core
                       if any(keep(d, u) for u in d["units"])})
        n_units = sum(1 for d in core for u in d["units"]
                      if keep(d, u))
        groups.append({"id": g, "label": label, "family": fam,
                       "rats": rats, "n_units": n_units})
        for what in ("edges", "power", "pac"):
            say("split", n_, len(SPLITS), "%s · %s" % (label, what))
            if check:
                check()
            got = pooled(out_dir, man, what, keep=keep)
            for layer, gl in got.items():
                fname = "%s_%s__%s.f32" % (what, layer, g)
                path = os.path.join(out_dir, fname)
                nbytes = write_layer(path, gl, shapes[what])
                files[fname] = {"bytes": nbytes, "sha256": _sha(path),
                                "shape": [len(QUANTITIES)] + list(
                                    shapes[what])}
                if what == "edges":
                    t_, c_, ct_, cc_ = _tops(gl, layer, names, pairs)
                    top.setdefault(g, {})[layer] = t_
                    cnt.setdefault(g, {})[layer] = c_
                    if layer == "raw":
                        ctop.setdefault(g, {})[layer] = ct_
                        ccnt.setdefault(g, {})[layer] = cc_
    summary["splits"] = {
        "at": now_iso(), "groups": groups, "files": files, "top": top,
        "counts": cnt, "family_say": SPLIT_FAMILY_SAY,
        "contrast": {"top": ctop, "counts": ccnt},
        "roles": {str(k): v for k, v in (role_notes or {}).items()},
        "role_map": {str(k): dict(v) for k, v in (roles or {}).items()},
    }
    _write_json(os.path.join(out_dir, "summary.json"), summary)
    return summary["splits"]


def split_role_map(summary):
    """{rat: {cue_type: role}} as the split was built with."""
    rm = (summary.get("splits") or {}).get("role_map") or {}
    return {int(k): v for k, v in rm.items()}


def roles_of(man, records=None):
    """{rat: {cue_type: "AB" | "CD"}} from the lab's identity sheet
    (ratidentity.py), and what each rat's seats are. A rat whose recorded
    pairings are not its two pairs on the sheet is left out of the split,
    and said. `records` is unused; it is kept for callers of the older
    reader."""
    from . import ratidentity as RI
    roles, notes = {}, {}
    for rat in sorted({int(d["rat"]) for d in man["days"]}):
        cts = {u.get("cue_type") for d in man["days"] if int(d["rat"]) == rat
               for u in d["units"] if u.get("cue_type")}
        try:
            got = RI.check(rat, cts)
        except RI.IdentityError as exc:
            notes[rat] = {"error": str(exc)}
            continue
        roles[rat] = {got["AB"]: "AB", got["CD"]: "CD"}
        notes[rat] = {"seats": RI.identity(rat), "AB": got["AB"],
                      "CD": got["CD"], "sheet": RI.SHEET_FILE}
    return roles, notes


def extend_work(worker, host, cfg):
    """Precon2 and Precon3 into the manifest, for the trajectory. Reads
    only (the bank, the registry, histology, the rest clipping)."""
    worker.note(phase="extending")
    man, added = extend_manifest(host, cfg, progress=lambda i, n, item:
                                 worker.note(i=i, of=n, item=item))
    worker.check()
    save_manifest(man)
    return {"added": added, "digest": man["digest"]}


def trajectory_status(st, man, summary):
    """Where the trajectory is: in what goes, whole on the cluster, run,
    built."""
    chk = st.get("check") or {}
    have = sorted({d["day"] for d in (man or {}).get("days") or []
                   if d["day"] in TRAJ_NAMES})
    return {"days": list(TRAJ_NAMES), "in_manifest": have,
            "ready": chk.get("traj_ready") or [],
            "checked_now": bool(man) and chk.get("manifest") == man.get(
                "digest"),
            # The run on the cluster now is the one that measures them.
            "running": bool(((st.get("run") or {}).get("adds") or {})
                            .get("days")),
            "built": ((summary or {}).get("trajectory") or {}).get("days")
            or [],
            # The whole pair's 20 s rest, on every day of what goes.
            "pair_rest": bool(man) and all(d.get("rest_pair") is not None
                                           for d in man.get("days") or [])}


#: Monolith Progress (the lab, 2026-10-06): every session's own value,
#: and each session's change from Precon1, for every entry -- descriptive,
#: never tested. Per session the mean over rats of each rat's session mean
#: (less its rest, minus FP; the contrast raw), its SE and the rats it rests
#: on; and the mean over rats of each rat's Pk - P1, and its SE.
SESSION_Q = ("mean", "se", "n", "chg", "chg_se")


def session_build(man, summary, out_dir, roles=None, progress=None,
                  check=None):
    """The page's Progress files, one per window so the page reads only
    the one it shows: `session_<edges|power>_<layer>[__<group>]_<w>.f32`,
    (sessions, SESSION_Q, ...) float32. Written into the summary under
    `sessions`."""
    say = progress or (lambda *a: None)
    tdays = set((summary.get("trajectory") or {}).get("days") or [])
    order = [x for x in ALL_DAY_ORDER if x in DAY_NAMES or x in tdays]
    days = [d for d in man["days"] if d["day"] in order]
    rats = sorted({int(d["rat"]) for d in days})
    groups = [None] + ([g for g in SPLIT_IDS] if roles else [])
    files = {}
    for gi, g in enumerate(groups):
        keep = split_keep(g, roles) if g else None
        for what in ("edges", "power"):
            say("sessions", gi, len(groups), "%s · %s" % (g or "pooled", what))
            if check:
                check()
            cue_name, rest_name = {"edges": ("edges", "edges_rest"),
                                   "power": ("power", "power_rest")}[what]
            per = {layer: {} for layer in LAYERS}      # layer -> (rat, day) -> m
            for d in days:
                X = _load_day(out_dir, d["rat"], d["day"], cue_name,
                              mmap="r" if keep else None)
                if X is None or not X.shape[0]:
                    continue
                if keep is not None:
                    idx = [i for i, u in enumerate(d["units"]) if keep(d, u)]
                    if not idx:
                        continue
                    X = np.asarray(X[idx])
                m, _s2, n = day_stats(with_contrast(X))
                m = np.where(n > 0, m, np.nan)
                key = (int(d["rat"]), d["day"])
                per["raw"][key] = m
                Xr = _load_day(out_dir, d["rat"], d["day"], rest_name)
                if Xr is not None and Xr.shape[0]:
                    rm, _r2, rn = _rest_for(out_dir, d, rest_name, Xr,
                                            m.shape[0])
                    mm = np.where(rn > 0, m - rm, np.nan)
                    mm[-1] = m[-1]                      # the contrast: raw
                    per["minus_fp"][key] = mm
            for layer in LAYERS:
                got = per[layer]
                if not got:
                    continue
                shape = next(iter(got.values())).shape  # (W+1, ...)
                out = np.full((len(order), len(SESSION_Q)) + shape, np.nan,
                              np.float32)
                for si, day in enumerate(order):
                    A = [got[(r, day)] for r in rats if (r, day) in got]
                    if A:
                        mm, s2, nn = day_stats(np.stack(A))
                        out[si, 0], out[si, 1], out[si, 2] = \
                            mm, np.sqrt(s2), nn
                    C = [got[(r, day)] - got[(r, order[0])] for r in rats
                         if (r, day) in got and (r, order[0]) in got]
                    if C:
                        cm, cs2, _cn = day_stats(np.stack(C))
                        out[si, 3], out[si, 4] = cm, np.sqrt(cs2)
                for w in range(shape[0]):
                    fname = "session_%s_%s%s_%d.f32" % (
                        what, layer, "__" + g if g else "", w)
                    path = os.path.join(out_dir, fname)
                    arr = np.ascontiguousarray(out[:, :, w])
                    arr.tofile(path)
                    files[fname] = {"shape": list(arr.shape)}
    summary["sessions"] = {"order": order, "quantities": list(SESSION_Q),
                           "files": files, "at": now_iso()}
    _write_json(os.path.join(out_dir, "summary.json"), summary)
    return summary["sessions"]


def split_work(worker, artifacts=None, by=None, roles_reader=None):
    """Split the built Monolith by cue pair, here: about two minutes."""
    d = data_dir()
    summ = summary_now()
    man = _read_json(_path("manifest.json"))
    if not d or not summ or not man:
        raise MonolithError("The Monolith has not been built yet.", 409)
    worker.note(phase="roles")
    roles, notes = (roles_reader or roles_of)(man)
    worker.note(phase="splitting")
    got = split_build(man, summ, d, roles, notes,
                      progress=lambda what, i, of, item: worker.note(
                          phase="splitting", i=i, of=of, item=item),
                      check=worker.check)
    worker.note(phase="sessions")
    session_build(man, summ, d, roles=roles, check=worker.check)
    if artifacts is not None:
        worker.note(phase="filing")
        rec = file_artifact(artifacts, summ, man, by=by)
        st = get_state().get("built") or {}
        save_state(built=dict(st, artifact_id=rec.get("id"),
                              version=rec.get("version"), split_at=got["at"]))
    return {"groups": [g["id"] for g in got["groups"]], "at": got["at"]}


def sessions_work(worker):
    """Monolith Progress's session files for the built Monolith, here, from
    the day arrays already fetched (a build made before Progress existed
    has none). Seconds to a minute; nothing is fetched or run."""
    d = data_dir()
    summ = summary_now()
    man = _read_json(_path("manifest.json"))
    if not d or not summ or not man:
        raise MonolithError("The Monolith has not been built yet.", 409)
    roles = split_role_map(summ) if (summ.get("splits") or {}).get(
        "files") else None
    worker.note(phase="sessions")
    got = session_build(man, summ, d, roles=roles,
                        progress=lambda what, i, of, item: worker.note(
                            phase="sessions", i=i, of=of, item=item),
                        check=worker.check)
    return {"files": len(got["files"]), "order": got["order"]}


# ==========================================================================
# Physical cue against balanced cue (the lab, 2026-10-06)
# ==========================================================================
# The comparisons are made by seat (A, B, C, D), which the identity sheet
# counterbalances over the four sounds. It does so in a way that makes the
# sounds testable with the numbers the Monolith already has: every rat opens
# BOTH its pairs with the same kind of sound -- a noise-like one (Click or
# Noise) for J3, J6, J7 and J8, a tone (High or Low) for J4, J9, J10 and J11
# -- and every ordered pair of sounds (Click → Low tone, ...) is heard by
# exactly two rats. So each rat's own Precon4 − Precon1 change can be signed
# by sound instead of by seat:
#
#   order        tone-first rats against noise-first rats (between rats,
#                four against four): in Cue 1 one group hears a tone and
#                the other a noise, in Cue 2 the other way round
#   sound_noise  within each noise-first rat, its Click-first pair against
#                its Noise-first pair
#   sound_tone   within each tone-first rat, its High-first pair against
#                its Low-first pair
#   tone_noise   Cue 2 − Cue 1 signed as tone − noise: it is tone − noise
#                for the noise-first rats as it stands and noise − tone for
#                the tone-first ones, so their sign is flipped
#   seat_abcd    the seat counterpart: each rat's AB against its CD
#
# If the sound itself drove a result, its sound-signed version would show
# it. The evidence that it did not: across every entry the sound-signed
# versions pass p < .05 at about the chance rate, and no more often than an
# arbitrary relabelling does (every other 4 + 4 split of the rats; every
# other way of signing the rats); and each lead holds in both groups of
# four, within half its own size (an equivalence test). Every p uncorrected.
NOISE_LIKE = ("Click", "Noise")
PHYS = (
    ("order", "Tone-first rats against noise-first rats", "sound"),
    ("sound_noise", "Click-first pair against Noise-first pair, in the noise-first rats", "sound"),
    ("sound_tone", "High-first pair against Low-first pair, in the tone-first rats", "sound"),
    ("tone_noise", "Cue 2 − Cue 1 signed as tone − noise", "sound"),
    ("seat_abcd", "AB against CD, in every rat", "seat"),
)
PHYS_IDS = tuple(c for c, _l, _k in PHYS)


#: Each sound on its own (the lab, 2026-10-07): every rat heard all four,
#: each in the cue window of its own seat -- A and C open their pairs (Cue
#: 1), B and D close them (Cue 2) -- so a rat's change while a sound plays
#: is that seat's window, and the four sounds are compared within rat.
SOUNDS = ("Click", "Noise", "High", "Low")
SOUND_PAIRS = tuple((a, b) for i, a in enumerate(SOUNDS) for b in SOUNDS[i + 1:])
SOUND_PAIR_IDS = tuple("%s-%s" % p for p in SOUND_PAIRS)
SOUND_IDS = SOUNDS + SOUND_PAIR_IDS + ("omni",)
SEAT_AT = {"A": ("ab", "cue1"), "B": ("ab", "cue2"), "C": ("cd", "cue1"),
           "D": ("cd", "cue2")}


def sound_changes(ab_l, cd_l):
    """(rats, Y, V): each rat's Precon4 − Precon1 change while each sound
    plays, (rats, sounds, bands, measures, pairs), from its AB and its CD:
    the cue window of the seat that sound has for that rat."""
    ra, Ya, Va = ab_l
    rc, Yc, Vc = cd_l
    rats = [r for r in ra if r in rc and ratidentity.identity(r)]
    wi = {w: WINDOWS.index(w) for w in ("cue1", "cue2")}
    shape = Ya.shape[2:]
    Y = np.full((len(rats), len(SOUNDS)) + shape, np.nan)
    V = np.full((len(rats), len(SOUNDS)) + shape, np.nan)
    for i, r in enumerate(rats):
        for seat, snd in ratidentity.identity(r).items():
            if snd not in SOUNDS or seat not in SEAT_AT:
                continue
            half, w = SEAT_AT[seat]
            src, var, rr = (Ya, Va, ra) if half == "ab" else (Yc, Vc, rc)
            j = rr.index(r)
            Y[i, SOUNDS.index(snd)] = src[j, wi[w]]
            V[i, SOUNDS.index(snd)] = var[j, wi[w]]
    return rats, Y, V


def rm_anova(X):
    """One-way repeated-measures ANOVA over axis 1 (the sounds), the rats
    as subjects, at every entry: {F, p, k, spread}. A rat counts at an entry
    only with every sound there; `spread` is the largest sound mean less
    the smallest."""
    import warnings
    from scipy.stats import f as _fd
    S = X.shape[1]
    ok = np.all(np.isfinite(X), axis=1)
    k = ok.sum(axis=0)
    Xm = np.where(ok[:, None], X, np.nan)
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        grand = np.nanmean(Xm, axis=(0, 1))
        ms = np.nanmean(Xm, axis=0)
        mr = np.nanmean(Xm, axis=1)
        ss_tot = np.nansum((Xm - grand) ** 2, axis=(0, 1))
        ss_snd = k * np.nansum((ms - grand) ** 2, axis=0)
        ss_rat = S * np.nansum((mr - grand) ** 2, axis=0)
        ss_err = ss_tot - ss_snd - ss_rat
        df2 = (S - 1) * (k - 1)
        F = (ss_snd / (S - 1)) / (ss_err / np.maximum(df2, 1))
        spread = np.nanmax(ms, axis=0) - np.nanmin(ms, axis=0)
    good = (k >= MIN_RATS) & np.isfinite(F) & (ss_err > 1e-30)
    p = np.full(F.shape, np.nan)
    if good.any():
        p[good] = _fd.sf(F[good], S - 1, df2[good])
    return {"F": np.where(good, F, np.nan), "p": p, "k": k,
            "spread": np.where(good, spread, np.nan)}


def sound_compare(ab_l, cd_l, check=None, n_perm=200, seed=6):
    """Each sound's own change, every pair of sounds (within rat: the change
    while one played less the change while the other did) and whether the
    four differ at all, at every entry; with their nulls: every way of
    signing the rats' differences (the pairs), and random relabellings of
    the four sounds within each rat (the four)."""
    rats, Y, V = sound_changes(ab_l, cd_l)
    n = len(rats)
    got = {}
    for i, s in enumerate(SOUNDS):
        got[s] = pool(Y[:, i], V[:, i])
    perm = {"pairs": {}, "omni": None}
    for (a, b), pid in zip(SOUND_PAIRS, SOUND_PAIR_IDS):
        ia, ib = SOUNDS.index(a), SOUNDS.index(b)
        D, DV = Y[:, ia] - Y[:, ib], V[:, ia] + V[:, ib]
        got[pid] = pool(D, DV)
        cs = []
        if 2 <= n <= 10:
            shp = (-1,) + (1,) * (D.ndim - 1)
            for bits in range(2 ** (n - 1)):
                if check and bits % 32 == 0:
                    check()
                sg = np.array([1.0] + [(-1.0 if (bits >> j) & 1 else 1.0) for j in range(n - 1)])
                cs.append(int((np.asarray(pool(D * sg.reshape(shp), DV)["p"]) < 0.05).sum()))
        obs = int((np.asarray(got[pid]["p"]) < 0.05).sum())
        perm["pairs"][pid] = {"counts": cs, "observed": obs, "n": len(cs),
                              "rank": _rank(cs, obs) if cs else None,
                              "say": "every way of signing the rats' differences"}
    om = rm_anova(Y)
    got["omni"] = {"est": om["spread"], "p": om["p"], "k": om["k"].astype(np.float64),
                   "same": np.zeros(om["p"].shape),
                   "se": np.full(om["p"].shape, np.nan),
                   "why": np.where(np.isfinite(om["p"]), 0, 1).astype(np.uint8)}
    obs = int((om["p"] < 0.05).sum())
    cs = [obs]
    rng = np.random.default_rng(seed)
    if n >= 2:
        for k_ in range(n_perm):
            if check and k_ % 20 == 0:
                check()
            Yp = np.stack([Y[i, rng.permutation(len(SOUNDS))] for i in range(n)])
            cs.append(int((rm_anova(Yp)["p"] < 0.05).sum()))
    perm["omni"] = {"counts": cs, "observed": obs, "n": len(cs), "rank": _rank(cs, obs),
                    "say": "the sounds as named, and %d random relabellings of the four within each rat" % (len(cs) - 1)}
    return {"rats": rats, "got": got, "omni": om, "perm": perm, "shape": tuple(Y.shape[2:])}


def opener_kind(rat):
    """"noise" or "tone": what opens both of a rat's pairs (seats A and C),
    or None if the sheet does not have the rat or its two openers differ in
    kind (the counterbalancing would then not hold for it)."""
    ids = ratidentity.identity(rat)
    if not ids:
        return None
    ka = "noise" if ids["A"] in NOISE_LIKE else "tone"
    kc = "noise" if ids["C"] in NOISE_LIKE else "tone"
    return ka if ka == kc else None


def ab_opens_first_sound(rat):
    """+1 when the rat's AB is opened by Click (noise-first rats) or High
    (tone-first rats), −1 when its CD is: the sign that turns AB − CD into
    Click-first − Noise-first, or High-first − Low-first."""
    ids = ratidentity.identity(rat)
    return 1.0 if ids and ids["A"] in ("Click", "High") else -1.0


def rat_changes(out_dir, man, what="edges", keep=None):
    """{layer: (rats, Y, V)}: each rat's own Precon4 − Precon1 change and
    its variance, at every entry (the contrast's slot last), exactly as
    pooled() works them out before pooling them."""
    cue_name, rest_name = {"edges": ("edges", "edges_rest"),
                           "power": ("power", "power_rest")}[what]
    cue, rest = {}, {}
    for d in core_view(man)["days"]:
        key = (d["rat"], d["day"])
        X = _load_day(out_dir, d["rat"], d["day"], cue_name,
                      mmap="r" if keep else None)
        if X is None or not X.shape[0]:
            continue
        if keep is not None:
            idx = [i for i, u in enumerate(d["units"]) if keep(d, u)]
            if not idx:
                continue
            X = np.asarray(X[idx])
        cue[key] = day_stats(with_contrast(X))
        Xr = _load_day(out_dir, d["rat"], d["day"], rest_name)
        if Xr is not None and Xr.shape[0]:
            rest[key] = _rest_for(out_dir, d, rest_name, Xr,
                                  cue[key][0].shape[0])
    out = {}
    for layer in LAYERS:
        if cue:
            out[layer] = layer_changes(cue, rest, layer)
    # The contrast is raw only, as pooled() has it: layer_changes would take
    # the rest off Cue 2 − Cue 1 itself, where it has already cancelled.
    if "raw" in out and "minus_fp" in out:
        rr, Yr, Vr = out["raw"]
        rm, Ym, Vm = out["minus_fp"]
        for i, r in enumerate(rm):
            if r in rr:
                j = rr.index(r)
                Ym[i, -1], Vm[i, -1] = Yr[j, -1], Vr[j, -1]
    return out


def pool_diff(a, b):
    """Two pools' difference, a − b, tested with Welch's t on the two
    Hartung–Knapp standard errors (Satterthwaite's df). {est, p, k, same,
    se, why}: `same` is 1 where both groups changed the same way."""
    est = a["est"] - b["est"]
    sa2, sb2 = a["se"] ** 2, b["se"] ** 2
    se = np.sqrt(sa2 + sb2)
    with np.errstate(invalid="ignore", divide="ignore"):
        df = (sa2 + sb2) ** 2 / (sa2 ** 2 / np.maximum(a["k"] - 1, 1)
                                 + sb2 ** 2 / np.maximum(b["k"] - 1, 1))
    ok = np.isfinite(est) & np.isfinite(se) & (se > 0) & np.isfinite(df)
    p = np.full(est.shape, np.nan)
    if ok.any():
        p[ok] = stdtr_p(est[ok] / se[ok], df[ok])
    why = np.where(ok, 0, np.where((a["k"] < MIN_RATS) | (b["k"] < MIN_RATS),
                                   1, 4)).astype(np.uint8)
    same = ((np.sign(a["est"]) == np.sign(b["est"])) & (a["est"] != 0)
            ).astype(np.float64)
    return {"est": est, "p": p, "k": a["k"] + b["k"], "same": same,
            "se": np.where(ok, se, np.nan), "why": why, "df": df}


def sound_row(snd, t0):
    """One lead, at its frequency, measure and region pair, while each sound
    plays: each sound's change, whether the four differ, and every pair."""
    if snd is None:
        return None
    a3 = (t0["bi"], t0["mi"], t0["pair"])
    G = snd["got"]
    return {"sounds": [{"sound": s, "est": _f(G[s]["est"][a3]), "se": _f(G[s]["se"][a3]),
                        "k": _f(G[s]["k"][a3]), "p": _f(G[s]["p"][a3])} for s in SOUNDS],
            "omni": {"F": _f(snd["omni"]["F"][a3]), "p": _f(G["omni"]["p"][a3]),
                     "k": _f(G["omni"]["k"][a3])},
            "pairs": {pid: {"est": _f(G[pid]["est"][a3]), "p": _f(G[pid]["p"][a3])}
                      for pid in SOUND_PAIR_IDS}}


def _count(got, sl=slice(None)):
    p = np.asarray(got["p"])[sl]
    tested = int(np.isfinite(p).sum())
    return {"tested": tested, "p05": int((p < 0.05).sum()),
            "p01": int((p < 0.01).sum()), "p001": int((p < 0.001).sum()),
            "chance_p05": int(round(0.05 * tested))}


def _rank(counts, observed):
    """Where `observed` falls among a relabelling's counts: how many of them
    pass at least as many entries (1 = the most)."""
    return int(sum(1 for c in counts if c >= observed))


def physical_build(man, summary, out_dir, roles, progress=None, check=None):
    """Section 6: every comparison by sound, at every entry, with the
    relabelling nulls and the leads split by group. Writes
    phys_edges_<layer>__<comparison>.f32 (QUANTITIES, the edges' shape),
    phys_groups_<layer>.f32 (tone est, se, k, noise est, se, k) and
    physical.json; the summary gets `physical`."""
    from itertools import combinations
    say = progress or (lambda *a: None)
    names = summary["regions"]
    pairs = summary["pairs"]
    nwin = len(WINDOWS)                     # the measured windows
    say("physical", 0, 4, "each rat's change, both pairs")
    if check:
        check()
    whole = rat_changes(out_dir, man)
    say("physical", 1, 4, "each rat's change, AB alone")
    ab = rat_changes(out_dir, man, keep=split_keep("ab", roles)) if roles else {}
    if check:
        check()
    say("physical", 2, 4, "each rat's change, CD alone")
    cd = rat_changes(out_dir, man, keep=split_keep("cd", roles)) if roles else {}
    files, counts, perm, groups_out = {}, {}, {}, {}
    sound_out = {"names": list(SOUNDS), "say": dict(ratidentity.SOUND_SAY),
                 "pairs": list(SOUND_PAIR_IDS), "counts": {}, "perm": {}, "rats": [],
                 "seat_at": {k: list(v) for k, v in SEAT_AT.items()}}
    shape = None
    leads = {}
    for layer in LAYERS:
        if layer not in whole:
            continue
        if check:
            check()
        say("physical", 3, 4, "%s · the comparisons and their nulls" % layer)
        rats, Y, V = whole[layer]
        shape = Y.shape[1:]
        kind = {r: opener_kind(r) for r in rats}
        gi = {g: [i for i, r in enumerate(rats) if kind[r] == g]
              for g in ("tone", "noise")}
        groups_out = {g: [rats[i] for i in ix] for g, ix in gi.items()}
        got = {}
        pt, pn = pool(Y[gi["tone"]], V[gi["tone"]]), pool(Y[gi["noise"]], V[gi["noise"]])
        got["order"] = pool_diff(pt, pn)
        G = np.stack([pt["est"], pt["se"], pt["k"], pn["est"], pn["se"], pn["k"]]).astype(np.float32)
        gname = "phys_groups_%s.f32" % layer
        G.tofile(os.path.join(out_dir, gname))
        files[gname] = {"shape": list(G.shape), "quantities": ["tone_est", "tone_se", "tone_k",
                                                               "noise_est", "noise_se", "noise_k"]}
        # The pair against pair, signed by seat and by sound, in the rats
        # with both their AB and their CD.
        if layer in ab and layer in cd:
            ra, Ya, Va = ab[layer]
            rc, Yc, Vc = cd[layer]
            both = [r for r in ra if r in rc]
            D_ = np.stack([Ya[ra.index(r)] - Yc[rc.index(r)] for r in both])
            DV = np.stack([Va[ra.index(r)] + Vc[rc.index(r)] for r in both])
            got["seat_abcd"] = pool(D_, DV)
            sgn = np.array([ab_opens_first_sound(r) for r in both])
            sel = lambda g: [i for i, r in enumerate(both) if opener_kind(r) == g]   # noqa: E731
            shd = (-1,) + (1,) * D_[0].ndim
            for cid, g in (("sound_noise", "noise"), ("sound_tone", "tone")):
                ix = sel(g)
                got[cid] = pool(D_[ix] * sgn[ix].reshape(shd), DV[ix])
                # Every way of signing these rats' AB − CD (the first rat's
                # sign fixed: flipping them all gives the same p): by seat
                # (none flipped) and by sound are two of them.
                n_ = len(ix)
                if check:
                    check()
                cs3 = []
                if 2 <= n_ <= 10:
                    for bits in range(2 ** (n_ - 1)):
                        s = np.array([1.0] + [(-1.0 if (bits >> i) & 1 else 1.0) for i in range(n_ - 1)])
                        gg = pool(D_[ix] * s.reshape(shd), DV[ix])
                        cs3.append(int((np.asarray(gg["p"])[:nwin] < 0.05).sum()))
                obs3 = int((np.asarray(got[cid]["p"])[:nwin] < 0.05).sum())
                seat3 = int((np.asarray(pool(D_[ix], DV[ix])["p"])[:nwin] < 0.05).sum())
                perm.setdefault(cid, {})[layer] = {
                    "counts": cs3, "observed": obs3, "n": len(cs3),
                    "rank": _rank(cs3, obs3) if cs3 else None,
                    "seat": seat3, "seat_rank": _rank(cs3, seat3) if cs3 else None,
                    "rats": [both[i] for i in ix],
                    "say": "every way of signing these rats' AB − CD"}
        # Cue 2 − Cue 1 as tone − noise: the contrast's slot, the
        # tone-first rats' sign flipped.
        s_tn = np.array([1.0 if kind[r] == "noise" else -1.0 if kind[r] == "tone" else np.nan
                         for r in rats])
        okr = np.isfinite(s_tn)
        sh1 = (-1,) + (1,) * (Y.ndim - 1)
        tn = pool(Y[okr] * s_tn[okr].reshape(sh1), V[okr])
        for k in tn:
            if isinstance(tn[k], np.ndarray) and tn[k].ndim:
                tn[k][:nwin] = np.nan if tn[k].dtype.kind == "f" else 5
        got["tone_noise"] = tn
        for cid, g in got.items():
            fname = "phys_edges_%s__%s.f32" % (layer, cid)
            write_layer(os.path.join(out_dir, fname), g, shape)
            files[fname] = {"shape": [len(QUANTITIES)] + list(shape)}
            sl = slice(nwin, nwin + 1) if cid == "tone_noise" else slice(0, nwin)
            counts.setdefault(cid, {})[layer] = _count(g, sl)
        # The relabelling nulls. Every way of splitting the rats into two
        # fours, for the order: does tone against noise pass more entries
        # than any arbitrary split?
        idx8 = list(range(len(rats)))
        splits = []
        if len(gi["tone"]) >= MIN_RATS and len(gi["noise"]) >= MIN_RATS and len(rats) == 8:
            for a in combinations(idx8, 4):
                b = tuple(i for i in idx8 if i not in a)
                if a > b:
                    continue
                splits.append((list(a), list(b)))
        cs = []
        for a, b in splits:
            if check:
                check()
            g = pool_diff(pool(Y[a], V[a]), pool(Y[b], V[b]))
            cs.append(int((np.asarray(g["p"])[:nwin] < 0.05).sum()))
        obs = counts["order"][layer]["p05"]
        perm.setdefault("order", {})[layer] = {
            "counts": cs, "observed": obs, "n": len(cs),
            "rank": _rank(cs, obs) if cs else None,
            "say": "every way of splitting the eight rats into two fours"}
        # Every way of signing the rats, for Cue 2 − Cue 1: the balanced
        # contrast (no flips) and tone − noise are two of them.
        cs2 = []
        Yc21, Vc21 = Y[:, nwin], V[:, nwin]
        n8 = len(rats)
        if n8 <= 10:
            for bits in range(2 ** (n8 - 1)):
                s = np.array([1.0] + [(-1.0 if (bits >> i) & 1 else 1.0) for i in range(n8 - 1)])
                g = pool(Yc21 * s.reshape((-1,) + (1,) * (Yc21.ndim - 1)), Vc21)
                cs2.append(int((np.asarray(g["p"]) < 0.05).sum()))
        bal = int((np.asarray(pool(Yc21, Vc21)["p"]) < 0.05).sum())
        perm.setdefault("tone_noise", {})[layer] = {
            "counts": cs2, "observed": counts["tone_noise"][layer]["p05"], "n": len(cs2),
            "rank": _rank(cs2, counts["tone_noise"][layer]["p05"]) if cs2 else None,
            "balanced": bal, "balanced_rank": _rank(cs2, bal) if cs2 else None,
            "say": "every way of signing the eight rats' Cue 2 − Cue 1"}
        # Each sound on its own: all eight rats, each sound in its own
        # seat's cue window, compared within rat.
        snd = None
        if layer in ab and layer in cd:
            if check:
                check()
            say("physical", 3, 4, "%s · each sound on its own" % layer)
            snd = sound_compare(ab[layer], cd[layer], check=check)
            for sid, g in snd["got"].items():
                fname = "phys_snd_%s__%s.f32" % (layer, sid)
                write_layer(os.path.join(out_dir, fname), g, (1,) + snd["shape"])
                files[fname] = {"shape": [len(QUANTITIES), 1] + list(snd["shape"])}
            sound_out["counts"][layer] = {sid: _count(g) for sid, g in snd["got"].items()}
            sound_out["perm"][layer] = snd["perm"]
            sound_out["rats"] = snd["rats"]
        # The leads, split by group, each with an equivalence test at half
        # its own size.
        from scipy.stats import t as _t
        tops = [("monolith", (summary.get("top") or {}).get(layer) or []),
                ("contrast", ((summary.get("contrast") or {}).get("top") or {}).get("raw") or [])]
        for kind_, lst in tops:
            rows = []
            for t0 in lst[:50]:
                at = (t0["wi"], t0["bi"], t0["mi"], t0["pair"])
                g = got["order"]
                q = lambda a: _f(np.asarray(a)[at])   # noqa: E731
                te, tse, tk = q(pt["est"]), q(pt["se"]), q(pt["k"])
                ne, nse, nk = q(pn["est"]), q(pn["se"]), q(pn["k"])
                d, dse, ddf, dp = q(g["est"]), q(g["se"]), q(g["df"]), q(g["p"])
                m = abs(t0["est"]) / 2.0
                eq = None
                if d is not None and dse is not None and ddf is not None and dse > 0:
                    h = float(_t.ppf(0.95, ddf)) * dse
                    eq = {"lo": d - h, "hi": d + h, "margin": m, "within": bool(d - h > -m and d + h < m)}
                rows.append({"w": t0["w"], "wi": t0["wi"], "band": t0["band"], "bi": t0["bi"], "hz": t0.get("hz"),
                             "m": t0["m"], "mi": t0["mi"], "pair": t0["pair"], "a": t0["a"], "b": t0["b"],
                             "est": t0["est"], "p": t0["p"], "k": t0["k"], "same": t0["same"],
                             "tone": {"est": te, "se": tse, "k": tk}, "noise": {"est": ne, "se": nse, "k": nk},
                             "diff": {"est": d, "se": dse, "df": ddf, "p": dp},
                             "both_ways": bool(te is not None and ne is not None and t0["est"] != 0
                                               and np.sign(te) == np.sign(ne) == np.sign(t0["est"])),
                             "equivalence": eq, "sound": sound_row(snd, t0)})
            if kind_ == "contrast" and layer != "raw":
                continue
            leads.setdefault(kind_, {})[layer if kind_ == "monolith" else "raw"] = rows
    out = {"at": now_iso(), "groups": groups_out,
           "group_say": {"noise": "open both pairs with a noise-like sound (Click or Noise), close with a tone",
                         "tone": "open both pairs with a tone (High or Low), close with Click or Noise"},
           "left_out": sorted(r for r in (whole.get("raw") or ([], None, None))[0] if opener_kind(r) is None),
           "comparisons": [{"id": c, "label": l, "by": k} for c, l, k in PHYS if c in counts],
           "files": files, "counts": counts, "perm": perm, "leads": leads,
           "sound": sound_out,
           "seat_counts": {"monolith": summary.get("counts") or {},
                           "contrast": ((summary.get("contrast") or {}).get("counts") or {})},
           "control_p05": 0.055,
           "control_say": "made-up data with no change at all, days the size of these (tools/check_monolith.py)"}
    _write_json(os.path.join(out_dir, "physical.json"), out)
    summary["physical"] = {"at": out["at"], "files": files,
                           "comparisons": out["comparisons"]}
    _write_json(os.path.join(out_dir, "summary.json"), summary)
    say("physical", 4, 4, "done")
    return out


def physical_work(worker):
    """Section 6 for the built Monolith, here, from the day arrays already
    fetched. A few minutes; nothing is fetched or run."""
    d = data_dir()
    summ = summary_now()
    man = _read_json(_path("manifest.json"))
    if not d or not summ or not man:
        raise MonolithError("The Monolith has not been built yet.", 409)
    roles = split_role_map(summ) if (summ.get("splits") or {}).get("files") else None
    worker.note(phase="physical")
    got = physical_build(man, summ, d, roles,
                         progress=lambda what, i, of, item: worker.note(
                             phase="physical", i=i, of=of, item=item),
                         check=worker.check)
    return {"comparisons": [c["id"] for c in got["comparisons"]], "at": got["at"]}


def additions_of(band_ids, pac_windows, kinds=()):
    """What a build has of the additions: {"delta": bool, "pac_trans":
    bool, "pair": bool} -- the whole pair only when its tasks were run."""
    return {"delta": "delta" in band_ids,
            "pac_trans": len(pac_windows) > len(sweep.STATE),
            "pair": "pair" in set(kinds)}


def fast_missing_of(asm, run):
    """[[rat, day], ...]: the rat-days whose fast transitions were refused
    because their transitions were not banked at -1/+2 s when they ran.
    Spark's transition check on those recordings makes them addable."""
    by = {}
    for ts in [run.get("tasks") or []] + [p_.get("tasks") or []
                                          for p_ in run.get("parts") or []]:
        for t in ts:
            by.setdefault(t["key"], t)
    out = set()
    for x in asm.get("refusals") or []:
        t = by.get(x.get("task"))
        if t and t["kind"] == "trans_fast" and "not banked" in (x.get("why")
                                                              or ""):
            out.add((int(t["rat"]), t["day"]))
    order = {d: i for i, d in enumerate(ALL_DAY_ORDER)}
    return [[r, d] for r, d in sorted(out, key=lambda k: (k[0], order.get(
        k[1], 9)))]


def refresh_fast(host, keys):
    """The days `keys` ([[rat, day], ...]) re-read from the bank where Spark
    has since clipping-checked their transitions at -1/+2 s: their
    `fast_banked`, and each cue pair's exclusions, which now hold the
    transition windows (the state windows come back as they were: one read
    answers both). Nothing else in the manifest moves. Returns the
    manifest and the days refreshed."""
    man = manifest()
    if not man:
        raise MonolithError("Ask for the upload plan first.", 409)
    want = {(int(r), str(d)) for r, d in keys or []}
    done = []
    for d in man["days"]:
        k = (int(d["rat"]), d["day"])
        if k not in want:
            continue
        entry = host.entry(d["gid"])
        tm, tb, ta = host.measured_transition(entry)
        if not (tm and abs(float(tb) - sweep.FAST_LEN[0]) < 1e-9
                and abs(float(ta) - sweep.FAST_LEN[1]) < 1e-9):
            continue
        bad = [int(c) for c in d.get("bad") or []]
        evs = {"p%02d" % i: ev for i, ev in
               enumerate(entry.get("events") or [], start=1)}
        for u in d["units"]:
            ev = evs.get(u["id"])
            if ev is not None:
                u["drop"] = circuitrun.plain(host.drop(ev, bad))
        d["fast_banked"] = True
        d["bank"] = {"entry": entry.get("id"), "version": entry.get("version")}
        for inp in man.get("inputs") or []:
            if inp.get("entry") == entry.get("id"):
                inp["version"] = entry.get("version")
        done.append("r%d %s" % k)
    if done:
        man["at"] = now_iso()
        man["digest"] = _digest(man)
        save_manifest(man)
    return man, done


def missing_additions(summary):
    """The additions the built Monolith lacks, as a run would plan them."""
    if not summary:
        return None
    bands = [b["id"] for b in summary.get("bands") or []]
    pacw = (summary.get("files") or {}).get("pac_raw.f32", {}).get(
        "shape", [0, 4])[1]
    out = {}
    if "delta" not in bands:
        out["bands"] = ["delta"]
    if pacw <= len(sweep.STATE):
        out["pac_trans"] = True
    if not (summary.get("additions") or {}).get("pair"):
        out["pair"] = True
    if summary.get("fast_missing"):
        out["fast"] = summary["fast_missing"]
    return out


def write_layer(path, got, shape):
    """The page's binary: QUANTITIES stacked, float32, C order."""
    stack = np.stack([np.asarray(got[q], dtype=np.float32).reshape(shape)
                      for q in QUANTITIES])
    tmp = path + ".part"
    stack.tofile(tmp)
    # On Windows a file the page is still being sent (or a memory map that
    # has not been let go) cannot be replaced for a moment; wait for it
    # rather than fail the whole build.
    for i in range(50):
        try:
            os.replace(tmp, path)
            break
        except PermissionError:
            if i == 49:
                raise
            time.sleep(0.2)
    return stack.nbytes


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def points(got, layer, names, pairs, n=TOP_N, per_pair=PER_PAIR,
           p_cut=P_POINT, w0=0):
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
        rec = _point(got, (w, b, m, pi), layer, names, pairs, w0=w0)
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


def _point(got, at, layer, names, pairs, w0=0):
    w, b, m, pi = (int(x) for x in at)
    a, bb = pairs[pi]
    est = float(got["est"][w, b, m, pi])
    wid = window_ids()[w + w0]
    return {"layer": layer, "w": wid, "wi": w + w0,
            "kind": window_kind(wid),
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


def pac_points(got, layer, names, n=20, w0=0):
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
        out.append({"layer": layer, "w": window_ids(pac=True)[w + w0],
                    "wi": w + w0, "cell": c,
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
    # One more window than measured: the contrast, Cue 2 - Cue 1.
    shapes = {"edges": (len(WINDOWS) + 1, len(sweep.BAND_IDS), len(METHODS),
                        len(pairs)),
              "power": (len(WINDOWS) + 1, len(sweep.BAND_IDS), len(names)),
              "pac": (len(PAC_WINDOWS) + 1, len(sweep.PAC_CELLS),
                      len(names) ** 2)}
    files, top, pac_top, cnt, rats_by = {}, {}, {}, {}, {}
    ctop, ccnt, cpac = {}, {}, {}
    shown = [label(n) for n in names]
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
                top[layer], cnt[layer], ct, cc = _tops(g, layer, shown,
                                                       pairs)
                if layer == "raw":
                    ctop[layer], ccnt[layer] = ct, cc
            elif what == "pac":
                pac_top[layer], _c, cp, _cc = _tops(g, layer, shown, pairs,
                                                    pac=True)
                if layer == "raw":
                    cpac[layer] = cp
    summary = {
        "schema": SCHEMA, "analysis": ANALYSIS, "name": NAME,
        "built_at": now_iso(), "rid": run["rid"],
        "rats": sorted({d["rat"] for d in man["days"]}),
        "rats_by_layer": rats_by,
        "days": DAY_NAMES, "layers": list(LAYERS), "layer_say": LAYER_SAY,
        "min_rats": MIN_RATS, "quantities": list(QUANTITIES),
        "why": {str(k): v for k, v in WHY.items()},
        "windows": [{"id": w, "label": WINDOW_SAY[w],
                     "kind": window_kind(w)} for w in window_ids()],
        "contrast": {"id": CONTRAST, "label": CONTRAST_SAY,
                     "say": "Within each presentation, Cue 2 minus Cue 1 -- "
                            "B - A in AB, D - C in CD -- then Precon4 "
                            "against Precon1. Raw only: the rest minus FP "
                            "takes away is the same for both cue windows, "
                            "so it cancels exactly.",
                     "top": ctop, "counts": ccnt, "pac_top": cpac},
        "lengths": {"state": "10 s", "slow": "−3 s / +3 s (bands ≤ 12 Hz, "
                    "theta)", "fast": "−1 s / +2 s (bands ≥ 13 Hz, beta, "
                    "low gamma)"},
        "bands": sweep.BANDS,
        "methods": [{"id": m, "label": METHOD_SAY[m][0],
                     "say": METHOD_SAY[m][1],
                     "directed": m in ("gc_ab", "gc_ba", "gc_net")}
                    for m in METHODS],
        "regions": shown, "region_keys": names,
        "pairs": [list(p) for p in pairs],
        "histology": {"version": histo.HISTO_VERSION,
                      "date": histo.HISTO_DATE, "rule": HISTO_RULE,
                      "say": HISTO_SAY,
                      "rats": {str(d["rat"]): sorted(label(x) for x in
                                                     d.get("blocked") or {})
                               for d in core_view(man)["days"]}},
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
        "fast_missing": fast_missing_of(asm, run),
        "refusals": asm["refusals"][:200],
        "manifest": {"digest": man.get("digest"), "at": man.get("at"),
                     "notes": man.get("notes") or []},
        "pac_windows": window_ids(pac=True),
        # Each rat's seats, from the lab's identity sheet, for the page's
        # labels and its physical cue sanity check.
        "identity": {"sheet": ratidentity.SHEET_FILE,
                     "seats": {str(r): ratidentity.identity(r)
                               for r in sorted({int(d["rat"])
                                                for d in man["days"]})
                               if ratidentity.known(r)},
                     "sound_say": ratidentity.SOUND_SAY},
        "additions": additions_of(sweep.BAND_IDS, PAC_WINDOWS, kinds={
            t["kind"] for t in list(run["tasks"]) + [
                t2 for p_ in run.get("parts") or [] for t2 in p_["tasks"]]}),
        "trajectory": trajectory_of(man, out_dir),
        "run": {"rid": run["rid"], "dest": run.get("dest"),
                "parts": [p_["rid"] for p_ in run.get("parts") or []],
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
def entry_detail(out_dir, man, summary, what, layer, at, group=None,
                 roles=None):
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
    # The contrast (Cue 2 - Cue 1): raw only, its wires those of Cue 2.
    contrast = at[0] == len(PAC_WINDOWS if what == "pac" else WINDOWS)
    wire_at = ((WINDOWS.index("cue2"),) + at[1:]) if contrast else at
    rows, per_rat = [], []
    for rat in summary["rats"]:
        per_day, gone = {}, None
        for day in DAY_NAMES:
            d = days.get((rat, day))
            X = _load_day(out_dir, rat, day, cue_name, mmap="r") if d else None
            if X is None or not X.shape[0]:
                gone = "%s: not computed" % day
                break
            vals = at_values(X, at, pac=(what == "pac"))
            units = [{"id": u["id"], "label": u["label"], "cue":
                      u["cue_label"], "v": _f(v),
                      "pair": ratidentity.pair_of(rat, u.get("cue_type")),
                      "seat_say": ratidentity.seat_say(rat, u.get("cue_type"))}
                     for u, v in zip(d["units"], vals)]
            # One split: only its cue pairs, by index into the day's.
            pick = list(range(len(units)))
            if group:
                kk = split_keep(group, roles or {})
                pick = [i for i, u in enumerate(d["units"]) if kk(d, u)]
            if what == "edges":
                wkey = wires_key(wire_at[0], at[1])
                Wt = _load_day(out_dir, rat, day, wkey, mmap="r")
                a, b = summary["pairs"][at[3]]
                wi = wires_index(wire_at[0])
                if Wt is not None:
                    for i, u in enumerate(units):
                        u["wires"] = [int(Wt[i, wi, a]), int(Wt[i, wi, b])]
                        if u["v"] is None:
                            u["why"] = unit_why(
                                summary, rat, day, u["id"],
                                [int(x) for x in Wt[i, wi]], names[a],
                                names[b], u["wires"])
            units = [units[i] for i in pick]
            if not units:
                gone = "%s: no cue pair of this kind" % day
                break
            m, s2, n = day_stats(vals[pick][:, None])
            slot = {"cue": _f(m[0]), "cue_se2": _f(s2[0]), "n": int(n[0]),
                    "of": len(units), "units": units}
            if layer == "minus_fp" and not contrast:
                pair_w = at[0] == (PAC_WINDOWS if what == "pac"
                                   else WINDOWS).index("pair")
                Xr = _load_day(out_dir, rat, day, rest_name +
                               ("_pair" if pair_w else ""), mmap="r")
                if Xr is None or not Xr.shape[0]:
                    gone = "%s: no %srest epochs" % (day, "20 s " if pair_w
                                                     else "")
                    break
                rv = np.asarray(Xr[(slice(None),) + rest_at],
                                dtype=np.float64)
                rm, rs2, rn = day_stats(rv[:, None])
                rest_list = (d.get("rest_pair") or []) if pair_w else d["rest"]
                slot.update(rest=_f(rm[0]), rest_se2=_f(rs2[0]),
                            n_rest=int(rn[0]), of_rest=len(rest_list),
                            rest_units=[{"id": u["id"], "label": u["label"],
                                         "run": u["run"], "v": _f(v)}
                                        for u, v in zip(rest_list, rv)])
                if what == "edges":
                    Wr = _load_day(out_dir, rat, day, "wires_rest" +
                                   ("_pair" if pair_w else ""), mmap="r")
                    a, b = summary["pairs"][at[3]]
                    for i, u in enumerate(slot["rest_units"]):
                        if Wr is not None and i < Wr.shape[0]:
                            u["wires"] = [int(Wr[i, 0, a]), int(Wr[i, 0, b])]
                            if u["v"] is None:
                                u["why"] = unit_why(
                                    summary, rat, day, u["id"],
                                    [int(x) for x in Wr[i, 0]], names[a],
                                    names[b], u["wires"])
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
        rec = {"rat": rat, "days": per_day,
               "seats": ratidentity.identity(rat)}
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
    fname = "%s_%s%s.f32" % (what, layer, "__" + group if group else "")
    path = os.path.join(out_dir, fname)
    fmap = ((summary.get("splits") or {}).get("files") or {}) if group \
        else summary["files"]
    if os.path.isfile(path) and fname in fmap:
        shape = fmap[fname]["shape"]
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
    ci = None
    if p is not None and t.get("se") and t.get("df"):
        from scipy.stats import t as _t
        half = float(_t.ppf(0.975, t["df"])) * t["se"]
        ci = [mp["mean"] - half, mp["mean"] + half]
    for rec in per_rat:
        if rec.get("v") is not None and rec["v"] >= 0:
            half = 1.959964 * math.sqrt(rec["v"])
            rec["ci"] = [rec["delta"] - half, rec["delta"] + half]
    # The sessions between, for the trajectory: each rat's value there,
    # worked out as the two days' are -- never in the change, never tested.
    tdays = [x for x in TRAJ_NAMES if x in ((summary.get("trajectory") or
                                            {}).get("days") or [])]
    for rec in per_rat:
        rec["traj"] = {}
        for day in tdays:
            d = days.get((rec["rat"], day))
            X = _load_day(out_dir, rec["rat"], day, cue_name, mmap="r") \
                if d else None
            if X is None or not X.shape[0]:
                continue
            vals = at_values(X, at, pac=(what == "pac"))
            pick = list(range(len(d["units"])))
            if group:
                kk = split_keep(group, roles or {})
                pick = [i for i, u in enumerate(d["units"]) if kk(d, u)]
            if not pick:
                continue
            m, s2, n = day_stats(vals[pick][:, None])
            slot = {"cue": _f(m[0]), "cue_se2": _f(s2[0]), "n": int(n[0]),
                    "of": len(pick), "units": [
                        {"id": d["units"][i]["id"], "label": d["units"][i]["label"],
                         "cue": d["units"][i]["cue_label"], "v": _f(vals[i]),
                         "pair": ratidentity.pair_of(
                             rec["rat"], d["units"][i].get("cue_type")),
                         "seat_say": ratidentity.seat_say(
                             rec["rat"], d["units"][i].get("cue_type"))}
                        for i in pick]}
            x, se2 = slot["cue"], slot["cue_se2"]
            if layer == "minus_fp" and not contrast:
                # The whole pair stands against its own 20 s rest.
                pair_w = at[0] == (PAC_WINDOWS if what == "pac"
                                   else WINDOWS).index("pair")
                Xr = _load_day(out_dir, rec["rat"], day, rest_name +
                               ("_pair" if pair_w else ""), mmap="r")
                if Xr is None or not Xr.shape[0]:
                    x = se2 = None
                else:
                    rv = np.asarray(Xr[(slice(None),) + rest_at],
                                    dtype=np.float64)
                    rm, rs2, rn = day_stats(rv[:, None])
                    slot.update(rest=_f(rm[0]), rest_se2=_f(rs2[0]),
                                n_rest=int(rn[0]))
                    x = None if x is None or slot["rest"] is None else \
                        x - slot["rest"]
                    se2 = None if se2 is None or slot["rest_se2"] is None \
                        else se2 + slot["rest_se2"]
            slot["x"], slot["se2"] = x, se2
            rec["traj"][day] = slot
    return {"what": what, "layer": layer, "at": list(at), "split": group,
            "contrast": contrast,
            "trajectory_days": tdays,
            "rats": per_rat, "pooled": {
                "est": mp.get("mean"), "se": t.get("se") if p is not None
                else None, "p": p, "df": t.get("df"), "k": mp["k"],
                "tau2": mp.get("tau2"), "ci": ci,
                "why": mp.get("why") or t.get("why")},
            "arrays": pooled_says, "agree": agree}



def pac_self(out_dir, man, summary, layer, w, cell=None, group=None,
             roles=None):
    """Within-region PAC, the conventional way: each region's own
    comodulogram -- phase and amplitude from its own wire -- for each
    session, as the mean over rats of each rat's mean over its
    presentations (minus FP: less the mean over its rest epochs). With, at
    one cell, every rat's two sessions, and a typical presentation of each
    session (the one nearest the session's median) to open. The change and
    its p are the pooled arrays' (pac_<layer>.f32), as everywhere else."""
    names = summary["regions"]
    R = len(names)
    C = len(summary["pac_cells"])
    diag = [r * R + r for r in range(R)]
    days = {(int(d["rat"]), d["day"]): d for d in man["days"]}
    keep = split_keep(group, roles or {}) if group else None
    per = {day: {} for day in DAY_NAMES}        # day -> rat -> (C, R)
    pres = {}                                   # (rat, day) -> (ids, (U, C, R))
    for rat in summary["rats"]:
        for day in DAY_NAMES:
            d = days.get((int(rat), day))
            X = _load_day(out_dir, int(rat), day, "pac", mmap="r") if d \
                else None
            contrast = w == len(PAC_WINDOWS)
            if X is None or not X.shape[0] or (w >= X.shape[1]
                                               and not contrast):
                continue
            pick = [i for i, u in enumerate(d["units"])
                    if keep is None or keep(d, u)]
            if not pick:
                continue
            V = at_values(X, (w,), pac=True)[pick][:, :, diag]
            m, _s2, n = day_stats(V)
            m = np.where(n > 0, m, np.nan)
            if layer == "minus_fp" and not contrast:
                Xr = _load_day(out_dir, int(rat), day, "pac_rest", mmap="r")
                if Xr is None or not Xr.shape[0]:
                    continue
                mr, _r2, nr = day_stats(
                    np.asarray(Xr[:, 0], dtype=np.float64)[:, :, diag])
                m = np.where(nr > 0, m - mr, np.nan)
            per[day][int(rat)] = m
            pres[(int(rat), day)] = ([d["units"][i]["id"] for i in pick], V)

    def over_rats(day):
        rats = sorted(per[day])
        if not rats:
            nan = np.full((C, R), np.nan)
            return nan, nan, np.zeros((C, R), int)
        A = np.stack([per[day][r] for r in rats])
        m, s2, n = day_stats(A)
        return m, np.sqrt(s2), n

    sessions = {}
    for day in DAY_NAMES:
        m, se, n = over_rats(day)
        sessions[day] = {"mean": [[_f(x) for x in m[:, r]] for r in range(R)],
                         "se": [[_f(x) for x in se[:, r]] for r in range(R)],
                         "n": [[int(x) for x in n[:, r]] for r in range(R)]}
    out = {"layer": layer, "window": w, "split": group, "regions": names,
           "days": list(DAY_NAMES), "sessions": sessions}
    if cell is None:
        return out
    c = int(cell)
    # Every rat at this cell, region by region, and each session's typical
    # presentation: the one nearest the median over every rat's
    # presentations (as measured -- rest is never taken off a presentation).
    rats = []
    for rat in summary["rats"]:
        row = {"rat": int(rat)}
        for day in DAY_NAMES:
            m = per[day].get(int(rat))
            row[day] = None if m is None else [_f(x) for x in m[c]]
        rats.append(row)
    examples, units = [], {}
    for r in range(R):
        ex = {}
        for day in DAY_NAMES:
            pool_ = []
            for rat in summary["rats"]:
                got = pres.get((int(rat), day))
                if not got:
                    continue
                ids, V = got
                for uid, v in zip(ids, V[:, c, r]):
                    if np.isfinite(v):
                        pool_.append((float(v), int(rat), uid))
            if not pool_:
                ex[day] = None
                continue
            med = float(np.median([v for v, _r, _u in pool_]))
            v, rat_, uid = min(pool_, key=lambda t: (abs(t[0] - med), t[1],
                                                       t[2]))
            ex[day] = {"rat": rat_, "unit": uid, "v": v, "median": med,
                       "n": len(pool_)}
            units.setdefault(str(rat_), {})
            for dd in DAY_NAMES:
                got = pres.get((rat_, dd))
                units[str(rat_)][dd] = list(got[0]) if got else []
        examples.append(ex)
    out.update(cell=c, rats=rats, examples=examples, units=units)
    return out

def trajectory_of(man, out_dir):
    """Which sessions between this build has, and in how many rats."""
    have = {}
    for d in man.get("days") or []:
        if d["day"] not in TRAJ_NAMES:
            continue
        X = _load_day(out_dir, int(d["rat"]), d["day"], "edges", mmap="r")
        if X is not None and X.shape[0] and np.isfinite(
                np.asarray(X[:, 1, 0, 0, :], dtype=np.float64)).any():
            have.setdefault(d["day"], []).append(int(d["rat"]))
    days = [x for x in TRAJ_NAMES if x in have]
    return {"days": days, "rats": {k: sorted(v) for k, v in have.items()},
            "order": [x for x in ALL_DAY_ORDER if x in DAY_NAMES or x in days],
            "in_manifest": sorted({d["day"] for d in man.get("days") or []
                                   if d["day"] in TRAJ_NAMES})}


def wires_key(w, b):
    """Which day file holds the wires a window was read on."""
    if w == PAIR_W:
        return "wires_pair"
    if w < 4:
        return "wires_state"
    return ("wires_slow" if sweep.BAND_BY_ID[sweep.BAND_IDS[b]]["speed"]
            == "slow" else "wires_fast")


def wires_index(w):
    """Where window `w` sits in its wires file."""
    return 0 if w == PAIR_W else w if w < 4 else w - 4


def unit_why(summary, rat, day, uid, row, name_a, name_b, wires):
    """Why one cue pair (or rest epoch) has no value for one region pair,
    in words, from the wires it was read on (-1: none usable)."""
    if row and all(x < 0 for x in row):
        said = None
        for r in summary.get("refusals") or []:
            if r.get("unit") == uid and str(r.get("task") or "").startswith(
                    "r%d_%s_" % (rat, day)):
                said = r.get("why")
                break
        return ("Not read in this window at all" + (": %s" % said if said
                                                     else " (every region's "
                                                     "wires were clipped or "
                                                     "bad there)") + ".")
    gone = [n for n, wv in ((name_a, wires[0]), (name_b, wires[1])) if wv < 0]
    if gone:
        return ("%s had no usable wire in this window: every wire it has "
                "was clipped there, marked bad, or the region is not placed "
                "in this rat." % " and ".join(gone))
    return ("Both regions were read, but this measure could not be formed "
            "here (a flat stretch, or too few pieces of the window for it).")


# ==========================================================================
# What was lost (the page's damage report)
# ==========================================================================
#: Why a region gave nothing in one window of one cue pair or rest epoch,
#: first reason that applies wins. "clipped" is the bank's exclusion for
#: that window (Spark's clipping check, and any hand edits made on top of
#: it); in the slow transitions, which the node measures itself, it is the
#: node's own clipping check.
DAMAGE_REASONS = ("histology", "bad", "clipped", "unread")
#: Why one wire was left out of one window, as the cue-pair view says it.
EXCLUDED_SAY = {
    "histology": "histology does not place this probe in %(region)s "
                 "(the Monolith keeps only probes scored “y”), so it is not "
                 "used; shown as recorded",
    "bad": "marked bad for the whole recording",
    "clipped": "left out of %(window)s: the clipping check found it at the "
               "rail there",
    "unread": "not read in %(window)s, for no reason on record",
}
DAMAGE_SAY = {
    "histology": "histology v%d did not score the probe “y” for this region "
                 "(it is elsewhere, or missed), or it is Right POR-SUB, "
                 "which the Monolith leaves out" % histo.HISTO_VERSION,
    "bad": "every wire it has is marked bad for the recording",
    "clipped": "every wire it has was clipped (or excluded in the bank) "
               "in that window",
    "unread": "it was not measured there (the cue pair or window was "
              "refused on the cluster, or nothing could be read)",
}
_DAMAGE_CACHE = {}


def histology_changes(rats):
    """{rat: [{region, v1, v2, monolith}]}: every cell histology v2 scored
    differently from v1, and whether the Monolith uses that probe now."""
    regions = probes.regions_for("dewey32",
                                 [{"number": n} for n in range(1, 33)])
    out = {}
    for rat in rats:
        rat = int(rat)
        old, new = histo.HISTO_RAW_V1.get(rat), histo.HISTO_RAW.get(rat)
        if not old or not new:
            continue
        blocked = histology_blocked(rat)
        rows = []
        for r in regions:
            col = histo.sheet_column(r.get("sheet_label") or r.get("region"))
            if not col or old.get(col) == new.get(col):
                continue
            rows.append({"region": label(r["region"]), "v1": old.get(col),
                         "v2": new.get(col),
                         "monolith": r["region"] not in blocked})
        out[str(rat)] = rows
    return out


def _relabel_damage(got):
    """The damage report in the Monolith's names (Left POR-SUB)."""
    got = dict(got)
    got["regions"] = [label(n) for n in got.get("regions") or []]
    for d in got.get("days") or []:
        for r in d.get("regions") or []:
            r["name"] = label(r["name"])
        d["histology"] = [label(x) for x in d.get("histology") or []]
    for k in ("state", "trans", "rest_regions", "pair"):
        for r in (got.get("whole") or {}).get(k) or []:
            r["name"] = label(r["name"])
    for e in (got.get("entries") or {}).values():
        for r in e.get("by_region") or []:
            r["name"] = label(r["name"])
    for p in got.get("pairs") or []:
        p["a"], p["b"] = label(p["a"]), label(p["b"])
    return got


def _drop_for(drop, wname):
    if drop is None:
        return None
    if isinstance(drop, dict):
        return drop.get(wname)
    return drop


def _lost_why(name, chans, blocked, bad, drop):
    """The reason one region has no wire in one window."""
    if name in blocked:
        return "histology"
    cs = set(chans.get(name) or [])
    if cs and cs <= bad:
        return "bad"
    if drop is not None and cs and cs <= (set(int(c) for c in drop) | bad):
        return "clipped"
    return "unread"


def _tally(names):
    return {n: dict({"of": 0, "kept": 0}, **{r: 0 for r in DAMAGE_REASONS})
            for n in names}


def damage(man, summary, out_dir):
    """What the Monolith lost, rat by rat and day by day, and in all.

    Read from what the node actually did -- the wire each region was read
    on in each window, -1 where none was usable -- with the reason worked
    out from the manifest: histology, bad wires, the bank's per-window
    exclusions. Cue pairs are counted kept (every region histology allows,
    in every state window), partly kept, or lost (fewer than two regions in
    every window, so no edge at all)."""
    names = summary.get("region_keys") or summary["regions"]
    # The sessions this build has: Precon1 and Precon4, and Precon2 and
    # Precon3 once they have been run and fetched. A session in what goes
    # but not run yet is not lost -- it is not here yet -- and counting it
    # made every one of its presentations read as lost.
    tdays = set((summary.get("trajectory") or {}).get("days") or [])
    pending = [x for x in ALL_DAY_ORDER if x not in DAY_NAMES and
               x not in tdays and any(d["day"] == x for d in man["days"])]
    man = dict(man, days=[d for d in man["days"]
                          if d["day"] in DAY_NAMES or d["day"] in tdays])
    chans = coupling.dewey_map()
    refused = {}
    for r in summary.get("refusals") or []:
        key = "_".join(str(r.get("task") or "").split("_")[:2])
        refused[key] = refused.get(key, 0) + 1
    notes = (summary.get("manifest") or {}).get("notes") or []
    days_out = []
    whole = {"cue": {"total": 0, "kept": 0, "partial": 0, "lost": 0},
             "seats": {x: {"total": 0, "kept": 0, "partial": 0, "lost": 0}
                       for x in ratidentity.SEATS},
             "rest": {"total": 0, "kept": 0, "lost": 0},
             "state": _tally(names), "trans": _tally(names),
             "rest_regions": _tally(names), "pair": _tally(names)}
    for d in man["days"]:
        rat, day = int(d["rat"]), d["day"]
        blocked = set(d.get("blocked") or {})
        bad = set(int(c) for c in d.get("bad") or [])
        units, rest = d.get("units") or [], d.get("rest") or []
        W = {k: _load_day(out_dir, rat, day, k) for k in
             ("wires_state", "wires_slow", "wires_fast", "wires_rest",
              "wires_pair")}
        st, tr, rr = _tally(names), _tally(names), _tally(names)
        # The whole pair: only where its tasks were run (the file exists
        # and some wire was read in it), clean in both cues.
        wp = W["wires_pair"]
        pair_on = wp is not None and bool((wp >= 0).any())
        pr = _tally(names)
        cue = {"total": len(units), "kept": 0, "partial": 0, "lost": 0}
        # Each cue as heard, by its seat: Cue 1 is A (in AB) or C (in CD),
        # Cue 2 is B or D -- kept, partly kept or lost in its own window.
        seats = {x: {"total": 0, "kept": 0, "partial": 0, "lost": 0}
                 for x in ratidentity.SEATS}
        allowed = [n for n in names if n not in blocked]
        for i, u in enumerate(units):
            ws = W["wires_state"]
            got_all, any_pair = True, False
            seat_pair = ratidentity.seats_of(rat, u.get("cue_type"))
            for wi, wname in enumerate(sweep.STATE):
                drop = _drop_for(u.get("drop"), wname)
                n_read = 0
                win_all = bool(allowed)
                for ri, name in enumerate(names):
                    st[name]["of"] += 1
                    ok = ws is not None and i < ws.shape[0] and ws[i, wi, ri] >= 0
                    if ok:
                        st[name]["kept"] += 1
                        n_read += 1
                    else:
                        st[name][_lost_why(name, chans, blocked, bad,
                                           drop)] += 1
                        if name not in blocked:
                            got_all = False
                            win_all = False
                if n_read >= 2:
                    any_pair = True
                if seat_pair and wname in ("cue1", "cue2"):
                    t = seats[seat_pair[0 if wname == "cue1" else 1]]
                    t["total"] += 1
                    t["kept" if win_all else "partial" if n_read >= 2
                      else "lost"] += 1
            if not allowed:
                got_all = False
            cue["kept" if got_all else "partial" if any_pair else "lost"] += 1
            if pair_on:
                d12 = [_drop_for(u.get("drop"), w) for w in ("cue1", "cue2")]
                dpair = None if all(x is None for x in d12) else \
                    sorted(set(d12[0] or []) | set(d12[1] or []))
                for ri, name in enumerate(names):
                    pr[name]["of"] += 1
                    if i < wp.shape[0] and wp[i, 0, ri] >= 0:
                        pr[name]["kept"] += 1
                    else:
                        pr[name][_lost_why(name, chans, blocked, bad,
                                           dpair)] += 1
            for wi, wname in enumerate(sweep.TRANSITION):
                for ri, name in enumerate(names):
                    # Slow and fast windows both: a region is kept in a
                    # transition window if either set read it there.
                    tr[name]["of"] += 1
                    hit = any(a is not None and i < a.shape[0] and a[i, wi, ri] >= 0
                              for a in (W["wires_slow"], W["wires_fast"]))
                    if hit:
                        tr[name]["kept"] += 1
                    else:
                        drop = _drop_for(u.get("drop"), wname)
                        why = _lost_why(name, chans, blocked, bad, drop)
                        if why == "unread" and drop is None:
                            why = "clipped"       # the node's own check
                        tr[name][why] += 1
        rest_t = {"total": len(rest), "kept": 0, "lost": 0}
        for i, u in enumerate(rest):
            wr = W["wires_rest"]
            drop = _drop_for(u.get("drop"), "rest")
            n_read = 0
            for ri, name in enumerate(names):
                rr[name]["of"] += 1
                if wr is not None and i < wr.shape[0] and wr[i, 0, ri] >= 0:
                    rr[name]["kept"] += 1
                    n_read += 1
                else:
                    rr[name][_lost_why(name, chans, blocked, bad, drop)] += 1
            rest_t["kept" if n_read >= 2 else "lost"] += 1
        label = "r%d %s" % (rat, day)
        days_out.append({
            "rat": rat, "day": day, "cue": cue, "rest": rest_t,
            "seats": seats,
            "histology": sorted(blocked), "bad": sorted(bad),
            "refused": refused.get("r%d_%s" % (rat, day), 0),
            "notes": [n[len(label) + 2:] if n.startswith(label + ":") else n
                      for n in notes if n.startswith(label + ":")],
            "regions": [{"name": n, "state": st[n], "trans": tr[n],
                         "rest": rr[n], "pair": pr[n] if pair_on else None}
                        for n in names]})
        for k in ("total", "kept", "partial", "lost"):
            whole["cue"][k] += cue[k]
            for x in ratidentity.SEATS:
                whole["seats"][x][k] += seats[x][k]
        for k in ("total", "kept", "lost"):
            whole["rest"][k] += rest_t[k]
        for key, tally in (("state", st), ("trans", tr), ("rest_regions", rr),
                           ("pair", pr)):
            for n in names:
                for k, v in tally[n].items():
                    whole[key][n][k] += v
    whole["state"] = [dict(name=n, **whole["state"][n]) for n in names]
    whole["trans"] = [dict(name=n, **whole["trans"][n]) for n in names]
    whole["pair"] = [dict(name=n, **whole["pair"][n]) for n in names]
    whole["rest_regions"] = [dict(name=n, **whole["rest_regions"][n])
                             for n in names]
    # Which comparisons survive: per region pair, the rats in which both
    # regions were read (in at least one cue-pair window) on BOTH days the
    # change is taken between, and the share of its entries tested.
    pairs = summary["pairs"]
    read = {}
    for d in man["days"]:
        W = _load_day(out_dir, int(d["rat"]), d["day"], "wires_state")
        read[(int(d["rat"]), d["day"])] = set() if W is None or not W.shape[0] \
            else {ri for ri in range(len(names)) if (W[:, :, ri] >= 0).any()}
    all_rats = sorted({int(d["rat"]) for d in man["days"]})
    pair_rows = []
    for pi, (a, b) in enumerate(pairs):
        rats = [r for r in all_rats if all(
            a in read.get((r, day), set()) and b in read.get((r, day), set())
            for day in DAY_NAMES)]
        pair_rows.append({"a": names[a], "b": names[b], "rats": rats,
                          "n": len(rats), "enough": len(rats) >= MIN_RATS})
    # What it cost the pooled result: entries not tested, and why.
    entries = {}
    for layer in LAYERS:
        fname = "edges_%s.f32" % layer
        info = (summary.get("files") or {}).get(fname)
        path = os.path.join(out_dir, fname)
        if not info or not os.path.isfile(path):
            continue
        A = np.memmap(path, dtype="<f4", mode="r", shape=tuple(info["shape"]))
        # The measured windows only: the contrast (the last, in a build
        # that has it) is worked out from two of them, not measured.
        nw = len(WINDOWS) if info["shape"][1] > len(WINDOWS) else None
        why = np.asarray(A[QUANTITIES.index("why")][:nw])
        p = np.asarray(A[QUANTITIES.index("p")][:nw])
        tested = np.isfinite(p)
        codes = {}
        for c in np.unique(why[~tested & np.isfinite(why)]).astype(int):
            codes[str(c)] = int(((why == c) & ~tested).sum())
        by_region = []
        for ri, n in enumerate(names):
            idx = [pi for pi, (a, b) in enumerate(pairs) if ri in (a, b)]
            sub = tested[..., idx]
            by_region.append({"name": n, "entries": int(sub.size),
                              "tested": int(sub.sum())})
        entries[layer] = {"entries": int(p.size), "tested": int(tested.sum()),
                          "untested": codes, "by_region": by_region,
                          "by_pair": [int(tested[..., pi].sum())
                                      for pi in range(len(pairs))],
                          "per_pair": int(tested[..., 0].size)}
        del A
    return {"ok": True, "rid": summary.get("rid"), "regions": names,
            "reasons": list(DAMAGE_REASONS), "reason_say": DAMAGE_SAY,
            "days": days_out, "whole": whole, "entries": entries,
            "pairs": pair_rows, "min_rats": MIN_RATS,
            "core_days": list(DAY_NAMES),
            # In what goes, not built yet: run and fetch them first.
            "pending_days": pending,
            "built_days": [x for x in ALL_DAY_ORDER
                           if x in DAY_NAMES or x in tdays],
            "pair_measured": bool((summary.get("additions") or {}).get("pair")),
            "why_say": summary.get("why") or {}}


def damage_now():
    """damage() for the built Monolith, kept until it is rebuilt."""
    d = data_dir()
    summ = summary_now()
    # The manifest as it is on disk: this describes a run already made, so
    # a manifest from before a change of file rule (which only decides what
    # an upload sends) still says which cue pairs and wires it had. Its
    # histology is the one in force, as the build's arrays are.
    man = _read_json(_path("manifest.json"))
    if not d or not summ or not man or man.get("schema") != SCHEMA:
        return None
    histology_now(man)
    key = (d, os.path.getmtime(os.path.join(d, "summary.json")), HISTO_RULE)
    got = _DAMAGE_CACHE.get(key)
    if got is None:
        _DAMAGE_CACHE.clear()
        got = _relabel_damage(damage(man, summ, d))
        got["histology"] = {"say": HISTO_SAY, "rule": HISTO_RULE,
                            "built": (summ.get("histology") or {}).get(
                                "rule"),
                            "changes": histology_changes(
                                sorted({int(d["rat"]) for d in man["days"]}))}
        got["seat_say"] = {str(r): ratidentity.identity(r)
                           for r in sorted({int(d["rat"]) for d in man["days"]})
                           if ratidentity.known(r)}
        _DAMAGE_CACHE[key] = got
    # The aliasing check is its own file and may arrive later.
    got = dict(got, aliasing=_read_json(_path("aliasing.json")))
    return got


# ==========================================================================
# One cue pair, all the way down to its traces (the page's cue-pair view)
# ==========================================================================
# Read from the cluster's copy, as asked (2026-10-02): Jarvis runs a few
# lines of the SAME backend on the login node -- coupling's own reader, the
# window cut to the sample and decimated exactly as the node did -- and
# brings back two traces as float32. Nothing is stored. A recording that is
# no longer there (Temp is purged) is said, not read from elsewhere.
LEAF_SPAN_PAD_S = 10.0
_LEAF_CACHE = {}
_LEAF_ORDER = []
_LEAF_MAX = 24
_PUSHED = {"sha": None}

_READ_PY = r"""
import base64, json, os, sys
sys.path.insert(0, ".")
args = json.loads(base64.b64decode("__ARGS__").decode("utf-8"))
out = {"windows": {}}
try:
    if not os.path.isdir(args["folder"]):
        out = {"gone": True, "folder": args["folder"]}
    else:
        import numpy as np
        from backend import coupling
        got = coupling._signals_for_windows(
            args["folder"], args["chan"], [tuple(w) for w in args["windows"]],
            {}, 1000.0)
        for name, w in got.items():
            regs = {}
            for k, r in w["regions"].items():
                sig = r.get("signal")
                regs[k] = {"why": r.get("why"), "channel": r.get("channel"),
                           "data": None if sig is None else base64.b64encode(
                               np.asarray(sig, dtype="<f4").tobytes()).decode(
                               "ascii")}
            out["windows"][name] = {"t0": w["t0"], "t1": w["t1"],
                                    "fs": w["fs"], "regions": regs}
        # The wires left out: measured again by Spark's own detector, so
        # the page can show where they hit the rail and how much.
        c = args.get("clip")
        if c and c.get("chans"):
            try:
                from backend import spark
                got2 = spark.clipping_windows(
                    args["folder"], [{"pair_id": 1, "windows": [
                        tuple(w) for w in c["windows"]]}], only=c["chans"])
                bp = got2.get("by_pair") or {}
                recs = bp.get(1) or bp.get("1") or {}
                out["clip"] = {str(k): {"windows": v.get("windows"),
                                        "detail": v.get("detail"),
                                        "spans": v.get("spans")}
                               for k, v in recs.items()}
                out["clip_why"] = got2.get("why")
            except Exception as exc:
                out["clip_error"] = "%s: %s" % (type(exc).__name__, exc)
except Exception as exc:
    out = {"error": "%s: %s" % (type(exc).__name__, exc)}
sys.stdout.write("JARVIS_JSON=" + json.dumps(out) + "\n")
"""


def read_remote(cfg, folder, chan, windows, ssh=None, clip=None):
    """{window name: {t0, t1, fs, regions: {key: {signal|None, why}}}} read
    on the login node from the cluster's copy; {"gone": ...} when the folder
    is not there."""
    import base64
    key = json.dumps([folder, chan, windows, clip], sort_keys=True)
    if key in _LEAF_CACHE:
        return _LEAF_CACHE[key]
    args = base64.b64encode(json.dumps({
        "folder": folder, "chan": chan, "windows": windows,
        "clip": clip}).encode("utf-8")).decode("ascii")
    script = "%s\ncd %s && python - <<'JARVIS_PY'\n%s\nJARVIS_PY\n" % (
        vacc.activate(cfg),
        vacc.q(vacc._remote_path(cfg.get("workspace") or ".", "code")),
        _READ_PY.replace("__ARGS__", args))
    raw = vacc._runner(cfg, ssh)("bash -s", stdin=script, timeout=180)
    line = next((x for x in (raw or "").splitlines()
                 if x.startswith("JARVIS_JSON=")), None)
    if line is None:
        raise MonolithError("The cluster did not answer with the traces: %s"
                            % (raw or "nothing")[-300:], 502)
    got = json.loads(line[len("JARVIS_JSON="):])
    if got.get("error"):
        raise MonolithError("Reading the traces on the cluster failed: %s"
                            % got["error"], 502)
    for w in (got.get("windows") or {}).values():
        for r in w["regions"].values():
            data = r.pop("data", None)
            r["signal"] = (None if data is None else np.frombuffer(
                base64.b64decode(data), dtype="<f4").astype(np.float64))
    _LEAF_CACHE[key] = got
    _LEAF_ORDER.append(key)
    while len(_LEAF_ORDER) > _LEAF_MAX:
        _LEAF_CACHE.pop(_LEAF_ORDER.pop(0), None)
    return got


def check_remote(chk, rat, day, role):
    """Where the last check found one folder whole on the cluster, or None:
    a run's own place (run.dest) need not be where every recording is --
    Precon2 and Precon3 went to Scratch while the first run was in Temp."""
    for x in (chk or {}).get("days") or []:
        if int(x.get("rat", -1)) == int(rat) and x.get("day") == day:
            for f in x.get("folders") or []:
                if f.get("role") == role and f.get("use") and f.get("remote"):
                    return f["remote"]
    return None


def leaf(cfg, man, summary, out_dir, run, layer, at, rat, day, unit_id,
         cell=None, ssh=None, app_dir=None, chk=None):
    """One cue pair (or rest epoch) of one entry, down to its traces: the
    whole cue pair for context, the analysed window as the node had it, and
    every measure's own picture of it (sweep.explain), with the stored
    number beside the one recomputed here."""
    wi, bi, mi, pi = (int(x) for x in at)
    # The contrast (Cue 2 - Cue 1) is shown on its Cue 2 window.
    contrast = wi == len(WINDOWS)
    if contrast:
        wi = WINDOWS.index("cue2")
    days_ = {(d["rat"], d["day"]): d for d in man["days"]}
    d = days_.get((int(rat), day))
    if not d:
        raise MonolithError("r%s %s is not in this Monolith." % (rat, day),
                            404)
    rest = str(unit_id).startswith("e")
    units = d["rest"] if rest else d["units"]
    ui = next((i for i, u in enumerate(units) if u["id"] == unit_id), None)
    if ui is None:
        raise MonolithError("%s has no %s." % (d["label"], unit_id), 404)
    unit = units[ui]
    band_id = sweep.BAND_IDS[bi]
    band = sweep.BAND_BY_ID[band_id]
    if rest:
        kind, wj, wkey = "rest", 0, "wires_rest"
    elif wi == PAIR_W:
        kind, wj, wkey = "pair", 0, "wires_pair"
    elif wi < 4:
        kind, wj, wkey = "state", wi, "wires_state"
    else:
        kind = "trans_slow" if band["speed"] == "slow" else "trans_fast"
        wj, wkey = wi - 4, wires_key(wi, bi)
    wname, w0, w1 = sweep._windows_for(kind, unit)[wj]
    ra, rb = summary["pairs"][pi]
    keys = summary.get("region_keys") or summary["regions"]
    names = [label(k) for k in keys]
    Wt = _load_day(out_dir, int(rat), day, wkey, mmap="r")
    ca = int(Wt[ui, wj, ra]) if Wt is not None else -1
    cb = int(Wt[ui, wj, rb]) if Wt is not None else -1
    pair = unit.get("pair") or {}
    if rest:
        span = [max(0.0, float(pair["t0"]) - LEAF_SPAN_PAD_S),
                float(pair["t1"]) + LEAF_SPAN_PAD_S]
        marks = [{"name": "rest epoch", "t0": float(pair["t0"]),
                  "t1": float(pair["t1"])}]
        folder = next((f for f in d["folders"] if f["gid"] == unit["fp_gid"]),
                      None)
    else:
        o, c, e = (float(pair[k]) for k in ("opener_t", "closer_t",
                                            "offset_t"))
        span = [o - LEAF_SPAN_PAD_S, e + LEAF_SPAN_PAD_S]
        marks = [{"name": n_, "t0": a_, "t1": b_} for n_, a_, b_ in
                 sweep._windows_for("state", unit)]
        folder = next((f for f in d["folders"] if f["role"] == "SPC"), None)
    remote = (check_remote(chk, rat, day, (folder or {}).get("role")) or
              ((folder or {}).get("remote") or {}).get(run.get("dest")))
    E = _load_day(out_dir, int(rat), day, "edges_rest" if rest else "edges",
                  mmap="r")
    stored = None
    if E is not None:
        stored = _f(E[ui, 0 if rest else wi, bi, mi, pi])
    pair_id = ratidentity.pair_of(rat, unit.get("cue_type"))
    out = {"ok": True, "rat": int(rat), "day": day, "unit": unit_id,
           "label": unit.get("label"), "cue": unit.get("cue_label"),
           "pair": pair_id,
           "pair_say": ratidentity.label(rat, unit.get("cue_type")),
           "run": unit.get("run"), "kind": kind, "rest": rest,
           "window": {"name": wname, "t0": w0, "t1": w1},
           "span": {"t0": span[0], "t1": span[1]}, "marks": marks,
           "regions": [names[ra], names[rb]], "wires": [ca, cb],
           "band": band, "method": METHODS[mi], "layer": layer,
           "stored": stored, "remote": remote,
           "units": [u["id"] for u in units],
           # The contrast is Cue 2 - Cue 1; this is its Cue 2 window.
           "contrast": contrast}
    if not remote:
        out.update(ok=False, gone=True, why="This Monolith's run did not "
                   "say where on the cluster the recording is.")
        return out
    if ca < 0 or cb < 0:
        out.update(measured=False, why=unit_why(
            summary, int(rat), day, unit_id,
            [int(x) for x in Wt[ui, wj]] if Wt is not None else [],
            names[ra], names[rb], [ca, cb]))
    if not _PUSHED.get("sha") and ssh is None and app_dir:
        try:
            _PUSHED["sha"] = vacc.push_code(cfg, app_dir).get("sha256")
        except Exception:                                # noqa: BLE001
            pass                        # the copy there reads as well
    # The wires each region has that were left out of this window, and
    # why: read and shown anyway, so a dashed line on the page can be
    # looked at rather than taken on trust. A spare that was fine but not
    # needed (the region was read on another wire) is not one of them.
    cmap = coupling.dewey_map()
    bad = set(int(c) for c in d.get("bad") or [])
    if kind == "pair":
        d1, d2 = (_drop_for(unit.get("drop"), w) for w in ("cue1", "cue2"))
        drop_w = None if d1 is None and d2 is None else \
            set(d1 or []) | set(d2 or [])
    else:
        drop_w = None if kind == "trans_slow" else _drop_for(
            unit.get("drop"), "rest" if rest else wname)
    drop_w = None if drop_w is None else set(int(c) for c in drop_w)
    excluded = []
    for side, rix, used in (("A", ra, ca), ("B", rb, cb)):
        key, name = keys[rix], names[rix]
        for ch in cmap.get(key) or []:
            ch = int(ch)
            if ch == used:
                continue
            if key in (d.get("blocked") or {}):
                why = "histology"
            elif ch in bad:
                why = "bad"
            elif drop_w is not None and ch in drop_w:
                why = "clipped"
            elif used >= 0:
                continue
            else:
                why = "clipped" if kind == "trans_slow" else "unread"
            excluded.append({"side": side, "region": name, "channel": ch,
                             "why": why, "say": EXCLUDED_SAY[why] % {
                                 "region": name, "window": wname}})
    out["excluded"] = excluded
    chan = {"A": [ca] if ca >= 0 else [], "B": [cb] if cb >= 0 else []}
    for x in excluded:
        chan["x%d" % x["channel"]] = [x["channel"]]
    if ca < 0 and cb < 0 and not excluded:
        return out
    clip = ({"chans": [x["channel"] for x in excluded],
             "windows": [[wname, w0, w1], ["span", span[0], span[1]]]}
            if excluded else None)
    got = read_remote(cfg, remote, chan, [["span", span[0], span[1]],
                                          [wname, w0, w1]], ssh=ssh,
                      clip=clip)
    if got.get("gone"):
        out.update(ok=False, gone=True, why=(
            "This recording is no longer on the VACC (%s): %s. Upload it "
            "again to see its traces." % (run.get("dest"), remote)))
        return out
    sp = got["windows"]["span"]
    win = got["windows"][wname]
    show = {}
    for key, r in sp["regions"].items():
        sig = r.get("signal")
        if sig is None:
            show[key] = None
            continue
        x = coupling.notch(sig, sp["fs"])[0]
        y, fs_d = coupling.decimate_to(x, sp["fs"], sweep.TRACE_FS)
        show[key] = sweep._rl(y)
    out["span"].update(fs=sweep.TRACE_FS, a=show.get("A"), b=show.get("B"))
    clips = got.get("clip") or {}
    for x in excluded:
        x["trace"] = show.get("x%d" % x["channel"])
        c = clips.get(str(x["channel"]))
        if c:
            det = (c.get("detail") or {}).get(wname) or {}
            x["clip"] = {"lost": bool(det.get("lost")),
                         "frac": det.get("frac"), "run_ms": det.get("run_ms"),
                         "spans": c.get("spans") or []}
    if got.get("clip_error"):
        out["clip_error"] = got["clip_error"]
    sa = win["regions"]["A"].get("signal")
    sb = win["regions"]["B"].get("signal")
    if sa is not None and sb is not None:
        ex = sweep.explain(sa, sb, band_id, cell=cell)
        out["explain"] = ex
        out["recomputed"] = ex["values"].get(METHODS[mi])
        out["matches"] = (stored is None and out["recomputed"] is None) or (
            stored is not None and out["recomputed"] is not None and
            abs(stored - out["recomputed"]) <= 1e-4 * max(1.0, abs(stored)))
    return out


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
             "Monolith", "split": "splitting the Monolith by cue pair",
             "events": "finding hippocampal events",
             "extend": "adding Precon2 and Precon3 to what goes",
             "rebuild": "rebuilding the Monolith under the histology",
             "sessions": "making Monolith Progress's session files",
             "physical": "comparing the physical cues with the balanced ones"}


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
    sp = room_of(remote, man, dest)
    fit = vacc.room(sp, send_b)
    return {"dest": dest, "rows": rows, "bytes": send_b, "files": send_n,
            "skipped": skip_n, "at": now_iso(),
            # Six streams measured at about 80 MB/s to the login node.
            "seconds": round(send_b / (80.0 * 1024 * 1024)) if send_b else 0,
            "space": sp, "room": fit}


def room_of(remote, man, dest):
    """The lab's room in `dest` (the far side's `space`), or unknown."""
    ask = getattr(remote, "space", None)
    if not ask:
        return {"why": "this far side cannot say"}
    root = ((man.get("roots") or {}).get(dest) or {}).get("root")
    if not root:
        for _d, f in folders_of(man):
            root = (f.get("remote") or {}).get(dest)
            if root:
                break
    return ask(root) if root else {"why": "no folder there"}


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
    if not plan["room"]["fits"]:
        # Said before a byte is sent, rather than found out file by file.
        raise MonolithError(plan["room"]["say"] + " Upload to the other "
                            "place, or free some space there first.", 409)
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
        except vaccupload.QuotaError as exc:
            # Out of room: every folder after this would be refused the
            # same way, so the upload stops here and says why.
            failed.append({"folder": "r%d %s %s" % (r["rat"], r["day"],
                                                    r["role"]),
                           "why": str(exc)[:300]})
            worker.note(failed=list(failed))
            save_state(upload=dict(get_state().get("upload") or {},
                                   status="out of room", ended=now_iso(),
                                   bytes_sent=done["b"], failed=failed))
            raise MonolithError(str(exc), 507)
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
        # Which run it is about: a poll from the run before is not this one's.
        out["poll"]["rid"] = run.get("rid")
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


def run_now(man, cfg, app_dir, ssh=None, extra=None):
    """Submit the run, or run again what did not finish -- or, with
    `extra`, a small run that ADDS to the Monolith already built (see
    plan_tasks); fetching it rebuilds the Monolith from both."""
    st = get_state()
    if extra:
        return run_addition(man, cfg, app_dir, st, extra, ssh=ssh)
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


def run_addition(man, cfg, app_dir, st, extra, ssh=None):
    run = st.get("run")
    built = st.get("built") or {}
    pl = st.get("poll") or {}
    if not run or built.get("rid") != run.get("rid"):
        raise MonolithError("Build the Monolith first: an addition is run "
                            "beside a Monolith that has been fetched.", 409)
    if pl.get("active"):
        raise MonolithError("A run is still going on the cluster.", 409)
    chk = st.get("check")
    if not chk:
        raise MonolithError("Check the VACC first: the recordings have to "
                            "be whole on the cluster still.", 409)
    # Bands, PAC at the transitions or the whole pair: on every day the
    # Monolith already has; the sessions between, if asked, whole.
    built = {t["day"] for t in run["tasks"]}
    kinds = {t["kind"] for t in run["tasks"]}
    for p_ in run.get("parts") or []:
        built |= {t["day"] for t in p_["tasks"]}
        kinds |= {t["kind"] for t in p_["tasks"]}
    extra = dict(extra, on_days=sorted(built - set(extra.get("days") or [])),
                 pair_built="pair" in kinds)
    tasks = plan_tasks(man, chk, extra=extra)
    if not tasks:
        raise MonolithError(
            "There is nothing to add: no Precon2 or Precon3 recording of a "
            "rat in the Monolith is whole on the cluster. Add them to what "
            "goes, upload, and check the VACC again." if extra.get("days")
            else "There is nothing to add: no rat has both days whole on "
            "the cluster.", 409)
    dest = (st.get("upload") or {}).get("dest") or run.get("dest") or \
        "scratch"
    new = submit(cfg, tasks, dest, app_dir, ssh=ssh)
    new["parts"] = list(run.get("parts") or []) + [
        {"rid": run["rid"], "tasks": run["tasks"]}]
    new["adds"] = extra
    new["ready_rats"] = chk.get("ready_rats")
    new["manifest"] = man.get("digest")
    save_state(run=new, poll=None, fetch=None)
    return new


def fetch_and_build(worker, man, cfg, artifacts, by=None, fetcher=None,
                    roles_reader=None):
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
    return _build_and_file(worker, man, run, raw, data, artifacts, by,
                           roles_reader)


def rebuild_work(worker, artifacts=None, by=None, roles_reader=None):
    """The built Monolith made again from the answers already here, under
    the histology in force: nothing is fetched or run. About two minutes."""
    st = get_state()
    run = st.get("run")
    built = st.get("built") or {}
    if not run or built.get("rid") != run.get("rid"):
        raise MonolithError("Fetch the run first: a rebuild remakes the "
                            "Monolith that has been fetched.", 409)
    man = manifest()
    if not man:
        raise MonolithError("There is no manifest.", 409)
    base = run_dir_local(run["rid"])
    raw = os.path.join(base, "raw")
    for rdir in [raw] + [os.path.join(run_dir_local(p_["rid"]), "raw")
                         for p_ in run.get("parts") or []]:
        if not os.path.isdir(rdir):
            raise MonolithError("The answers fetched before are not here "
                                "any more (%s); fetch again." % rdir, 409)
    return _build_and_file(worker, man, run, raw, os.path.join(base, "data"),
                           artifacts, by, roles_reader)


def _build_and_file(worker, man, run, raw, data, artifacts, by,
                    roles_reader):
    worker.note(phase="building", step=None)
    if os.path.isdir(data):
        shutil.rmtree(data, ignore_errors=True)
    summary = build(man, run, raw, data, progress=lambda what, i, of, w:
                    worker.note(phase="building", step=what, i=i, of=of,
                                item=w))
    worker.check()
    # Split by cue pair as well, so the page can show each half.
    try:
        worker.note(phase="splitting")
        roles, notes = (roles_reader or roles_of)(man)
        split_build(man, summary, data, roles, notes,
                    progress=lambda what, i, of, item: worker.note(
                        phase="splitting", i=i, of=of, item=item),
                    check=worker.check)
    except Stopped:
        raise
    except Exception as exc:                             # noqa: BLE001
        summary["splits_error"] = "%s: %s" % (type(exc).__name__, exc)
        _write_json(os.path.join(data, "summary.json"), summary)
        roles = None
    # Monolith Progress: every session's own values.
    try:
        worker.note(phase="sessions")
        session_build(man, summary, data, roles=roles,
                      progress=lambda what, i, of, item: worker.note(
                          phase="sessions", i=i, of=of, item=item),
                      check=worker.check)
    except Stopped:
        raise
    except Exception as exc:                             # noqa: BLE001
        summary["sessions_error"] = "%s: %s" % (type(exc).__name__, exc)
        _write_json(os.path.join(data, "summary.json"), summary)
    # Section 6: the physical cues against the balanced ones.
    if roles:
        try:
            worker.note(phase="physical")
            physical_build(man, summary, data, roles,
                           progress=lambda what, i, of, item: worker.note(
                               phase="physical", i=i, of=of, item=item),
                           check=worker.check)
        except Stopped:
            raise
        except Exception as exc:                         # noqa: BLE001
            summary["physical_error"] = "%s: %s" % (type(exc).__name__, exc)
            _write_json(os.path.join(data, "summary.json"), summary)
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
        # What a small run could still add to the built Monolith.
        "missing": missing_additions(summary_now()) if st.get("built")
        else None,
        "trajectory": trajectory_status(st, man, summary_now()
                                        if st.get("built") else None),
        "additions_say": ADDITIONS_SAY,
        # A Monolith built under an older histology than the one in force
        # is remade here, from the answers already fetched.
        "histology": {"now": HISTO_RULE, "say": HISTO_SAY,
                      "built": ((summary_now() or {}).get("histology") or {})
                      .get("rule") if st.get("built") else None},
    }
