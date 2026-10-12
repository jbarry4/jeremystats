# -*- coding: utf-8 -*-
"""The waveform-across-depth classifier comparison, on cached snippets.

Same question and same variants as classifier_design.py -- does a candidate
look like this recording's confirmed IEDs across the depth of the probe --
but reading the 64-channel segments why_garbage.py already cut out and
cached, and filtering each one once per (band, referencing) rather than once
per variant. That is the difference between minutes and hours.

Template matching only, by decision: there are 170 Solids, which is too few
to train a model on honestly.

    python classifier_fast.py
"""
import json
import os
from collections import defaultdict

import numpy as np

import classifier_design as CD
import ied_common as C
from step3_sweep import chan_rows

CENTRE = int(1.0 * C.FS)          # the stamp, in a cached 2 s segment


def load_segments():
    z = np.load(os.path.join(C.DATA, "labelled_segments.npz"),
                allow_pickle=True)
    keys = [k.split("|") for k in z["keys"]]
    return [(k, float(t)) for k, t in keys], z["data"]


def main():
    gt = {r["key"]: r for r in C.load_gt()}
    ids, data = load_segments()
    lab_of = {}
    for key, rec in gt.items():
        for e in rec["events"]:
            lab_of[(key, round(e["t"], 4))] = e["label"]
    nums = list(range(1, 65))
    recs = sorted({k for k, _ in ids})
    rows_out = []
    for band in CD.BANDS:
        for use_car in (False, True):
            # filter every snippet once for this band and referencing
            filt = {}
            for (key, t), s in zip(ids, data):
                good = chan_rows(nums, gt[key]["bad"], "all_good")
                filt[(key, t)] = CD.prep(s.astype(np.float64), CD.BANDS[band],
                                         good if use_car else None)
            for align in ("peak", "template"):
                for score in (False, True, "size"):
                    pooled = defaultdict(list)
                    per = {}
                    for key in recs:
                        good = chan_rows(nums, gt[key]["bad"], "all_good")
                        items = []
                        for (k2, t), y in filt.items():
                            if k2 != key:
                                continue
                            lab = lab_of.get((key, round(t, 4)))
                            if lab not in ("solid", "garbage", "sputter", "flag"):
                                continue
                            # the cached segment is +/-1 s; CD expects the
                            # stamp in the middle, which it is
                            pk = CD.peak_index(y, good)
                            items.append((lab, y, pk))
                        sc = score_items(items, good, align, score)
                        if sc is None:
                            continue
                        if sc["garbage"]:
                            per[key] = CD.auc(sc["solid"], sc["garbage"])
                        for lab, v in sc.items():
                            pooled[lab].extend(v)
                    sol = np.asarray(pooled["solid"])
                    gar = np.asarray(pooled["garbage"])
                    row = {"band": band, "car": use_car, "align": align,
                           "score": ("shape+size" if score == "size" else
                                     "profile" if score else "space-time"),
                           "auc_pooled": round(CD.auc(sol, gar), 3),
                           "auc_per_rec_median": round(float(np.nanmedian(
                               list(per.values()))), 3),
                           "garbage_through_at_all_solids": round(float(
                               np.mean(gar >= sol.min())), 3),
                           "garbage_through_at_95pct_solids": round(float(
                               np.mean(gar >= np.percentile(sol, 5))), 3),
                           "per_rec": {k: round(v, 3) for k, v in per.items()}}
                    rows_out.append(row)
                    C.log(row)
    rows_out.sort(key=lambda r: -r["auc_per_rec_median"])
    with open(os.path.join(C.OUT, "classifier_fast.json"), "w") as fh:
        json.dump(rows_out, fh, indent=1)
    C.log("\nBEST 6 by median per-recording AUC")
    for r in rows_out[:6]:
        C.log(r)


def score_items(items, good, align, score):
    sol = [i for i, it in enumerate(items) if it[0] == "solid"]
    if len(sol) < 3:
        return None
    lag_n = int(CD.LAG * C.FS)

    def snip(i, shift=0):
        _lab, y, pk = items[i]
        return CD.cut(y, pk + shift, good)
    shifts = {i: 0 for i in range(len(items))}
    if align == "template":
        full = {i: (None, (lambda sh, i=i: snip(i, sh))) for i in sol}
        shifts.update(CD.realign(full, sol, good))
    sn = {i: snip(i, shifts[i]) for i in range(len(items))}
    Tsum = np.sum([sn[i] for i in sol], axis=0)
    out = defaultdict(list)
    for i, (lab, _y, _pk) in enumerate(items):
        T = (Tsum - sn[i]) / (len(sol) - 1) if i in sol else Tsum / len(sol)
        lag = lag_n if (i in sol and align == "template") else int(0.050 * C.FS)
        out[lab].append(CD.best_r(sn[i], T, lag, score))
    return out


if __name__ == "__main__":
    main()
