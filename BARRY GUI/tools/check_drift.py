# -*- coding: utf-8 -*-
"""Does Drift's arithmetic say what it claims to?

backend/drift.py pools each side of a comparison by DerSimonian-Laird
random-effects meta-analysis of RECORDINGS (cue pairs nested within them),
then tests the delta and corrects by Benjamini-Hochberg per panel. This
checks it three ways:

  1. REFERENCE. An independent re-derivation of DL tau^2, the weights, the
     pooled mean and SE -- plain Python loops, nothing imported from
     drift.py -- on small hand-made cases (including a recording that must
     borrow the pooled SD), asserted to 1e-12. Then the published BCG
     vaccine meta-analysis (13 trials, log risk ratios; the standard
     worked example of the R package metafor, `rma(..., method="DL")`):
     tau^2 = 0.3088, estimate = -0.7141, SE = 0.1787, Q = 152.23.
     statsmodels is not installed on this machine, so the published example
     is the external cross-check.
  2. BEHAVIOUR. Identical groups; a shifted copy; n = 1 vs n = 8 weighting;
     inflated n (every pair duplicated) with pair-pooled and nested p side by
     side; BH against a hand list; grey regions and absent cells; k = 1;
     nothing to borrow; refusals naming the field; strict JSON.
  3. NEGATIVE CONTROLS. `--break tau0` forces tau^2 = 0 (fixed effect);
     `--break pairs` pools pairs across recordings as if independent;
     `--break bh` reports q = p; `--break vid` pins by version number only
     (forgets version_id); `--break kindparams` compares every window
     parameter whatever the kind. Each must make the relevant checks FAIL.
     The breaks are monkeypatches in this process only -- drift.py on disk
     is never touched, so "restore" is simply running without --break.

  4. WITHIN RAT, HARTUNG-KNAPP, CONTRASTS, BH SCOPE (arc_contracts.md 7.4),
     each against an independent re-derivation in plain loops (nothing from
     drift.py; the t tail is the closed-form integer-df series of
     Abramowitz & Stegun 26.7.3/26.7.4, written here), to 1e-12:
       - matched + HK and matched + z through the WHOLE build (circuits in,
         cell out): heterogeneous rats, a rat with n = 1 on each side
         (pooled SD borrowed), k = 2, near-identical changes (HK factor < 1,
         said), k = 1 (HK untestable with the reason, z testable);
       - the PUBLISHED DerSimonian-Laird + Knapp-Hartung example: the BCG
         trials, `rma(yi, vi, method="DL", data=dat.bcg, knha=TRUE)` in
         metafor, as printed on slide 88 of W. Viechtbauer's Cochrane
         Statistical Methods Group training (2016): tau^2 0.3088, estimate
         -0.7141, se 0.1807, t -3.9520, p 0.0019, CI -1.1078 to -0.3204 --
         fed through build as 13 "rats" whose change and variance are the
         trials' log risk ratio and its variance;
       - matched against independent on a within-rat shift riding on big
         between-rat baselines (both p shown), and the refusals: a rat on
         one side only (named), twice on a side, no rat, HK or roles without
         the matched design;
       - cue - baseline from the REAL circuit fixture: every derived cell
         equals a hand per-pair subtraction of the circuit's `values`, a pair
         missing in either window is dropped and n says so; a transition
         circuit against its state circuit's pre, and every refusal of a
         wrong baseline;
       - food - no-food: a hand difference of changes over four circuits a
         rat, with a borrowed SD; BH over the whole drift against a hand BH
         of every tested cell; roles compared instead of pairings; band-mode
         circuits refused against old ones; a default drift byte-identical to
         one with the defaults spelled out, and without any new key.
     Negative controls: `--break hkvar` (DL's SE instead of HK's), `hkdf`
     (k df instead of k - 1), `pairing` (the right side's rats shifted by
     one), `borrow` (a pooled SD twice too big), `baseline` (the pre MEAN
     subtracted instead of each pair's pre), `bhscope` (artifact scope run
     per panel), `roles` (food and no-food read the wrong way round).

Run (PowerShell):  python tools\\check_drift.py [--break <name>]
Exit code 1 if anything failed.
"""
import copy
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scipy import stats                                   # noqa: E402

from backend import drift as D                            # noqa: E402

FAILED = []


def ck(name, ok, detail=""):
    print("  %-5s %s%s" % ("ok" if ok else "FAIL", name,
                           ("   [%s]" % detail) if detail else ""))
    if not ok:
        FAILED.append(name)


def close(a, b, tol=1e-12):
    return a is not None and b is not None and abs(a - b) <= tol


# ---------------------------------------------------------------------------
# Synthetic circuits, built to contract section 3 to the letter.
# ---------------------------------------------------------------------------

ORDER = ["Right ACC", "Right OFC", "Right DHC", "Right RSC", "Right PER",
         "Right POR", "Left POR", "Left PER", "Left RSC", "Left DHC",
         "Left OFC", "Left ACC"]
STATE = ["pre", "cue1", "cue2", "post"]
METHODS = ["coherence", "raw_cc", "amp_cc"]
PARAMS = {"low": 4.0, "high": 12.0, "summary_hz": 8.0, "max_lag_ms": 500.0,
          "notch_hz": 60.0, "pad_s": 10.0, "analysis_fs": 1000.0,
          "channel_rule": "lowest-numbered usable wire", "kind": "state",
          "before_s": 1.0, "after_s": 2.0}
DEV8 = [-0.12, -0.08, -0.04, 0.0, 0.02, 0.05, 0.07, 0.10]   # per-pair scatter


def _sd(xs):
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _offset(w, m, a, b):
    """A fixed, cell-specific offset so cells are not all the same."""
    h = sum(ord(c) for c in w + m + a + b)
    return (h % 17) / 100.0


def circuit(gid, level, grey=(), n_pairs=8, per_pair=None, rep=1,
            params=None, kind="state", windows=None, cue_type="HighTone_LowTone",
            methods=None, usable=None, raw_cells=None, effect=None):
    """One recording's circuit payload.

    Cell value for pair j = level + offset(cell) + per_pair[j] (repeated
    `rep` times -- rep > 1 duplicates every pair to inflate n). `usable`
    limits how many pairs each cell has. `raw_cells` overrides cells with
    {(w, m, key): [values]}.
    """
    windows = windows or STATE
    methods = methods or METHODS
    per_pair = list(DEV8 if per_pair is None else per_pair)
    grey = set(grey)
    regions = [{"region": r, "slot": r.replace(" ", "_"), "label": r,
                "histology": "missed" if r in grey else "intended",
                "status": "grey" if r in grey else "ok",
                "why": ("probe missed %s" % r) if r in grey else "on target"}
               for r in ORDER]
    pairs = [{"pair_id": j + 1, "label": "High tone → Low Tone",
              "opener_t": 100.0 + 60 * j} for j in range(n_pairs * rep)]
    cells = {}
    for w in windows:
        cells[w] = {}
        for m in methods:
            cells[w][m] = {}
            for i, a in enumerate(ORDER):
                for b in ORDER[i + 1:]:
                    if a in grey or b in grey:
                        continue
                    key = "%s|%s" % (a, b)
                    if raw_cells and (w, m, key) in raw_cells:
                        vals = raw_cells[(w, m, key)]
                    else:
                        base = level + _offset(w, m, a, b)
                        if effect:
                            base += effect(w, m, a, b)
                        devs = per_pair[:n_pairs if usable is None else usable]
                        vals = [base + d for d in devs] * rep
                    if not vals:
                        continue
                    n = len(vals)
                    of = n_pairs * rep
                    cells[w][m][key] = {
                        "n": n, "mean": sum(vals) / n, "sd": _sd(vals),
                        "values": [{"pair_id": j + 1, "v": v}
                                   for j, v in enumerate(vals)],
                        "of": of,
                        "warn": ("usable in %d of %d pairs" % (n, of)
                                 if n < of / 2.0 else None)}
    p = dict(PARAMS)
    p["kind"] = kind
    p.update(params or {})
    return {
        "schema": "arc.circuit/1", "kind": kind, "cue_type": cue_type,
        "cue_label": "High tone → Low Tone",
        "windows": list(windows), "methods": list(methods),
        "region_order": list(ORDER), "regions": regions, "pairs": pairs,
        "n_pairs": n_pairs * rep, "cells": cells,
        "region_usable": {w: {r: {"usable": 0 if r in grey else n_pairs,
                                  "of": n_pairs} for r in ORDER}
                          for w in windows},
        "grey": sorted(grey), "params": p,
        "source": {"gid": gid, "session_label": gid, "bank_entry": "e" + gid,
                   "bank_version": 1},
        "computed_on": {"kind": "local"},
    }


def refs(payloads, prefix):
    return [{"artifact_id": "%s%02d" % (prefix, i), "version": 1,
             "digest": "d%s%02d" % (prefix, i),
             "name": p["source"]["gid"]} for i, p in enumerate(payloads)]


def run(L, R, labels=("left", "right")):
    return D.build(L, R, refs(L, "a"), refs(R, "b"), labels)


def safe_build(L, R, lr, rr):
    """build, or None (said) when it refuses -- so a negative control fails
    the checks that depend on it instead of crashing the run."""
    try:
        return D.build(L, R, lr, rr, ("l", "r"))
    except D.DriftError as e:
        print("        (build refused: %s)" % e)
        return None


def cells_of(payload):
    for w, byw in payload["cells"].items():
        for m, panel in byw.items():
            for k, c in panel.items():
                yield w, m, k, c


# ---------------------------------------------------------------------------
# Independent reference (plain loops; shares nothing with drift.py).
# ---------------------------------------------------------------------------

