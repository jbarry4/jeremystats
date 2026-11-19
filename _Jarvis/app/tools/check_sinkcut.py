# -*- coding: utf-8 -*-
"""check_sinkcut.py -- the Bite line's sink and the blobs, on made-up
recordings whose answer is known (2026-11-12, "the camel hump").

    python tools/check_sinkcut.py

ONE FAMILY WITH A NOTCH. Every event has two humps (one per blade); the top
hump has two sub-sinks with a notch between, and on some events the notch
reaches zero. Taking each event's own two biggest bumps then counts the top
hump's halves as "the two", and the line splits off the events whose notch
touched zero -- a split made of bookkeeping. The recording's two humps
(sink="humps", the default) must see one family.

TWO FAMILIES. DS1's sinks sit further apart than DS2's (outer vs middle
molecular layer, in both blades). The humps must still find them.

Exits 1 when any check fails.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402

from backend import sinkcut, blobs  # noqa: E402

FAILS = []


def ck(name, ok, detail=""):
    print("%s  %s%s" % ("ok  " if ok else "FAIL", name, ("  -- " + detail) if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def ari(a, b):
    from sklearn.metrics import adjusted_rand_score
    return adjusted_rand_score(a, b)


D, T, T0 = 30, 101, 50
z = np.arange(D, dtype=float)
t = np.arange(T, dtype=float) - T0
TIME = np.exp(-(t ** 2) / (2 * 4.0 ** 2))


def gauss(c, w):
    return np.exp(-((z - c) ** 2) / (2 * w ** 2))


def event(sinks, sources, rng, noise=0.01):
    """One event's CSD (sinks negative): depth shape x time course."""
    prof = np.zeros(D)
    for c, w, a in sinks:
        prof -= a * gauss(c, w)
    for c, w, a in sources:
        prof += a * gauss(c, w)
    return prof[:, None] * TIME[None, :] + noise * rng.standard_normal((D, T))


def arrays(disp):
    n = disp.shape[0]
    return {"disp": disp, "prof": np.zeros((n, D)), "nums_sel": np.arange(1, D + 1),
            "nums_all": np.arange(1, D + 1)}


rng = np.random.default_rng(1)

# ---- one family, a notched top hump --------------------------------------
N, NOTCH = 200, 30
evs, notched = [], np.zeros(N, dtype=bool)
for i in range(N):
    deep = i < NOTCH                         # the notch reaches zero on these
    j = rng.normal(0, 0.15)
    # Two sub-sinks 5 contacts apart: between them the sink is about 0.31,
    # so a notch of 0.12 leaves it a sink and one of 0.45 just takes it past
    # zero -- the events differ by a sliver, not by half a hump.
    top = [(6 + j, 1.3, 1.0), (11 + j, 1.3, 1.0)]
    src_notch = [(8.5 + j, 0.6, 0.45 if deep else 0.12)]
    evs.append(event(top + [(22 + j, 1.6, 1.3)],
                     src_notch + [(16.5 + j, 1.6, 0.9)], rng))
    notched[i] = deep
disp = np.array(evs)
A1 = arrays(disp)

Fb = sinkcut.fit(A1, sink="bumps")
lab_b = np.zeros(N, dtype=int)
lab_b[Fb["live"][:Fb["k"]]] = 1
small_b = lab_b if lab_b.sum() <= N / 2 else 1 - lab_b
vb = sinkcut.view(Fb)
ck("each event's own bumps: the small side is the notched events (the bug this fixes)",
   ari(small_b, notched.astype(int)) > 0.6,
   "ARI %.2f SI %s" % (ari(small_b, notched.astype(int)), vb["scores"]["si"]))

Fh = sinkcut.fit(A1)                         # the default
vh = sinkcut.view(Fh)
ck("the default sink is the recording's two humps", Fh["params"]["sink"] == "humps"
   and vh["bumps"]["sink"] == "humps")
