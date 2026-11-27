"""Per-series measures from the raw AxoGraph recordings, following the HM4D/CNO methods.

Run it where the .axgd files are; it writes one row per file:

    file, sampling rate, sweeps, first step (pA), increment (pA), spikes per sweep,
    rheobase (pA), mean threshold of first spikes (mV), resting potential (mV), per-sweep counts

    PATCH_RAW=/path/to/recordings python3 patch/axg_measures.py filelist.txt 0 999

Spikes are peaks above -10 mV preceded within 2 ms by dV/dt > 100 mV/ms; threshold is the first
sample of the spike's own contiguous rising phase at which dV/dt reaches 20 mV/ms; a spike is
accepted when its peak exceeds threshold by at least 20 mV.  200 kHz series are resampled to
80 kHz (polyphase 2:5) first, so the detection window is identical across recordings.  The step
runs from 21 ms for 500 ms; the first step amplitude and the increment are read from the pulse
row stored in each file's own notes (UTF-16BE, at the end of the file).

Needs neo and scipy.
"""
import os, sys, re, numpy as np
from neo.io import AxographIO
from scipy.signal import resample_poly

D = os.environ.get('PATCH_RAW', '.')
SR = 80000.0
ON, DUR = 0.0207, 0.500
PEAK_MIN, DVDT_PRE, DVDT_THR, OVERSHOOT = -10.0, 100.0, 20.0, 20.0


def pulse_row(path):
    """First step amplitude and increment in pA, from the file's own stored protocol."""
    txt = open(path, 'rb').read()[-9000:].decode('utf-16-be', 'ignore')
    m = re.search(r'Pulse #1[^\n]*\n([^\n]*)', txt)
    if not m: return None, None
    f = m.group(1).split('\t')
    try: return float(f[11]), float(f[12])
    except Exception: return None, None


def spikes_in(v, sr):
    i0, i1 = int(ON * sr), int((ON + DUR) * sr)
    w = v[i0:i1]
    dv = np.gradient(w) * sr / 1000.0
    above = w > PEAK_MIN
    if not above.any(): return 0, np.nan
    e = np.diff(np.r_[0, above.astype(int), 0])
    n, first = 0, np.nan
    pre = int(0.002 * sr)
    for a, b in zip(np.where(e == 1)[0], np.where(e == -1)[0]):
        pk = a + int(np.argmax(w[a:b]))
        if dv[max(0, pk - pre):pk].max(initial=0) <= DVDT_PRE: continue
        j = pk
        while j > 0 and dv[j - 1] > 0: j -= 1
        rise = np.arange(j, pk)
        k = rise[dv[rise] >= DVDT_THR]
        if not len(k): continue
        thr = w[k[0]]
        if w[pk] - thr < OVERSHOOT: continue
        n += 1
        if np.isnan(first): first = thr
    return n, first


def series(path):
    bl = AxographIO(path).read_block()
    sr0 = float(bl.segments[0].analogsignals[0].sampling_rate)
    per, thr, rest = [], [], []
    for seg in bl.segments:
        v = np.asarray(seg.analogsignals[0]).ravel() * 1000.0
        if abs(sr0 - 200000.0) < 1:
            v = resample_poly(v, 2, 5)
        n, t = spikes_in(v, SR)
        per.append(n)
        if n: thr.append(t)
        rest.append(float(v[int(0.003 * SR):int(0.016 * SR)].mean()))
    return sr0, per, thr, float(np.mean(rest))


if __name__ == '__main__':
    names = [l.rstrip('\n') for l in open(sys.argv[1]) if l.strip()]
    for f in names[int(sys.argv[2]):int(sys.argv[3])]:
        p = os.path.join(D, f)
        try:
            start, inc = pulse_row(p)
            sr0, per, thr, rest = series(p)
            rb = ''
            if start is not None and any(per):
                rb = '%.0f' % (start + inc * int(np.argmax(np.array(per) > 0)))
            print('%s\t%g\t%d\t%s\t%s\t%.4f\t%s\t%s\t%.2f\t%s' % (
                f, sr0, len(per), '%g' % start if start is not None else '',
                '%g' % inc if inc is not None else '', np.mean(per), rb,
                ('%.2f' % np.mean(thr)) if thr else '', rest, ','.join(map(str, per))), flush=True)
        except Exception as e:
            print('%s\tERR\t%s' % (f, type(e).__name__), flush=True)
