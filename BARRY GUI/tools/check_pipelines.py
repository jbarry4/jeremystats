# -*- coding: utf-8 -*-
"""Ten real recordings and ten synthetic sets, through both pipelines.

Every stage is printed, and the two questions are kept apart because they
have different answers:

    INDEX match      given the same samples, do the two detectors pick the
                     same ones? This is the detector, and nothing else.

    TIMESTAMP match  what second does each then call that sample? This is
                     the clock, and nothing else.

Conflating them is what made the first round of this comparison unreadable.
A detector that agrees perfectly and a clock that disagrees by 15 ms looks
exactly like a detector that is 15 ms out.

TOOTHY'S CODE
-------------
Extracted from its source and run in a namespace holding numpy, scipy and
pandas -- see `check_against_toothy_code.py` for why it is not imported.
Toothy's time axis is reproduced exactly as `raw_data_pipeline.py:200` builds
it, including the `linspace` quirk, because that is the thing being compared.

Run: python tools/check_pipelines.py
"""
import ast
import io
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOTHY = r"C:\Users\Z390\Desktop\jeremystats\Toothy\Toothy-main"
sys.path.insert(0, ROOT)

N_REAL = 10
N_SYNTH = 10
FAILED = []


def ck(name, ok, detail=""):
    print("    %-5s %s%s" % ("ok" if ok else "FAIL", name,
                             "" if ok else "   [%s]" % detail))
    if not ok:
        FAILED.append(name)


def extract_toothy():
    """Toothy's own functions, off its source, with no Qt."""
    import pandas as pd
    import scipy
    import scipy.signal                                   # noqa: F401
    ns = {"np": np, "numpy": np, "scipy": scipy, "pd": pd, "pandas": pd}
    want = {"ephys.py": ("get_asym", "get_ds_peaks"),
            "pyfx.py": ("butter_bandpass", "butter_bandpass_filter")}
    for fname, names in want.items():
        src = io.open(os.path.join(TOOTHY, fname), encoding="utf-8").read()
        for node in ast.parse(src).body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                exec(compile(ast.get_source_segment(src, node),
                             "%s::%s" % (fname, node.name), "exec"), ns)
    return ns


def toothy_time(n, lfp_fs):
    """Toothy's time axis, exactly as it builds it.

        raw_data_pipeline.py:200
        lfp_time = np.linspace(0, NSAMPLES_DN_TRUNC/lfp_fs, NSAMPLES_DN_TRUNC)

    Note the off-by-one that is baked in: `linspace` with N points spanning
    0 to N/fs puts them N/(fs*(N-1)) apart, not 1/fs. On 1.76 million
    samples that is a factor of 1 + 5.7e-7, which is a millisecond by the
    end of a half-hour recording -- before any gap is considered.
    """
    return np.linspace(0, n / lfp_fs, n)


