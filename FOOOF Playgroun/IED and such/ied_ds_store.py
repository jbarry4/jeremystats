"""
ied_ds_store.py -- every curated event of both classes, held at once.

WHY THIS EXISTS
===============
v2 keeps each event's window at the full 30 kHz, in float64, because it only
ever holds ten of them. All 296 dentate spikes and every IED will not fit that
way: 309 events x 400 ms x 64 contacts, raw and filtered, is about 5.7 GB.

So the store decimates. The measurement trace is already lowpassed at 300 Hz,
which makes 30 kHz roughly fifty times more sample rate than the signal needs,
and the 300 Hz Butterworth is itself the anti-alias filter. Dropping to 2 kHz
was checked against the full-rate answer on twelve events:

    mean|amp|   max relative error 0.66%,  median 0.31%
    centring    max disagreement 0.37 ms,  median 0.05 ms

against a statistic whose between-event spread is tens of percent and a
centring whose search window is tens of milliseconds. Everything then fits in
63 MB, which is why v3's sliders stay instant over 309 events where v2's
approach would not have loaded them at all.

THE LOWPASS IS PART OF THE CACHE, NOT A TOGGLE
==============================================
v2 lets the lowpass be switched off. v3 cannot: the lowpass IS the anti-alias
filter, so decimated data with it removed would be aliased rather than
unfiltered, and the trace would be quietly wrong instead of visibly raw.
`--lowpass` therefore changes the cache key and rebuilds. The 60 Hz notch is
still a live toggle, because 60 Hz is far below the 1 kHz Nyquist that
survives decimation.

READING IS ONCE
===============
Reading 309 events across 64 .ncs files is about 70 seconds. That happens on
the first run and is cached to an .npz beside this file, keyed by a hash of
everything that would change the numbers -- folder, event list, span, lowpass,
decimation. Change any of them and it rebuilds; change none and it loads in
about a second. Same arrangement as `ds_pca_gui.py`'s cache, for the same
reason.
"""
from __future__ import annotations

import hashlib
import json
import os

import numpy as np
from scipy.signal import filtfilt, iirnotch

from ied_ds import RAIL_UV, Probe64, prep, read_ds_bank, read_ied_events

_HERE = os.path.dirname(os.path.abspath(__file__))

DEC_Q = 15                  # 30000 -> 2000 Hz
HALF_MS = 200.0             # cached either side of each stamp
CACHE_VERSION = 2           # 2: carries the rail mask


def _key(folder, events, half_ms, lowpass, q):
    h = hashlib.sha1()
    h.update(json.dumps({
        "v": CACHE_VERSION, "folder": os.path.normcase(folder),
        "half_ms": half_ms, "lowpass": lowpass, "q": q,
        "events": [[e[0], int(e[1]), round(float(e[2]), 6)] for e in events],
    }, sort_keys=True).encode())
    return h.hexdigest()[:12]


