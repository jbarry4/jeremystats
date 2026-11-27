"""Everything figure E draws, measured from the raw: KCNT1 Hom mouse 459, session 1 (2024-12-06).

Source: Jarvis's raw cache of the Neuralynx recording (%LOCALAPPDATA%/Jarvis/seahorse_raw/m459_s1_cache.npz, read on a VACC
compute node by _Jarvis/app/tools/seahorse/story_m459.py --fetch): LFP at 1 kHz for 850-1000 s and a 600-660 s quiet baseline,
and the 300-6000 Hz signal of CSC 35-48 at 30 kHz for the unit sort. Recipes are m459_panelA_v6.py's (via story_m459.py):
CSD = 60 Hz low-pass, 1.2 contacts of depth smoothing, -d2V/dz2, 4 ms in time; traces 1-300 Hz on every fourth contact; each
channel's |CSD| (0.1 s boxcar) against its own quiet-baseline median; the hilar interneuron sorted with story_m459.sort_unit."""
import os, sys, json
import numpy as np
from scipy import signal as sg
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
SEA = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\app\tools\seahorse"
sys.path.insert(0, SEA)
import story_m459 as S  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "seizure.npz")
d = np.load(S.CACHE)
L, Lb, H = d["L"].astype(np.float64), d["Lb"].astype(np.float64), d["H"]
w0 = S.window_start(d)
FS = S.FS_LFP
t = w0 + np.arange(L.shape[1]) / FS - S.ONSET            # s from the hilar onset
print("window starts %.4f s; LFP %s; baseline %s" % (w0, L.shape, Lb.shape))

def csd(X, pitch=S.FIG_PITCH_MM):
    Xf = sg.sosfiltfilt(sg.butter(4, 60, fs=FS, output="sos"), S.fix_bad(X), axis=1)
    C = -np.diff(gaussian_filter1d(Xf, 1.2, axis=0), 2, axis=0) / pitch ** 2      # rows = CSC 2..63
    return np.vstack([np.full((1, C.shape[1]), np.nan), C, np.full((1, C.shape[1]), np.nan)])  # rows = CSC 1..64

C = csd(L); Cb = csd(Lb)
Cs = gaussian_filter1d(np.nan_to_num(C), 0.004 * FS, axis=1)
Cs[[0, 63]] = np.nan
LT = sg.sosfiltfilt(sg.butter(4, [1, 300], "band", fs=FS, output="sos"), S.fix_bad(L), axis=1)

# the four stage windows, padded so the figure can choose its own crop
snaps, traces, tt = [], [], []
for a, b in S.STAGES:
    m = (t >= a - 1e-9) & (t < b - 1e-9)
    snaps.append(Cs[:, m].astype(np.float32)); traces.append(LT[:, m].astype(np.float32)); tt.append(t[m].astype(np.float32))
rows = np.arange(2, 60) - 1                                   # CSC 2-59, figure A's rows
vmax = float(np.percentile(np.abs(np.concatenate([s[rows].ravel() for s in snaps])), 98.5))
tr_rows = np.arange(4, 60, 4) - 1
gap = float(np.percentile(np.abs(np.concatenate([x[tr_rows].ravel() for x in traces])), 99.0))
print("CSD limit (98.5th pct of |CSD| over the stages) %.0f; trace gap (99th pct) %.0f uV" % (vmax, gap))

# each zone's |CSD| against its own quiet baseline (m459_csdratio.py: 0.1 s boxcar of |CSD|, / the channel's baseline median)
A = uniform_filter1d(np.abs(np.nan_to_num(C)), int(0.1 * FS), axis=1)
Ab = uniform_filter1d(np.abs(np.nan_to_num(Cb)), int(0.1 * FS), axis=1)
R = A / np.median(Ab, 1, keepdims=True)
R[[0, 63]] = np.nan
GROUPS = {"CA1": (5, 9), "Supra blade": (28, 39), "Hilus": (40, 49), "Infra blade": (50, 58)}
zt = t[::10]
zone = {k: uniform_filter1d(np.nanmedian(R[a - 1:b], 0)[::10], 20) for k, (a, b) in GROUPS.items()}   # 100 Hz, 0.2 s smoothing (panel A)

# the hilar interneuron on CSC 41 (story_m459.sort_unit = m459_sort.py's recipe)
tsec, lab, units = S.sort_unit(H, w0)
cands = [u for u in units if abs(u["chan"] - 41) <= 1] or units
pick = min(cands, key=lambda u: (abs(u["chan"] - 41), abs(u["rate"] - 13.7)))
st = np.sort(tsec[lab == pick["u"]])
ci = S.SORT_CH.index(pick["chan"])
idx = ((st - w0) * 30000).astype(int)
base = st < 885.0
pre, post = 18, 36
ok = (idx > pre) & (idx < H.shape[1] - post) & base
wf = np.stack([H[ci, i - pre:i + post] for i in idx[ok][:4000]]).astype(np.float32) / 4.0       # uV
print("unit", pick, "spikes", len(st))
np.savez_compressed(OUT, t_stage=np.array(tt, dtype=object), snaps=np.array(snaps, dtype=object), traces=np.array(traces, dtype=object),
                    vmax=vmax, gap=gap, zt=zt - 0, zone_names=np.array(list(zone)), zone=np.stack(list(zone.values())),
                    spikes=st - S.ONSET, unit=json.dumps(pick), wf_mean=wf.mean(0), wf_sd=wf.std(0), stages=np.array(S.STAGES))
print("wrote", OUT)
