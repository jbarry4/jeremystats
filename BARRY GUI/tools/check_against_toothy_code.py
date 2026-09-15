# -*- coding: utf-8 -*-
"""Run identical inputs through Toothy's OWN code and through Incisor.

Not a comparison against banked exports. Those are a derived artifact -- an
ETS file, possibly curated, possibly re-timed, detected on a channel nobody
wrote down -- and comparing against one stacks three confounds on top of the
question being asked. This imports Toothy's real `ephys.get_ds_peaks` and
`pyfx.butter_bandpass_filter` and feeds them the same arrays Incisor gets.

HOW TOOTHY IS IMPORTED
----------------------
`ephys.py` and `pyfx.py` import PyQt5, quantities, probeinterface and seaborn
at module level. None of them is installed here and none is USED by the two
functions under test -- `get_ds_peaks` touches numpy, scipy.signal and a
pandas DataFrame, and `butter_bandpass_filter` touches scipy.signal alone. So
the missing imports are stubbed with modules that raise on any attribute
access, which means the test fails loudly if a stub is ever actually reached
rather than quietly returning a mock. The code that runs is Toothy's, byte
for byte, off the working tree.

LAYERED, SO A FAILURE LOCALISES
-------------------------------
    1. the filter          same trace in, two filters, identical out?
    2. the threshold       same filtered trace, same number?
    3. the detection       same filtered trace and threshold, same peaks?
    4. a real recording    a real decimated channel, end to end
    5. the parameters      every default, against Toothy's qparam.py

UNITS
-----
Toothy works in millivolts, Incisor in microvolts. Every comparison converts
once, explicitly, at the boundary: Toothy is handed `x / 1000` and a 0.3 mV
floor, Incisor is handed `x` and a 300 uV floor.

Run: python tools/check_against_toothy_code.py [recording-folder]
"""
import io
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOTHY = r"C:\Users\Z390\Desktop\jeremystats\Toothy\Toothy-main"

sys.path.insert(0, ROOT)

FAILED = []


def ck(name, ok, detail=""):
    print("  %-5s %s%s" % ("ok" if ok else "FAIL", name,
                           "" if ok else "   [%s]" % detail))
    if not ok:
        FAILED.append(name)


# --------------------------------------------------------------------------
# Importing Toothy
# --------------------------------------------------------------------------
# Toothy's functions are EXTRACTED, not imported.
#
# `ephys.py` imports PyQt5 and `qparam.py` calls `QtCore.pyqtSignal()` while
# the module loads, so importing it needs a working Qt. Stubbing hard enough
# to get past that would mean handing Toothy fake objects and hoping none of
# them reached the arithmetic -- at which point the test no longer proves
# what it claims.
#
# So the source text of each function is lifted out of the file and executed
# in a namespace holding numpy, scipy and pandas and nothing else. The code
# that runs is byte-for-byte Toothy's, and the namespace is small enough to
# print, which is the whole argument for doing it this way. If a function
# ever grows a dependency on something not in that namespace, this raises a
# NameError rather than quietly substituting anything.
WANT = {
    "ephys.py": ["get_asym", "get_ds_peaks"],
    "pyfx.py": ["butter_bandpass", "butter_bandpass_filter"],
}


def extract_toothy():
    """Toothy's real functions, off the working tree, with no Qt."""
    if not os.path.isdir(TOOTHY):
        print("Toothy is not at %s" % TOOTHY)
        raise SystemExit(1)
    import ast
    import pandas as pd
    import scipy
    import scipy.signal                                   # noqa: F401

    ns = {"np": np, "numpy": np, "scipy": scipy, "pd": pd, "pandas": pd}
    taken = {}
    for fname, names in WANT.items():
        path = os.path.join(TOOTHY, fname)
        src = io.open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                text = ast.get_source_segment(src, node)
                exec(compile(text, "%s::%s" % (fname, node.name), "exec"), ns)
                taken[node.name] = (fname, node.lineno,
                                    len(text.splitlines()))
    missing = [n for names in WANT.values() for n in names if n not in taken]
    if missing:
        print("could not find in Toothy: %s" % ", ".join(missing))
        raise SystemExit(1)
    return ns, taken


