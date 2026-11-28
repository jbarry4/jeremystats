"""The lag the film quotes ("CA1 hears each discharge about 15 ms after the dentate gyrus"), measured on
mouse 459's recording: discharge by discharge, once the seizure is going, how long after the perforant
path's sink in the dentate's molecular layer (the cortex's input arriving) the Schaffer collaterals' sink
in CA1 radiatum (CA3's output arriving in CA1) peaks.

    python tools/seahorse/film/measure_lag.py [--png lag.png]

Reads the story's raw cache (1 kHz LFP, every contact, 850-1000 s; story_m459.py writes it) and the
story's discharge times (story_m459.json). The CSD: 150 Hz low-pass (zero phase), 1.2 contacts of depth
smoothing, -d2V/dz2, each contact in units of its own spread over 5-43 s. The contacts: where the average
of the seizure's discharges (5-43.5 s after the onset) has its deepest sink in the upper blade's molecular
layer (CSC 28-32: CSC30, its middle and outer thirds, where the perforant path lands), the lower blade's
(CSC 53-58: CSC54, its inner third) and CA1 radiatum (CSC 11-20: CSC17), each with its neighbours. The
film quotes the upper blade's.
Per discharge: each sink's peak within the window (parabolic), kept when both are clear (the upper blade
below -1.5 sd, CA1 below -1 sd). Also the cross-correlation of the two contacts over 5-43 s.

Measured 2026-11-27 (n = 265 discharges, 99 clear in both): CA1 radiatum after the upper blade, median
15.3 ms (IQR 9.1-21.6); after the lower blade, 12.1 ms; cross-correlation 16 ms (upper), 10 ms (lower).
Discharges come every 145 ms (median) in that stretch, so the lag is a tenth of the interval: at the
film's frame rate (33 ms a frame) CA1 and the dentate gyrus fire in the same frame or the next.
"""
import argparse, json, os
import numpy as np
from scipy import signal as sg
from scipy.ndimage import gaussian_filter1d

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CACHE = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'Jarvis', 'seahorse_raw', 'm459_s1_cache.npz')
STORY = os.path.join(APP, 'web', 'seahorse', 'story_m459.json')
ONSET, FS = 888.7, 1000.0
SPAN = (5.0, 43.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--png', default='', help='a picture of the average discharge and the lags')
    a = ap.parse_args()
    z = np.load(CACHE)
    L = z['L'].astype(np.float64)
    w0 = float(z['t0'][0])
    L[58] = 0.5 * (L[57] + L[59])                      # CSC59 is bad: its neighbours
    t = w0 + np.arange(L.shape[1]) / FS - ONSET
    Xf = sg.sosfiltfilt(sg.butter(4, 150, fs=FS, output='sos'), L, axis=1)
    C = -np.diff(gaussian_filter1d(Xf, 1.2, axis=0), 2, axis=0)
    C = np.vstack([np.full((1, C.shape[1]), np.nan), C, np.full((1, C.shape[1]), np.nan)])   # row i = CSC i+1
    ict = (t >= 5) & (t <= 43)
    C = C / np.nanstd(C[:, ict], axis=1, keepdims=True)

    dis = np.array(json.load(open(STORY, encoding='utf-8'))['discharges'])
    dis = dis[(dis >= SPAN[0]) & (dis <= SPAN[1])]
    W = np.arange(-60, 81)
    idx = [int(round((d - t[0]) * FS)) for d in dis]
    avg = np.nanmean(np.stack([C[:, i + W] for i in idx]), 0)

    def deepest(c0, c1, w):
        m = (W >= w[0]) & (W <= w[1])
        sub = avg[c0 - 1:c1, :][:, m]
        r, j = np.unravel_index(np.nanargmin(sub), sub.shape)
        return c0 + r, W[m][j]
    up, _ = deepest(28, 32, (-30, 30))
    low, _ = deepest(53, 58, (-30, 30))
    ca1, _ = deepest(11, 20, (-30, 40))
    ch = lambda c: np.nanmean(C[c - 2:c + 1], 0)
    yU, yL, yS = ch(up), ch(low), ch(ca1)

    def peak(y, i0, lo, hi):
        seg = y[i0 + lo:i0 + hi + 1]
        j = int(np.nanargmin(seg))
        d = 0.0
        if 0 < j < len(seg) - 1:
            den = seg[j - 1] - 2 * seg[j] + seg[j + 1]
            if den:
                d = 0.5 * (seg[j - 1] - seg[j + 1]) / den
        return lo + j + d, seg[j]
    rows = []
    for i in idx:
        tu, vu = peak(yU, i, -35, 25)
        tl, vl = peak(yL, i, -35, 25)
        ts, vs = peak(yS, i, int(tu) - 5, int(tu) + 45)
        rows.append((tu, vu, tl, vl, ts, vs))
    R = np.array(rows)
    okU = (R[:, 1] < -1.5) & (R[:, 5] < -1.0)
    okL = (R[:, 3] < -1.5) & (R[:, 5] < -1.0)
    lagU, lagL = (R[:, 4] - R[:, 0])[okU], (R[:, 4] - R[:, 2])[okL]

    def xl(x, y, maxlag=60):
        x = np.nan_to_num(x - np.nanmean(x)); y = np.nan_to_num(y - np.nanmean(y))
        cc = sg.correlate(y, x, mode='full'); lg = np.arange(-len(x) + 1, len(x)); m = np.abs(lg) <= maxlag
        return int(lg[m][np.argmax(cc[m])])
    print('contacts: upper blade CSC%d, lower blade CSC%d, CA1 radiatum CSC%d' % (up, low, ca1))
    print('%d discharges %.0f-%.1f s; clear in both: %d (upper), %d (lower)' % (len(dis), SPAN[0], SPAN[1], okU.sum(), okL.sum()))
    print('CA1 after the upper blade: median %.1f ms, IQR %.1f-%.1f' % (np.median(lagU), *np.percentile(lagU, [25, 75])))
    print('CA1 after the lower blade: median %.1f ms, IQR %.1f-%.1f' % (np.median(lagL), *np.percentile(lagL, [25, 75])))
    print('cross-correlation 5-43 s: %d ms (upper), %d ms (lower)' % (xl(yU[ict], yS[ict]), xl(yL[ict], yS[ict])))
    print('discharge interval: median %.0f ms' % (1000 * np.median(np.diff(dis))))
    if a.png:
        import matplotlib; matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(13, 5.5), gridspec_kw=dict(width_ratios=[1.2, 1]))
        v = np.nanpercentile(np.abs(avg), 98)
        ax[0].imshow(avg, aspect='auto', cmap='RdBu_r', vmin=-v, vmax=v, extent=[W[0] - 0.5, W[-1] + 0.5, 64.5, 0.5])
        ax[0].set_title('m459: the average of %d seizure discharges (CSD; blue = sink)' % len(dis), fontsize=10)
        ax[0].set_xlabel('ms from the dentate discharge'); ax[0].set_ylabel('CSC (1 = top of the probe)')
        for c, nm in [(up, 'upper blade, molecular'), (low, 'lower blade, molecular'), (ca1, 'CA1 radiatum')]:
            ax[0].axhline(c, color='k', lw=0.5, ls=':'); ax[0].text(W[-1] - 2, c - 0.6, nm, ha='right', fontsize=8)
        ax[1].hist(lagU, bins=np.arange(-20, 51, 2), color='#5f9e2f', alpha=0.85)
        ax[1].axvline(np.median(lagU), color='k')
        ax[1].set_xlabel('ms: CA1 radiatum sink after the upper blade\'s perforant-path sink')
        ax[1].set_title('per discharge (n = %d): median %.1f ms' % (len(lagU), np.median(lagU)), fontsize=10)
        plt.tight_layout(); plt.savefig(a.png, dpi=110)
        print('wrote', a.png)


if __name__ == '__main__':
    main()
