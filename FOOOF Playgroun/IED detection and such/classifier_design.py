# -*- coding: utf-8 -*-
"""Designing the waveform-across-depth classifier, on the labels alone.

The question the user asked of every unreviewed candidate: does it look like
the IEDs a person confirmed on this recording, across the depth of the
probe? Before that is trusted on 2,760 unreviewed candidates it has to
separate the LABELLED ones -- Solid from Garbage -- and this measures how
well each variant does.

It works on the hand-sorted stamps directly, so it does not depend on any
detector setting. Only a short segment around each stamp is read and
filtered, which is what makes it fast enough to compare variants.

Variants compared
  band     1-30, 1-70 (the IED preset), 3-100, low-pass 300 Hz
  ref      as recorded, or common-average referenced
  align    on the largest deflection, or iteratively onto the template
  score    space-time correlation over every good channel, or the depth
           profile alone (each channel's value at the aligned moment)

Scored by the AUC of Solid (leave-one-out) against Garbage, per recording
and pooled, and by how much Garbage a threshold that keeps EVERY Solid
lets through.

    python classifier_design.py
"""
import json
import os
from collections import defaultdict

import numpy as np

import ied_common as C
from step3_sweep import chan_rows

HALF_SEG = 1.5          # seconds read either side, so filter edges fall off
PRE, POST = 0.200, 0.300
CMP_PRE, CMP_POST = 0.100, 0.200
LAG = 0.025
SEARCH = 0.060          # where the true peak may be relative to the stamp

BANDS = {"1-30": (1, 30), "1-70": (1, 70), "3-100": (3, 100),
         "lp300": (None, 300)}


def segs(X, times, rows):
    out = []
    h = int(HALF_SEG * C.FS)
    for t in times:
        i = int(round(t * C.FS))
        if i - h < 0 or i + h > X.shape[1]:
            out.append(None)
            continue
        out.append(np.asarray(X[:, i - h:i + h], dtype=np.float64))
    return out


def prep(seg, band, car_rows):
    x = seg
    if car_rows is not None:
        x = x - x[car_rows].mean(axis=0, keepdims=True)
    x = C.notch(x)
    lo, hi = band
    return C.band(x, lo, hi)


def cut(y, centre_i, rows):
    a = centre_i - int(PRE * C.FS)
    b = centre_i + int(POST * C.FS)
    s = y[rows, a:b]
    base = np.median(s[:, :int(0.1 * C.FS)], axis=1, keepdims=True)
    return s - base


def peak_index(y, rows):
    mid = y.shape[1] // 2
    w = int(SEARCH * C.FS)
    seg = y[rows, mid - w:mid + w]
    seg = seg - np.median(seg, axis=1, keepdims=True)
    return mid - w + int(np.argmax(np.max(np.abs(seg), axis=0)))


def zflat(a):
    v = a.ravel()
    return (v - v.mean()) / (v.std() + 1e-12)


def best_r(s, T, lag_n, profile=False):
    c0 = int((PRE - CMP_PRE) * C.FS)
    c1 = int((PRE + CMP_POST) * C.FS)
    if profile == "size":
        # SHAPE AND SIZE. The correlation says whether the space-time shape
        # matches; `g` is the least-squares gain of the template onto the
        # candidate, so a candidate shaped like an IED but a fifth of the
        # size scores a fifth as well. A person filing a picture as Garbage
        # was often looking at the right shape at the wrong size.
        t_raw = T[:, c0:c1].ravel()
        t = zflat(T[:, c0:c1])
        best = -1
        for L in range(-lag_n, lag_n + 1, 5):
            if c0 + L < 0 or c1 + L > s.shape[1]:
                continue
            raw = s[:, c0 + L:c1 + L].ravel()
            v = zflat(s[:, c0 + L:c1 + L])
            r = float(np.dot(v, t) / v.size)
            g = float(np.dot(raw, t_raw) / max(np.dot(t_raw, t_raw), 1e-12))
            size = min(g, 1.0 / g) if g > 0 else 0.0
            best = max(best, r * size)
        return best
    if profile:
        # The depth profile: each channel's mean over a 20 ms window at the
        # template's peak moment, compared as a vector across channels.
        pk = int(PRE * C.FS)
        w = int(0.010 * C.FS)
        t = zflat(T[:, pk - w:pk + w].mean(axis=1))
        best = -1
        for L in range(-lag_n, lag_n + 1, 5):
            v = zflat(s[:, pk - w + L:pk + w + L].mean(axis=1))
            best = max(best, float(np.dot(v, t) / v.size))
        return best
    t = zflat(T[:, c0:c1])
    best = -1
    for L in range(-lag_n, lag_n + 1, 5):
        if c0 + L < 0 or c1 + L > s.shape[1]:
            continue
        v = zflat(s[:, c0 + L:c1 + L])
        best = max(best, float(np.dot(v, t) / v.size))
    return best


