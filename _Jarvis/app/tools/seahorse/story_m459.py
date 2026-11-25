# -*- coding: utf-8 -*-
"""Build the data for Seahorse's seizure story: KCNT1 Hom mouse 459, session 1
(2024-12-06), the seizure whose spread is figure A of
Barry Playground/KCNT1 Spreadsheets/KCNT1 mouse 459/Seizure anatomical spread.

    python tools/seahorse/story_m459.py           read the raw once (cached), write the story
    python tools/seahorse/story_m459.py --fresh   read the raw again

Reads the Neuralynx recording on the lab share (64 CSC files, 30 kHz, contacts
50 um apart; CSC1 shallowest) and writes web/seahorse/story_m459.json:

  zones   the probe's dendritic zones, cell layers and hilus (the zones of
          figure B), each with the Seahorse layers it paints
  csd     each zone's current source density, signed (sink < 0), in units of
          its own quiet baseline, 50 samples a second from -12 to +60 s
  absx    each zone's |CSD| change from its own baseline, smoothed (figure A,
          bottom panel)
  mua     each zone's multi-unit activity, x its own baseline
  unit    the hilar interneuron on CSC 41: its firing in 0.25 s bins from
          -10 to +90 s (sorted here the way m459_sort.py sorted it)
  lfp     two channels (CA1 pyramidale, hilus) at 250 Hz, for a real trace
  move    what the video tracker (VT1.nvt) saw move, if anything did

t = 0 is the hilar onset, 888.7 s into the session (m459_panelA_v6.py).
The quiet baseline is 600-660 s (the figures used 400-840 s; a minute of it
is enough for a median and keeps the read small).

Nothing here is a model: every number is measured from the recording.
"""
import argparse
import json
import os
import struct
import sys
import time

import numpy as np
from scipy import signal as sg
from scipy.ndimage import gaussian_filter1d, uniform_filter1d

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, APP)
from backend import nlx  # noqa: E402

SESSION = r"\\netfiles03.uvm.edu\bigdata_jbarry\Jeremy3\KCNT1\Fall'24\Kcnt1_459\kcnt_459_s1Dec6\2024-12-06_13-32-22"
ONSET = 888.7
WIN = (850.0, 1000.0)
BASE = (600.0, 660.0)
FS_LFP = 1000.0
FS_OUT = 50.0
SPAN = (-12.0, 60.0)
CACHE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Jarvis", "seahorse_raw", "m459_s1_cache.npz")
OUT = os.path.join(APP, "web", "seahorse", "story_m459.json")
PITCH_MM = 0.05
BAD = [59]                       # CSC59 is bad (figure B): filled from its neighbours
SORT_CH = list(range(35, 49))    # CSC 35-48: the unit and its neighbours

# key, words, first CSC, last CSC, the Seahorse layers it paints
ZONES = [
    ("ca1o", "CA1 oriens and pyramidale", 1, 10, ["ca1so", "ca1sp"]),
    ("ca1r", "CA1 radiatum and lacunosum-moleculare", 11, 27, ["ca1sr", "ca1slm"]),
    ("supd", "upper blade, distal dendrites", 28, 31, ["oml1", "mml1"]),
    ("supp", "upper blade, proximal dendrites", 33, 34, ["iml1"]),
    ("supg", "upper blade, granule cell layer", 35, 39, ["gcl1"]),
    ("hil", "hilus", 40, 49, ["hil"]),
    ("infg", "lower blade, granule cell layer", 50, 52, ["gcl2"]),
    ("infp", "lower blade, proximal dendrites", 53, 54, ["iml2"]),
    ("infd", "lower blade, distal dendrites", 56, 58, ["mml2", "oml2"]),
]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- the raw
def read_raw():
    """LFP at 1 kHz and MUA at 50 Hz for every channel, story window and
    baseline; the high-passed 30 kHz signal around the unit for the sort."""
    sos_lfp = sg.butter(4, 300, fs=30000, output="sos")
    sos_mua = sg.butter(3, [300, 5000], "band", fs=30000, output="sos")
    sos_hp = sg.butter(3, [300, 6000], "band", fs=30000, output="sos")
    L, M, Lb, Mb, H = [], [], [], [], []
    for c in range(1, 65):
        path = os.path.join(SESSION, "CSC%d.ncs" % c)
        out = []
        for (a, b) in (WIN, BASE):
            x, t0, fs = nlx.read_ncs_range(path, a, b)
            if abs(fs - 30000) > 1 or abs(t0 - a) > 0.02:
                raise SystemExit("CSC%d: unexpected fs %.1f or start %.3f for %.1f" % (c, fs, t0, a))
            n = int(round((b - a) * fs))
            x = x[:n]
            lfp = sg.sosfiltfilt(sos_lfp, x)[::30].astype(np.float32)
            mua = uniform_filter1d(np.abs(sg.sosfiltfilt(sos_mua, x)), 300)[::600].astype(np.float32)
            out.append((lfp, mua))
            if a == WIN[0] and c in SORT_CH:
                H.append((sg.sosfiltfilt(sos_hp, x) * 4).astype(np.int16))      # 0.25 uV steps
        (l, m), (lb, mb) = out
        L.append(l); M.append(m); Lb.append(lb); Mb.append(mb)
        if c % 8 == 0:
            log("read CSC1-%d" % c)
    return dict(L=np.stack(L), M=np.stack(M), Lb=np.stack(Lb), Mb=np.stack(Mb), H=np.stack(H))