# --------------------------------------------------------------------------
# The pipelines, said out loud
# --------------------------------------------------------------------------
def show_pipelines(P):
    print("=" * 78)
    print("THE TWO PIPELINES")
    print("=" * 78)
    rows = [
        ("read",
         "spikeinterface NeuralynxRecordingExtractor, 600 s chunks",
         "nlx.read_ncs_range, 120 s chunks, walked in samples"),
        ("scale",
         "raw / 1000  ->  millivolts",
         "raw * adbitvolts * 1e6  ->  microvolts"),
        ("polarity",
         "none",
         "inverted (nlx.py:157, lab convention); explicit in the spec"),
        ("downsample",
         "scipy.signal.resample (FFT) to 1000 Hz, per 600 s chunk",
         "scipy.signal.decimate staged 5x6, per 120 s chunk, 1 s margin"),
        ("gaps",
         "none -- samples concatenated, gaps invisible",
         "segmented; each segment filtered and detected separately"),
        ("filter",
         "butter(3, [5,100], sos); sosfiltfilt padtype='odd'",
         "identical -- same call, same order, same padtype"),
        ("threshold",
         "max(4.5 * std(whole filtered trace), 0.3 mV)",
         "identical, in microvolts: max(4.5 * std, 300 uV)"),
        ("detect",
         "find_peaks(height=thr, distance=100 ms, prominence=0)",
         "identical"),
        ("shape",
         "peak_widths(rel_height=0.5, wlen=125 ms); asym on int edges",
         "identical, including the int cast"),
        ("time",
         "linspace(0, N/1000, N)[idx]  -- index over a nominal rate",
         "continuity.sample_to_true(seg_start + idx*30)  -- record clock"),
    ]
    print("%-11s %-44s %s" % ("stage", "TOOTHY", "INCISOR"))
    print("-" * 78)
    for stage, a, b in rows:
        print("%-11s %s" % (stage, a))
        print("%-11s %s" % ("", b))
        print()


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------
def synthetic(seed, fs=1000.0):
    """Ten different recordings, not ten runs of one.

    The seed changes the noise, the event times and the amplitudes; the other
    knobs change the character -- how much theta, how many spikes, how big,
    how noisy -- so the comparison covers a quiet channel with four spikes
    and a loud one with eight hundred, not one comfortable middle case.
    """
    rng = np.random.default_rng(1000 + seed)
    n = int(rng.integers(120000, 900000))
    noise = float(rng.uniform(20, 160))
    rate = float(rng.uniform(0.05, 1.2))          # spikes per second
    amp_lo = float(rng.uniform(80, 400))
    amp_hi = amp_lo + float(rng.uniform(100, 2500))
    theta = float(rng.uniform(0, 400))

    t = np.arange(n) / fs
    x = rng.normal(0, noise, n)
    x += theta * np.sin(2 * np.pi * rng.uniform(5, 10) * t)
    x += 400 * np.sin(2 * np.pi * 0.3 * t)
    n_ev = max(1, int(rate * n / fs))
    at = np.sort(rng.choice(np.arange(200, n - 200), size=min(n_ev, n // 400),
                            replace=False))
    w = rng.uniform(6, 18) * fs / 1000.0
    for i in at:
        a = rng.uniform(amp_lo, amp_hi)
        lo, hi = max(0, int(i - 4 * w)), min(n, int(i + 4 * w))
        x[lo:hi] += a * np.exp(-((np.arange(lo, hi) - i) ** 2) / (2 * w ** 2))
    label = ("%d samples, noise %.0f uV, %d planted, theta %.0f uV"
             % (n, noise, at.size, theta))
    return x, fs, label


def real_cases(limit):
    """One channel from each of `limit` reachable recordings."""
    import json
    import urllib.request
    from backend import app as appmod, continuity, incisor
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:8791/api/registry", timeout=300) as fh:
            reg = json.loads(fh.read())
    except Exception as exc:                              # noqa: BLE001
        print("no registry (%s)" % exc)
        return []
    out = []
    for p in reg.get("tree", []):
        for m in p.get("mice", []):
            for s in m.get("sessions", []):
                path = (s.get("here") or [None])[0]
                if not path:
                    continue
                try:
                    rep = continuity.check(path)
                    if not rep.get("ok"):
                        continue
                    sess, err = appmod._session_for(path, False, True)
                    if err:
                        continue
                    chans = sess["channels"]
                    ch = chans[min(40, len(chans) - 1)]
                    spec = {"path": path, "channels": [ch["index"]],
                            "invert": True}
                    segs = incisor._segment_traces(sess, ch, rep, spec)
                    if not segs:
                        continue
                    seg = max(segs, key=lambda x: x[2].size)
                except Exception as exc:                  # noqa: BLE001
                    print("  skipped %s (%s)" % (s.get("label"), exc))
                    continue
                q = incisor.decimation_for(float(rep["fs"]), incisor.LFP_FS)
                out.append({
                    "label": "%s %s" % (s.get("label"), ch.get("label")),
                    "trace": seg[2], "fs": float(rep["fs"]) / q,
                    "rep": rep, "seg_start": seg[1], "q": q,
                    "segments": rep["n_segments"],
                    "lost": rep.get("seconds_lost") or 0.0,
                })
                if len(out) >= limit:
                    return out
    return out


# --------------------------------------------------------------------------
def compare(ns, P, uv, fs, rep=None, seg_start=0, q=30):
    """One trace through both, returning the two agreement measures."""
    mv = uv / 1000.0
    # Both filter the same input with the same call, checked rather than
    # assumed -- if this ever diverges, nothing below means anything.
    theirs_f = ns["butter_bandpass_filter"](mv, *P.DS_BAND, lfp_fs=fs,
                                            order=P.DS_ORDER)
    mine_f = P._filtered(uv, fs, P.DS_BAND)
    filt_rel = float(np.max(np.abs(theirs_f * 1000.0 - mine_f))
                     / max(1e-12, np.max(np.abs(mine_f))))

    lfp_time = toothy_time(mine_f.size, fs)
    df, _ = ns["get_ds_peaks"](
        mine_f / 1000.0, lfp_time, fs, pprint=False,
        ds_height_thr=P.DS_HEIGHT_SD, ds_abs_thr=P.DS_ABS_THR_UV / 1000.0,
        ds_dist_thr=P.DS_DIST_MS, ds_prom_thr=P.DS_PROM_UV / 1000.0,
        ds_wlen=P.DS_WLEN_MS)
    thr = P.threshold_for(mine_f, P.DS_HEIGHT_SD, P.DS_ABS_THR_UV)
    got = P._detect(mine_f, fs, thr["thr_uv"], {})

    ti = np.asarray(df["idx_peak"], dtype=np.int64)
    mi = np.asarray(got["idx"], dtype=np.int64)
    same_idx = ti.size == mi.size and bool(np.array_equal(ti, mi))

    # ---- the timestamps ----
    t_theirs = np.asarray(df["time"], dtype=np.float64)
    if rep is not None:
        from backend import continuity
        t_mine = np.array([continuity.sample_to_true(rep, seg_start + int(j) * q)
                           for j in mi], dtype=np.float64)
        # Toothy's axis starts at zero for the concatenated recording, so a
        # segment that is not the first one has to be put on the same origin
        # before the numbers can be subtracted.
        base = continuity.sample_to_true(rep, seg_start) or 0.0
        t_mine = t_mine - base
    else:
        t_mine = mi / fs
    d = (t_mine - t_theirs) if same_idx and t_theirs.size == t_mine.size \
        else np.array([])
    return {
        "n_theirs": ti.size, "n_mine": mi.size, "same_idx": same_idx,
        "filt_rel": filt_rel, "thr": thr["thr_uv"],
        "dt": d, "ti": ti, "mi": mi,
    }


def main():
    ns = extract_toothy()
    from backend import incisor as P
    show_pipelines(P)

    print("=" * 78)
    print("TEN SYNTHETIC RECORDINGS")
    print("=" * 78)
    print("%-3s %-52s %6s %6s %7s" % ("#", "recording", "Toothy", "Incisor",
                                      "same?"))
    syn_rows = []
    for k in range(N_SYNTH):
        uv, fs, label = synthetic(k)
        r = compare(ns, P, uv, fs)
        syn_rows.append(r)
        print("%-3d %-52s %6d %6d %7s"
              % (k + 1, label[:52], r["n_theirs"], r["n_mine"],
                 "yes" if r["same_idx"] else "NO"))
    ck("every synthetic recording finds the same peaks",
       all(r["same_idx"] for r in syn_rows),
       "%d of %d differ" % (sum(1 for r in syn_rows if not r["same_idx"]),
                            len(syn_rows)))
    ck("and the filters never diverge",
       all(r["filt_rel"] < 1e-9 for r in syn_rows),
       "worst %.2g" % max(r["filt_rel"] for r in syn_rows))
    tot = sum(r["n_mine"] for r in syn_rows)
    print("    %d events across %d synthetic recordings" % (tot, N_SYNTH))

    print()
    print("=" * 78)
    print("TEN REAL RECORDINGS")
    print("=" * 78)
    cases = real_cases(N_REAL)
    if not cases:
        print("  none reachable")
    print("%-34s %5s %5s %6s %6s %6s %9s"
          % ("recording", "segs", "lost", "Toothy", "Incisor", "same?",
             "dt median"))
    real_rows = []
    for c in cases:
        r = compare(ns, P, c["trace"], c["fs"], c["rep"], c["seg_start"],
                    c["q"])
        r["label"] = c["label"]
        r["map_fs"] = c["rep"].get("map_fs")
        r["hdr_fs"] = c["rep"].get("fs")
        r["n_samples"] = int(c["trace"].size)
        real_rows.append(r)
        dtm = (np.median(r["dt"]) * 1e3) if r["dt"].size else float("nan")
        print("%-34s %5d %5.2f %6d %6d %6s %7.2f ms"
              % (c["label"][:34], c["segments"], c["lost"], r["n_theirs"],
                 r["n_mine"], "yes" if r["same_idx"] else "NO", dtm))

    if real_rows:
        ck("every real recording finds the same peaks",
           all(r["same_idx"] for r in real_rows),
           "%d of %d differ" % (sum(1 for r in real_rows if not r["same_idx"]),
                                len(real_rows)))
        ck("and the filters never diverge",
           all(r["filt_rel"] < 1e-9 for r in real_rows),
           "worst %.2g" % max(r["filt_rel"] for r in real_rows))
        tot = sum(r["n_mine"] for r in real_rows)
        print("    %d events across %d real recordings" % (tot, len(real_rows)))

        print()
        print("-" * 78)
        print("THE TIMESTAMP DIFFERENCE, on identical peaks")
        print("-" * 78)
        print("Same sample, two clocks. Toothy calls it index/1000 on a")
        print("linspace axis; Incisor calls it what the .ncs record says.")
        print()
        print("%-30s %8s %8s %8s %8s %8s %8s"
              % ("recording", "median", "p95", "worst", "observed",
                 "clock", "linspace"))
        print("%-30s %8s %8s %8s %8s %8s %8s"
              % ("", "", "", "", "ppm", "ppm", "ppm"))
        alld, row_ppm = [], []
        for r in real_rows:
            if not r["dt"].size:
                continue
            d = r["dt"] * 1e3
            alld.append(r["dt"])
            # A difference that grows with time is a rate disagreement.
            idx = r["mi"].astype(float)
            ppm = (np.polyfit(idx / 1000.0, r["dt"], 1)[0] * 1e6
                   if idx.size > 8 and np.ptp(idx) > 1000 else float("nan"))
            # What the recording's OWN clock says, independent of any
            # event: the rate fitted to its record timestamps against the
            # 30000 the header claims and Toothy assumes. If the observed
            # drift is this, the timestamp difference is the rig's crystal
            # and nothing else.
            clock_ppm = ((r.get("map_fs") or 0) / (r.get("hdr_fs") or 1)
                         - 1.0) * 1e6 if r.get("map_fs") else float("nan")
            # And Toothy's own linspace off-by-one, which is a real part of
            # the answer on a short recording: N points spanning 0..N/fs sit
            # N/(fs*(N-1)) apart, not 1/fs.
            lin_ppm = (1e6 / max(1, r.get("n_samples", 1) - 1))
            print("%-30s %7.2fms %7.2fms %7.2fms %8.2f %8.2f %8.2f"
                  % (r["label"][:30], np.median(d),
                     np.percentile(np.abs(d), 95), np.max(np.abs(d)),
                     ppm, clock_ppm, lin_ppm))
            row_ppm.append((ppm, clock_ppm + lin_ppm))
        if row_ppm:
            a = np.array([x for x, _ in row_ppm])
            b = np.array([y for _, y in row_ppm])
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() > 2:
                print()
                print("    observed drift vs (clock + linspace): "
                      "mean gap %.2f ppm, worst %.2f ppm"
                      % (float(np.mean(np.abs(a[ok] + b[ok]))),
                         float(np.max(np.abs(a[ok] + b[ok])))))
                ck("the timestamp drift IS the rig's clock plus Toothy's "
                   "linspace, not a detector difference",
                   float(np.mean(np.abs(a[ok] + b[ok]))) < 6.0,
                   "mean gap %.2f ppm" % float(np.mean(np.abs(a[ok] + b[ok]))))
        if alld:
            every = np.concatenate(alld) * 1e3
            print()
            print("    all %d events: median %+.2f ms, p95 %.2f ms, "
                  "worst %.2f ms" % (every.size, np.median(every),
                                     np.percentile(np.abs(every), 95),
                                     np.max(np.abs(every))))

    print()
    if FAILED:
        print("%d check(s) FAILED: %s" % (len(FAILED), ", ".join(FAILED)))
        raise SystemExit(1)
    print("all good")


main()
