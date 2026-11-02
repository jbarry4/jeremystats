# -*- coding: utf-8 -*-
"""Why does so much Garbage get past the detector?

Two kinds of evidence.

ABOUT THE DETECTOR, run exactly as the lab ran it (raw 30 kHz, 40 ms line
length, even channels, one pooled 99.9th-percentile threshold):
  * how many detections each recording produces against how many Solids it
    has -- a percentile threshold fixes the first and ignores the second;
  * which channels do the crossing -- one pooled threshold and "any channel
    starts an event" hand the event list to whichever channel is noisiest.

ABOUT THE EVENTS, every hand-labelled one (Solid, Sputter, Flag, Garbage),
measured at the stamp:
  orig_n_cross   even channels over the original threshold
  orig_top_ch    the channel with the most line length over threshold
  top_share      how far the top channel stands above the second
  top_is_bad     whether that channel is on the recording's bad list
  amp_uv         largest peak-to-peak deflection, 1-70 Hz, good channels
  amp_rel        that, relative to this recording's median Solid
  hf_ll_share    on the top channel: how much of the line length comes from
                 300-900 Hz rather than below 300 Hz
  hf_frac        300-900 Hz share of the power, good channels
  mains_frac     60/120/180 Hz share of the power
  common_mode    how much of each channel the channel-mean explains
  car_keep       line length of the top channel after common-average
                 referencing, over before (1 = untouched, 0 = all common)
  width_ms       half-amplitude width of the main deflection
  peak_row       which channel (in probe order) carries the main deflection
  neighbours     other candidates (any label) within 2 s -- bursts

Writes out/why_garbage.csv, out/why_garbage_summary.txt and figures in
out/figs/, and caches every labelled event's 64-channel segment for the
classifier design.

    python why_garbage.py
"""
import csv
import json
import os
from collections import Counter, defaultdict

import numpy as np

import ied_common as C
from step3_sweep import chan_rows, thresholds_from_hist

FIG = os.path.join(C.OUT, "figs")
os.makedirs(FIG, exist_ok=True)

HALF = 1.0                 # segment read either side of a stamp
W_STAMP = 0.075            # how near the stamp the crossing must be
LAB = ("solid", "sputter", "flag", "garbage")


def seg(X, t, half=HALF):
    i = int(round(t * C.FS))
    h = int(half * C.FS)
    if i - h < 0 or i + h > X.shape[1]:
        return None
    return np.asarray(X[:, i - h:i + h], dtype=np.float64)


def band_ll(x, lo, hi):
    y = C.band(x, lo, hi) if (lo or hi) else x
    return np.abs(np.diff(y, axis=-1)).sum(axis=-1)