def load(fresh):
    if os.path.exists(CACHE) and not fresh:
        z = np.load(CACHE)
        return {k: z[k] for k in z.files}
    log("reading the raw from", SESSION)
    d = read_raw()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp.npz"
    np.savez(tmp, **d)
    os.replace(tmp, CACHE)
    log("cached", CACHE, "%.0f MB" % (os.path.getsize(CACHE) / 1e6))
    return d


# ---------------------------------------------------------------- measures
def fix_bad(X):
    X = X.copy()
    for c in BAD:
        X[c - 1] = 0.5 * (X[c - 2] + X[c])
    return X


def csd(L):
    """-d2V/dz2 (uV/mm2) on 60 Hz LFP, smoothed 1.2 contacts in depth (figure A's recipe)."""
    X = sg.sosfiltfilt(sg.butter(4, 60, fs=FS_LFP, output="sos"), fix_bad(L), axis=1)
    C = -np.diff(gaussian_filter1d(X, 1.2, axis=0), 2, axis=0) / PITCH_MM ** 2
    return np.vstack([np.full((1, C.shape[1]), np.nan), C, np.full((1, C.shape[1]), np.nan)])


def zone_rows(C, a, b):
    return np.nanmean(C[a - 1:b], axis=0)


def to_out(x, fs_in, t_first):
    """Resample a series to FS_OUT on the story's span (t relative to the onset)."""
    t_out = np.arange(SPAN[0], SPAN[1] + 1e-9, 1 / FS_OUT)
    t_in = t_first - ONSET + np.arange(len(x)) / fs_in
    return np.interp(t_out, t_in, x)