ck("hump_cut parts them at the source between (contact 17 or 18)",
   vh["bumps"]["hump_at"] in (17, 18, 19), str(vh["bumps"]["hump_at"]))
ck("under the humps the notched recording is one family (SI under the partial line)",
   vh["scores"]["si"] < sinkcut.PARTIAL_SI, str(vh["scores"]["si"]))
lab_h = np.zeros(N, dtype=int)
lab_h[Fh["live"][:Fh["k"]]] = 1
ck("... and the line no longer follows the notch",
   abs(ari(lab_h, notched.astype(int))) < 0.2, "ARI %.2f" % ari(lab_h, notched.astype(int)))
ck("the notched events are counted as camels, every one of them kept as one hump",
   vh["bumps"]["camel"] >= NOTCH and all(len(p) == 2 for p in vh["bumps"]["peaks"]),
   "camel %s" % vh["bumps"]["camel"])
ck("each event's peaks: one in each hump, the top one above the part",
   all(p[0] < vh["bumps"]["hump_at"] <= p[1] for p in vh["bumps"]["peaks"]))
S = Fh["S"]
top_mass = S[:, :vh["bumps"]["hump_at"] - 1].sum(axis=1)
ck("each hump weighs the same in every event's sink", np.allclose(top_mass, 0.5, atol=1e-9),
   "%.3f..%.3f" % (top_mass.min(), top_mass.max()))

# ---- two families ---------------------------------------------------------
N2, K2 = 200, 60
evs, fam = [], np.zeros(N2, dtype=int)
for i in range(N2):
    ds2 = i < K2
    j = rng.normal(0, 0.3)
    up, lo = (9.0, 19.0) if ds2 else (5.0, 23.0)    # DS2's sinks are closer
    evs.append(event([(up + j, 1.2, 1.0), (lo + j, 1.4, 1.2)], [(14 + j, 2.0, 0.8)], rng))
    fam[i] = int(ds2)
A2 = arrays(np.array(evs))
F2 = sinkcut.fit(A2)
v2 = sinkcut.view(F2)
lab2 = np.zeros(N2, dtype=int)
lab2[F2["live"][:F2["k"]]] = 1
ck("two families: the humps find them (ARI > 0.9) and call them separate",
   ari(lab2, fam) > 0.9 and v2["verdict"]["word"] == "separate",
   "ARI %.2f SI %s" % (ari(lab2, fam), v2["scores"]["si"]))

# ---- the blobs ------------------------------------------------------------
ev = blobs.event_blobs(disp, list(range(D)), 50.0, fs=1000.0, t0=T0)
part = ev["hump_row"]
ck("the blobs are the humps too", ev["sink"] == "humps" and part is not None)
spans = ev["top"]["span"][notched]
ck("a notched event's top blob is its whole top hump, notch and all (both sub-sinks)",
   bool(np.all(spans[:, 0] <= 6) and np.all(spans[:, 1] >= 11) and np.all(spans[:, 1] < part)),
   "spans %s" % spans[:3].tolist())
ck("every event has a top and a bottom blob", bool(ev["top"]["has"].all() and ev["bottom"]["has"].all()))
evb = blobs.event_blobs(disp, list(range(D)), 50.0, fs=1000.0, t0=T0, sink="bumps")
top_b = evb["top"]["span"][notched]
ck("(each event's own bumps gave a notched event half its top hump as its top blob)",
   bool(np.mean((top_b[:, 0] <= 6) & (top_b[:, 1] >= 11)) < 0.5), "top spans %s" % top_b[:3].tolist())
summ = blobs.recording_summary(ev)
ck("the summary says what a blob is and how many were notched",
   summ["sink"] == "humps" and summ["camel"] >= NOTCH, "%s %s" % (summ["sink"], summ["camel"]))

print()
print("%d check(s) failed" % len(FAILS) if FAILS else "all checks passed")
sys.exit(1 if FAILS else 0)