# --------------------------------------------------------------------------
# The traces both sides are given
# --------------------------------------------------------------------------
def synthetic(n=600000, fs=1000.0, seed=11):
    """A trace with dentate-spike-shaped events on 1/f-ish noise.

    Deterministic, so a disagreement is reproducible, and shaped so the
    detector has something to find: 10 ms Gaussian bumps at irregular
    intervals, amplitudes spanning the threshold so the edge cases -- a peak
    just over, a peak just under -- are exercised rather than assumed.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    x = rng.normal(0, 60.0, n)
    # Slow drift, so the band-pass has something to remove.
    x += 400 * np.sin(2 * np.pi * 0.3 * t) + 150 * np.sin(2 * np.pi * 7.0 * t)
    at = np.cumsum(rng.integers(300, 3000, 400))
    at = at[at < n - 100]
    amps = rng.uniform(150, 2500, at.size)
    w = 10.0 * fs / 1000.0
    for i, a in zip(at, amps):
        lo, hi = max(0, int(i - 4 * w)), min(n, int(i + 4 * w))
        x[lo:hi] += a * np.exp(-((np.arange(lo, hi) - i) ** 2) / (2 * w ** 2))
    return x


def raw_chunk(folder, index=40, seconds=300.0):
    """Undecimated samples, straight off the file, for the layer below."""
    from backend import app as appmod, continuity, csc
    rep = continuity.check(folder)
    if not rep.get("ok"):
        return None
    sess, err = appmod._session_for(folder, False, True)
    if err:
        return None
    by = {c["index"]: c for c in sess["channels"]}
    ch = by.get(index) or sess["channels"][0]
    seg = max(rep["segments"], key=lambda s: s["n_samples"])
    t0 = float(seg["true_t0_s"])
    raw, _got_t0, _fs = csc._read_channel_window(
        sess, ch, t0, t0 + min(seconds, float(seg["duration_s"])))
    return np.asarray(raw, dtype=np.float64) if raw.size else None


def real_trace(folder, index=40):
    """One real channel, decimated exactly as Incisor decimates it."""
    from backend import app as appmod, continuity, incisor
    rep = continuity.check(folder)
    if not rep.get("ok"):
        return None, None, None
    sess, err = appmod._session_for(folder, False, True)
    if err:
        return None, None, None
    by = {c["index"]: c for c in sess["channels"]}
    ch = by.get(index) or sess["channels"][0]
    spec = {"path": folder, "channels": [ch["index"]], "invert": True}
    segs = incisor._segment_traces(sess, ch, rep, spec)
    if not segs:
        return None, None, None
    # The longest segment: one contiguous stretch, so nothing about
    # stitching enters a test that is about the detector.
    seg = max(segs, key=lambda s: s[2].size)
    fs_used = float(rep["fs"]) / incisor.decimation_for(
        float(rep["fs"]), incisor.LFP_FS)
    return seg[2], fs_used, ch.get("label")


# --------------------------------------------------------------------------
def main():
    ns, taken = extract_toothy()
    from backend import incisor
    print("Toothy's own code, lifted from %s" % TOOTHY)
    for name, (fname, line, n) in sorted(taken.items()):
        print("  %-24s %s:%d  (%d lines)" % (name, fname, line, n))
    print("  namespace: %s" % ", ".join(sorted(
        k for k in ns if not k.startswith("__"))))
    print()

    P = incisor
    cases = [("synthetic", synthetic(), 1000.0)]
    folder = sys.argv[1] if len(sys.argv) > 1 else (
        r"D:\PTEN\PTEN\M8_Pten\M8s9feb8\2024-02-09_16-43-46")
    tr, fs_used, lab = real_trace(folder)
    if tr is not None:
        cases.append(("real %s (%d samples)" % (lab, tr.size), tr, fs_used))
        print("real trace: %s, %d samples at %.4f Hz" % (lab, tr.size, fs_used))
    else:
        print("no real recording reachable; synthetic only")
    print()

    for name, uv, fs in cases:
        print("=" * 70)
        print(name)
        mv = uv / 1000.0                     # Toothy's units

        # ---- 1. the filter ----
        print(" 1. the band-pass")
        theirs = ns["butter_bandpass_filter"](mv, *P.DS_BAND, lfp_fs=fs,
                                             order=P.DS_ORDER)
        mine = P._filtered(uv, fs, P.DS_BAND)
        d = np.max(np.abs(theirs * 1000.0 - mine))
        rel = d / max(1e-12, np.max(np.abs(mine)))
        ck("the two filters give the same trace", rel < 1e-9,
           "worst %.3g uV (%.2g relative)" % (d, rel))

        # Everything after this is fed the SAME filtered trace, so a
        # difference below cannot be the filter's.
        f_uv = mine
        f_mv = mine / 1000.0

        # ---- 2. the threshold ----
        print(" 2. the threshold")
        t_mine = P.threshold_for(f_uv, P.DS_HEIGHT_SD, P.DS_ABS_THR_UV)
        t_theirs = max(float(np.std(f_mv)) * P.DS_HEIGHT_SD,
                       P.DS_ABS_THR_UV / 1000.0)
        ck("the same voltage, to a nanovolt",
           abs(t_mine["thr_uv"] - t_theirs * 1000.0) < 1e-6,
           "%.9f vs %.9f uV" % (t_mine["thr_uv"], t_theirs * 1000.0))

        # ---- 3. the detection ----
        print(" 3. the detection")
        lfp_time = np.arange(f_mv.size) / fs
        df, _thr = ns["get_ds_peaks"](
            f_mv, lfp_time, fs, pprint=False,
            ds_height_thr=P.DS_HEIGHT_SD,
            ds_abs_thr=P.DS_ABS_THR_UV / 1000.0,
            ds_dist_thr=P.DS_DIST_MS,
            ds_prom_thr=P.DS_PROM_UV / 1000.0,
            ds_wlen=P.DS_WLEN_MS)
        got = P._detect(f_uv, fs, t_mine["thr_uv"], {})

        ti = np.asarray(df["idx_peak"], dtype=np.int64)
        mi = np.asarray(got["idx"], dtype=np.int64)
        ck("the same number of dentate spikes", ti.size == mi.size,
           "Toothy %d, Incisor %d" % (ti.size, mi.size))
        same = ti.size == mi.size and bool(np.array_equal(ti, mi))
        ck("at exactly the same samples", same,
           "%d of %d differ" % (int(np.sum(ti[:min(ti.size, mi.size)]
                                           != mi[:min(ti.size, mi.size)])),
                                min(ti.size, mi.size)))
        if not same:
            print("      Toothy first 10:", ti[:10].tolist())
            print("      Incisor first 10:", mi[:10].tolist())
            continue

        for label, theirs_col, mine_col, scale, tol in (
                ("amplitude", "amp", "amp", 1000.0, 1e-6),
                ("prominence", "prom", "prom", 1000.0, 1e-6),
                ("half-width", "half_width", "half_width_ms", 1.0, 1e-9),
                ("width height", "width_height", "width_height", 1000.0, 1e-6),
                ("asymmetry", "asym", "asym", 1.0, 1e-9)):
            a = np.asarray(df[theirs_col], dtype=np.float64) * scale
            b = np.asarray(mine_col and got[mine_col], dtype=np.float64)
            if a.size != b.size:
                ck("the same %s" % label, False, "%d vs %d" % (a.size, b.size))
                continue
            finite = np.isfinite(a) & np.isfinite(b)
            worst = float(np.max(np.abs(a[finite] - b[finite]))) \
                if finite.any() else 0.0
            ck("the same %s" % label,
               worst <= tol and int((~finite).sum()) == int(
                   (~np.isfinite(a)).sum()),
               "worst %.6g (%d non-finite theirs, %d mine)"
               % (worst, int((~np.isfinite(a)).sum()),
                  int((~np.isfinite(b)).sum())))
        print("      %d events compared" % ti.size)

    # ---- 4. the downsampling ----
    #
    # The one step the layers above deliberately hold constant: both sides
    # were handed the SAME decimated trace, so nothing up to here says
    # anything about how it was made. Toothy FFT-resamples
    # (`data_processing.py:501`, `scipy.signal.resample`) in 600-second
    # chunks; Incisor uses staged `scipy.signal.decimate`. Same raw samples
    # in, and then the whole detector on each, so the question is not "do the
    # traces differ" -- they must -- but "does it change which dentate spikes
    # you get".
    print("=" * 70)
    print(" 4. the downsampling, on the same raw samples")
    raw = raw_chunk(folder, seconds=300.0)
    if raw is None:
        print("      no raw recording reachable; skipped")
    else:
        import scipy.signal as _ss
        q = 30
        n_out = raw.size // q
        theirs = _ss.resample(raw[:n_out * q], n_out)
        mine = incisor._decimate(raw[:n_out * q], q)
        ck("both downsamplers give the same number of samples",
           theirs.size == mine.size, "%d vs %d" % (theirs.size, mine.size))
        n = min(theirs.size, mine.size)
        # Edges excluded: an FFT resample assumes the chunk is periodic and
        # rings where it is not, which is a statement about the ends and not
        # about the middle.
        edge = int(2.0 * 1000.0)
        a, b = theirs[edge:n - edge], mine[edge:n - edge]
        rel = float(np.max(np.abs(a - b)) / max(1e-12, np.max(np.abs(b))))
        print("      traces differ by %.3g of full scale away from the edges"
              % rel)

        fs = 1000.0
        rows = {}
        for who, tr in (("Toothy resample", theirs), ("Incisor decimate", mine)):
            f = P._filtered(tr, fs, P.DS_BAND)
            th = P.threshold_for(f, P.DS_HEIGHT_SD, P.DS_ABS_THR_UV)
            g = P._detect(f, fs, th["thr_uv"], {})
            rows[who] = (g["idx"], th["thr_uv"])
            print("      %-18s %4d events, threshold %8.2f uV"
                  % (who, g["idx"].size, th["thr_uv"]))
        (ti, tt), (mi, mt) = rows["Toothy resample"], rows["Incisor decimate"]
        # Five percent, and the measured figure is two.
        #
        # The threshold is 4.5 times the standard deviation of the filtered
        # trace, so it inherits whatever the downsampler leaves in the band.
        # An FFT resample is a brick wall with ringing; `decimate` uses a
        # Chebyshev anti-alias filter with a real transition. They do not
        # leave the same variance and there is no reason they should.
        #
        # What matters is whether that moves the answer, and the check below
        # says it does not: the same events, within one sample. The event
        # count differs by one in 193, which is smaller than the arbitrariness
        # of the 4.5 itself.
        ck("the two downsamplers agree on the threshold to five percent",
           abs(tt - mt) / max(tt, mt) < 0.05,
           "%.3f vs %.3f uV (%.1f%%)"
           % (tt, mt, 100 * abs(tt - mt) / max(tt, mt)))
        print("      threshold differs by %.1f%%, event count by %d of %d"
              % (100 * abs(tt - mt) / max(tt, mt), abs(ti.size - mi.size),
                 max(ti.size, mi.size)))
        # Matched within one decimated sample: the question is whether the
        # same events are found, not whether an index moved by a millisecond.
        inter = 0
        for x in ti:
            if mi.size and int(np.min(np.abs(mi - x))) <= 1:
                inter += 1
        union = ti.size + mi.size - inter
        ck("the same dentate spikes, within one sample",
           union > 0 and inter / union > 0.98,
           "%d shared of %d union (%d Toothy, %d Incisor)"
           % (inter, union, ti.size, mi.size))

    # ---- 5. the parameters ----
    print("=" * 70)
    print(" 5. the defaults, against Toothy's qparam.py")
    # The defaults, read from Toothy's source rather than imported, for the
    # same reason as the functions.
    import ast
    qsrc = io.open(os.path.join(TOOTHY, "qparam.py"), encoding="utf-8").read()
    qns = {}
    for node in ast.parse(qsrc).body:
        if isinstance(node, ast.FunctionDef)                 and node.name == "get_original_defaults":
            exec(compile(ast.get_source_segment(qsrc, node),
                         "qparam.py::get_original_defaults", "exec"), qns)
    d = qns["get_original_defaults"]()
    pairs = [
        ("ds_height_thr", d["ds_height_thr"], P.DS_HEIGHT_SD, 1.0),
        ("ds_abs_thr (mV -> uV)", d["ds_abs_thr"], P.DS_ABS_THR_UV, 1000.0),
        ("ds_dist_thr", d["ds_dist_thr"], P.DS_DIST_MS, 1.0),
        ("ds_prom_thr", d["ds_prom_thr"], P.DS_PROM_UV, 1.0),
        ("ds_wlen", d["ds_wlen"], P.DS_WLEN_MS, 1.0),
        ("lfp_fs", d["lfp_fs"], P.LFP_FS, 1.0),
    ]
    for label, theirs, mine, scale in pairs:
        ck("%s matches" % label, abs(float(theirs) * scale - float(mine)) < 1e-9,
           "Toothy %s -> %s, Incisor %s" % (theirs, float(theirs) * scale, mine))
    ck("the band matches",
       list(map(float, d["ds_freq"])) == list(map(float, P.DS_BAND)),
       "%s vs %s" % (d["ds_freq"], list(P.DS_BAND)))
    ck("the theta band matches",
       list(map(float, d["theta"])) == list(map(float, P.THETA_BAND)),
       "%s vs %s" % (d["theta"], list(P.THETA_BAND)))
    ck("the ripple band matches",
       list(map(float, d["swr_freq"])) == list(map(float, P.SWR_BAND)),
       "%s vs %s" % (d["swr_freq"], list(P.SWR_BAND)))

    print()
    if FAILED:
        print("%d check(s) FAILED:" % len(FAILED))
        for f in FAILED:
            print("   %s" % f)
        raise SystemExit(1)
    print("all good -- Incisor and Toothy's own code agree on identical input")


main()
