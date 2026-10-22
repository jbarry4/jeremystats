"""
joefigs.py -- the Monolith page's ninth tab: Joe's figures.

Publication figures, in Nature's format, for what tab 8 (backend/joe.py)
found (Shahriar, 2026-10-21). Broad first, then zooming in:

  * For each result that changed (a first-pass coherence comparison lit in
    Dickson's coherence): the connectome, a ring of the regions with an
    edge per pair, for Precon1, Precon4 and Precon4 - Precon1, each as the
    net increases, the net decreases and both. Every one of those nine
    graphs is set against its own permutation null: within each session,
    each trial's two windows are swapped at random (which flips the sign of
    that trial's change), 10,000 times, and the graph's statistic is taken
    again. Its rank in that null and its P are on the figure, starred when
    P < 0.05.
  * For each follow-up that changed (a pair, a family of measures): the
    pair on the ring, each rat's four values, each rat's change between
    the days with its t-test, and the same within-session null.
  * PAC is never drawn as a line: each rat's modulation index, and, where
    the recordings can be read, the gamma amplitude at each theta phase as
    rose plots and the comodulogram's change.

Every number comes from tab 8's own cached rat-days (GUI_logs/.cache/
monolith/joe/days), so the figures agree with tab 8 to the last digit;
only the phase-amplitude profiles read the recordings again, through the
same wires tab 8 chose. Matplotlib draws each figure as SVG and PDF
(vector, Arial, fonts embedded) and a 600 dpi PNG, at Nature's widths: 89
mm a column, 183 mm two.

    joefigs.build(progress)   -> the manifest (figs.json) and the files
"""
from __future__ import annotations

import itertools
import json
import math
import os
import time

import numpy as np

from . import joe

N_PERM = 10000
SEED = 20261021
MM = 1.0 / 25.4
WIDTH = {"single": 89.0, "one_half": 120.0, "double": 183.0}
#: Colours: the days in greyscale; an increase and a decrease as the
#: colour-blind-safe PuOr pair; nulls light grey.
C_P1, C_P4 = "#8C8C8C", "#1A1A1A"
C_UP, C_DOWN = "#E66101", "#5E3C99"
C_NULL = "#D4D4D4"
C_NODE = "#FFFFFF"
#: Each comparison's two windows, for the within-session swap (the two must
#: be the same length; the FP comparisons have no trial to swap within).
WINDOWS = {"m1": ("base20", "pair"), "m2": ("base10", "cue1"), "m3": ("base10", "cue2"),
           "m4": ("swa", "swb"), "m5": ("cue1", "cue2")}
#: The follow-ups, by family, as the face of tab 8 groups them.
FAMILIES = (("conduction", "Not volume conduction", ("pli", "icoh")),
            ("direction", "Direction", ("gc_ab", "gc_ba", "xlag")),
            ("amplitude", "Amplitudes together", ("xpeak",)),
            ("pac", "Phase–amplitude coupling", ("pac_ab", "pac_ba", "pac_aa", "pac_bb")))
YLABEL = {"pli": "PLI", "icoh": "Imaginary coherence", "gc_ab": "Granger causality", "gc_ba": "Granger causality",
          "xlag": "Amplitude cross-correlation lag (ms)", "xpeak": "Amplitude cross-correlation peak (r)",
          "pac_ab": "Modulation index", "pac_ba": "Modulation index", "pac_aa": "Modulation index", "pac_bb": "Modulation index",
          "coh": "Coherence"}
#: The phase-amplitude profiles: theta phase in 18 bins, and the
#: comodulogram's phase and amplitude frequencies (Hz).
PAC_BINS = joe.PAC_BINS
COMOD_PHASE = tuple(range(4, 13))            # 2 Hz wide
COMOD_AMP = tuple(range(30, 91, 10))         # 10 Hz wide


class FigError(Exception):
    def __init__(self, msg, status=409):
        super().__init__(msg)
        self.status = status


def figs_dir(*parts):
    return joe.joe_dir("figs", *parts)


# --------------------------------------------------------------------------
# The data: tab 8's own rat-days
# --------------------------------------------------------------------------
def load_days():
    """{(rat, day): (arrs, fp, meta)} from tab 8's cache."""
    d = joe.joe_dir("days")
    out = {}
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith(".npz"):
            arrs, fp, meta = joe.load_day(os.path.join(d, f))
            out[(int(meta["rat"]), meta["day"])] = (arrs, fp, meta)
    return out


def _wi(name):
    return joe.WINDOWS.index(name)


def session_pairs(arrs, mid, b, m):
    """One session's coherence for every pair: (base, cue), each (trials, P)."""
    wa, wb = WINDOWS[mid]
    return arrs["coh"][_wi(wa), :, b, m, :], arrs["coh"][_wi(wb), :, b, m, :]


def session_measure(arrs, mid, key, b, p, a, bb):
    """One session's follow-up measure for one pair: (base, cue), each (trials, 1)."""
    wa, wb = WINDOWS[mid]
    if key.startswith("pac_"):
        i, j = {"pac_ab": (a, bb), "pac_ba": (bb, a), "pac_aa": (a, a), "pac_bb": (bb, bb)}[key]
        x, y = arrs["pac"][_wi(wa), :, i, j], arrs["pac"][_wi(wb), :, i, j]
    else:
        x, y = arrs[key][_wi(wa), :, b, p], arrs[key][_wi(wb), :, b, p]
    return np.asarray(x, np.float64)[:, None], np.asarray(y, np.float64)[:, None]


def _means(base, cue, flips=None):
    """Each window's mean over the session's trials (NaN ignored), after
    swapping the two windows in the trials `flips` marks: (K,) or (N, K)."""
    with np.errstate(invalid="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore", RuntimeWarning)
        if flips is None:
            return np.nanmean(base, axis=0), np.nanmean(cue, axis=0)
        s = flips[:, :, None]
        b_ = np.where(s, cue[None], base[None])
        c_ = np.where(s, base[None], cue[None])
        return np.nanmean(b_, axis=1), np.nanmean(c_, axis=1)


def per_rat_changes(sessions, rats, flips=None):
    """{day: (rats, [N,] K) cue - base}, each session's own change."""
    out = {}
    for day in joe.TESTED:
        rows = []
        for r in rats:
            s = sessions.get((r, day))
            if s is None:
                rows.append(None)
                continue
            b_, c_ = _means(s[0], s[1], None if flips is None else flips[(r, day)])
            rows.append(c_ - b_)
        shape = next(x.shape for x in rows if x is not None)
        out[day] = np.stack([x if x is not None else np.full(shape, np.nan) for x in rows])
    return out


def make_flips(sessions, n=N_PERM, seed=SEED):
    """For each session, n random swaps of its trials' two windows: (n, T)."""
    rng = np.random.default_rng(seed)
    return {k: rng.random((n, v[0].shape[0])) < 0.5 for k, v in sorted(sessions.items())}


def _nanmean0(x):
    import warnings
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(x, axis=0)


def num(x, fmt="%.2f"):
    """A number the way Nature prints it: a true minus sign."""
    return (fmt % x).replace("-", "−")


def stars(p):
    return "" if p is None or p >= 0.05 else "***" if p < 0.001 else "**" if p < 0.01 else "*"


def p_say(p):
    """Nature's P: P = 0.030, P < 0.001."""
    if p is None or not np.isfinite(p):
        return "P = n/a"
    return "P < 0.001" if p < 0.001 else "P = %.3f" % p


def perm_p(obs, null, side):
    """A permutation P with its +1 (the observed is one of the shuffles):
    'up' asks for at least as large, 'down' at least as small, 'two' at
    least as far from zero."""
    null = np.asarray(null, np.float64)
    null = null[np.isfinite(null)]
    n = null.size
    if side == "up":
        k = np.sum(null >= obs)
    elif side == "down":
        k = np.sum(null <= obs)
    else:
        k = np.sum(np.abs(null) >= abs(obs))
    rank = int(np.sum(null < obs)) + 1
    return float((1 + k) / (n + 1)), rank, n + 1


def _hist(null, bins=40):
    null = np.asarray(null, np.float64)
    null = null[np.isfinite(null)]
    c, e = np.histogram(null, bins=bins)
    return {"counts": c.tolist(), "edges": e.tolist(), "mean": float(null.mean()), "sd": float(null.std())}


# --------------------------------------------------------------------------
# The connectome of a result that changed
# --------------------------------------------------------------------------
GRAPHS = (("pos", "Increases", "up"), ("neg", "Decreases", "down"), ("net", "Both", "two"))
ROWS = (("Precon1", "Precon1"), ("Precon4", "Precon4"), ("delta", "Precon4 − Precon1"))


