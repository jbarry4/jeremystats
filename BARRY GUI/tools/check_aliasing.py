# -*- coding: utf-8 -*-
"""Is anything aliased into the Monolith's 1-55 Hz?

    python tools\\check_aliasing.py            check, and file the result
                                               where the Monolith page reads it
    python tools\\check_aliasing.py --no-save  check only

Sampling folds everything above half the sampling rate back down, where it
looks exactly like activity at a lower frequency. The Monolith's signals go
through two samplings that could do that:

  1. ACQUISITION. Cheetah samples each wire at its own rate (32 kHz here)
     after a hardware/DSP low-pass. If that low-pass were above half the
     rate, the recording itself would be aliased and nothing afterwards
     could undo it. Read from every CSC header of every folder the
     Monolith used.

  2. DECIMATION. Every trace is brought down to 1000 Hz
     (coupling.decimate_to: staged order-8 Chebyshev, zero phase) and, for
     Granger and the page's traces, on to 250 Hz. Measured on pure tones put
     through the real functions: every tone whose fold lands in 0.5-55 Hz,
     and every mains harmonic, and how much of it survives.

  3. THE DATA. On real stretches of every rat-day (four regions' first
     wires, 60 s each): the 1-55 Hz spectrum through the real chain against
     a reference decimation with a very steep FIR (stopband far below
     anything recorded), and against no anti-alias filter at all (every
     32nd sample) -- the second says how much there was to fold, the first
     how much of it got through.

     The real chain is not flat in its passband: an order-8 Chebyshev
     ripples by 0.05 dB, run forwards and backwards and in two stages, so
     up to 0.2 dB. That is a GAIN, the same on both days and both regions,
     and it cancels from every coupling measure and every within-rat
     change -- but it would read as a difference from the flat reference.
     So the chain's own gain is measured on tones at every frequency the
     spectrum is read at, and taken out before comparing: what remains is
     what folding could have added.

CONTROL: the no-filter decimation must show aliasing on the same data (it
folds what is above 500 Hz into the band), or the comparison could not
have seen any.

Reads E: only. Writes GUI_logs/.cache/monolith/aliasing.json (unless
--no-save), which the page's "What was lost" section shows.
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

import numpy as np                                        # noqa: E402
from scipy.signal import firwin, oaconvolve, welch        # noqa: E402

from backend import coupling, monolith as MO, nlx         # noqa: E402

N = {"ok": 0, "bad": 0}
BAND = (1.0, 55.0)
FS_OUT = 1000.0
GC_FS = 250.0


def check(name, cond, detail=""):
    N["ok" if cond else "bad"] += 1
    print("  %s  %s%s" % ("ok  " if cond else "FAIL", name,
                          "" if cond or not detail else "   [%s]" % (detail,)))
    return cond


def fold(f, fs):
    """Where a frequency f lands after sampling at fs."""
    r = math.fmod(f, fs)
    return min(r, fs - r)


def tone_survival(fs_in, f, fs_out, seconds=12.0):
    """Amplitude (re 1) of a unit tone at f after decimate_to(fs_in ->
    fs_out), measured at its folded frequency over the middle half."""
    n = int(round(seconds * fs_in))
    t = np.arange(n) / fs_in
    x = np.sin(2 * np.pi * f * t)
    y, fo = coupling.decimate_to(x, fs_in, fs_out)
    fa = fold(f, fo)
    m = y.size
    a, b = m // 4, 3 * m // 4
    tt = np.arange(a, b) / fo
    z = np.exp(-2j * np.pi * fa * tt)
    return 2 * abs(np.mean(y[a:b] * z)), fa


def headers(man):
    print("\n1. Acquisition: the hardware filter against half the sampling rate")
    combos, n_files, worst = {}, 0, None
    for d in man["days"]:
        for f in d["folders"]:
            local = f.get("local")
            if not local or not os.path.isdir(local):
                continue
            for name in sorted(os.listdir(local)):
                if not name.upper().startswith("CSC") or not name.lower().endswith(".ncs"):
                    continue
                try:
                    h = nlx.read_header(os.path.join(local, name))
                except OSError:
                    continue
                n_files += 1
                fs = float(h.get("SamplingFrequency") or 0)
                hc = h.get("DspHighCutFrequency")
                en = str(h.get("DspHighCutFilterEnabled", "True"))
                key = (fs, hc, h.get("DspHighCutFilterType"), h.get("DspHighCutNumTaps"),
                       en, h.get("DspLowCutFrequency"))
                combos[key] = combos.get(key, 0) + 1
    rows = []
    for (fs, hc, typ, taps, en, lc), n in sorted(combos.items(), key=lambda x: -x[1]):
        nyq = fs / 2.0
        hcv = float(hc) if hc not in (None, "") else float("nan")
        ok = math.isfinite(hcv) and hcv < nyq and en.lower() not in ("false", "0")
        rows.append({"fs": fs, "high_cut": hcv, "type": typ, "taps": taps, "low_cut": lc,
                     "files": n, "below_nyquist": bool(ok)})
        print("     %5d files: %g Hz, hardware low-pass %s Hz (%s, %s taps), high-pass %s Hz -- %s"
              % (n, fs, hc, typ, taps, lc, "below half the rate" if ok else "NOT below half the rate"))
    check("every CSC header read (%d files)" % n_files, n_files > 0)
    check("every recording's low-pass is below half its sampling rate",
          rows and all(r["below_nyquist"] for r in rows))
    return {"files": n_files, "settings": rows}


def chain():
    print("\n2. Decimation: pure tones through the real functions")
    out = {}
    # fs -> 1000: tones that fold into 0.5-55 Hz, and every mains harmonic
    # that does.
    fs_in = 32000.0
    tones = set()
    for k in range(1, int(fs_in / 2 / FS_OUT) + 1):
        for a in (0.5, 1, 2, 5, 10, 20, 30, 40, 50, 55):
            for f in (k * FS_OUT - a, k * FS_OUT + a):
                if 0 < f < fs_in / 2:
                    tones.add(round(f, 3))
    mains = [60.0 * n for n in range(1, int(fs_in / 2 / 60))
             if 60.0 * n > FS_OUT / 2 and BAND[0] - 0.5 <= fold(60.0 * n, FS_OUT) <= BAND[1]]
    tones |= set(mains)
    t0 = time.time()
    worst, worst_f = 0.0, None
    for f in sorted(tones):
        amp, fa = tone_survival(fs_in, f, FS_OUT)
        if amp > worst:
            worst, worst_f = amp, (f, fa)
    db = 20 * math.log10(max(worst, 1e-15))
    out["to_1000"] = {"fs_in": fs_in, "tones": len(tones), "mains": len(mains), "worst_db": round(db, 1),
                      "worst_at": worst_f, "seconds": round(time.time() - t0, 1)}
    print("     32 kHz -> 1000 Hz: %d tones (%d of them mains harmonics) that fold into the band;"
          " the worst comes through at %.1f dB (%g Hz -> %g Hz)" % (len(tones), len(mains), db,
                                                                   worst_f[0], worst_f[1]))
    check("nothing that folds into 1-55 Hz survives decimation to 1000 Hz above -100 dB", db < -100, db)
    # A control: a tone inside the band passes, changed only by the
    # filters' passband ripple (2 stages x 2 passes x 0.05 dB).
    amp_in, _ = tone_survival(fs_in, 10.0, FS_OUT)
    check("CONTROL: a 10 Hz tone passes, within the filter's ripple (%.3f dB)" % (20 * math.log10(amp_in)),
          abs(20 * math.log10(amp_in)) <= 0.21)
    # 1000 -> 250 (Granger, and the page's traces).
    tones2 = set()
    for k in range(1, int(FS_OUT / 2 / GC_FS) + 1):
        for a in (0.5, 1, 2, 5, 10, 20, 30, 40, 50, 55):
            for f in (k * GC_FS - a, k * GC_FS + a):
                if GC_FS / 2 < f < FS_OUT / 2:
                    tones2.add(round(f, 3))
    mains2 = [60.0 * n for n in range(3, 9) if BAND[0] - 0.5 <= fold(60.0 * n, GC_FS) <= BAND[1]]
    tones2 |= set(mains2)
    worst2, wf2 = 0.0, None
    for f in sorted(tones2):
        amp, fa = tone_survival(FS_OUT, f, GC_FS, seconds=40.0)
        if amp > worst2:
            worst2, wf2 = amp, (f, fa)
    db2 = 20 * math.log10(max(worst2, 1e-15))
    out["to_250"] = {"tones": len(tones2), "mains": mains2, "worst_db": round(db2, 1), "worst_at": wf2}
    print("     1000 Hz -> 250 Hz: %d tones (mains %s) that fold into the band; the worst at %.1f dB (%g Hz -> %g Hz)"
          % (len(tones2), ", ".join("%g" % m for m in mains2), db2, wf2[0], wf2[1]))
    check("nothing that folds into 1-55 Hz survives decimation to 250 Hz above -100 dB", db2 < -100, db2)
    return out


def reference_decimate(x, fs, q):
    """A decimation by q nobody could fault: a 6401-tap Kaiser FIR (beta
    14, cut at 450 Hz for 32 kHz), zero phase by symmetric convolution."""
    h = firwin(6401, 0.9 * (fs / q / 2.0), window=("kaiser", 14.0), fs=fs)
    y = oaconvolve(x, h, mode="same")
    return y[::q]


def passband_gain(fs, freqs):
    """The real chain's own gain (amplitude) at each frequency, on tones."""
    return np.array([tone_survival(fs, float(f), FS_OUT, seconds=12.0)[0] if f > 0 else 1.0 for f in freqs])


