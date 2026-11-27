"""Three remedies for the camel hump, on every recording of a room version:

  repair   linear (what the reads hold: a bad row = mean of its 2 neighbours,
           which forces the CSD there to ZERO and pushes half its sink to each
           neighbour) vs cubic (4-point: the CSD there = its neighbours').
  sinks    bumps (today: each event's own two largest bumps, split at zero
           crossings -- a camel whose dip touches zero becomes two bumps and
           the 'top two' becomes a ranking) vs halves (the recording's two
           humps: the band cut at the source between the two biggest sinks of
           the average, every event's negative side kept in each half).
  trim     none vs a DBSCAN-style density trim (Toothy's idea): events whose
           5th-nearest neighbour is further than most events' (Hellinger
           distance on the sinks) are left unsorted before the line.

For each: the default line's split, its SI, lambda2, and how stable it is
(mean adjusted Rand index of the line refitted on 25 random 80% subsets
against the full line, on the shared events).
Usage: camel_try.py [version] [label filter]"""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camel_try.json")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import dspca, sinkcut  # noqa: E402
from backend import extraction as EX  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import adjusted_rand_score  # noqa: E402

VERSION = int(sys.argv[1]) if len(sys.argv) > 1 else 4
ONLY = sys.argv[2] if len(sys.argv) > 2 else None
room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], VERSION)
RNG = np.random.default_rng(0)


def cubic(got):
    """The read with each bad row made again from two good neighbours a
    side (4-point Lagrange); where that is not possible, left linear."""
    nums = [int(n) for n in got["nums"]]
    bad = {int(k) for k in (got.get("bad") or {})}
    out = dict(got)
    out["sur"] = {}
    done = []
    for key, X in got["sur"].items():
        X = np.array(X, dtype=float, copy=True)
        for b in sorted(bad):
            i = nums.index(b)
            nb = [i - 2, i - 1, i + 1, i + 2]
            if all(0 <= k < len(nums) and nums[k] not in bad for k in nb):
                X[:, i] = (-X[:, i - 2] + 4 * X[:, i - 1] + 4 * X[:, i + 1] - X[:, i + 2]) / 6.0
                if key == "band":
                    done.append(b)
        out["sur"][key] = X
    return out, done


def profiles(A_, half_ms=3.0):
    """Each event's negative CSD profile in the band (E x D), as sinkcut
    takes it, and the band's contact numbers."""
    disp = np.asarray(A_["disp"], dtype=float)
    ns = [int(n) for n in A_["nums_sel"]]
    na = [int(n) for n in A_["nums_all"]]
    rows = sinkcut.band_rows(na, ns)
    fs, t0 = sinkcut.time_axis(disp.shape[2])
    h = int(round(half_ms * fs / 1000.0))
    win = disp[:, rows, t0 - h:t0 + h + 1].mean(axis=2)
    return np.maximum(0.0, -win), ns


def S_bumps(neg):
    mask, found, _sp, _th = sinkcut.top_bumps(neg, 2)
    return neg * mask, found


def halves(neg):
    """The cut between the recording's two humps: the most positive point of
    the mean profile (its source) between its two biggest sink bumps."""
    mean = neg.mean(axis=0)
    bb = sorted(sinkcut.bumps(mean), key=lambda b: -b[2])[:2]
    if len(bb) < 2:
        return None, bb
    (a1, b1, _), (a2, b2, _) = sorted(bb, key=lambda b: b[0])
    # neg is >= 0: the source is where the mean negative side is least; take
    # the middle of the stretch where it is smallest between the two.
    seg = mean[b1 - 1:a2 + 1]
    lo = np.flatnonzero(seg <= seg.min() + 1e-12)
    cut = b1 - 1 + int(round(lo.mean()))
    return cut, bb


def S_halves(neg, cut):
    # Every event's negative side, everywhere in the band; the halves only
    # decide what a 'hump' is for the camel count. Normalised per half so the
    # two humps weigh the same whatever their sizes -- a version without that
    # is 'S_whole'.
    top, bot = neg[:, :cut + 1], neg[:, cut + 1:]
    st = top.sum(axis=1, keepdims=True)
    sb = bot.sum(axis=1, keepdims=True)
    return np.hstack([np.divide(top, st, out=np.zeros_like(top), where=st > 0),
                      np.divide(bot, sb, out=np.zeros_like(bot), where=sb > 0)])


def norm(S):
    m = S.sum(axis=1, keepdims=True)
    return np.divide(S, m, out=np.zeros_like(S), where=m > 0)