def features(rec, X, P30, thr30, nums, good, even):
    """One row per labelled stamp (and per unreviewed one, without a segment)."""
    rows = []
    segs = {}
    centre = int(HALF * C.FS)
    wst = int(W_STAMP * C.FS)
    pool_fs = C.FS_POOL
    times_all = np.asarray(sorted(e["t"] for e in rec["events"]))
    for k, e in enumerate(rec["events"]):
        t, lab = e["t"], e["label"] or "unreviewed"
        r = {"key": rec["key"], "t": round(t, 4), "label": lab}
        # ---- the original detector at this stamp ----
        b0 = max(0, int((t - W_STAMP - 0.02) * pool_fs))
        b1 = min(P30.shape[1], int((t + W_STAMP - 0.02) * pool_fs) + 1)
        if b1 <= b0:
            # A stamp past the end of the file: m28 s7's sort runs 3 s past
            # its recording (tools/import_ied.py says so). Nothing to measure.
            r["note"] = "past the end of the recording"
            rows.append(r)
            continue
        llmax = np.asarray(P30[even, b0:b1]).max(axis=1)
        ratio = llmax / thr30
        order = np.argsort(ratio)[::-1]
        r["orig_n_cross"] = int((ratio > 1).sum())
        r["orig_top_ch"] = int(nums[even[order[0]]])
        r["top_ratio"] = round(float(ratio[order[0]]), 3)
        r["top_share"] = round(float(ratio[order[0]] /
                                     max(ratio[order[1]], 1e-9)), 3)
        r["top_is_bad"] = int(nums[even[order[0]]] in set(rec["bad"]))
        r["neighbours"] = int(((times_all > t - 2) & (times_all < t + 2)).sum()
                              - 1)
        s = seg(X, t)
        if s is None:
            rows.append(r)
            continue
        n = C.notch(s)
        lfp = C.band(n, 1, 70)
        a, b = centre - int(0.1 * C.FS), centre + int(0.1 * C.FS)
        w = lfp[good, a:b]
        p2p = w.max(axis=1) - w.min(axis=1)
        pk_row = int(np.argmax(p2p))
        r["amp_uv"] = round(float(p2p[pk_row]), 1)
        r["peak_row"] = int(good[pk_row])
        # width of the main deflection on the peak channel
        tr = w[pk_row] - np.median(w[pk_row])
        j = int(np.argmax(np.abs(tr)))
        half_amp = abs(tr[j]) / 2
        lo_ = j
        while lo_ > 0 and abs(tr[lo_]) > half_amp:
            lo_ -= 1
        hi_ = j
        while hi_ < len(tr) - 1 and abs(tr[hi_]) > half_amp:
            hi_ += 1
        r["width_ms"] = round((hi_ - lo_) / C.FS * 1000, 1)
        r["polarity"] = int(np.sign(tr[j]))
        # spectra on the raw segment, +/-100 ms
        raw = s[good, a:b] - s[good, a:b].mean(axis=1, keepdims=True)
        F = np.abs(np.fft.rfft(raw * np.hanning(raw.shape[1]), axis=1)) ** 2
        f = np.fft.rfftfreq(raw.shape[1], 1 / C.FS)
        Pm = F.mean(axis=0)
        tot = Pm[(f >= 1) & (f <= 900)].sum() + 1e-12
        r["hf_frac"] = round(float(Pm[(f >= 300) & (f <= 900)].sum() / tot), 4)
        r["mains_frac"] = round(float(sum(Pm[(f >= h - 4) & (f <= h + 4)].sum()
                                          for h in (60, 120, 180)) / tot), 4)
        bb = C.band(n, 1, 300)[good, a:b]
        bb = bb - bb.mean(axis=1, keepdims=True)
        m = bb.mean(axis=0)
        r["common_mode"] = round(float(np.var(m) /
                                       max(np.mean(np.var(bb, axis=1)), 1e-12)),
                                 4)
        # what drives the line length on the channel that crossed most
        top_row = even[order[0]]
        sl = slice(centre - int(0.05 * C.FS), centre + int(0.05 * C.FS))
        ll_lo = band_ll(n[top_row, sl], 1, 300)
        ll_hi = band_ll(n[top_row, sl], 300, 900)
        r["hf_ll_share"] = round(float(ll_hi / max(ll_lo + ll_hi, 1e-9)), 4)
        car = n - n[good].mean(axis=0, keepdims=True)
        ll_car = band_ll(car[top_row, sl], 1, 300)
        r["car_keep"] = round(float(ll_car / max(ll_lo, 1e-9)), 4)
        rows.append(r)
        if lab in LAB:
            segs[(rec["key"], round(t, 4))] = s.astype(np.float32)
    return rows, segs


def summarize(rows):
    out = []
    feats = ("orig_n_cross", "top_ratio", "top_share", "top_is_bad", "amp_uv",
             "amp_rel", "width_ms", "hf_frac", "hf_ll_share", "mains_frac",
             "common_mode", "car_keep", "neighbours")
    by = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for f in feats:
            if f in r and r[f] is not None:
                by[r["label"]][f].append(float(r[f]))
    out.append("%-13s %-22s %-22s %-22s %s" % (
        "feature", "Solid median [IQR]", "Garbage median [IQR]",
        "Unreviewed median", "AUC solid vs garbage"))
    for f in feats:
        def q(lab):
            v = np.asarray(by[lab][f])
            if not v.size:
                return "-"
            return "%.3g [%.3g-%.3g]" % (np.median(v), *np.percentile(v, [25, 75]))
        s_, g_ = np.asarray(by["solid"][f]), np.asarray(by["garbage"][f])
        a = auc(s_, g_)
        u = np.asarray(by["unreviewed"][f])
        out.append("%-13s %-22s %-22s %-22s %.2f" % (
            f, q("solid"), q("garbage"),
            "%.3g" % np.median(u) if u.size else "-", a))
    return out


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    if not len(pos) or not len(neg):
        return float("nan")
    r = np.argsort(np.argsort(np.concatenate([pos, neg])))
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) - 1) / 2)
                 / (len(pos) * len(neg)))


