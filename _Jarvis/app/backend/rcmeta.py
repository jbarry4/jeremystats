# -*- coding: utf-8 -*-
"""rcmeta.py -- Root Canal's Meta Workflow (2026-11-11).

THE QUESTION
============
The Ambiguous Dataset puts two boxes on the PTEN pool: the DS box, drawn
around every CTL Baseline event, and the P-spike box, drawn around the
hand-sorted P-spikes, each at a grace. An event inside both is purple --
ambiguous -- and on PTEN Baseline v2 at 5% that is 1,334 of 3,018 events.
The boxes live in the three numbers Root Canal measures per event
(amplitude, HF power, half-width), and HOW each is measured is a choice.
The user (2026-11-11): "find the set of parameters that lead to the minimum
amount of ambiguous spikes ... a single output of the best parameters. Two
instances, one for 5% and one at 10% grace."

THE KNOBS (the user's answers, 2026-11-11)
  filter  the band the waveform is filtered to before its amplitude and
          half-width are measured ("just filtering ... no cut-offs based on
          raw amp"): none, the DS filter, the LFP filter, or any corners.
  win     the amplitude peak window, +- ms around the stamp.
  cross   the half-width search, +- ms.
  band    the HF power band, both edges, anywhere the read allows ("it
          could be 1-2000 or 800-832, we don't know").
The HF windows are what each read took off the disk, so they stay as read.

THE GOAL: the fewest purple events. One guard, because the cheapest way to
fewer purple is fewer measured events: a setting that measures fewer than
95% as many complete events as today's -- on the target, on the CTL pool, or
on the hand-sorted sets -- does not count. Ties go to fewer events outside
both boxes.

THE SEARCH NARROWS DOWN ("whatever is most efficient"; "a narrow down
process instead of trying every combination"):
  1. each knob alone, from today's settings, on a coarse grid;
  2. the best few of each knob, every combination of them;
  3. each knob in turn, finer, around the best, until a round finds nothing
     with fewer purple.
Every number is the one Root Canal itself measures (rootcanal.measure and
rootcanal.hf_db, on the reads already on this machine), and every box the
one the Workflow tab draws (rcborder.box_for), so the best setting, put into
Root Canal, gives the purple count said here. Today's settings are scored
first, and must give the Ambiguous Dataset's own count.

THE WORK IS SPREAD over worker processes, each holding some of the reads for
the whole search: a filter, a window or a search is a re-filter of every
event (seconds per read), a band is a sum over spectra already on disk.

IT PICKS UP WHERE IT LEFT OFF (2026-11-11: "if it crashes out it can pick
up where it left off"). Every measurement is written to disk the moment it
is made, under a fingerprint of the reads and the settings it starts from.
The search is deterministic, so a run started again replays it off the disk
-- scoring a setting takes milliseconds, measuring one takes seconds --
and only measures what the run before never reached. The workers are not
even started until something has to be measured.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
import time

import numpy as np

from . import rcborder
from . import rootcanal

GUARD = 0.95                     # share of today's complete events a setting keeps
N_WORKERS = max(1, min(10, (os.cpu_count() or 4) - 2))

# The coarse grid (stage 1), one knob at a time from today's settings.
COARSE_WIN = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0)
COARSE_CROSS = (10.0, 20.0, 30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0)
COARSE_LO = (0.0, 1.0, 5.0, 10.0, 20.0)            # filter corners, Hz
COARSE_HI = (50.0, 100.0, 200.0, 400.0)
COARSE_EDGES = (0.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0,
                600.0, 700.0, 800.0, 900.0, 1000.0, 1200.0, 1400.0, 1600.0,
                1800.0, 2000.0)
TOP = {"band": 5, "filter": 3, "win": 3, "cross": 3}   # carried into stage 2
ROUNDS = 3                                              # stage 3 at most
BAND_STEP = 20.0                 # about one bin of the +-25 ms event spectrum
BAND_MAX = 2000.0                # where the read's anti-alias filter starts
# Corners given by hand keep the DS filter's order and its mains removal, so
# a corner is the only thing that differs from the filter the pools use.
CUSTOM_ORDER, CUSTOM_MAINS = 3, True


CACHE_VERSION = 1                # bump when a measurement would come out different

# THE STEPS, in order, as the page lists them. Stage 3 repeats in rounds.
PLAN = (("reads", "Open the reads"),
        ("today", "Today’s settings, measured again here"),
        ("band", "Stage 1 of 3 · the HF band alone"),
        ("filter", "Stage 1 of 3 · the amplitude filter alone"),
        ("win", "Stage 1 of 3 · the peak window alone"),
        ("cross", "Stage 1 of 3 · the half-width search alone"),
        ("together", "Stage 2 of 3 · the best few of each, together"),
        ("refine", "Stage 3 of 3 · finer around the best, round by round"),
        ("save", "Save the answer"))


class MetaError(Exception):
    """Something a person can fix, said in a sentence."""


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def filt_params(fkey):
    """Root Canal's settings for a filter key: ("none",), ("ds",), ("lfp",)
    or ("custom", lo_hz, hi_hz)."""
    if fkey[0] in ("none", "ds", "lfp"):
        return {"filt": fkey[0]}
    return {"filt": "custom", "lo_hz": float(fkey[1]), "hi_hz": float(fkey[2]),
            "order": CUSTOM_ORDER, "mains_out": CUSTOM_MAINS}


def filt_key(measure):
    """The filter key of a Root Canal measure (a pool's `measure`)."""
    f = str((measure or {}).get("filt") or rootcanal.DEFAULT_FILTER)
    if f in ("none", "ds", "lfp"):
        return (f,)
    return ("custom", float(measure.get("lo_hz")), float(measure.get("hi_hz")))


def filt_words(fkey):
    if fkey[0] == "none":
        return "no filter"
    if fkey[0] in ("ds", "lfp"):
        pre = rootcanal.FILTERS[fkey[0]]
        return "%s, %g–%g Hz" % (pre["label"], pre["lo_hz"], pre["hi_hz"])
    if not fkey[1]:
        return "lowpass at %g Hz" % fkey[2]
    return "%g–%g Hz" % (fkey[1], fkey[2])


def corners(fkey):
    """(lo, hi) of a filter key, for refining it; None for no filter."""
    if fkey[0] == "none":
        return None
    if fkey[0] in ("ds", "lfp"):
        pre = rootcanal.FILTERS[fkey[0]]
        return float(pre["lo_hz"]), float(pre["hi_hz"])
    return float(fkey[1]), float(fkey[2])


def amp_words(k):
    fkey, win, cross = k
    return "%s · peak ±%g ms · half-width search ±%g ms" % (filt_words(fkey), win, cross)


def band_words(b):
    return "HF %g–%g Hz" % (b[0], b[1])


def fingerprint(specs, base):
    """What the measurements kept on disk are measurements OF: every read's
    events (role, times) and the settings the knobs are changes from."""
    rows = []
    for sp in sorted(specs, key=lambda x: x["id"]):
        rows.append([sp["id"], sp["role"],
                     os.path.basename(sp.get("path") or "") or "inline",
                     [round(float(t), 4) for t in sp.get("times") or []]])
    blob = json.dumps({"v": CACHE_VERSION, "base": base, "reads": rows},
                      sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def theta_dict(th):
    """A setting as plain values, for the payload and the page."""
    fkey, win, cross, band = th
    return {"filter": list(fkey), "filter_words": filt_words(fkey),
            "win_ms": float(win), "cross_ms": float(cross),
            "band_lo": float(band[0]), "band_hi": float(band[1]),
            "params": dict(filt_params(fkey), win_ms=float(win),
                           cross_ms=float(cross), band_lo=float(band[0]),
                           band_hi=float(band[1]))}


def theta_words(th):
    fkey, win, cross, band = th
    return "%s · peak ±%g ms · half-width search ±%g ms · HF %g–%g Hz" % (
        filt_words(fkey), win, cross, band[0], band[1])


# --------------------------------------------------------------------------
# The workers: each holds some of the reads for the whole search
# --------------------------------------------------------------------------
def _worker(conn, specs, base):
    reads = {}
    try:
        for sp in specs:
            if sp.get("got") is not None:
                reads[sp["id"]] = sp["got"]
                continue
            got = rootcanal.load_read(sp["path"])
            sub = rootcanal.subset(got, sp["times"])
            if sub is None:
                raise MetaError("%s: its read does not hold every event the "
                                "pool asks for." % sp.get("label"))
            reads[sp["id"]] = sub
            del got
        conn.send(("ready", None))
    except Exception as exc:                             # noqa: BLE001
        conn.send(("error", "%s" % exc))
        return
    while True:
        try:
            cmd, arg = conn.recv()
        except EOFError:
            return
        if cmd == "stop":
            return
        out = {}
        try:
            if cmd == "amphw":
                for key, setting in arg:
                    try:
                        p = rootcanal.Params(**dict(base, **setting))
                    except Exception:                    # noqa: BLE001
                        p = None
                    for rid, g in reads.items():
                        if p is None:
                            out[(rid, key)] = None
                            continue
                        m = rootcanal.measure(g, p)
                        out[(rid, key)] = (np.asarray(m["amp"], float),
                                           np.asarray(m["hw"], float))
            elif cmd == "hf":
                for band in arg:
                    try:
                        p = rootcanal.Params(**dict(base, band_lo=band[0],
                                                    band_hi=band[1]))
                    except Exception:                    # noqa: BLE001
                        p = None
                    for rid, g in reads.items():
                        try:
                            best = rootcanal.hf_db(g, p)[1] if p else None
                        except Exception:                # noqa: BLE001
                            best = None             # too narrow for the bins
                        out[(rid, band)] = (None if best is None
                                            else np.asarray(best, float))
            conn.send(("ok", out))
        except Exception as exc:                         # noqa: BLE001
            conn.send(("error", "%s" % exc))


class Engine:
    """The three numbers of every event, per setting, kept once measured.

    `specs`: [{id, label, role, pos, path + times | got}] -- each read, the
    role its events play ("ctl", "p" or "tgt") and where they go in that
    role's list. `base`: the Root Canal settings every knob is a change
    from."""

    def __init__(self, specs, base, n_workers=None, say=None, cache_dir=None):
        self.say = say or (lambda **k: None)
        self.specs = specs
        self.base = base
        self.n_workers = n_workers
        self.cache_dir = cache_dir
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        self.n = {}
        for sp in specs:
            self.n[sp["role"]] = max(self.n.get(sp["role"], 0),
                                     max(sp["pos"]) + 1 if sp["pos"] else 0)
        self.procs, self.conns = [], []
        self._amphw, self._hf = {}, {}
        self.passes = 0          # settings measured in this run
        self.kept = 0            # measurements found on disk from a run before
        self.started = False

    # -- kept on disk ----------------------------------------------------
    def _path(self, kind, key):
        h = hashlib.sha1(json.dumps(key, default=str).encode("utf-8")).hexdigest()[:20]
        return os.path.join(self.cache_dir, "%s_%s.npz" % (kind, h))

    def _load(self, kind, key):
        if not self.cache_dir:
            return None
        p = self._path(kind, key)
        if not os.path.isfile(p):
            return None
        try:
            with np.load(p) as z:
                got = {r: np.array(z[r]) for r in z.files}
            if set(got) != set(self.n):
                return None
            return got
        except Exception:                                # noqa: BLE001
            return None             # half-written by a crash: measure again

    def _save(self, kind, key, arrs):
        if not self.cache_dir:
            return
        p = self._path(kind, key)
        tmp = p[:-4] + ".part.npz"
        np.savez(tmp, **arrs)
        os.replace(tmp, p)

    def _start(self):
        """The workers, each opening its reads: only when something has to
        be measured, so a run replayed off the disk never waits for them."""
        if self.started:
            return
        import multiprocessing as mp
        specs = self.specs
        ctx = mp.get_context("spawn")
        k = max(1, min(self.n_workers or N_WORKERS, len(specs)))
        self.say(item="starting %d workers, each opening its share of the %d reads"
                 % (k, len(specs)))
        groups, load = [[] for _ in range(k)], [0] * k
        for sp in sorted(specs, key=lambda s: -len(s["pos"])):
            i = int(np.argmin(load))
            groups[i].append(sp)
            load[i] += len(sp["pos"])
        for g in groups:
            a, b = ctx.Pipe()
            pr = ctx.Process(target=_worker, args=(b, g, self.base), daemon=True)
            pr.start()
            self.procs.append(pr)
            self.conns.append(a)
        bad = []
        for c in self.conns:
            tag, msg = c.recv()
            if tag != "ready":
                bad.append(msg)
        if bad:
            self.close()
            raise MetaError("The reads could not be opened: %s" % "; ".join(bad))
        self.started = True

    def close(self):
        if not self.procs:
            return
        for c in self.conns:
            try:
                c.send(("stop", None))
            except Exception:                            # noqa: BLE001
                pass
        for p in self.procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()

    def _ask(self, cmd, arg):
        for c in self.conns:
            c.send((cmd, arg))
        out, bad = {}, []
        for c in self.conns:
            tag, got = c.recv()
            if tag != "ok":
                bad.append(got)
            else:
                out.update(got)
        if bad:
            raise MetaError("A worker failed: %s" % "; ".join(bad))
        return out

    def _scatter(self, got, key, width):
        out = {r: np.full((n, width), np.nan) for r, n in self.n.items()}
        for sp in self.specs:
            v = got.get((sp["id"], key))
            if v is None:
                continue
            cols = v if isinstance(v, tuple) else (v,)
            for j, col in enumerate(cols):
                out[sp["role"]][sp["pos"], j] = col
        return out

    def amphw(self, keys):
        """Amplitude and half-width at each (filter, win, cross): from the
        disk where a run before measured it, else measured, one setting at
        a time, and kept the moment it is."""
        want = list(dict.fromkeys(keys))
        todo = []
        for k in want:
            if k in self._amphw:
                continue
            got = self._load("a", k)
            if got is not None:
                self._amphw[k] = got
                self.kept += 1
            else:
                todo.append(k)
        n, done = len(want), len(want) - len(todo)
        if not todo:
            self.say(done=n, of=n, item="all %d kept from before" % n if n > 1
                     else None)
            return
        for k in todo:
            self._start()
            self.say(done=done, of=n, item="measuring " + amp_words(k))
            got = self._ask("amphw", [(k, dict(filt_params(k[0]), win_ms=k[1],
                                               cross_ms=k[2]))])
            self._amphw[k] = self._scatter(got, k, 2)
            self._save("a", k, self._amphw[k])
            self.passes += 1
            done += 1
        self.say(done=n, of=n, item=None)

    def hf(self, bands, chunk=20):
        want = list(dict.fromkeys(bands))
        todo = []
        for b in want:
            if b in self._hf:
                continue
            got = self._load("h", b)
            if got is not None:
                self._hf[b] = got
                self.kept += 1
            else:
                todo.append(b)
        n, done = len(want), len(want) - len(todo)
        if not todo:
            self.say(done=n, of=n, item="all %d kept from before" % n if n > 1
                     else None)
            return
        for i in range(0, len(todo), chunk):
            part = todo[i:i + chunk]
            self._start()
            self.say(done=done, of=n, item="measuring HF power in %d bands, %s to %s"
                     % (len(part), band_words(part[0]), band_words(part[-1])))
            got = self._ask("hf", part)
            for b in part:
                self._hf[b] = self._scatter(got, b, 1)
                self._save("h", b, self._hf[b])
            done += len(part)
        self.say(done=n, of=n, item=None)

    def features(self, th):
        """{role: [n x 3]} -- amplitude, HF power, half-width, rcborder's
        AXES order -- at a setting already measured."""
        fkey, win, cross, band = th
        ah, h = self._amphw[(fkey, win, cross)], self._hf[band]
        return {r: np.column_stack([ah[r][:, 0], h[r][:, 0], ah[r][:, 1]])
                for r in self.n}


# --------------------------------------------------------------------------
# The score of one setting
# --------------------------------------------------------------------------
def evaluate(F, grace, floor=None):
    """Purple and the rest at one setting's numbers. `floor`: the fewest
    complete events each role may have and still count (the guard)."""
    comp = {r: np.isfinite(F[r]).all(axis=1) for r in F}
    n = {r: int(comp[r].sum()) for r in F}
    out = {"measured": n, "ok": True, "why": None}
    if floor:
        short = [r for r in floor if n.get(r, 0) < floor[r]]
        if short:
            out.update(ok=False, why="measures fewer events than today's "
                       "settings (%s)" % ", ".join(
                           "%s %d of %d" % (ROLE_WORDS[r], n[r],
                                            int(np.ceil(floor[r] / GUARD)))
                           for r in short))
    if n["ctl"] < rcborder.MIN_EACH or n["p"] < rcborder.MIN_EACH:
        out.update(ok=False, why=out["why"] or "too few events to draw a box",
                   purple=None)
        return out
    lo_d, hi_d, _q, _pd = rcborder.box_for(F["ctl"][comp["ctl"]], float(grace))
    lo_p, hi_p, _q, _pp = rcborder.box_for(F["p"][comp["p"]], float(grace))
    X = F["tgt"]
    ind = rcborder._inside(X, lo_d, hi_d)
    inp = rcborder._inside(X, lo_p, hi_p)
    none = ~np.isfinite(X).any(axis=1)
    out.update(
        purple=int(np.sum(ind & inp)), ds=int(np.sum(ind & ~inp)),
        pspike=int(np.sum(inp & ~ind)),
        neither=int(np.sum(~ind & ~inp & ~none)), none=int(np.sum(none)),
        n=int(X.shape[0]),
        box_ds={"lo": [float(v) for v in lo_d], "hi": [float(v) for v in hi_d]},
        box_p={"lo": [float(v) for v in lo_p], "hi": [float(v) for v in hi_p]})
    return out


ROLE_WORDS = {"ctl": "the CTL pool", "p": "the hand-sorted P-spikes",
              "tgt": "the target"}


def _rank(r):
    """Fewest purple first; a setting the guard refuses after every one it
    allows; ties to fewer events outside both boxes."""
    if r.get("purple") is None:
        return (2, 0, 0)
    return (0 if r["ok"] else 1, r["purple"], r.get("neither") or 0)


# --------------------------------------------------------------------------
# The search
# --------------------------------------------------------------------------
def coarse_filters():
    out = [("none",), ("ds",), ("lfp",)]
    for lo, hi in itertools.product(COARSE_LO, COARSE_HI):
        if lo < hi / 2.0:
            out.append(("custom", lo, hi))
    return out


def coarse_bands():
    return [(a, b) for a, b in itertools.combinations(COARSE_EDGES, 2)]


def _near(v, steps, lo, hi):
    return sorted({round(min(hi, max(lo, v + s)), 3) for s in steps})


def search(E, grace, today, say=None):
    """The fewest purple at `grace`, starting from `today` (a setting).
    Returns {best, today, trail, evaluated, seconds}."""
    say = say or (lambda **k: None)
    t0 = time.time()
    seen = {}

    def run(ths, stage):
        """Score settings already measured; keep every score."""
        out = []
        for th in ths:
            if th not in seen:
                seen[th] = evaluate(E.features(th), grace, floor)
            out.append((th, seen[th]))
        out.sort(key=lambda x: _rank(x[1]))
        return out

    def measure(amp_keys=(), bands=()):
        E.amphw(list(amp_keys))
        E.hf(list(bands))

    fk0, w0, c0, b0 = today
    say(step="today", words="Today’s settings, measured again here: "
        + theta_words(today))
    measure([(fk0, w0, c0)], [b0])
    base = evaluate(E.features(today), grace)
    floor = {r: GUARD * base["measured"][r] for r in base["measured"]}
    seen[today] = evaluate(E.features(today), grace, floor)
    best = (today, seen[today])
    say(today=best[1]["purple"], best=best[1]["purple"])
    trail = [{"stage": "today", "words": "Today's settings",
              "setting": theta_dict(today), "purple": best[1]["purple"],
              "tried": 1}]

    def better(cands):
        nonlocal best
        if cands and _rank(cands[0][1]) < _rank(best[1]):
            best = cands[0]
            say(best=best[1]["purple"], best_words=theta_words(best[0]))
            return True
        return False

    def tops(ranked, k, pick):
        keep, seen_v = [], set()
        for th, r in ranked:
            if not r["ok"]:
                continue
            v = pick(th)
            if v not in seen_v:
                seen_v.add(v)
                keep.append(v)
            if len(keep) >= k:
                break
        return keep

    # 1. EACH KNOB ALONE, COARSE, from today's settings.
    bands = coarse_bands()
    say(step="band", words="Stage 1 of 3 · the HF band alone: %d bands from 0 to "
        "%g Hz, the rest as today" % (len(bands), BAND_MAX))
    measure(bands=bands)
    rb = run([(fk0, w0, c0, b) for b in bands], "coarse band")
    better(rb)
    filters = coarse_filters()
    if fk0 not in filters:
        filters.append(fk0)
    say(step="filter", words="Stage 1 of 3 · the amplitude filter alone: %d "
        "filters (none, DS, LFP and corners up to %g Hz)"
        % (len(filters), rootcanal.MAX_HI_HZ))
    measure([(f, w0, c0) for f in filters])
    rf = run([(f, w0, c0, b0) for f in filters], "coarse filter")
    better(rf)
    wins = sorted(set(COARSE_WIN) | {w0})
    say(step="win", words="Stage 1 of 3 · the peak window alone: %d windows, "
        "±%g to ±%g ms" % (len(wins), wins[0], wins[-1]))
    measure([(fk0, w, c0) for w in wins])
    rw = run([(fk0, w, c0, b0) for w in wins], "coarse window")
    better(rw)
    crosses = sorted(set(COARSE_CROSS) | {c0})
    say(step="cross", words="Stage 1 of 3 · the half-width search alone: %d "
        "searches, ±%g to ±%g ms" % (len(crosses), crosses[0], crosses[-1]))
    measure([(fk0, w0, c) for c in crosses])
    rc = run([(fk0, w0, c, b0) for c in crosses], "coarse search")
    better(rc)
    tried1 = len(bands) + len(filters) + len(wins) + len(crosses)
    trail.append({"stage": "coarse", "words": "Each knob alone, coarse",
                  "setting": theta_dict(best[0]), "purple": best[1]["purple"],
                  "tried": tried1})

    # 2. THE BEST FEW OF EACH, TOGETHER.
    tb = tops(rb, TOP["band"], lambda th: th[3])
    tf = tops(rf, TOP["filter"], lambda th: th[0])
    tw = tops(rw, TOP["win"], lambda th: th[1])
    tc = tops(rc, TOP["cross"], lambda th: th[2])
    tb = list(dict.fromkeys(tb + [b0]))
    tf = list(dict.fromkeys(tf + [fk0]))
    tw = list(dict.fromkeys(tw + [w0]))
    tc = list(dict.fromkeys(tc + [c0]))
    keys = [(f, w, c) for f in tf for w in tw for c in tc]
    say(step="together", words="Stage 2 of 3 · the best few of each, together: "
        "%d filters × %d windows × %d searches × %d bands = %d settings"
        % (len(tf), len(tw), len(tc), len(tb), len(keys) * len(tb)))
    measure(keys, tb)
    ranked = run([(f, w, c, b) for (f, w, c) in keys for b in tb], "together")
    better(ranked)
    trail.append({"stage": "together", "words": "The best few of each, together",
                  "setting": theta_dict(best[0]), "purple": best[1]["purple"],
                  "tried": len(keys) * len(tb)})

    # 3. EACH KNOB IN TURN, FINER, AROUND THE BEST, until a round finds
    # nothing with fewer purple.
    for rnd in range(ROUNDS):
        gained = False
        tried = 0
        fk, w, c, b = best[0]
        steps = [BAND_STEP * j for j in range(-5, 6)]
        los = _near(b[0], steps, 0.0, BAND_MAX - BAND_STEP)
        his = _near(b[1], steps, BAND_STEP, BAND_MAX)
        bs = [(a, z) for a in los for z in his if z - a >= 2 * BAND_STEP]
        say(step="refine", words="Stage 3 of 3 · round %d: the HF band's edges, "
            "%d bands %g Hz apart around %g–%g Hz"
            % (rnd + 1, len(bs), BAND_STEP, b[0], b[1]))
        measure([(fk, w, c)], bs)
        gained |= better(run([(fk, w, c, x) for x in bs], "fine band"))
        tried += len(bs)
        fk, w, c, b = best[0]
        cn = corners(fk)
        if cn:
            lo, hi = cn
            lo_c = sorted({v for v in (0.0, lo * 0.5, lo * 0.7, lo, lo * 1.4,
                                       lo * 2.0, lo - 1.0, lo + 1.0)
                           if 0.0 <= v < hi / 2.0})
            hi_c = sorted({v for v in (hi - 50.0, hi - 25.0, hi - 10.0, hi,
                                       hi + 10.0, hi + 25.0, hi + 50.0)
                           if lo * 2.0 < v <= rootcanal.MAX_HI_HZ})
            fs = [("custom", round(a, 3), round(z, 3)) for a in lo_c
                  for z in (hi,)] + [("custom", round(lo, 3), round(z, 3))
                                     for z in hi_c]
            fs = list(dict.fromkeys(fs))
            say(step="refine", words="Stage 3 of 3 · round %d: the filter's "
                "corners, %d filters around %s" % (rnd + 1, len(fs), filt_words(fk)))
            measure([(f, w, c) for f in fs])
            gained |= better(run([(f, w, c, b) for f in fs], "fine filter"))
            tried += len(fs)
        fk, w, c, b = best[0]
        ws = _near(w, (-8, -5, -3, -2, -1, 0, 1, 2, 3, 5, 8), 1.0, 100.0)
        say(step="refine", words="Stage 3 of 3 · round %d: the peak window, %d "
            "windows around ±%g ms" % (rnd + 1, len(ws), w))
        measure([(fk, x, c) for x in ws])
        gained |= better(run([(fk, x, c, b) for x in ws], "fine window"))
        tried += len(ws)
        fk, w, c, b = best[0]
        cs = _near(c, (-20, -10, -5, -2, 0, 2, 5, 10, 20), 10.0, 200.0)
        say(step="refine", words="Stage 3 of 3 · round %d: the half-width "
            "search, %d searches around ±%g ms" % (rnd + 1, len(cs), c))
        measure([(fk, w, x) for x in cs])
        gained |= better(run([(fk, w, x, b) for x in cs], "fine search"))
        tried += len(cs)
        trail.append({"stage": "refine", "round": rnd + 1,
                      "words": "Round %d, each knob finer" % (rnd + 1),
                      "setting": theta_dict(best[0]),
                      "purple": best[1]["purple"], "tried": tried})
        if not gained:
            break

    # How close the next few came: is the best a lone point, or a plateau?
    near = [{"setting": theta_dict(th), "purple": r["purple"],
             "neither": r.get("neither")}
            for th, r in sorted(seen.items(), key=lambda x: _rank(x[1]))[:8]
            if r["ok"]]
    return {"grace": float(grace),
            "today": dict(theta_dict(today), score=seen[today]),
            "best": dict(theta_dict(best[0]), score=best[1],
                         words=theta_words(best[0])),
            "trail": trail, "near": near, "evaluated": len(seen),
            "eligible": sum(1 for r in seen.values() if r["ok"]),
            "guard": GUARD, "seconds": round(time.time() - t0, 1)}
