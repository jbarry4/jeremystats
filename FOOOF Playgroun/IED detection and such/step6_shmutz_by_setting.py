# -*- coding: utf-8 -*-
"""Step 6 -- what each candidate setting's extra detections are.

For a handful of settings (the original, the best without common-average
referencing, the best with it, and each with the lab's channel rule), every
detection that does NOT contain a hand-sorted Solid is measured with exactly
the measurements why_garbage.py uses on the labelled stamps, and sorted into
the first shmutz type it belongs to.

A type is defined by the labelled Solids, so that no real IED could ever be
put in it: a detection is "too small" only if it is smaller than EVERY Solid
on its recording was, "HF-driven" only if more of its line length comes
from 300-900 Hz than for any Solid, and so on. A detection that is inside
the Solids' range on every measurement is "IED-like" -- a candidate worth a
person's look, not shmutz.

Writes out/shmutz_types.csv and prints the table.

    python step6_shmutz_by_setting.py
"""
import csv
import json
import os
from collections import Counter

import numpy as np

import detector as D
import ied_common as C
import why_garbage as WG
from step3_sweep import chan_rows, thresholds_from_hist, vmatch

# setting name -> (setting, kmin, kmax)
SETTINGS = {
    "original (30 kHz raw, 99.9)": (
        {"prefilter": "orig30k", "llw": 0.04, "chanset": "even",
         "mode": "global", "prc": 99.9, "merge": 0.3, "min_s": 0.025}, 1, None),
    "original + 5-10 even rule": (
        {"prefilter": "orig30k", "llw": 0.04, "chanset": "even",
         "mode": "global", "prc": 99.9, "merge": 0.3, "min_s": 0.025}, 5, 10),
}
# The sweep's winners are filled in from out/rule_ranked.csv and
# out/sweep_frontier.csv by `pick()`.

# The order types are checked in: the most specific cause first.
TYPES = [
    ("dominant", "the recording's single dominant crossing channel tops it"),
    ("hf_ll_share", "line length driven by 300-900 Hz (unit/EMG burst)"),
    ("car_keep", "common-mode: mostly gone after common-average referencing"),
    ("amp_rel", "smaller than every confirmed IED on this recording"),
    ("top_ratio", "barely over the threshold"),
    ("orig_n_cross", "too few channels"),
]


def pick():
    out = dict(SETTINGS)
    rr = os.path.join(C.OUT, "rule_ranked.csv")
    if os.path.exists(rr):
        rows = list(csv.DictReader(open(rr)))
        def first(pred):
            for r in rows:
                if pred(r):
                    return r
        for label, pred in (
            ("best overall (detector + channel rule)", lambda r: True),
            ("best with CAR, no rule",
             lambda r: r["prefilter"].startswith("car") and r["kmin"] == "1"
             and r["kmax"] == ""),
            ("best without CAR, no rule",
             lambda r: not r["prefilter"].startswith("car")
             and r["prefilter"] != "orig30k" and r["kmin"] == "1"
             and r["kmax"] == ""),
            ("best without CAR, with rule",
             lambda r: not r["prefilter"].startswith("car")
             and r["prefilter"] != "orig30k")):
            r = first(pred)
            if r:
                s = {k: r[k] for k in ("prefilter", "llw", "chanset", "mode",
                                       "prc", "merge", "min_s")}
                out[label] = (s, int(r["kmin"]),
                              int(r["kmax"]) if r["kmax"] else None)
    return out


def bounds(rows):
    """Per measurement and recording, the edge of the Solids' range."""
    b = {}
    for key in {r["key"] for r in rows}:
        sol = [r for r in rows if r["key"] == key and r["label"] == "solid"]
        if not sol:
            continue
        def ext(f, fn):
            v = [float(r[f]) for r in sol if r.get(f) not in (None, "")]
            return fn(v) if v else np.nan
        b[key] = {"amp_rel": ext("amp_rel", min),
                  "top_ratio": ext("top_ratio", min),
                  "hf_ll_share": ext("hf_ll_share", max),
                  "car_keep": ext("car_keep", min),
                  "orig_n_cross": ext("orig_n_cross", min)}
    return b