def sort_unit(H):
    """The hilar interneuron (m459_sort.py's recipe, on CSC 35-48 of the story window)."""
    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture
    FS = 30000.0
    Hf = H.astype(np.float32) / 4.0
    nC, nS = Hf.shape
    t_base = int((885.0 - WIN[0]) * FS)
    mad = np.median(np.abs(Hf[:, :t_base]), 1) / 0.6745
    evs = []
    for c in range(nC):
        pk, _ = sg.find_peaks(-Hf[c], height=5.0 * mad[c], distance=int(0.0008 * FS))
        evs.append(np.c_[pk, np.full(len(pk), c), Hf[c, pk] / mad[c]])
    E = np.vstack(evs)
    E = E[np.argsort(E[:, 0], kind="stable")]
    keep, i, win = [], 0, int(0.0004 * FS)
    while i < len(E):
        j = i
        while j + 1 < len(E) and E[j + 1, 0] - E[i, 0] <= win:
            j += 1
        keep.append(i + int(np.argmin(E[i:j + 1, 2])))
        i = j + 1
    E = E[keep]
    t = E[:, 0].astype(int)
    pc = E[:, 1].astype(int)
    pre, post = int(0.0006 * FS), int(0.0012 * FS)
    ok = (t > pre) & (t < nS - post) & (pc >= 3) & (pc <= nC - 4)
    t, pc = t[ok], pc[ok]
    W = np.stack([np.stack([Hf[p + d, s - pre:s + post] for d in range(-3, 4)]) for s, p in zip(t, pc)])
    tsec = WIN[0] + t / FS
    base = tsec < 885.0
    F = W.reshape(len(W), -1)
    pca = PCA(8, random_state=0).fit(F[base][::2])
    X = np.c_[pca.transform(F), pc * 40.0]
    rng = np.random.default_rng(0)
    sub = rng.choice(np.flatnonzero(base), min(40000, int(base.sum())), replace=False)
    best = None
    for k in range(4, 13):
        g = GaussianMixture(k, covariance_type="full", random_state=0).fit(X[sub])
        b = g.bic(X[sub])
        if best is None or b < best[0]:
            best = (b, k, g)
    _, K, gmm = best
    lab = gmm.predict(X)
    lab[gmm.predict_proba(X).max(1) < 0.8] = -1
    units = []
    for u in range(K):
        m = (lab == u) & base
        if m.sum() < 100:
            continue
        T = W[m].mean(0)
        main = int(np.argmin(T.min(1)))
        chan = SORT_CH[int(np.median(pc[lab == u])) + main - 3]
        w = T[main]
        up = sg.resample(w, len(w) * 8)
        tr = int(np.argmin(up))
        width = (tr + int(np.argmax(up[tr:tr + int(0.0012 * FS * 8)])) - tr) / (FS * 8) * 1000
        units.append(dict(u=u, chan=int(chan), rate=float(m.sum() / (885.0 - WIN[0])), width=round(width, 3),
                          amp=round(float(-w.min()), 1), n=int((lab == u).sum())))
    log("units:", [(d["u"], d["chan"], round(d["rate"], 1), d["width"]) for d in units])
    return tsec, lab, units


def nvt_motion():
    """What the video tracker saw: per frame, how many points passed its threshold
    and where their middle was. Head-fixed, so any change is the body moving."""
    path = os.path.join(SESSION, "VT1.nvt")
    if not os.path.exists(path):
        return None
    rec = np.dtype([("stx", "<u2"), ("id", "<u2"), ("size", "<u2"), ("ts", "<u8"), ("pts", "<u4", 400),
                    ("crc", "<i2"), ("x", "<i4"), ("y", "<i4"), ("ang", "<i4"), ("tg", "<i4", 50)])
    nrec = (os.path.getsize(path) - 16384) // rec.itemsize
    t_first_csc = None
    with open(os.path.join(SESSION, "CSC1.ncs"), "rb") as fh:
        fh.seek(16384)
        t_first_csc = struct.unpack("<Q", fh.read(8))[0]
    with open(path, "rb") as fh:
        fh.seek(16384)
        first = np.frombuffer(fh.read(rec.itemsize), dtype=rec)[0]
        fps = 29.97
        r0 = max(0, int((t_first_csc + (WIN[0] - 2) * 1e6 - int(first["ts"])) / 1e6 * fps))
        fh.seek(16384 + r0 * rec.itemsize)
        R = np.fromfile(fh, dtype=rec, count=int((WIN[1] - WIN[0] + 4) * fps))
    if not len(R):
        return None
    ts = (R["ts"].astype(np.int64) - int(t_first_csc)) / 1e6
    P = R["pts"]
    n = (P != 0).sum(1)
    xs = (P & 0xFFF).astype(np.float32)
    ys = ((P >> 16) & 0xFFF).astype(np.float32)
    nz = P != 0
    with np.errstate(invalid="ignore"):
        cx = np.where(n > 0, (xs * nz).sum(1) / np.maximum(n, 1), np.nan)
        cy = np.where(n > 0, (ys * nz).sum(1) / np.maximum(n, 1), np.nan)
    # motion: how far the middle of what is seen moves, and how much the count changes
    step = np.hypot(np.diff(cx, prepend=cx[0]), np.diff(cy, prepend=cy[0]))
    dn = np.abs(np.diff(n.astype(np.float32), prepend=float(n[0])))
    return dict(t=ts, n=n.astype(np.float32), step=np.nan_to_num(step), dn=dn, x=R["x"], y=R["y"])


FIG_DIR = os.path.join(os.path.dirname(os.path.dirname(APP)), "Barry Playground", "KCNT1 Spreadsheets", "KCNT1 mouse 459")
IMG_DIR = os.path.join(APP, "web", "seahorse", "story")


