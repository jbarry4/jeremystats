"""Are contacts 38/39 on m6 s4 at fault? Five tests on its read (room v8).

A  gain against the cubic through two neighbours a side, on the voltage,
   its first and its second time derivative (low, middle, high frequencies
   weighted), baseline only (|t| > 30 ms)
B  a swap in the channel map: each adjacent pair's cubic misfit as wired and
   with the two swapped (a swapped pair fits far better swapped)
C  where the notch in the top hump sits, event by event, against where its
   two sub-sinks sit (a fault holds still; anatomy moves)
D  every recording: does its mean CSD have a notch at 38/39 wherever its
   humps are?
E  38 and 39 rebuilt by the cubic from 36, 37, 40, 41 -- and, as a control,
   a pair nobody suspects -- and the Bite line again
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import numpy as np  # noqa: E402
from backend import app as A  # noqa: E402
from backend import dspca, sinkcut  # noqa: E402
from backend import extraction as EX  # noqa: E402

room = A._er_rooms()["dentate_spike"]
pay = A.ARTIFACTS.payload(room["id"], 8)
rec = next(r for r in pay["recordings"] if "m6 s4" in r["session_label"])
got = A._dspca_load(rec["gid"], rec["read"])
nums = [int(n) for n in got["nums"]]
bad = {int(k) for k in (got.get("bad") or {})}
E, C, T = np.asarray(got["sur"]["band"]).shape
t = np.linspace(-50, 50, T)
base = np.abs(t) > 30
print("m6 s4: %d events, %d contacts, %d samples (fs %s), probe %s, spacing %s um, bad %s, band %s-%s" % (
    E, C, T, got.get("fs"), got.get("probe"), got.get("spacing_um"), sorted(bad),
    rec["box"]["sel_lo"], rec["box"]["sel_hi"]))
print("contact order in the read: %s ... %s (monotone: %s)" % (nums[:4], nums[-4:], all(np.diff(nums) > 0)))
ix = {n: i for i, n in enumerate(nums)}


def slope(y, x):
    x = x - x.mean()
    y = y - y.mean()
    d = float((x * x).sum())
    return float((x * y).sum() / d) if d > 0 else float("nan")


def stencil(X, i):
    return (-X[:, i - 2] + 4 * X[:, i - 1] + 4 * X[:, i + 1] - X[:, i + 2]) / 6.0


# A
print("\nA  gain against the cubic from two neighbours a side, baseline; V, dV/dt, d2V/dt2 (median of all contacts = 1)")
for key in ("band", "raw"):
    X0 = np.asarray(got["sur"][key], dtype=float)
    rows = {}
    for name, X in (("V", X0), ("dV/dt", np.diff(X0, axis=2)), ("d2V/dt2", np.diff(X0, n=2, axis=2))):
        b = base[:X.shape[2]]
        g = {}
        for i in range(2, C - 2):
            if any(nums[k] in bad for k in range(i - 2, i + 3)):
                continue
            g[nums[i]] = slope(X[:, i][:, b].ravel(), stencil(X, i)[:, b].ravel())
        med = np.median(list(g.values()))
        mad = np.median(np.abs(np.array(list(g.values())) - med))
        rows[name] = (g, med, mad)
    print("  signal %-5s %s" % (key, "  ".join("%s MAD %.2f%%" % (k, 100 * v[2]) for k, v in rows.items())))
    for n in range(32, 45):
        print("     contact %2d  %s" % (n, "  ".join(
            ("%-8s %+6.2f%%" % (k, 100 * (v[0][n] / v[1] - 1))) if n in v[0] else "%-8s   --  " % k
            for k, v in rows.items())))

# B
print("\nB  a swapped pair: cubic misfit at the four contacts around each pair, swapped / as wired (<<1 = wired wrong)")
for key in ("band", "raw"):
    X = np.asarray(got["sur"][key], dtype=float)
    out = []
    for n in range(32, 46):
        i = ix[n]
        if any(nums[k] in bad for k in range(i - 3, i + 5)):
            continue

        def misfit(Y):
            return sum(float(np.mean((Y[:, k] - stencil(Y, k)) ** 2)) for k in range(i - 1, i + 3))
        Y = X.copy()
        Y[:, [i, i + 1]] = Y[:, [i + 1, i]]
        out.append("%d/%d %.2f" % (n, n + 1, misfit(Y) / misfit(X)))
    print("  %-5s %s" % (key, "  ".join(out)))

# C
A8, _r, _f = A._er_split_arrays(rec)
prof, ns = sinkcut.stamp_profiles(A8)
neg = np.maximum(0.0, -prof)
cut = sinkcut.hump_cut(prof.mean(axis=0))
top = neg[:, :cut]
nt, pk1, pk2 = [], [], []
for r in top:
    bb = sinkcut.bumps(r)
    if len(bb) < 2:
        continue
    two = sorted(sorted(bb, key=lambda b: -b[2])[:2])
    a1, e1 = two[0][0], two[0][1]
    a2 = two[1][0]
    pk1.append(ns[a1 + int(np.argmax(r[a1:e1]))])
    pk2.append(ns[a2 + int(np.argmax(r[a2:two[1][1]]))])
    gap = r[e1 - 1:a2 + 1]
    nt.append(ns[e1 - 1 + int(np.argmin(gap))])
print("\nC  top hump %s-%s: %d of %d events have two sub-sinks there" % (ns[0], ns[cut - 1], len(nt), E))
for name, v in (("upper sub-sink", pk1), ("notch", nt), ("lower sub-sink", pk2)):
    vals, cnt = np.unique(v, return_counts=True)
    print("   %-15s %s" % (name, "  ".join("%d:%d" % (a, b) for a, b in zip(vals, cnt))))
mp = prof.mean(axis=0)
print("   mean CSD at the stamp, top hump:", " ".join("%d:%+.2f" % (ns[j], mp[j]) for j in range(cut)))

# D
print("\nD  every recording's mean stamp CSD: its top hump, and any notch (a local rise inside a sink) in it")
for r in pay["recordings"]:
    Ar, _a, _b = A._er_split_arrays(r)
    pr, nn = sinkcut.stamp_profiles(Ar)
    m = pr.mean(axis=0)
    cc = sinkcut.hump_cut(m)
    notches = [nn[j] for j in range(1, len(m) - 1) if m[j] < 0 and m[j] > m[j - 1] and m[j] > m[j + 1]
               and min(m[j - 1], m[j + 1]) < 0]
    print("   %-22s band %s-%s, humps part at %s, notches at %s" % (
        r["session_label"][:22], nn[0], nn[-1], nn[cc] if cc is not None else None, notches))

# E
print("\nE  rebuilt by the cubic from the two good contacts either side of the pair, then the Bite line")


def rebuild_pair(g, pair):
    out = dict(g)
    out["sur"] = {}
    for key, X in g["sur"].items():
        X = np.array(X, dtype=float, copy=True)
        i, j = ix[pair[0]], ix[pair[1]]
        pts = [i - 2, i - 1, j + 1, j + 2]
        for k in (i, j):
            w = EX._lagrange_at(pts, k)
            X[:, k] = sum(wk * X[:, p] for wk, p in zip(w, pts))
        out["sur"][key] = X
    return out


lay = A._dspca_layers(rec["gid"])
for name, g in (("as read", got), ("38+39 rebuilt", rebuild_pair(got, (38, 39))),
                ("33+34 rebuilt (control)", rebuild_pair(got, (33, 34))),
                ("42+43 rebuilt (control)", rebuild_pair(got, (42, 43)))):
    p = A._er_fit_params(g, rec["box"])
    res = dspca.fit(g, p, layers=lay)
    Ar = EX.split_arrays(res)
    EX.add_bite(Ar, str(p.rule), bool(p.flip))
    v = EX.bite_view(Ar)
    pr, nn = sinkcut.stamp_profiles(Ar)
    m = pr.mean(axis=0)
    print("   %-24s Bite %s/%s SI %.3f (%s) | humps part at %s | notched events %d | mean CSD 34-42: %s" % (
        name, v["scores"]["n1"], v["scores"]["n2"], v["scores"]["si"], v["verdict"]["word"],
        v["bumps"]["hump_at"], v["bumps"]["camel"],
        " ".join("%+.2f" % m[nn.index(c)] for c in range(34, 43))))