def data(man):
    print("\n3. The data: 60 s of four regions' first wires on every rat-day")
    G2 = None
    cmap = coupling.dewey_map()
    regions = ("Right ACC", "Right OFC", "Left DHC", "Left RSC")
    worst_diff, worst_naive, n = 0.0, 0.0, 0
    per = []
    for d in man["days"]:
        spc = next((f for f in d["folders"] if f["role"] == "SPC"), None)
        if not spc or not os.path.isdir(spc.get("local") or ""):
            continue
        t0 = 100.0
        unit = (d.get("units") or [{}])[0].get("pair") or {}
        if unit.get("opener_t"):
            t0 = max(0.0, float(unit["opener_t"]) - 10.0)
        for reg in regions:
            if reg in (d.get("blocked") or {}):
                continue
            ch = cmap[reg][0]
            path = os.path.join(spc["local"], "CSC%d.ncs" % ch)
            if not os.path.isfile(path):
                continue
            x, _start, fs = nlx.read_ncs_range(path, t0, t0 + 60.0)
            x = np.asarray(x, dtype=np.float64)
            q = int(round(fs / FS_OUT))
            if x.size < fs * 30 or abs(fs / q - FS_OUT) > 1e-6:
                continue
            ours, _ = coupling.decimate_to(x, fs, FS_OUT)
            ref = reference_decimate(x, fs, q)
            naive = x[::q]
            m = min(ours.size, ref.size, naive.size)
            cut = int(2 * FS_OUT)                 # leave the filters' edges out
            spec = {}
            for name, y in (("ours", ours), ("ref", ref), ("naive", naive)):
                f, P = welch(y[cut:m - cut], fs=FS_OUT, nperseg=2000)
                spec[name] = P
            sel = (f >= BAND[0]) & (f <= BAND[1])
            if G2 is None:
                G2 = passband_gain(fs, f[sel]) ** 2
                ripple = 10 * np.log10(G2)
                print("     the chain's own passband ripple over 1-55 Hz: %.3f to %.3f dB (taken out below)"
                      % (ripple.min(), ripple.max()))
            d_ours = np.max(np.abs(10 * np.log10(spec["ours"][sel] / G2 / spec["ref"][sel])))
            d_naive = np.max(10 * np.log10(spec["naive"][sel] / spec["ref"][sel]))
            worst_diff = max(worst_diff, float(d_ours))
            worst_naive = max(worst_naive, float(d_naive))
            n += 1
            per.append({"rat": d["rat"], "day": d["day"], "region": reg, "channel": ch,
                        "ours_vs_ref_db": round(float(d_ours), 4), "naive_vs_ref_db": round(float(d_naive), 2)})
        print("     r%d %s: %d channels" % (d["rat"], d["day"], sum(1 for p in per if p["rat"] == d["rat"] and p["day"] == d["day"])))
    print("     %d channels: with its own ripple taken out, the real chain's 1-55 Hz spectrum is within %.4f dB of the"
          " reference everywhere; with no anti-alias filter it would have been up to %.1f dB too high"
          % (n, worst_diff, worst_naive))
    check("read real stretches (%d channels)" % n, n >= 8)
    check("the real chain matches the steep reference in 1-55 Hz within 0.02 dB, its ripple aside (%.4f)" % worst_diff,
          worst_diff < 0.02)
    check("CONTROL: with no anti-alias filter the same data DOES fold into the band (+%.1f dB)" % worst_naive,
          worst_naive > 0.5)
    return {"channels": n, "ours_vs_ref_db": round(worst_diff, 4), "naive_vs_ref_db": round(worst_naive, 2),
            "ripple_db": [round(float(10 * np.log10(G2.min())), 3), round(float(10 * np.log10(G2.max())), 3)]
            if G2 is not None else None, "per": per}


