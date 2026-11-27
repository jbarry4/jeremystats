# -*- coding: utf-8 -*-
"""Build the data for Seahorse's seizure story: KCNT1 Hom mouse 459, session 1
(2024-12-06), the seizure whose spread is figure A of
Barry Playground/KCNT1 Spreadsheets/KCNT1 mouse 459/Seizure anatomical spread.

    python tools/seahorse/story_m459.py           read the raw once (cached), write the story
    python tools/seahorse/story_m459.py --fresh   read the raw again
    python tools/seahorse/story_m459.py --fetch --cache PATH
                                                  only read the raw into a cache (on a machine
                                                  that sees the share, e.g. a VACC compute node)

Reads the Neuralynx recording on the lab share (64 CSC files, 30 kHz; CSC1
shallowest; an H3 probe by Cheetah's log, 20 um apart, where the figures say 50).
Off campus the share is reachable from a VACC compute node (the login nodes'
netfiles mount refused with "Protocol not supported" on 11-25): run --fetch
there with the cluster's Python and copy the cache to
%LOCALAPPDATA%/Jarvis/seahorse_raw/m459_s1_cache.npz; the build needs nothing else.

Writes web/seahorse/story_m459.json:

  zones   the probe's dendritic zones, cell layers and hilus (the zones of
          figure B), each with the Seahorse layers it paints
  csd     each zone's current source density, signed (sink < 0), in units of
          its own quiet baseline, 50 samples a second from -12 to +60 s
  absx    each zone's |CSD| change from its own baseline, smoothed (figure A,
          bottom panel)
  mua     each zone's multi-unit activity, x its own baseline
  unit    the hilar interneuron on CSC 41: its firing in 0.25 s bins from
          -10 to +90 s (sorted here the way m459_sort.py sorted it; a sort
          on another machine can differ by a spike here and there)
  move    what the video tracker (VT1.nvt) saw move, if anything did: nothing.
          Its 64,128 frames carry no tracked point, and the session saved no
          VT1.mpg (checked on the share, 11-25)

and web/seahorse/story_m459_probe.shb.gz, the picture the story's card draws at
every stop: figure A's CSD on CSC 2-59 and its 1-300 Hz potentials on every
fourth contact, -12 to +60 s, and the interneuron's spikes (probe_blob).

t = 0 is the hilar onset, 888.7 s into the session (m459_panelA_v6.py), on the
recording's own clock (the first sample of a window is where the reader says
it is, not the second that was asked for).
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
sys.path.insert(0, HERE)
from backend import nlx  # noqa: E402

SESSION_UNC = r"\\netfiles03.uvm.edu\bigdata_jbarry\Jeremy3\KCNT1\Fall'24\Kcnt1_459\kcnt_459_s1Dec6\2024-12-06_13-32-22"
SESSION = SESSION_UNC
ONSET = 888.7
WIN = (850.0, 1000.0)
BASE = (600.0, 660.0)
FS_LFP = 1000.0
FS_OUT = 50.0
SPAN = (-12.0, 60.0)
CACHE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Jarvis", "seahorse_raw", "m459_s1_cache.npz")
OUT = os.path.join(APP, "web", "seahorse", "story_m459.json")
PITCH_MM = 0.02                  # Cheetah's log names the "H3 Acute Video New" config (20 um); the figures say 50.
                                 # Only the CSD's units depend on it, and every zone is read against its own baseline.
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
    baseline; the high-passed 30 kHz signal around the unit for the sort.
    t0: where each window really starts (the reader hands back whole 512-sample
    records, so a window starts up to 17 ms before the second it was asked for)."""
    sos_lfp = sg.butter(4, 300, fs=30000, output="sos")
    sos_mua = sg.butter(3, [300, 5000], "band", fs=30000, output="sos")
    sos_hp = sg.butter(3, [300, 6000], "band", fs=30000, output="sos")
    L, M, Lb, Mb, H = [], [], [], [], []
    starts = None
    for c in range(1, 65):
        path = os.path.join(SESSION, "CSC%d.ncs" % c)
        out, got = [], []
        for (a, b) in (WIN, BASE):
            x, t0, fs = nlx.read_ncs_range(path, a, b)
            if abs(fs - 30000) > 1 or abs(t0 - a) > 0.02:
                raise SystemExit("CSC%d: unexpected fs %.1f or start %.3f for %.1f" % (c, fs, t0, a))
            got.append(t0)
            n = int(round((b - a) * fs))
            x = x[:n]
            lfp = sg.sosfiltfilt(sos_lfp, x)[::30].astype(np.float32)
            mua = uniform_filter1d(np.abs(sg.sosfiltfilt(sos_mua, x)), 300)[::600].astype(np.float32)
            out.append((lfp, mua))
            if a == WIN[0] and c in SORT_CH:
                H.append((sg.sosfiltfilt(sos_hp, x) * 4).astype(np.int16))      # 0.25 uV steps
        if starts is None:
            starts = got
        elif max(abs(p - q) for p, q in zip(starts, got)) > 1e-4:
            raise SystemExit("CSC%d starts at %s, CSC1 at %s: the channels are not aligned" % (c, got, starts))
        (l, m), (lb, mb) = out
        L.append(l); M.append(m); Lb.append(lb); Mb.append(mb)
        if c % 8 == 0:
            log("read CSC1-%d" % c)
    return dict(L=np.stack(L), M=np.stack(M), Lb=np.stack(Lb), Mb=np.stack(Mb), H=np.stack(H), t0=np.array(starts))


