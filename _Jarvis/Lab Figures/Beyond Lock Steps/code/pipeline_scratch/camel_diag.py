"""The camel hump: is a contact bad, drifting, or is the dip real?

For each recording of the room's v4 (the Halo set) read:
  per contact, on the band-limited LFP (5-100 Hz, what the CSD is made of):
    g     its RMS over the geometric mean of its two neighbours' (1 = smooth)
    a     the slope of V[c] on the mean of its neighbours, baseline only
          (|t| > 30 ms, no spike), and over the stamp (|t| <= 5 ms)
    rn    the residual V[c] - mean(neighbours) in the baseline, over its RMS
  per event, from the CSD at the stamp (+-3 ms) inside the band:
    where its sink bumps have a dip inside them (a camel), and at which contact
  drift: a in four blocks of events in time order.
Writes camel_diag.json beside this script and prints a summary."""
import json
import os
import sys

APP = r"c:\Users\Z390\Desktop\jeremystats\_Jarvis\app"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camel_diag.json")
os.chdir(APP)
sys.path.insert(0, APP)
import logging  # noqa: E402
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from backend import app as A  # noqa: E402
from backend import dspca  # noqa: E402
import numpy as np  # noqa: E402

VERSION = int(sys.argv[1]) if len(sys.argv) > 1 else 4
ONLY = sys.argv[2] if len(sys.argv) > 2 else None
room = A._er_rooms().get("dentate_spike")
pay = A.ARTIFACTS.payload(room["id"], VERSION)


def slope(y, x):
    x = x - x.mean()
    y = y - y.mean()
    d = float((x * x).sum())
    return float((x * y).sum() / d) if d > 0 else float("nan")


def camels(neg, nums_sel, rel=0.8):
    """Each event's negative CSD profile (events x contacts, >= 0): for each
    stretch above zero, its interior local minima that fall below `rel` of the
    smaller of the two peaks either side. Returns a list of dip contacts per
    event and how many stretches had one."""
    out = []
    for row in neg:
        dips = []
        on = row > 0
        edge = np.diff(np.concatenate([[0], on.astype(np.int8), [0]]))
        lo, hi = np.flatnonzero(edge == 1), np.flatnonzero(edge == -1)
        for a, b in zip(lo, hi):
            seg = row[a:b]
            if seg.size < 3:
                continue
            for j in range(1, seg.size - 1):
                if seg[j] < seg[j - 1] and seg[j] <= seg[j + 1]:
                    left, right = seg[:j].max(), seg[j + 1:].max()
                    if seg[j] < rel * min(left, right):
                        dips.append(int(nums_sel[a + j]))
        out.append(dips)
    return out


rows_out = []
for rec in pay["recordings"]:
    if ONLY and ONLY not in rec["session_label"]:
        continue
    gid, rh = rec["gid"], rec.get("read")
    try:
        got = A._dspca_load(gid, rh)
    except Exception as exc:  # noqa: BLE001
        print(rec["session_label"], "no read:", exc)
        continue
    nums = [int(n) for n in got["nums"]]
    bad = {int(k) for k in (got.get("bad") or {})}
    sur = np.asarray(got["sur"]["band"], dtype=float)          # E x C x T, uV
    E, C, T = sur.shape
    t = np.linspace(-50, 50, T)
    base = np.abs(t) > 30
    at = np.abs(t) <= 5
    order = np.argsort([float(r.get("stamp_s") or 0) for r in got["rows"]])
    rms = np.sqrt((sur ** 2).mean(axis=(0, 2)))
    per = []
    for c in range(1, C - 1):
        if nums[c] in bad or nums[c - 1] in bad or nums[c + 1] in bad:
            per.append(None)
            continue
        nb = 0.5 * (sur[:, c - 1, :] + sur[:, c + 1, :])
        v = sur[:, c, :]
        g = rms[c] / np.sqrt(rms[c - 1] * rms[c + 1]) if rms[c - 1] > 0 and rms[c + 1] > 0 else float("nan")
        a_b = slope(v[:, base].ravel(), nb[:, base].ravel())
        a_s = slope(v[:, at].ravel(), nb[:, at].ravel())
        rn = float(np.std((v - nb)[:, base]) / (np.sqrt((v[:, base] ** 2).mean()) or 1))
        blocks = []
        for blk in np.array_split(order, 4):
            blocks.append(round(slope(v[blk][:, base].ravel(), nb[blk][:, base].ravel()), 3))
        per.append({"num": nums[c], "g": round(float(g), 3), "a_base": round(a_b, 3),
                    "a_stamp": round(a_s, 3), "rn": round(rn, 3), "blocks": blocks})
    # The CSD the room uses, in the record's band, and its camels.
    band = rec.get("box") or {}
    p = A._er_fit_params(got, band)
    res = dspca.fit(got, p, layers=A._dspca_layers(gid))
    disp = np.asarray(res["disp"], dtype=float)               # E x C x T (CSD)
    lo_n, hi_n = int(band["sel_lo"]), int(band["sel_hi"])
    sel = [i for i, n in enumerate(nums) if lo_n <= n <= hi_n]
    win = np.abs(t) <= 3
    prof = disp[:, sel][:, :, win].mean(axis=2)
    neg = np.clip(-prof, 0, None)
    dips = camels(neg, [nums[i] for i in sel])
    flat = [d for row in dips for d in row]
    hist = {}
    for d in flat:
        hist[d] = hist.get(d, 0) + 1
    n_cam = sum(1 for row in dips if row)
    # The mean CSD profile at the stamp across the whole shank, for the picture.
    mean_prof = disp[:, :, win].mean(axis=(0, 2))
    out = {"label": rec["session_label"], "gid": gid, "read": rh, "group": rec.get("group"),
           "n": E, "bad": sorted(bad), "band": [lo_n, hi_n], "probe": got.get("probe"),
           "spacing": got.get("spacing_um"),
           "per": per, "camel_events": n_cam, "camel_frac": round(n_cam / max(1, E), 3),
           "dip_hist": dict(sorted(hist.items())), "mean_prof": [round(float(x), 2) for x in mean_prof],
           "rms": [round(float(x), 2) for x in rms]}
    rows_out.append(out)
    # The summary line: contacts whose g or a stands out.
    odd = [x for x in per if x and (abs(x["g"] - 1) > 0.08 or abs(x["a_base"] - 1) > 0.08 or x["rn"] > 0.15)]
    top_d = sorted(hist.items(), key=lambda kv: -kv[1])[:4]
    print("%-24s %-4s n %4d band %d-%d bad %s | camel %3d%% dips at %s" % (
        rec["session_label"][:24], rec.get("group"), E, lo_n, hi_n, sorted(bad),
        round(100 * n_cam / max(1, E)), ", ".join("%d(%d)" % kv for kv in top_d)))
    for x in odd:
        inb = lo_n - 3 <= x["num"] <= hi_n + 3
        print("      %s contact %2d  g %.3f  a_base %.3f  a_stamp %.3f  rn %.3f  blocks %s" % (
            "*" if inb else " ", x["num"], x["g"], x["a_base"], x["a_stamp"], x["rn"], x["blocks"]))
with open(OUT, "w") as fh:
    json.dump(rows_out, fh)
print("wrote", OUT)