#: Each connectome has two nulls (2026-10-22), shown one at a time with a
#: toggle on tab 9. The main one is the rats: tab 8's light is a mixed
#: model with the rat as the unit, so the ring is tested the same way --
#: every way of flipping the sign of each rat's change (2^8 = 256 for 8
#: rats, all of them). The other is the within-session shuffle, trial
#: noise inside each session; it answers a different question ("bigger
#: than trial-to-trial noise?") and is kept for comparison.
NULLS = (("rats", "Rats flipped", "every way of flipping the sign of each rat\u2019s change, the rat as the unit, as tab 8\u2019s light"),
         ("trials", "Trials swapped", "each session\u2019s trials with their two windows swapped at random, trial-to-trial noise inside each session"))
#: More rats than this and the sign patterns are sampled, not all listed.
RAT_EXACT_MAX = 14


def rat_signs(n_rats, n=N_PERM, seed=SEED):
    """Every sign pattern for n_rats rats, the real one (+1 everywhere)
    first: (2^n_rats, n_rats). Past RAT_EXACT_MAX rats, `n` random ones
    with the real one first."""
    if n_rats <= RAT_EXACT_MAX:
        return np.array(list(itertools.product((1.0, -1.0), repeat=n_rats)), np.float64), True
    rng = np.random.default_rng(seed)
    S = np.where(rng.random((n, n_rats)) < 0.5, -1.0, 1.0)
    S[0] = 1.0
    return S, False


def exact_p(obs, null, side):
    """A P from a null that lists every arrangement, the real one among
    them: the share at least as extreme (no +1, it is already counted)."""
    null = np.asarray(null, np.float64)
    null = null[np.isfinite(null)]
    eps = 1e-12 * max(1.0, abs(obs))
    if side == "up":
        k = np.sum(null >= obs - eps)
    elif side == "down":
        k = np.sum(null <= obs + eps)
    else:
        k = np.sum(np.abs(null) >= abs(obs) - eps)
    rank = int(np.sum(null < obs - eps)) + 1
    return float(k / null.size), rank, int(null.size)


def _graph_stat(kind, edges):
    with np.errstate(invalid="ignore"):
        if kind == "pos":
            return np.nansum(np.clip(edges, 0, None), axis=-1)
        if kind == "neg":
            return np.nansum(np.clip(edges, None, 0), axis=-1)
        return np.nansum(edges, axis=-1)


def connectome(R, days, res):
    """The nine graphs of one result, with their nulls."""
    mid = res["model"]
    b = [x for x, _l, _h in joe.BANDS].index(res["band"])
    m = joe.METHODS.index(res["method"])
    keep = [R["pairs"].index(u) for u in res["units"]]
    rats = sorted({r for r, d in days if d in joe.TESTED})
    sessions = {}
    for (r, d), (arrs, _fp, _meta) in days.items():
        if d in joe.TESTED:
            base, cue = session_pairs(arrs, mid, b, m)
            sessions[(r, d)] = (base[:, keep], cue[:, keep])
    obs = per_rat_changes(sessions, rats)
    flips = make_flips(sessions)
    null = per_rat_changes(sessions, rats, flips)
    e = {"Precon1": _nanmean0(obs["Precon1"]), "Precon4": _nanmean0(obs["Precon4"])}
    e["delta"] = e["Precon4"] - e["Precon1"]
    ne = {"Precon1": _nanmean0(null["Precon1"]), "Precon4": _nanmean0(null["Precon4"])}
    ne["delta"] = ne["Precon4"] - ne["Precon1"]
    # The rats' null: each rat's own change (rats x pairs) with its sign
    # flipped every way, then averaged over the rats as the edges are.
    per_rat = {"Precon1": obs["Precon1"], "Precon4": obs["Precon4"],
               "delta": obs["Precon4"] - obs["Precon1"]}
    S, exact = rat_signs(len(rats))
    nr = {row: _nanmean0(np.moveaxis(S[:, :, None] * X[None], 1, 0)) for row, X in per_rat.items()}
    graphs, graphs_t = [], []
    for row, row_say in ROWS:
        for kind, kind_say, side in GRAPHS:
            o = float(_graph_stat(kind, e[row]))
            base = {"row": row, "row_say": row_say, "kind": kind, "kind_say": kind_say, "side": side, "stat": o}
            nn = _graph_stat(kind, nr[row])
            # The real arrangement is the first pattern (every sign +1), and
            # its value is what is ranked: the same as `o` unless a rat has
            # a pair on one day only, where the change row's mean of the
            # rats' differences is not the difference of the days' means
            # (on the real data no rat does; they agree to 1e-17).
            o_r = float(nn[0])
            p, rank, n = exact_p(o_r, nn, side) if exact else perm_p(o_r, nn[1:], side)
            graphs.append(dict(base, stat=o_r, p=p, rank=rank, n=n, stars=stars(p), null=_hist(nn), null_kind="rats"))
            nn = _graph_stat(kind, ne[row])
            p, rank, n = perm_p(o, nn, side)
            graphs_t.append(dict(base, p=p, rank=rank, n=n, stars=stars(p), null=_hist(nn), null_kind="trials"))
    return {"model": mid, "band": res["band"], "method": res["method"], "pairs": [R["pairs"][i] for i in keep],
            "pair_index": keep, "edges": {k: [None if not np.isfinite(x) else float(x) for x in v] for k, v in e.items()},
            "graphs": graphs, "graphs_trials": graphs_t, "null": "rats", "rat_exact": bool(exact),
            "n_signs": int(S.shape[0]), "rats": rats, "n_perm": N_PERM}


# --------------------------------------------------------------------------
# The follow-ups that changed
# --------------------------------------------------------------------------
def follow_items(R):
    """Every (result, pair, family) with a follow-up at p < .05, its lit
    measures in the order tab 8 lists them."""
    out = []
    for res in R["results"]:
        f = res.get("follow")
        if not f or res["model"] not in WINDOWS:
            continue
        for pr in f["pairs"]:
            for fam, fam_say, keys in FAMILIES:
                lit = [k for k in keys if (pr["measures"].get(k) or {}).get("p") is not None and pr["measures"][k]["p"] < joe.ALPHA]
                if lit:
                    out.append({"model": res["model"], "band": res["band"], "method": res["method"], "pair": pr["pair"],
                                "a": pr["a"], "b": pr["b"], "bilateral": pr.get("bilateral"), "family": fam,
                                "family_say": fam_say, "keys": lit, "measures": {k: pr["measures"][k] for k in lit}})
    return out


def follow_null(R, days, item, key):
    """One follow-up's within-session null: the mean over rats of each rat's
    (Precon4 change) - (Precon1 change), each session's trials swapped."""
    mid = item["model"]
    b = [x for x, _l, _h in joe.BANDS].index(item["band"])
    p = R["pairs"].index(item["pair"])
    a, bb = joe.pairs_of(len(R["regions"]))[p]
    rats = sorted({r for r, d in days if d in joe.TESTED})
    sessions = {}
    for (r, d), (arrs, _fp, _meta) in days.items():
        if d in joe.TESTED:
            sessions[(r, d)] = session_measure(arrs, mid, key, b, p, a, bb)
    obs = per_rat_changes(sessions, rats)
    flips = make_flips(sessions, seed=SEED + 1 + p * 16 + joe.FOLLOW_KEYS.index(key))
    null = per_rat_changes(sessions, rats, flips)
    dl = obs["Precon4"][:, 0] - obs["Precon1"][:, 0]                  # per rat
    nd = null["Precon4"][:, :, 0] - null["Precon1"][:, :, 0]           # rats x N
    ok = np.isfinite(dl)
    o = float(np.mean(dl[ok]))
    nn = _nanmean0(nd[ok])
    pv, rank, n = perm_p(o, nn, "two")
    return {"obs": o, "p": pv, "rank": rank, "n": n, "stars": stars(pv), "null": _hist(nn), "n_rats": int(ok.sum())}


# --------------------------------------------------------------------------
# Phase-amplitude profiles, from the recordings (the one thing that is)
# --------------------------------------------------------------------------
def _pac_regions(item, key):
    """(phase region, amplitude region) names (short) of a PAC follow-up."""
    a, b = item["a"], item["b"]
    return {"pac_ab": (a, b), "pac_ba": (b, a), "pac_aa": (a, a), "pac_bb": (b, b)}[key]