def window_start(d):
    """Where the story window's samples begin (s into the session). A cache from
    before 11-25 did not keep it; then the start of the 512-sample record that
    holds WIN[0], counted from the first record, which is right to a few ms (the
    real one for this session, read 11-25: 849.9846 s)."""
    if "t0" in d:
        return float(d["t0"][0])
    block = 512 / 30000.0
    return float(np.floor(WIN[0] / block) * block)


def session_path(p):
    """The session as this machine sees it: the share's UNC path on a desk, or
    where the cluster mounts the share (vacc.json's path map) on the VACC."""
    if os.path.isdir(p):
        return p
    try:
        with open(os.path.join(APP, "vacc.json"), encoding="utf-8") as fh:
            rules = json.load(fh).get("path_map") or []
    except (OSError, ValueError):
        rules = []
    unc = p.replace("\\", "/")
    for r in rules:
        a = (r.get("unc") or "").rstrip("/")
        if a and r.get("vacc") and unc.lower().startswith(a.lower()):
            q = r["vacc"].rstrip("/") + unc[len(a):]
            if os.path.isdir(q):
                return q
    return p


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


def sort_unit(H, w0):
    """The hilar interneuron (m459_sort.py's recipe, on CSC 35-48 of the story
    window, whose first sample is at w0 s)."""
    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture
    FS = 30000.0
    Hf = H.astype(np.float32) / 4.0
    nC, nS = Hf.shape
    t_base = int((885.0 - w0) * FS)
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
    tsec = w0 + t / FS
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
        units.append(dict(u=u, chan=int(chan), rate=float(m.sum() / (885.0 - w0)), width=round(width, 3),
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


# ---------------------------------------------------------------- the probe, drawn
# Figure A's CSD and traces over the whole story span, so the card can show the
# same picture at every stop: the contacts down the probe against time, red sink
# and blue source, the potentials drawn over them.
PROBE_OUT = os.path.join(APP, "web", "seahorse", "story_m459_probe.shb.gz")
FIG_PITCH_MM = 0.05                  # figure A's units; the card shows sink and source, not numbers
CSD_FS = 400.0                       # 60 Hz low-passed and 4 ms smoothed: nothing above ~80 Hz to lose
CSD_CSC = list(range(2, 60))         # figure A's rows: CSC 2-59 (60-64 lie below the dentate)
TRACE_CSC = list(range(4, 60, 4))    # figure A's overlay: every fourth contact
STAGES = [(0.0, 1.0), (1.3, 2.3), (2.6, 3.6), (4.6, 5.6)]     # figure A's four windows (s from onset)
VMAX_COUNTS = 8000                   # figure A's colour limit, in the file's steps (the CSD peaks at ~3x it)


def probe_blob(L, w0, spikes, masked):
    """Write the probe's picture: the CSD (int16; figure A's colour limit is
    VMAX_COUNTS) on CSC 2-59 at CSD_FS, the 1-300 Hz potentials (int16, uV) on
    every fourth contact at 1 kHz, and the sorted interneuron's spikes (s from
    the onset). All of it on the story's span, t = 0 at the onset."""
    from common import write_blob
    X = fix_bad(L).astype(np.float64)
    t = w0 + np.arange(X.shape[1]) / FS_LFP - ONSET
    # m459_panelA_v6.py: 60 Hz low-pass, 1.2 contacts of depth smoothing, -d2V/dz2, then 4 ms in time
    Xf = sg.sosfiltfilt(sg.butter(4, 60, fs=FS_LFP, output="sos"), X, axis=1)
    C = -np.diff(gaussian_filter1d(Xf, 1.2, axis=0), 2, axis=0) / FIG_PITCH_MM ** 2     # rows: CSC 2..63
    C = gaussian_filter1d(C, 0.004 * FS_LFP, axis=1)
    rows = np.array(CSD_CSC) - 2
    stage = lambda Y: np.concatenate([Y[:, (t >= a) & (t < b)].ravel() for a, b in STAGES])
    vmax = float(np.percentile(np.abs(stage(C[rows])), 98.5))        # figure A's VMAX
    t_csd = np.round(np.arange(SPAN[0], SPAN[1] + 1e-9, 1 / CSD_FS), 6)
    Cs = np.stack([np.interp(t_csd, t, C[r]) for r in rows])
    csd = np.clip(np.round(Cs / vmax * VMAX_COUNTS), -32767, 32767).astype(np.int16)
    # m459_panelA_v6.py's traces: 1-300 Hz
    Lt = sg.sosfiltfilt(sg.butter(4, [1, 300], "band", fs=FS_LFP, output="sos"), X, axis=1)
    tr_rows = np.array(TRACE_CSC) - 1
    gap = float(np.percentile(np.abs(stage(Lt[tr_rows])), 99.0))      # figure A's GAP_OV
    t_lfp = np.round(np.arange(SPAN[0], SPAN[1] + 1e-9, 1 / FS_LFP), 6)
    lfp = np.round(np.stack([np.interp(t_lfp, t, Lt[r]) for r in tr_rows])).astype(np.int16)
    sp = np.asarray([s for s in spikes if SPAN[0] <= s <= SPAN[1]], dtype=np.float32)
    header = dict(
        what="KCNT1 mouse 459, session 1: the probe through the seizure", onset_s=ONSET, t0=SPAN[0], t1=SPAN[1],
        csd=dict(fs=CSD_FS, csc=CSD_CSC, vmax=VMAX_COUNTS, peak=int(np.abs(csd).max()),
                 recipe="m459_panelA_v6.py: 60 Hz low-pass, depth smoothing 1.2 contacts, -d2V/dz2, 4 ms in time; "
                        "colour limit = the 98.5th percentile of |CSD| over its four stage windows; CSC59 filled from its neighbours"),
        lfp=dict(fs=FS_LFP, csc=TRACE_CSC, units="uV", band=[1, 300], gap_uv=round(gap, 1),
                 recipe="m459_panelA_v6.py's overlay: 1-300 Hz on every fourth contact; gap_uv (the 99th percentile over the stages) spans 4 contacts"),
        unit=dict(csc=41, n=int(len(sp)), masked=masked,
                  note="figure A: single spikes are masked by population discharges from 3.7 s; masked runs to the seizure's last discharge"),
    )
    n = write_blob(PROBE_OUT, header, [("csd", csd), ("lfp", lfp), ("spikes", sp)])
    log("probe: CSD %s at %g Hz (limit %.0f, peak %.1fx), traces %s (gap %.0f uV), %d spikes; wrote %s, %.1f MB" % (
        csd.shape, CSD_FS, vmax, np.abs(Cs).max() / vmax, lfp.shape, gap, len(sp), os.path.basename(PROBE_OUT), n / 1e6))


def main():
    global SESSION, CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="read the raw again")
    ap.add_argument("--fetch", action="store_true",
                    help="only read the raw into the cache (for a machine that can see the share, e.g. a VACC compute node)")
    ap.add_argument("--cache", default="", help="where the raw cache lives (default: %%LOCALAPPDATA%%/Jarvis/seahorse_raw)")
    a = ap.parse_args()
    SESSION = session_path(SESSION)
    if a.cache:
        CACHE = os.path.abspath(a.cache)
    if a.fetch:
        load(True)
        return
    d = load(a.fresh)
    L, M, Lb, Mb, H = d["L"], d["M"], d["Lb"], d["Mb"], d["H"]
    w0 = window_start(d)
    log("LFP", L.shape, "MUA", M.shape, "sort", H.shape,
        "story window from %.4f s%s" % (w0, "" if "t0" in d else " (derived: a cache from before 11-25)"))

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
    t_lfp = w0 + np.arange(C.shape[1]) / FS_LFP
    t_mua = w0 + np.arange(M.shape[1]) / 50.0
    zones, sig, absx, mua = [], {}, {}, {}
    for key, words, a0, a1, lam in ZONES:
        sig[key] = to_out(gaussian_filter1d(np.nanmean(Cn[a0 - 1:a1], 0), 0.01 * FS_LFP), FS_LFP, w0)
        ab = gaussian_filter1d(np.nanmean(R[a0 - 1:a1], 0), 0.08 * FS_LFP)
        absx[key] = to_out(ab, FS_LFP, w0)
        mz = gaussian_filter1d(Mn[a0 - 1:a1].mean(0), 0.1 * 50)
        mua[key] = to_out(mz, 50.0, w0)
        # when it went quiet: the last time its MUA z-score held above 6 for 0.3 s (m459_spread.py's
        # threshold). When it joined is figure A's, read by eye from the recording, not recomputed here.
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
    # the seizure's run of discharges: from the onset to the first pause of more than 2 s
    post = [t for t in dis if t >= 0]
    last = post[0] if post else 0.0
    for p_, q_ in zip(post, post[1:]):
        if q_ - p_ > 2.0:
            break
        last = q_
    log("the seizure's discharges run to %.2f s" % last)

    tsec, lab, units = sort_unit(H, w0)
    # the unit: on CSC 41, the narrowest, nearest 13.7 Hz at baseline (figure A)
    cands = [u for u in units if abs(u["chan"] - 41) <= 1] or units
    pick = min(cands, key=lambda u: (abs(u["chan"] - 41), abs(u["rate"] - 13.7)))
    st = np.sort(tsec[lab == pick["u"]]) - ONSET
    edges = np.arange(-10.0, 90.0 + 1e-9, 0.25)
    rate = np.histogram(st, edges)[0] / 0.25
    rm = lambda a_, b_: rate[(edges[:-1] >= a_ - 1e-9) & (edges[:-1] < b_ - 1e-9)].mean()
    log("unit", pick, "| -10..-4 s %.1f Hz | last 3 s %.1f (%.0f, %.0f, %.0f) | 0.5-1 s %.0f | 1-2 s %.0f | 3-80 s after %.2f Hz" % (
        rm(-10, -4), rm(-3, 0), rm(-3, -2), rm(-2, -1), rm(-1, 0), rm(0.5, 1), rm(1, 2), rm(3, 80)))

    probe_blob(L, w0, st, [3.7, round(float(last), 2)])

    mv = nvt_motion()
    move = None
    if mv is not None:
        rel = mv["t"] - ONSET
        keep = (rel >= SPAN[0]) & (rel <= SPAN[1])
        log("tracker: %d frames, points per frame median %d (range %d-%d)" % (keep.sum(), np.median(mv["n"][keep]) if keep.any() else 0,
                                                                          mv["n"][keep].min() if keep.any() else 0, mv["n"][keep].max() if keep.any() else 0))
        # an empty tracker (no point ever passed its threshold: no camera, or no light) says nothing
        if keep.sum() > 100 and mv["n"][keep].max() > 0:
            move = dict(fps=29.97, t0=round(float(rel[keep][0]), 3),
                        n=[int(v) for v in mv["n"][keep]], step=[round(float(v), 1) for v in mv["step"][keep]])

    r2 = lambda arr: [round(float(v), 2) for v in arr]
    story = dict(
        what="KCNT1 Hom mouse 459, session 1 (2024-12-06), awake head-fixed, 64-contact linear probe",
        source="Neuralynx recording " + SESSION_UNC.split("\\Jeremy3\\")[-1].replace("\\", "/"),
        built=time.strftime("%Y-%m-%d"), onset_s=ONSET, fs=FS_OUT, t0=SPAN[0], t1=SPAN[1],
        baseline_s=list(BASE), zones=zones, discharges=[t for t in dis if SPAN[0] - 30 <= t <= SPAN[1]],
        csd={k: r2(v) for k, v in sig.items()}, absx={k: r2(v) for k, v in absx.items()}, mua={k: r2(v) for k, v in mua.items()},
        unit=dict(csc=pick["chan"], width_ms=pick["width"], baseline_hz=round(pick["rate"], 1), bin_s=0.25, t0=-10.0,
                  hz=[round(float(v), 1) for v in rate]),
        probe=os.path.basename(PROBE_OUT),
        move=move,
    )
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(story, fh, separators=(",", ":"))
    os.replace(tmp, OUT)
    log("wrote", OUT, "%.0f KB" % (os.path.getsize(OUT) / 1e3))


if __name__ == "__main__":
    main()