def ref_pool(recs):
    """recs: [(n, mean, sd or None)]. Returns (mean, se, tau2)."""
    num = 0.0
    den = 0
    for n, m, s in recs:
        if s is not None and n >= 2:
            num = num + (n - 1) * s ** 2
            den = den + (n - 1)
    sp = math.sqrt(num / den) if den else None
    ys, vs = [], []
    for n, m, s in recs:
        ys.append(m)
        if s is not None and n >= 2:
            vs.append(s ** 2 / n)
        else:
            vs.append(sp ** 2 / n)
    k = len(ys)
    if k == 1:
        t2 = 0.0
    else:
        W = 0.0
        WY = 0.0
        W2 = 0.0
        for y, v in zip(ys, vs):
            W += 1 / v
            WY += y / v
            W2 += 1 / v ** 2
        yb = WY / W
        Q = 0.0
        for y, v in zip(ys, vs):
            Q += (y - yb) ** 2 / v
        t2 = (Q - (k - 1)) / (W - W2 / W)
        if t2 < 0:
            t2 = 0.0
    S = 0.0
    SY = 0.0
    for y, v in zip(ys, vs):
        S += 1 / (v + t2)
        SY += y / (v + t2)
    return SY / S, math.sqrt(1 / S), t2


def cellish(recs):
    return {"r%d" % i: {"n": n, "mean": m, "sd": s,
                        "warn": None} for i, (n, m, s) in enumerate(recs)}


def pair_pooled(L, R, w, m, key):
    """What pooling every pair as independent would say (the wrong way)."""
    def side(ps):
        xs = []
        for p in ps:
            c = p["cells"][w][m].get(key)
            if c:
                xs.extend(v["v"] for v in c["values"])
        n = len(xs)
        mu = sum(xs) / n
        return mu, _sd(xs) / math.sqrt(n), n
    ml, sl, nl = side(L)
    mr, sr, nr = side(R)
    se = math.sqrt(sl ** 2 + sr ** 2)
    z = (mr - ml) / se
    return mr - ml, z, 2 * stats.norm.sf(abs(z)), nl, nr


# ---------------------------------------------------------------------------
# Negative controls (monkeypatches in this process only).
# ---------------------------------------------------------------------------

def _break(which):
    if which == "tau0":
        orig = D._dl_tau2
        D._dl_tau2 = lambda ys, vs: (0.0, orig(ys, vs)[1])
    elif which == "pairs":
        orig_pool = D.pool

        def pairs_pool(cells_by_recording):
            out = orig_pool(cells_by_recording)
            xs = []
            for _, c in D._as_members(cells_by_recording):
                if c and c.get("values"):
                    xs.extend(v["v"] for v in c["values"])
            if len(xs) >= 2 and out["testable"]:
                n = len(xs)
                mu = sum(xs) / n
                sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
                out.update(mean=mu, se=sd / math.sqrt(n), tau2=0.0, n=n)
            return out
        D.pool = pairs_pool
    elif which == "bh":
        D._bh = lambda ps: list(ps)
    elif which == "vid":
        # Pin by number only: forget the version id.
        orig_get = D._ref_get
        D._ref_get = lambda ref, *keys: (None if keys == ("version_id",)
                                         else orig_get(ref, *keys))
    elif which == "kindparams":
        # Compare every parameter whatever the kind (the old behaviour).
        D.number_params = lambda kind: D.NUMBER_PARAMS
    elif which == "hkvar":
        # Hartung-Knapp's t on DL's SE: no rescaling by the scatter.
        orig_hk = D.hk_test

        def hk_dl(lp, rp, pooled=None):
            out = orig_hk(lp, rp, pooled)
            if out.get("p") is not None:
                se = pooled["se"]
                out.update(se=se, stat=pooled["mean"] / se,
                           p=D._t_p(pooled["mean"] / se, out["df"]))
            return out
        hk_dl.id, hk_dl.label = "hk", D.hk_test.label
        D.hk_test = hk_dl
        D.TESTS["hk"] = hk_dl
    elif which == "hkdf":
        orig_hk = D.hk_test

        def hk_k(lp, rp, pooled=None):
            out = orig_hk(lp, rp, pooled)
            if out.get("p") is not None:
                out.update(df=out["df"] + 1,
                           p=D._t_p(out["stat"], out["df"] + 1))
            return out
        hk_k.id, hk_k.label = "hk", D.hk_test.label
        D.hk_test = hk_k
        D.TESTS["hk"] = hk_k
    elif which == "pairing":
        orig_rats = D._rats

        def shifted(*a, **k):
            got = orig_rats(*a, **k)
            rights = [{g: v for g, v in s.items() if g[0] == "right"}
                      for _, s in got]
            rights = rights[1:] + rights[:1]
            return [(rat, dict({g: v for g, v in s.items()
                                if g[0] == "left"}, **rights[i]))
                    for i, (rat, s) in enumerate(got)]
        D._rats = shifted
    elif which == "borrow":
        orig_psd = D._pooled_sd
        D._pooled_sd = lambda ns, sds: (None if orig_psd(ns, sds) is None
                                        else 2 * orig_psd(ns, sds))
    elif which == "baseline":
        orig_bc = D.baseline_contrast

        def by_mean(payload, state=None):
            out = orig_bc(payload, state)
            base = payload if payload.get("kind") == "state" else state
            for dname, w in D.CONTRAST_WINDOWS[payload["kind"]]:
                for m, panel in out["cells"].get(dname, {}).items():
                    for key, c in panel.items():
                        pre = base["cells"]["pre"][m][key]["mean"]
                        src = {x["pair_id"]: x["v"] for x in
                               payload["cells"][w][m][key]["values"]}
                        xs = [src[v["pair_id"]] - pre for v in c["values"]]
                        c["mean"] = sum(xs) / len(xs)
            return out
        D.baseline_contrast = by_mean
    elif which == "bhscope":
        orig_opts = D.options

        def per_panel(*a, **k):
            o = orig_opts(*a, **k)
            if o["bh_scope"] == "artifact":
                o = dict(o, bh_scope="panel")
            return o
        D.options = per_panel
    elif which == "roles":
        orig_build = D.build

        def swapped(L, R, *a, **k):
            flip = {"food": "no_food", "no_food": "food"}

            def sw(ps):
                out = []
                for p in ps:
                    if p.get("cue_role") in flip:
                        p = dict(p, cue_role=flip[p["cue_role"]])
                    out.append(p)
                return out
            return orig_build(sw(L), sw(R), *a, **k)
        D.build = swapped
    else:
        raise SystemExit("unknown --break %r" % which)
    print("*** NEGATIVE CONTROL: drift.%s broken (%s) -- checks below "
          "SHOULD fail ***\n" % ({"tau0": "_dl_tau2", "pairs": "pool",
                                  "bh": "_bh", "vid": "_ref_get",
                                  "kindparams": "number_params",
                                  "hkvar": "hk_test", "hkdf": "hk_test",
                                  "pairing": "_rats",
                                  "borrow": "_pooled_sd",
                                  "baseline": "baseline_contrast",
                                  "bhscope": "options",
                                  "roles": "build"}[which],
                                 which))


# ---------------------------------------------------------------------------
# 7.4 references: plain loops, nothing imported from drift.py.
# ---------------------------------------------------------------------------

