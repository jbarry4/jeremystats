"""Does the Bite line follow the camel's bookkeeping? And does merging a camel
into one bump fix it?

Per recording: the default line under today's bumps; how much of its smaller
side is events whose profile had three or more bumps (a camel split at zero);
then the same line under
  merge G   two bumps whose zero stretch between them is at most G contacts
            are one bump, before the top two are taken (G = 1, 2, 3)
  halves    the recording's two humps: the band cut at the source of the mean
            profile between its two biggest sinks; each event's negative side
            in each half, the halves weighted equally
  whole     the whole negative side in the band
-- split, SI, stability (mean ARI over 25 random 80% refits).
Usage: camel_merge.py [version] [label filter]"""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camel_merge.json")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import sinkcut  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import adjusted_rand_score  # noqa: E402

VERSION = int(sys.argv[1]) if len(sys.argv) > 1 else 4
ONLY = sys.argv[2] if len(sys.argv) > 2 else None
room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], VERSION)
RNG = np.random.default_rng(0)


def signed(A_, half_ms=3.0):
    disp = np.asarray(A_["disp"], dtype=float)
    ns = [int(n) for n in A_["nums_sel"]]
    na = [int(n) for n in A_["nums_all"]]
    rows = sinkcut.band_rows(na, ns)
    fs, t0 = sinkcut.time_axis(disp.shape[2])
    h = int(round(half_ms * fs / 1000.0))
    return disp[:, rows, t0 - h:t0 + h + 1].mean(axis=2), ns


def merged_bumps(row, G):
    """sinkcut.bumps, then neighbours whose zero stretch is <= G merged."""
    bb = sinkcut.bumps(row)
    out = []
    for a, b, s in bb:
        if out and a - out[-1][1] <= G:
            pa, pb, ps = out[-1]
            out[-1] = (pa, b, ps + s)
        else:
            out.append((a, b, s))
    return out


def S_merge(neg, G):
    S = np.zeros_like(neg)
    found = []
    for i, row in enumerate(neg):
        bb = sorted(merged_bumps(row, G), key=lambda b: -b[2])
        found.append(len(bb))
        for a, b, _ in bb[:2]:
            S[i, a:b] = row[a:b]
    return S, np.asarray(found)


def halves_cut(prof):
    m = prof.mean(axis=0)
    neg = np.maximum(0.0, -m)
    bb = sorted(sinkcut.bumps(neg), key=lambda b: -b[2])[:2]
    if len(bb) < 2:
        return None
    (a1, b1, _), (a2, b2, _) = sorted(bb, key=lambda b: b[0])
    seg = m[b1:a2]
    if not seg.size:
        return b1
    return b1 + int(np.argmax(seg))


def S_halves(neg, cut):
    top, bot = neg[:, :cut + 1], neg[:, cut + 1:]
    st, sb = top.sum(axis=1, keepdims=True), bot.sum(axis=1, keepdims=True)
    return np.hstack([np.divide(top, st, out=np.zeros_like(top), where=st > 0),
                      np.divide(bot, sb, out=np.zeros_like(bot), where=sb > 0)])


def norm(S):
    m = S.sum(axis=1, keepdims=True)
    return np.divide(S, m, out=np.zeros_like(S), where=m > 0)


def line(S, min_share=0.02):
    W = sinkcut.overlap(S)
    idx, coord, lam2 = sinkcut.order(sinkcut.affinity(W), sinkcut.centroid(S))
    live = idx[np.isfinite(coord[idx])]
    sw = sinkcut.sweep(W, live, min_share, sinkcut.MIN_EVENTS)
    k = sw["best"]
    lab = np.full(S.shape[0], -1)
    lab[live[:k]] = 0
    lab[live[k:]] = 1
    return lab, sw["si"][k - 1]


def stability(S, lab, reps=25, frac=0.8):
    n = S.shape[0]
    out = []
    for _ in range(reps):
        sub = np.sort(RNG.choice(n, int(frac * n), replace=False))
        l2, _si = line(S[sub])
        ok = (lab[sub] >= 0) & (l2 >= 0)
        out.append(adjusted_rand_score(lab[sub][ok], l2[ok]))
    return float(np.mean(out))


rows = []
for rec in pay["recordings"]:
    if ONLY and ONLY not in rec["session_label"]:
        continue
    if rec["n"] < 20:
        continue
    Ar, _rule, _flip = A._er_split_arrays(dict(rec, direct=True))
    prof, ns = signed(Ar)
    neg = np.maximum(0.0, -prof)
    out = {"label": rec["session_label"], "group": rec.get("group"), "n": int(neg.shape[0]),
           "band": [rec["box"]["sel_lo"], rec["box"]["sel_hi"]], "v": {}}
    Sb, found = S_merge(neg, 0)                     # G = 0: today's bumps
    lab, si = line(norm(Sb))
    small = 0 if (lab == 0).sum() <= (lab == 1).sum() else 1
    three = found >= 3
    out["camel_split_events"] = int(three.sum())
    out["small_side"] = int((lab == small).sum())
    out["small_side_camel"] = int(((lab == small) & three).sum())
    variants = {"bumps": norm(Sb)}
    for G in (1, 2, 3):
        variants["merge%d" % G] = norm(S_merge(neg, G)[0])
    cut = halves_cut(prof)
    if cut is not None:
        variants["halves"] = norm(S_halves(neg, cut))
        out["halves_at"] = ns[cut]
    variants["whole"] = norm(neg)
    for name, S in variants.items():
        l2, si2 = line(S)
        st = stability(S, l2)
        out["v"][name] = {"split": [int((l2 == 0).sum()), int((l2 == 1).sum())], "si": si2, "stab": round(st, 3),
                          "ari_vs_bumps": round(adjusted_rand_score(lab[(lab >= 0) & (l2 >= 0)], l2[(lab >= 0) & (l2 >= 0)]), 3)}
    rows.append(out)
    print("%-22s %-4s n %4d band %s | camel-split events %d; smaller side %d, of them camel-split %d | halves at %s" % (
        out["label"][:22], out["group"], out["n"], out["band"], out["camel_split_events"], out["small_side"],
        out["small_side_camel"], out.get("halves_at")))
    for k, v in out["v"].items():
        print("    %-7s split %-9s SI %-7s stab %-6s same as bumps (ARI) %s" % (
            k, "%d/%d" % tuple(v["split"]), v["si"], v["stab"], v["ari_vs_bumps"]))
    sys.stdout.flush()
with open(OUT, "w") as fh:
    json.dump(rows, fh)
print("wrote", OUT)