def realign(snips_full, idx, rows, iters=2):
    """Iteratively align the Solids onto their own template (+/-50 ms)."""
    lag = int(0.050 * C.FS)
    shifts = {i: 0 for i in idx}
    for _ in range(iters):
        T = np.mean([snips_full[i][1](shifts[i]) for i in idx], axis=0)
        for i in idx:
            best, bL = -2, 0
            for L in range(-lag, lag + 1, 2):
                v = snips_full[i][1](shifts[i] + L)
                r = float(np.dot(zflat(v), zflat(T)) / v.size)
                if r > best:
                    best, bL = r, L
            shifts[i] += bL
    return shifts


def evaluate(rec, X, nums, band, use_car, align, profile):
    good = chan_rows(nums, rec["bad"], "all_good")
    ev = [(e["t"], e["label"]) for e in rec["events"]
          if e["label"] in ("solid", "garbage", "sputter", "flag")]
    S = segs(X, [t for t, _ in ev], slice(None))
    items = []
    for (t, lab), s in zip(ev, S):
        if s is None:
            continue
        y = prep(s, BANDS[band], good if use_car else None)
        pk = peak_index(y, good)
        items.append((lab, y, pk))
    sol = [i for i, it in enumerate(items) if it[0] == "solid"]
    if len(sol) < 3:
        return None
    lag_n = int(LAG * C.FS)

    def snip(i, shift=0):
        lab, y, pk = items[i]
        return cut(y, pk + shift, good)
    shifts = {i: 0 for i in range(len(items))}
    if align == "template":
        full = {i: (None, (lambda sh, i=i: snip(i, sh))) for i in sol}
        shifts.update(realign(full, sol, good))
    sn = {i: snip(i, shifts[i]) for i in range(len(items))}
    Tsum = np.sum([sn[i] for i in sol], axis=0)
    scores = defaultdict(list)
    for i, (lab, _y, _pk) in enumerate(items):
        T = (Tsum - sn[i]) / (len(sol) - 1) if i in sol else Tsum / len(sol)
        # A non-solid candidate is scored with the search widened, the way
        # it would be in use: it was never aligned onto the template.
        lag = lag_n if i in sol and align == "template" else int(0.050 * C.FS)
        scores[lab].append(best_r(sn[i], T, lag, profile))
    return scores


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    if not len(pos) or not len(neg):
        return np.nan
    r = np.argsort(np.argsort(np.concatenate([pos, neg])))
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) - 1) / 2)
                 / (len(pos) * len(neg)))


def main():
    gt = C.load_gt()
    recs = [r for r in gt if r["counts"].get("garbage")]
    data = {}
    for rec in recs:
        d = os.path.join(C.DATA, rec["key"])
        meta = json.load(open(os.path.join(d, "meta.json")))
        data[rec["key"]] = (np.load(os.path.join(d, "sig2k.npy"),
                                    mmap_mode="r"), meta["channels"])
    import sys
    variants = []
    scores_ = (False, True, "size")
    if "--size-only" in sys.argv:
        scores_ = ("size",)
    for band in BANDS:
        for use_car in (False, True):
            for align in ("peak", "template"):
                for profile in scores_:
                    variants.append((band, use_car, align, profile))
    rows = []
    for v in variants:
        pooled = defaultdict(list)
        per = {}
        for rec in recs:
            X, nums = data[rec["key"]]
            sc = evaluate(rec, X, nums, *v)
            if sc is None:
                continue
            per[rec["key"]] = auc(sc["solid"], sc["garbage"])
            for k, vals in sc.items():
                pooled[k].extend(vals)
        sol = np.asarray(pooled["solid"])
        gar = np.asarray(pooled["garbage"])
        thr = sol.min()
        row = {"band": v[0], "car": v[1], "align": v[2],
               "score": ("shape+size" if v[3] == "size"
                         else "profile" if v[3] else "space-time"),
               "auc_pooled": round(auc(sol, gar), 3),
               "auc_per_rec_median": round(float(np.nanmedian(
                   list(per.values()))), 3),
               "garbage_through_at_all_solids": round(float(np.mean(gar >= thr)), 3),
               "garbage_through_at_95pct_solids": round(float(np.mean(
                   gar >= np.percentile(sol, 5))), 3),
               "solid_median": round(float(np.median(sol)), 2),
               "garbage_median": round(float(np.median(gar)), 2),
               "sputter_median": round(float(np.median(pooled["sputter"])), 2)
               if pooled["sputter"] else None,
               "per_rec": {k: round(x, 3) for k, x in per.items()}}
        rows.append(row)
        C.log(row)
    rows.sort(key=lambda r: -r["auc_per_rec_median"])
    name = "classifier_design_size.json" if "--size-only" in sys.argv \
        else "classifier_design.json"
    with open(os.path.join(C.OUT, name), "w") as fh:
        json.dump(rows, fh, indent=1)
    C.log("\nBEST (by median per-recording AUC):")
    for r in rows[:5]:
        C.log(r)


if __name__ == "__main__":
    main()
