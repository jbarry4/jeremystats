# -*- coding: utf-8 -*-
"""Section 7 of the Monolith page: narrowing down (the lab, 2026-10-08).

Every p on the page is uncorrected, by the lab's choice: one test per entry,
DerSimonian-Laird pooling of each rat's own Precon4 - Precon1 change and a
Hartung-Knapp t on k - 1 degrees of freedom. This module shows what the
corrections would do, and runs tests that make fewer assumptions -- without
changing anything else on the page.

The relabelling. Under "nothing changed", a rat's change is as likely to
have come out with the other sign: so every way of flipping the eight rats'
signs (2^7 = 128, the first rat fixed: flipping all gives the same answer)
is as likely as the real one. Each flip is pooled exactly as the Monolith
pools, at every entry at once, which keeps how the entries move together.
From the same 128:

  perm_p      each entry's exact permutation p: the share of flips whose
              |t| is at least the real one's (the smallest possible 1/128)
  max-t       family-wise: an entry survives where its |t| beats the largest
              |t| anywhere in the family in all but 5% of the flips
              (Westfall & Young 1993)
  clusters    runs of neighbouring 1 Hz bands (same window, measure, pair)
              that pass p < .05 the same way, weighed by their summed |t|,
              against the heaviest run anywhere in each flip (Maris &
              Oostenveld 2007)
  global      how many entries pass p < .05 in each flip: is the real count
              beyond what relabelling the same rats gives?
  replication the same flips applied to each rat's AB and CD: how many
              entries pass in both pairs, the same way

and, from the entries' p alone: Bonferroni, Holm, Benjamini-Hochberg and
Benjamini-Yekutieli; and the exact sign test of how many rats went up.
"""
from __future__ import annotations

import os
import time

import numpy as np

from . import monolith as MO

#: The quantities of narrow_<layer>.f32, in order.
NQ = ("hk_p", "perm_p", "sign_p", "bh_q", "by_q", "holm_p", "maxt_p",
      "cluster_p", "rep", "est")
#: The core family, chosen before looking: the two cue windows, the named
#: bands, one measure from each kind (spectral, correlation, phase lag,
#: direction).
CORE_MEASURES = ("coherence", "env_cc", "wpli", "gc_net")
STATE = ("pre", "cue1", "cue2", "post")
CUE = ("cue1", "cue2")
FAMILIES = (
    ("all", "Every stat test the Monolith runs"),
    ("named", "The named bands only (delta, theta, beta, low gamma)"),
    ("states_named", "The four state windows × the named bands"),
    ("core", "Cue 1 and Cue 2 × the named bands × coherence, envelope cc, wPLI, Granger net"),
)
ALPHA = 0.05