def kind(r, b, dom):
    bb = b.get(r["key"])
    if not bb:
        return "no Solids to compare with"
    if r.get("orig_top_ch") and int(r["orig_top_ch"]) == dom.get(r["key"]) \
            and dom.get(r["key"]) is not None:
        return "dominant"
    def num(f):
        v = r.get(f)
        return float(v) if v not in (None, "") else np.nan
    if num("hf_ll_share") > bb["hf_ll_share"]:
        return "hf_ll_share"
    if num("car_keep") < bb["car_keep"]:
        return "car_keep"
    if num("amp_rel") < bb["amp_rel"]:
        return "amp_rel"
    if num("top_ratio") < bb["top_ratio"]:
        return "top_ratio"
    if num("orig_n_cross") < bb["orig_n_cross"]:
        return "orig_n_cross"
    return "IED-like"


def main():
    gt = C.load_gt()
    labelled = list(csv.DictReader(open(os.path.join(C.OUT, "why_garbage.csv"))))
    b = bounds(labelled)
    dom = {}
    for line in open(os.path.join(C.OUT, "why_garbage_summary.txt")):
        if line.startswith("{'key'"):
            d = eval(line)                                # our own file
            # Only where one channel really dominates -- over a third of all
            # crossings -- and no Solid is topped by it (m13 s2's dominant
            # channel is its IED channel, and is excluded by that test).
            if d["top3_share"][0] > 0.3:
                dom[d["key"]] = d["top3_channels"][0]
    for key in list(dom):
        if any(r["key"] == key and r["label"] == "solid" and r.get("orig_top_ch")
               and int(r["orig_top_ch"]) == dom[key] for r in labelled):
            del dom[key]
    C.log("dominant channels used:", dom)

    table = []
    for name, (s, kmin, kmax) in pick().items():
        C.log("\n===", name, s, "rule", kmin, kmax)
        allrows = []
        for rec in gt:
            d, meta, X = D.load_rec(rec)
            evs = D.run_setting(rec, s, X=X, meta=meta, d=d)
            evs = [e for e in evs if e["n"] >= kmin
                   and (kmax is None or e["n"] <= kmax)]
            arr = np.asarray([[e["on"], e["off"]] for e in evs]) if evs \
                else np.zeros((0, 2))
            sol_t = np.asarray(sorted(e["t"] for e in rec["events"]
                                      if e["label"] == "solid"))
            hit = set(vmatch(arr, sol_t).tolist()) - {-1}
            pseudo = dict(rec)
            pseudo["events"] = [{"t": (e["on"] + e["off"]) / 2,
                                 "label": "solid" if i in hit else "extra"}
                                for i, e in enumerate(evs)]
            nums = meta["channels"]
            P30 = np.load(os.path.join(d, "ll30k_pool.npy"), mmap_mode="r")
            hist = np.load(os.path.join(d, "ll30k_hist.npy"))
            lo, hi, nb = meta["hist"]
            even = chan_rows(nums, rec["bad"], "even")
            good = chan_rows(nums, rec["bad"], "all_good")
            thr = thresholds_from_hist(hist, even, [99.9], lo, hi, nb)[0]
            rows, _segs = WG.features(pseudo, X, P30, thr, nums, good, even)
            sol_amp = np.median([float(r["amp_uv"]) for r in labelled
                                 if r["key"] == rec["key"]
                                 and r["label"] == "solid"
                                 and r.get("amp_uv") not in (None, "")]
                                or [np.nan])
            for r in rows:
                if "amp_uv" in r:
                    r["amp_rel"] = r["amp_uv"] / sol_amp
            allrows.extend(rows)
            C.log("  %s: %d detections" % (rec["key"], len(evs)))
        extra = [r for r in allrows if r["label"] == "extra"]
        k = Counter(kind(r, b, dom) for r in extra)
        row = {"setting": name, "detections": len(allrows),
               "with_solid": sum(1 for r in allrows if r["label"] == "solid"),
               "extra": len(extra)}
        for t, _desc in TYPES:
            row[t] = k.get(t, 0)
        row["IED-like"] = k.get("IED-like", 0)
        row["no Solids to compare with"] = k.get("no Solids to compare with", 0)
        table.append(row)
        C.log(row)
    with open(os.path.join(C.OUT, "shmutz_types.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)
    C.log("\nTYPES")
    for t, desc in TYPES:
        C.log("  %-13s %s" % (t, desc))


if __name__ == "__main__":
    main()