def pac_profiles(R, days, inputs, items, progress=None):
    """For each PAC follow-up, per rat and day and window: the gamma
    amplitude at each theta phase (18 bins, normalised) and the
    comodulogram's modulation index, through the very wires tab 8 chose.
    Returns {item key: {...}} and the notes for what could not be read."""
    from . import coupling, sweep
    regions = R["regions"]                          # short names, in tab 8's order
    full = inputs["regions"]
    chan_map = {k: [int(c) for c in v] for k, v in inputs["channels"].items()}
    want = []
    for it in items:
        for key in it["keys"]:
            if key.startswith("pac_"):
                want.append((it, key))
    out, notes = {}, []
    if not want:
        return out, notes
    trials_of = {(int(d["rat"]), d["day"]): d for d in inputs["days"]}
    edges = np.linspace(-np.pi, np.pi, PAC_BINS + 1)
    for n_it, (it, key) in enumerate(want):
        ph_r, am_r = _pac_regions(it, key)
        ri, rj = regions.index(ph_r), regions.index(am_r)
        need = sorted({full[ri], full[rj]})
        wa, wb = WINDOWS[it["model"]]
        acc = {}
        for (rat, day), (arrs, _fp, meta) in sorted(days.items()):
            if day not in joe.TESTED:
                continue
            if progress:
                progress(n_it, len(want), "%s %s · r%d %s" % (it["pair"], key, rat, day))
            src = trials_of.get((rat, day))
            folder = next((p for role, p in (src or {}).get("folders") or [] if role == "SPC"), None)
            if not folder or not os.path.isdir(folder):
                notes.append("r%d %s: its recording is not here (%s)" % (rat, day, folder or "no folder"))
                continue
            for ti, t in enumerate(meta["trials"]):
                tr = next((x for x in src["trials"] if x["id"] == t["id"]), None)
                if tr is None:
                    continue
                # Only the windows where tab 8 had a wire in both regions: in
                # the others it measured nothing, and neither does this.
                wins = [w for w in joe.trial_windows(tr) if w[0] in (wa, wb)
                        and all(int(arrs["wires"][_wi(w[0]), ti, full.index(reg)]) >= 0 for reg in need)]
                if not wins:
                    continue
                excl = {}
                for wname, _t0, _t1 in wins:
                    wi = _wi(wname)
                    excl[wname] = sorted({c for reg in need for c in chan_map.get(reg) or []
                                          if c != int(arrs["wires"][wi, ti, full.index(reg)])})
                try:
                    got = coupling._signals_for_windows(folder, {k: chan_map[k] for k in need}, wins, excl, joe.FS)
                except Exception as exc:                     # noqa: BLE001
                    notes.append("r%d %s %s: %s" % (rat, day, t["id"], exc))
                    continue
                for wname, _t0, _t1 in wins:
                    w = got.get(wname) or {}
                    rp = (w.get("regions") or {}).get(full[ri]) or {}
                    ra = (w.get("regions") or {}).get(full[rj]) or {}
                    if not (rp.get("usable") and ra.get("usable")):
                        continue
                    x = coupling.notch(np.asarray(rp["signal"], np.float64), joe.FS)[0]
                    y = coupling.notch(np.asarray(ra["signal"], np.float64), joe.FS)[0]
                    n = min(x.size, y.size)
                    x, y = x[:n], y[:n]
                    th = np.angle(sweep.analytic(x, joe.FS, 5.0, 12.0, pad=True))
                    ga = np.abs(sweep.analytic(y, joe.FS, 30.0, 90.0, pad=True))
                    idx = np.clip(np.digitize(th, edges) - 1, 0, PAC_BINS - 1)
                    cnt = np.bincount(idx, minlength=PAC_BINS).astype(float)
                    prof = np.bincount(idx, weights=ga, minlength=PAC_BINS) / np.maximum(cnt, 1)
                    prof = prof / prof.sum()
                    com = np.full((len(COMOD_AMP), len(COMOD_PHASE)), np.nan)
                    phs = [np.angle(sweep.analytic(x, joe.FS, f - 1.0, f + 1.0, pad=True)) for f in COMOD_PHASE]
                    for ai, fa in enumerate(COMOD_AMP):
                        amp = np.abs(sweep.analytic(y, joe.FS, fa - 5.0, fa + 5.0, pad=True))
                        for pi_, ph in enumerate(phs):
                            com[ai, pi_] = _mi(ph, amp, edges)
                    # The trial's own MI, which is tab 8's number when the
                    # same wire was read: the check that it was.
                    acc.setdefault((rat, day, wname), []).append((prof, com, t["id"], _mi(th, ga, edges)))
        per = {}
        for (rat, day, wname), rows in acc.items():
            per.setdefault(str(rat), {}).setdefault(day, {})[wname] = {
                "profile": np.mean([r[0] for r in rows], axis=0).tolist(),
                "comod": np.nanmean([r[1] for r in rows], axis=0).tolist(), "n": len(rows),
                "mi": {r[2]: r[3] for r in rows}}
        if not per:
            continue                                  # nothing read: no profile, the figure says so
        out["%s|%s|%s|%s" % (it["model"], it["band"], it["pair"], key)] = {
            "phase_region": ph_r, "amp_region": am_r, "windows": [wa, wb], "per_rat": per,
            "phase_hz": list(COMOD_PHASE), "amp_hz": list(COMOD_AMP)}
    return out, notes


def pac_agrees(R, days, profiles):
    """Each trial's MI as read for the profiles against tab 8's own (its
    cached t_pac): the proof that the same wire of the same recording was
    read, wherever it was read. None when the profiles carry no MI."""
    regions = R["regions"]
    worst, n, only_tab, only_read = 0.0, 0, 0, 0
    for prof in profiles.values():
        ri, rj = regions.index(prof["phase_region"]), regions.index(prof["amp_region"])
        for (rat, day), (arrs, _fp, meta) in days.items():
            if day not in joe.TESTED:
                continue
            ids = [t["id"] for t in meta["trials"]]
            for wname in prof["windows"]:
                got = ((prof["per_rat"].get(str(rat)) or {}).get(day) or {}).get(wname)
                if got is not None and "mi" not in got:
                    return None
                got = (got or {}).get("mi") or {}
                tab = {ids[ti]: float(arrs["pac"][_wi(wname), ti, ri, rj]) for ti in range(len(ids))}
                tab = {k: v for k, v in tab.items() if np.isfinite(v)}
                only_tab += len(set(tab) - set(got))
                only_read += len(set(got) - set(tab))
                for k in set(tab) & set(got):
                    worst = max(worst, abs(tab[k] - float(got[k])))
                    n += 1
    # `matched`: every trial read is tab 8's own. `only_tab`: trials tab 8
    # measured that were not read (a copy that failed its size check, say:
    # the notes name it), so the roses average fewer of them.
    matched = n > 0 and worst < 1e-6 and not only_read
    return {"compared": n, "worst": worst, "only_tab": only_tab, "only_read": only_read,
            "matched": matched, "ok": matched and not only_tab}


def _mi(phase, amp, edges):
    idx = np.clip(np.digitize(phase, edges) - 1, 0, PAC_BINS - 1)
    cnt = np.bincount(idx, minlength=PAC_BINS).astype(float)
    m = np.bincount(idx, weights=amp, minlength=PAC_BINS) / np.maximum(cnt, 1)
    p = m / m.sum()
    h = -np.sum(np.where(p > 0, p * np.log(p), 0.0))
    return float((math.log(PAC_BINS) - h) / math.log(PAC_BINS))


# --------------------------------------------------------------------------
# The same profiles, read on the VACC
# --------------------------------------------------------------------------
# Every DEWEY recording was uploaded to the lab's scratch (`Jarvis Data/
# DEWEY/...`), and the Monolith's manifest names each folder's copy. So when
# E: is not plugged in the profiles are read THERE (Shahriar, 2026-10-22:
# "they are all on VACC"): the backend is shipped to a run folder of its
# own, `pac_profiles` runs as one slurm job on the cluster's copies, and only
# its numbers (kilobytes) come home, to joe/pac_vacc.json. Nothing is written
# beside a recording. Each copy's .ncs and .nev sizes are checked against the
# ones tab 8 read before a byte of it is used.
PAC_VACC = "pac_vacc.json"
PAC_ROW_H = 40.0             # mm: the roses and the comodulogram
PAC_VERSION = 2              # pac_profiles' arithmetic; a saved reading from another is not used


def _pac_want(items):
    return [(it, k) for it in items for k in it["keys"] if k.startswith("pac_")]