def main():
    gt = C.load_gt()
    all_rows, all_segs, detector = [], {}, []
    for rec in gt:
        d = os.path.join(C.DATA, rec["key"])
        meta = json.load(open(os.path.join(d, "meta.json")))
        nums = meta["channels"]
        X = np.load(os.path.join(d, "sig2k.npy"), mmap_mode="r")
        P30 = np.load(os.path.join(d, "ll30k_pool.npy"), mmap_mode="r")
        hist = np.load(os.path.join(d, "ll30k_hist.npy"))
        lo, hi, nb = meta["hist"]
        even = chan_rows(nums, rec["bad"], "even")
        good = chan_rows(nums, rec["bad"], "all_good")
        thr = thresholds_from_hist(hist, even, [99.9], lo, hi, nb)[0]
        # ---- the detector as the lab ran it: who crosses? ----
        Pe = np.asarray(P30[even])
        cross = Pe > thr
        per_ch = cross.sum(axis=1)
        any_bins = cross.any(axis=0).sum()
        solo = (cross.sum(axis=0) == 1)
        top = np.argsort(per_ch)[::-1][:3]
        detector.append({
            "key": rec["key"], "minutes": round(meta["seconds"] / 60, 1),
            "solids": rec["counts"].get("solid", 0),
            "candidates_in_bank": len(rec["events"]),
            "bins_over": int(any_bins),
            "share_single_channel": round(float(solo.sum() / max(any_bins, 1)), 3),
            "top3_channels": [int(nums[even[i]]) for i in top],
            "top3_share": [round(float(per_ch[i] / max(per_ch.sum(), 1)), 3)
                           for i in top],
            "bad_even": [n for n in rec["bad"] if n % 2 == 0],
        })
        rows, segs = features(rec, X, P30, thr, nums, good, even)
        sol_amp = np.median([r["amp_uv"] for r in rows
                             if r["label"] == "solid" and "amp_uv" in r] or [np.nan])
        for r in rows:
            if "amp_uv" in r:
                r["amp_rel"] = round(r["amp_uv"] / sol_amp, 3)
        all_rows.extend(rows)
        all_segs.update(segs)
        C.log(rec["key"], len(rows), "events measured", detector[-1])
        del Pe, cross

    # ---- write ----
    keys = sorted({k for r in all_rows for k in r})
    with open(os.path.join(C.OUT, "why_garbage.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(all_rows)
    np.savez(os.path.join(C.DATA, "labelled_segments.npz"),
             keys=np.array(["%s|%.4f" % k for k in all_segs], dtype=object),
             data=np.stack(list(all_segs.values())))
    lines = ["THE DETECTOR AS THE LAB RAN IT (raw 30 kHz, 40 ms, even channels, "
             "pooled 99.9th percentile)", ""]
    for dd in detector:
        lines.append(str(dd))
    lines += ["", "SOLID vs GARBAGE at the hand-sorted stamps", ""]
    lines += summarize(all_rows)
    with open(os.path.join(C.OUT, "why_garbage_summary.txt"), "w") as fh:
        fh.write("\n".join(lines))
    C.log("\n".join(lines))
    figures(all_rows, all_segs, gt)


def figures(rows, segs, gt):
    """Average 64-channel waveform of Solid vs Garbage, per recording."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for rec in gt:
        key = rec["key"]
        good = None
        sol = [segs[(key, round(e["t"], 4))] for e in rec["events"]
               if e["label"] == "solid" and (key, round(e["t"], 4)) in segs]
        gar = [segs[(key, round(e["t"], 4))] for e in rec["events"]
               if e["label"] == "garbage" and (key, round(e["t"], 4)) in segs]
        if len(sol) < 2 or len(gar) < 2:
            continue
        fig, axs = plt.subplots(1, 2, figsize=(11, 9), sharey=True)
        for ax, group, title in ((axs[0], sol, "Solid (n=%d)" % len(sol)),
                                 (axs[1], gar, "Garbage (n=%d)" % len(gar))):
            m = np.mean([C.band(C.notch(g.astype(np.float64)), 1, 70)
                         for g in group], axis=0)
            m = m[:, int(0.7 * C.FS):int(1.3 * C.FS)]
            m = m - np.median(m[:, :int(0.1 * C.FS)], axis=1, keepdims=True)
            sc = np.percentile(np.abs(m), 99) or 1
            tt = (np.arange(m.shape[1]) / C.FS - 0.3) * 1000
            for i in range(m.shape[0]):
                ax.plot(tt, -i + m[i] / sc * 2.5, lw=0.6,
                        color="k" if (i + 1) not in rec["bad"] else "r")
            ax.set_title(title)
            ax.set_xlabel("ms from stamp")
        axs[0].set_ylabel("CSC number order, CSC1 at top (red = bad)")
        fig.suptitle("%s  average waveform, 1-70 Hz" % key)
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, "avg_%s.png" % key), dpi=110)
        plt.close(fig)


if __name__ == "__main__":
    main()
