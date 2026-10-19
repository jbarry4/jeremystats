# -*- coding: utf-8 -*-
"""Solid vs Garbage, compared WITHIN the recordings that have both.

why_garbage.py measured every labelled stamp. Its pooled summary compares
Solids against Garbage across all ten recordings -- but half the Solids come
from recordings with no Garbage labels at all, so any feature that differs
between RECORDINGS looks like a Solid/Garbage difference. This restricts the
comparison to the five recordings with both (m5 s7, m13 s2, m13 s17, m28 s2,
m34 s5), reports a per-recording AUC beside the pooled one, and uses
tie-aware ranks (most features are not ties; `top_is_bad` is nearly all 0).

AUC reads as: the probability a random Solid scores higher than a random
Garbage. 0.5 = no separation; above 0.5 Solids are higher, below 0.5
Garbage is higher.

Also: for each of those recordings, how many Garbage / unreviewed / Solid
events have the recording's single DOMINANT channel as their top crosser.

    python why_garbage_within.py
"""
import csv
import os

import numpy as np
from scipy.stats import rankdata

import ied_common as C

BOTH = ["m5_s7", "m13_s2", "m13_s17", "m28_s2", "m34_s5"]
FEATS = ["amp_rel", "amp_uv", "top_ratio", "orig_n_cross", "car_keep",
         "common_mode", "hf_ll_share", "hf_frac", "mains_frac", "width_ms",
         "top_is_bad", "neighbours", "polarity"]


def auc(p, n):
    p, n = np.asarray(p, float), np.asarray(n, float)
    if not len(p) or not len(n):
        return np.nan
    r = rankdata(np.concatenate([p, n]))
    return (r[:len(p)].sum() - len(p) * (len(p) + 1) / 2) / (len(p) * len(n))


def main():
    rows = list(csv.DictReader(open(os.path.join(C.OUT, "why_garbage.csv"))))

    def vals(lab, f, keys):
        return [float(r[f]) for r in rows if r["label"] == lab
                and r["key"] in keys and r.get(f) not in ("", None)]

    lines = ["%-13s %-10s %-10s %-10s %-8s %s" % (
        "feature", "Solid", "Garbage", "Unrev", "AUC", "per recording " + " ".join(BOTH))]
    for f in FEATS:
        s, g, u = vals("solid", f, BOTH), vals("garbage", f, BOTH), \
            vals("unreviewed", f, BOTH)
        per = [auc(vals("solid", f, [k]), vals("garbage", f, [k])) for k in BOTH]
        lines.append("%-13s %-10.3g %-10.3g %-10.3g %-8.2f %s" % (
            f, np.median(s), np.median(g), np.median(u) if u else np.nan,
            auc(s, g), " ".join("%.2f" % x for x in per)))
    lines.append("")
    # the recording's dominant crossing channel, from why_garbage_summary
    dom = {}
    for line in open(os.path.join(C.OUT, "why_garbage_summary.txt")):
        if line.startswith("{'key'"):
            d = eval(line)                       # our own file
            dom[d["key"]] = d["top3_channels"][0]
    for k in BOTH:
        def share(lab):
            L = [r for r in rows if r["key"] == k and r["label"] == lab
                 and r.get("orig_top_ch")]
            return 100 * np.mean([int(r["orig_top_ch"]) == dom[k] for r in L]) \
                if L else float("nan")
        lines.append("%-8s dominant channel CSC%-3d tops: garbage %3.0f%%  "
                     "unreviewed %3.0f%%  solid %3.0f%%"
                     % (k, dom[k], share("garbage"), share("unreviewed"),
                        share("solid")))
    text = "\n".join(lines)
    with open(os.path.join(C.OUT, "why_garbage_within.txt"), "w") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