def main():
    save = "--no-save" not in sys.argv
    MO.configure(os.path.join(APP, "GUI_logs"))
    man = MO._read_json(MO._path("manifest.json"))
    if not man:
        print("No Monolith manifest here.")
        return 2
    H = headers(man)
    C = chain()
    Dd = data(man)
    ok = N["bad"] == 0
    hc = sorted({r["high_cut"] for r in H["settings"]})
    say = ("checked: every recording's hardware low-pass (%s Hz) is below half its sampling rate; decimating to 1000 Hz "
           "lets nothing that folds into 1–55 Hz through above %.0f dB (to 250 Hz, %.0f dB); on %d real channels the "
           "1–55 Hz spectrum matches a steep reference within %.3f dB (once the filter’s own %.2f dB passband ripple, "
           "a gain that cancels from every change, is taken out), where no anti-alias filter would have added up to "
           "%.1f dB. Nothing is aliased." % ("/".join("%g" % x for x in hc), C["to_1000"]["worst_db"],
                                           C["to_250"]["worst_db"], Dd["channels"], Dd["ours_vs_ref_db"],
                                           max(abs(x) for x in (Dd.get("ripple_db") or [0])),
                                           Dd["naive_vs_ref_db"])) if ok else (
        "the check found a problem; see tools/check_aliasing.py's output.")
    res = {"ok": ok, "at": MO.now_iso(), "say": say, "headers": H, "chain": C, "data": Dd}
    if save:
        MO._write_json(MO._path("aliasing.json"), res)
        print("\nFiled for the Monolith page: %s" % MO._path("aliasing.json"))
    print("\n%d passed, %d failed" % (N["ok"], N["bad"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