def figure_crops():
    """The four recorded CSD snapshots of figure A (1 s each, traces over the CSD),
    cut out for the story's cards. The panels' places come from the figure's own
    gridspec (m459_panelA_v6.py: 24 x 18 in at 300 dpi)."""
    from PIL import Image
    src = os.path.join(FIG_DIR, "Seizure anatomical spread", "KCNT1_m459_A_origin_v6_overlay.png")
    if not os.path.exists(src):
        log("no figure A at", src)
        return []
    im = Image.open(src).convert("RGB")
    os.makedirs(IMG_DIR, exist_ok=True)
    out = []
    for k, (x0, x1) in enumerate([(684, 2044), (2235, 3595), (3785, 5145), (5336, 6696)]):
        box = (x0 - 14, 1700, min(im.width, x1 + 90), 3215)
        c = im.crop(box)
        c = c.resize((620, round(620 * c.height / c.width)), Image.LANCZOS)
        name = "m459_stage%d.jpg" % (k + 1)
        c.save(os.path.join(IMG_DIR, name), quality=86, optimize=True)
        out.append("story/" + name)
    log("figure crops:", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    d = load(a.fresh)
    L, M, Lb, Mb, H = d["L"], d["M"], d["Lb"], d["Mb"], d["H"]
    log("LFP", L.shape, "MUA", M.shape, "sort", H.shape)

    C, Cb = csd(L), csd(Lb)
    # figure A's recipe: each channel against its own quiet baseline, then the zone's mean
    # (averaging signed CSD across a zone first cancels its inner sink-source pairs)
    base_ch = np.nanmedian(np.abs(Cb), axis=1)
    Cn = C / base_ch[:, None]
    A = uniform_filter1d(np.abs(np.nan_to_num(C)), int(0.1 * FS_LFP), axis=1)
    Ab = uniform_filter1d(np.abs(np.nan_to_num(Cb)), int(0.1 * FS_LFP), axis=1)
    R = A / np.median(Ab, 1, keepdims=True)
    Mn = M / np.median(Mb, 1, keepdims=True)
    # m459_spread.py's activity measure: MUA as a robust z-score against the quiet baseline
    mb_med = np.median(Mb, 1, keepdims=True)
    Mz = (M - mb_med) / (1.4826 * np.median(np.abs(Mb - mb_med), 1, keepdims=True))
    t_lfp = WIN[0] + np.arange(C.shape[1]) / FS_LFP
    t_mua = WIN[0] + np.arange(M.shape[1]) / 50.0
    zones, sig, absx, mua = [], {}, {}, {}
    for key, words, a0, a1, lam in ZONES:
        sig[key] = to_out(gaussian_filter1d(np.nanmean(Cn[a0 - 1:a1], 0), 0.01 * FS_LFP), FS_LFP, WIN[0])
        ab = gaussian_filter1d(np.nanmean(R[a0 - 1:a1], 0), 0.08 * FS_LFP)
        absx[key] = to_out(ab, FS_LFP, WIN[0])
        mz = gaussian_filter1d(Mn[a0 - 1:a1].mean(0), 0.1 * 50)
        mua[key] = to_out(mz, 50.0, WIN[0])
        # when it went quiet: the last time its MUA z-score held above 6 for 0.3 s (m459_spread.py's
        # threshold). When it joined is figure A's, read by eye from the recording, not recomputed here.
        on = None
        zz = uniform_filter1d(Mz[a0 - 1:a1].mean(0), 5)
        okm = (zz > 6) & (t_mua > 905) & (t_mua < 950)
        km = int(0.3 * 50)
        off = None
        for i in np.flatnonzero(okm):
            if okm[i:i + km].mean() > 0.8:
                off = t_mua[min(len(t_mua) - 1, i + km)]
        zones.append(dict(key=key, words=words, csc=[a0, a1], layers=lam,
                          off_s=None if off is None else round(float(off - ONSET), 2)))
        log("%-5s peak sink %.0fx  peak |CSD| %.0fx  peak MUA %.0fx  quiet from %s s" % (
            key, -np.nanmin(sig[key]), absx[key].max(), mua[key].max(), zones[-1]["off_s"]))
    # the dentate's discharges (m459_zones.py: summed |CSD| over CSC 28-58 above median + 15 MAD of the baseline)
    dg = uniform_filter1d(np.nansum(np.abs(np.nan_to_num(C[27:58])), 0), int(0.01 * FS_LFP))
    dgb = uniform_filter1d(np.nansum(np.abs(np.nan_to_num(Cb[27:58])), 0), int(0.01 * FS_LFP))
    thr = np.median(dgb) + 15 * np.median(np.abs(dgb - np.median(dgb))) / 0.6745
    pk, _ = sg.find_peaks(dg, height=thr, distance=int(0.06 * FS_LFP), prominence=thr * 0.5)
    dis = [round(float(t_lfp[i] - ONSET), 3) for i in pk]
    log("discharges: %d before onset (850 s on), %d from onset to +60 s" % (sum(1 for t in dis if t < 0), sum(1 for t in dis if 0 <= t <= 60)))

    tsec, lab, units = sort_unit(H)
    # the unit: on CSC 41, the narrowest, nearest 13.7 Hz at baseline (figure A)
    cands = [u for u in units if abs(u["chan"] - 41) <= 1] or units
    pick = min(cands, key=lambda u: (abs(u["chan"] - 41), abs(u["rate"] - 13.7)))
    st = np.sort(tsec[lab == pick["u"]]) - ONSET
    edges = np.arange(-10.0, 90.0 + 1e-9, 0.25)
    rate = np.histogram(st, edges)[0] / 0.25
    log("unit", pick, "pre-onset 3 s: %.1f Hz, 3-80 s after: %.2f Hz" % (rate[(edges[:-1] >= -3) & (edges[:-1] < 0)].mean(),
                                                                        rate[(edges[:-1] >= 3) & (edges[:-1] < 80)].mean()))

    lf = {}
    for c, name in ((7, "CA1 pyramidale"), (44, "hilus")):
        x = sg.sosfiltfilt(sg.butter(4, [1, 100], "band", fs=FS_LFP, output="sos"), fix_bad(L)[c - 1])[::4]
        t_in = WIN[0] - ONSET + np.arange(len(x)) / 250.0
        keep = (t_in >= SPAN[0]) & (t_in <= SPAN[1])
        lf[str(c)] = dict(words=name, uv=[int(v) for v in np.round(x[keep])])

    mv = nvt_motion()
    move = None
    if mv is not None:
        rel = mv["t"] - ONSET
        keep = (rel >= SPAN[0]) & (rel <= SPAN[1])
        if keep.sum() > 100:
            move = dict(fps=29.97, t0=round(float(rel[keep][0]), 3),
                        n=[int(v) for v in mv["n"][keep]], step=[round(float(v), 1) for v in mv["step"][keep]])
            log("tracker: %d frames, points per frame median %d (range %d-%d)" % (keep.sum(), np.median(mv["n"][keep]),
                                                                              mv["n"][keep].min(), mv["n"][keep].max()))

    r2 = lambda arr: [round(float(v), 2) for v in arr]
    story = dict(
        what="KCNT1 Hom mouse 459, session 1 (2024-12-06), awake head-fixed, 64-contact linear probe 50 um apart",
        source="Neuralynx recording " + SESSION.split("\\Jeremy3\\")[-1].replace("\\", "/"),
        built=time.strftime("%Y-%m-%d"), onset_s=ONSET, fs=FS_OUT, t0=SPAN[0], t1=SPAN[1],
        baseline_s=list(BASE), zones=zones, discharges=[t for t in dis if SPAN[0] - 30 <= t <= SPAN[1]],
        csd={k: r2(v) for k, v in sig.items()}, absx={k: r2(v) for k, v in absx.items()}, mua={k: r2(v) for k, v in mua.items()},
        unit=dict(csc=pick["chan"], width_ms=pick["width"], baseline_hz=round(pick["rate"], 1), bin_s=0.25, t0=-10.0,
                  hz=[round(float(v), 1) for v in rate]),
        lfp=dict(fs=250.0, t0=SPAN[0], ch=lf),
        snapshots=figure_crops(),
        move=move,
    )
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(story, fh, separators=(",", ":"))
    os.replace(tmp, OUT)
    log("wrote", OUT, "%.0f KB" % (os.path.getsize(OUT) / 1e3))


if __name__ == "__main__":
    main()