def pac_key(R, days, inputs, items):
    """What the profiles depend on, as one hash: the regions, the PAC
    follow-ups, and each tested rat-day's trials and chosen wires. Not the
    folders' paths, which differ between here and the cluster."""
    import hashlib
    want = sorted([it["model"], it["band"], it["pair"], it["a"], it["b"], k] for it, k in _pac_want(items))
    rd = []
    for (rat, day), (arrs, _fp, meta) in sorted(days.items()):
        if day in joe.TESTED:
            rd.append([rat, day, [t["id"] for t in meta["trials"]], np.asarray(arrs["wires"]).astype(int).tolist()])
    tr = sorted([[int(d["rat"]), d["day"], d["trials"]] for d in inputs["days"] if d["day"] in joe.TESTED],
                key=lambda x: (x[0], x[1]))
    blob = json.dumps([PAC_VERSION, R["regions"], inputs["regions"], inputs["channels"], want, rd, tr, PAC_BINS,
                       list(COMOD_PHASE), list(COMOD_AMP)], sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def pac_spec(R, days, inputs, items):
    """What the cluster needs: tab 8's regions, the PAC follow-ups, each
    tested rat-day's trials and chosen wires, and each recording's copy on
    the cluster with the sizes of its files as tab 8 read them."""
    from . import monolith as MO
    norm = lambda p: os.path.normcase(os.path.normpath(p))        # noqa: E731
    man = MO.manifest()
    if man is None:
        raise FigError("There is no Monolith manifest under the current rules: make it again (Drift, then Monolith).")
    remote, sizes = {}, {}
    for d in man.get("days") or []:
        for f in d.get("folders") or []:
            r = (f.get("remote") or {}).get("scratch")
            if f.get("local") and r:
                remote[norm(f["local"])] = r
                sizes[r] = {n: b for n, b in (f.get("files") or {}).items() if n.lower().endswith((".ncs", ".nev"))}
    want = _pac_want(items)
    light = {}
    for it, k in want:
        key = (it["model"], it["band"], it["pair"])
        light.setdefault(key, dict({x: it[x] for x in ("model", "band", "pair", "a", "b")}, keys=[]))["keys"].append(k)
    in_days, out_days, missing = [], [], []
    for d in sorted(inputs["days"], key=lambda d: (int(d["rat"]), d["day"])):
        rd = (int(d["rat"]), d["day"])
        if d["day"] not in joe.TESTED or rd not in days:
            continue
        spc = next((p for role, p in d.get("folders") or [] if role == "SPC"), None)
        r = remote.get(norm(spc)) if spc else None
        if not r:
            missing.append("r%d %s: the Monolith knows of no copy of it on the VACC (%s)" % (rd[0], rd[1], spc or "no folder"))
            continue
        in_days.append(dict(d, folders=[["SPC", r]]))
        arrs, _fp, meta = days[rd]
        out_days.append({"rat": rd[0], "day": rd[1], "wires": np.asarray(arrs["wires"]).astype(int).tolist(),
                         "trials": [{"id": t["id"]} for t in meta["trials"]]})
    return {"schema": 1, "key": pac_key(R, days, inputs, items), "regions": list(R["regions"]),
            "items": list(light.values()), "inputs": dict(inputs, days=in_days), "days": out_days,
            "sizes": {d["folders"][0][1]: sizes.get(d["folders"][0][1]) or {} for d in in_days}, "missing": missing}


def pac_remote(spec_path, out_path):
    """What the compute node runs: `python -m backend.joefigs pac SPEC OUT`.
    Checks each copy against the sizes tab 8 read, then `pac_profiles`, one
    process per PAC measure."""
    import platform
    import scipy
    from concurrent.futures import ProcessPoolExecutor, as_completed
    t0 = time.time()
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    notes, ok = list(spec.get("missing") or []), []
    for d in spec["inputs"]["days"]:
        folder = d["folders"][0][1]
        bad = []
        for name, size in sorted((spec["sizes"].get(folder) or {}).items()):
            p = os.path.join(folder, name)
            got = os.path.getsize(p) if os.path.isfile(p) else None
            if got != size:
                bad.append("%s is %s, not %d bytes" % (name, "missing" if got is None else "%d bytes" % got, size))
        if not spec["sizes"].get(folder):
            bad.append("the manifest has no file sizes to check it by")
        if bad:
            notes.append("r%d %s: the cluster's copy is not the recording tab 8 read (%s)" % (d["rat"], d["day"], "; ".join(bad[:3])))
        else:
            ok.append(d)
    good = {(int(d["rat"]), d["day"]) for d in ok}
    days = {(int(d["rat"]), d["day"]): ({"wires": np.asarray(d["wires"], np.int64)}, None, {"trials": d["trials"]})
            for d in spec["days"] if (int(d["rat"]), d["day"]) in good}
    inputs = dict(spec["inputs"], days=ok)
    R = {"regions": spec["regions"]}
    jobs = [(it, k) for it in spec["items"] for k in it["keys"]]
    n = max(1, min(len(jobs), int(os.environ.get("SLURM_CPUS_PER_TASK") or os.cpu_count() or 1)))
    profiles = {}
    print("%d PAC measures on %d rat-days, %d at a time" % (len(jobs), len(days), n), flush=True)
    with ProcessPoolExecutor(n) as ex:
        futs = {ex.submit(pac_profiles, R, days, inputs, [dict(it, keys=[k])]): (it, k) for it, k in jobs}
        for i, f in enumerate(as_completed(futs)):
            it, k = futs[f]
            got, nn = f.result()
            profiles.update(got)
            notes.extend(nn)
            print("%d/%d %s %s" % (i + 1, len(jobs), it["pair"], k), flush=True)
    out = {"schema": 1, "key": spec["key"], "profiles": profiles, "notes": list(dict.fromkeys(notes)),
           "rat_days": sorted("r%d %s" % rd for rd in good), "host": platform.node(),
           "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
           "seconds": round(time.time() - t0, 1)}
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    os.replace(tmp, out_path)
    print("done in %.0f s" % out["seconds"], flush=True)


def pac_saved():
    p = joe.joe_dir(PAC_VACC)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def pac_on_vacc(progress=None, check=None, R=None, days=None, inputs=None):
    """Read the PAC profiles from the cluster's copies, as one slurm job
    (joe.vacc_job), and keep them in joe/pac_vacc.json, where build()
    finds them."""
    say = progress or (lambda i, n, s: None)
    R = R if R is not None else joe.result()
    if not R:
        raise FigError("Work tab 8 out first: these figures are made from its numbers.")
    days = days if days is not None else load_days()
    if inputs is None:
        with open(joe.joe_dir("joe_inputs.json"), encoding="utf-8") as fh:
            inputs = json.load(fh)
    spec = pac_spec(R, days, inputs, follow_items(R))
    if not spec["items"]:
        raise FigError("No PAC follow-up changed, so there is nothing to read.")
    if not spec["inputs"]["days"]:
        raise FigError("The Monolith knows of no copy of these recordings on the VACC.")
    # Its own copy of the backend, not the shared `code` folder: a job
    # running from that one imports lazily, and swapping it underneath would
    # break it.
    from . import vacc
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = {}
    for rel in vacc._code_files(app_dir):
        if rel.startswith("backend"):
            with open(os.path.join(app_dir, rel), "rb") as fh:
                files["code/" + rel.replace(os.sep, "/")] = fh.read()
    files["spec.json"] = json.dumps(spec).encode("utf-8")
    cpus = max(1, min(8, sum(len(it["keys"]) for it in spec["items"])))
    try:
        cfg, ws, jid = joe.vacc_job(files, "cd code && exec python -m backend.joefigs pac ../spec.json ../result.json",
                                    cpus=cpus, progress=lambda s: say(1, 3, s), check=check, kind="joefigs")
        say(2, 3, "bringing the profiles home")
        out = json.loads(joe.vacc_text(cfg, ws, "result.json"))
    except joe.JoeError as exc:
        raise FigError(str(exc), exc.status)
    if out.get("key") != spec["key"]:
        raise FigError("The VACC answered for a different tab 8 than this one.")
    out.update({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": R.get("at"), "slurm_id": jid, "where": ws})
    joe._write(joe.joe_dir(PAC_VACC), out)
    try:
        vacc._ssh(cfg, "rm -rf %s/code" % vacc.q(ws), timeout=60)        # the spec, script, log and answer stay
    except Exception:                                    # noqa: BLE001
        pass
    return out


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    fam = next((f for f in ("Arial", "Helvetica", "Liberation Sans") if f in have), "DejaVu Sans")
    plt.rcParams.update({
        "font.family": fam, "font.size": 6, "axes.titlesize": 6.5, "axes.labelsize": 6,
        "xtick.labelsize": 5.5, "ytick.labelsize": 5.5, "legend.fontsize": 5.5,
        "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
        "xtick.major.size": 2.0, "ytick.major.size": 2.0, "xtick.major.pad": 1.5, "ytick.major.pad": 1.5,
        "lines.linewidth": 0.75, "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "axes.unicode_minus": True,
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    })
    return plt


def _ax(fig, x_mm, y_mm, w_mm, h_mm, H_mm, W_mm, **kw):
    """An axes placed in millimetres from the figure's top-left."""
    return fig.add_axes([x_mm / W_mm, 1 - (y_mm + h_mm) / H_mm, w_mm / W_mm, h_mm / H_mm], **kw)


def _letter(fig, x_mm, y_mm, s, H_mm, W_mm):
    fig.text(x_mm / W_mm, 1 - y_mm / H_mm, s, fontsize=8, fontweight="bold", va="top", ha="left")


def ring_pos(n):
    """The Monolith's ring: the first region at the top right, the right
    hemisphere down the right side, the left back up the left."""
    out = []
    for i in range(n):
        a = -math.pi / 2 + (i + 0.5) * (2 * math.pi / n)
        out.append((math.cos(a), -math.sin(a)))
    return out


def draw_ring(ax, regions, edges, vmax, present=None, focus=None, arrow=None, self_loop=None, labels=True, node_size=16):
    """A connectome: nodes on a ring, an edge per (i, j, value) curving
    toward the centre, its width the size of the value and its colour the
    sign. `focus` (i, j) draws one pair alone, `arrow` its direction,
    `self_loop` a region coupled with itself."""
    from matplotlib.patches import Circle, FancyArrowPatch, PathPatch
    from matplotlib.path import Path
    ax.set_xlim(-1.62, 1.62)
    ax.set_ylim(-1.62, 1.62)
    ax.set_aspect("equal")
    ax.axis("off")
    pos = ring_pos(len(regions))
    ax.add_patch(Circle((0, 0), 1.0, fill=False, lw=0.35, ec="#E3E3E3", zorder=0))
    for i, j, v in sorted(edges, key=lambda x: abs(x[2])):
        if v is None or not np.isfinite(v) or v == 0:
            continue
        (x0, y0), (x1, y1) = pos[i], pos[j]
        mx, my = (x0 + x1) / 2 * 0.35, (y0 + y1) / 2 * 0.35
        lw = 0.3 + 2.4 * min(1.0, abs(v) / vmax)
        col = C_UP if v > 0 else C_DOWN
        ax.add_patch(PathPatch(Path([(x0, y0), (mx, my), (x1, y1)], [Path.MOVETO, Path.CURVE3, Path.CURVE3]),
                               fill=False, lw=lw, ec=col, alpha=0.92, capstyle="round", zorder=1))
    if focus is not None:
        i, j = focus
        (x0, y0), (x1, y1) = pos[i], pos[j]
        if arrow is not None:
            s, t = (pos[i], pos[j]) if arrow == (i, j) else (pos[j], pos[i])
            ax.add_patch(FancyArrowPatch(s, t, connectionstyle="arc3,rad=-0.25", arrowstyle="-|>,head_length=3,head_width=1.8",
                                         lw=1.1, color="#1A1A1A", shrinkA=5, shrinkB=5, zorder=2))
        else:
            mx, my = (x0 + x1) / 2 * 0.35, (y0 + y1) / 2 * 0.35
            ax.add_patch(PathPatch(Path([(x0, y0), (mx, my), (x1, y1)], [Path.MOVETO, Path.CURVE3, Path.CURVE3]),
                                   fill=False, lw=1.1, ec="#1A1A1A", zorder=2))
    if self_loop is not None:
        x, y = pos[self_loop]
        ax.add_patch(Circle((x * 1.17, y * 1.17), 0.15, fill=False, lw=1.0, ec="#1A1A1A", zorder=2))
    for k, (x, y) in enumerate(pos):
        on = present is None or k in present
        hot = focus is not None and k in focus or self_loop == k
        ax.scatter([x], [y], s=node_size if not hot else node_size * 1.6, c=("#1A1A1A" if hot else C_NODE) if on else "#F2F2F2",
                   edgecolors="#1A1A1A" if on else "#BDBDBD", linewidths=0.5, zorder=3)
        if labels:
            lx, ly = x * 1.36, y * 1.30
            ax.text(lx, ly, regions[k], fontsize=5, ha="left" if x > 0.15 else "right" if x < -0.15 else "center",
                    va="center", color="#1A1A1A" if on else "#A6A6A6")


def draw_null(ax, hist, obs, p, rank, n, label=True, xlabel=None, what="shuffles"):
    c, e = np.array(hist["counts"]), np.array(hist["edges"])
    ax.bar(e[:-1], c, width=np.diff(e), align="edge", color=C_NULL, lw=0)
    ax.axvline(obs, color="#1A1A1A", lw=0.8)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    lo, hi = min(e[0], obs), max(e[-1], obs)
    pad = (hi - lo) * 0.05
    ax.set_xlim(lo - pad, hi + pad)
    ax.tick_params(axis="x", labelsize=5)
    ax.locator_params(axis="x", nbins=3)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=5, labelpad=1)
    if label:
        st = stars(p)
        ax.text(0.0, 1.30, "%s%s" % (p_say(p), (" " + st) if st else ""), transform=ax.transAxes, fontsize=5.5,
                fontweight="bold" if st else "normal", va="bottom", ha="left")
        ax.text(0.0, 1.04, "rank %s of %s %s" % (format(rank, ","), format(n, ","), what), transform=ax.transAxes, fontsize=5,
                va="bottom", ha="left", color="#4D4D4D")


def _save(fig, name):
    os.makedirs(figs_dir(), exist_ok=True)
    out = {}
    for ext in ("svg", "pdf", "png"):
        p = figs_dir("%s.%s" % (name, ext))
        fig.savefig(p, dpi=600 if ext == "png" else None)
        out[ext] = os.path.basename(p)
    return out


def connectome_figure(C, regions, title_no, null="rats"):
    """Nine rings (Precon1, Precon4, the change; increases, decreases, both)
    with a null under each: the rats' (the main figure) or the trials'
    (`<name>_trials`). Double column."""
    gs = C["graphs"] if null == "rats" else C["graphs_trials"]
    plt = _plt()
    W, H = WIDTH["double"], 206.0
    fig = plt.figure(figsize=(W * MM, H * MM))
    present = {regions.index(x) for pr in C["pairs"] for x in pr.split(" – ")}
    pairs = joe.pairs_of(len(regions))
    col_x = (14.0, 70.0, 126.0)
    row_y = (9.0, 71.0, 133.0)
    ring_w, ring_h, hist_h = 54.0, 42.0, 9.0
    vmax_day = max(1e-9, max(abs(x) for k in ("Precon1", "Precon4") for x in C["edges"][k] if x is not None))
    vmax_d = max(1e-9, max(abs(x) for x in C["edges"]["delta"] if x is not None))
    for ci, (kind, kind_say, _side) in enumerate(GRAPHS):
        fig.text((col_x[ci] + ring_w / 2) / W, 1 - 3.5 / H, {"pos": "Increases", "neg": "Decreases", "net": "Increases and decreases"}[kind],
                 ha="center", va="top", fontsize=6.5, fontweight="bold")
    letters = "abcdefghi"
    k = 0
    for ri, (row, row_say) in enumerate(ROWS):
        fig.text(4.0 / W, 1 - (row_y[ri] + ring_h / 2) / H, row_say, rotation=90, ha="center", va="center", fontsize=6.5, fontweight="bold")
        vals = C["edges"][row]
        vmax = vmax_d if row == "delta" else vmax_day
        for ci, (kind, _say, _side) in enumerate(GRAPHS):
            g = next(x for x in gs if x["row"] == row and x["kind"] == kind)
            ax = _ax(fig, col_x[ci], row_y[ri], ring_w, ring_h, H, W)
            ed = []
            for v, p in zip(vals, C["pair_index"]):
                if v is None:
                    continue
                if (kind == "pos" and v <= 0) or (kind == "neg" and v >= 0):
                    continue
                i, j = pairs[p]
                ed.append((i, j, v))
            draw_ring(ax, regions, ed, vmax, present=present)
            hx = _ax(fig, col_x[ci] + 9.0, row_y[ri] + ring_h + 6.0, ring_w - 18.0, hist_h, H, W)
            draw_null(hx, g["null"], g["stat"], g["p"], g["rank"], g["n"],
                      xlabel="Summed Δ coherence" if ri == 2 else None,
                      what="sign flips" if null == "rats" else "shuffles")
            _letter(fig, col_x[ci] - 2.0, row_y[ri], letters[k], H, W)
            k += 1
    # The key: edge widths and colours.
    kx = _ax(fig, 14.0, H - 7.0, 168.0, 6.0, H, W)
    kx.axis("off")
    kx.set_xlim(0, 168)
    kx.set_ylim(0, 6)
    for x0, v, say in ((0, vmax_day, "Δ coherence %.3f (Precon rows)" % vmax_day), (52, vmax_d, "%.3f (change row)" % vmax_d)):
        kx.plot([x0, x0 + 8], [3, 3], lw=0.3 + 2.4, color="#1A1A1A", solid_capstyle="round")
        kx.text(x0 + 10, 3, say, va="center", fontsize=5)
    kx.plot([96, 104], [3, 3], lw=1.5, color=C_UP, solid_capstyle="round")
    kx.text(106, 3, "increase", va="center", fontsize=5)
    kx.plot([124, 132], [3, 3], lw=1.5, color=C_DOWN, solid_capstyle="round")
    kx.text(134, 3, "decrease", va="center", fontsize=5)
    files = _save(fig, "fig_%s" % title_no if null == "rats" else "fig_%s_trials" % title_no)
    plt.close(fig)
    return files


def _sem(x):
    x = np.asarray(x, np.float64)
    x = x[np.isfinite(x)]
    return float(x.std(ddof=1) / math.sqrt(x.size)) if x.size > 1 else float("nan")


def _ci95(x):
    from scipy.stats import t as tdist
    x = np.asarray(x, np.float64)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return float("nan")
    return float(tdist.ppf(0.975, x.size - 1) * x.std(ddof=1) / math.sqrt(x.size))


def _measure_say(key, item):
    a, b = item["a"], item["b"]
    return {"pli": "PLI", "icoh": "Imaginary coherence", "gc_ab": "Granger %s → %s" % (a, b), "gc_ba": "Granger %s → %s" % (b, a),
            "xlag": "Amplitude lag", "xpeak": "Amplitude cross-correlation peak", "pac_ab": "PAC %s θ → %s γ" % (a, b),
            "pac_ba": "PAC %s θ → %s γ" % (b, a), "pac_aa": "PAC within %s" % a, "pac_bb": "PAC within %s" % b}[key]


def _sci(ax):
    """Small values (a modulation index of 0.0003) as 3 × 10^-4 on the axis."""
    from matplotlib.ticker import ScalarFormatter
    f = ScalarFormatter(useMathText=True)
    f.set_powerlimits((-2, 3))
    ax.yaxis.set_major_formatter(f)
    ax.yaxis.get_offset_text().set_fontsize(5)


def follow_figure(item, nulls, regions, levels, title_no, profile=None):
    """One follow-up that changed: the pair on the ring; each rat's four
    values; each rat's change between the days with its t-test; the
    within-session null. One row per lit measure; PAC adds the
    phase-amplitude roses and the comodulogram's change where read, and
    never draws its modulation index as lines."""
    plt = _plt()
    keys = item["keys"]
    pac_rows = [k for k in keys if k.startswith("pac_") and profile and profile.get(k)]
    W = WIDTH["double"]
    row_h = 44.0
    H = 4.0 + row_h * len(keys) + PAC_ROW_H * len(pac_rows) + 2.0
    fig = plt.figure(figsize=(W * MM, H * MM))
    ia, ib = regions.index(item["a"]), regions.index(item["b"])
    la, lb = levels
    letters = iter("abcdefghijklmnop")
    k0 = keys[0]
    arrow = loop = None
    if k0 in ("gc_ab", "pac_ab"):
        arrow = (ia, ib)
    elif k0 in ("gc_ba", "pac_ba"):
        arrow = (ib, ia)
    elif k0 == "pac_aa":
        loop = ia
    elif k0 == "pac_bb":
        loop = ib
    # a: the pair on the ring
    ax = _ax(fig, 3.0, 8.0, 40.0, 34.0, H, W)
    draw_ring(ax, regions, [], 1.0, focus=None if loop is not None else (ia, ib), arrow=arrow, self_loop=loop, node_size=10)
    _letter(fig, 1.0, 3.0, next(letters), H, W)
    y = 3.0
    for key in keys:
        ms = item["measures"][key]
        per = ms.get("per_rat") or {}
        rats = sorted(per, key=int)
        v = np.array([per[r][:4] for r in rats], np.float64)          # p1a p1b p4a p4b
        dl = np.array([per[r][4] for r in rats], np.float64)
        pac = key.startswith("pac_")
        # b: four conditions; each rat's two windows joined within a day
        # (PAC: dots only -- its modulation index is never drawn as lines)
        _letter(fig, 50.0, y, next(letters), H, W)
        fig.text(56.0 / W, 1 - (y + 0.4) / H, _measure_say(key, item), fontsize=6, fontweight="bold", va="top", ha="left")
        bx = _ax(fig, 62.0, y + 7.0, 46.0, row_h - 19.0, H, W)
        xs = (0.0, 1.0, 2.4, 3.4)
        if not pac:
            for r in range(v.shape[0]):
                bx.plot(xs[:2], v[r, :2], color=C_P1, lw=0.4, alpha=0.8, zorder=1)
                bx.plot(xs[2:], v[r, 2:], color=C_P4, lw=0.4, alpha=0.8, zorder=1)
        jit = np.linspace(-0.09, 0.09, max(1, v.shape[0])) if pac else np.zeros(v.shape[0])
        for c in range(4):
            col = C_P1 if c < 2 else C_P4
            bx.scatter(xs[c] + jit, v[:, c], s=5, c=col, edgecolors="white", linewidths=0.3, zorder=2)
            mu, se = np.nanmean(v[:, c]), _sem(v[:, c])
            bx.errorbar([xs[c] + 0.26], [mu], yerr=[se], fmt="_", color=col, ms=5, mew=1.0, elinewidth=0.8, capsize=0, zorder=3)
        bx.set_xticks(xs)
        bx.set_xticklabels([_short_level(la), _short_level(lb), _short_level(la), _short_level(lb)], fontsize=5)
        bx.set_xlim(-0.5, 3.9)
        bx.set_ylabel(YLABEL[key] if key != "xlag" else "Lag (ms); below 0, %s leads" % item["a"], fontsize=5.5, labelpad=1.5)
        _sci(bx)
        bx.text(0.5, -0.16, "Precon1", transform=bx.get_xaxis_transform(), ha="center", va="top", fontsize=5.5, color=C_P1, fontweight="bold")
        bx.text(2.9, -0.16, "Precon4", transform=bx.get_xaxis_transform(), ha="center", va="top", fontsize=5.5, color=C_P4, fontweight="bold")
        # c: each rat's change between the days, its mean and 95% CI
        _letter(fig, 116.0, y, next(letters), H, W)
        st = stars(ms.get("p"))
        fig.text(124.0 / W, 1 - (y + 0.4) / H, "t(%d) = %s, %s%s" % (ms.get("df") or 0, num(ms.get("t") or float("nan")), p_say(ms.get("p")),
                                                                       (" " + st) if st else ""),
                 fontsize=5.5, fontweight="bold" if st else "normal", va="top", ha="left")
        cx = _ax(fig, 130.0, y + 7.0, 16.0, row_h - 19.0, H, W)
        jit = np.linspace(-0.12, 0.12, max(1, dl.size))
        cx.scatter(jit, dl, s=6, c=C_P4, edgecolors="white", linewidths=0.3, zorder=2)
        mu, ci = float(np.nanmean(dl)), _ci95(dl)
        cx.errorbar([0.34], [mu], yerr=[ci], fmt="o", color="#1A1A1A", ms=2.5, elinewidth=0.8, capsize=0, zorder=3)
        cx.axhline(0, color="#7F7F7F", lw=0.5, ls=(0, (2, 2)), zorder=0)
        cx.set_xticks([])
        cx.set_xlim(-0.4, 0.6)
        cx.spines["bottom"].set_visible(False)
        cx.set_ylabel("Change, Precon4 − Precon1", fontsize=5.5, labelpad=1.5)
        _sci(cx)
        # d: the within-session null of the same change
        nl = nulls[key]
        _letter(fig, 152.0, y, next(letters), H, W)
        dx = _ax(fig, 156.0, y + 12.0, 25.0, row_h - 26.0, H, W)
        draw_null(dx, nl["null"], nl["obs"], nl["p"], nl["rank"], nl["n"], xlabel="Shuffled within sessions")
        y += row_h
    for key in pac_rows:
        y = _pac_panels(fig, plt, profile[key], levels, y, H, W, letters, item, key)
    files = _save(fig, "fig_%s" % title_no)
    plt.close(fig)
    return files


def _short_level(label):
    return {"Baseline (20 s)": "Base", "Baseline (10 s)": "Base", "Cue 1 + Cue 2 (20 s)": "Cues", "Cue 1": "Cue 1",
            "Cue 2": "Cue 2", "8–10 s": "8–10 s", "10–12 s": "10–12 s"}.get(label, label)


def _pac_panels(fig, plt, pf, levels, y, H, W, letters, item, key):
    """Rose plots of the gamma amplitude over the theta cycle (Precon1 and
    Precon4, each window, the mean over rats), and the comodulogram's
    change (Precon4 change − Precon1 change)."""
    wa, wb = pf["windows"]
    per = pf["per_rat"]
    centers = (np.arange(PAC_BINS) + 0.5) * (2 * np.pi / PAC_BINS) - np.pi
    width = 2 * np.pi / PAC_BINS
    conds = (("Precon1", wa), ("Precon1", wb), ("Precon4", wa), ("Precon4", wb))
    _letter(fig, 4.0, y, next(letters), H, W)
    mx = 0
    profs = []
    for day, w in conds:
        rows = [np.array(per[r][day][w]["profile"]) for r in per if day in per[r] and w in per[r][day]]
        prof = np.mean(rows, axis=0) if rows else np.full(PAC_BINS, np.nan)
        profs.append((day, w, prof, len(rows)))
        if rows:
            mx = max(mx, float(np.nanmax(prof - 1.0 / PAC_BINS)))
    for k, (day, w, prof, n) in enumerate(profs):
        ax = _ax(fig, 8.0 + k * 31.0, y + 8.0, 24.0, 24.0, H, W, projection="polar")     # below its title and the 90°
        dev = prof - 1.0 / PAC_BINS
        ax.bar(centers, np.abs(dev), width=width * 0.92, bottom=0.0,
               color=[C_UP if d > 0 else C_DOWN for d in dev], edgecolor="none", alpha=0.9)
        ax.set_ylim(0, mx * 1.05 if mx > 0 else 1)
        ax.set_yticks([])
        ax.set_xticks(np.deg2rad([0, 90, 180, 270]))
        ax.set_xticklabels(["0°", "90°", "180°", "270°"] if k == 0 else ["", "", "", ""], fontsize=4.5)
        ax.tick_params(pad=-1)
        ax.spines["polar"].set_linewidth(0.4)
        ax.grid(lw=0.3, color="#E0E0E0")
        fig.text((8.0 + k * 31.0 + 12.0) / W, 1 - (y + 1.0) / H,
                 "%s · %s" % (day, _short_level({"base20": "Baseline (20 s)", "base10": "Baseline (10 s)", "pair": "Cue 1 + Cue 2 (20 s)",
                                                 "cue1": "Cue 1", "cue2": "Cue 2", "swa": "8–10 s", "swb": "10–12 s"}[w])),
                 fontsize=5.5, ha="center", va="top", fontweight="bold", color=C_P1 if day == "Precon1" else C_P4)
    fig.text(8.0 / W, 1 - (y + 36.0) / H, "%s gamma amplitude at each %s theta phase: how far above (orange) or below (purple) its "
             "mean over the cycle; the mean over rats" % (pf["amp_region"], pf["phase_region"]), fontsize=5, va="top", ha="left", color="#4D4D4D")
    # the comodulogram's change
    _letter(fig, 132.0, y, next(letters), H, W)
    def comod(day, w):
        rows = [np.array(per[r][day][w]["comod"]) for r in per if day in per[r] and w in per[r][day]]
        return np.nanmean(rows, axis=0) if rows else None
    c1a, c1b, c4a, c4b = comod("Precon1", wa), comod("Precon1", wb), comod("Precon4", wa), comod("Precon4", wb)
    ax = _ax(fig, 140.0, y + 8.0, 28.0, 24.0, H, W)
    if all(x is not None for x in (c1a, c1b, c4a, c4b)):
        dlt = (c4b - c4a) - (c1b - c1a)
        lim = float(np.nanmax(np.abs(dlt))) or 1e-9
        im = ax.imshow(dlt, origin="lower", aspect="auto", cmap="PuOr_r", vmin=-lim, vmax=lim,
                       extent=[COMOD_PHASE[0] - 0.5, COMOD_PHASE[-1] + 0.5, COMOD_AMP[0] - 5, COMOD_AMP[-1] + 5])
        ax.set_xlabel("Phase frequency (Hz)", fontsize=5.5, labelpad=1)
        ax.set_ylabel("Amplitude frequency (Hz)", fontsize=5.5, labelpad=1)
        ax.set_xticks([4, 6, 8, 10, 12])
        cb = fig.colorbar(im, ax=ax, fraction=0.08, pad=0.03)
        from matplotlib.ticker import ScalarFormatter
        sf = ScalarFormatter(useMathText=True)
        sf.set_powerlimits((-2, 3))
        cb.ax.yaxis.set_major_formatter(sf)
        cb.ax.yaxis.get_offset_text().set_fontsize(4.5)
        cb.ax.tick_params(labelsize=4.5, width=0.4, length=1.5)
        cb.outline.set_linewidth(0.4)
        cb.set_label("Δ modulation index", fontsize=5)
        ax.set_title("Comodulogram: the change\nbetween the days", fontsize=5.5, pad=3, loc="left")
    return y + PAC_ROW_H


# --------------------------------------------------------------------------
# Legends, Nature's way
# --------------------------------------------------------------------------
def _model_title(R, mid):
    m = next(x for x in R["models"] if x["id"] == mid)
    return m.get("no"), m.get("title") or m["label"], m


def connectome_legend(R, C, null="rats"):
    no, title, m = _model_title(R, C["model"])
    la, lb = [lv["label"] for lv in m["levels"]]
    gs = C["graphs"] if null == "rats" else C["graphs_trials"]
    sig = [g for g in gs if g["p"] < 0.05]
    if null == "rats":
        n_s = format(C["n_signs"], ",")
        how = ("against every way of flipping the sign of each rat\u2019s change (%s sign patterns%s; the rat is the unit, "
               "as in the mixed model that lit tab 8\u2019s light), the vertical line the observed value, with its rank among "
               "them and its exact P (the share at least as extreme" % (n_s, "" if C.get("rat_exact") else ", sampled"))
        if C.get("rat_exact"):
            # Flipping every rat gives minus the observed, which is always as
            # extreme for "both": two of the patterns at least.
            how += ("; with %d rats P moves in steps of 1/%s, so the smallest possible is 1/%s for the increases or the "
                    "decreases and 2/%s for both" % (len(C["rats"]), n_s, n_s, n_s))
        how += "; increases one-sided upward, decreases downward, both two-sided"
    else:
        how = ("against %s shuffles in which each session\u2019s trials had their two windows swapped at random (the sign of "
               "that trial\u2019s change flipped: trial-to-trial noise inside each session), the vertical line the observed "
               "value, with its rank among the shuffles and its permutation P (increases one-sided upward, decreases "
               "downward, both two-sided" % format(C["n_perm"], ","))
    sig_say = "; ".join("%s, %s: %s" % (g["row_say"], g["kind_say"].lower(), p_say(g["p"])) for g in sig) or "none"
    return {
        "title": "%s, %s: the connectome of the change from %s to %s." % (title, joe.BAND_SAY[C["band"]].replace("Gamma", "gamma").replace("Theta", "theta"), la, lb),
        "body": ("a–c, Precon1; d–f, Precon4; g–i, Precon4 − Precon1. Each ring holds the %d regions (open, a region no pair "
                 "reaches with at least %d rats); each edge is one of the %d pairs tested, curving toward the centre, its width the "
                 "mean change in coherence from %s to %s over the rats (Dickson 2022: 59–61 Hz notch, hanning(1024), 512 overlap, "
                 "2,048 points, averaged over 30–90 Hz without 59–61 Hz), orange for an increase and purple for a decrease. Left "
                 "column, the increases; middle, the decreases; right, both. Under each ring, its statistic (the summed increases, "
                 "the summed decreases, or the sum of all) %s; *P < 0.05, **P < 0.01, ***P < 0.001; uncorrected). n = %d rats, "
                 "16 trials per session. Significant: %s.")
        % (len(R["regions"]), R.get("min_rats", 4), len(C["pairs"]), la, lb, how, len(C["rats"]), sig_say)}


def follow_legend(R, item, nulls, levels):
    no, title, _m = _model_title(R, item["model"])
    la, lb = levels
    parts = []
    for key in item["keys"]:
        ms = item["measures"][key]
        nl = nulls[key]
        parts.append("%s: t(%d) = %s, %s (one-sample t-test of each rat's change, uncorrected); within-session shuffles %s, rank %s of %s"
                     % (_measure_say(key, item), ms.get("df") or 0, num(ms.get("t") or float("nan")), p_say(ms.get("p")), p_say(nl["p"]),
                        format(nl["rank"], ","), format(nl["n"], ",")))
    return {
        "title": "%s, %s, %s: %s." % (title, item["band"], item["pair"], item["family_say"].lower()),
        "body": ("a, the pair on the ring of regions%s. Then, for each measure: its value for each rat at %s and %s on Precon1 "
                 "(grey) and Precon4 (black), each rat's two windows joined, the mean ± s.e.m. beside them; each rat's change "
                 "between the days, (Precon4 %s − %s) − (Precon1 %s − %s), with the mean ± 95%% confidence interval; and that "
                 "mean against %s shuffles in which each session's trials had their two windows swapped at random. "
                 "The pair was followed up because it moved most in its comparison, but it does not survive correction across "
                 "the pairs on its own: these are leads. %s.")
        % (" (the arrow, the direction measured)" if any(k in ("gc_ab", "gc_ba", "pac_ab", "pac_ba") for k in item["keys"]) else "",
           la, lb, lb, la, lb, la, format(N_PERM, ","), "; ".join(parts))}


# --------------------------------------------------------------------------
# The work
# --------------------------------------------------------------------------
def build(progress=None, check=None, read_recordings=True, R=None, days=None, inputs=None, prefer_vacc=False):
    """Every figure, its legend and its numbers, into figs_dir(). `R`,
    `days` and `inputs` default to tab 8's own (joe.json, its cached
    rat-days, joe_inputs.json); tools/check_joe.py hands in made-up ones."""
    import shutil
    R = R if R is not None else joe.result()
    if not R:
        raise FigError("Work tab 8 out first: these figures are made from its numbers.")
    days = days if days is not None else load_days()
    if not days:
        raise FigError("Tab 8's rat-days are not on this machine: work tab 8 out here first.")
    # Clear the last drawing. The folder itself may be held open (Windows
    # will not remove a folder something is sitting in), so its files go
    # one by one and the folder stays.
    shutil.rmtree(figs_dir(), ignore_errors=True)
    os.makedirs(figs_dir(), exist_ok=True)
    for f in os.listdir(figs_dir()):
        try:
            os.remove(figs_dir(f))
        except OSError:
            pass
    regions = R["regions"]
    models = {m["id"]: m for m in R["models"]}
    shown = R.get("shown") or "dickson"
    lit = [r for r in R["results"] if r["model"] in WINDOWS and r["method"] == shown and r.get("gate", {}).get("passed")]
    lit.sort(key=lambda r: (models[r["model"]].get("no") or 0, r["band"]))
    items = follow_items(R)
    ip = joe.joe_dir("joe_inputs.json")
    if inputs is None and os.path.isfile(ip):
        with open(ip, encoding="utf-8") as fh:
            inputs = json.load(fh)
    profiles, notes, where, vacc_run = {}, [], None, None
    if read_recordings and inputs:
        # Read here when every recording is here. If not, the VACC's
        # reading (pac_on_vacc), when it was made from this very tab 8; if
        # there is none, whatever here can read.
        here = all(os.path.isdir(p) for d in inputs["days"] if d["day"] in joe.TESTED
                   for role, p in d.get("folders") or [] if role == "SPC")
        saved = pac_saved() if (prefer_vacc or not here) else None
        if saved and saved.get("key") == pac_key(R, days, inputs, items):
            profiles, notes, where = saved.get("profiles") or {}, list(saved.get("notes") or []), "vacc"
            vacc_run = {k: saved.get(k) for k in ("at", "slurm_id", "where", "rat_days", "host", "python", "numpy", "scipy", "seconds")}
        else:
            profiles, notes = pac_profiles(R, days, inputs, items,
                                           progress=(lambda i, n, s: progress(i, n, "reading the recordings for PAC: " + s)) if progress else None)
            where = "here" if profiles else None
    figures = []
    for ri, res in enumerate(lit):
        if check:
            check()
        no = models[res["model"]].get("no")
        if progress:
            progress(ri, len(lit), "the connectome of %d, %s" % (no, res["band"]))
        C = connectome(R, days, res)
        fid = "%d" % (ri + 1)
        files = connectome_figure(C, regions, fid, "rats")
        files_t = connectome_figure(C, regions, fid, "trials")
        gkeys = ("row", "row_say", "kind", "kind_say", "side", "stat", "p", "rank", "n", "stars", "null", "null_kind")
        # The main figure is the rats' null (what lit tab 8's light); the
        # trials' is `alt`, a toggle away on tab 9.
        figures.append({"id": fid, "no": fid, "kind": "connectome", "model": res["model"], "band": res["band"],
                        "comparison": no, "files": files, "legend": connectome_legend(R, C, "rats"),
                        "null": "rats", "null_say": NULLS[0][1], "null_why": NULLS[0][2],
                        "stats": {"graphs": [{k: g[k] for k in gkeys} for g in C["graphs"]], "pairs": C["pairs"],
                                  "edges": C["edges"], "rats": C["rats"], "n_perm": C["n_perm"],
                                  "n_signs": C["n_signs"], "rat_exact": C["rat_exact"]},
                        "alt": {"null": "trials", "null_say": NULLS[1][1], "null_why": NULLS[1][2], "files": files_t,
                                "legend": connectome_legend(R, C, "trials"),
                                "stats": {"graphs": [{k: g[k] for k in gkeys} for g in C["graphs_trials"]],
                                          "n_perm": C["n_perm"]},
                                "methods": ["connectome", "permutation", "coherence"]},
                        "methods": ["connectome", "ratflip", "coherence"]})
        mine = [it for it in items if it["model"] == res["model"] and it["band"] == res["band"]]
        for si, it in enumerate(mine):
            if check:
                check()
            if progress:
                progress(si, len(mine), "%s · %s" % (it["pair"], it["family_say"]))
            levels = [lv["label"] for lv in models[it["model"]]["levels"]]
            nulls = {k: follow_null(R, days, it, k) for k in it["keys"]}
            prof = {}
            for k in it["keys"]:
                pk = "%s|%s|%s|%s" % (it["model"], it["band"], it["pair"], k)
                if pk in profiles:
                    prof[k] = profiles[pk]
            sid = "%s.%d" % (fid, si + 1)
            files = follow_figure(it, nulls, regions, levels, sid.replace(".", "_"), profile=prof)
            pac_missing = [k for k in it["keys"] if k.startswith("pac_") and k not in prof]
            figures.append({"id": sid, "no": sid, "kind": "follow", "family": it["family"], "model": it["model"],
                            "band": it["band"], "comparison": no, "pair": it["pair"], "a": it["a"], "b": it["b"],
                            "keys": it["keys"], "files": files, "legend": follow_legend(R, it, nulls, levels),
                            "pac_profiles": sorted(prof), "pac_missing": pac_missing,
                            "stats": {"measures": {k: {x: it["measures"][k].get(x) for x in ("delta", "t", "df", "p", "n")}
                                                   for k in it["keys"]},
                                      "nulls": nulls},
                            "methods": ["follow", "permutation"] + sorted({{"pli": "pli", "icoh": "icoh", "gc_ab": "granger",
                                                                           "gc_ba": "granger", "xlag": "xcorr", "xpeak": "xcorr"}
                                                                          .get(k, "pac") for k in it["keys"]})})
    out = {"schema": 1, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": R.get("at"), "n_perm": N_PERM, "seed": SEED,
           "regions": regions, "figures": figures, "notes": notes,
           "recordings_read": bool(profiles), "recordings_where": where, "vacc_run": vacc_run,
           "pac_check": pac_agrees(R, days, profiles) if profiles else None,
           "format": {"widths_mm": WIDTH, "font": "Arial", "sizes_pt": [5, 8]}}
    joe._write(figs_dir("figs.json"), out)
    return out


def result():
    p = figs_dir("figs.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def figs_work(worker, on_vacc=False):
    """The Monolith's work runner: every figure, here; with `on_vacc`, the
    PAC profiles read on the VACC first."""
    note = lambda i, n, s: worker.note(phase="joefigs", i=i, of=n, item=s)       # noqa: E731
    if on_vacc:
        pac_on_vacc(progress=lambda i, n, s: note(i, n, "PAC on the VACC: " + s), check=worker.check)
    return build(progress=note, check=worker.check, prefer_vacc=on_vacc)


def work_safe(worker, on_vacc=False):
    from . import monolith as MO, vacc
    try:
        out = figs_work(worker, on_vacc=on_vacc)
    except FigError as exc:
        raise MO.MonolithError(str(exc), exc.status)
    except vacc.SSHError as exc:
        raise MO.MonolithError("The VACC: %s" % exc, 502)
    return {"figures": len(out["figures"]), "recordings_read": out["recordings_read"],
            "recordings_where": out.get("recordings_where")}


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["pac"]:
        pac_remote(sys.argv[2], sys.argv[3])