def line(S, min_share=0.02):
    """The Bite line on sink distributions S (rows add to 1): labels at the
    default line (0 left, 1 right; -1 no sink), SI there, lambda2."""
    W = sinkcut.overlap(S)
    G = sinkcut.affinity(W)
    cen = sinkcut.centroid(S if S.shape[1] == S.shape[1] else S)
    idx, coord, lam2 = sinkcut.order(G, cen)
    live = idx[np.isfinite(coord[idx])]
    sw = sinkcut.sweep(W, live, min_share, sinkcut.MIN_EVENTS)
    k = sw["best"]
    lab = np.full(S.shape[0], -1)
    lab[live[:k]] = 0
    lab[live[k:]] = 1
    si = sw["si"][k - 1]
    return lab, si, lam2, W


def stability(S, lab, reps=25, frac=0.8, min_share=0.02):
    n = S.shape[0]
    out = []
    for _ in range(reps):
        sub = np.sort(RNG.choice(n, int(frac * n), replace=False))
        try:
            l2, _si, _l, _w = line(S[sub], min_share)
        except Exception:  # noqa: BLE001
            continue
        ok = (lab[sub] >= 0) & (l2 >= 0)
        out.append(adjusted_rand_score(lab[sub][ok], l2[ok]))
    return float(np.mean(out)) if out else float("nan")


def trim(W, m=5, q=90):
    """DBSCAN's noise points, Toothy's way of leaving odd events out: the
    Hellinger distance sqrt(1 - BC), eps the q-th percentile of every
    event's m-th neighbour distance; an event whose m-th neighbour is further
    than eps is not a core point and, if no core point is within eps either,
    is noise."""
    from sklearn.cluster import DBSCAN
    D = np.sqrt(np.clip(1.0 - W, 0.0, None))
    np.fill_diagonal(D, 0.0)
    kd = np.sort(D, axis=1)[:, m]
    eps = float(np.percentile(kd, q))
    lab = DBSCAN(eps=eps, min_samples=m, metric="precomputed").fit(D).labels_
    return lab != -1, eps, len(set(lab) - {-1})


rows = []
for rec in pay["recordings"]:
    if ONLY and ONLY not in rec["session_label"]:
        continue
    if rec["n"] < 20:
        continue
    got = A._dspca_load(rec["gid"], rec["read"])
    band = rec["box"]
    lay = A._dspca_layers(rec["gid"])
    res_l = dspca.fit(got, A._er_fit_params(got, band), layers=lay)
    got_c, done = cubic(got)
    res_c = dspca.fit(got_c, A._er_fit_params(got_c, band), layers=lay)
    out = {"label": rec["session_label"], "group": rec.get("group"), "n": rec["n"],
           "band": [band["sel_lo"], band["sel_hi"]], "bad": sorted(int(k) for k in got.get("bad") or {}),
           "cubic_done": done, "v": {}}
    for rep, res in (("linear", res_l), ("cubic", res_c)):
        Aa = EX.split_arrays(res)
        neg, ns = profiles(Aa)
        Sb, found = S_bumps(neg)
        cut, _bb = halves(neg)
        variants = {"bumps": norm(Sb), "whole": norm(neg)}
        if cut is not None:
            variants["halves"] = norm(S_halves(neg, cut))
            out["halves_cut"] = ns[cut]
        out["camel_three"] = out.get("camel_three", {})
        out["camel_three"][rep] = int((found >= 3).sum())
        for name, S in variants.items():
            lab, si, lam2, W = line(S)
            n0, n1 = int((lab == 0).sum()), int((lab == 1).sum())
            st = stability(S, lab)
            lab10, si10, _l, _w = line(S, 0.10)
            st10 = stability(S, lab10, min_share=0.10)
            keep, eps, ncl = trim(W)
            labt, sit, _l2, _w2 = line(S[keep])
            stt = stability(S[keep], labt)
            out["v"]["%s+%s" % (rep, name)] = {
                "split": [n0, n1], "si": si, "lam2": lam2, "stab": round(st, 3),
                "split10": [int((lab10 == 0).sum()), int((lab10 == 1).sum())], "si10": si10, "stab10": round(st10, 3),
                "trim_left": int((~keep).sum()), "trim_split": [int((labt == 0).sum()), int((labt == 1).sum())],
                "trim_si": sit, "trim_stab": round(stt, 3), "trim_clusters": ncl}
    rows.append(out)
    print("%-22s %-4s n %4d band %s bad %s cubic %s camel3 %s halves@%s" % (
        out["label"][:22], out["group"], out["n"], out["band"], out["bad"], out["cubic_done"],
        out["camel_three"], out.get("halves_cut")))
    for k, v in out["v"].items():
        print("   %-15s split %-10s SI %-6s stab %-6s | 10%%: %-10s SI %-6s stab %-6s | trim -%-3d %-10s SI %-6s stab %s" % (
            k, "%d/%d" % tuple(v["split"]), v["si"], v["stab"], "%d/%d" % tuple(v["split10"]), v["si10"], v["stab10"],
            v["trim_left"], "%d/%d" % tuple(v["trim_split"]), v["trim_si"], v["trim_stab"]))
    sys.stdout.flush()
with open(OUT, "w") as fh:
    json.dump(rows, fh)
print("wrote", OUT)