class EventStore:
    """Decimated windows for every event of both classes, plus the metadata.

    `data` is [n_events, T, n_contacts] float32 at `fs`, each row centred on
    that event's ORIGINAL stamp -- the user's centring is an index offset
    applied at read time, never baked in, so re-centring never needs a rebuild.
    """

    def __init__(self, probe, kinds, ids, t_s, data, fs, half_ms, lowpass, q,
                 rail=None):
        self.p = probe
        self.kinds = np.asarray(kinds)
        self.ids = np.asarray(ids, dtype=int)
        self.t_s = np.asarray(t_s, dtype=float)
        self.data = data                     # [n, T, 64] float32
        self.fs = float(fs)
        self.half_ms = float(half_ms)
        self.lowpass = lowpass
        self.q = int(q)
        self.stamp_i = data.shape[1] // 2
        self.notch = None
        self._view = data                    # notch applied lazily
        # [n, T, 64] -- was the RAW trace on the rail at this sample? Read off
        # the unfiltered data before decimation, because a 300 Hz lowpass
        # rounds a clipped plateau's corners and a decimated, filtered trace no
        # longer looks flat-topped at all. A statistic that takes a maximum
        # needs this: v3 averaged 62 contacts so a censored one was 1/62 of the
        # answer, but a max IS the censored contact whenever one is railed.
        self.rail = (np.zeros(data.shape, dtype=bool) if rail is None
                     else np.asarray(rail, dtype=bool))
        self._derive()

    def _derive(self):
        """Per-event baseline and activity trace, computed once per view.

        Neither depends on where the centre currently sits or how wide the
        measure window is, so recomputing them inside a slider callback would
        redo a 309 x 801 x 64 median on every drag. Precomputed, a window
        change is a slice and a mean, and the controls stay live over the
        whole set instead of the ten events v2 could afford.
        """
        v = self._view
        self._base = np.median(v, axis=1)                    # [n, 64]
        inc = self.p.included
        self._act = np.mean(
            np.abs(v[:, :, inc] - self._base[:, None, inc]), axis=2)  # [n, T]

    # ------------------------------------------------------------- building
    @classmethod
    def build(cls, probe, ied_tab, ds_tab, half_ms=HALF_MS, lowpass=300.0,
              q=DEC_Q, progress=None, cache_dir=_HERE, refresh=False):
        rows = ([("IED", int(r["id"]), float(r["t_s"])) for _, r in ied_tab.iterrows()]
                + [("DS", int(r["id"]), float(r["t_s"])) for _, r in ds_tab.iterrows()])
        key = _key(probe.session["path"], rows, half_ms, lowpass, q)
        path = os.path.join(cache_dir, "ied_ds_store_%s.npz" % key)

        if os.path.exists(path) and not refresh:
            try:
                z = np.load(path, allow_pickle=False)
                if progress:
                    progress(1, 1, "loaded cache %s" % os.path.basename(path))
                return cls(probe, z["kinds"].astype(str), z["ids"], z["t_s"],
                           z["data"], float(z["fs"]), float(z["half_ms"]),
                           lowpass, int(z["q"]),
                           rail=z["rail"] if "rail" in z.files else None)
            except Exception:
                pass                          # a bad cache is rebuilt, not fatal

        fs_d = probe.fs / q
        T = int(round(2 * half_ms * 1e-3 * fs_d)) + 1
        data = np.zeros((len(rows), T, len(probe.numbers)), dtype=np.float32)
        rail = np.zeros((len(rows), T, len(probe.numbers)), dtype=bool)
        half_s = half_ms * 1e-3
        for i, (kind, eid, t) in enumerate(rows):
            if progress:
                progress(i, len(rows), "reading %s%d" % (kind, eid))
            seg, t0 = probe.read(t - half_s - 0.05, t + half_s + 0.05)
            f = prep(seg, probe.fs, lowpass=lowpass, notch=None)
            hit = np.abs(seg) >= RAIL_UV          # on the RAW trace
            ci = int(round((t - t0) * probe.fs))
            # Decimate by slicing AROUND the stamp, so the stamp lands exactly
            # on a kept sample and every event's row is aligned the same way.
            lo = ci - int(round(half_s * probe.fs))
            idx = lo + np.arange(T) * q
            ok = (idx >= 0) & (idx < f.shape[0])
            data[i, ok, :] = f[idx[ok], :].astype(np.float32)
            # Each kept sample stands for the q raw samples around it, so it
            # is marked railed if ANY of them clipped -- taking only the kept
            # sample would miss a plateau that fell between two of them.
            for j in np.where(ok)[0]:
                a = max(0, idx[j] - q // 2)
                b = min(hit.shape[0], idx[j] + q // 2 + 1)
                rail[i, j, :] = hit[a:b, :].any(axis=0)
        try:
            np.savez(path, kinds=np.array([r[0] for r in rows]),
                     ids=np.array([r[1] for r in rows]),
                     t_s=np.array([r[2] for r in rows]), data=data, rail=rail,
                     fs=fs_d, half_ms=half_ms, q=q)
            if progress:
                progress(len(rows), len(rows),
                         "cached -> %s" % os.path.basename(path))
        except Exception as exc:
            if progress:
                progress(len(rows), len(rows), "cache write failed: %s" % exc)
        return cls(probe, [r[0] for r in rows], [r[1] for r in rows],
                   [r[2] for r in rows], data, fs_d, half_ms, lowpass, q,
                   rail=rail)

    # -------------------------------------------------------------- access
    def set_notch(self, hz):
        """60 Hz survives decimation, so it stays a live toggle."""
        if hz == self.notch:
            return
        self.notch = hz
        if not hz:
            self._view = self.data
        else:
            b, a = iirnotch(float(hz), 30.0, self.fs)
            out = np.empty_like(self.data)
            for i in range(self.data.shape[0]):
                out[i] = filtfilt(b, a, self.data[i], axis=0).astype(np.float32)
            self._view = out
        self._derive()

    def __len__(self):
        return self.data.shape[0]

    def where(self, kind):
        return np.where(self.kinds == kind)[0]

    def trace(self, i):
        return self._view[i]

    def label(self, i):
        return "%s %d" % (self.kinds[i], self.ids[i])

    # --------------------------------------------------------- measurement
    def activity(self, i, baseline=True):
        """Across-channel mean |x - baseline| against time, for event i."""
        if baseline:
            return self._act[i]
        y = self._view[i][:, self.p.included]
        return np.mean(np.abs(y), axis=1)

    def centre(self, i, shift, search_ms, method="mean|amp| peak",
               baseline=True):
        """(shift_samples, at_edge) for event i, searched around the stamp.

        Searched from the stamp, never from `shift`, so pressing centre twice
        cannot walk the centre along the trace.
        """
        h = int(round(search_ms * 1e-3 * self.fs))
        n = self._view.shape[1]
        lo, hi = max(0, self.stamp_i - h), min(n - 1, self.stamp_i + h)
        if hi - lo < 2:
            return shift, False
        if method == "mean|amp| peak":
            pick = lo + int(np.argmax(self.activity(i, baseline)[lo:hi + 1]))
        else:
            y = self._view[i][:, self.p.included]
            seg = np.abs(y[lo:hi + 1] - np.median(y, axis=0))
            pick = lo + int(np.argmax(seg.max(axis=1)))
        return pick - self.stamp_i, bool(pick <= lo or pick >= hi)

    def stat(self, i, shift, win_ms, baseline=True):
        """(scalar, per_contact[64]) for event i at the given centre."""
        y = self._view[i]
        c = self.stamp_i + int(shift)
        h = int(round(win_ms * 1e-3 * self.fs))
        lo, hi = max(0, c - h), min(y.shape[0], c + h + 1)
        if hi - lo < 2:
            return np.nan, np.full(y.shape[1], np.nan)
        base = self._base[i] if baseline else np.zeros(y.shape[1])
        per = np.mean(np.abs(y[lo:hi] - base), axis=0)
        per = np.where(self.p.included, per, np.nan)
        return float(np.nanmean(per)), per

    def stats_for(self, idx, shifts, win_ms, baseline=True):
        """Vectorised over a set of events: (scalars[n], profiles[n, 64])."""
        S = np.empty(len(idx))
        P = np.empty((len(idx), self._view.shape[2]))
        for j, i in enumerate(idx):
            S[j], P[j] = self.stat(i, shifts[j], win_ms, baseline)
        return S, P

    def peak_stat(self, i, shift, win_ms, baseline=True, k=1,
                  mode="peak |amp|", exclude_railed=True):
        """v4's statistic: the biggest contact, not the average of all of them.

        Returns (scalar, per_contact[64], usable[64], win_contact).

        `mode` picks how each contact is reduced over the window:
          "peak |amp|"    its largest |x - baseline| at any sample -- the
                          literal highest absolute amplitude.
          "channel mean"  its mean |x - baseline| over the window, which is
                          exactly the per-contact quantity v3 averaged.
        `k` is how many of the best contacts are then averaged: k=1 is the
        single biggest, and "channel mean" with k=62 reproduces v3 exactly, so
        the slider spans the whole question of how much the quiet contacts
        were diluting the signal.

        `exclude_railed` drops any contact that clipped ANYWHERE inside the
        window. It defaults on because a max is precisely the statistic the
        rail eats: 92% of Solid IEDs and 34% of dentate spikes have their
        peak contact railed, so an unguarded max reports the amplifier's
        limit for most IEDs and the brain for most DS -- a difference between
        classes that is entirely an artefact of which ones clipped.
        """
        y = self._view[i]
        c = self.stamp_i + int(shift)
        h = int(round(win_ms * 1e-3 * self.fs))
        lo, hi = max(0, c - h), min(y.shape[0], c + h + 1)
        nch = y.shape[1]
        if hi - lo < 2:
            return np.nan, np.full(nch, np.nan), np.zeros(nch, bool), -1
        base = self._base[i] if baseline else np.zeros(nch)
        dev = np.abs(y[lo:hi] - base)
        per = dev.max(axis=0) if mode == "peak |amp|" else dev.mean(axis=0)

        usable = self.p.included.copy()
        if exclude_railed:
            usable &= ~self.rail[i, lo:hi, :].any(axis=0)
            if not usable.any():          # every good contact clipped
                usable = self.p.included.copy()
        vals = np.where(usable, per, np.nan)
        order = np.argsort(np.where(np.isnan(vals), -np.inf, vals))[::-1]
        top = [j for j in order if usable[j]][:max(1, int(k))]
        if not top:
            return np.nan, np.where(self.p.included, per, np.nan), usable, -1
        return (float(np.mean(per[top])),
                np.where(self.p.included, per, np.nan), usable, int(top[0]))

    def peak_stats_for(self, idx, shifts, win_ms, **kw):
        S = np.empty(len(idx))
        P = np.empty((len(idx), self._view.shape[2]))
        W = np.empty(len(idx), dtype=int)
        R = np.zeros(len(idx), dtype=bool)
        for j, i in enumerate(idx):
            S[j], P[j], usable, W[j] = self.peak_stat(i, shifts[j], win_ms, **kw)
            # Was this event censored -- did any good contact clip in-window?
            c = self.stamp_i + int(shifts[j])
            h = int(round(win_ms * 1e-3 * self.fs))
            a, b = max(0, c - h), min(self._view.shape[1], c + h + 1)
            R[j] = bool((self.rail[i, a:b, :] & self.p.included).any())
        return S, P, W, R

    def centre_all(self, shifts, search_ms, method="mean|amp| peak",
                   baseline=True):
        """Centre every event. Returns (shifts, at_edge) as arrays."""
        out = np.array(shifts, dtype=int, copy=True)
        edge = np.zeros(len(self), dtype=bool)
        for i in range(len(self)):
            out[i], edge[i] = self.centre(i, out[i], search_ms, method,
                                          baseline)
        return out, edge

    def slice_(self, i, shift, view_ms):
        """The window as drawn, centred, NaN-padded at the cache edge."""
        y = self._view[i]
        h = int(round(view_ms * 1e-3 * self.fs))
        c = self.stamp_i + int(shift)
        out = np.full((2 * h + 1, y.shape[1]), np.nan, dtype=float)
        lo, hi = c - h, c + h + 1
        a, b = max(0, lo), min(y.shape[0], hi)
        if b > a:
            out[a - lo:b - lo] = y[a:b]
        return out


def load_all(probe=None, category="Solid", ds_label="spike", **kw):
    """Every DS and every IED of `category`, ready to measure."""
    p = probe or Probe64()
    ied = read_ied_events(category=category)
    ds = read_ds_bank(label=ds_label)
    return p, EventStore.build(p, ied, ds, **kw)


def _selftest():
    import time
    def prog(i, n, msg):
        if i % 40 == 0 or i >= n - 1:
            print("  [%3d/%3d] %s" % (i, n, msg))
    t = time.time()
    p, st = load_all(progress=prog)
    print("built/loaded in %.1f s" % (time.time() - t))
    print("events %d  (IED %d, DS %d)  fs %.0f  T %d  %.0f MB"
          % (len(st), len(st.where("IED")), len(st.where("DS")), st.fs,
             st.data.shape[1], st.data.nbytes / 1e6))
    shifts = np.zeros(len(st), dtype=int)
    t = time.time()
    edges = 0
    for i in range(len(st)):
        shifts[i], e = st.centre(i, 0, 25.0)
        edges += e
    print("centred all %d in %.2f s   (%d at the search edge)"
          % (len(st), time.time() - t, edges))
    for kind in ("IED", "DS"):
        idx = st.where(kind)
        S, _ = st.stats_for(idx, shifts[idx], 25.0)
        print("  %-4s n=%3d  mean|amp| %7.2f  median %7.2f  IQR %.2f-%.2f"
              % (kind, len(idx), np.mean(S), np.median(S),
                 *np.percentile(S, [25, 75])))


if __name__ == "__main__":
    _selftest()