def t2p(t, df):
    """Two-sided p of Student's t on an integer df, from the finite closed
    forms of Abramowitz & Stegun 26.7.3 (odd df) and 26.7.4 (even df):
    A(t|df) = P(|T| < t), p = 1 - A."""
    th = math.atan(abs(t) / math.sqrt(df))
    c = math.cos(th)
    s = math.sin(th)
    if df % 2 == 1:
        tot = 0.0
        if df > 1:
            term = c
            tot = c
            for j in range(1, (df - 3) // 2 + 1):
                term = term * (2.0 * j) / (2.0 * j + 1.0) * c * c
                tot = tot + term
        a = 2.0 / math.pi * (th + s * tot)
    else:
        term = 1.0
        tot = 1.0
        for j in range(1, (df - 2) // 2 + 1):
            term = term * (2.0 * j - 1.0) / (2.0 * j) * c * c
            tot = tot + term
        a = s * tot
    return 1.0 - a


def nms(vals):
    """n, mean, sample SD (None under 2) -- by hand."""
    n = len(vals)
    m = 0.0
    for v in vals:
        m = m + v
    m = m / n
    if n < 2:
        return n, m, None
    ss = 0.0
    for v in vals:
        ss = ss + (v - m) * (v - m)
    return n, m, math.sqrt(ss / (n - 1))


def rclose(a, b, tol=1e-12):
    """Equal to a RELATIVE tolerance -- the right test for p and q, which
    run down to 1e-30, where an absolute 1e-12 would pass anything."""
    if a is None or b is None:
        return a is None and b is None
    return a == b or abs(a - b) <= tol * max(abs(a), abs(b))


def ref_rats(changes, test):
    """changes: [(rat, d, v)]. DerSimonian-Laird over rats, then z or HK.
    A v of None (nothing to borrow an SD from) -> plain mean, untestable."""
    k = len(changes)
    if any(v is None for _, _, v in changes):
        mu = 0.0
        for _, d, _ in changes:
            mu = mu + d
        return {"delta": mu / k, "tau2": None, "se_dl": None, "k": k,
                "se": None, "stat": None, "df": None, "p": None,
                "deltas": [(r, d, None, None) for r, d, _ in changes]}
    t2 = 0.0
    if k > 1:
        W = WY = W2 = 0.0
        for _, d, v in changes:
            W = W + 1.0 / v
            WY = WY + d / v
            W2 = W2 + 1.0 / (v * v)
        yb = WY / W
        Q = 0.0
        for _, d, v in changes:
            Q = Q + (d - yb) * (d - yb) / v
        t2 = (Q - (k - 1)) / (W - W2 / W)
        if t2 < 0:
            t2 = 0.0
    S = SY = 0.0
    for _, d, v in changes:
        S = S + 1.0 / (v + t2)
        SY = SY + d / (v + t2)
    mu = SY / S
    out = {"delta": mu, "tau2": t2, "se_dl": math.sqrt(1.0 / S), "k": k,
           "deltas": [(r, d, math.sqrt(v), (1.0 / (v + t2)) / S)
                      for r, d, v in changes]}
    if test == "z":
        z = mu / math.sqrt(1.0 / S)
        out.update(se=math.sqrt(1.0 / S), stat=z, df=None,
                   p=2.0 * stats.norm.sf(abs(z)))
    elif k < 2:
        out.update(se=None, stat=None, df=None, p=None)
    else:
        ss = 0.0
        for _, d, v in changes:
            ss = ss + (1.0 / (v + t2)) * (d - mu) * (d - mu)
        var = ss / ((k - 1) * S)
        if var <= 0:
            out.update(se=None, stat=None, df=None, p=None)
            return out
        t = mu / math.sqrt(var)
        out.update(se=math.sqrt(var), stat=t, df=k - 1, p=t2p(t, k - 1),
                   factor=ss / (k - 1))
    return out


def _psd(stats_):
    num = 0.0
    den = 0
    for n, m, s in stats_:
        if s is not None and n >= 2:
            num = num + (n - 1) * s * s
            den = den + (n - 1)
    return math.sqrt(num / den) if den else None


def _var(n, s, sp):
    if s is not None and n >= 2:
        return s * s / n
    if sp is None:
        return None
    return sp * sp / n


def _add(*vs):
    tot = 0.0
    for v in vs:
        if v is None:
            return None
        tot = tot + v
    return tot


def ref_matched(spec, test):
    """spec: [(rat, left values, right values)] -- the matched design."""
    Ls = [nms(lv) for _, lv, _ in spec]
    Rs = [nms(rv) for _, _, rv in spec]
    spL, spR = _psd(Ls), _psd(Rs)
    ch = []
    for i, (rat, _, _) in enumerate(spec):
        d = Rs[i][1] - Ls[i][1]
        v = _add(_var(Ls[i][0], Ls[i][2], spL), _var(Rs[i][0], Rs[i][2], spR))
        ch.append((rat, d, v))
    return ref_rats(ch, test)


def ref_roles(spec, test):
    """spec: [(rat, {(side, role): values})] -- food - no-food change."""
    groups = [(s, r) for r in ("food", "no_food") for s in ("left", "right")]
    st = {g: [nms(vals[g]) for _, vals in spec] for g in groups}
    sp = {g: _psd(st[g]) for g in groups}
    ch = []
    for i, (rat, _) in enumerate(spec):
        f = st[("right", "food")][i][1] - st[("left", "food")][i][1]
        o = st[("right", "no_food")][i][1] - st[("left", "no_food")][i][1]
        v = _add(*[_var(st[g][i][0], st[g][i][2], sp[g]) for g in groups])
        ch.append((rat, f - o, v))
    return ref_rats(ch, test)


def hand_bh(ps):
    idx = [i for i, p in enumerate(ps) if p is not None]
    m = len(idx)
    srt = sorted(idx, key=lambda i: ps[i])
    q = [None] * len(ps)
    run_min = 1.0
    for r in range(m, 0, -1):
        run_min = min(run_min, ps[srt[r - 1]] * m / r)
        q[srt[r - 1]] = min(1.0, run_min)
    return q


KEY = "Right ACC|Right OFC"
WIN, MET = "cue1", "coherence"


def rat_ref(side, rat, gid, role=None):
    aid = "%s-%s%s" % (side[0], rat, "-" + role if role else "")
    return {"artifact_id": aid, "version": 1, "version_id": "v" + aid,
            "digest": "d" + aid, "name": gid, "rat": rat}


def mk_matched(spec, key=KEY, w=WIN, m=MET):
    """[(rat, left values, right values)] -> L, R, lrefs, rrefs. The one
    cell under test holds exactly these values; every other cell gets a
    rat-specific level, change and spread, so rats differ everywhere (with
    one level for all, every rat's change in the other cells is the same
    number and HK is -- rightly -- untestable there)."""
    L, R, lr, rr = [], [], [], []
    for i, (rat, lv, rv) in enumerate(spec):
        lev = 0.2 + 0.05 * i
        for side, vals, P, refs, sh in (("left", lv, L, lr, 0.0),
                                        ("right", rv, R, rr,
                                         0.01 * ((i * 7) % 5) + 0.002 * i)):
            gid = "%s-%s" % (side[0].upper(), rat)
            # A cell- and rat-specific change on the right, so the panels'
            # p differ and BH has something to reorder.
            fx = None if side == "left" else (
                lambda w_, m_, a_, b_, i=i: (((sum(ord(ch) for ch in
                                                   w_ + m_ + a_ + b_)
                                               * (i + 3)) % 9) - 4) * 0.004)
            P.append(circuit(gid, lev + sh,
                             per_pair=[d * (0.6 + 0.15 * ((i + len(side)) % 4))
                                       for d in DEV8],
                             raw_cells={(w, m, key): vals}, effect=fx))
            refs.append(rat_ref(side, rat, gid))
    return L, R, lr, rr


def pair_vals(mean, sd):
    """Two values with exactly this mean and sample SD."""
    h = sd / math.sqrt(2.0)
    return [mean - h, mean + h]


def cmp_cell(c, ref, tol=1e-12):
    """(ok, detail): a built cell against a reference dict."""
    got = [("delta", c.get("delta"), ref["delta"]),
           ("tau2", c.get("tau2"), ref["tau2"]),
           ("se", c.get("se"), ref["se"]),
           ("p", c.get("p"), ref["p"])]
    stat = c.get("t") if ref.get("df") is not None else c.get("z")
    got.append(("stat", stat, ref["stat"]))
    bad = []
    for nm, a, b in got:
        if a is None and b is None:
            continue
        # delta, tau2, se, p: absolute 1e-12. The statistic: RELATIVE 1e-12
        # -- it can be in the hundreds, and it is what p is a monotone
        # function of. (p is not compared relatively: the reference's
        # closed form is 1 - A, which cancels for tiny p -- measured 3e-11
        # relative at p = 4e-5 and 1e-7 at p = 1e-9 -- so a relative p test
        # would be testing the reference, not drift.)
        if nm == "stat":
            if not rclose(a, b):
                bad.append("%s %r vs %r" % (nm, a, b))
        elif a is None or b is None or abs(a - b) > tol * max(1.0, abs(b)):
            bad.append("%s %r vs %r" % (nm, a, b))
    if (ref.get("df") if ref.get("p") is not None else None) \
            != (c.get("df") if c.get("p") is not None else None):
        bad.append("df %r vs %r" % (c.get("df"), ref.get("df")))
    if len(ref["deltas"]) != len(c.get("deltas") or []):
        bad.append("%d rats vs %d" % (len(c.get("deltas") or []),
                                      len(ref["deltas"])))
    for (r, d, se, w), dd in zip(ref["deltas"], c.get("deltas") or []):
        if dd["rat"] != r or abs(dd["delta"] - d) > tol \
                or ((se is None) != (dd["se"] is None)) \
                or (se is not None and abs(dd["se"] - se) > tol) \
                or ((w is None) != (dd.get("weight") is None)) \
                or (w is not None and abs(dd["weight"] - w) > tol):
            bad.append("rat %s: %r vs %r" % (r, dd, (d, se, w)))
            break
    return not bad, "; ".join(bad)


def load_fixture(name):
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "web", "_dev", "fixtures", name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def shift_circuit(base, gid, i, off, rng):
    """A schema-valid synthetic recording from a real circuit: every value
    v -> v + off + a per-cell wobble + seeded per-pair noise (so rats'
    changes differ); n, mean, SD recomputed by hand."""
    P = copy.deepcopy(base)
    P["source"] = dict(P["source"], gid=gid, session_label=gid)
    k = 0
    for w in P["windows"]:
        for m in P["methods"]:
            for c in P["cells"][w][m].values():
                k += 1
                o = off + ((k * 7 + i * 3) % 5 - 2) * 0.004 + 0.001 * i
                for x in c["values"]:
                    x["v"] = x["v"] + o + rng.gauss(0, 0.01)
                n, mu, sd = nms([x["v"] for x in c["values"]])
                c["mean"], c["sd"] = mu, sd
    return P


def within_rat_checks():
    print("\n4. Within rat, Hartung-Knapp, contrasts, BH scope "
          "(arc_contracts.md 7.4)")
    rng = random.Random(20260929)

    def rvals(mu, sd, n):
        return [mu + rng.gauss(0, sd) for _ in range(n)]

    print("   the published DL + Knapp-Hartung example (metafor BCG, "
          "knha=TRUE, method=DL)")
    bcg = [(4, 119, 11, 128), (6, 300, 29, 274), (3, 228, 11, 209),
           (62, 13536, 248, 12619), (33, 5036, 47, 5761),
           (180, 1361, 372, 1079), (8, 2537, 10, 619),
           (505, 87886, 499, 87892), (29, 7470, 45, 7232),
           (17, 1699, 65, 1600), (186, 50448, 141, 27197),
           (5, 2493, 3, 2338), (27, 16886, 29, 17825)]
    spec = []
    for j, (tp, tn, cp, cn) in enumerate(bcg):
        yi = math.log((tp / (tp + tn)) / (cp / (cp + cn)))
        vi = 1 / tp - 1 / (tp + tn) + 1 / cp - 1 / (cp + cn)
        # left n=2 mean 0, right n=2 mean yi, each SD sqrt(vi): the rat's
        # change is yi and its variance vi/2 + vi/2 = vi, exactly.
        spec.append(("r%d" % (j + 1), pair_vals(0.0, math.sqrt(vi)),
                     pair_vals(yi, math.sqrt(vi))))
    L, R, lr, rr = mk_matched(spec)
    b = D.build(L, R, lr, rr, ("before", "after"), design="matched",
                test="hk")
    c = b["cells"][WIN][MET][KEY]
    tcrit = stats.t.ppf(0.975, 12)
    lo, hi = c["delta"] - tcrit * c["se"], c["delta"] + tcrit * c["se"]
    ck("BCG through build: tau2 %.4f est %.4f se %.4f t %.4f df %s p %.4f "
       "CI %.4f..%.4f  [published 0.3088 / -0.7141 / 0.1807 / -3.9520 / 12 "
       "/ 0.0019 / -1.1078..-0.3204]"
       % (c["tau2"], c["delta"], c["se"], c["t"], c["df"], c["p"], lo, hi),
       round(c["tau2"], 4) == 0.3088 and round(c["delta"], 4) == -0.7141
       and round(c["se"], 4) == 0.1807 and round(c["t"], 4) == -3.9520
       and c["df"] == 12 and round(c["p"], 4) == 0.0019
       and round(lo, 4) == -1.1078 and round(hi, 4) == -0.3204)
    ref = ref_matched(spec, "hk")
    ok, why = cmp_cell(c, ref)
    ck("  and equal to the hand implementation to 1e-12 (HK factor %.4f)"
       % ref["factor"], ok, why)

    print("\n   matched against a hand implementation, through build "
          "(tol 1e-12)")
    cases = {
        "heterogeneous rats, n 3-8":
            [("r%d" % i, rvals(0.2 + 0.1 * i, 0.03 + 0.01 * i, 3 + i),
              rvals(0.25 + 0.1 * i + 0.02 * (i % 3), 0.02 + 0.015 * i, 8 - i))
             for i in range(6)],
        "a rat with n = 1 on the right, another on the left (pooled SD)":
            [("r3", rvals(0.30, 0.04, 6), [0.41]),
             ("r4", [0.22], rvals(0.30, 0.05, 7)),
             ("r6", rvals(0.35, 0.03, 8), rvals(0.36, 0.06, 5)),
             ("r7", rvals(0.28, 0.05, 4), rvals(0.33, 0.02, 8))],
        "k = 2": [("r8", rvals(0.30, 0.05, 7), rvals(0.40, 0.04, 6)),
                  ("r9", rvals(0.50, 0.03, 5), rvals(0.52, 0.05, 8))],
        "near-identical changes (HK factor < 1)":
            [("r%d" % i, [0.1 * i + d for d in (-0.05, 0.0, 0.05)],
              [0.1 * i + 0.02 + 0.0001 * i + d for d in (-0.05, 0.0, 0.05)])
             for i in range(5)],
    }
    for name, spec in cases.items():
        L, R, lr, rr = mk_matched(spec)
        for test in ("hk", "z"):
            b = D.build(L, R, lr, rr, ("P1", "P4"), design="matched",
                        test=test)
            c = b["cells"][WIN][MET][KEY]
            ref = ref_matched(spec, test)
            ok, why = cmp_cell(c, ref)
            extra = (" factor %.3f" % ref["factor"]) if test == "hk" else ""
            ck("%s, %s: delta %.5f se %.5f %s %.3f p %.5g k %d%s"
               % (name, test, ref["delta"], ref["se"],
                  "t" if test == "hk" else "z", ref["stat"], ref["p"],
                  ref["k"], extra), ok, why)
        if "n = 1" in name:
            ck("  the n = 1 rats are used with a borrowed-SD warning each",
               sum(1 for s in c["warn"] if "borrowed" in s) == 2
               and c["k"] == 4, c["warn"])
        if "factor < 1" in name:
            bh_ = D.build(L, R, lr, rr, ("P1", "P4"), design="matched",
                          test="hk")
            ch_ = bh_["cells"][WIN][MET][KEY]
            ck("  the HK factor is below 1 (%.3g) and the HK SE is SMALLER "
               "than DL's (%.3g < %.3g) -- and the result says so"
               % (ch_["hk_factor"], ch_["se"], ch_["se_dl"]),
               ch_["hk_factor"] < 1 and ch_["se"] < ch_["se_dl"]
               and D.HK_NOTE in bh_["notes"])

    spec = [("r5", rvals(0.30, 0.04, 6), rvals(0.40, 0.03, 7))]
    L, R, lr, rr = mk_matched(spec)
    b = D.build(L, R, lr, rr, ("P1", "P4"), design="matched", test="hk")
    c = b["cells"][WIN][MET][KEY]
    ck("k = 1 with HK: not tested, and why: %s" % c["why"],
       c["p"] is None and c["t"] is None and not c["testable"]
       and "two" in (c["why"] or "") and c["delta"] is not None)
    bz = D.build(L, R, lr, rr, ("P1", "P4"), design="matched", test="z")
    cz = bz["cells"][WIN][MET][KEY]
    ok, why = cmp_cell(cz, ref_matched(spec, "z"))
    ck("k = 1 with z: tested on the one rat's own SE, and warned", ok
       and any(D.K1_RAT_SAY in s for s in cz["warn"]), why)
    ck("the t tail: drift's p against A&S's closed form, df 1..12, t in "
       "0.1..9 (max |diff| %.2g)" % max(
           abs(D._t_p(t, df) - t2p(t, df)) for df in range(1, 13)
           for t in (0.1, 0.7, 1.5, 2.2, 3.9, 9.0)),
       max(abs(D._t_p(t, df) - t2p(t, df)) for df in range(1, 13)
           for t in (0.1, 0.7, 1.5, 2.2, 3.9, 9.0)) < 1e-12)

    print("\n   matched is more powerful than independent on a within-rat "
          "change")
    levels = [0.15, 0.62, 0.31, 0.80, 0.45, 0.22, 0.70, 0.38]
    spec = [("r%d" % (i + 3), rvals(lev, 0.02, 8),
             rvals(lev + 0.03, 0.02, 8)) for i, lev in enumerate(levels)]
    L, R, lr, rr = mk_matched(spec)
    ind = D.build(L, R, lr, rr, ("P1", "P4"))
    mhk = D.build(L, R, lr, rr, ("P1", "P4"), design="matched", test="hk",
                  bh_scope="artifact")
    mz = D.build(L, R, lr, rr, ("P1", "P4"), design="matched", test="z")
    ci, ch, cz = (x["cells"][WIN][MET][KEY] for x in (ind, mhk, mz))
    print("   8 rats, baselines 0.15..0.80, every rat +0.03 on the right, "
          "pair noise SD 0.02:")
    print("     independent (z):  delta %.4f  se %.4f  p %.3g"
          % (ci["delta"], ci["se"], ci["p"]))
    print("     matched, z:       delta %.4f  se %.4f  p %.3g"
          % (cz["delta"], cz["se"], cz["p"]))
    print("     matched, HK:      delta %.4f  se %.4f  t %.2f on %d df  "
          "p %.3g" % (ch["delta"], ch["se"], ch["t"], ch["df"], ch["p"]))
    ck("matched HK finds it (p %.2g < .001) where independent does not "
       "(p %.2g > .2)" % (ch["p"], ci["p"]), ch["p"] < 0.001 and ci["p"] > 0.2)
    ck("the result says it in words: %r" % mhk["analysis_say"],
       mhk["analysis_say"].startswith(
           "within-rat, 8 rats; Hartung–Knapp t on 7 df; BH across all "
           "windows and methods"))
    ck("the payload carries design/test/bh_scope/contrast/pooled_by and "
       "the rats paired", mhk["design"] == "matched"
       and mhk["test"]["id"] == "hk" and mhk["bh_scope"] == "artifact"
       and mhk["contrast"] is None and mhk["pooled_by"] == "cue_type"
       and [m["rat"] for m in mhk["matched"]]
       == ["r%d" % (i + 3) for i in range(8)]
       and all(m["left"]["artifact_id"] == "l-" + m["rat"]
               and m["right"]["artifact_id"] == "r-" + m["rat"]
               for m in mhk["matched"]))
    ck("each HK cell has t, df, hk_factor and per-rat deltas",
       all(c.get("t") is not None and c.get("df") == 7
           and c.get("hk_factor") is not None and len(c["deltas"]) == 8
           for *_, c in cells_of(mhk)))

    print("\n   BH across the whole drift")
    every = [(w, m, k) for w in mhk["windows"] for m in mhk["methods"]
             for k in mhk["cells"][w][m]]
    hq = hand_bh([mhk["cells"][w][m][k]["p"] for w, m, k in every])
    ck("q equals a hand BH over all %d tested cells of %d panels "
       "(relative 1e-12)"
       % (sum(1 for x in hq if x is not None),
          len(mhk["windows"]) * len(mhk["methods"])),
       all(rclose(mhk["cells"][w][m][k]["q"], q)
           for (w, m, k), q in zip(every, hq)))
    mpan = D.build(L, R, lr, rr, ("P1", "P4"), design="matched", test="hk")
    ndiff = sum(1 for w, m, k in every
                if not rclose(mpan["cells"][w][m][k]["q"],
                              mhk["cells"][w][m][k]["q"], 1e-9))
    ck("  and it is not per-panel BH by another name (%d of %d q differ)"
       % (ndiff, len(every)), ndiff > 0)
    ck("  the payload counts the family (%s tests)" % mhk.get("bh_tests"),
       mhk.get("bh_tests") == sum(1 for x in hq if x is not None))

    print("\n   refusals of the matched design")
    one = [x for x in spec if x[0] != "r5"]
    Lx, Rx, lrx, rrx = mk_matched(spec)
    k5 = [i for i, r in enumerate(rrx) if r["rat"] == "r5"][0]
    ok, why = D.compatible(Lx, Rx[:k5] + Rx[k5 + 1:], lrx,
                           rrx[:k5] + rrx[k5 + 1:], design="matched")
    s = next((x for x in why if "r5" in x), "")
    ck("a rat on one side only is refused, named: %s" % s,
       not ok and "only in the left group" in s)
    dup = circuit("R-r3b", 0.3)
    ok, why = D.compatible(Lx, Rx + [dup], lrx,
                           rrx + [rat_ref("right", "r3", "R-r3b", "again")],
                           design="matched")
    s = next((x for x in why if "r3 is in the right group 2 times" in x), "")
    ck("a rat twice on a side is refused (its own artifact, so only the "
       "rat rule catches it): %s" % s, not ok and bool(s) and len(why) == 1,
       why)
    ok, why = D.compatible(Lx, Rx, [dict(r, rat=None) for r in lrx], rrx,
                           design="matched")
    ck("a member with no rat is refused", not ok
       and any("which rat" in x for x in why))
    ok, why = D.compatible(Lx, Rx, lrx, rrx, test="hk")
    ck("Hartung-Knapp without the matched design is refused: %s"
       % next((x for x in why if "Hartung" in x), ""),
       not ok and any("Hartung" in x for x in why))
    try:
        D.build(Lx, Rx, lrx, rrx, ("a", "b"), design="paired")
        ck("an unknown design is refused", False)
    except D.DriftError as e:
        ck("an unknown design is refused: %s" % e, "design" in str(e))
    _ = one

    print("\n   cue - baseline, from the real circuit fixture "
          "(J7 s1, Click -> High tone)")
    S7 = load_fixture("circuit_s360e48254222.json")
    der = D.baseline_contrast(S7)
    n_cells = n_dropped_cells = n_dropped_pairs = n_absent = 0
    bad = []
    for dname, w in (("cue1-pre", "cue1"), ("cue2-pre", "cue2"),
                     ("post-pre", "post")):
        for m in S7["methods"]:
            for key, cell in S7["cells"][w][m].items():
                pre = {}
                pc = S7["cells"]["pre"][m].get(key)
                for x in (pc or {}).get("values") or []:
                    pre[x["pair_id"]] = x["v"]
                diffs = [x["v"] - pre[x["pair_id"]] for x in cell["values"]
                         if x["pair_id"] in pre]
                got = der["cells"][dname][m].get(key)
                if not diffs:
                    n_absent += 1
                    if got is not None:
                        bad.append("%s %s %s should be absent" % (dname, m,
                                                                 key))
                    continue
                n_cells += 1
                n, mu, sd = nms(diffs)
                if n < len(cell["values"]) or n < len(pre):
                    n_dropped_cells += 1
                    n_dropped_pairs += max(len(cell["values"]),
                                           len(pre)) - n
                of = cell["of"]
                warn = ("usable in %d of %d pairs" % (n, of)
                        if n < of / 2.0 else None)
                if got is None or got["n"] != n \
                        or abs(got["mean"] - mu) > 1e-12 \
                        or ((sd is None) != (got["sd"] is None)) \
                        or (sd is not None and abs(got["sd"] - sd) > 1e-12) \
                        or got["warn"] != warn or got["of"] != of:
                    bad.append("%s %s %s: %r vs n %d mean %r sd %r"
                               % (dname, m, key, got and {
                                   k: got[k] for k in ("n", "mean", "sd")},
                                  n, mu, sd))
    ck("every derived cell equals a hand per-pair subtraction (%d cells, "
       "tol 1e-12)" % n_cells, not bad and n_cells > 0,
       "; ".join(bad[:3]))
    ck("  pairs missing in either window are dropped and n says so (%d "
       "cells lost %d pairs; %d cells with no common pair are absent)"
       % (n_dropped_cells, n_dropped_pairs, n_absent),
       n_dropped_cells > 0 and not bad)
    ck("  windows are %s, the grey regions carried" % der["windows"],
       der["windows"] == ["cue1-pre", "cue2-pre", "post-pre"]
       and der["grey"] == sorted(S7["grey"]))

    # A transition circuit takes its pre from the state circuit.
    tr = copy.deepcopy(S7)
    tr["kind"] = "transition"
    tr["params"] = dict(tr["params"], kind="transition", before_s=1.0,
                        after_s=2.0)
    tr["windows"] = ["onset", "switch", "offset"]
    tr["cells"] = {nw: copy.deepcopy(S7["cells"][ow]) for nw, ow in
                   (("onset", "cue1"), ("switch", "cue2"), ("offset", "post"))}
    for w in tr["windows"]:
        for m in tr["methods"]:
            for c in tr["cells"][w][m].values():
                for x in c["values"]:
                    x["v"] = x["v"] + 0.01 * x["pair_id"]
                c["n"], c["mean"], c["sd"] = nms([x["v"] for x in c["values"]])
    base = copy.deepcopy(S7)
    base["grey"] = sorted(set(base["grey"]) | {"Right DHC"})
    dt = D.baseline_contrast(tr, base)
    bad, n_t = [], 0
    for dname, w in (("onset-pre", "onset"), ("switch-pre", "switch"),
                     ("offset-pre", "offset")):
        for m in tr["methods"]:
            for key, cell in tr["cells"][w][m].items():
                if "Right DHC" in key.split("|"):
                    if key in dt["cells"][dname][m]:
                        bad.append("%s should be grey" % key)
                    continue
                pre = {x["pair_id"]: x["v"] for x in
                       (base["cells"]["pre"][m].get(key) or {})
                       .get("values") or []}
                diffs = [x["v"] - pre[x["pair_id"]] for x in cell["values"]
                         if x["pair_id"] in pre]
                got = dt["cells"][dname][m].get(key)
                if not diffs:
                    continue
                n_t += 1
                n, mu, sd = nms(diffs)
                if got is None or got["n"] != n or abs(got["mean"] - mu) > 1e-12:
                    bad.append("%s %s %s" % (dname, m, key))
    ck("transition: onset/switch/offset minus the STATE circuit's pre, per "
       "pair (%d cells); a region grey in the baseline is grey here"
       % n_t, not bad and n_t > 0 and "Right DHC" in dt["grey"],
       "; ".join(bad[:3]))

    def refused_base(bp, word):
        Lt = [tr]
        Rt = [dict(copy.deepcopy(tr), source=dict(tr["source"],
                                                  gid="other-gid"))]
        rb = copy.deepcopy(S7)
        rb["source"] = dict(rb["source"], gid="other-gid")
        ok, why = D.compatible(Lt, Rt, refs(Lt, "a"), refs(Rt, "b"),
                               contrast="baseline",
                               baselines={"left": [bp], "right": [rb]})
        s = next((x for x in why if word in x), "")
        return (not ok) and bool(s), s or "; ".join(why) or "accepted"
    ok, s = refused_base(None, "none was given")
    ck("a transition member with no baseline is refused: %s" % s, ok)
    other = copy.deepcopy(S7)
    other["source"] = dict(other["source"], gid="elsewhere")
    ok, s = refused_base(other, "recording")
    ck("a baseline from another recording is refused: %s" % s, ok)
    moved = copy.deepcopy(S7)
    moved["pairs"] = [dict(p, opener_t=p["opener_t"] + 30.0)
                      for p in moved["pairs"]]
    ok, s = refused_base(moved, "not the same cue pairs")
    ck("a baseline whose pairs open at other moments is refused: %s" % s, ok)
    bandb = copy.deepcopy(S7)
    bandb["params"] = dict(bandb["params"], band="theta",
                           coherence_mode="band")
    ok, s = refused_base(bandb, "band")
    ck("a baseline of another band is refused: %s" % s, ok)
    Lt = [tr]
    rb = copy.deepcopy(S7)
    rb["source"] = dict(rb["source"], gid="other-gid")
    Rt = [dict(copy.deepcopy(tr), source=dict(tr["source"], gid="other-gid"))]
    ok, why = D.compatible(Lt, Rt, refs(Lt, "a"), refs(Rt, "b"),
                           contrast="baseline",
                           baselines={"left": [copy.deepcopy(S7)],
                                      "right": [rb]})
    ck("  (the right baselines are accepted)", ok, "; ".join(why))
    rest = copy.deepcopy(S7)
    rest["kind"], rest["windows"] = "rest", ["rest"]
    ok, why = D.compatible([rest], [copy.deepcopy(rest)], refs([rest], "a"),
                           refs([rest], "b"), contrast="baseline")
    ck("rest circuits have no baseline contrast: %s"
       % next((x for x in why if "Rest" in x), ""),
       not ok and any("Rest" in x for x in why))

    print("\n   cue - baseline through build: matched, HK, real-fixture "
          "rats")
    rats = ["r%d" % i for i in (3, 4, 6, 7)]
    Lb = [shift_circuit(S7, "L-" + r, i, 0.0, rng)
          for i, r in enumerate(rats)]
    Rb = [shift_circuit(S7, "R-" + r, i + 5, 0.02, rng)
          for i, r in enumerate(rats)]
    lrb = [rat_ref("left", r, "L-" + r) for r in rats]
    rrb = [rat_ref("right", r, "R-" + r) for r in rats]
    bb = D.build(Lb, Rb, lrb, rrb, ("P1", "P4"), design="matched",
                 test="hk", bh_scope="artifact", contrast="baseline")
    checked, bad = 0, []
    for dname, w in (("cue1-pre", "cue1"), ("post-pre", "post")):
        for m in ("coherence", "amp_cc"):
            for key, c in bb["cells"][dname][m].items():
                spec = []
                for r, pl, pr in zip(rats, Lb, Rb):
                    sides = []
                    for P in (pl, pr):
                        pre = {x["pair_id"]: x["v"] for x in
                               (P["cells"]["pre"][m].get(key) or {})
                               .get("values") or []}
                        src = (P["cells"][w][m].get(key) or {}).get(
                            "values") or []
                        sides.append([x["v"] - pre[x["pair_id"]] for x in src
                                      if x["pair_id"] in pre])
                    spec.append((r, sides[0], sides[1]))
                if any(not a or not b_ for _, a, b_ in spec):
                    continue
                ok, why = cmp_cell(c, ref_matched(spec, "hk"))
                checked += 1
                if not ok:
                    bad.append("%s %s %s: %s" % (dname, m, key, why))
    ck("%d cue - baseline cells equal the hand per-pair subtraction then "
       "the hand matched HK" % checked, checked > 20 and not bad,
       "; ".join(bad[:2]))
    ck("  the payload says contrast baseline, and the note on wires",
       bb["contrast"] == "baseline" and bb["windows"]
       == ["cue1-pre", "cue2-pre", "post-pre"]
       and any("wire" in n for n in bb["notes"])
       and "each window minus the baseline" in bb["analysis_say"])

    print("\n   food - no-food: four circuits a rat")
    spec = []
    for i, r in enumerate(["r3", "r4", "r6", "r7", "r8"]):
        vals = {}
        for s, role, mu in (("left", "food", 0.3), ("right", "food", 0.36),
                            ("left", "no_food", 0.32),
                            ("right", "no_food", 0.34)):
            n = 1 if (r == "r6" and s == "right" and role == "food") \
                else 4 + (i + len(role)) % 4
            vals[(s, role)] = rvals(mu + 0.05 * i, 0.03 + 0.005 * i, n)
        spec.append((r, vals))
    Lr, Rr, lrr, rrr = [], [], [], []
    for r, vals in spec:
        for s, P, refs_ in (("left", Lr, lrr), ("right", Rr, rrr)):
            gid = "%s-%s" % (s[0].upper(), r)
            for role in ("food", "no_food"):
                ct = "Click_HighTone" if role == "food" else "Noise_LowTone"
                c = circuit(gid, 0.3, cue_type=ct,
                            raw_cells={(WIN, MET, KEY): vals[(s, role)]})
                c["cue_role"] = role
                c["role_source"] = {"sessions": ["con-" + r]}
                P.append(c)
                refs_.append(rat_ref(s, r, gid, role))
    rb_ = D.build(Lr, Rr, lrr, rrr, ("P1", "P4"), design="matched",
                  test="hk", contrast="roles")
    c = rb_["cells"][WIN][MET][KEY]
    ref = ref_roles(spec, "hk")
    ok, why = cmp_cell(c, ref)
    ck("D = food change - no-food change, per rat, equals the hand "
       "difference of changes (D %.5f, se %.5f, t %.3f on %d df; r6 borrows "
       "an SD)" % (ref["delta"], ref["se"], ref["stat"], ref["df"]),
       ok and any("r6" in s and "borrowed" in s for s in c["warn"]), why)
    ck("  each rat's D carries its two changes",
       all(close(d["food"] - d["no_food"], d["delta"]) for d in c["deltas"]))
    ck("  the cell's left/right are the pooled no-food and food changes, "
       "and the payload says so", "no-food" in rb_["cell_sides"]["left"]
       and "food" in rb_["cell_sides"]["right"]
       and c["left"]["k"] == 5 and c["right"]["k"] == 5)
    ck("  matched rows per rat and role, members carry role and source",
       len(rb_["matched"]) == 10 and rb_["pooled_by"] == "cue_role"
       and all(m.get("role_source") for m in rb_["left"]["members"]))
    ok, why = D.compatible(Lr[:-1], Rr, lrr[:-1], rrr, design="matched",
                           contrast="roles")
    ck("a rat missing one of its four is refused, naming what: %s"
       % next((x for x in why if "missing" in x), why),
       not ok and any("r8 is missing its no-food pair on the left" in x
                      for x in why))
    ok, why = D.compatible(Lr, Rr, lrr, rrr, contrast="roles")
    ck("roles without the matched design is refused",
       not ok and any("matched" in x for x in why))

    print("\n   compared by cue role (7.2)")
    food_L = [p for p in Lr if p["cue_role"] == "food"]
    food_R = [p for p in Rr if p["cue_role"] == "food"]
    fl = [r for r, p in zip(lrr, Lr) if p["cue_role"] == "food"]
    fr = [r for r, p in zip(rrr, Rr) if p["cue_role"] == "food"]
    food_R[1] = dict(food_R[1], cue_type="HighTone_Noise",
                     cue_label="High tone → Noise")
    ok, why = D.compatible(food_L, food_R, fl, fr, design="matched")
    ck("every member with a role: pairings are not compared, a rat whose "
       "food pair changed pairing between days is: %s"
       % next((x for x in why if "within a rat" in x), why),
       not ok and len(why) == 1 and "within a rat" in why[0])
    food_R[1] = dict(food_R[1], cue_type="Click_HighTone",
                     cue_label="Click → High tone")
    for p in food_L[:2]:
        p["cue_type"] = "LowTone_Click"
    for p in food_R[:2]:
        p["cue_type"] = "LowTone_Click"
    fb = D.build(food_L, food_R, fl, fr, ("P1", "P4"), design="matched",
                 test="hk")
    ck("two pairings under one role are compared, pooled_by cue_role, "
       "labelled '%s'" % fb["cue_label"], fb["pooled_by"] == "cue_role"
       and fb["cue_role"] == "food" and fb["cue_label"] == "food pair"
       and "the food pair of each rat" in fb["analysis_say"])
    mixed = [dict(food_L[0])]
    mixed[0].pop("cue_role")
    ok, why = D.compatible(mixed + food_L[1:], food_R, fl, fr,
                           design="matched")
    ck("some with a role and some without is refused: %s"
       % next((x for x in why if "some do not" in x), why),
       not ok and any("some do not" in x for x in why))
    ok, why = D.compatible(food_L, [p for p in Rr if p["cue_role"]
                                    == "no_food"], fl,
                           [r for r, p in zip(rrr, Rr)
                            if p["cue_role"] == "no_food"], design="matched")
    ck("food against no-food (not the roles contrast) is refused naming "
       "cue_role", not ok and any("cue_role" in x for x in why))

    print("\n   band mode, and the defaults")
    bandc = circuit("R0", .3, params={"band": "theta",
                                      "coherence_mode": "band",
                                      "raw_cc_filtered": True})
    Lp = [circuit("L%d" % i, v) for i, v in enumerate([.25, .3, .35])]
    ok, why = D.compatible(Lp, [bandc], refs(Lp, "a"), refs([bandc], "b"))
    ck("a theta band circuit against old ones (same low/high/max_lag) is "
       "refused naming coherence_mode: %s"
       % next((x for x in why if "coherence_mode" in x), ""),
       not ok and any("coherence_mode" in x for x in why))
    Rp = [circuit("R%d" % i, v) for i, v in enumerate([.3, .33, .4])]
    d0 = D.build(Lp, Rp, refs(Lp, "a"), refs(Rp, "b"), ("l", "r"))
    d1 = D.build(Lp, Rp, refs(Lp, "a"), refs(Rp, "b"), ("l", "r"),
                 design="independent", test="z", bh_scope="panel",
                 contrast=None)
    ck("a default drift is byte-identical to one with the defaults spelled "
       "out, and has none of the new keys",
       json.dumps(d0, sort_keys=True) == json.dumps(d1, sort_keys=True)
       and not any(k in d0 for k in ("design", "bh_scope", "contrast",
                                     "pooled_by", "matched",
                                     "analysis_say"))
       and "id" not in d0["test"])
    try:
        json.dumps(mhk, allow_nan=False)
        json.dumps(rb_, allow_nan=False)
        json.dumps(bb, allow_nan=False)
        ck("matched, roles and baseline payloads are strict JSON", True)
    except ValueError as e:
        ck("matched, roles and baseline payloads are strict JSON", False,
           str(e))


def main():
    if "--break" in sys.argv:
        _break(sys.argv[sys.argv.index("--break") + 1])

    print("1. Reference: independent loops vs drift.pool (tol 1e-12)")
    cases = {
        "three recordings, heterogeneous":
            [(8, 0.31, 0.08), (6, 0.42, 0.10), (7, 0.25, 0.05)],
        "five recordings, homogeneous (tau2 -> 0)":
            [(8, 0.300, 0.08), (8, 0.302, 0.08), (8, 0.299, 0.08),
             (8, 0.301, 0.08), (8, 0.300, 0.08)],
        "one recording with n = 1 borrows the pooled SD":
            [(8, 0.31, 0.08), (1, 0.60, None), (5, 0.28, 0.12),
             (3, 0.35, 0.02)],
        "k = 1": [(6, 0.40, 0.09)],
        "k = 2": [(8, 0.10, 0.20), (2, 0.90, 0.05)],
    }
    for name, recs in cases.items():
        rm, rse, rt2 = ref_pool(recs)
        got = D.pool(cellish(recs))
        ck("%s: mean %.6f se %.6f tau2 %.6g" % (name, rm, rse, rt2),
           close(got["mean"], rm) and close(got["se"], rse)
           and close(got["tau2"], rt2),
           "drift: mean %r se %r tau2 %r" % (got["mean"], got["se"],
                                             got["tau2"]))

    # BCG vaccine trials (Colditz et al. 1994), metafor's dat.bcg.
    bcg = [(4, 119, 11, 128), (6, 300, 29, 274), (3, 228, 11, 209),
           (62, 13536, 248, 12619), (33, 5036, 47, 5761),
           (180, 1361, 372, 1079), (8, 2537, 10, 619),
           (505, 87886, 499, 87892), (29, 7470, 45, 7232),
           (17, 1699, 65, 1600), (186, 50448, 141, 27197),
           (5, 2493, 3, 2338), (27, 16886, 29, 17825)]
    recs = []
    for tp, tn, cp, cn in bcg:
        yi = math.log((tp / (tp + tn)) / (cp / (cp + cn)))
        vi = 1 / tp - 1 / (tp + tn) + 1 / cp - 1 / (cp + cn)
        # a cell with n = 2 and sd = sqrt(2 v) has se^2 = v exactly
        recs.append((2, yi, math.sqrt(2 * vi)))
    got = D.pool(cellish(recs))
    ck("published BCG example (metafor DL): tau2 %.4f  est %.4f  se %.4f  "
       "Q %.2f   [published 0.3088 / -0.7141 / 0.1787 / 152.23]"
       % (got["tau2"], got["mean"], got["se"], got["q_het"]),
       round(got["tau2"], 4) == 0.3088 and round(got["mean"], 4) == -0.7141
       and round(got["se"], 4) == 0.1787 and round(got["q_het"], 2) == 152.23)

    print("\n2. Behaviour")
    lv = [0.25, 0.30, 0.35, 0.28, 0.32]
    rv = [0.29, 0.36, 0.33, 0.40, 0.31]
    L = [circuit("L%d" % i, v) for i, v in enumerate(lv)]
    R = [circuit("R%d" % i, v) for i, v in enumerate(rv)]

    same = run(L, [circuit("S%d" % i, v) for i, v in enumerate(lv)])
    worst = max(abs(c["delta"]) for *_, c in cells_of(same))
    minp = min(c["p"] for *_, c in cells_of(same))
    ck("identical groups: max |delta| %.3g, min p %.6f" % (worst, minp),
       worst < 1e-12 and minp > 0.999999)

    shift = 0.1
    sh = run(L, [circuit("S%d" % i, v + shift) for i, v in enumerate(lv)])
    err = max(abs(c["delta"] - shift) for *_, c in cells_of(sh))
    t2 = max(abs(c["left"]["tau2"] - c["right"]["tau2"])
             for *_, c in cells_of(sh))
    ck("shifted copy (+0.1): max |delta - 0.1| %.3g, tau2 unchanged (%.3g)"
       % (err, t2), err < 1e-12 and t2 < 1e-12)

    base = [circuit("B%d" % i, v) for i, v in
            enumerate([0.30, 0.31, 0.29, 0.30])]
    one = circuit("X1", 0.50, usable=1)
    eight = circuit("X8", 0.50)
    key, w, m = "Right ACC|Right OFC", "pre", "coherence"

    def side_mean(ps):
        return D.pool({p["source"]["gid"]: p["cells"][w][m].get(key)
                       for p in ps})
    b0 = side_mean(base)
    b1 = side_mean(base + [one])
    b8 = side_mean(base + [eight])
    wt1 = [x for x in b1["members"] if x["member"] == "X1"][0]["weight"]
    wt8 = [x for x in b8["members"] if x["member"] == "X8"][0]["weight"]
    ck("adding an offset recording: n=1 moves the mean %.4f (weight %.3f), "
       "n=8 moves it %.4f (weight %.3f)"
       % (b1["mean"] - b0["mean"], wt1, b8["mean"] - b0["mean"], wt8),
       0 < b1["mean"] - b0["mean"] < b8["mean"] - b0["mean"] and wt1 < wt8)
    ck("the n=1 recording is used, with a borrowed-SD warning",
       b1["k"] == 5 and any("borrowed" in s for s in
                            [x for x in D.pool({"X1": one["cells"][w][m][key],
                                                "B": base[0]["cells"][w][m][key]}
                                               )["warn"]]))

    print("\n   inflated n: every pair duplicated 10x within its recording")
    # Recordings differ in spread and in usable pairs, so the weights are
    # unequal (with equal se_r, DL's v + tau2 equals the variance of the
    # means exactly and the invariance would be a special-case identity).
    scale = [0.6, 1.0, 1.4, 0.8, 1.2]
    use = [8, 6, 8, 5, 7]

    def fx(w, m, a, b):
        # a cell-specific true change on the right, so a panel's p differ
        # and BH has something to reorder
        return ((sum(ord(c) for c in a + b + m + w) * 7) % 11) / 100.0

    def grp(prefix, levels, rep, effect=None):
        return [circuit("%s%d" % (prefix, i), v, rep=rep, usable=use[i],
                        per_pair=[d * scale[i] for d in DEV8], effect=effect)
                for i, v in enumerate(levels)]
    L, R = grp("L", lv, 1), grp("R", rv, 1, fx)
    Ld, Rd = grp("L", lv, 10), grp("R", rv, 10, fx)
    a = run(L, R)
    b = run(Ld, Rd)
    print("   %-22s %8s %12s %12s %12s %12s"
          % ("cell", "delta", "nested p", "nested p x10",
             "pair-pool p", "pair-pool x10"))
    ratios_n, ratios_p = [], []
    shown = 0
    for (w_, m_, k_, c) in cells_of(a):
        cd = b["cells"][w_][m_][k_]
        _, _, pp, _, _ = pair_pooled(L, R, w_, m_, k_)
        _, _, ppd, nl, nr = pair_pooled(Ld, Rd, w_, m_, k_)
        ratios_n.append(cd["p"] / c["p"])
        ratios_p.append(ppd / pp)
        if shown < 4 and m_ == "coherence" and w_ == "pre":
            print("   %-22s %8.4f %12.4g %12.4g %12.4g %12.4g"
                  % (k_, c["delta"], c["p"], cd["p"], pp, ppd))
            shown += 1
    rn = sorted(ratios_n)[len(ratios_n) // 2]
    rp = sorted(ratios_p)[len(ratios_p) // 2]
    print("   (pairs per side: %d -> %d; median p ratio x10/x1: nested %.3f, "
          "pair-pooled %.3g)" % (sum(use), 10 * sum(use), rn, rp))
    # One-sided on purpose. Nested p may RISE with inflated n: as every
    # se_r -> 0, DL weights tend to 1/tau2 (equal), so the pooled mean moves
    # from precision-weighted towards the plain mean of recordings. What it
    # must never do is fall towards significance because pairs multiplied.
    ck("nested p is not pushed down by inflated n (median ratio %.3f >= 0.5)"
       % rn, rn >= 0.5)
    ck("nested p stays within an order of magnitude (%.3f in 0.1-10)" % rn,
       0.1 <= rn <= 10)
    ck("pair-pooling WOULD be driven by it (median ratio %.3g < 0.01) -- "
       "the reference comparator, not drift" % rp, rp < 0.01)

    print("\n   Benjamini-Hochberg")
    hand_p = [0.01, 0.04, 0.03, 0.005, 0.5]
    hand_q = [0.025, 0.05, 0.05, 0.025, 0.5]         # worked by hand
    got_q = D._bh(hand_p)
    ck("BH on %s -> %s (hand: %s)" % (hand_p, [round(q, 6) for q in got_q],
                                      hand_q),
       all(close(g, h) for g, h in zip(got_q, hand_q)))
    ck("BH passes None through and counts only real tests",
       D._bh([None, 0.02, None, 0.01]) == [None, 0.02, None, 0.02])
    qs = [(c["p"], c["q"]) for *_, c in cells_of(a)]
    ck("q >= p in every cell of a real build (%d cells)" % len(qs),
       all(q >= p - 1e-15 for p, q in qs))
    ck("... and q > p somewhere (the correction did something: %d of %d)"
       % (sum(1 for p, q in qs if q > p * (1 + 1e-9)), len(qs)),
       any(q > p * (1 + 1e-9) for p, q in qs))
    # q recomputed by hand for one panel
    panel = a["cells"]["cue1"]["raw_cc"]
    ps = [c["p"] for c in panel.values()]
    mm = len(ps)
    srt = sorted(range(mm), key=lambda i: ps[i])
    hq = [0.0] * mm
    run_min = 1.0
    for r in range(mm, 0, -1):
        run_min = min(run_min, ps[srt[r - 1]] * mm / r)
        hq[srt[r - 1]] = min(1.0, run_min)
    ck("q of panel cue1/raw_cc matches a hand BH over its %d cells" % mm,
       all(close(c["q"], h) for c, h in zip(panel.values(), hq)))

    print("\n   grey regions, absent cells, k = 1, nothing to borrow")
    Lg = [circuit("L0", 0.3, grey=["Left POR"]), circuit("L1", 0.32),
          circuit("L2", 0.28)]
    Rg = [circuit("R0", 0.35, grey=["Left POR"]), circuit("R1", 0.33,
                                                          grey=["Left POR"])]
    g = run(Lg, Rg)
    kk = "Right ACC|Left POR"
    ck("'grey' lists Left POR, with the members it was grey in (%s)"
       % ", ".join(d["member"] for d in g["grey_detail"]["Left POR"]),
       g["grey"] == ["Left POR"]
       and len(g["grey_detail"]["Left POR"]) == 3)
    ck("grey on EVERY right member: cell absent (not zero), with a reason",
       kk in g["absent"]["pre"]["coherence"]
       and "grey" in g["absent"]["pre"]["coherence"][kk],
       g["absent"]["pre"]["coherence"].get(kk))
    Rg2 = [circuit("R0", 0.35, grey=["Left POR"]), circuit("R1", 0.33)]
    g2 = run(Lg, Rg2)
    c2 = g2["cells"]["pre"]["coherence"][kk]
    ck("grey in one of two right members: k left %d, right %d, warn says so"
       % (c2["left"]["k"], c2["right"]["k"]),
       c2["left"]["k"] == 2 and c2["right"]["k"] == 1
       and any("pooled over" in s for s in c2["warn"]))

    k1 = run(L, [circuit("R0", 0.4)])
    c = k1["cells"]["pre"]["coherence"]["Right ACC|Right OFC"]
    ck("k = 1 side: tau2 %.3g, warned" % c["right"]["tau2"],
       c["right"]["tau2"] == 0.0 and c["right"]["k"] == 1
       and any("k = 1" in s for s in c["warn"]))

    thin = run(L, [circuit("R0", 0.4, usable=1), circuit("R1", 0.5, usable=1)])
    c = thin["cells"]["pre"]["coherence"]["Right ACC|Right OFC"]
    ck("no right recording has n >= 2: mean %.3f reported, p None, why given"
       % c["right"]["mean"],
       c["p"] is None and c["q"] is None and not c["testable"]
       and c["right"]["mean"] is not None
       and any("test impossible" in s for s in c["warn"]))
    ck("... and the untestable cells are left out of BH's m (%d tests)"
       % thin["panels"]["pre"]["coherence"]["tests"],
       thin["panels"]["pre"]["coherence"]["tests"] == 0)

    print("\n   refusals")

    def refused(Lx, Rx, field, lrefs=None, rrefs=None):
        ok, why = D.compatible(Lx, Rx, lrefs or refs(Lx, "a"),
                               rrefs or refs(Rx, "b"))
        hit = [s for s in why if field in s]
        return (not ok) and bool(hit), (hit or why or ["accepted"])[0]

    tests = [
        ("notch_hz across sides", L, [circuit("R0", .3,
                                               params={"notch_hz": None})],
         "notch_hz"),
        ("low within left", L[:2] + [circuit("L9", .3, params={"low": 6.0})],
         R, "low"),
        ("pad_s on state circuits", [circuit("L0", .3, params={"pad_s": 5.0})],
         R, "pad_s"),
        ("before_s on transition circuits",
         [circuit("L0", .3, kind="transition",
                  windows=["onset", "switch", "offset"],
                  params={"before_s": 0.5})],
         [circuit("R0", .3, kind="transition",
                  windows=["onset", "switch", "offset"])], "before_s"),
        ("analysis_fs", L, [circuit("R0", .3,
                                    params={"analysis_fs": 500.0})],
         "analysis_fs"),
        ("kind", L, [circuit("R0", .3, kind="transition",
                             windows=["onset", "switch", "offset"])], "kind"),
        ("cue_type", L, [circuit("R0", .3, cue_type="Click_Noise")],
         "cue_type"),
        ("windows", L, [circuit("R0", .3, windows=["pre", "cue1"])],
         "windows"),
        ("methods", L, [circuit("R0", .3, methods=["coherence"])], "methods"),
        ("empty side", [], R, "empty"),
    ]
    for name, Lx, Rx, field in tests:
        ok, s = refused(Lx, Rx, field)
        ck("refuses %s: %s" % (name, s), ok)
    ok, s = refused(L, R, "both sides", refs(L, "a"), refs(R, "a"))
    ck("refuses the same (artifact, version) on both sides: %s" % s, ok)
    ok, s = refused(L + [L[0]], R, "more than once")
    ck("refuses one recording twice in a side: %s" % s, ok)
    ok, _ = D.compatible(L, R, refs(L, "a"), refs(R, "b"))
    ck("accepts a compatible pair of groups", ok)

    print("\n   parameters are compared only where the kind reads them")
    # Spark writes before/after as None on a state entry; a state circuit
    # never reads them, so a difference there must not refuse.
    st_none = [circuit("L0", .3, params={"before_s": None, "after_s": None})]
    st_set = [circuit("R0", .3, params={"before_s": 1.0, "after_s": 2.0})]
    ok, why = D.compatible(st_none, st_set, refs(st_none, "a"),
                           refs(st_set, "b"))
    ck("state: before/after None vs 1/2 is ACCEPTED (not read by state)",
       ok, "; ".join(why))
    tw = ["onset", "switch", "offset"]
    tr_a = [circuit("L0", .3, kind="transition", windows=tw,
                    params={"pad_s": 10.0})]
    tr_b = [circuit("R0", .3, kind="transition", windows=tw,
                    params={"pad_s": None})]
    ok, why = D.compatible(tr_a, tr_b, refs(tr_a, "a"), refs(tr_b, "b"))
    ck("transition: pad_s 10 vs None is ACCEPTED (not read by transition)",
       ok, "; ".join(why))
    b1 = safe_build(st_none, st_set, refs(st_none, "a"), refs(st_set, "b"))
    ck("a state drift's params carry pad_s and not before/after",
       b1 is not None and "pad_s" in b1["params"]
       and "before_s" not in b1["params"]
       and "after_s" not in b1["params"], b1 and sorted(b1["params"]))

    print("\n   pinned by version_id")
    one = [circuit("L0", .3)]
    two = [circuit("R0", .3)]
    ra = [{"artifact_id": "X", "version": 2, "version_id": "vidA",
           "digest": "d1", "name": "L0"}]
    rb = [{"artifact_id": "X", "version": 3, "version_id": "vidA",
           "digest": "d1", "name": "R0"}]
    ok, why = D.compatible(one, two, ra, rb)
    ck("the same version_id on both sides is refused even when the numbers "
       "differ (numbers clash across machines): %s"
       % ((why or ["accepted"])[0]), not ok and any("both sides" in s
                                                   for s in why))
    rc = [{"artifact_id": "X", "version": 2, "version_id": "vidB",
           "digest": "d2", "name": "R0"}]
    ok, why = D.compatible(one, two, ra, rc)
    ck("the same number with a different version_id is two versions, "
       "not a duplicate", ok, "; ".join(why))
    b2 = safe_build(one, two, ra, rc)
    ck("members carry version_id", b2 is not None
       and b2["left"]["members"][0]["version_id"]
       == "vidA" and b2["right"]["members"][0]["version_id"] == "vidB")

    print("\n   cue types are counterbalanced: refuse, or a recorded choice")
    cl = [circuit("L%d" % i, .3, cue_type="Click_HighTone") for i in range(2)]
    for c_ in cl:
        c_["cue_label"] = "Click → High tone"
    cr = [circuit("R%d" % i, .3, cue_type="HighTone_Noise") for i in range(2)]
    for c_ in cr:
        c_["cue_label"] = "High tone → Noise"
    ok, why = D.compatible(cl, cr, refs(cl, "a"), refs(cr, "b"))
    s = next((x for x in why if "cue_type" in x), "")
    ck("different pairings are refused with a sentence naming both",
       not ok and "Click → High tone" in s and "High tone → Noise" in s, s)
    eq = [{"from": "HighTone_Noise", "to": "Click_HighTone",
           "by": "harness", "at": "2026-09-28T00:00:00+00:00"},
          {"from": "LowTone_Click", "to": "Noise_LowTone", "by": "h",
           "at": "x"}]
    ok, why = D.compatible(cl, cr, refs(cl, "a"), refs(cr, "b"), eq)
    ck("with the equivalence recorded, they are compared", ok, "; ".join(why))
    be = D.build(cl, cr, refs(cl, "a"), refs(cr, "b"), ("l", "r"),
                 cue_equivalence=eq)
    ck("the payload records the choice (from/to sorted, by, at) and only "
       "the one that was used: %s" % be["cue_equivalence"],
       be["cue_equivalence"] == [{"from": "Click_HighTone",
                                  "to": "HighTone_Noise", "by": "harness",
                                  "at": "2026-09-28T00:00:00+00:00"}])
    ck("and names both pairings: cue_types %s, label %r"
       % (be["cue_types"], be["cue_label"]),
       be["cue_types"] == ["Click_HighTone", "HighTone_Noise"]
       and "≡" in be["cue_label"])
    ck("an equivalence is transitive (A=B, B=C joins A and C)",
       len(set(D.cue_classes([{"from": "A", "to": "B"},
                              {"from": "B", "to": "C"}]).values())) == 1)
    try:
        D.build(cl, cr, refs(cl, "a"), refs(cr, "b"), ("l", "r"),
                cue_equivalence=[{"from": "Click_HighTone"}])
        ck("a malformed equivalence is refused", False)
    except D.DriftError as e:
        ck("a malformed equivalence is refused: %s" % e, True)

    print("\n   the weaknesses are said, not hidden")
    k1 = D.build(L, [circuit("R0", .4)], refs(L, "a"), refs([R[0]], "b"),
                 ("l", "r"))
    ck("a k = 1 side is flagged (right.one_recording) and said at the top",
       k1["right"]["one_recording"] and not k1["left"]["one_recording"]
       and any(D.K1_SAY in s for s in k1["warn"]))
    c = k1["cells"]["pre"]["coherence"]["Right ACC|Right OFC"]
    ck("  and on every cell, in those words",
       any(D.K1_SAY in s for s in c["warn"]))
    ck("the z-test note is on the result", D.Z_NOTE in k1["notes"])
    ck("the test is named on the result (%s)" % k1["test"],
       k1["test"]["name"] == "z_test")

    def half(lp, rp):
        return {"se": 1.0, "stat": 0.0, "p": 0.5}
    half.label = "constant"
    sw = D.build(L, R, refs(L, "a"), refs(R, "b"), ("l", "r"), test=half)
    ck("the test is one swappable function: every p is the stand-in's 0.5",
       all(c["p"] == 0.5 for *_, c in cells_of(sw))
       and sw["test"]["name"] == "half")
    seen_prog = []
    D.build(L, R, refs(L, "a"), refs(R, "b"), ("l", "r"),
            progress=lambda d, o: seen_prog.append((d, o)))
    ck("progress reports each panel, ending at the total (%s)"
       % (seen_prog[-1:],),
       len(seen_prog) == 12 and seen_prog[-1][0] == seen_prog[-1][1])
    sm = D.summary(a)
    ck("summary counts the groups and the tests (%s)" % sm,
       sm["left_k"] == 5 and sm["right_k"] == 5 and sm["tests"] > 0)
    try:
        D.build(L, [circuit("R0", .3, params={"notch_hz": None})],
                refs(L, "a"), [None], ("l", "r"))
        ck("build raises DriftError when refused", False)
    except D.DriftError as e:
        ck("build raises DriftError when refused", "notch_hz" in str(e))

    try:
        s = json.dumps(a, allow_nan=False)
        ck("payload is strict JSON (%d kB, %d cells)"
           % (len(s) // 1024, sum(1 for _ in cells_of(a))), True)
        s = json.dumps(thin, allow_nan=False)
        ck("untestable payload is strict JSON", True)
    except ValueError as e:
        ck("payload is strict JSON", False, str(e))

    try:
        within_rat_checks()
    except Exception as exc:                             # noqa: BLE001
        import traceback
        traceback.print_exc()
        ck("section 4 CRASHED: %s" % exc, False)

    print()
    if FAILED:
        print("FAILED %d: %s" % (len(FAILED), "; ".join(FAILED)))
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