class SignPool(object):
    """MO.pool's Hartung-Knapp t, for many signings of the same rats: what
    does not depend on the signs is worked out once."""

    def __init__(self, Y, V):
        Y = np.asarray(Y, dtype=np.float64)
        V = np.asarray(V, dtype=np.float64)
        self.present = np.isfinite(Y)
        self.k = self.present.sum(axis=0)
        vnone = (self.present & ~np.isfinite(V)).any(axis=0)
        vzero = (self.present & np.isfinite(V) & (V == 0)).any(axis=0)
        self.y = np.where(self.present, Y, 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.Vs = np.where(self.present & np.isfinite(V) & (V > 0), V, np.inf)
            self.w = np.where(self.present, 1.0 / self.Vs, 0.0)
            self.sw = self.w.sum(axis=0)
            self.c = self.sw - (self.w * self.w).sum(axis=0) / self.sw
        self.ok0 = ~vnone & ~vzero & (self.k >= MO.MIN_RATS) & (self.k >= 2)
        self.km1 = np.maximum(self.k - 1, 1)

    def t(self, s=None):
        y = self.y if s is None else self.y * np.asarray(s, dtype=np.float64).reshape(
            (-1,) + (1,) * (self.y.ndim - 1))
        with np.errstate(invalid="ignore", divide="ignore"):
            yfe = (self.w * y).sum(axis=0) / self.sw
            q = (self.w * (y - yfe) ** 2).sum(axis=0)
            tau2 = np.where((self.k >= 2) & (self.c > 0),
                            np.maximum(0.0, (q - (self.k - 1)) / self.c), 0.0)
            wr = np.where(self.present, 1.0 / (self.Vs + tau2), 0.0)
            swr = wr.sum(axis=0)
            est = (wr * y).sum(axis=0) / swr
            var = (wr * (y - est) ** 2).sum(axis=0) / (self.km1 * swr)
            t = est / np.sqrt(var)
        return np.where(self.ok0 & np.isfinite(var) & (var > 0), t, np.nan)


def signings(n):
    """Every way of signing n rats, the first fixed at +1: (2^(n-1), n)."""
    rows = []
    for bits in range(2 ** max(n - 1, 0)):
        rows.append([1.0] + [(-1.0 if (bits >> j) & 1 else 1.0) for j in range(n - 1)])
    return np.array(rows)


def adjust(p):
    """Holm, Benjamini-Hochberg and Benjamini-Yekutieli adjusted p for a
    1-D array of p (the tested entries of one family)."""
    m = p.size
    if not m:
        return p, p, p
    o = np.argsort(p)
    ps = p[o]
    i = np.arange(1, m + 1)
    holm = np.minimum(1.0, np.maximum.accumulate((m - i + 1) * ps))
    bh = np.minimum(1.0, np.minimum.accumulate((ps * m / i)[::-1])[::-1])
    by = np.minimum(1.0, bh * np.sum(1.0 / i))
    out = [np.empty(m) for _ in range(3)]
    for a, b in zip(out, (holm, bh, by)):
        a[o] = b
    return tuple(out)


def clusters(t, tcrit, hz_idx):
    """Runs of neighbouring 1 Hz bands passing p < .05 the same way, in an
    array (windows, bands, measures, pairs): (labels, masses), labels in the
    1 Hz bands' layout (windows, measures, pairs, bands), 0 off any run."""
    tt = np.moveaxis(t[:, hz_idx], 1, -1)            # (W, M, P, B1)
    tc = np.moveaxis(tcrit[:, hz_idx], 1, -1)
    with np.errstate(invalid="ignore"):
        sig = np.isfinite(tt) & (np.abs(tt) > tc)
    sgn = np.sign(np.where(sig, tt, 0.0))
    prev_sig = np.zeros_like(sig)
    prev_sig[..., 1:] = sig[..., :-1]
    prev_sgn = np.zeros_like(sgn)
    prev_sgn[..., 1:] = sgn[..., :-1]
    start = sig & ~(prev_sig & (prev_sgn == sgn))
    lab = np.cumsum(start.ravel()).reshape(sig.shape) * sig
    mass = np.bincount(lab.ravel(), weights=np.where(sig, np.abs(tt), 0.0).ravel())
    return lab, mass


def _counts(p, mask):
    q = p[mask]
    q = q[np.isfinite(q)]
    return int(q.size), int((q < ALPHA).sum())


def family_masks(summary, shape, nwin):
    """{family: boolean mask over the measured windows' entries}."""
    W, B, M, P = shape
    wins = list(MO.WINDOWS)[:nwin]
    bands = summary["bands"]
    meths = [m["id"] for m in summary["methods"]]
    named = np.array([bool(b.get("named")) for b in bands])
    st = np.array([w in STATE for w in wins])
    cue = np.array([w in CUE for w in wins])
    core_m = np.array([m in CORE_MEASURES for m in meths])
    full = np.ones((nwin, B, M, P), bool)
    return {
        "all": full,
        "named": full & named[None, :, None, None],
        "states_named": full & st[:, None, None, None] & named[None, :, None, None],
        "core": full & cue[:, None, None, None] & named[None, :, None, None] & core_m[None, None, :, None],
    }


def funnel(st, o, nwin):
    """The steps, each keeping only what passed the one before: p < .05;
    in both pairs the same way; in both layers; in a run of frequencies that
    survives; Benjamini-Hochberg. `st` this layer's arrays, `o` the other
    layer's {p, est} (or None)."""
    mon = np.s_[:nwin]
    p_ = np.asarray(st["hk_p"])[mon]
    with np.errstate(invalid="ignore"):
        s1 = np.isfinite(p_) & (p_ < ALPHA)
        s2 = s1 & (np.asarray(st["rep"])[mon] == 1)
        s3 = (s2 & (np.asarray(o["p"])[mon] < ALPHA) & (np.sign(np.asarray(o["est"])[mon]) == np.sign(np.asarray(st["est"])[mon]))
              if o is not None else s2 & False)
        s4 = s3 & (np.asarray(st["cluster_p"])[mon] < ALPHA)
        s5 = s3 & (np.asarray(st["bh_q"])[mon] < ALPHA)
    return [{"id": "tested", "n": int(np.isfinite(p_).sum())}, {"id": "p05", "n": int(s1.sum())},
            {"id": "replicated", "n": int(s2.sum())}, {"id": "layers", "n": int(s3.sum())},
            {"id": "cluster", "n": int(s4.sum())}, {"id": "bh", "n": int(s5.sum())}]


def narrow_build(man, summary, out_dir, roles=None, progress=None, check=None):
    """Section 7: what correcting does, and the tests that assume less.
    Writes narrow_<layer>.f32 (NQ, the edges' shape) and narrow.json."""
    from scipy.stats import binom, t as tdist
    say = progress or (lambda *a: None)
    t_start = time.time()
    nwin = len(MO.WINDOWS)
    say("narrow", 0, 5, "each rat's change")
    whole = MO.rat_changes(out_dir, man)
    halves = {}
    if roles:
        halves = {g: MO.rat_changes(out_dir, man, keep=MO.split_keep(g, roles)) for g in ("ab", "cd")}
    bands = summary["bands"]
    hz_idx = [i for i, b in sorted(enumerate(bands), key=lambda x: (x[1].get("hz") or 0))
              if not b.get("named")]
    hz_of = {i: bands[i].get("hz") for i in hz_idx}
    names, pairs = summary["regions"], summary["pairs"]
    out = {"at": MO.now_iso(), "alpha": ALPHA, "families": [{"id": f, "label": l} for f, l in FAMILIES],
           "counts": {}, "global": {}, "cluster": {}, "replication": {}, "funnel": {}, "leads": {},
           "maxt": {}, "files": {}, "how": {}, "contrast": {}}
    obs = {}
    for li, layer in enumerate(MO.LAYERS):
        if layer not in whole:
            continue
        if check:
            check()
        say("narrow", 1 + 2 * li, 5, "%s · the shuffles" % layer)
        rats, Y, V = whole[layer]
        n = len(rats)
        shape = Y.shape[1:]                            # (W+1, B, M, P)
        sp = SignPool(Y, V)
        g0 = MO.pool(Y, V)
        t_obs = sp.t()
        p_obs = np.asarray(g0["p"])
        k = sp.k
        with np.errstate(invalid="ignore"):
            tcrit = np.where(k >= 2, tdist.ppf(1 - ALPHA / 2, np.maximum(k - 1, 1)), np.nan)
        S = signings(n)
        fam = family_masks(summary, (nwin,) + shape[1:], nwin)
        absobs = np.abs(t_obs)
        cge = np.zeros(shape)
        maxt = {f: [] for f in fam}
        maxt_c = []
        c05 = {f: [] for f in fam}
        c05_c = []
        cmax, cmax_c = [], []
        # The two halves, signed the same way (a rat's sign is the rat's).
        rep_null = []
        hsp = {}
        if layer == "raw" and halves.get("ab", {}).get(layer) and halves.get("cd", {}).get(layer):
            for g in ("ab", "cd"):
                rr, Yh, Vh = halves[g][layer]
                hsp[g] = (rr, SignPool(Yh, Vh))
        for si, s in enumerate(S):
            if check and si % 8 == 0:
                check()
            ts = t_obs if si == 0 else sp.t(s)
            a = np.abs(ts)
            with np.errstate(invalid="ignore"):
                cge += np.where(np.isfinite(a) & np.isfinite(absobs), a >= absobs - 1e-9, False)
                sig = a > tcrit
            mon, con = ts[:nwin], ts[nwin]
            for f, mk in fam.items():
                v = np.abs(mon[mk])
                maxt[f].append(float(np.nanmax(v)) if np.isfinite(v).any() else 0.0)
                c05[f].append(int((sig[:nwin] & mk).sum()))
            vc = np.abs(con)
            maxt_c.append(float(np.nanmax(vc)) if np.isfinite(vc).any() else 0.0)
            c05_c.append(int(sig[nwin].sum()))
            _l, m_ = clusters(mon, tcrit[:nwin], hz_idx)
            cmax.append(float(m_[1:].max()) if m_.size > 1 else 0.0)
            _l, m_ = clusters(con[None], tcrit[nwin][None], hz_idx)
            cmax_c.append(float(m_[1:].max()) if m_.size > 1 else 0.0)
            if hsp:
                tt = {}
                for g, (rr, spg) in hsp.items():
                    tt[g] = spg.t(np.array([s[rats.index(r)] for r in rr]))
                with np.errstate(invalid="ignore"):
                    ok = (np.abs(tt["ab"]) > tcrit) & (np.abs(tt["cd"]) > tcrit) & (np.sign(tt["ab"]) == np.sign(tt["cd"]))
                rep_null.append(int(ok[:nwin].sum()))
        nS = len(S)
        perm_p = np.where(np.isfinite(absobs), cge / nS, np.nan)
        # The sign test: how many of the rats went up, exactly.
        with np.errstate(invalid="ignore"):
            npos = (Y > 0).sum(axis=0)
            nneg = (Y < 0).sum(axis=0)
        mm = npos + nneg
        sign_p = np.where(np.isfinite(p_obs) & (mm > 0),
                          np.minimum(1.0, 2.0 * binom.cdf(np.minimum(npos, nneg), np.maximum(mm, 1), 0.5)), np.nan)
        # Corrections from the p alone, over each family's tested entries;
        # the contrast is a family of its own.
        holm = np.full(shape, np.nan)
        bh = np.full(shape, np.nan)
        by = np.full(shape, np.nan)
        for sl in (np.s_[:nwin], np.s_[nwin:nwin + 1]):
            sub = p_obs[sl]
            ok = np.isfinite(sub)
            h_, b_, y_ = adjust(sub[ok])
            for arr, v in ((holm, h_), (bh, b_), (by, y_)):
                part = np.full(sub.shape, np.nan)
                part[ok] = v
                arr[sl] = part
        # max-t: the share of signings whose largest |t| in the family is at
        # least this entry's.
        maxt_p = np.full(shape, np.nan)
        mt = np.sort(np.array(maxt["all"]))
        maxt_p[:nwin] = np.where(np.isfinite(absobs[:nwin]),
                                 (nS - np.searchsorted(mt, absobs[:nwin] - 1e-9, side="left")) / nS, np.nan)
        mtc = np.sort(np.array(maxt_c))
        maxt_p[nwin] = np.where(np.isfinite(absobs[nwin]),
                                (nS - np.searchsorted(mtc, absobs[nwin] - 1e-9, side="left")) / nS, np.nan)
        # Clusters, real: each one's p against the heaviest run in each flip.
        cluster_p = np.full(shape, np.nan)
        cl_out = {}
        for fid, sl, tsl, tcsl, nullm in (("monolith", np.s_[:nwin], t_obs[:nwin], tcrit[:nwin], cmax),
                                           ("contrast", np.s_[nwin:nwin + 1], t_obs[nwin][None], tcrit[nwin][None], cmax_c)):
            lab, mass = clusters(tsl, tcsl, hz_idx)
            nm = np.sort(np.array(nullm))
            cp = (nS - np.searchsorted(nm, mass - 1e-9, side="left")) / nS
            cp[0] = np.nan
            cell = np.where(lab > 0, cp[lab], np.nan)            # (W, M, P, B1)
            back = np.full(tsl.shape, np.nan)
            back[:, hz_idx] = np.moveaxis(cell, -1, 1)
            cluster_p[sl] = back
            # The heaviest runs, said.
            top = []
            ids = np.argsort(-mass)
            Wl = tsl.shape[0]
            for cid in ids[:40]:
                if cid == 0 or mass[cid] <= 0:
                    continue
                where = np.argwhere(lab == cid)
                w_, m_, p_ = (int(x) for x in where[0][:3])
                bb = [hz_idx[int(x)] for x in where[:, 3]]
                top.append({"w": MO.WINDOWS[w_] if fid == "monolith" else "c21", "wi": w_ if fid == "monolith" else nwin,
                            "m": MO.METHODS[m_], "mi": m_, "pair": p_,
                            "a": names[pairs[p_][0]], "b": names[pairs[p_][1]],
                            "from_hz": hz_of[bb[0]], "to_hz": hz_of[bb[-1]], "n_bands": len(bb),
                            "mass": float(mass[cid]), "p": float(cp[cid]),
                            "sign": int(np.sign(tsl[(w_,) + (bb[0], m_, p_)]))})
                if len(top) >= 20:
                    break
            sig_ids = np.nonzero(cp < ALPHA)[0] if mass.size > 1 else []
            cl_out[fid] = {"n": int(mass.size - 1), "n_sig": int(len(sig_ids)),
                           "cells_sig": int((np.where(np.isfinite(cell), cell, 1.0) < ALPHA).sum()),
                           "threshold_mass": float(nm[int(np.ceil((1 - ALPHA) * nS)) - 1]) if nS else None,
                           "top": top}
        # Replication across the two pairs, per entry.
        rep = np.full(shape, np.nan)
        rep_obs = None
        if halves.get("ab", {}).get(layer) and halves.get("cd", {}).get(layer):
            ga = MO.pool(*halves["ab"][layer][1:])
            gc = MO.pool(*halves["cd"][layer][1:])
            pa, pc = np.asarray(ga["p"]), np.asarray(gc["p"])
            both = np.isfinite(pa) & np.isfinite(pc)
            with np.errstate(invalid="ignore"):
                r_ = both & (pa < ALPHA) & (pc < ALPHA) & (np.sign(ga["est"]) == np.sign(gc["est"]))
            rep = np.where(both, r_.astype(np.float64), np.nan)
            rep_obs = {"observed": int(np.nansum(rep[:nwin])), "tested_both": int(both[:nwin].sum()),
                       "expected_independent": round(float(both[:nwin].sum()) * ALPHA * ALPHA / 2.0, 1),
                       "ab_p": pa, "cd_p": pc, "ab_est": np.asarray(ga["est"]), "cd_est": np.asarray(gc["est"])}
        est = np.asarray(g0["est"])
        stack = {"hk_p": p_obs, "perm_p": perm_p, "sign_p": sign_p, "bh_q": bh, "by_q": by, "holm_p": holm,
                 "maxt_p": maxt_p, "cluster_p": cluster_p, "rep": rep, "est": est}
        A = np.stack([np.asarray(stack[q], dtype=np.float32).reshape(shape) for q in NQ])
        fname = "narrow_%s.f32" % layer
        tmp = os.path.join(out_dir, fname + ".part")
        A.tofile(tmp)
        os.replace(tmp, os.path.join(out_dir, fname))
        out["files"][fname] = {"shape": list(A.shape), "quantities": list(NQ)}
        obs[layer] = {"p": p_obs, "est": est, "t": t_obs}
        # What survives, family by family.
        cnt = {}
        for f, mk in fam.items():
            m_, unc = _counts(p_obs[:nwin], mk)
            sub = p_obs[:nwin][mk]
            okp = np.isfinite(sub)
            h_, b_, y_ = adjust(sub[okp])
            mtf = np.sort(np.array(maxt[f]))
            ao = absobs[:nwin][mk][okp]
            mtp = (nS - np.searchsorted(mtf, ao - 1e-9, side="left")) / nS
            pp = perm_p[:nwin][mk][okp]
            c = {"m": m_, "uncorrected": unc, "chance": round(ALPHA * m_, 1),
                 "bonferroni": int((sub[okp] < ALPHA / max(m_, 1)).sum()),
                 "bonferroni_p": ALPHA / max(m_, 1),
                 "holm": int((h_ < ALPHA).sum()), "bh": int((b_ < ALPHA).sum()), "by": int((y_ < ALPHA).sum()),
                 "bh_p": float(sub[okp][b_ < ALPHA].max()) if (b_ < ALPHA).any() else None,
                 "maxt": int((mtp <= ALPHA).sum()),
                 "maxt_t": float(mtf[int(np.ceil((1 - ALPHA) * nS)) - 1]),
                 "perm": int((pp < ALPHA).sum()),
                 "perm_bh": int((adjust(pp)[1] < ALPHA).sum()) if pp.size else 0,
                 "sign": int((sign_p[:nwin][mk] < ALPHA).sum())}
            if f == "all":
                c["cluster_cells"] = cl_out["monolith"]["cells_sig"]
                c["clusters"] = cl_out["monolith"]["n_sig"]
                if rep_obs:
                    c["replicated"] = rep_obs["observed"]
            cnt[f] = c
            co = c05[f]
            out["global"].setdefault(f, {})[layer] = {"counts": co, "observed": co[0], "n": nS,
                                                      "rank": MO._rank(co, co[0]), "expected": round(ALPHA * m_, 1)}
        for f, c in cnt.items():
            out["counts"].setdefault(f, {})[layer] = c
        out["maxt"][layer] = {f: sorted(v)[-int(np.ceil(ALPHA * nS)):] for f, v in maxt.items()}
        out["cluster"][layer] = cl_out["monolith"]
        if layer == "raw":
            # The contrast, its own family, raw only.
            pc_ = p_obs[nwin]
            okc = np.isfinite(pc_)
            h_, b_, y_ = adjust(pc_[okc])
            mtp = (nS - np.searchsorted(mtc, absobs[nwin][okc] - 1e-9, side="left")) / nS
            pp = perm_p[nwin][okc]
            m_ = int(okc.sum())
            out["contrast"] = {
                "counts": {"m": m_, "uncorrected": int((pc_[okc] < ALPHA).sum()), "chance": round(ALPHA * m_, 1),
                           "bonferroni": int((pc_[okc] < ALPHA / max(m_, 1)).sum()), "bonferroni_p": ALPHA / max(m_, 1),
                           "holm": int((h_ < ALPHA).sum()), "bh": int((b_ < ALPHA).sum()), "by": int((y_ < ALPHA).sum()),
                           "maxt": int((mtp <= ALPHA).sum()), "maxt_t": float(mtc[int(np.ceil((1 - ALPHA) * nS)) - 1]),
                           "perm": int((pp < ALPHA).sum()), "perm_bh": int((adjust(pp)[1] < ALPHA).sum()) if pp.size else 0,
                           "sign": int((sign_p[nwin][okc] < ALPHA).sum()),
                           "cluster_cells": cl_out["contrast"]["cells_sig"], "clusters": cl_out["contrast"]["n_sig"]},
                "global": {"counts": c05_c, "observed": c05_c[0], "n": nS, "rank": MO._rank(c05_c, c05_c[0]),
                           "expected": round(ALPHA * m_, 1)},
                "cluster": cl_out["contrast"]}
            if rep_null:
                out["replication"] = {"observed": rep_obs["observed"], "tested_both": rep_obs["tested_both"],
                                      "expected_independent": rep_obs["expected_independent"],
                                      "counts": rep_null, "n": len(rep_null), "rank": MO._rank(rep_null, rep_null[0])}
        obs[layer]["rep"] = rep_obs
        obs[layer]["arrays"] = stack
    # The funnel and the leads need both layers.
    say("narrow", 5, 5, "the top results")
    other = {"raw": "minus_fp", "minus_fp": "raw"}
    for layer in obs:
        st = obs[layer]["arrays"]
        o = obs.get(other[layer])
        out["funnel"][layer] = funnel(st, o, nwin)
        tops = [("monolith", (summary.get("top") or {}).get(layer) or [])]
        if layer == "raw":
            tops.append(("contrast", ((summary.get("contrast") or {}).get("top") or {}).get("raw") or []))
        for kind, lst in tops:
            rows = []
            for t0 in lst[:50]:
                at = (t0["wi"], t0["bi"], t0["mi"], t0["pair"])
                v = {q: MO._f(np.asarray(st[q])[at]) for q in NQ}
                cl = None
                if v["cluster_p"] is not None:
                    # The run this entry belongs to: its 1 Hz neighbours that
                    # carry the same cluster p and sign.
                    w_, b_, m_, pp_ = at
                    row = np.asarray(st["cluster_p"])[w_, :, m_, pp_]
                    sg = np.sign(np.asarray(st["est"])[w_, :, m_, pp_])
                    pos = hz_idx.index(b_) if b_ in hz_idx else None
                    if pos is not None:
                        lo = hi = pos
                        while lo > 0 and row[hz_idx[lo - 1]] == row[b_] and sg[hz_idx[lo - 1]] == sg[b_]:
                            lo -= 1
                        while hi < len(hz_idx) - 1 and row[hz_idx[hi + 1]] == row[b_] and sg[hz_idx[hi + 1]] == sg[b_]:
                            hi += 1
                        cl = {"p": v["cluster_p"], "from_hz": hz_of[hz_idx[lo]], "to_hz": hz_of[hz_idx[hi]], "n_bands": hi - lo + 1}
                r = obs[layer]["rep"]
                rows.append({"w": t0["w"], "wi": t0["wi"], "band": t0["band"], "bi": t0["bi"], "hz": t0.get("hz"),
                             "m": t0["m"], "mi": t0["mi"], "pair": t0["pair"], "a": t0["a"], "b": t0["b"],
                             "est": t0["est"], "p": t0["p"], "k": t0["k"], "same": t0["same"],
                             "perm_p": v["perm_p"], "sign_p": v["sign_p"], "bh_q": v["bh_q"], "by_q": v["by_q"],
                             "holm_p": v["holm_p"], "maxt_p": v["maxt_p"], "cluster": cl,
                             "rep": None if not r else {"ab_p": MO._f(r["ab_p"][at]), "cd_p": MO._f(r["cd_p"][at]),
                                                        "ab_est": MO._f(r["ab_est"][at]), "cd_est": MO._f(r["cd_est"][at]),
                                                        "replicated": v["rep"] == 1.0},
                             "other": None if o is None or kind == "contrast" else {
                                 "layer": other[layer], "p": MO._f(o["p"][at]), "est": MO._f(o["est"][at])}})
            out["leads"].setdefault(kind, {})[layer] = rows
    # How the p were made, from the first lead's own numbers.
    t0 = ((summary.get("top") or {}).get("raw") or [None])[0]
    if t0 is not None:
        out["how"] = {"lead": {k_: t0.get(k_) for k_ in ("w", "band", "hz", "m", "pair", "a", "b", "est", "se", "p", "k", "same")}}
    out["n_signings"] = len(signings(len(whole[next(iter(whole))][0]))) if whole else 0
    out["rats"] = whole[next(iter(whole))][0] if whole else []
    out["entries"] = {"monolith": int(np.isfinite(obs["raw"]["p"][:nwin]).sum()) if "raw" in obs else 0}
    out["seconds"] = round(time.time() - t_start, 1)
    MO._write_json(os.path.join(out_dir, "narrow.json"), out)
    summary["narrow"] = {"at": out["at"], "files": out["files"]}
    MO._write_json(os.path.join(out_dir, "summary.json"), summary)
    say("narrow", 5, 5, "done")
    return out


def narrow_work(worker):
    """Section 7 for the built Monolith, here, from the day arrays already
    fetched. A few minutes; nothing is fetched or run."""
    d = MO.data_dir()
    summ = MO.summary_now()
    man = MO._read_json(MO._path("manifest.json"))
    if not d or not summ or not man:
        raise MO.MonolithError("The Monolith has not been built yet.", 409)
    roles = MO.split_role_map(summ) if (summ.get("splits") or {}).get("files") else None
    worker.note(phase="narrow")
    got = narrow_build(man, summ, d, roles,
                       progress=lambda what, i, of, item: worker.note(phase="narrow", i=i, of=of, item=item),
                       check=worker.check)
    return {"at": got["at"], "seconds": got["seconds"]}
